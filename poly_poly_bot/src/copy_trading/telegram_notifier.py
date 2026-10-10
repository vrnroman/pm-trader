"""Telegram notification sender for copy-trading events."""

import httpx
from typing import Optional

from src.config import CONFIG
from src.logger import logger
from src.utils import error_message
from src.copy_trading.msg_format import (cents, esc, join, pick_line, shares, signed_usd,
                                          title_line, usd, wallet)

BOT_TOKEN = CONFIG.telegram_bot_token
CHAT_ID = CONFIG.telegram_chat_id


def _escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _bet_label(market: str, outcome: str = "") -> str:
    """What was bet, for the phone: the market title and the side taken.

    A trade whose market could not be named shows ``(market unnamed)`` rather
    than a bare ``""`` — an empty quote told the owner nothing on 2026-09-26.
    """
    title = _escape_html(market) if market else "(market unnamed)"
    side = f" — {_escape_html(outcome)}" if outcome else ""
    return f'"{title}"{side}' if market else f"{title}{side}"


def _plain(text: str) -> str:
    """Drop the HTML tags and unescape entities, for the plain-text retry."""
    import re
    out = re.sub(r"<[^>]+>", "", text)
    return (out.replace("&lt;", "<").replace("&gt;", ">")
               .replace("&quot;", '"').replace("&amp;", "&"))


async def _send_message(text: str, kind: str | None = "deal") -> bool:
    """Send as HTML; on a rejected parse retry as plain text. Returns whether
    anything was delivered, and LOGS a rejection: a 400 that vanished unlogged
    is how a message that mattered never reached the owner.

    Everything the executor announces is about a real order, so the default
    class is DEAL; the process-level notices pass KIND_BOT explicitly. The
    class prefix and the research switch live in `telegram_bot.classify`, one
    rule for both senders."""
    if not BOT_TOKEN or not CHAT_ID:
        return False
    from src import telegram_bot as _tb
    text, deliver = _tb.classify(text, kind)
    if not deliver:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})
            if resp.status_code == 200:
                return True
            logger.warn(f"Telegram rejected an HTML send ({resp.status_code}); "
                        f"retrying as plain text")
            resp2 = await client.post(url, json={"chat_id": CHAT_ID, "text": _plain(text)})
            if resp2.status_code == 200:
                return True
            logger.warn(f"Telegram rejected the plain retry too ({resp2.status_code}): "
                        f"{resp2.text[:120]}")
            return False
    except Exception as err:
        logger.warn(f"Telegram send failed: {error_message(err)}")
        return False


def _prefix(live_emoji: str) -> str:
    return "🔵 [PAPER]" if CONFIG.preview_mode else f"{live_emoji} [LIVE]"


def _win_lines(price: float, stake_usd: float, fee_bps: Optional[int]) -> list[str]:
    """What this ticket pays if it wins, after the fee, and the win rate it
    needs to break even (owner, 2026-10-01; reworded 2026-10-10)."""
    from src.copy_trading import fee_rate
    b = fee_rate.break_even(price, fee_bps, stake_usd)
    if fee_bps is None:
        fee = " (fee not read)"
    elif fee_bps <= 0:
        fee = " (no fee)"
    else:
        fee = f" after the {usd(b['fee_usd'])} fee ({b['fee_share'] * 100:.1f}%)"
    return [f"If it wins: {usd(b['payout'])} back, {signed_usd(b['net'])}{fee}",
            f"<i>Break-even: needs to win {b['be_win'] * 100:.0f}% of bets like this</i>"]


class TelegramNotifier:
    async def trade_placed(self, market: str, side: str, size: float, price: float,
                           outcome: str = "", trader: str = "",
                           their_price: Optional[float] = None) -> None:
        """The order is on the exchange; the fill report follows."""
        who = f"Copying {wallet(trader)}" if trader else ""
        if who and their_price:
            who += f" (they paid {cents(their_price)})" if side == "BUY" else f" (they sold at {cents(their_price)})"
        if side == "BUY":
            n = (size / price) if price else 0.0
            text = join(f"{_prefix('🟢')} <b>Bet placed: {usd(size)}</b>",
                        title_line(market),
                        pick_line(outcome),
                        f"Price {cents(price)}, about {shares(n)} shares; pays about {usd(n)} if it wins"
                        if price else "",
                        who)
        else:
            text = join(f"{_prefix('🟠')} <b>Selling: about {usd(size)}</b>",
                        title_line(market),
                        pick_line(outcome),
                        f"Price {cents(price)}",
                        who.replace("Copying", "Following") + " out of this bet" if who else "")
        await _send_message(text)

    async def trade_filled(self, market: str, shares_n: float, price: float,
                           outcome: str = "", fee_bps: Optional[int] = None,
                           side: str = "BUY") -> None:
        cost = shares_n * price
        if side == "BUY":
            lines = [f"{_prefix('✅')} <b>Bet filled: {usd(cost)}</b>",
                     title_line(market), pick_line(outcome),
                     f"{shares(shares_n)} shares at {cents(price)}"]
            if shares_n and price:
                try:
                    lines += _win_lines(price, cost, fee_bps)
                except Exception:  # noqa: BLE001  a line, never a blocker
                    pass
        else:
            lines = [f"{_prefix('✅')} <b>Sold: {usd(cost)} back</b>",
                     title_line(market), pick_line(outcome),
                     f"{shares(shares_n)} shares at {cents(price)}"]
        await _send_message(join(*lines))

    async def trade_unfilled(self, market: str, outcome: str = "") -> None:
        await _send_message(join(f"{_prefix('⚪')} <b>Bet not filled, cancelled</b>",
                                 title_line(market), pick_line(outcome),
                                 "Nobody took the order at our price. No money spent."))

    async def trade_failed(self, market: str, reason: str, outcome: str = "") -> None:
        await _send_message(join(f"{_prefix('🔴')} <b>Bet NOT placed</b>",
                                 title_line(market), pick_line(outcome),
                                 f"Why: {esc(reason)}"))

    async def _bot_kind(self, text: str) -> None:
        await _send_message(text, kind="bot")

    async def bot_started(self, traders: int, balance: float) -> None:
        mode = "paper mode" if CONFIG.preview_mode else "LIVE"
        await _send_message(join(f"🚀 <b>Bot started ({mode})</b>",
                                 f"Following {traders} wallets. Cash: {usd(balance)}"), kind="bot")

    async def bot_error(self, error: str) -> None:
        await _send_message(f"⚠️ <b>Error</b>\n{_escape_html(error)}", kind="bot")

    async def positions_redeemed(self, count: int, details: list) -> None:
        lines = [f"💰 <b>Collected {count} finished bet(s)</b>"]
        for d in details:
            pnl = d.returned - d.cost_basis
            icon = "✅" if d.returned > d.cost_basis else "❌"
            lines.append(f"{icon} {esc(d.title)}: staked {usd(d.cost_basis)}, "
                         f"got {usd(d.returned)} ({signed_usd(pnl)})")
        await _send_message("\n".join(lines))

    async def daily_summary(self, trades: int, pnl: str, balance: float) -> None:
        await _send_message(join("📊 <b>Daily summary</b>",
                                 f"Copies today: {trades}", f"Result: {pnl}",
                                 f"Cash: {usd(balance)}"))


telegram = TelegramNotifier()
