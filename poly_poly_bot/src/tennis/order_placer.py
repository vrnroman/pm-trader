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
import time
from typing import Optional

from py_clob_client_v2 import (
    ClobClient,
    OrderArgs,
    OrderType,
    PartialCreateOrderOptions,
)
from py_clob_client_v2.clob_types import TradeParams
from py_clob_client_v2.exceptions import PolyApiException
from py_clob_client_v2.order_builder.constants import BUY, SELL

from src.config import CONFIG
from src.utils import error_message, quantize_buy_shares, quantize_sell_shares

logger = logging.getLogger("strategy.tennis_arb")

# Polymarket's CLOB returns HTTP 425 ("Too Early") on freshly-listed markets
# whose order book hasn't fully spun up. The condition clears within a few
# seconds — single retries with short backoff have flipped both observed
# instances (2026-05-12 Garin/Midon at 13:16 and 13:18 hit the same market
# 2 min apart and both failed; a single 1–5s retry should catch the recovery
# window). Cap at 3 attempts so a genuinely dead market doesn't stall the
# strategy loop for too long.
_RETRY_TRANSIENT_STATUSES = {425}
_RETRY_BACKOFFS_S = (1.0, 3.0)  # 1st retry after 1s, 2nd after 3s; total <=4s


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


def _post_order_with_retry(clob_client: ClobClient, order, order_type: OrderType):
    """Post an order, retrying on transient CLOB status codes (425).

    Re-posts the same signed order on retry — the FAK order body is
    salt-keyed so the server treats each attempt as a fresh request, but the
    underlying limit price was decided once at the call site and isn't
    refreshed between attempts (acceptable: 425 means the book isn't ready
    yet, not that the price stale-ed; total retry budget is <5s so the
    price drift risk is small).
    """
    last_exc: BaseException | None = None
    for attempt in range(len(_RETRY_BACKOFFS_S) + 1):
        try:
            return clob_client.post_order(order, order_type)
        except PolyApiException as exc:
            status = getattr(exc, "status_code", None)
            if status not in _RETRY_TRANSIENT_STATUSES:
                raise
            last_exc = exc
            if attempt >= len(_RETRY_BACKOFFS_S):
                break
            backoff = _RETRY_BACKOFFS_S[attempt]
            logger.warning(
                f"[tennis-live] CLOB {status} transient (attempt "
                f"{attempt + 1}/{len(_RETRY_BACKOFFS_S) + 1}); waiting "
                f"{backoff:.1f}s before retry"
            )
            time.sleep(backoff)
    # Exhausted retries — re-raise the last 425 so the caller logs it.
    assert last_exc is not None
    raise last_exc


