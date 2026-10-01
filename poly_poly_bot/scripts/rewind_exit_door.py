#!/usr/bin/env python3
"""Rewind set Z's exit door over the paper-book history at several windows.

The door (zset_decay) evicts a member after ZSET_DECAY_DAYS consecutive
days below the gate; the run that shipped it picked 7 from the same history
this script replays. This prints the alternatives beside the pick: for
windows 5, 7, 10 and 14 days, who each would have evicted, on which day,
for which check, and what that wallet's book-B copies did in the 14 days
after (at their price, labelled). The three wallets evicted by hand or by
probation ride as rows too. The table is frozen once as a retained
baseline; the number the owner picks afterwards is his.

    COPY_PAPER_LEDGER=... COPY_PAPER_B_LEDGER=... python scripts/rewind_exit_door.py \
        --z data/promoted_wallets_z.json --data-dir data --days 45 \
        --out scripts/baselines/decay-baseline-YYYY-MM-DD.json

Pure over the two ledgers and the Z record; writes only the --out file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.config import CONFIG  # noqa: E402
from src.copy_trading import promotion_gate, zset_candidates as zc, zset_decay as zd  # noqa: E402
from src.copy_trading.copy_paper import PaperCopyLedger  # noqa: E402

WINDOWS = (5, 7, 10, 14)
ERA_DEFAULT = 1784976482.215206   # the clean era's floor (ab_race_state.json on the box)


def daily_fails(wallets: dict, b, a, *, era, now: float, days: int) -> dict:
    """wallet -> list (oldest first) of decay_fails() per day, None when no rows."""
    series = {w: [] for w in wallets}
    for d in range(days, -1, -1):
        t = now - d * 86400.0
        bb = zd._book_as_of(b, t)
        aa = zd._book_as_of(a, t)
        corr = promotion_gate.split_half_corr(bb, min_opened_ts=era)
        for w in wallets:
            c = zc.evaluate(w, bb, aa, era=era, now=t, book_corr=corr)
            series[w].append(None if c is None else zd.decay_fails(c.checks))
    return series


def replay(series: dict, admitted: dict, *, now: float, days: int, window: int, b) -> list[dict]:
    rows = []
    for w, adm in sorted(admitted.items(), key=lambda x: x[1]):
        cnt, evict_t, first = 0, None, None
        for i, f in enumerate(series[w]):
            t = now - (days - i) * 86400.0
            if t < adm or f is None:
                continue
            if f:
                cnt += 1
                first = first or f[0][0]
                if cnt >= window:
                    evict_t = t
                    break
            else:
                cnt, first = 0, None
        row = {"wallet": w, "evicted_on": None, "check": None, "after_n": 0, "after_roi_their": None,
               "trailing_below": 0}
        if evict_t:
            after = [p for p in b if (p.target or "").lower() == w and p.closed and p.won is not None
                     and not getattr(p, "refunded", False) and evict_t <= p.opened_ts < evict_t + 14 * 86400]
            row.update(evicted_on=time.strftime("%Y-%m-%d", time.gmtime(evict_t)), check=first,
                       after_n=len(after),
                       after_roi_their=(round(sum(((1 / p.their_price - 1) if p.won else -1) for p in after)
                                              / len(after), 4) if after else None))
        else:
            tr = 0
            for f in reversed(series[w]):
                if f:
                    tr += 1
                else:
                    break
            row["trailing_below"] = tr
        rows.append(row)
    return rows


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--z", required=True, help="promoted_wallets_z.json")
    ap.add_argument("--extra", default="", help="comma list of wallet:admitted_ts to ride as rows (the evicted)")
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--era", type=float, default=ERA_DEFAULT)
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-dir", default="", help="the box's data dir (form table, shadow quotes); "
                    "the scalper and execution rails read it. Default: CONFIG.data_dir")
    args = ap.parse_args(argv)
    if args.data_dir:
        CONFIG.data_dir = args.data_dir
    now = time.time()
    z = json.load(open(args.z, encoding="utf-8"))
    admitted = {v["wallet"].lower(): float(v["ts"]) for v in z.values()}
    for item in filter(None, args.extra.split(",")):
        w, ts = item.split(":")
        admitted[w.lower()] = float(ts)
    b = list(PaperCopyLedger(CONFIG.copy_paper_b_ledger).positions.values())
    a = list(PaperCopyLedger(CONFIG.copy_paper_ledger).positions.values())
    series = daily_fails(admitted, b, a, era=args.era, now=now, days=args.days)
    out = {"ts": now, "day": time.strftime("%Y-%m-%d", time.gmtime(now)), "days": args.days,
           "note": ("the scalper check reads the live form table, so in a replay it is constant over the "
                    "history: a member the form calls a scalper today reads as below the door on every day"),
           "windows": {}}
    for wdw in WINDOWS:
        rows = replay(series, admitted, now=now, days=args.days, window=wdw, b=b)
        out["windows"][str(wdw)] = {"evictions": sum(1 for r in rows if r["evicted_on"]), "rows": rows}
        print(f"window {wdw:2}d: {out['windows'][str(wdw)]['evictions']} eviction(s): "
              + ", ".join(f"{r['wallet'][:10]} on {r['evicted_on']} ({(r['check'] or '')[:28]}; next 14d n={r['after_n']}"
                          f"{'' if r['after_roi_their'] is None else f' {100 * r['after_roi_their']:+.0f}%'})"
                          for r in rows if r["evicted_on"]))
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"written {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
