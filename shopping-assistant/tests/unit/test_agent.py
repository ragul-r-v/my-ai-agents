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
"""
Security boundary & business logic test suite for the discount redemption tool.

Test strategy
-------------
These are deterministic unit tests of the tool *function* — they do NOT call
the LLM and do NOT assert on LLM response text.  All assertions are on the
return values of `redeem_discount_code` and `list_available_products`, which
are pure Python functions.

Threat-model coverage (from threat_model.md)
--------------------------------------------
  S-1  Spoofing        — unauthenticated / empty user_id must be rejected
  T-1  Tampering       — in-memory store state must be isolated between tests
  T-2  Tampering       — raw string inputs must be normalised safely
  R-1  Repudiation     — redemption state must be recorded on the entry itself
  E-2  Elev. of Priv.  — tool-level guard must fire independent of LLM prompt

State isolation
---------------
`_DISCOUNT_CODES` is a mutable module-level dict.  Every test that mutates it
uses the `fresh_codes` fixture, which patches the dict back to its pristine
state via `monkeypatch.setitem` / `monkeypatch.setattr` so tests cannot bleed
into each other.
"""

from __future__ import annotations

import copy

import pytest

import app.tools as tools_module
from app.tools import list_available_products, redeem_discount_code

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PRISTINE_CODES: dict = {
    "WELCOME50": {"discount_pct": 50, "redeemed": False, "redeemed_by": None},
    "SUMMER20": {"discount_pct": 20, "redeemed": False, "redeemed_by": None},
}


