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


def fmt_cents(price: float) -> str:
    """A 0–1 probability as cents for Telegram display, keeping sub-cent precision
    on longshots so a genuine fill never misreads as free: 0.004 → ``0.4¢``, and a
    positive price too small to show even one decimal → ``<0.1¢`` (not ``0.0¢``).
    One shared formatter for every trade/signal message."""
    c = price * 100.0
    if c <= 0:
        return "0¢"
    if c < 0.1:
        return "<0.1¢"          # positive but below display resolution — not "0.0¢"
    if c < 1:
        return f"{c:.1f}¢"
    return f"{c:.0f}¢"


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
    """Return (p_int, m_step) for the 2-decimal share grid m = shares * 100.

    py-clob-client-v2's RoundConfig sets ``size = 2`` for every tick, so the
    library round_down's our shares to 2dp before signing. If we hand it a
    4dp share count the 0.0001-place gets silently dropped and the resulting
    maker_amount = round_down(size, 2) * price is no longer cents-clean,
    which Polymarket's CLOB rejects on BUY orders with
    ``invalid amounts, the market buy orders maker amount supports a max
    accuracy of 2 decimals``. So we quantize directly on the 2dp grid.

    On that grid: maker_cents = m * P / scale where P = price * 10^d and
    scale = 10^d. ``m * P`` must be a multiple of ``scale`` for the maker
    amount to land on whole cents, so the step in m-units is
    scale // gcd(P, scale).
    """
    d = _tick_decimals(tick)
    scale = 10 ** d
    p_int = int(round(price * scale))
    if p_int <= 0 or p_int >= scale:
        return 0, 0
    return p_int, scale // math.gcd(p_int, scale)


def quantize_buy_shares(notional_usd: float, price: float, tick: float) -> float:
    """Largest BUY shares such that:
      - shares has <=2 decimals (matches py-clob-client-v2 RoundConfig.size)
      - price*shares is cents-clean (Polymarket BUY maker_amount rule)
      - price*shares <= notional_usd (never overspend, modulo half-cent dust)
    Returns 0.0 if no valid positive size fits the budget at this price/tick.

    Float dust on the budget (Kelly often returns 10.79999…6 when the bet was
    meant to be $10.80) is absorbed by rounding half-up to the nearest cent
    before quantization. Max overspend from the cushion is 0.5¢.
    """
    if price <= 0 or tick <= 0 or notional_usd <= 0:
        return 0.0
    p_int, step = _clob_share_step(price, tick)
    if step <= 0:
        return 0.0
    scale = 10 ** _tick_decimals(tick)
    notional_cents = int(math.floor(notional_usd * 100 + 0.5))
    if notional_cents <= 0:
        return 0.0
    m_max = (notional_cents * scale) // p_int
    m = (m_max // step) * step
    return m / 100.0 if m > 0 else 0.0


def quantize_sell_shares(available_shares: float, price: float, tick: float) -> float:
    """Largest SELL shares such that:
      - shares <= available_shares
      - shares has <=2 decimals (matches py-clob-client-v2 RoundConfig.size)
      - price*shares is cents-clean (defensive — taker_amount allows 4dp
        for SELL today, but keeping it cents-clean preserves the symmetry
        with BUY and shields us if Polymarket tightens taker precision).
    Returns 0.0 if no valid positive size fits.
    """
    if price <= 0 or tick <= 0 or available_shares <= 0:
        return 0.0
    _, step = _clob_share_step(price, tick)
    if step <= 0:
        return 0.0
    m_max = math.floor(available_shares * 100 + 1e-9)
    if m_max <= 0:
        return 0.0
    m = (m_max // step) * step
    return m / 100.0 if m > 0 else 0.0


def today_utc() -> str:
    """Return today's date as YYYY-MM-DD in UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def error_message(err: BaseException | object) -> str:
    """Extract a human-readable message from an exception or unknown object."""
    if isinstance(err, Exception):
        return str(err)
    return str(err)
