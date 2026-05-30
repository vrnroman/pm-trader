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

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.copy_trading.copy_paper import CopyPaperEngine, PaperCopyLedger, report
from src.copy_trading.trader_scoring import classify_market

DATA = os.environ.get("DATA_API_URL", "https://data-api.polymarket.com")
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
LEDGER_PATH = os.environ.get("COPY_PAPER_LEDGER", "data/copy_paper_ledger.jsonl")

_S = requests.Session()


def _get(base, path, **params):
    for _ in range(3):
        try:
            r = _S.get(base + path, params=params, timeout=25)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(0.3)
    return None


def make_detector(wallets: list[str], max_age_s: float, min_usd: float):
    """Return a detector() that yields fresh target BUY trades."""

    def detect() -> list[dict]:
        out = []
        cutoff = time.time() - max_age_s
        for w in wallets:
            acts = _get(DATA, "/activity", user=w, limit=30) or []
            for a in acts:
                if a.get("type") != "TRADE" or a.get("side") != "BUY":
                    continue
                ts = float(a.get("timestamp") or 0)
                if ts < cutoff:
                    continue
                price = float(a.get("price") or 0)
                if not (0.05 <= price <= 0.95):
                    continue
                usd = float(a.get("usdcSize") or 0)
                if usd < min_usd:
                    continue
                tx = a.get("transactionHash") or ""
                token = a.get("asset") or ""
                if not tx or not token:
                    continue
                out.append({
                    "copy_id": f"{tx}-{token}",
                    "target": w,
                    "condition_id": a.get("conditionId", ""),
                    "token_id": token,
                    "outcome_index": int(a.get("outcomeIndex") or 0),
                    "category": classify_market(a.get("title", "")),
                    "their_price": price,
                    "their_usd": usd,
                })
        return out

    return detect


def fetch_asks(token_id: str) -> list[tuple[float, float]]:
    b = _get(CLOB, "/book", token_id=token_id)
    if not b:
        return []
    return [(float(a["price"]), float(a["size"])) for a in (b.get("asks") or [])]


def resolve(condition_id: str):
    if not condition_id:
        return None
    j = _get(GAMMA, "/markets", condition_ids=condition_id, closed="true")
    if not j:
        return None
    op = j[0].get("outcomePrices")
    if isinstance(op, str):
        try:
            op = json.loads(op)
        except json.JSONDecodeError:
            return None
    if not op:
        return None
    for i, p in enumerate(op):
        try:
            if float(p) >= 0.99:
                return i
        except (ValueError, TypeError):
            continue
    return None


def load_wallets(args) -> list[str]:
    if args.wallets:
        return [w.strip() for w in args.wallets.split(",") if w.strip()]
    if args.watchlist and os.path.exists(args.watchlist):
        data = json.load(open(args.watchlist))
        return [t["wallet"] for t in data.get("targets", [])]
    return []


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
