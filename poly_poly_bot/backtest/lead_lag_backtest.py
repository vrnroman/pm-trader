#!/usr/bin/env python3
"""Lead-lag / informed-money backtest (better trader & insider identification).

Answers two questions the outcome-ROI ranker can't:

1. Which wallets *lead the price* — after they buy, the market moves their way
   within hours? That is an informed-money fingerprint independent of the final
   resolution, and the rigorous replacement for the failed young-account
   "insider shape".

2. How much of that edge survives a realistic *delayed* copy (enter M minutes
   after them, measure the move over the next H)? This ranks wallets by
   *copyable* edge, fixing the 7%-fill / adverse-selection problem.

Data: data-api /activity for each wallet's recent BUYs, CLOB price-history for
the surrounding price path. CLOB retains ~31 days of history, so only trades
within the lookback window are usable (the tool enforces this).

Usage:
    python -m backtest.lead_lag_backtest --watchlist data/copy_watchlist.json \
        --delay-min 15 --horizon-min 240 --output results/lead_lag.json
    python -m backtest.lead_lag_backtest --wallets 0xabc,0xdef --lookback-days 25
"""

from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.copy_trading.lead_lag import WalletLeadLag, analyze_buy
from src.copy_trading.copy_paper_live import load_watchlist_wallets

DATA = os.environ.get("DATA_API_URL", "https://data-api.polymarket.com")
CLOB = "https://clob.polymarket.com"
HISTORY_RETENTION_DAYS = 31  # CLOB price-history rolling window


def _get(session, base, path, **params):
    for _ in range(4):
        try:
            r = session.get(base + path, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(1.0)
        except requests.RequestException:
            pass
        time.sleep(0.25)
    return None


def fetch_recent_buys(wallet: str, since_ts: float, min_usd: float) -> list[dict]:
    """Recent large BUYs for a wallet, newest-first from /activity."""
    s = requests.Session()
    out, offset = [], 0
    while offset < 1500:
        acts = _get(s, DATA, "/activity", user=wallet, limit=500, offset=offset)
        if not acts:
            break
        stop = False
        for a in acts:
            ts = float(a.get("timestamp") or 0)
            if ts < since_ts:
                stop = True
                continue
            if a.get("type") != "TRADE" or a.get("side") != "BUY":
                continue
            price = float(a.get("price") or 0)
            if not (0.05 <= price <= 0.95):
                continue
            usd = float(a.get("usdcSize") or 0) or float(a.get("size") or 0) * price
            if usd < min_usd:
                continue
            token = a.get("asset") or ""
            if token:
                out.append({"token": token, "ts": ts, "price": price, "usd": usd})
        if stop or len(acts) < 500:
            break
        offset += 500
    return out


_price_cache: dict[str, list[tuple[float, float]]] = {}


def fetch_price_series(token: str) -> list[tuple[float, float]]:
    if token in _price_cache:
        return _price_cache[token]
    s = requests.Session()
    j = _get(s, CLOB, "/prices-history", market=token, interval="max", fidelity=10)
    series = []
    for pt in (j or {}).get("history", []) or []:
        t, p = pt.get("t"), pt.get("p")
        if t is not None and p is not None:
            series.append((float(t), float(p)))
    series.sort()
    _price_cache[token] = series
    return series


def analyze_wallet(wallet: str, buys: list[dict], delay_s: float, horizon_s: float) -> WalletLeadLag:
    w = WalletLeadLag()
    tokens = {b["token"] for b in buys}
    series_by_token = {t: fetch_price_series(t) for t in tokens}
    for b in buys:
        series = series_by_token.get(b["token"])
        if not series:
            continue
        r = analyze_buy(series, b["ts"], delay_s=delay_s, horizon_s=horizon_s)
        if r is not None:
            w.add(r, side_sign=1)
    return w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watchlist", default=None)
    ap.add_argument("--wallets", default=None)
    ap.add_argument("--lookback-days", type=float, default=28)
    ap.add_argument("--delay-min", type=float, default=15)
    ap.add_argument("--horizon-min", type=float, default=240)
    ap.add_argument("--min-usd", type=float, default=500)
    ap.add_argument("--min-trades", type=int, default=5)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    if args.lookback_days > HISTORY_RETENTION_DAYS - 1:
        print(f"warning: lookback {args.lookback_days}d exceeds CLOB ~{HISTORY_RETENTION_DAYS}d "
              f"retention; older trades will have no price series", file=sys.stderr)

    if args.wallets:
        wallets = [w.strip() for w in args.wallets.split(",") if w.strip()]
    else:
        wallets = load_watchlist_wallets(args.watchlist or "")
    if not wallets:
        print("no wallets (use --watchlist or --wallets)", file=sys.stderr)
        sys.exit(1)

    since = time.time() - args.lookback_days * 86400
    delay_s = args.delay_min * 60
    horizon_s = args.horizon_min * 60

    print(f"analyzing {len(wallets)} wallets | delay={args.delay_min:.0f}m "
          f"horizon={args.horizon_min:.0f}m lookback={args.lookback_days:.0f}d", file=sys.stderr)

    # fetch buys
    buys_by_wallet: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(fetch_recent_buys, w, since, args.min_usd): w for w in wallets}
        for f in as_completed(futs):
            buys_by_wallet[futs[f]] = f.result() or []

    rows = []
    for w in wallets:
        buys = buys_by_wallet.get(w, [])
        if len(buys) < args.min_trades:
            continue
        agg = analyze_wallet(w, buys, delay_s, horizon_s)
        if agg.n < args.min_trades:
            continue
        rows.append((w, agg))

    rows.sort(key=lambda x: x[1].informed_score, reverse=True)

    print("\n" + "=" * 92)
    print("  Lead-Lag / Informed-Money Backtest  (price move in ¢, + = leads the market)")
    print("=" * 92)
    print(f"  {'wallet':42} {'n':>4} {'lead¢':>6} {'capture¢':>8} "
          f"{'slip¢':>6} {'leadHit':>7} {'capHit':>6}")
    out = []
    for w, a in rows:
        print(f"  {w:42} {a.n:>4} {a.avg_lead*100:>+6.2f} {a.avg_capture*100:>+8.2f} "
              f"{a.avg_slippage*100:>+6.2f} {a.lead_hit_rate:>6.0%} {a.capture_hit_rate:>5.0%}")
        out.append({
            "wallet": w, "n": a.n,
            "lead_cents": round(a.avg_lead * 100, 3),
            "capture_cents": round(a.avg_capture * 100, 3),
            "slippage_cents": round(a.avg_slippage * 100, 3),
            "lead_hit_rate": round(a.lead_hit_rate, 3),
            "capture_hit_rate": round(a.capture_hit_rate, 3),
        })

    if rows:
        leaders = [a.avg_lead for _, a in rows]
        caps = [a.avg_capture for _, a in rows]
        print(f"\n  population: median lead={st.median(leaders)*100:+.2f}¢  "
              f"median capture={st.median(caps)*100:+.2f}¢  "
              f"({sum(c > 0 for c in caps)}/{len(caps)} wallets copy-positive)")
        print("  Interpretation: high positive lead = informed timing; positive *capture*")
        print("  after delay = edge a real copier keeps. Rank/select on capture, not lead.")

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        json.dump({"generated": int(time.time()), "params": vars(args), "wallets": out},
                  open(args.output, "w"), indent=2)
        print(f"\nwrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
