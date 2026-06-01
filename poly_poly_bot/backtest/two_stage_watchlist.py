#!/usr/bin/env python3
"""Two-stage copy watchlist: skill ∩ copyability.

The validated pipeline in one command:

  Stage 1 (skill)        robust scorer over cached activity -> top-N skilled
                         wallets (recency + concentration filter, ranked by the
                         t-stat of per-market PnL). Finds wallets with a
                         *repeatable* edge.

  Stage 2 (copyability)  lead-lag on each survivor's recent BUYs -> keep only
                         wallets whose price edge SURVIVES a realistic copy
                         delay (delayed-capture >= threshold). Drops the
                         "skilled but un-copyable" wallets whose ROI comes from
                         holding to resolution rather than copyable timing.

Output is ranked by delayed-capture (the edge a real copier keeps), annotated
with the stage-1 skill metrics. Feed it straight to scripts/copy_paper_run.py.

Usage:
    python -m backtest.two_stage_watchlist --cache-dir data/wcache \
        --category ALL --skill-pool 40 --top-k 15 \
        --min-capture-cents 0.5 --output data/copy_watchlist.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.copy_trading.trader_scoring import compute_wallet_metrics, select_targets

# reuse the live fetchers from the single-stage tools — no duplication
from backtest.trader_scoring_backtest import build_universe, fetch_all
from backtest.lead_lag_backtest import (
    HISTORY_RETENTION_DAYS,
    analyze_wallet,
    fetch_recent_buys,
)


def stage1_skill(activity, category, lookback_days, method, min_capital,
                 min_closed, pool):
    """Robust skill ranking -> top-`pool` candidate wallets with metrics."""
    lookback = time.time() - lookback_days * 86400
    scored = {
        w: compute_wallet_metrics(a, start_ts=lookback, category=category)
        for w, a in activity.items()
    }
    return select_targets(
        scored, method=method, min_capital=min_capital,
        min_closed=min_closed, top_k=pool,
    )


def stage2_copyability(candidates, lookback_days, delay_s, horizon_s,
                       min_usd, min_ll_trades):
    """Lead-lag capture for each candidate; returns dict wallet -> WalletLeadLag."""
    since = time.time() - lookback_days * 86400
    out = {}
    for rw in candidates:
        buys = fetch_recent_buys(rw.address, since, min_usd)
        if len(buys) < min_ll_trades:
            out[rw.address] = None
            continue
        out[rw.address] = analyze_wallet(rw.address, buys[:60], delay_s, horizon_s)
    return out


def combine_and_rank(candidates, ll, min_capture_cents, keep_unscored, top_k):
    """Pure: merge stage-1 candidates with stage-2 lead-lag, filter, rank.

    Returns (rows, stats) where rows is a list of (candidate, WalletLeadLag|None)
    ranked best-first and capped at ``top_k``; stats reports drop counts.
    """
    rows = []
    dropped_uncopyable = dropped_unscored = 0
    for rw in candidates:
        agg = ll.get(rw.address)
        if agg is None:
            if keep_unscored:
                rows.append((rw, None))
            else:
                dropped_unscored += 1
            continue
        if agg.avg_capture * 100 < min_capture_cents:
            dropped_uncopyable += 1
            continue
        rows.append((rw, agg))
    # scored wallets first, ranked by capture; unscored (if kept) after, by t-stat
    rows.sort(key=lambda r: (r[1] is not None,
                             r[1].avg_capture if r[1] else 0.0,
                             r[0].metrics.tstat), reverse=True)
    stats = {"pool": len(candidates), "dropped_uncopyable": dropped_uncopyable,
             "dropped_unscored": dropped_unscored, "final": min(len(rows), top_k)}
    return rows[:top_k], stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default=None, help="dir of cached wallet activity")
    ap.add_argument("--universe", type=int, default=850,
                    help="wallets to fetch if cache is empty")
    ap.add_argument("--category", default="ALL")
    ap.add_argument("--lookback-days", type=float, default=120,
                    help="skill-scoring lookback (stage 1)")
    ap.add_argument("--ll-lookback-days", type=float, default=28,
                    help="lead-lag lookback (stage 2); capped at CLOB retention")
    ap.add_argument("--method", default="robust",
                    choices=["robust", "tstat", "roi", "median_roi"])
    ap.add_argument("--min-capital", type=float, default=5000.0)
    ap.add_argument("--min-closed", type=int, default=10)
    ap.add_argument("--skill-pool", type=int, default=40,
                    help="how many skilled wallets to pass into stage 2")
    ap.add_argument("--top-k", type=int, default=15, help="final watchlist size")
    ap.add_argument("--delay-min", type=float, default=15)
    ap.add_argument("--horizon-min", type=float, default=240)
    ap.add_argument("--min-usd", type=float, default=500)
    ap.add_argument("--min-ll-trades", type=int, default=4,
                    help="min recent BUYs with price data to score copyability")
    ap.add_argument("--min-capture-cents", type=float, default=0.0,
                    help="keep wallets with delayed-capture >= this (¢/trade)")
    ap.add_argument("--keep-unscored", action="store_true",
                    help="keep skilled wallets that lack enough recent trades to "
                         "score copyability (default: drop them)")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    if args.ll_lookback_days > HISTORY_RETENTION_DAYS - 1:
        args.ll_lookback_days = HISTORY_RETENTION_DAYS - 1
        print(f"note: capping lead-lag lookback at {args.ll_lookback_days:.0f}d "
              f"(CLOB price-history retention)", file=sys.stderr)

    # --- load activity (cache-first) ---
    wallets = []
    if args.cache_dir and os.path.isdir(args.cache_dir):
        wallets = [f[:-5] for f in os.listdir(args.cache_dir) if f.endswith(".json")]
    if not wallets:
        print(f"building universe of {args.universe} wallets…", file=sys.stderr)
        wallets = build_universe(args.universe)
    print(f"loading activity for {len(wallets)} wallets…", file=sys.stderr)
    activity = fetch_all(wallets, args.cache_dir)

    # --- stage 1: skill ---
    candidates = stage1_skill(
        activity, args.category, args.lookback_days, args.method,
        args.min_capital, args.min_closed, args.skill_pool,
    )
    print(f"stage 1 (skill, {args.method}): {len(candidates)} candidates",
          file=sys.stderr)

    # --- stage 2: copyability ---
    delay_s, horizon_s = args.delay_min * 60, args.horizon_min * 60
    ll = stage2_copyability(
        candidates, args.ll_lookback_days, delay_s, horizon_s,
        args.min_usd, args.min_ll_trades,
    )

    # --- combine + filter (pure) ---
    rows, stats = combine_and_rank(
        candidates, ll, args.min_capture_cents, args.keep_unscored, args.top_k,
    )

    print(f"\nTwo-stage watchlist — category={args.category} method={args.method}")
    print(f"  stage1 pool={stats['pool']}  dropped: un-copyable="
          f"{stats['dropped_uncopyable']} unscored={stats['dropped_unscored']}"
          f"  ->  final={len(rows)}")
    print(f"  {'rank':>4} {'wallet':42} {'ROI':>7} {'tstat':>6} "
          f"{'capture¢':>8} {'lead¢':>6} {'capHit':>6} {'n':>4}")
    out = []
    for i, (rw, agg) in enumerate(rows, 1):
        s = rw.metrics
        if agg is not None:
            cap_c, lead_c, hit, n = (agg.avg_capture * 100, agg.avg_lead * 100,
                                     agg.capture_hit_rate, agg.n)
            print(f"  {i:>4} {rw.address:42} {s.roi:>+6.0%} {s.tstat:>6.1f} "
                  f"{cap_c:>+8.2f} {lead_c:>+6.2f} {hit:>5.0%} {n:>4}")
        else:
            cap_c = lead_c = hit = None
            n = 0
            print(f"  {i:>4} {rw.address:42} {s.roi:>+6.0%} {s.tstat:>6.1f} "
                  f"{'   n/a':>8} {'  n/a':>6} {'  n/a':>6} {n:>4}")
        rec = {
            "rank": i, "wallet": rw.address,
            "roi": round(s.roi, 4), "tstat": round(s.tstat, 3),
            "concentration": round(s.concentration, 3),
            "pnl": round(s.pnl, 2), "n_closed": s.n_closed,
            "hit_rate": round(s.hit_rate, 4), "capital": round(s.capital, 2),
        }
        if agg is not None:
            rec.update(capture_cents=round(cap_c, 3), lead_cents=round(lead_c, 3),
                       capture_hit_rate=round(hit, 3), ll_trades=n)
        out.append(rec)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        json.dump({
            "category": args.category, "method": args.method,
            "lookback_days": args.lookback_days,
            "ll_lookback_days": args.ll_lookback_days,
            "delay_min": args.delay_min, "horizon_min": args.horizon_min,
            "min_capture_cents": args.min_capture_cents,
            "generated": int(time.time()), "targets": out,
        }, open(args.output, "w"), indent=2)
        print(f"\nwrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
