"""Every refusal gets a price (run s-k7m2qa, 2026-10-01).

The owner asked whether the deals the bot does not follow are refused
wisely. The data to answer that already existed in three files nobody read
together: the SKIPPED rows of the trade history say what was refused and
why; book B holds what the same copy did at the wallet's own price; the
shadow quote taken at detection says what WE would have paid. Joined, each
refusal reads as a counterfactual: would it have won, and what would it
have netted at their price and at ours.

This module is pure: rows in, a table out. Per refusal class it prints
refusals, how many joined a settled paper copy, how many of those won, and
the net at the wallet's price and at our quote per copy at the live stake.
The table is argued from, never trusted: a class whose net at our quote is
positive is a refusal costing money and the rail behind it is the one to
question; a class that goes negative at our quote is the rail doing its
job. The first table written is kept as ``refusal-baseline.json`` and
never overwritten, so a later change compares against a snapshot, not a
memory (the owner's rule on retained baselines).

Rows this cannot join (no paper copy within two hours, no shadow quote)
are counted and said, never dropped: the join rate is on the line.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Iterable, Optional

from src.config import CONFIG
from src.logger import logger

BASELINE_FILE = "refusal-baseline.json"
JOIN_WINDOW_S = 2 * 3600.0       # a paper copy of the same (wallet, token) this close is the same trade
QUOTE_WINDOW_S = 600.0           # a shadow quote this close to the trade is its quote

# Refusal classes, matched on the SKIPPED row's reason text, first hit wins.
CLASSES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("drift", ("price drift",)),
    ("spread", ("spread too wide",)),
    ("no book", ("could not fetch order book",)),
    ("form", ("out of form", "wallet out of form")),
    ("new-wallet cap", ("new-wallet cap",)),
    ("daily cap", ("copies from", "probation share", "per day")),
    ("floor", ("min_trader_bet", "is under", "under the")),
    ("copies cap", ("max copies",)),
    ("trim", ("trimmed",)),
    ("flipped", ("already", "exited")),
    ("price cap", ("> tier", "tier 1b max", "tier 1a max", "tier 1c max", "fee")),
    ("too old", ("too old",)),
    ("cash", ("cash on chain",)),
    ("governor", ("governor",)),
)


def classify(reason: str) -> str:
    r = (reason or "").lower()
    for name, needles in CLASSES:
        if any(n in r for n in needles):
            return name
    return "other"


def _ts(v) -> float:
    """Epoch seconds from the trade history's timestamp (ISO text or number)."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    try:
        return float(s)
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)   # the history writes UTC
    return dt.timestamp()


def load_refusals(path: str, since_ts: float) -> list[dict]:
    """SKIPPED BUY rows of the trade history since ``since_ts``."""
    out: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(r, dict) or r.get("status") != "SKIPPED":
                    continue
                if str(r.get("side") or "").upper() != "BUY":
                    continue
                ts = _ts(r.get("timestamp"))
                if ts < since_ts:
                    continue
                out.append({"ts": ts, "trader": str(r.get("trader_address") or "").lower(),
                            "token": str(r.get("token_id") or ""), "reason": str(r.get("reason") or ""),
                            "cls": classify(str(r.get("reason") or "")),
                            "price": float(r.get("price") or 0.0), "title": str(r.get("market") or "")})
    except OSError:
        pass
    return out


def join(refusals: list[dict], b_positions: Iterable, shadow_rows: Iterable[dict]) -> list[dict]:
    """Attach each refusal's paper copy (outcome at their price) and shadow
    quote (our price). Rows without one keep ``None`` there; nothing is
    dropped."""
    by_key: dict = {}
    for p in b_positions or []:
        k = ((getattr(p, "target", "") or "").lower(), str(getattr(p, "token_id", "") or ""))
        by_key.setdefault(k, []).append(p)
    quotes: dict = {}
    for q in shadow_rows or []:
        if not isinstance(q, dict) or q.get("boot_flush"):
            continue
        k = (str(q.get("target") or "").lower(), str(q.get("token_id") or ""))
        quotes.setdefault(k, []).append(q)
    out = []
    for r in refusals:
        k = (r["trader"], r["token"])
        pos = None
        for p in by_key.get(k, []):
            if abs(float(getattr(p, "opened_ts", 0.0) or 0.0) - r["ts"]) <= JOIN_WINDOW_S:
                if pos is None or abs(float(p.opened_ts) - r["ts"]) < abs(float(pos.opened_ts) - r["ts"]):
                    pos = p
        quote = None
        for q in quotes.get(k, []):
            dt = abs(float(q.get("their_ts") or 0.0) - r["ts"])
            if dt <= QUOTE_WINDOW_S and (quote is None or dt < abs(float(quote.get("their_ts") or 0.0) - r["ts"])):
                quote = q
        row = dict(r)
        row["copy_id"] = str(getattr(pos, "copy_id", "") or "") if pos is not None else ""
        row["settled"] = bool(pos is not None and getattr(pos, "closed", False)
                              and getattr(pos, "won", None) is not None and not getattr(pos, "refunded", False))
        row["won"] = bool(getattr(pos, "won", False)) if row["settled"] else None
        row["their_price"] = float(getattr(pos, "their_price", 0.0) or 0.0) if pos is not None else (r["price"] or None)
        row["our_price"] = float(quote.get("our_price") or 0.0) if quote and quote.get("our_price") else None
        out.append(row)
    return out


