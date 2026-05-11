"""Live-order placement for the tennis arb strategy.

Tennis arb is unidirectional: BUY YES on entry, SELL YES on take-profit.
Both legs cross the spread immediately at the live best ask/bid plus a
configurable slippage and use FAK (fill-and-kill) — whatever fills fills,
the unmatched remainder cancels rather than resting in the book. The
old GTC-with-cents-rounding path silently rested below the ask on
tick-0.001 markets and never traded; FAK + tick-aware pricing makes
that class of bug impossible.
"""

from __future__ import annotations

import logging
from typing import Optional

from py_clob_client_v2 import (
    ClobClient,
    OrderArgs,
    OrderType,
    PartialCreateOrderOptions,
)
from py_clob_client_v2.order_builder.constants import BUY, SELL

from src.config import CONFIG
from src.utils import error_message, quantize_buy_shares, quantize_sell_shares

logger = logging.getLogger("strategy.tennis_arb")


def _extract_order_id(resp) -> str:
    if isinstance(resp, dict):
        return (
            resp.get("orderID")
            or resp.get("order_id")
            or resp.get("id")
            or ""
        )
    if isinstance(resp, str):
        return resp
    return ""


def _fetch_book(clob_client: ClobClient, token_id: str) -> tuple[float, float, float]:
    """Return (best_ask, best_bid, tick_size) from the live CLOB orderbook.

    Bids/asks come back sorted ascending and descending respectively, so
    the best price (highest bid / lowest ask) is the LAST entry of each.
    """
    book = clob_client.get_order_book(token_id)
    if not isinstance(book, dict):
        # py-clob-client-v2 may return an OrderBookSummary dataclass.
        bids = list(getattr(book, "bids", []) or [])
        asks = list(getattr(book, "asks", []) or [])
        tick = float(getattr(book, "tick_size", 0.01) or 0.01)
    else:
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        tick = float(book.get("tick_size") or 0.01)

    def _price(entry):
        if isinstance(entry, dict):
            return float(entry.get("price") or 0)
        return float(getattr(entry, "price", 0) or 0)

    best_ask = _price(asks[-1]) if asks else 0.0
    best_bid = _price(bids[-1]) if bids else 0.0
    return best_ask, best_bid, tick


def _round_to_tick(price: float, tick_size: float) -> float:
    """Round to the nearest valid CLOB tick (0.01, 0.001, etc.)."""
    if tick_size <= 0:
        return price
    n = round(price / tick_size)
    decimals = max(0, -int(round(__import__("math").log10(tick_size))))
    return round(n * tick_size, decimals)


def _tick_size_str(tick_size: float) -> str:
    """Render the tick size in the exact format the V2 builder expects."""
    if tick_size >= 0.1 - 1e-9:
        return "0.1"
    if tick_size >= 0.01 - 1e-9:
        return "0.01"
    if tick_size >= 0.001 - 1e-9:
        return "0.001"
    return "0.0001"


