#!/usr/bin/env python3
"""Out-of-sample calibration backtest for the strategy theories (1a..1j).

For a cutoff date, each wallet's activity is split into a *lookback* (≤ cutoff,
used to build the WalletContext and run the detectors) and a *forward* (> cutoff,
used to measure what copying it would actually have earned). The forward
copy-PnL **follows the target's exits**: a copied BUY is closed when the wallet
later SELLs that outcome (exit at their sell price), and only falls back to the
resolution payoff if they held to settlement — so a swing trader who takes
profit early is scored on the round trip, not on holding to resolution.

For each theory we report, at its default params and a couple of stricter
variants, how many wallets it flags and the forward copy-ROI of their
subsequent bets vs the population baseline. That's the signal for calibrating
each theory's thresholds to a sane flag rate with positive edge.

Usage:
    python -m backtest.theory_backtest calibrate --universe 400 --forward-days 30 \
        --cache-dir data/wcache --res-cache data/rescache
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

from src.copy_trading.copy_replay import forward_copy_rois
from src.copy_trading.market_resolution import fetch_resolutions
from src.copy_trading.theories import REGISTRY, evaluate_all
from src.copy_trading.wallet_context import build_context

DATA_API = os.environ.get("DATA_API_URL", "https://data-api.polymarket.com")


def _get(session, path, **params):
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


def build_universe(target, min_amounts=(3000, 1200, 500, 250, 100)):
    s = requests.Session()
    seen: set[str] = set()
    for amt in min_amounts:
        off = 0
        while off <= 3000 and len(seen) < target:
            tr = _get(s, "/trades", limit=500, offset=off,
                      filterType="CASH", filterAmount=amt, takerOnly="true")
            if not tr:
                break
            for t in tr:
                if t.get("proxyWallet"):
                    seen.add(t["proxyWallet"])
            off += 500
            if len(tr) < 500:
                break
    return list(seen)[:target]


def fetch_activity(wallet, cache_dir, cap=4000):
    if cache_dir:
        p = os.path.join(cache_dir, f"{wallet}.json")
        if os.path.exists(p):
            try:
                return json.load(open(p))
            except (json.JSONDecodeError, OSError):
                pass
    s = requests.Session()
    acts, off = [], 0
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


def fetch_all(wallets, cache_dir, workers=10):
    out = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_activity, w, cache_dir): w for w in wallets}
        done = 0
        for f in as_completed(futs):
            try:
                out[futs[f]] = f.result() or []
            except Exception:
                out[futs[f]] = []
            done += 1
            if done % 100 == 0:
                print(f"  fetched {done}/{len(wallets)}", file=sys.stderr)
    return out


# --------------------------------------------------------------------------- #
# Forward copy-PnL with exit-following
# --------------------------------------------------------------------------- #
def _forward_copy_rois(forward_acts, resolutions, min_usd=100.0, slippage_bps=0.0):
    """Copy each forward BUY and close it the way the target did.

    Thin wrapper over ``copy_replay.forward_copy_rois`` (the shared definition of
    "what a copy earns", also used by the live discovery sweep). Exit-following
    is on here so a swing trader is scored on the round trip, not on holding to
    resolution.
    """
    return forward_copy_rois(forward_acts, resolutions, min_usd=min_usd,
                             slippage_bps=slippage_bps, follow_exits=True)


def _split(acts, cutoff):
    lb, fw = [], []
    for ev in acts:
        (lb if float(ev.get("timestamp") or 0.0) <= cutoff else fw).append(ev)
    return lb, fw


def calibrate(args):
    cache_dir = args.cache_dir
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
    res_cache = args.res_cache
    if res_cache:
        os.makedirs(res_cache, exist_ok=True)

    if args.wallets_from and os.path.isdir(args.wallets_from):
        universe = [f[:-5] for f in os.listdir(args.wallets_from) if f.endswith(".json")][:args.universe]
        print(f"universe: {len(universe)} wallets from cache {args.wallets_from}", file=sys.stderr)
    else:
        universe = build_universe(args.universe)
        print(f"universe: {len(universe)} wallets from trade feed", file=sys.stderr)

    activity = fetch_all(universe, cache_dir)
    now = time.time()
    cutoff = now - args.forward_days * 86400

    # resolutions for every market touched (cached; resolved markets immutable)
    cids = {ev.get("conditionId") for a in activity.values() for ev in a if ev.get("conditionId")}
    print(f"fetching resolutions for {len(cids)} markets...", file=sys.stderr)
    resolutions = fetch_resolutions(cids, res_cache)
    print(f"  {len(resolutions)} resolved", file=sys.stderr)

    # build lookback contexts + forward copy-ROIs once per wallet
    ctxs, fwd_rois = {}, {}
    for w, acts in activity.items():
        lb, fw = _split(acts, cutoff)
        if not lb:
            continue
        ctxs[w] = build_context(w, lb, now=cutoff, resolutions=resolutions,
                                lookback_ts=0.0)
        fwd_rois[w] = _forward_copy_rois(fw, resolutions, args.min_usd, args.slippage_bps)

    # diagnostics: why some theories can't fire in this (recent, mostly-open) sample
    n_skill = sum(1 for c in ctxs.values() if c.metrics.n_closed >= 10)
    n_curve = sum(1 for c in ctxs.values() if c.curve.n > 0)
    n_capture = sum(1 for c in ctxs.values() if c.n_capture > 0)
    n_ls = sum(1 for c in ctxs.values()
               if sum(1 for b in c.buys if b.won is not None and 0.05 <= b.price <= 0.40) >= 8)
    n_trips = sum(1 for c in ctxs.values() if len(c.round_trips) >= 8)
    print(f"diagnostics: {len(ctxs)} ctxs | >=10 closed: {n_skill} | curve pts: {n_curve} "
          f"| capture: {n_capture} | >=8 resolved-longshot buys: {n_ls} | >=8 round-trips: {n_trips}",
          file=sys.stderr)

    scored = [w for w in ctxs if fwd_rois.get(w)]  # wallets with forward copy activity
    pop_rois = [r for w in scored for r in fwd_rois[w]]
    pop_mean = st.mean(pop_rois) if pop_rois else 0.0
    days = max(1.0, args.forward_days)
    print(f"\nscored {len(scored)} wallets with forward bets; "
          f"population copy-ROI/$ = {pop_mean:+.3f} (n={len(pop_rois)})\n")

    # param variants per theory: default + two stricter
    variants = _variant_grid()
    print(f"{'theory':22s} {'variant':10s} {'flagged':>7s} {'/day':>5s} "
          f"{'copyROI':>8s} {'hit%':>5s} {'vsPop':>7s}")
    print("-" * 72)
    for tid, theory in REGISTRY.items():
        for label, override in variants.get(tid, [("default", {})]):
            params = {tid: override}
            flagged = [w for w in scored
                       if any(f.theory == tid for f in evaluate_all(ctxs[w], enabled={tid}, params=params))]
            rois = [r for w in flagged for r in fwd_rois[w]]
            if not rois:
                print(f"{theory.desc[:22]:22s} {label:10s} {len(flagged):7d} "
                      f"{len(flagged)/days:5.1f} {'—':>8s} {'—':>5s} {'—':>7s}")
                continue
            mean = st.mean(rois)
            hit = sum(1 for r in rois if r > 0) / len(rois)
            print(f"{theory.desc[:22]:22s} {label:10s} {len(flagged):7d} "
                  f"{len(flagged)/days:5.1f} {mean:+8.3f} {hit:4.0%} {mean-pop_mean:+7.3f}")
    print("\n(copyROI = mean forward copy-ROI per $1, exit-following; vsPop = edge over population)")


def _variant_grid():
    """A small stricter-threshold grid per theory for the calibration sweep."""
    return {
        "1a": [("default", {}), ("strict", {"min_bet": 5000, "min_hours": 48})],
        "1b": [("default", {}), ("t2", {"min_tstat": 2}), ("t3", {"min_tstat": 3}),
               ("t5", {"min_tstat": 5})],
        "1c": [("default", {}), ("cap2.5", {"min_capture_cents": 2.5})],
        "1d": [("default", {}), ("sharpe.5", {"min_sharpe": 0.5, "max_drawdown_frac": 0.3})],
        "1e": [("default", {}), ("edge.1", {"min_edge": 0.10, "min_n": 12})],
        "1f": [("default", {}), ("win.6", {"min_win_rate": 0.6, "min_mean_roi": 0.10})],
        "1g": [("default", {}), ("roi.3", {"min_roi": 0.30})],
        "1h": [("default", {}), ("lead6", {"min_lead_cents": 6.0})],
        "1i": [("default", {}), ("hit.65", {"min_hit_rate": 0.65, "min_capital": 100000})],
        "1j": [("default", {}), ("bet5k", {"min_bet": 5000, "max_markets": 4})],
    }


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calibrate")
    c.add_argument("--universe", type=int, default=400)
    c.add_argument("--forward-days", type=int, default=30)
    c.add_argument("--min-usd", type=float, default=100.0)
    c.add_argument("--slippage-bps", type=float, default=0.0,
                   help="execution drag: copier fills worse than the target on entry+exit")
    c.add_argument("--cache-dir", default="data/wcache")
    c.add_argument("--res-cache", default="data/rescache")
    c.add_argument("--wallets-from", default="", help="dir of cached {wallet}.json to reuse as universe")
    c.set_defaults(func=calibrate)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
