#!/usr/bin/env python3
"""Live driver for the forward paper-copy harness (Strategy 1b).

Wires real Polymarket data into `CopyPaperEngine`:
  - detection : data-api /activity for each watchlist wallet (new BUY trades)
  - books     : CLOB /book (live asks, so copies pay realistic prices)
  - resolution: gamma /markets?condition_ids=...&closed=true -> winning index

Places NO real orders. Accumulates a paper ledger whose realized PnL — net of
execution drag — is the gate for graduating a wallet to real capital.

Usage:
    # one cycle against a watchlist file (from trader_scoring_backtest watchlist)
    python -m scripts.copy_paper_run --watchlist results/copy_watchlist.json --once
    # explicit wallets, loop every 60s
    python -m scripts.copy_paper_run --wallets 0xabc,0xdef --loop 60
    # show the running report
    python -m scripts.copy_paper_run --report
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.copy_trading.copy_paper import CopyPaperEngine, PaperCopyLedger, report
from src.copy_trading.copy_paper_live import (
    fetch_asks,
    load_watchlist_wallets,
    make_detector,
    resolve,
)

LEDGER_PATH = os.environ.get("COPY_PAPER_LEDGER", "data/copy_paper_ledger.jsonl")


def load_wallets(args) -> list[str]:
    if args.wallets:
        return [w.strip() for w in args.wallets.split(",") if w.strip()]
    return load_watchlist_wallets(args.watchlist)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watchlist", default=None)
    ap.add_argument("--wallets", default=None)
    ap.add_argument("--ledger", default=LEDGER_PATH)
    ap.add_argument("--max-copy-usd", type=float, default=50.0)
    ap.add_argument("--copy-pct", type=float, default=1.0)
    ap.add_argument("--max-slippage-bps", type=int, default=200)
    ap.add_argument("--max-age-s", type=float, default=21600)  # 6h freshness
    ap.add_argument("--min-usd", type=float, default=500.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", type=int, default=0)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    ledger = PaperCopyLedger(args.ledger)
    if args.report:
        print(json.dumps(report(ledger), indent=2))
        return

    wallets = load_wallets(args)
    if not wallets:
        print("no wallets (use --watchlist or --wallets)", file=sys.stderr)
        sys.exit(1)
    print(f"paper-copying {len(wallets)} wallets -> {args.ledger}", file=sys.stderr)

    engine = CopyPaperEngine(
        ledger, detector=make_detector(wallets, args.max_age_s, args.min_usd),
        book_fetcher=fetch_asks, resolver=resolve,
        copy_pct=args.copy_pct, max_copy_usd=args.max_copy_usd,
        max_slippage_bps=args.max_slippage_bps,
    )

    def cycle():
        s = engine.run_cycle()
        print(f"[{time.strftime('%H:%M:%S')}] detected={s.detected} opened={s.opened} "
              f"unfilled={s.skipped_unfilled} resolved={s.resolved} | "
              f"open={len(ledger.open_positions())} closed={len(ledger.closed_positions())}",
              file=sys.stderr)

    cycle()
    if args.loop:
        while True:
            time.sleep(args.loop)
            cycle()
    print(json.dumps(report(ledger), indent=2))


if __name__ == "__main__":
    main()
