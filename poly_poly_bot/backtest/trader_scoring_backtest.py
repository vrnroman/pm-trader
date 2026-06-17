#!/usr/bin/env python3
"""Backtest + watchlist builder for copy-trading selection (Strategy 1b).

This is a genuine out-of-sample test (no lookahead): it ranks wallets by
realized closed-position ROI over a *lookback* window
using only information available at the cutoff, then measures how those wallets
actually performed in the *forward* window.

It does two things:
  1. validate  — for one or more cutoff dates, report rank persistence
     (Spearman P1->P2 ROI) and the out-of-sample ROI of a top-K copy portfolio.
  2. watchlist — score every universe wallet over the trailing window ending
     now and emit the current copy targets (the wallets the live forward
     paper-harness should track).

The selection logic lives in src/copy_trading/trader_scoring.py and is unit
tested; this file is the network/CLI shell around it.

Usage:
    python -m backtest.trader_scoring_backtest validate --cutoffs 2026-02-01,2026-03-01,2026-04-01
    python -m backtest.trader_scoring_backtest watchlist --category sports --top-k 25 --output results/copy_watchlist.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import statistics as st
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.copy_trading.trader_scoring import (
    compute_wallet_metrics,
    score_wallet,
    select_copy_targets,
    select_targets,
)

DATA_API = os.environ.get("DATA_API_URL", "https://data-api.polymarket.com")


def _get(session: requests.Session, path: str, **params):
    for _ in range(4):
        try:
            r = session.get(DATA_API + path, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(1.0)
        except requests.RequestException:
            pass
        time.sleep(0.25)
    return None


def build_universe(target: int, min_amounts=(3000, 1200, 500)) -> list[str]:
    """Collect active, large-stake wallets from the recent taker trade feed."""
    s = requests.Session()
    seen: set[str] = set()
    for amt in min_amounts:
        off = 0
        while off < 6000 and len(seen) < target:
            tr = _get(s, "/trades", limit=500, offset=off,
                      filterType="CASH", filterAmount=amt, takerOnly="true")
            if not tr:
                break
            for t in tr:
                w = t.get("proxyWallet")
                if w:
                    seen.add(w)
            off += 500
    return list(seen)[:target]


def fetch_activity(wallet: str, cache_dir: str | None, cap: int = 4000) -> list[dict]:
    if cache_dir:
        p = os.path.join(cache_dir, f"{wallet}.json")
        if os.path.exists(p):
            try:
                return json.load(open(p))
            except (json.JSONDecodeError, OSError):
                pass
    s = requests.Session()
    acts: list[dict] = []
    off = 0
    while off < cap:
        a = _get(s, "/activity", user=wallet, limit=500, offset=off)
        if not a:
            break
        acts += a
        off += 500
        if len(a) < 500:
            break
    if cache_dir:
        try:
            json.dump(acts, open(os.path.join(cache_dir, f"{wallet}.json"), "w"))
        except OSError:
            pass
    return acts


def fetch_all(wallets: list[str], cache_dir: str | None, workers: int = 12) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_activity, w, cache_dir): w for w in wallets}
        done = 0
        for f in as_completed(futs):
            w = futs[f]
            try:
                out[w] = f.result()
            except Exception:
                out[w] = []
            done += 1
            if done % 100 == 0:
                print(f"  fetched {done}/{len(wallets)}", file=sys.stderr)
    return out


def _spearman(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0

    def ranks(v):
        order = sorted(range(n), key=lambda k: v[k])
        r = [0] * n
        for i, k in enumerate(order):
            r[k] = i
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


def _epoch(date_str: str) -> float:
    return dt.datetime.strptime(date_str, "%Y-%m-%d").replace(
        tzinfo=dt.timezone.utc).timestamp()


def cmd_validate(args, activity: dict[str, list[dict]]):
    print("=" * 68)
    print("  Copy-Trading Selection — Out-of-Sample Validation")
    print("=" * 68)
    for cat in args.categories:
        print(f"\n  category = {cat}")
        for cs in args.cutoffs:
            cutoff = _epoch(cs)
            rows = []  # (p1_roi, p2_roi, p2_pnl, p2_capital)
            for acts in activity.values():
                p1 = score_wallet(acts, end_ts=cutoff, category=cat)
                p2 = score_wallet(acts, start_ts=cutoff, category=cat)
                if p1.capital < args.min_capital or p1.n_closed < args.min_closed:
                    continue
                if p2.capital < 800 or p2.n_closed < 3:
                    continue
                rows.append((p1.roi, p2.roi, p2.pnl, p2.capital))
            if len(rows) < 20:
                print(f"    {cs}: n={len(rows)} (too few)")
                continue
            r1 = [x[0] for x in rows]
            r2 = [x[1] for x in rows]
            ranked = sorted(rows, key=lambda x: -x[0])
            k = min(args.top_k, len(ranked) // 3)
            top = ranked[:k]
            agg = sum(x[2] for x in top) / sum(x[3] for x in top)
            med = st.median(x[1] for x in top)
            prof = st.mean(x[2] > 0 for x in top)
            print(f"    {cs}: n={len(rows):3d}  Spearman={_spearman(r1, r2):+.2f}  "
                  f"TOP{k} fwd aggROI={agg:+.1%} medROI={med:+.1%} profitable={prof:.0%}  "
                  f"| population medROI={st.median(r2):+.1%}")


def cmd_watchlist(args, activity: dict[str, list[dict]]):
    lookback = time.time() - args.lookback_days * 86400
    scored = {
        w: compute_wallet_metrics(a, start_ts=lookback, category=args.category)
        for w, a in activity.items()
    }
    picks = select_targets(
        scored, method=args.method, min_capital=args.min_capital,
        min_closed=args.min_closed, top_k=args.top_k,
    )
    print(f"\nCopy watchlist — category={args.category} lookback={args.lookback_days}d "
          f"method={args.method}")
    print(f"{'rank':>4} {'wallet':42} {'ROI':>8} {'tstat':>6} {'conc':>5} "
          f"{'PnL':>10} {'closed':>6} {'hit%':>6}")
    out = []
    for i, rw in enumerate(picks, 1):
        s = rw.metrics
        print(f"{i:>4} {rw.address:42} {s.roi:>+7.1%} {s.tstat:>6.1f} "
              f"{s.concentration:>5.0%} {s.pnl:>+10,.0f} {s.n_closed:>6} {s.hit_rate:>5.0%}")
        out.append({
            "rank": i, "wallet": rw.address, "roi": round(s.roi, 4),
            "tstat": round(s.tstat, 3), "concentration": round(s.concentration, 3),
            "pnl": round(s.pnl, 2), "n_closed": s.n_closed,
            "hit_rate": round(s.hit_rate, 4), "capital": round(s.capital, 2),
        })
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        json.dump({"category": args.category, "lookback_days": args.lookback_days,
                   "method": args.method, "generated": int(time.time()),
                   "targets": out}, open(args.output, "w"), indent=2)
        print(f"\nwrote {args.output}")


def main():
    ap = argparse.ArgumentParser(description="Copy-trading selection backtest/watchlist")
    ap.add_argument("mode", choices=["validate", "watchlist"])
    ap.add_argument("--universe", type=int, default=850)
    ap.add_argument("--cache-dir", default=None, help="dir to cache wallet activity")
    ap.add_argument("--category", default="ALL",
                    choices=["ALL", "sports", "crypto", "research", "other"])
    ap.add_argument("--categories", default="ALL,sports,research",
                    help="(validate) comma list of categories")
    ap.add_argument("--cutoffs", default="2026-02-01,2026-03-01,2026-04-01")
    ap.add_argument("--lookback-days", type=int, default=120)
    ap.add_argument("--min-capital", type=float, default=5000.0)
    ap.add_argument("--min-closed", type=int, default=10)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--method", default="robust",
                    choices=["robust", "tstat", "roi", "median_roi"],
                    help="(watchlist) selection metric; robust = recency + "
                         "concentration filter ranked by t-stat (validated best)")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()
    args.cutoffs = [c.strip() for c in args.cutoffs.split(",") if c.strip()]
    args.categories = [c.strip() for c in args.categories.split(",") if c.strip()]

    if args.cache_dir:
        os.makedirs(args.cache_dir, exist_ok=True)
    print("building universe...", file=sys.stderr)
    universe = build_universe(args.universe)
    print(f"universe: {len(universe)} wallets", file=sys.stderr)
    activity = fetch_all(universe, args.cache_dir)
    activity = {w: a for w, a in activity.items() if a and len(a) < 4000}
    print(f"scored wallets: {len(activity)}", file=sys.stderr)

    if args.mode == "validate":
        cmd_validate(args, activity)
    else:
        cmd_watchlist(args, activity)


if __name__ == "__main__":
    main()
