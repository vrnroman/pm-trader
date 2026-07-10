"""A-vs-B race comparison — the week's verdict machinery (2026-07).

Strategy A (lagged, censored, live-book fills) and strategy B (borrowed-clock
instant-copy at the target's price) run as parallel paper books. This module
computes the comparison both the daily snapshot and the day-7 verdict memo
render: headline realized dollars per book with the witnesses logged next to it
(ROI/copy, win rate, capital cycled — dollars decide, nothing gets dropped),
a per-wallet ROUTING TABLE (the deliverable is "which wallet routes through
which strategy", not a single winner), and a verdict-validity stamp — a week in
which either book sat starved for 48h+ must not produce a confident-sounding
winner.

The comparison window (the "era") starts at strategy B's first open: A existed
before the race, so only A copies opened inside the era count toward the race
(A's all-time record is shown as a witness, never the comparator).
"""

from __future__ import annotations

import datetime as _dt
import json
import time
from typing import Optional

from src.copy_trading import promotion_state

STALL_VOID_HOURS = 48.0     # a zero-open window this long compromises the verdict
MIN_WALLET_N = 5            # per-wallet routing needs at least this many settled


def _load_rows(path: str) -> list[dict]:
    rows: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    rows.append(d)
    except OSError:
        pass
    return rows


def _book_stats(rows: list[dict]) -> dict:
    closed = [r for r in rows if r.get("closed")]
    open_rows = [r for r in rows if not r.get("closed")]
    pnl = sum(float(r.get("pnl") or 0.0) for r in closed)
    spent = sum(float(r.get("spent") or 0.0) for r in closed)
    wins = sum(1 for r in closed if r.get("won"))
    return {
        "n_settled": len(closed),
        "n_open": len(open_rows),
        "open_usd": round(sum(float(r.get("spent") or 0.0) for r in open_rows), 2),
        "pnl": round(pnl, 2),
        "spent": round(spent, 2),
        "roi": round(pnl / spent, 4) if spent else 0.0,
        "win_rate": round(wins / len(closed), 4) if closed else 0.0,
    }