def _fetch_fill(
    clob_client: ClobClient, order_id: str, fallback_price: float
) -> tuple[float, float, bool]:
    """Return (filled_shares, avg_fill_price, fill_certain).

    ``fill_certain`` distinguishes "definitively 0 fills" from "API call
    failed, fill state unknown". A retry path can act on the first but
    must NOT retry on the second — re-submitting on an opaque outcome
    could double exposure if the original actually did fill.

    The bot used to record paper-book positions sized off the *requested*
    bet, not the actual fill. FAK orders can fill below the requested size
    (book thins out before maker_amount is fully consumed), and BUY FAK can
    even fill *more* shares than requested when the matching price is below
    the limit (the matcher consumes the maker_amount in USDC and gives more
    shares back at the cheaper price). Both cases cause paper-book drift
    that later trips up SELL with "not enough balance" — see the 2026-05-12
    Garin 50.555/55.555 incident.

    Strategy: pull the placed order via get_order for ``size_matched`` (the
    canonical filled share count). Then fetch get_trades filtered on the
    token to derive the size-weighted avg fill price; the order's ``price``
    field is the limit, not the realised VWAP. On any get_order failure or
    empty response, return ``(0.0, fallback_price, False)`` — uncertain. On
    a clean ``size_matched == 0``, return ``(0.0, fallback_price, True)``.
    """
    if not order_id:
        return 0.0, fallback_price, False
    try:
        order = clob_client.get_order(order_id)
    except Exception as exc:
        logger.warning(
            f"[tennis-live] get_order({order_id[:10]}…) failed: "
            f"{error_message(exc)} — falling back to limit price"
        )
        return 0.0, fallback_price, False

    if not isinstance(order, dict):
        return 0.0, fallback_price, False

    try:
        size_matched = float(order.get("size_matched") or 0)
    except (TypeError, ValueError):
        size_matched = 0.0
    if size_matched <= 0:
        # FAK is atomic — size_matched=0 from a successfully-fetched order
        # means the order definitively did not fill. Safe to retry.
        return 0.0, fallback_price, True

    token_id = order.get("asset_id") or ""
    # VWAP via get_trades. Filter to our taker_order_id since the listing is
    # account-wide. Best-effort: if get_trades fails (auth, rate limit) we
    # fall back to the order's limit price, which over-reports cost on BUYs
    # that filled below limit and under-reports on SELLs that filled above —
    # both directions are conservative for the paper-book entry.
    try:
        params = TradeParams(asset_id=token_id) if token_id else TradeParams()
        trades = clob_client.get_trades(params=params, only_first_page=True) or []
    except Exception as exc:
        logger.debug(
            f"[tennis-live] get_trades for {order_id[:10]}… failed: "
            f"{error_message(exc)} — using limit price as fill price"
        )
        return size_matched, float(order.get("price") or fallback_price), True

    matched_trades = [t for t in trades if t.get("taker_order_id") == order_id]
    if not matched_trades:
        return size_matched, float(order.get("price") or fallback_price), True

    total_size = 0.0
    total_usdc = 0.0
    for t in matched_trades:
        try:
            s = float(t.get("size") or 0)
            p = float(t.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if s <= 0 or p <= 0:
            continue
        total_size += s
        total_usdc += s * p
    if total_size <= 0:
        return size_matched, float(order.get("price") or fallback_price), True

    return total_size, total_usdc / total_size, True


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
    book_hint: tuple[float, float, float] | None = None,
) -> Optional[dict]:
    """Cross the spread with a BUY at best_ask × (1 + slippage_bps/10000), FAK.

    `ref_price` is logged for sanity but no longer drives the limit price —
    Gamma's lastTradePrice is too stale on fast-moving books, and the old
    cents-only rounding was killing the buffer on cheap markets. We always
    quote off the live CLOB ask now.

    `book_hint=(best_ask, best_bid, tick)` lets the caller pass in an
    already-fetched book to skip the second CLOB roundtrip. The caller is
    on the hook for freshness — if the hint is more than a few hundred ms
    old, the FAK may not fill; the existing slippage_bps buffer is what
    absorbs that drift.

    Returns ``{order_id, shares, order_price}`` on submission, ``{"error":
    msg, ...}`` on CLOB rejection, or ``None`` only on invalid input.
    """
    if bet_size_usd <= 0 or not token_id:
        logger.warning(
            f"[tennis-live] BUY skipped: invalid args "
            f"size={bet_size_usd} ref={ref_price} token={token_id[:12] if token_id else ''}"
        )
        return None

    if book_hint is not None:
        best_ask, _, tick = book_hint
    else:
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
        resp = _post_order_with_retry(clob_client, order, OrderType.FAK)
    except Exception as exc:
        msg = error_message(exc)
        logger.error(f"[tennis-live] BUY failed: {msg}")
        return {"error": msg, "shares": shares, "order_price": order_price}

    order_id = _extract_order_id(resp)
    if not order_id:
        logger.warning(f"[tennis-live] BUY posted but no order_id in resp: {resp}")
        return {"order_id": "", "shares": shares, "order_price": order_price, "unfilled": False}

    filled_shares, avg_fill_price, fill_certain = _fetch_fill(
        clob_client, order_id, fallback_price=order_price
    )
    # `unfilled` is True only when the order DEFINITIVELY didn't fill —
    # FAK matched nothing and we got a clean get_order response saying so.
    # When reconcile errored (fill_certain=False) we don't know, so the
    # caller must NOT retry (could double exposure). When some shares
    # filled, also not "unfilled".
    unfilled = fill_certain and filled_shares <= 0
    # Mask 0-fill to planned shares for paper-book sizing hygiene. Existing
    # behavior — the `unfilled` flag is what the caller uses for the retry
    # decision, separate from the bookkeeping fallback.
    if filled_shares <= 0:
        filled_shares = shares
        avg_fill_price = order_price
    return {
        "order_id": order_id,
        "shares": shares,
        "order_price": order_price,
        "filled_shares": filled_shares,
        "filled_avg_price": avg_fill_price,
        "unfilled": unfilled,
    }


def place_sell_yes(
    clob_client: ClobClient,
    token_id: str,
    shares: float,
    ref_price: float,
    book_hint: tuple[float, float, float] | None = None,
) -> Optional[dict]:
    """Cross the spread with a SELL at best_bid × (1 - slippage_bps/10000), FAK.

    `book_hint=(best_ask, best_bid, tick)` skips the second CLOB roundtrip
    when the caller already has a fresh book.
    """
    if shares <= 0 or not token_id:
        logger.warning(
            f"[tennis-live] SELL skipped: invalid args "
            f"shares={shares} ref={ref_price} token={token_id[:12] if token_id else ''}"
        )
        return None

    if book_hint is not None:
        _, best_bid, tick = book_hint
    else:
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
        resp = _post_order_with_retry(clob_client, order, OrderType.FAK)
    except Exception as exc:
        msg = error_message(exc)
        logger.error(f"[tennis-live] SELL failed: {msg}")
        return {"error": msg, "shares": sell_shares, "order_price": order_price}

    order_id = _extract_order_id(resp)
    if not order_id:
        logger.warning(f"[tennis-live] SELL posted but no order_id in resp: {resp}")
        return {"order_id": "", "shares": sell_shares, "order_price": order_price}

    filled_shares, avg_fill_price, _fill_certain = _fetch_fill(
        clob_client, order_id, fallback_price=order_price
    )
    if filled_shares <= 0:
        filled_shares = sell_shares
        avg_fill_price = order_price
    return {
        "order_id": order_id,
        "shares": sell_shares,
        "order_price": order_price,
        "filled_shares": filled_shares,
        "filled_avg_price": avg_fill_price,
    }
