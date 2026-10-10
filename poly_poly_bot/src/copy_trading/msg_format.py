"""One phone grammar for every real-money message (owner, 2026-10-10: "what
did we bet, etc, just make everything more readable").

Every deal message has the same shape, so the owner reads them the same way:

    <emoji> <b>Headline with the money</b>
    <b>Market title</b>
    Pick: <b>outcome</b>
    one or two plain lines of numbers

Prices are shown in cents (45¢), money with a sign where it is a result
(+$7.80, -$6.40). No em or en dashes (the owner has named them). Pure
functions, no I/O: tested directly.
"""
from __future__ import annotations

from typing import Optional


def esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def usd(x: float) -> str:
    """$6.40, or $1,234 for big round numbers."""
    x = float(x or 0.0)
    return f"${x:,.0f}" if abs(x) >= 1000 else f"${x:,.2f}"


def signed_usd(x: float) -> str:
    """+$7.80 / -$6.40 / $0.00."""
    x = round(float(x or 0.0), 2)
    if x > 0:
        return f"+{usd(x)}"
    if x < 0:
        return f"-{usd(-x)}"
    return usd(0.0)


def cents(price: Optional[float]) -> str:
    """0.45 -> 45¢, 0.995 -> 99.5¢. An unknown price reads '?'."""
    if price is None:
        return "?"
    c = float(price) * 100.0
    if abs(c - round(c)) < 0.05:
        return f"{round(c):.0f}¢"
    return f"{c:.1f}¢"


def shares(n: float) -> str:
    n = float(n or 0.0)
    return f"{n:,.0f}" if abs(n - round(n)) < 0.005 else f"{n:,.2f}"


def wallet(addr: str) -> str:
    a = str(addr or "")
    return f"{a[:6]}…{a[-4:]}" if len(a) > 12 else (a or "?")


def title_line(title: str) -> str:
    return f"<b>{esc(title)}</b>" if title else "<i>(market name unknown)</i>"


def pick_line(outcome: str) -> str:
    return f"Pick: <b>{esc(outcome)}</b>" if outcome else ""


def join(*lines: str) -> str:
    """The non-empty lines, one per row."""
    return "\n".join(l for l in lines if l)
