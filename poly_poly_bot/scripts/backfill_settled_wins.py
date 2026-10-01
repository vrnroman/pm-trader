#!/usr/bin/env python3
"""Backfill the wins Polymarket paid before the ledger could see them.

Until 2026-10-01 (PR #53) the ops ledger booked only losses: a winner left
the wallet when Polymarket paid it and the booker dropped the row. This
script reads the proxy wallet's own activity, finds every WON market since
live trading started whose token the ledger never booked, and appends it as
a ``settled`` receipt marked ``backfill``, dated at the payout. Wins only:
a backfill can move a probation verdict away from a wrong eviction, never
admit anyone. The loss streak and the day's pnl are not touched.

Reversible: every row carries ``"backfill": true``.

    python scripts/backfill_settled_wins.py            # dry run: prints the rows
    python scripts/backfill_settled_wins.py --apply    # writes them

Run inside the bot's container (it reads CONFIG and the data dir).
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.config import CONFIG  # noqa: E402
from src.copy_trading import ops_watch, real_money  # noqa: E402


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    path = os.path.join(CONFIG.data_dir, "trade-history.jsonl")
    th = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                th.append(json.loads(line))
            except ValueError:
                continue
    orders = real_money.collapse_orders(th)
    live_ts = real_money.live_start_ts(orders) or 0
    activity = real_money.fetch_activity(CONFIG.proxy_wallet, since_ts=int(live_ts) - 3600)
    positions = real_money.fetch_chain_positions(CONFIG.proxy_wallet)
    if activity is None or positions is None:
        print("activity or positions unreadable; nothing done", file=sys.stderr)
        return 2
    book = real_money.build_book(activity, positions, orders, since_ts=0)
    deals, _other = real_money.parse_deals(activity, since_ts=live_ts)
    real_money.attribute_wallets(deals, orders)
    already = set(ops_watch._read_json(ops_watch._p(ops_watch.STATE_FILE)).get("settled_tokens") or [])
    rows = ops_watch.backfill_rows(deals, book.markets, already=already)
    total = round(sum(r["payout"] - r["cost"] for r in rows), 2)
    print(f"{len(rows)} won market(s) to backfill, net {total:+.2f}; already booked: {len(already)}")
    for r in rows:
        print(f"  {time.strftime('%Y-%m-%d %H:%M', time.gmtime(r['ts']))}  {r['wallet'][:10]:10}  "
              f"${r['cost']:.2f} -> ${r['payout']:.2f}  {r['title'][:50]}")
    if not apply:
        print("dry run; pass --apply to write")
        return 0
    n = ops_watch.apply_backfill(rows)
    print(f"written: {n} settled row(s) marked backfill")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