def _per_wallet(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        if not r.get("closed"):
            continue
        w = (r.get("target") or "").lower()
        p = out.setdefault(w, {"n": 0, "pnl": 0.0, "spent": 0.0, "wins": 0})
        p["n"] += 1
        p["pnl"] += float(r.get("pnl") or 0.0)
        p["spent"] += float(r.get("spent") or 0.0)
        p["wins"] += 1 if r.get("won") else 0
    for p in out.values():
        p["roi"] = p["pnl"] / p["spent"] if p["spent"] else 0.0
    return out


def _route_verdict(a: Optional[dict], b: Optional[dict]) -> str:
    """Per-wallet routing: which book does this wallet's evidence support?"""
    a_ok = a is not None and a["n"] >= MIN_WALLET_N
    b_ok = b is not None and b["n"] >= MIN_WALLET_N
    if not a_ok and not b_ok:
        return "dual-track (thin evidence)"
    if a_ok and not b_ok:
        return "A" if a["roi"] > 0 else "neither (A-negative, B thin)"
    if b_ok and not a_ok:
        return "B" if b["roi"] > 0 else "neither (B-negative, A thin)"
    a_pos, b_pos = a["roi"] > 0, b["roi"] > 0
    if a_pos and b_pos:
        return "both (A first)" if a["roi"] >= b["roi"] else "both (B first)"
    if a_pos:
        return "A"
    if b_pos:
        return "B"
    return "neither"


def _largest_gap_hours(rows: list[dict], era_start: float, now: float) -> float:
    """Largest zero-open stretch (hours) inside [era_start, now]."""
    opens = sorted(float(r.get("opened_ts") or 0.0) for r in rows
                   if float(r.get("opened_ts") or 0.0) >= era_start)
    points = [era_start] + opens + [now]
    return max((b - a) for a, b in zip(points, points[1:])) / 3600.0


def compare(
    a_ledger_path: str,
    b_ledger_path: str,
    *,
    b_slippage_bps: int = 0,
    now: Optional[float] = None,
) -> dict:
    """Compute the full A-vs-B comparison. Era = [B's first open, now]."""
    now = now if now is not None else time.time()
    a_rows_all = _load_rows(a_ledger_path)
    b_rows = _load_rows(b_ledger_path)

    era_start = min((float(r.get("opened_ts") or 0.0) for r in b_rows),
                    default=None)
    a_rows_era = ([r for r in a_rows_all
                   if float(r.get("opened_ts") or 0.0) >= era_start]
                  if era_start else [])

    a_stats = _book_stats(a_rows_era)
    b_stats = _book_stats(b_rows)
    a_all = _book_stats(a_rows_all)

    # per-wallet routing table (era-windowed on both sides)
    a_pw = _per_wallet(a_rows_era)
    b_pw = _per_wallet(b_rows)
    routing = []
    for w in sorted(set(a_pw) | set(b_pw),
                    key=lambda x: -(a_pw.get(x, {}).get("pnl", 0.0)
                                    + b_pw.get(x, {}).get("pnl", 0.0))):
        routing.append({
            "wallet": w, "a": a_pw.get(w), "b": b_pw.get(w),
            "route": _route_verdict(a_pw.get(w), b_pw.get(w)),
        })

    # verdict validity — a starved book voids the confident winner
    validity = {"valid": True, "reasons": [], "extend_days": 0.0}
    if era_start is None:
        validity = {"valid": False,
                    "reasons": ["strategy B has opened nothing yet — no era"],
                    "extend_days": 0.0}
    else:
        for name, rows in (("A", a_rows_era), ("B", b_rows)):
            gap_h = _largest_gap_hours(rows, era_start, now)
            if gap_h >= STALL_VOID_HOURS:
                validity["valid"] = False
                validity["reasons"].append(
                    f"book {name} had a {gap_h:.0f}h zero-open window")
                validity["extend_days"] = max(validity["extend_days"],
                                              round(gap_h / 24.0, 1))

    # promotions / governance per scope
    def _gov(scope: str) -> dict:
        return {
            "promoted": sorted(promotion_state.promoted_set(scope)),
            "offers": {w: r.get("status") for w, r in
                       promotion_state.offers_map(scope).items()},
            "blacklisted": sorted(promotion_state.active_blacklist(now, scope=scope)),
        }

    # day-by-day cumulative realized PnL per book (era only)
    def _daily(rows: list[dict]) -> list[tuple[str, float]]:
        per: dict[str, float] = {}
        for r in rows:
            if not r.get("closed"):
                continue
            day = _dt.datetime.fromtimestamp(
                float(r.get("closed_ts") or 0.0), _dt.timezone.utc).strftime("%m-%d")
            per[day] = per.get(day, 0.0) + float(r.get("pnl") or 0.0)
        out, cum = [], 0.0
        for day in sorted(per):
            cum += per[day]
            out.append((day, round(cum, 2)))
        return out

    return {
        "now": now,
        "era_start": era_start,
        "era_days": round((now - era_start) / 86400.0, 2) if era_start else 0.0,
        "b_slippage_bps": b_slippage_bps,
        "a": a_stats, "b": b_stats, "a_all_time": a_all,
        "routing": routing,
        "validity": validity,
        "gov_a": _gov(""), "gov_b": _gov("b"),
        "daily_a": _daily(a_rows_era), "daily_b": _daily(b_rows),
    }


def _fmt_book(name: str, s: dict) -> str:
    return (f"{name}: {s['n_settled']} settled, ${s['pnl']:+.0f} "
            f"({s['roi'] * 100:+.1f}%/copy, win {s['win_rate'] * 100:.0f}%, "
            f"${s['spent']:.0f} cycled) · {s['n_open']} open (${s['open_usd']:.0f})")


def format_snapshot(cmp: dict) -> str:
    """Compact daily Telegram snapshot (plain text, HTML-safe)."""
    v = cmp["validity"]
    lines = [
        f"🏁 A-vs-B race — day {cmp['era_days']:.1f}"
        + ("" if v["valid"] else " ⚠ WINDOW COMPROMISED"),
        _fmt_book("A (lagged)", cmp["a"]),
        _fmt_book(f"B (instant, +{cmp['b_slippage_bps']}bps)", cmp["b"]),
    ]
    routed = [r for r in cmp["routing"] if r["route"] in ("A", "B")]
    if routed:
        lines.append("routes: " + ", ".join(
            f"{r['wallet'][:8]}→{r['route']}" for r in routed[:6]))
    for reason in v["reasons"]:
        lines.append(f"⚠ {reason}")
    gov_bits = []
    if cmp["gov_a"]["promoted"]:
        gov_bits.append(f"A promoted {len(cmp['gov_a']['promoted'])}")
    if cmp["gov_b"]["promoted"]:
        gov_bits.append(f"B promoted {len(cmp['gov_b']['promoted'])}")
    if gov_bits:
        lines.append(" · ".join(gov_bits))
    return "\n".join(lines)


def format_verdict(cmp: dict) -> str:
    """The day-7 verdict memo (plain text; also the CLI report body)."""
    v = cmp["validity"]
    out = []
    out.append("=" * 64)
    out.append(f"A-vs-B RACE VERDICT — {cmp['era_days']:.1f} days "
               f"(era start {_dt.datetime.fromtimestamp(cmp['era_start'], _dt.timezone.utc):%Y-%m-%d %H:%M} UTC)"
               if cmp["era_start"] else "A-vs-B RACE — no era yet (B never opened)")
    out.append("=" * 64)
    if not v["valid"]:
        out.append("⚠ VERDICT INVALID — " + "; ".join(v["reasons"]))
        if v["extend_days"]:
            out.append(f"⚠ extend the window by ~{v['extend_days']:.1f} day(s) "
                       f"before calling a winner")
    out.append("")
    out.append("HEADLINE (realized $ decides; the rest are witnesses):")
    out.append("  " + _fmt_book("A in-era ", cmp["a"]))
    out.append("  " + _fmt_book(f"B (+{cmp['b_slippage_bps']}bps)", cmp["b"]))
    out.append("  " + _fmt_book("A all-time", cmp["a_all_time"]) + "  [witness]")
    out.append("")
    out.append(f"ROUTING TABLE (per-wallet, n>={MIN_WALLET_N} to route):")
    for r in cmp["routing"]:
        a, b = r["a"], r["b"]
        fa = (f"A {a['n']:>3} ${a['pnl']:+7.0f} {a['roi'] * 100:+6.1f}%"
              if a else "A   —              ")
        fb = (f"B {b['n']:>3} ${b['pnl']:+7.0f} {b['roi'] * 100:+6.1f}%"
              if b else "B   —              ")
        out.append(f"  {r['wallet'][:10]}… {fa} | {fb}  → {r['route']}")
    if not cmp["routing"]:
        out.append("  (no settled copies in either book yet)")
    out.append("")
    for name, key in (("A", "gov_a"), ("B", "gov_b")):
        g = cmp[key]
        out.append(f"GOVERNANCE {name}: promoted={len(g['promoted'])} "
                   f"offers={len(g['offers'])} blacklisted={len(g['blacklisted'])}"
                   + (f" ({', '.join(w[:8] for w in g['promoted'])})"
                      if g["promoted"] else ""))
    out.append("")
    for name, key in (("A", "daily_a"), ("B", "daily_b")):
        daily = cmp[key]
        if daily:
            out.append(f"CUM $ {name}: " + " ".join(f"{d}:{v:+.0f}" for d, v in daily))
    return "\n".join(out)
