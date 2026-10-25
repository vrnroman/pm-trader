"""What the phone says: one fire message per paper fire, one line a day,
surprise pings by a rules table, and /news on demand.

Rulings (manager, 2026-10-25): the fire message carries headline, market,
honest ask, depth and the tape's freshness line, never a confidence number
(it stays in the ledger). Timed exits are never pinged; they land in the
08:00 UTC brief. The brief is one gist line first, then raw counts, with
estimates labelled "estimate" and the dark fraction printed even when ugly.
Every number carries n; empty is "collecting, n=0".
"""

from __future__ import annotations

import json
import time
from typing import Callable, Optional

from src.newsbot import paper as paper_mod

_esc_fn: Optional[Callable[[str], str]] = None


def _esc(s: str) -> str:
    global _esc_fn
    if _esc_fn is None:
        try:
            from src.telegram_bot import _esc as e
            _esc_fn = e
        except Exception:  # noqa: BLE001
            import html
            _esc_fn = lambda t: html.escape(str(t), quote=False)  # noqa: E731
    return _esc_fn(str(s))


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x * 100:+.1f}%"


def _dur(s: Optional[float]) -> str:
    if s is None:
        return "n/a"
    s = float(s)
    if abs(s) < 90:
        return f"{s:.0f}s"
    if abs(s) < 5400:
        return f"{s / 60:.0f}m"
    return f"{s / 3600:.1f}h"


# ---- per-fire message ----

def fire_message(row: paper_mod.PaperRow, *, headline: str, source: str,
                 freshness_detail: str, depth_usd: Optional[float]) -> str:
    """Headline, market, the honest ask, depth, the tape's line. No confidence."""
    depth = f"${depth_usd:.0f} on the ask" if depth_usd is not None else "depth unknown"
    fill = (f"filled ${row.filled_usd:.2f} of ${row.stake:.2f}"
            if row.filled_usd < row.stake - 0.01 else f"${row.filled_usd:.2f}")
    return (f"📰 <b>Paper BUY</b> {fill} @ {row.entry_price:.3f} (top {row.ask_top:.3f}, fee ${row.fee_usd:.2f})\n"
            f"<b>{_esc(row.question[:90])}</b> [{_esc(row.outcome)}]\n"
            f"{_esc(headline[:140])}\n"
            f"via {_esc(source)} · {depth} · tape: {_esc(freshness_detail)}\n"
            f"book {row.book} · exits at +5m/+30m/+2h/+24h in the morning brief")


# ---- surprise pings (a rules table, not a judgement) ----

def missed_move_message(question: str, cents: float, horizon: str, item_source: str) -> str:
    return (f"👀 <b>Moved without us</b> {cents:+.0f}c in {horizon}\n"
            f"<b>{_esc(question[:90])}</b>\nmapped from {_esc(item_source)} but not fired "
            f"(tape said it was already moving, or the budget was out)")


def silent_source_message(key: str, hours: float) -> str:
    return f"🔇 <b>Source silent</b> {_esc(key)}: nothing for {hours:.0f}h (others still arrive)"


def quiet_box_message(minutes: float) -> str:
    return f"🫥 <b>No items at all</b> for {minutes:.0f} min across every source: check the box"


# ---- the daily brief and /news ----

def _book_line(name: str, s: dict) -> str:
    hs = s.get("horizons", {})
    cells = []
    for h in ("5m", "30m", "2h", "24h"):
        c = hs.get(h, {"n": 0})
        if not c.get("n"):
            cells.append(f"{h} n=0")
        else:
            cells.append(f"{h} {_pct(c.get('roi'))}±{c.get('sd', 0) * 100:.0f} n={c['n']}")
    res = s.get("resolution", {"n": 0})
    rl = (f" · settled {res['n']}: {res.get('won', 0)}W ${res.get('pnl', 0):+.2f}" if res.get("n") else "")
    return f"  {name}: " + " · ".join(cells) + rl