def _roi(won: bool, price: Optional[float]) -> Optional[float]:
    if price is None or price <= 0:
        return None
    return (1.0 / price - 1.0) if won else -1.0


def table(joined: list[dict], *, stake_usd: float) -> list[dict]:
    """Per class: refusals, joined, settled, won, net at their price and at
    our quote (dollars at ``stake_usd`` per copy), quoted (how many had a
    shadow quote). Sorted by refusals, most first.

    One paper copy counts ONCE per class however many refusal rows point at
    it: a trade refused on ten retries, or offered by ten wallets, is one
    outcome, not ten (the verifier, s-k7m2qa round 3: 742 "settled twins"
    were 252 copies, one counted 34 times). ``repeats`` says how many rows
    folded into an earlier one."""
    agg: dict = {}
    seen: dict = {}
    for r in joined:
        a = agg.setdefault(r["cls"], {"cls": r["cls"], "n": 0, "settled": 0, "won": 0, "quoted": 0,
                                       "net_their": 0.0, "net_our": 0.0, "settled_quoted": 0, "repeats": 0})
        a["n"] += 1
        if not r["settled"]:
            continue
        cid = r.get("copy_id") or ""
        key = (r["cls"], cid)
        if cid and key in seen:
            a["repeats"] += 1
            continue
        seen[key] = True
        a["settled"] += 1
        a["won"] += 1 if r["won"] else 0
        rt = _roi(r["won"], r["their_price"])
        if rt is not None:
            a["net_their"] += stake_usd * rt
        if r["our_price"]:
            a["quoted"] += 1
            ro = _roi(r["won"], r["our_price"])
            if ro is not None:
                a["net_our"] += stake_usd * ro
                a["settled_quoted"] += 1
    rows = sorted(agg.values(), key=lambda a: -a["n"])
    for a in rows:
        a["net_their"] = round(a["net_their"], 2)
        a["net_our"] = round(a["net_our"], 2)
    return rows


def per_wallet(joined: list[dict], *, stake_usd: float) -> dict:
    """Per followed wallet: refusals, settled twins, won, net at their price
    (book B's price, their price plus one percent) at ``stake_usd`` a copy."""
    out: dict = {}
    seen: set = set()
    for r in joined:
        w = r.get("trader") or "?"
        a = out.setdefault(w, {"wallet": w, "n": 0, "settled": 0, "won": 0, "net_their": 0.0, "repeats": 0})
        a["n"] += 1
        if not r.get("settled"):
            continue
        cid = r.get("copy_id") or ""
        if cid and (w, cid) in seen:
            a["repeats"] += 1
            continue
        seen.add((w, cid))
        a["settled"] += 1
        a["won"] += 1 if r.get("won") else 0
        rt = _roi(bool(r.get("won")), r.get("their_price"))
        if rt is not None:
            a["net_their"] += stake_usd * rt
    for a in out.values():
        a["net_their"] = round(a["net_their"], 2)
    return out


def distinct_copies(joined: list[dict]) -> int:
    """How many distinct paper copies the settled refusals point at, across
    classes (a copy refused under two classes is one copy here, two rows in
    the table)."""
    return len({r.get("copy_id") for r in joined if r.get("settled") and r.get("copy_id")})