@pytest.fixture(autouse=True)
def fresh_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset _DISCOUNT_CODES to pristine state before every test.

    Uses a deep copy so mutations in one test cannot affect another,
    even if the fixture teardown order is non-deterministic.
    """
    monkeypatch.setattr(tools_module, "_DISCOUNT_CODES", copy.deepcopy(_PRISTINE_CODES))


# ---------------------------------------------------------------------------
# Security Boundaries & Assertions (TDD Planning Gate — CONTEXT.md)
# ---------------------------------------------------------------------------
# Edge cases that could exploit the redeem_discount_code tool:
#   1. Empty user_id (bypasses the "registered user" requirement)
#   2. Whitespace-only user_id (normalisation bypass attempt)
#   3. Unknown / fabricated discount codes
#   4. Re-use of an already-redeemed code (single-use enforcement)
#   5. Concurrent redemption of the same code by two different users
#   6. Code string injection via mixed case, leading/trailing whitespace
#   7. Extremely long inputs (no max-length guard yet — document as known gap)
# ---------------------------------------------------------------------------


class TestSpoofing:
    """S-1: user_id must refer to a registered user — empty values must fail."""

    def test_empty_user_id_is_rejected(self) -> None:
        result = redeem_discount_code("WELCOME50", "")
        assert "failed" in result.lower(), (
            "Empty user_id must be rejected — tool must not redeem for anonymous callers"
        )
        # Confirm state was NOT mutated (code still available)
        assert tools_module._DISCOUNT_CODES["WELCOME50"]["redeemed"] is False

    def test_whitespace_only_user_id_is_rejected(self) -> None:
        result = redeem_discount_code("WELCOME50", "   ")
        assert "failed" in result.lower(), (
            "Whitespace-only user_id must be treated as empty — normalisation bypass blocked"
        )
        assert tools_module._DISCOUNT_CODES["WELCOME50"]["redeemed"] is False

    def test_user_id_is_recorded_on_success(self) -> None:
        """R-1 overlap: the redeemed_by field must be set so transactions are attributable."""
        redeem_discount_code("WELCOME50", "user-abc-123")
        entry = tools_module._DISCOUNT_CODES["WELCOME50"]
        assert entry["redeemed_by"] == "user-abc-123", (
            "redeemed_by must record the user_id for audit purposes"
        )

    def test_user_id_is_stripped_before_recording(self) -> None:
        """Leading/trailing whitespace in user_id must be stripped — no ghost identities."""
        redeem_discount_code("WELCOME50", "  user-xyz  ")
        entry = tools_module._DISCOUNT_CODES["WELCOME50"]
        assert entry["redeemed_by"] == "user-xyz"


class TestTampering:
    """T-1 / T-2: Inputs must be normalised; store state must only change on valid requests."""

    def test_unknown_code_is_rejected(self) -> None:
        result = redeem_discount_code("FAKECODE99", "user-1")
        assert "failed" in result.lower() or "not recognised" in result.lower(), (
            "Unknown codes must be rejected without mutating store state"
        )

    def test_unknown_code_does_not_mutate_store(self) -> None:
        redeem_discount_code("FAKECODE99", "user-1")
        # The store must be unchanged
        assert set(tools_module._DISCOUNT_CODES.keys()) == {"WELCOME50", "SUMMER20"}

    def test_code_normalised_to_uppercase(self) -> None:
        """Lowercase input must be accepted — case normalisation prevents user friction."""
        result = redeem_discount_code("welcome50", "user-1")
        assert "success" in result.lower(), (
            "Code should be accepted case-insensitively"
        )

    def test_code_with_leading_trailing_whitespace(self) -> None:
        """Whitespace around the code must be stripped before lookup."""
        result = redeem_discount_code("  WELCOME50  ", "user-1")
        assert "success" in result.lower()

    def test_mixed_case_code_normalised(self) -> None:
        result = redeem_discount_code("SuMmEr20", "user-2")
        assert "success" in result.lower()

    def test_store_state_unchanged_after_rejected_redemption(self) -> None:
        """A failed attempt (empty user_id) must leave the store completely unchanged."""
        before = copy.deepcopy(tools_module._DISCOUNT_CODES)
        redeem_discount_code("WELCOME50", "")
        after = tools_module._DISCOUNT_CODES
        assert before == after


class TestSingleUseEnforcement:
    """Core business rule: each code may only be redeemed once across all users."""

    def test_second_redemption_of_same_code_is_blocked(self) -> None:
        redeem_discount_code("WELCOME50", "user-first")
        result = redeem_discount_code("WELCOME50", "user-second")
        assert "failed" in result.lower() or "already been used" in result.lower(), (
            "A code redeemed by user-first must not be redeemable by user-second"
        )

    def test_same_user_cannot_redeem_same_code_twice(self) -> None:
        redeem_discount_code("SUMMER20", "user-greedy")
        result = redeem_discount_code("SUMMER20", "user-greedy")
        assert "failed" in result.lower(), (
            "Re-redemption by the same user must also be blocked"
        )

    def test_redeemed_flag_is_set_after_success(self) -> None:
        redeem_discount_code("SUMMER20", "user-1")
        assert tools_module._DISCOUNT_CODES["SUMMER20"]["redeemed"] is True

    def test_codes_are_independent(self) -> None:
        """Redeeming WELCOME50 must not affect SUMMER20 and vice-versa."""
        redeem_discount_code("WELCOME50", "user-a")
        assert tools_module._DISCOUNT_CODES["SUMMER20"]["redeemed"] is False, (
            "Codes must be independent — redeeming one must not mark others as used"
        )


class TestConcurrentRedemptionSimulation:
    """
    T-1 (elevated): Simulate two callers racing to redeem the same code.

    Note: Python's GIL makes true concurrency hard to test here. This test
    exercises the logical ordering — the second call must be blocked regardless
    of who 'won'. A proper fix requires atomic DB transactions (see threat_model.md).
    """

    def test_only_first_redemption_wins(self) -> None:
        result_a = redeem_discount_code("WELCOME50", "user-alice")
        result_b = redeem_discount_code("WELCOME50", "user-bob")

        assert "success" in result_a.lower(), "First caller must succeed"
        assert "failed" in result_b.lower(), "Second caller must be blocked"

        entry = tools_module._DISCOUNT_CODES["WELCOME50"]
        assert entry["redeemed_by"] == "user-alice", (
            "redeemed_by must record the winner, not the loser"
        )


class TestDiscountValues:
    """Business logic: correct discount percentages must be returned."""

    def test_welcome50_gives_fifty_percent_off(self) -> None:
        result = redeem_discount_code("WELCOME50", "user-1")
        assert "50%" in result, "WELCOME50 must grant exactly 50% discount"

    def test_summer20_gives_twenty_percent_off(self) -> None:
        result = redeem_discount_code("SUMMER20", "user-1")
        assert "20%" in result, "SUMMER20 must grant exactly 20% discount"

    def test_success_response_contains_code_name(self) -> None:
        result = redeem_discount_code("WELCOME50", "user-1")
        assert "WELCOME50" in result

    def test_success_response_contains_user_id(self) -> None:
        result = redeem_discount_code("WELCOME50", "user-42")
        assert "user-42" in result


class TestProductCatalogue:
    """Smoke tests for list_available_products — no security boundary, but guards regressions."""

    def test_no_filter_returns_all_categories(self) -> None:
        result = list_available_products()
        for category in ("Electronics", "Clothing", "Home"):
            assert category in result, f"Category '{category}' missing from unfiltered listing"

    def test_valid_category_filter(self) -> None:
        result = list_available_products("electronics")
        assert "Electronics" in result
        assert "Clothing" not in result

    def test_invalid_category_returns_error_message(self) -> None:
        result = list_available_products("weaponry")
        assert "weaponry" in result.lower(), (
            "Error message must echo back the invalid category so the user knows what they asked"
        )
        assert "available categories" in result.lower()

    def test_category_filter_case_insensitive(self) -> None:
        lower = list_available_products("home")
        upper = list_available_products("HOME")
        mixed = list_available_products("HoMe")
        assert lower == upper == mixed, "Category filter must be case-insensitive"


# ---------------------------------------------------------------------------
# Known gaps — document as xfail until mitigations from threat_model.md land
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason=(
        "T-2 gap: no max_length guard on user_id — extremely long strings are accepted. "
        "Fix: wrap inputs in Pydantic schema (threat_model.md T-2, P2)."
    ),
    strict=False,
)
def test_extremely_long_user_id_is_rejected() -> None:
    long_id = "A" * 10_000
    result = redeem_discount_code("WELCOME50", long_id)
    assert "failed" in result.lower(), "Excessively long user_id should be rejected"


@pytest.mark.xfail(
    reason=(
        "S-1 gap: user_id is not bound to an authenticated session — any string is accepted. "
        "Fix: validate against JWT claim in middleware (threat_model.md S-1, P0)."
    ),
    strict=False,
)
def test_user_id_must_match_authenticated_session() -> None:
    # Simulates the future state where user_id is verified against a session token.
    # Currently this test passes with any string, demonstrating the gap.
    result = redeem_discount_code("WELCOME50", "unauthenticated-user")
    assert "failed" in result.lower(), (
        "Once auth middleware is in place, unverified user_ids must be rejected at the tool layer"
    )
