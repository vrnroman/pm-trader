"""Has a market resolved, and which outcome won? Read from Gamma.

``resolve(condition_id)`` returns the winning outcome index, ``REFUNDED`` for
a cancelled market (every outcome priced about 0.5, the 50/50 payout), or
None while it is open or not cleanly resolved.
"""

from __future__ import annotations

import json
from typing import Optional

import httpx

GAMMA = "https://gamma-api.polymarket.com"
REFUNDED = -1


def parse_winner(market: dict) -> Optional[int]:
    if not market or not market.get("closed", True):
        return None
    op = market.get("outcomePrices")
    if isinstance(op, str):
        try:
            op = json.loads(op)
        except json.JSONDecodeError:
            return None
    if not op:
        return None
    prices: list[float] = []
    for p in op:
        try:
            prices.append(float(p))
        except (ValueError, TypeError):
            return None
    for i, p in enumerate(prices):
        if p >= 0.99:
            return i
    if len(prices) >= 2 and all(0.45 <= p <= 0.55 for p in prices):
        return REFUNDED
    return None


def resolve(condition_id: str, client: Optional[httpx.Client] = None) -> Optional[int]:
    if not condition_id:
        return None
    try:
        c = client or httpx.Client(timeout=10.0)
        r = c.get(f"{GAMMA}/markets", params={"condition_ids": condition_id, "closed": "true"})
        if r.status_code != 200:
            return None
        rows = r.json()
    except Exception:  # noqa: BLE001
        return None
    if isinstance(rows, dict):
        rows = rows.get("data") or []
    return parse_winner(rows[0]) if rows else None