def render(rows: list[dict], *, days: float, stake_usd: float, n_refusals: int,
           n_distinct: Optional[int] = None) -> str:
    if not rows:
        return (f"🧾 <b>Refusals, last {days:.0f}d</b>: none recorded. "
                f"<i>Market-quality refusals are written from 2026-10-01; older ones were retries only.</i>")
    lines = [f"🧾 <b>Refusals, last {days:.0f}d</b>  <i>what each 'no' would have done, "
             f"at ${stake_usd:.2f} a copy; a paper copy counts once per class</i>",
             "<i>class · refused · settled paper twins · won · net at their price · net at OUR quote (n quoted)</i>"]
    for a in rows:
        if a["settled"]:
            our = (f"{a['net_our']:+.0f} ({a['settled_quoted']})" if a["settled_quoted"] else "no quote")
            lines.append(f"  <b>{a['cls']}</b> · {a['n']} · {a['settled']} · {a['won']} · "
                         f"{a['net_their']:+.0f} · {our}")
        else:
            lines.append(f"  <b>{a['cls']}</b> · {a['n']} · 0 settled twins yet")
    joined = sum(a["settled"] for a in rows)
    reps = sum(a.get("repeats", 0) for a in rows)
    copies = f" over {n_distinct} distinct copies" if n_distinct is not None and n_distinct != joined else ""
    lines.append(f"<i>{n_refusals} refusals, {joined} settled class rows{copies}"
                 f"{f' ({reps} repeat refusals of the same copy folded in)' if reps else ''}. A positive net at our quote "
                 f"is a rail costing money; negative is the rail earning its keep. "
                 f"Argue the rails from this table, not from the config comment that set them.</i>")
    return "\n".join(lines)


def line(rows: list[dict], *, days: float) -> str:
    """One line for the daily digest: the three classes with the most money
    behind them at our quote, signed."""
    with_money = [a for a in rows if a["settled_quoted"]]
    if not with_money:
        return ""
    top = sorted(with_money, key=lambda a: -abs(a["net_our"]))[:3]
    bits = [f"{a['cls']} {a['n']} ({a['net_our']:+.0f} at our quote)" for a in top]
    return f"🧾 refusals {days:.0f}d: " + ", ".join(bits)


def write_baseline_once(rows: list[dict], *, days: float, now: float, path: Optional[str] = None) -> bool:
    """The first table is kept, never overwritten. True when written now."""
    path = path or os.path.join(CONFIG.data_dir, BASELINE_FILE)
    if os.path.exists(path):
        return False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ts": now, "day": time.strftime("%Y-%m-%d", time.gmtime(now)), "days": days,
                       "rows": rows}, f, indent=1)
        return True
    except OSError as exc:
        logger.warn(f"[refusals] baseline not written: {exc}")
        return False


def report(*, days: float = 7.0, now: Optional[float] = None, stake_usd: Optional[float] = None) -> dict:
    """The impure edge: read the three files, join, table. Never raises."""
    now = time.time() if now is None else now
    since = now - days * 86400.0
    try:
        from src.copy_trading import live_budget, shadow_quote
        from src.copy_trading.copy_paper import PaperCopyLedger
        if stake_usd is None:
            caps = live_budget.caps(live=True)
            stake_usd = float(getattr(caps, "per_copy_usd", 0.0) or 0.0) if caps is not None else 0.0
        stake_usd = stake_usd or 6.4
        refusals = load_refusals(os.path.join(CONFIG.data_dir, "trade-history.jsonl"), since)
        b = list(PaperCopyLedger(CONFIG.copy_paper_b_ledger).positions.values())
        quotes = shadow_quote.load_rows(since_ts=since - QUOTE_WINDOW_S)
        joined = join(refusals, b, quotes)
        rows = table(joined, stake_usd=stake_usd)
        wrote = write_baseline_once(rows, days=days, now=now)
        return {"rows": rows, "n": len(refusals), "days": days, "stake": stake_usd, "baseline_written": wrote,
                "per_wallet": per_wallet(joined, stake_usd=stake_usd),
                "n_distinct": distinct_copies(joined),
                "text": render(rows, days=days, stake_usd=stake_usd, n_refusals=len(refusals),
                               n_distinct=distinct_copies(joined)),
                "line": line(rows, days=days)}
    except Exception as exc:  # noqa: BLE001
        logger.warn(f"[refusals] report failed: {exc}")
        return {"rows": [], "n": 0, "days": days, "stake": stake_usd or 0.0, "baseline_written": False,
                "text": f"🧾 refusals: not measured ({exc})", "line": ""}