def place_buy_yes(
    clob_client: ClobClient,
    token_id: str,
    bet_size_usd: float,
    ref_price: float,
) -> Optional[dict]:
    """Cross the spread with a BUY at best_ask × (1 + slippage_bps/10000), FAK.

    `ref_price` is logged for sanity but no longer drives the limit price —
    Gamma's lastTradePrice is too stale on fast-moving books, and the old
    cents-only rounding was killing the buffer on cheap markets. We always
    quote off the live CLOB ask now.

    Returns ``{order_id, shares, order_price}`` on submission, ``{"error":
    msg, ...}`` on CLOB rejection, or ``None`` only on invalid input.
    """
    if bet_size_usd <= 0 or not token_id:
        logger.warning(
            f"[tennis-live] BUY skipped: invalid args "
            f"size={bet_size_usd} ref={ref_price} token={token_id[:12] if token_id else ''}"
        )
        return None

    try:
        best_ask, _, tick = _fetch_book(clob_client, token_id)
    except Exception as exc:
        msg = error_message(exc)
        logger.error(f"[tennis-live] BUY book fetch failed: {msg}")
        return {"error": f"book_fetch_failed:{msg}"}

    if best_ask <= 0:
        logger.warning(f"[tennis-live] BUY skipped: empty book token={token_id[:12]}...")
        return {"error": "empty_book"}

    slippage_bps = max(0, int(CONFIG.live_order_slippage_bps))
    slip = max(best_ask * slippage_bps / 10_000.0, tick)
    order_price = _round_to_tick(min(best_ask + slip, 1.0 - tick), tick)
    if order_price < tick:
        order_price = tick

    shares = quantize_buy_shares(bet_size_usd, order_price, tick)
    if shares <= 0:
        logger.warning(
            f"[tennis-live] BUY skipped: bet_size=${bet_size_usd:.2f} too small "
            f"for cents-clean order at price={order_price} tick={tick} "
            f"(maker must round to cents; smallest valid notional > budget). "
            f"token={token_id[:12]}..."
        )
        return {"error": "notional_below_clob_step", "order_price": order_price}

    actual_notional = order_price * shares
    logger.info(
        f"[tennis-live] BUY YES {shares}@{order_price} "
        f"(req=${bet_size_usd:.2f}, fill=${actual_notional:.2f}, ref={ref_price:.4f}, "
        f"ask={best_ask:.4f}, slip={slippage_bps}bps, tick={tick}, "
        f"token={token_id[:12]}...)"
    )

    try:
        order = clob_client.create_order(
            OrderArgs(price=order_price, size=shares, side=BUY, token_id=token_id),
            options=PartialCreateOrderOptions(tick_size=_tick_size_str(tick)),
        )
        resp = clob_client.post_order(order, OrderType.FAK)
    except Exception as exc:
        msg = error_message(exc)
        logger.error(f"[tennis-live] BUY failed: {msg}")
        return {"error": msg, "shares": shares, "order_price": order_price}

    order_id = _extract_order_id(resp)
    if not order_id:
        logger.warning(f"[tennis-live] BUY posted but no order_id in resp: {resp}")
    return {"order_id": order_id, "shares": shares, "order_price": order_price}


def place_sell_yes(
    clob_client: ClobClient,
    token_id: str,
    shares: float,
    ref_price: float,
) -> Optional[dict]:
    """Cross the spread with a SELL at best_bid × (1 - slippage_bps/10000), FAK."""
    if shares <= 0 or not token_id:
        logger.warning(
            f"[tennis-live] SELL skipped: invalid args "
            f"shares={shares} ref={ref_price} token={token_id[:12] if token_id else ''}"
        )
        return None

    try:
        _, best_bid, tick = _fetch_book(clob_client, token_id)
    except Exception as exc:
        msg = error_message(exc)
        logger.error(f"[tennis-live] SELL book fetch failed: {msg}")
        return {"error": f"book_fetch_failed:{msg}"}

    if best_bid <= 0:
        logger.warning(f"[tennis-live] SELL skipped: empty book token={token_id[:12]}...")
        return {"error": "empty_book"}

    slippage_bps = max(0, int(CONFIG.live_order_slippage_bps))
    slip = max(best_bid * slippage_bps / 10_000.0, tick)
    order_price = _round_to_tick(max(best_bid - slip, tick), tick)

    sell_shares = quantize_sell_shares(shares, order_price, tick)
    if sell_shares <= 0:
        logger.warning(
            f"[tennis-live] SELL skipped: position={shares} too small for "
            f"cents-clean order at price={order_price} tick={tick}. "
            f"token={token_id[:12]}..."
        )
        return {"error": "position_below_clob_step", "order_price": order_price}

    logger.info(
        f"[tennis-live] SELL YES {sell_shares}@{order_price} "
        f"(have={shares}, proceeds=${order_price * sell_shares:.2f}, "
        f"ref={ref_price:.4f}, bid={best_bid:.4f}, slip={slippage_bps}bps, "
        f"tick={tick}, token={token_id[:12]}...)"
    )

    try:
        order = clob_client.create_order(
            OrderArgs(price=order_price, size=sell_shares, side=SELL, token_id=token_id),
            options=PartialCreateOrderOptions(tick_size=_tick_size_str(tick)),
        )
        resp = clob_client.post_order(order, OrderType.FAK)
    except Exception as exc:
        msg = error_message(exc)
        logger.error(f"[tennis-live] SELL failed: {msg}")
        return {"error": msg, "shares": sell_shares, "order_price": order_price}

    order_id = _extract_order_id(resp)
    if not order_id:
        logger.warning(f"[tennis-live] SELL posted but no order_id in resp: {resp}")
    return {"order_id": order_id, "shares": sell_shares, "order_price": order_price}
