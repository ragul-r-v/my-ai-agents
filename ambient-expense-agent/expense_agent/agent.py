# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Ambient agent that processes expense report events with security controls.

This agent receives expense events via ADK trigger endpoints (Pub/Sub)
and routes them through a graph-based workflow:

- Expenses under $100 are auto-approved immediately.
- Expenses of $100 or more go through a security checkpoint:
  - Description is scrubbed of PII (SSNs and Credit Cards).
  - Description is scanned for prompt injection attacks.
  - Clean expenses continue to the LLM reviewer.
  - Suspicious expenses bypass the LLM reviewer and route straight to a manager.
"""

import base64
import json
import re
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.agents import Agent
from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.adk.events import EventActions
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.workflow import Workflow
from pydantic import BaseModel, Field

from .config import config

# Regular expressions for scrubbing PII
SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CC_REGEX = re.compile(r"\b(?:\d[ -]?){13,16}\b")

# Keywords indicative of prompt injection attacks
INJECTION_KEYWORDS = [
    "ignore previous",
    "ignore instructions",
    "bypass",
    "override",
    "system prompt",
    "auto-approve",
    "auto approve",
    "force approve",
    "you are now",
    "developer mode",
]


# ---------------------------------------------------------------------------
# Pydantic schemas for structured data flow between nodes
# ---------------------------------------------------------------------------


class ExpenseData(BaseModel):
    """Expense report data extracted from the incoming email event."""

    amount: float = Field(description="Expense amount in USD")
    submitter: str = Field(description="Email of the person who submitted")
    category: str = Field(description="Expense category, e.g. travel, meals")
    description: str = Field(description="What the expense is for")
    date: str = Field(description="Date of the expense (YYYY-MM-DD)")


# ---------------------------------------------------------------------------
# Function nodes
# ---------------------------------------------------------------------------


def parse_expense_email(node_input: str) -> Event:
    """Parse a Pub/Sub trigger event and extract expense data.

    The trigger endpoint delivers the raw Pub/Sub message JSON. The
    expense payload lives in the ``data`` field, which may be
    base64-encoded (real Pub/Sub) or plain JSON (local testing).
    """
    try:
        event = json.loads(node_input)
    except json.JSONDecodeError:
        return Event(output={"error": f"Invalid JSON: {node_input[:200]}"})

    data = event.get("data", {})

    if isinstance(data, str):
        try:
            data = json.loads(base64.b64decode(data).decode("utf-8"))
        except Exception:
            return Event(output={"error": f"Failed to decode data: {data[:200]}"})

    return Event(
        output={
            "amount": float(data.get("amount", 0)),
            "submitter": data.get("submitter", "unknown"),
            "category": data.get("category", "other"),
            "description": data.get("description", ""),
            "date": data.get("date", ""),
        }
    )


def route_by_amount(node_input: dict[str, Any], ctx: Context) -> Event:
    """Route expenses based on the configured dollar threshold.

    Returns a routing event that the workflow uses to pick the next
    node: ``AUTO_APPROVE`` for amounts under the threshold, ``NEEDS_REVIEW``
    for amounts equal to or above it.

    Also stores the expense data in workflow state so the HITL
    approval node can include it in the RequestInput payload.
    """
    ctx.state["expense_data"] = node_input
    amount = node_input.get("amount", 0.0)
    if amount >= config.review_threshold:
        return Event(output=node_input, actions=EventActions(route="NEEDS_REVIEW"))
    return Event(output=node_input, actions=EventActions(route="AUTO_APPROVE"))


def security_checkpoint(node_input: dict[str, Any], ctx: Context) -> Event:
    """Scrubs personal data (SSNs/Credit Cards) and flags prompt injections."""
    description = node_input.get("description", "")
    category = node_input.get("category", "")

    # 1. Scrub Personal Data (PII)
    redacted_desc = description
    redacted_desc, ssn_count = SSN_REGEX.subn("[SSN_REDACTED]", redacted_desc)
    redacted_desc, cc_count = CC_REGEX.subn("[CREDIT_CARD_REDACTED]", redacted_desc)

    # Save cleaned payload so model and human approval logs remain safe
    cleaned_expense = dict(node_input)
    cleaned_expense["description"] = redacted_desc
    ctx.state["expense_data"] = cleaned_expense

    if ssn_count > 0 or cc_count > 0:
        redacted_categories = ctx.state.setdefault("redacted_categories", [])
        if category not in redacted_categories:
            redacted_categories.append(category)

    # 2. Defend against prompt injection
    desc_lower = description.lower()
    has_injection = any(keyword in desc_lower for keyword in INJECTION_KEYWORDS)

    if has_injection:
        ctx.state["security_alert"] = True
        log_entry = {
            "severity": "CRITICAL",
            "message": (
                f"Security Alert: Prompt injection detected in expense "
                f"submitted by {node_input.get('submitter', 'unknown')}"
            ),
            "alert_type": "security_violation",
            "description": description,
        }
        print(json.dumps(log_entry), flush=True)
        # Bypass LLM review and route straight to manager approval
        return Event(
            output=cleaned_expense,
            actions=EventActions(route="BYPASS_REVIEW"),
        )

    # Route clean expense to LLM review
    return Event(
        output=cleaned_expense,
        actions=EventActions(route="CONTINUE_TO_REVIEW"),
    )


def auto_approve(node_input: dict[str, Any]) -> Event:
    """Auto-approve a low-value expense and log the decision."""
    log_entry = {
        "severity": "INFO",
        "message": (
            f"Expense auto-approved: ${node_input['amount']:.2f}"
            f" from {node_input['submitter']}"
        ),
        "decision": "approved",
        "amount": node_input["amount"],
        "submitter": node_input["submitter"],
        "category": node_input["category"],
    }
    print(json.dumps(log_entry), flush=True)
    return Event(output={"status": "approved", **node_input})


# ---------------------------------------------------------------------------
# LLM review agent (invoked only for expenses >= threshold)
# ---------------------------------------------------------------------------


def emit_expense_alert(
    submitter: str,
    amount: float,
    category: str,
    risk_summary: str,
) -> dict[str, Any]:
    """Emit a structured log alerting finance to review a high-value expense.

    Args:
        submitter: Who submitted the expense.
        amount: The expense amount in USD.
        category: The expense category.
        risk_summary: Why this expense needs review.

    Returns:
        Confirmation that the alert was emitted.
    """
    log_entry = {
        "severity": "WARNING",
        "message": (
            f"Expense review alert: ${amount:.2f} from {submitter} — {risk_summary}"
        ),
        "alert_type": "expense_review",
        "submitter": submitter,
        "amount": amount,
        "category": category,
        "risk_summary": risk_summary,
    }
    print(json.dumps(log_entry), flush=True)
    return {"status": "alert_emitted", "submitter": submitter, "amount": amount}


review_agent = Agent(
    name="review_agent",
    model=config.model,
    mode="single_turn",
    instruction="""You are an expense review agent. You receive expense reports
