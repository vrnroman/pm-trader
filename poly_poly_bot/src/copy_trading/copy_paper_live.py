"""Live Polymarket I/O for the forward paper-copy harness (Strategy 1b).

Factored out of the CLI so the offline script and the in-bot runner share one
tested code path. These are the three dependencies `CopyPaperEngine` needs:
detection (data-api), books (CLOB), resolution (gamma). They place no orders.
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

import requests

from src.copy_trading.trader_scoring import classify_market

DATA = os.environ.get("DATA_API_URL", "https://data-api.polymarket.com")
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

_S = requests.Session()


def _get(base: str, path: str, **params):
    for _ in range(3):
        try:
            r = _S.get(base + path, params=params, timeout=25)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(0.3)
    return None


def make_detector(wallets: list[str], max_age_s: float, min_usd: float):
    """Return a detector() yielding fresh, large target BUY trades to copy."""

    def detect() -> list[dict]:
        out = []
        cutoff = time.time() - max_age_s
        for w in wallets:
            acts = _get(DATA, "/activity", user=w, limit=30) or []
            for a in acts:
                if a.get("type") != "TRADE" or a.get("side") != "BUY":
                    continue
                if float(a.get("timestamp") or 0) < cutoff:
                    continue
                price = float(a.get("price") or 0)
                if not (0.05 <= price <= 0.95):
                    continue
                usd = float(a.get("usdcSize") or 0)
                if usd <= 0:
                    usd = float(a.get("size") or 0) * price
                if usd < min_usd:
                    continue
                tx = a.get("transactionHash") or ""
                token = a.get("asset") or ""
                if not tx or not token:
                    continue
                title = a.get("title", "") or ""
                out.append({
                    "copy_id": f"{tx}-{token}",
                    "target": w,
                    "condition_id": a.get("conditionId", ""),
                    "token_id": token,
                    "outcome_index": int(a.get("outcomeIndex") or 0),
                    "category": classify_market(title),
                    "title": title,
                    # event slug drives the polymarket.com/event/<slug> link;
                    # data-api uses eventSlug, falling back to the market slug.
                    "slug": a.get("eventSlug") or a.get("slug") or "",
                    "their_price": price,
                    "their_usd": usd,
                })
        return out

    return detect


def fetch_asks(token_id: str) -> list[tuple[float, float]]:
    b = _get(CLOB, "/book", token_id=token_id)
    if not b:
        return []
    return [(float(a["price"]), float(a["size"])) for a in (b.get("asks") or [])]


def resolve(condition_id: str) -> Optional[int]:
    """Winning outcome index for a resolved market, else None (still open)."""
    if not condition_id:
        return None
    j = _get(GAMMA, "/markets", condition_ids=condition_id, closed="true")
    if not j:
        return None
    op = j[0].get("outcomePrices")
    if isinstance(op, str):
        try:
            op = json.loads(op)
        except json.JSONDecodeError:
            return None
    if not op:
        return None
    for i, p in enumerate(op):
        try:
            if float(p) >= 0.99:
                return i
        except (ValueError, TypeError):
            continue
    return None


def load_watchlist_wallets(path: str) -> list[str]:
    """Read wallet addresses from a trader_scoring_backtest watchlist JSON."""
    if not path or not os.path.exists(path):
        return []
    try:
        data = json.load(open(path))
    except (json.JSONDecodeError, OSError):
        return []
    return [t["wallet"] for t in data.get("targets", []) if t.get("wallet")]
