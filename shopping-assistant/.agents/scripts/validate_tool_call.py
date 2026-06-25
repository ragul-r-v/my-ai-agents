#!/usr/bin/env python3
"""
.agents/scripts/validate_tool_call.py

PreToolUse gate for run_command executions.

The Gemini CLI / agents-cli hook system passes the pending tool call as a
JSON object on stdin before the tool is executed. This script inspects the
command and either:

  - exits 0  → allow the execution to proceed
  - exits 1  → block the execution; the JSON written to stdout becomes the
               error message shown to the agent

Blocked command classes (per CONTEXT.md "No Shell Execution" policy):
  • Network fetchers:   curl, wget, Invoke-WebRequest, Invoke-RestMethod
  • Package installers: pip, pip3, npm, yarn, pnpm, cargo, gem
  • Privilege escalation: sudo, runas
  • Destructive ops:    rm -rf /, format, del /f /s /q
"""

from __future__ import annotations

import json
import re
import sys

# ---------------------------------------------------------------------------
# Policy: blocked command prefixes / patterns
# ---------------------------------------------------------------------------

BLOCKED_PREFIXES: tuple[str, ...] = (
    "curl",
    "wget",
    "pip ",
    "pip3 ",
    "npm install",
    "yarn add",
    "pnpm add",
    "cargo install",
    "gem install",
    "sudo",
    "runas",
)

BLOCKED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+-rf\s+/"),          # rm -rf /
    re.compile(r"\bdel\s+/f\s+/s\s+/q"),    # del /f /s /q (Windows)
    re.compile(r"\bformat\s+[A-Za-z]:"),     # format C: (Windows)
    re.compile(r"Invoke-WebRequest", re.I),  # PowerShell web fetch
    re.compile(r"Invoke-RestMethod", re.I),  # PowerShell REST call
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_blocked(command: str) -> str | None:
    """Return a reason string if the command is blocked, else None."""
    cmd_lower = command.lower().strip()

    for prefix in BLOCKED_PREFIXES:
        if cmd_lower.startswith(prefix.lower()):
            return f"Command starts with blocked prefix '{prefix}'"

    for pattern in BLOCKED_PATTERNS:
        if pattern.search(command):
            return f"Command matches blocked pattern '{pattern.pattern}'"

    return None


def _block(reason: str, command: str) -> None:
    """Write a structured block response to stdout and exit 1."""
    response = {
        "error": "run_command blocked by PreToolUse policy",
        "reason": reason,
        "command": command,
        "remediation": (
            "Per .agents/CONTEXT.md 'No Shell Execution' policy, this command "
            "class requires explicit approval in hooks.json before it can run. "
            "If this command is genuinely needed, add it to the allow-list in "
            "hooks.json and commit the change for review."
        ),
    }
    print(json.dumps(response, indent=2))
    sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    # The hook framework pipes the tool-call payload as JSON on stdin.
    raw = sys.stdin.read().strip()

    if not raw:
        # No payload — allow through (nothing to inspect)
        sys.exit(0)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        # Malformed input — fail open (allow) with a warning to stderr
        print("validate_tool_call: could not parse stdin as JSON", file=sys.stderr)
        sys.exit(0)

    # The tool call payload shape:  {"tool": "run_command", "input": {"command": "..."}}
    tool_input = payload.get("input", {})
    command: str = tool_input.get("command", "") or tool_input.get("CommandLine", "")

    if not command:
        # No command found in payload — allow through
        sys.exit(0)

    reason = _is_blocked(command)
    if reason:
        _block(reason, command)

    # Command is allowed — exit 0 silently
    sys.exit(0)


if __name__ == "__main__":
    main()