of $100 or more that need review before approval.

Analyze the expense and:
1. Check for risk factors: unusual category for the amount, vague description,
   suspiciously round numbers, very high value (>$1000), or potential policy
   violations.
2. Call the `emit_expense_alert` tool with the submitter, amount, category,
   and a brief risk summary explaining why this expense needs human review.
3. Return a structured review.

Your review MUST include:
- **Amount**: The expense amount
- **Submitter**: Who submitted it
- **Category**: The expense category
- **Risk level**: low, medium, or high
- **Risk factors**: What flags you found (if any)
- **Recommendation**: approve, request-more-info, or escalate""",
    input_schema=ExpenseData,
    tools=[emit_expense_alert],
)


# ---------------------------------------------------------------------------
# HITL: pause the workflow for human approval
# ---------------------------------------------------------------------------


async def request_approval(
    node_input: Any, ctx: Context
) -> AsyncGenerator[RequestInput, None]:
    """Pause the workflow and wait for a human to approve or reject.

    Yields a ``RequestInput`` that the ADK runtime surfaces to the UI.
    The workflow stays paused until someone resumes the session (via the
    approval UI or ``POST /run``). The human's response becomes the
    output of this node and flows into ``process_decision``.
    """
    expense = ctx.state.get("expense_data", {})
    message = "Expense requires manager approval. Approve or reject."
    if ctx.state.get("security_alert"):
        message = "WARNING: Security Alert triggered on this expense! Review carefully before approving."

    yield RequestInput(
        interrupt_id="approve",
        message=message,
        payload=expense,
    )


def process_decision(node_input: Any, ctx: Context) -> Event:
    """Process the human's approval decision and log the outcome."""
    decision = "unknown"
    if isinstance(node_input, dict):
        decision = node_input.get("decision", "unknown")
    elif isinstance(node_input, str):
        decision = "approve" if "approve" in node_input.lower() else "reject"

    approved = decision == "approve"
    expense = ctx.state.get("expense_data", {})
    status = "approved" if approved else "rejected"
    security_alert = ctx.state.get("security_alert", False)

    log_entry = {
        "severity": "INFO" if approved and not security_alert else "WARNING",
        "message": f"Expense {status} by manager",
        "decision": status,
        "security_alert": security_alert,
    }
    print(json.dumps(log_entry), flush=True)

    submitter = expense.get("submitter", "unknown")
    amount = expense.get("amount", 0.0)
    category = expense.get("category", "")
    description = expense.get("description", "")
    date = expense.get("date", "")

    parts = [f"${amount:.2f} expense from {submitter} has been {status}."]
    if security_alert:
        parts.append("[SECURITY WARNING: Prompt injection was flagged on this report.]")
    if description:
        parts.append(f'"{description}" ({category}) on {date}.')
    if approved:
        parts.append(
            "The expense has been logged and will be processed for reimbursement."
        )
    else:
        parts.append(
            "The submitter will be notified and may resubmit with additional documentation."
        )

    return Event(output={"status": status, "message": " ".join(parts)})


# ---------------------------------------------------------------------------
# Graph-based workflow — the root agent
# ---------------------------------------------------------------------------

root_agent = Workflow(
    name="expense_processor",
    edges=[
        ("START", parse_expense_email, route_by_amount),
        (
            route_by_amount,
            {
                "AUTO_APPROVE": auto_approve,
                "NEEDS_REVIEW": security_checkpoint,
            },
        ),
        (
            security_checkpoint,
            {
                "BYPASS_REVIEW": request_approval,
                "CONTINUE_TO_REVIEW": review_agent,
            },
        ),
        (review_agent, request_approval),
        (request_approval, process_decision),
    ],
)

# Define App with ResumabilityConfig enabled for Human-in-the-loop support
app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True),
)
