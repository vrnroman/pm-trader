"""The missed book: live copies refused for lack of money, kept on paper.

Owner, 2026-10-11: "If you don't do a bet due to some reason like no money
again, still keep it in paper, so later I can check." With ~$50 in the wallet
the live book runs out of room often (open-at-once cap reached, cash tied up
in open bets, the bankroll governor or the arm off), and every one of those
refusals is a bet the strategy WOULD have made. This ledger books each one at
the live stake and the target's own price, and settles it from Gamma, so
"what did running out of money cost?" has a number.

Only refusals for money or capacity land here. Rule refusals (price band,
trader bet under the floor, flip gate, market quality, max copies per market)
are the strategy saying no, not the wallet, and stay out.

Entry is the target's price with no slippage: our measured median fill gap to
the target is 0% (2026-10-11, 60 matched copies), so this is the honest
estimate, not a flattering one.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable, Optional

from src.copy_trading.copy_paper import REFUNDED, PaperCopyLedger, PaperPosition
from src.logger import logger

_lock = threading.Lock()

# Reasons (lower-cased substrings) that mean "no money or no room", not "no".
MONEY_REASONS = (
    "bankroll governor",
    "exposure full",
    "daily spend cap",
    "spend guard closed",
    "cash on chain",
    "disarmed",
    # Not money, but capacity the owner chose (3 open per wallet, 2026-10-14):
    # booked so the cap can be judged against what it turned away.
    "wallet slots full",
    # Owner's long-shot rule (no entry under 0.35, 2026-10-14): booked for
    # the same reason, so the rule is judged against what it turned away.
    "entry under",
    # Market-quality refusals (price drift, spread): booked since 2026-10-18
    # because the drift rail was keeping the losers (see trade_executor).
    "market quality",
)


def ledger_path() -> str:
    return os.environ.get("MISSED_PAPER_LEDGER", "data/missed-live-ledger.jsonl")


def stake_usd() -> float:
    try:
        v = float(os.environ.get("LIVE_PER_COPY_USD", "") or 5.0)
    except ValueError:
        v = 5.0
    return v if v > 0 else 5.0


def is_money_reason(reason: str) -> bool:
    r = (reason or "").lower()
    return any(k in r for k in MONEY_REASONS)


def record(trade, reason: str, *, now: Optional[float] = None,
           max_per_token: Optional[int] = None) -> bool:
    """Book a refused live BUY on paper. Returns True when a row was written.
    Never raises: a paper bookkeeping failure must not touch the live path."""
    try:
        if (getattr(trade, "side", "") or "").upper() != "BUY":
            return False
        price = float(getattr(trade, "price", 0.0) or 0.0)
        token = str(getattr(trade, "token_id", "") or "")
        if not (0.0 < price < 1.0) or not token:
            return False
        if max_per_token is None:
            from src.config import CONFIG
            max_per_token = int(getattr(CONFIG, "max_copies_per_market_side", 2) or 2)
        now = time.time() if now is None else now
        copy_id = f"{getattr(trade, 'id', '')}-{token}"
        stake = stake_usd()
        with _lock:
            led = PaperCopyLedger(ledger_path())
            if led.has(copy_id):
                return False
            # The live book copies a market side at most this many times;
            # the missed book must not be more generous than live would be.
            target = (getattr(trade, "trader_address", "") or "").lower()
            same = sum(1 for p in led.positions.values()
                       if p.token_id == token and p.target == target)
            if same >= max_per_token:
                return False
            led.add(PaperPosition(
                copy_id=copy_id, target=target,
                condition_id=str(getattr(trade, "condition_id", "") or ""),
                token_id=token, outcome_index=-1, category="missed",
                their_price=price, entry_price=price,
                shares=round(stake / price, 4), spent=stake, drag_bps=0,
                opened_ts=now, title=str(getattr(trade, "market", "") or "")[:120],
                slug=str(reason or "")[:160]))
        logger.info(f"[missed] on paper: ${stake:.2f} on "
                    f"'{str(getattr(trade, 'market', ''))[:40]}' @ {price:.3f} "
                    f"(live refused: {str(reason)[:80]})")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warn(f"[missed] paper row not written: {exc}")
        return False


def _gamma_market(condition_id: str) -> Optional[dict]:
    from src.copy_trading.copy_paper_live import GAMMA, _get
    j = _get(GAMMA, "/markets", condition_ids=condition_id, closed="true")
    return j[0] if j else None


def _winner(market: dict, token_id: str) -> Optional[object]:
    """True / False for a resolved market, REFUNDED for a cancelled one,
    None while open or unreadable."""
    from src.copy_trading.copy_paper_live import parse_winner
    idx = parse_winner(market)
    if idx is None:
        return None
    if idx == REFUNDED:
        return REFUNDED  # an int, never a bool: settle() tells them apart
    toks = market.get("clobTokenIds")
    if isinstance(toks, str):
        try:
            toks = json.loads(toks)
        except json.JSONDecodeError:
            return None
    if not toks or idx >= len(toks):
        return None
    return str(toks[idx]) == str(token_id)


def settle(*, now: Optional[float] = None, max_lookups: int = 25,
           fetch: Callable[[str], Optional[dict]] = _gamma_market) -> int:
    """Close the missed bets whose markets resolved. Returns how many closed.
    Bounded per call (oldest first) so a backlog never stalls the guard."""
    now = time.time() if now is None else now
    with _lock:
        led = PaperCopyLedger(ledger_path())
        open_ = sorted(led.open_positions(), key=lambda p: p.opened_ts)
    seen: dict[str, Optional[dict]] = {}
    verdicts: dict[str, object] = {}
    for p in open_:
        if len(seen) >= max_lookups:
            break
        if not p.condition_id:
            continue
        if p.condition_id not in seen:
            try:
                seen[p.condition_id] = fetch(p.condition_id)
            except Exception:  # noqa: BLE001
                seen[p.condition_id] = None
        m = seen[p.condition_id]
        if m:
            w = _winner(m, p.token_id)
            if w is not None:
                verdicts[p.copy_id] = w
    if not verdicts:
        return 0
    with _lock:
        led = PaperCopyLedger(ledger_path())
        n = 0
        for cid, w in verdicts.items():
            p = led.positions.get(cid)
            if p is None or p.closed:
                continue
            if not isinstance(w, bool) and w == REFUNDED:
                p.realize_refund(now)
            else:
                p.realize(bool(w), now)
            n += 1
        if n:
            led.save()
    logger.info(f"[missed] settled {n} paper bet(s)")
    return n


def summary(since_ts: float = 0.0) -> dict:
    """Totals for the missed book: what lack of money cost (or saved)."""
    led = PaperCopyLedger(ledger_path())
    rows = [p for p in led.positions.values() if p.opened_ts >= since_ts]
    closed = [p for p in rows if p.closed]
    spent = sum(p.spent for p in closed)
    pnl = sum(p.pnl for p in closed)
    by_wallet: dict[str, list] = {}
    for p in closed:
        b = by_wallet.setdefault(p.target, [0, 0, 0.0, 0.0])
        b[0] += 1
        b[1] += bool(p.won)
        b[2] += p.spent
        b[3] += p.pnl
    return {
        "booked": len(rows), "open": len(rows) - len(closed),
        "open_usd": round(sum(p.spent for p in rows if not p.closed), 2),
        "settled": len(closed), "won": sum(1 for p in closed if p.won),
        "spent": round(spent, 2), "pnl": round(pnl, 2),
        "roi": (pnl / spent) if spent else None,
        "by_wallet": by_wallet,
        "by_reason": _reason_counts(rows),
    }


def _reason_counts(rows) -> dict:
    out: dict[str, int] = {}
    for p in rows:
        r = (p.slug or "").lower()
        k = next((m for m in MONEY_REASONS if m in r), "other")
        out[k] = out.get(k, 0) + 1
    return out


def summary_lines(since_ts: float = 0.0) -> list[str]:
    """Plain-text lines for Telegram (the caller escapes)."""
    s = summary(since_ts)
    if not s["booked"]:
        return ["Missed book: no live copies refused for money yet."]
    roi = f"{s['roi'] * 100:+.1f}%" if s["roi"] is not None else "n/a"
    out = [f"Missed book (live refused for money, kept on paper at ${stake_usd():.0f}):",
           f"  {s['booked']} booked · {s['open']} open (${s['open_usd']:.2f})",
           f"  settled {s['settled']}: {s['won']} won · P&L ${s['pnl']:+.2f} · ROI {roi}"]
    for w, (n, won, spent, pnl) in sorted(s["by_wallet"].items(), key=lambda kv: kv[1][3]):
        out.append(f"  {w[:6]}…{w[-4:]}: {n} settled, {won} won, ${pnl:+.2f}")
    if s.get("by_reason"):
        out.append("  refused because: " + ", ".join(
            f"{k} {v}" for k, v in sorted(s["by_reason"].items(), key=lambda kv: -kv[1])))
    # The owner tops up after a "stable 3-day winning streak" on this book
    # (2026-10-15): one line per UTC day of settlement, and the streak.
    days = by_day(since_ts)
    if days:
        out.append("  by day settled (UTC):")
        for d, (n, won, pnl) in days[-7:]:
            out.append(f"    {d}: {n} settled, {won} won, ${pnl:+.2f}")
        streak = winning_streak(days)
        out.append(f"  winning days in a row: {streak}" + (" ✅ (3 reached)" if streak >= 3 else " (top-up at 3)"))
    return out


def by_day(since_ts: float = 0.0) -> list:
    """[(YYYY-MM-DD, settled, won, pnl)] per UTC day of settlement, ascending."""
    led = PaperCopyLedger(ledger_path())
    d: dict[str, list] = {}
    for p in led.positions.values():
        if not p.closed or p.opened_ts < since_ts:
            continue
        k = time.strftime("%Y-%m-%d", time.gmtime(p.closed_ts))
        b = d.setdefault(k, [0, 0, 0.0])
        b[0] += 1
        b[1] += bool(p.won)
        b[2] += p.pnl
    return sorted((k, (v[0], v[1], round(v[2], 2))) for k, v in d.items())


def winning_streak(days: list, now: Optional[float] = None) -> int:
    """Consecutive positive days ending with the last day that has settled
    bets. A day with no settlements breaks nothing and counts nothing."""
    n = 0
    for _, (cnt, _won, pnl) in reversed(days):
        if cnt and pnl > 0:
            n += 1
        else:
            break
    return n
