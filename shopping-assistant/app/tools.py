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

"""Tools for the Shopping Assistant agent."""

from typing import TypedDict

# ---------------------------------------------------------------------------
# In-memory discount code store
# ---------------------------------------------------------------------------


class DiscountCode(TypedDict):
    discount_pct: int  # e.g. 50 means 50 % off
    redeemed: bool  # True once used
    redeemed_by: str | None  # user_id that redeemed it


# Single-use discount code registry.
# Keys are uppercase code strings.
_DISCOUNT_CODES: dict[str, DiscountCode] = {
    "WELCOME50": {"discount_pct": 50, "redeemed": False, "redeemed_by": None},
    "SUMMER20": {"discount_pct": 20, "redeemed": False, "redeemed_by": None},
}

# ---------------------------------------------------------------------------
# Tool functions exposed to the ADK agent
# ---------------------------------------------------------------------------


def redeem_discount_code(code: str, user_id: str) -> str:
    """Redeem a single-use discount code for a registered user.

    Each code can only be redeemed once across all users. The caller must
    supply a non-empty ``user_id`` that identifies the registered customer.

    Args:
        code:    The discount code to redeem (case-insensitive).
        user_id: The unique identifier of the registered customer attempting
                 the redemption.

    Returns:
        A human-readable string describing the outcome:
        - Success: confirms the discount percentage applied.
        - Failure: explains why redemption was refused (unknown code, already
          used, or missing user ID).
    """
    if not user_id or not user_id.strip():
        return (
            "Redemption failed: a registered user ID is required to redeem a "
            "discount code. Please log in and try again."
        )

    normalised_code = code.strip().upper()

    if normalised_code not in _DISCOUNT_CODES:
        return (
            f"Redemption failed: the code '{code}' is not recognised. "
            "Please check the code and try again."
        )

    entry = _DISCOUNT_CODES[normalised_code]

    if entry["redeemed"]:
        return (
            f"Redemption failed: the code '{normalised_code}' has already been "
            f"used and cannot be redeemed again."
        )

    # Mark as redeemed
    entry["redeemed"] = True
    entry["redeemed_by"] = user_id.strip()

    discount = entry["discount_pct"]
    return (
        f"Success! Code '{normalised_code}' redeemed for user '{user_id.strip()}'. "
        f"You receive {discount}% off your order. Enjoy your savings!"
    )


def list_available_products(category: str = "") -> str:
    """Return a curated list of products available in the store.

    Args:
        category: Optional product category filter (e.g. 'electronics',
                  'clothing', 'home'). Leave empty to list all categories.

    Returns:
        A formatted string listing available products and their prices.
    """
    catalogue: dict[str, list[tuple[str, str]]] = {
        "electronics": [
            ("Wireless Noise-Cancelling Headphones", "$149.99"),
            ("Smart Watch Series X", "$299.99"),
            ("Portable Bluetooth Speaker", "$79.99"),
        ],
        "clothing": [
            ("Premium Cotton T-Shirt", "$29.99"),
            ("Slim-Fit Chino Trousers", "$59.99"),
            ("Waterproof Rain Jacket", "$119.99"),
        ],
        "home": [
            ("Stainless Steel Coffee Maker", "$89.99"),
            ("Memory Foam Pillow Set", "$49.99"),
            ("LED Desk Lamp", "$34.99"),
        ],
    }

    filter_key = category.strip().lower()

    if filter_key and filter_key not in catalogue:
        return (
            f"Sorry, we don't carry a '{category}' category. "
            f"Available categories: {', '.join(catalogue)}."
        )

    selected = {filter_key: catalogue[filter_key]} if filter_key else catalogue

    lines: list[str] = []
    for cat, items in selected.items():
        lines.append(f"\n{cat.capitalize()}:")
        for name, price in items:
            lines.append(f"  • {name} — {price}")

    return "Here are our available products:" + "".join(lines)
