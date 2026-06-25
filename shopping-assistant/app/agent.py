# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shopping Assistant — ADK 2.0 agent definition.

NOTE: The api_key below is intentionally hardcoded to demonstrate
automated pre-commit security gating (semgrep will flag it).
In a real deployment, use Secret Manager or environment variables.
"""

import os
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.tools import list_available_products, redeem_discount_code

load_dotenv()

# google-adk Gemini() stubs are incomplete — kwargs are valid at runtime.
_model = Gemini(
    model="gemini-2.5-flash",
    retry_options=types.HttpRetryOptions(attempts=3),
)

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
root_agent = Agent(
    name="shopping_assistant",
    model=_model,
    instruction=(
        "You are a friendly and knowledgeable AI shopping assistant for a "
        "retail store. Your goals are:\n"
        "1. Help customers discover products using `list_available_products`.\n"
        "2. Apply discount codes via `redeem_discount_code` — always ask for "
        "   the customer's registered user ID before attempting redemption.\n"
        "3. Answer questions about products, pricing, and promotions clearly "
        "   and honestly.\n"
        "4. If a discount code has already been redeemed, inform the customer "
        "   politely and suggest they check for other promotions.\n\n"
        "Always be concise, helpful, and professional."
    ),
    tools=[list_available_products, redeem_discount_code],
)

# ---------------------------------------------------------------------------
# App wrapper (name must match the package directory — 'app')
# ---------------------------------------------------------------------------
app = App(
    root_agent=root_agent,
    name="app",
)