def best_exit_estimate(books: dict) -> str:
    """The horizon with the best ROI on the main book, labelled an estimate."""
    s = books.get("llm") or {}
    best = None
    for h, c in (s.get("horizons") or {}).items():
        if c.get("n", 0) >= 10 and c.get("roi") is not None:
            if best is None or c["roi"] > best[1]:
                best = (h, c["roi"], c["n"])
    if not best:
        return "best exit: collecting (needs n>=10 per horizon)"
    return f"best exit (estimate): {best[0]} at {_pct(best[1])} on n={best[2]}"


def gist(stats: dict, books: dict, today: dict) -> str:
    a = stats["domains"].get("all", {})
    fired = a.get("fired", 0)
    moved = a.get("fired_moved_our_way", 0)
    dark = a.get("dark_frac")
    dark_s = "dark n=0" if dark is None else (f"dark {dark * 100:.0f}% of {a.get('jumps', 0)} jumps "
                                                f"(watched {a.get('watched', 0)}, unknown {a.get('unknown', 0)})")
    if a.get("owner_explained"):
        dark_s += f" · explained later by owner {a['owner_explained']} (late by {_dur(a.get('owner_late_median_s'))})"
    lead = a.get("lead_median_s")
    stale = f" ({today['stale']} stale skipped)" if today.get("stale") else ""
    return (f"{today.get('items', 0)} items{stale}, {a.get('mapped', 0)} mapped, {fired} fired, "
            f"{moved} moved our way · our lag {_dur(a.get('latency_median_s'))} · "
            f"source lead median {_dur(lead)} · {dark_s}")


def brief_text(*, stats: dict, books: dict, today: dict, roster: dict, llm: dict,
               since_label: str) -> str:
    lines = [f"🗞 <b>News bot</b> {since_label}", _esc(gist(stats, books, today)), ""]
    lines.append("<b>By domain</b> (items · mapped · fired · moved/against/flat · dark)")
    for dom, d in sorted(stats["domains"].items()):
        if dom == "all":
            continue
        if not d.get("items") and not d.get("jumps"):
            continue
        dk = "n=0" if d.get("dark_frac") is None else f"{d['dark_frac'] * 100:.0f}% of {d['jumps']}"
        if d.get("unknown"):
            dk += f" (unknown {d['unknown']})"
        if d.get("owner_explained"):
            dk += f" · owner explained {d['owner_explained']}"
        lines.append(f"  {dom}: {d['items']} · {d['mapped']} · {d['fired']} · "
                     f"{d['fired_moved_our_way']}/{d['fired_moved_against']}/{d['fired_flat']} · {dk}"
                     + (f" · lead {_dur(d['lead_median_s'])} (n={d['lead_n']})" if d.get("lead_n") else ""))
    lines.append("")
    lines.append("<b>Books</b> (ROI after fees at the honest bid, ±1 SD)")
    for name in ("llm", "tape-first", "headline-any", "random"):
        if name in books:
            lines.append(_esc(_book_line(name, books[name])))
    lines.append("  " + _esc(best_exit_estimate(books)))
    lines.append("")
    # the machinery, collapsed to raw counts
    srcs = roster or {}
    silent = [k for k, v in srcs.items() if v.get("last_item_ts") and time.time() - float(v["last_item_ts"]) > 6 * 3600]
    errs = sum(int(v.get("errors", 0) or 0) for v in srcs.values())
    lines.append(f"<i>machinery: {len(srcs)} sources, {sum(int(v.get('items', 0) or 0) for v in srcs.values())} items total, "
                 f"{errs} errors, {len(silent)} silent >6h · LLM calls today {llm.get('today', 0)}/{llm.get('limit', 0)}"
                 f"{' · budget hit' if llm.get('exhausted') else ''}</i>")
    return "\n".join(lines)


def load_roster_counters(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def today_counts(items_seen_path: str) -> dict:
    """Raw count of items seen today from the dedup store's day counter file."""
    try:
        with open(items_seen_path, encoding="utf-8") as f:
            d = json.load(f)
        day = time.strftime("%Y-%m-%d", time.gmtime())
        return {"items": int((d.get("days") or {}).get(day, 0))}
    except (OSError, ValueError):
        return {"items": 0}
