"""Shared utility functions."""

import asyncio
import math
from datetime import datetime, timezone


async def async_sleep(seconds: float) -> None:
    """Async sleep wrapper."""
    await asyncio.sleep(seconds)


def short_address(addr: str) -> str:
    """Abbreviate address to 0x1234...5678."""
    return f"{addr[:6]}...{addr[-4:]}"


def round_cents(n: float) -> float:
    """Round to 2 decimal places."""
    return round(n * 100) / 100


def ceil_cents(n: float) -> float:
    """Ceil to 2 decimal places."""
    return math.ceil(n * 100) / 100


def _tick_decimals(tick: float) -> int:
    if tick >= 0.1 - 1e-9:
        return 1
    if tick >= 0.01 - 1e-9:
        return 2
    if tick >= 0.001 - 1e-9:
        return 3
    return 4


def _clob_share_step(price: float, tick: float) -> tuple[int, int]:
    """Return (price_int_at_tick, share_step_e4) — the smallest m=shares*10000
    increment such that price*shares lands on cents. Returns (0, 0) if invalid.

    Polymarket CLOB enforces: maker_amount (USDC for BUY, shares for SELL)
    has <=2 decimal cents, taker_amount has <=4 decimals. With shares
    expressed as m/10000, maker_cents = P*m / (10^d * 100) where P = price
    in tick units. Integer maker_cents <=> m divisible by step.
    """
    d = _tick_decimals(tick)
    scale = 10 ** d
    p_int = int(round(price * scale))
    if p_int <= 0 or p_int >= scale:
        return 0, 0
    modulus = scale * 100
    return p_int, modulus // math.gcd(p_int, modulus)


def quantize_buy_shares(notional_usd: float, price: float, tick: float) -> float:
    """Largest share count for a BUY such that:
      - shares has <=4 decimals
      - price*shares is cents-clean (<=2 decimals) — Polymarket maker_amount limit
      - price*shares <= notional_usd (never overspend)
    Returns 0.0 if no valid positive size fits the budget at this price/tick.
    """
    if price <= 0 or tick <= 0 or notional_usd <= 0:
        return 0.0
    p_int, step = _clob_share_step(price, tick)
    if step <= 0:
        return 0.0
    notional_cents = math.floor(notional_usd * 100 + 1e-9)
    if notional_cents <= 0:
        return 0.0
    modulus = (10 ** _tick_decimals(tick)) * 100
    m_max = (notional_cents * modulus) // p_int
    m = (m_max // step) * step
    return m / 10000.0 if m > 0 else 0.0


def quantize_sell_shares(available_shares: float, price: float, tick: float) -> float:
    """Largest share count for a SELL such that shares <= available_shares,
    shares has <=4 decimals, and price*shares is cents-clean (taker_amount limit).
    Returns 0.0 if no valid positive size fits.
    """
    if price <= 0 or tick <= 0 or available_shares <= 0:
        return 0.0
    _, step = _clob_share_step(price, tick)
    if step <= 0:
        return 0.0
    m_max = math.floor(available_shares * 10000 + 1e-9)
    if m_max <= 0:
        return 0.0
    m = (m_max // step) * step
    return m / 10000.0 if m > 0 else 0.0


def today_utc() -> str:
    """Return today's date as YYYY-MM-DD in UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def error_message(err: BaseException | object) -> str:
    """Extract a human-readable message from an exception or unknown object."""
    if isinstance(err, Exception):
        return str(err)
    return str(err)
