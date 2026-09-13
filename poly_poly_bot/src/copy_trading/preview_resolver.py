"""Paper-mode realization for the tiered executor (System A).

In preview mode the on-chain redeemer is gated off, so copy positions held in
``inventory`` would never realize — realized P&L would sit at $0 forever and
closed bets would vanish. This module is the paper analogue of the redeemer: it
checks each open inventory position's market on Gamma and, once the market
resolves, books a realized-P&L row (attributed to the position's tier + followed
wallet) and drops the token from inventory.

The classification + row-building is **pure** (a market dict and positions are
injected) so it unit-tests without network. ``run_preview_realization`` is the
thin live wrapper the periodic loop calls.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable, Optional

from src.logger import logger

_RESOLVED_PRICE = 0.99   # a resolved YES outcome prices ~1.0 (matches market_resolution)


def _parse_list(raw) -> list:
    """Gamma returns ``outcomePrices``/``clobTokenIds`` as a JSON string or list."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    return list(raw) if isinstance(raw, (list, tuple)) else []


def classify_payout(market: Optional[dict], token_id: str) -> Optional[float]:
    """What one held share of ``token_id`` pays at resolution: 1.0 (won),
    0.0 (lost), 0.5 (a cancelled market's 50/50 refund, issue #33), or
    ``None`` if the market is open / not cleanly resolved / the token isn't
    in the market.

    Maps the token to its outcome via ``clobTokenIds`` and reads that outcome's
    resolved price from ``outcomePrices`` (winner prices ~1.0; a cancelled
    market prices every outcome ~0.5)."""
    if not market or not market.get("closed"):
        return None
    prices = _parse_list(market.get("outcomePrices"))
    tokens = _parse_list(market.get("clobTokenIds"))
    if not prices or not tokens or token_id not in tokens:
        return None
    try:
        fprices = [float(p) for p in prices]
    except (ValueError, TypeError):
        return None
    idx = tokens.index(token_id)
    if idx >= len(fprices):
        return None
    if max(fprices) >= _RESOLVED_PRICE:
        return 1.0 if fprices[idx] >= _RESOLVED_PRICE else 0.0
    if len(fprices) >= 2 and all(0.45 <= p <= 0.55 for p in fprices):
        return 0.5
    return None   # closed but not a clean resolution yet


def classify_position(market: Optional[dict], token_id: str) -> Optional[bool]:
    """Did the held ``token_id`` win? ``True`` won, ``False`` lost, ``None`` if
    the market is open / not cleanly resolved / the token isn't in the market.
    A cancelled market is neither: ``None`` (the late-bet lead reads this)."""
    payout = classify_payout(market, token_id)
    if payout is None or payout == 0.5:
        return None
    return payout >= 1.0


def realize_preview_positions(
    positions: dict,
    market_fetcher: Callable[[str], Optional[dict]],
    *,
    now_iso: Optional[str] = None,
) -> tuple[list[dict], list[str]]:
    """Build realized rows for any resolved open positions.

    Returns ``(realized_rows, token_ids_to_drop)``. ``positions`` is the
    inventory shape ``{token_id: {shares, avg_price, market, market_key, tier,
    trader_address}}``; ``market_fetcher`` maps a condition id to a Gamma market
    dict (or None)."""
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    drop: list[str] = []
    for token_id, pos in positions.items():
        condition_id = pos.get("market_key") or ""
        if not condition_id:
            continue
        shares = float(pos.get("shares", 0) or 0)
        if shares <= 0:
            continue
        payout = classify_payout(market_fetcher(condition_id), token_id)
        if payout is None:
            continue
        won = payout >= 1.0
        avg = float(pos.get("avg_price", 0) or 0)
        cost = shares * avg
        returned = shares * payout
        rows.append({
            "timestamp": ts,
            "title": pos.get("market", "") or "",
            "condition_id": condition_id,
            "token_id": token_id,
            "shares": round(shares, 6),
            "avg_price": round(avg, 6),
            "cost_basis": round(cost, 6),
            "returned": round(returned, 6),
            "pnl": round(returned - cost, 6),
            "won": won,
            "tier": pos.get("tier", "") or "",
            "trader_address": pos.get("trader_address", "") or "",
            "exit": "resolution",
            "source": "preview",
            # a cancelled market's 50/50 refund: neither a win nor a loss
            "refunded": payout == 0.5,
        })
        drop.append(token_id)
    return rows, drop


def run_preview_realization(market_fetcher: Optional[Callable[[str], Optional[dict]]] = None) -> int:
    """Live wrapper: realize resolved preview positions, append the rows, and
    drop them from inventory. Returns the number realized. Best-effort."""
    from src.copy_trading import inventory
    from src.copy_trading.pnl import append_realized

    if market_fetcher is None:
        from src.copy_trading.market_resolution import fetch_market
        market_fetcher = fetch_market

    positions = inventory.get_positions()
    if not positions:
        return 0
    rows, drop = realize_preview_positions(positions, market_fetcher)
    for row in rows:
        append_realized(row)
    for token_id in drop:
        try:
            inventory.record_sell(token_id, positions[token_id].get("shares", 0))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[preview-realize] failed to drop {token_id[:12]}...: {e}")
    if rows:
        logger.info(f"[preview-realize] realized {len(rows)} resolved preview position(s)")
    return len(rows)
