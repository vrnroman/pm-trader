#!/usr/bin/env python3
"""Reset all copy P&L + risk/spend state to zero (archive then clear).

Clears BOTH copy systems' ledgers/state — System A (realized-pnl, inventory,
risk-state, tiered-risk-state, daily-spend, trader-counts, trade-history) and
System B (copy_paper_ledger) — after archiving each to ``data/archive/``. Open
positions are dropped. Discovery watchlist/state, dedup caches, and the market
resolution cache are left untouched.

Run this with the bot STOPPED so the running process can't re-persist its
in-memory ledger over the cleared files:

    # on the VM, over IAP SSH:
    docker stop poly-poly-bot
    python -m scripts.reset_pnl --confirm
    docker start poly-poly-bot

Usage:
    python -m scripts.reset_pnl --confirm           # archive + clear
    python -m scripts.reset_pnl --confirm --no-archive
    python -m scripts.reset_pnl                      # dry-run (prints targets, no changes)
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import CONFIG  # noqa: E402
from src.copy_trading.reset_pnl import _target_paths, reset_pnl  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Reset copy P&L + risk/spend state to zero.")
    ap.add_argument("--confirm", action="store_true",
                    help="actually perform the reset (without it, this is a dry run)")
    ap.add_argument("--no-archive", action="store_true",
                    help="skip the timestamped backup (still clears)")
    args = ap.parse_args()

    targets = _target_paths(CONFIG.data_dir, CONFIG.copy_paper_ledger)

    if not args.confirm:
        print("DRY RUN — would archive + clear these files (pass --confirm to do it):")
        for p in targets:
            mark = "exists" if os.path.exists(p) else "absent"
            print(f"  [{mark}] {p}")
        print(f"\nArchive dir: {os.path.join(CONFIG.data_dir, 'archive')}")
        return 0

    res = reset_pnl(
        CONFIG.data_dir,
        confirm=True,
        archive=not args.no_archive,
        copy_paper_ledger=CONFIG.copy_paper_ledger,
    )
    print(f"Reset complete: {res.summary()}")
    if res.archived:
        print("Archived:")
        for p in res.archived:
            print(f"  {p}")
    print("Cleared:")
    for p in res.cleared:
        print(f"  {p}")
    if res.skipped:
        print(f"Skipped (absent): {len(res.skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
