"""The go-live bar, written down before the books run (run s-wj4gnb, 2026-11-01).

The owner's mandate after the copy bot (2026-10-18): real money resumes only
on a positive slice at REAL quotes and fees, about two standard errors clear.
This module is that sentence as code, so a lucky three days cannot read as
an edge and nobody re-derives the bar from a chart.

Counted per EVENT, not per row: the Serbian turnout night put six threshold
markets of one election in the llm book and they moved as one. A row's
event is its ``event`` field (the Gamma event title), else its market.
Only rows whose every mark read a current book (``fresh_marks``) count.

    GO       >= MIN_EVENTS events and the mean event ROI is more than Z
             standard errors above zero
    NO-GO    >= MIN_EVENTS events and it is not
    NOT-YET  fewer events than that: "n of 25", never a hint either way
"""

from __future__ import annotations

import math
import os
from typing import Iterable, Optional

MIN_EVENTS = 25
Z = 2.0


def _env_i(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def min_events() -> int:
    return _env_i("NEWS_VERDICT_MIN_EVENTS", MIN_EVENTS)


def event_key(row) -> str:
    return str(getattr(row, "event", "") or row.condition_id or row.market_id)


def clean(rows: Iterable) -> list:
    return [r for r in rows if getattr(r, "fresh_marks", False) and not r.void]


def _cluster(pairs: list[tuple[str, float, float]]) -> Optional[dict]:
    """pairs of (event, value, weight). Per event: the weighted mean value;
    then the mean over events and its standard error."""
    by: dict[str, list[float]] = {}
    for ev, v, w in pairs:
        acc = by.setdefault(ev, [0.0, 0.0])
        acc[0] += v
        acc[1] += w
    if not by:
        return None
    vals = [s / w for s, w in by.values() if w > 0]
    k = len(vals)
    if not k:
        return None
    mean = sum(vals) / k
    # the sample SE (k - 1): the bar must not be easier than it says
    se = math.sqrt(sum((x - mean) ** 2 for x in vals) / (k - 1)) / math.sqrt(k) if k > 1 else float("inf")
    return {"rows": len(pairs), "events": k, "mean": mean, "se": se}


def book_stat(rows: Iterable, horizon: str = "2h") -> Optional[dict]:
    """ROI per event at ``horizon``: event P&L over event dollars staked."""
    pairs = []
    for r in clean(rows):
        m = r.marks.get(horizon) or {}
        if m.get("pnl") is None:
            continue
        cost = r.filled_usd + r.fee_usd
        pairs.append((event_key(r), float(m["pnl"]), cost))
    st = _cluster(pairs)
    if st is not None:
        st["pnl"] = round(sum(v for _, v, _ in pairs), 2)
    return st


def split(rows: Iterable, horizon: str = "2h") -> Optional[dict]:
    """Where the money went: ``spread`` is what crossing the book cost at
    entry (ask - bid over the entry price), ``signal`` is how far the MID
    moved our way by ``horizon`` over the entry price. A book with no edge
    reads signal ~0 and loses the spread; per event, like the verdict."""
    sp, sg = [], []
    for r in clean(rows):
        m = r.marks.get(horizon) or {}
        if not r.entry_price or r.bid_top is None or r.ask_top is None:
            continue
        ev = event_key(r)
        sp.append((ev, (r.ask_top - r.bid_top) / r.entry_price, 1.0))
        if r.mid_entry is not None and m.get("mid") is not None:
            sg.append((ev, (m["mid"] - r.mid_entry) / r.entry_price, 1.0))
    a, b = _cluster(sp), _cluster(sg)
    if a is None:
        return None
    return {"spread": a, "signal": b}


def verdict(rows: Iterable, horizon: str = "2h", *, need: Optional[int] = None, z: float = Z) -> dict:
    need = min_events() if need is None else need
    st = book_stat(rows, horizon)
    if st is None:
        return {"state": "NOT-YET", "events": 0, "need": need, "stat": None}
    if st["events"] < need:
        return {"state": "NOT-YET", "events": st["events"], "need": need, "stat": st}
    ok = st["se"] != float("inf") and st["mean"] > z * st["se"]
    return {"state": "GO" if ok else "NO-GO", "events": st["events"], "need": need, "stat": st}


def verdict_line(name: str, rows: Iterable, horizon: str = "2h") -> str:
    v = verdict(rows, horizon)
    st = v["stat"]
    if st is None:
        return f"{name}: NOT-YET (0 of {v['need']} events, collecting)"
    se = "n/a" if st["se"] == float("inf") else f"{st['se'] * 100:.1f}"
    body = f"{st['mean'] * 100:+.1f}% ±{se} per event, {st['events']} events / {st['rows']} bets"
    if v["state"] == "NOT-YET":
        return f"{name}: NOT-YET ({st['events']} of {v['need']} events) {body}"
    return f"{name}: {v['state']} {body}"


def by_domain(rows: Iterable, horizon: str = "2h") -> dict:
    """The break-even map (run s-wj4gnb, phase 2): per domain, the spread
    paid and the mid's move our way, per event. A group under the bar's
    event count is "too few": the copy bot's 11,626 slices left 0 survivors
    out of sample (2026-10-18), so a small group's number is never an edge."""
    groups: dict[str, list] = {}
    for r in clean(rows):
        for d in (r.domains or ("?",))[:1]:
            groups.setdefault(str(d), []).append(r)
    return {d: split(rs, horizon) for d, rs in sorted(groups.items())}


def domain_lines(rows: Iterable, horizon: str = "2h") -> list[str]:
    need = min_events()
    out = []
    for d, sp in by_domain(rows, horizon).items():
        if sp is None:
            continue
        a, b = sp["spread"], sp["signal"]
        if b is None:
            sig, ev = "signal n=0", a["events"]
        else:
            se = "" if b["se"] == float("inf") else f" ±{b['se'] * 100:.1f}"
            sig, ev = f"signal {b['mean'] * 100:+.1f}%{se}", b["events"]
        flag = "too few" if ev < need else ("clears the spread" if b is not None and b["se"] != float("inf")
                                             and b["mean"] - Z * b["se"] > a["mean"] else "does not clear")
        out.append(f"{d}: spread {a['mean'] * 100:.1f}%, {sig} ({ev} events, {flag})")
    return out
