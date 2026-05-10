"""Live-order placement for the tennis arb strategy.

Tennis arb is unidirectional: BUY YES on entry, SELL YES on take-profit.
This module wraps the shared py-clob-client with that narrow surface.
"""

from __future__ import annotations

import logging
from typing import Optional

from py_clob_client_v2 import ClobClient, OrderArgs, OrderType
from py_clob_client_v2.order_builder.constants import BUY, SELL

from src.utils import ceil_cents, error_message, round_cents

logger = logging.getLogger("strategy.tennis_arb")

BUY_BUFFER = 1.02
SELL_BUFFER = 0.98


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


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


def place_buy_yes(
    clob_client: ClobClient,
    token_id: str,
    bet_size_usd: float,
    ref_price: float,
) -> Optional[dict]:
    """Place a BUY YES limit at ref_price * BUY_BUFFER (capped 1c–99c).

    Returns ``{order_id, shares, order_price}`` on submission, or None on
    invalid args or CLOB failure.
    """
    if bet_size_usd <= 0 or ref_price <= 0 or not token_id:
        logger.warning(
            f"[tennis-live] BUY skipped: invalid args "
            f"size={bet_size_usd} ref={ref_price} token={token_id[:12] if token_id else ''}"
        )
        return None

    order_price = _clamp(round_cents(ref_price * BUY_BUFFER), 0.01, 0.99)
    shares = ceil_cents(bet_size_usd / order_price) if order_price > 0 else 0.0
    if shares <= 0:
        logger.warning(f"[tennis-live] BUY non-positive shares: {shares}")
        return None

    logger.info(
        f"[tennis-live] BUY YES {shares}@{order_price} "
        f"(size=${bet_size_usd:.2f}, ref={ref_price:.4f}, token={token_id[:12]}...)"
    )

    try:
        order = clob_client.create_order(
            OrderArgs(price=order_price, size=shares, side=BUY, token_id=token_id)
        )
        resp = clob_client.post_order(order, OrderType.GTC)
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
    """Place a SELL YES limit at ref_price * SELL_BUFFER (capped 1c–99c)."""
    if shares <= 0 or ref_price <= 0 or not token_id:
        logger.warning(
            f"[tennis-live] SELL skipped: invalid args "
            f"shares={shares} ref={ref_price} token={token_id[:12] if token_id else ''}"
        )
        return None

    order_price = _clamp(round_cents(ref_price * SELL_BUFFER), 0.01, 0.99)
    sell_shares = round_cents(shares)
    if sell_shares <= 0:
        return None

    logger.info(
        f"[tennis-live] SELL YES {sell_shares}@{order_price} "
        f"(ref={ref_price:.4f}, token={token_id[:12]}...)"
    )

    try:
        order = clob_client.create_order(
            OrderArgs(price=order_price, size=sell_shares, side=SELL, token_id=token_id)
        )
        resp = clob_client.post_order(order, OrderType.GTC)
    except Exception as exc:
        msg = error_message(exc)
        logger.error(f"[tennis-live] SELL failed: {msg}")
        return {"error": msg, "shares": sell_shares, "order_price": order_price}

    order_id = _extract_order_id(resp)
    if not order_id:
        logger.warning(f"[tennis-live] SELL posted but no order_id in resp: {resp}")
    return {"order_id": order_id, "shares": sell_shares, "order_price": order_price}
