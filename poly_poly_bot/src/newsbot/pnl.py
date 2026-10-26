"""The experiment's P&L, in money: what the news bot would have won or lost.

Every number is a paper bet of NEWS_STAKE_USD bought at the real ask (walked
for the size, fee in) and sold at the real bid (walked, fee again) at each
horizon, or held to resolution. The ``llm`` book is the one that would trade
real money; the others are its controls. Nothing is shown without its n; an
empty horizon reads "collecting", never $0. Void rows (duplicates) are left
out and counted. Days are Singapore days: the owner reads SGT.
"""

from __future__ import annotations

import html
import time
from typing import Callable, Mapping, Optional

from src.newsbot.paper import HORIZONS_S, PaperLedger

SGT_S = 8 * 3600
EXIT = "2h"       # the planned exit: the owner's 2 h to 1 day, the first of them
CONTROLS = (("llm", "material and the market had not moved yet: the book that would trade"),
            ("headline-any", "every material call, moved or not"),
            ("tape-first", "a price jump with a headline minutes before it"),
            ("random", "a random market for every llm bet: the bar to beat"))


def _esc(s) -> str:
    return html.escape(str(s), quote=False)


def _sgt(ts: float, fmt: str = "%m-%d %H:%M") -> str:
    return time.strftime(fmt, time.gmtime(ts + SGT_S))


def _money(x: float) -> str:
    return f"{'+' if x >= 0 else '-'}${abs(x):.2f}"


def _horizon(rows, h: str) -> Optional[tuple[int, float, float]]:
    """(n, pnl, roi) of the rows marked at ``h`` with a readable bid."""
    rs = [r for r in rows if h in r.marks and r.marks[h].get("pnl") is not None]
    if not rs:
        return None
    pnl = sum(r.marks[h]["pnl"] for r in rs)
    spent = sum(r.filled_usd + r.fee_usd for r in rs)
    return len(rs), pnl, (pnl / spent if spent else 0.0)


def _line(label: str, v: Optional[tuple[int, float, float]], width: int = 4) -> str:
    if v is None:
        return f"{label:<{width}} collecting (n=0)"
    n, pnl, roi = v
    return f"{label:<{width}} {_money(pnl)} ({roi * 100:+.1f}%, n={n})"


def book_rows(ledger: PaperLedger, since_ts: float = 0.0) -> list:
    return [r for r in ledger.live_rows() if r.decided_ts >= since_ts]


def pnl_text(ledgers: Mapping[str, PaperLedger], *, now: Optional[float] = None,
             bid_now: Optional[Callable[[str], Optional[float]]] = None, short: bool = False) -> str:
    """The /pnl report. ``bid_now(token)`` marks open bets at the current
    bid when the running bot can read one."""
    now = time.time() if now is None else now
    llm = ledgers.get("llm")
    rows = book_rows(llm) if llm else []
    all_rows = [r for led in ledgers.values() for r in led.rows.values()]
    start = min((r.decided_ts for r in all_rows), default=None)
    void = sum(1 for r in all_rows if r.void)
    out = ["📊 <b>News bot P&amp;L</b> (paper: $%.0f a bet at the real ask, sold at the real bid, fees in)"
           % (rows[0].stake if rows else 5)]
    if start is not None:
        out.append(f"Since {_sgt(start, '%Y-%m-%d %H:%M')} SGT")
    out.append("")
    staked = sum(r.filled_usd + r.fee_usd for r in rows)
    resolved = [r for r in rows if r.resolution_pnl is not None]
    open_rows = [r for r in rows if not r.closed]
    out.append(f"<b>The book that would trade (llm)</b>: {len(rows)} bets, ${staked:.2f} staked, "
               f"{len(open_rows)} open, {len(resolved)} resolved")
    out.append("<pre>")
    for h in HORIZONS_S:
        out.append(_esc(_line(f"{h}", _horizon(rows, h))) + ("  ← planned exit" if h == EXIT else ""))
    if resolved:
        won = sum(1 for r in resolved if r.resolved)
        rp = sum(r.resolution_pnl for r in resolved)
        out.append(_esc(f"held {_money(rp)} ({won} won of {len(resolved)})"))
    else:
        out.append("held collecting (none resolved yet)")
    out.append("</pre>")
    if bid_now is not None and open_rows:
        val, n = 0.0, 0
        for r in open_rows:
            b = bid_now(r.token_id)
            if b is not None:
                val += r.exit_pnl(b)
                n += 1
        if n:
            out.append(f"Open bets if sold at the bid now: {_money(val)} (n={n})")
    if short:
        v = _horizon(rows, EXIT)
        r = _horizon(book_rows(ledgers["random"]), EXIT) if "random" in ledgers else None
        out.append(f"Against random at {EXIT}: llm {_money(v[1]) if v else 'n=0'} vs random "
                   f"{_money(r[1]) if r else 'n=0'}. /pnl for the rest.")
        return "\n".join(out)

    out.append("")
    out.append(f"<b>Against the controls</b>, sold after {EXIT}:")
    out.append("<pre>")
    for name, _ in CONTROLS:
        if name in ledgers:
            out.append(_esc(_line(name, _horizon(book_rows(ledgers[name]), EXIT), width=12)))
    out.append("</pre>")
    out.append("<i>" + " · ".join(f"{n}: {d}" for n, d in CONTROLS if n in ledgers) + "</i>")

    day0 = now - ((now + SGT_S) % 86400)
    today = book_rows(llm, since_ts=day0) if llm else []
    tv = _horizon(today, EXIT)
    out.append("")
    out.append(f"Today (SGT): {len(today)} bets" + (f", {EXIT} {_money(tv[1])} (n={tv[0]})" if tv else ""))
    if rows:
        out.append("")
        out.append("<b>Last bets</b>")
        for r in sorted(rows, key=lambda r: r.decided_ts)[-6:]:
            m = r.marks.get(EXIT) or {}
            res = (f"{EXIT} {_money(m['pnl'])}" if m.get("pnl") is not None
                   else "unquotable" if EXIT in r.marks else "open")
            if r.resolution_pnl is not None:
                res += f", held {_money(r.resolution_pnl)}"
            out.append(f"{_sgt(r.decided_ts)} {_esc(r.outcome)} @ {r.entry_price:.2f} "
                       f"<b>{_esc(r.question[:70])}</b>: {res}")
    if void:
        out.append(f"\n<i>{void} duplicate row(s) voided and left out.</i>")
    return "\n".join(out)
