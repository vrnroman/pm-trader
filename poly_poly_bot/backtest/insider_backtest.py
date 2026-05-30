#!/usr/bin/env python3
"""Backtest for Strategy 1a — insider trade-shape following.

Hypothesis: a large, concentrated bet from a young/first-time account on a
news/geopolitical market is an informed-trader fingerprint, and copying it
(hold to resolution) is profitable.

This is a genuine backtest — on-chain trade history and market resolutions are
fully archived, so no lookahead is required. For a sample of resolved geo
markets it reconstructs every large BUY, computes the trader's account age (#
prior trades at the moment of the bet), flags the insider shape, and measures
copy PnL vs two controls (veteran large bettors; all large bettors).

NOTE: true insider trades are rare binary events, so expect a modest sample and
wide confidence intervals. Wilson 95% CIs are reported so weak signals aren't
over-read.

Usage:
    python -m backtest.insider_backtest --markets 60 --min-bet 1000 --max-prior 5
"""

from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.copy_trading.insider_signal import (
    copy_pnl_per_dollar,
    is_geopolitical_market,
    is_insider_shaped,
    prior_trade_count,
    trade_usd,
    wilson_interval,
)

GAMMA = "https://gamma-api.polymarket.com"
DATA = os.environ.get("DATA_API_URL", "https://data-api.polymarket.com")
GEO_TAGS = ["geopolitics", "world", "elections", "ukraine", "israel",
            "middle-east", "iran", "russia", "china", "nato", "war", "trump"]


def _parse_iso(s: str) -> float:
    """Parse Polymarket date strings to epoch seconds.

    Handles both '2026-02-05T00:00:00Z' (endDate) and
    '2026-02-06 07:06:43+00' (closedTime).
    """
    import datetime as _dt
    s = s.strip().replace("Z", "+00:00")
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)
    if s.endswith("+00"):
        s = s + ":00"
    return _dt.datetime.fromisoformat(s).timestamp()


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


def fetch_resolved_geo_markets(max_markets: int) -> list[dict]:
    """Return [{condition_id, question, winner_index}] for resolved geo markets."""
    s = requests.Session()
    out: dict[str, dict] = {}
    for tag in GEO_TAGS:
        offset = 0
        while offset < 600 and len(out) < max_markets:
            evs = _get(s, GAMMA, "/events", tag_slug=tag, limit=100,
                       offset=offset, closed="true", order="volume", ascending="false")
            if not evs:
                break
            for e in evs:
                for m in e.get("markets", []):
                    cid = m.get("conditionId")
                    q = m.get("question", "")
                    if not cid or cid in out:
                        continue
                    if not is_geopolitical_market(q, cid):
                        continue
                    op = m.get("outcomePrices")
                    if isinstance(op, str):
                        try:
                            op = json.loads(op)
                        except json.JSONDecodeError:
                            continue
                    if not op or len(op) < 2:
                        continue
                    winner = None
                    for i, p in enumerate(op):
                        try:
                            if float(p) >= 0.99:
                                winner = i
                        except (ValueError, TypeError):
                            pass
                    if winner is None:
                        continue  # voided/ambiguous
                    end_ts = 0.0
                    # closedTime = actual resolution; endDate = scheduled (often
                    # later). Prefer the real resolution moment for the timing gate.
                    ed = m.get("closedTime") or m.get("endDate") or m.get("endDateIso")
                    if ed:
                        try:
                            end_ts = _parse_iso(ed)
                        except (ValueError, TypeError):
                            end_ts = 0.0
                    out[cid] = {"condition_id": cid, "question": q,
                                "winner_index": winner, "end_ts": end_ts}
            offset += 100
            if len(out) >= max_markets:
                break
        if len(out) >= max_markets:
            break
    return list(out.values())[:max_markets]


def fetch_market_trades(cid: str, cap: int = 12000) -> list[dict]:
    # /trades is newest-first, so reaching EARLY bets requires paging deep.
    s = requests.Session()
    out, offset = [], 0
    while offset < cap:
        tr = _get(s, DATA, "/trades", market=cid, limit=500, offset=offset, takerOnly="false")
        if not tr:
            break
        out += tr
        offset += 500
        if len(tr) < 500:
            break
    return out


def fetch_activity(wallet: str, cap: int = 1500) -> list[dict]:
    s = requests.Session()
    out, offset = [], 0
    while offset < cap:
        a = _get(s, DATA, "/activity", user=wallet, limit=500, offset=offset)
        if not a:
            break
        out += a
        offset += 500
        if len(a) < 500:
            break
    return out


def _summary(name: str, pnls: list[float], wins: int) -> dict:
    n = len(pnls)
    if n == 0:
        return {"group": name, "n": 0}
    lo, hi = wilson_interval(wins, n)
    return {
        "group": name, "n": n,
        "ev_per_dollar": round(st.mean(pnls), 4),
        "median_pnl": round(st.median(pnls), 4),
        "hit_rate": round(wins / n, 4),
        "hit_ci95": [round(lo, 3), round(hi, 3)],
        "total_pnl_per_dollar": round(sum(pnls), 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets", type=int, default=60)
    ap.add_argument("--min-bet", type=float, default=1000.0)
    ap.add_argument("--max-prior", type=int, default=5)
    ap.add_argument("--min-price", type=float, default=0.05)
    ap.add_argument("--max-price", type=float, default=0.95)
    ap.add_argument("--min-hours-before", type=float, default=48.0,
                    help="exclude bets placed within N hours of resolution "
                         "(removes settlement-lag scooping, isolates EARLY bets)")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    markets = fetch_resolved_geo_markets(args.markets)
    print(f"resolved geo markets: {len(markets)}", file=sys.stderr)
    winners = {m["condition_id"]: m["winner_index"] for m in markets}
    end_ts = {m["condition_id"]: m.get("end_ts", 0.0) for m in markets}

    with_end = sum(1 for v in end_ts.values() if v > 0)
    print(f"markets with resolution timestamp: {with_end}/{len(markets)}", file=sys.stderr)

    # 1) gather large BUY candidates across all markets
    candidates = []  # (cid, wallet, ts, price, outcome_index, bet_usd)
    n_late_dropped = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_market_trades, m["condition_id"]): m["condition_id"]
                for m in markets}
        for f in as_completed(futs):
            cid = futs[f]
            for t in f.result() or []:
                if t.get("side") != "BUY":
                    continue
                price = float(t.get("price") or 0)
                if not (args.min_price <= price <= args.max_price):
                    continue
                usd = trade_usd(t.get("size") or 0, price, t.get("usdcSize"))
                if usd < args.min_bet:
                    continue
                w = t.get("proxyWallet")
                if not w:
                    continue
                ts = float(t.get("timestamp") or 0)
                # Timing control: drop late bets placed near resolution, which
                # are settlement-lag scooping (buying a near-certain $1 cheap),
                # not informed early positioning.
                et = end_ts.get(cid, 0.0)
                if et and ts > et - args.min_hours_before * 3600:
                    n_late_dropped += 1
                    continue
                candidates.append((cid, w, ts, price, int(t.get("outcomeIndex") or 0), usd))
    print(f"large BUY candidates (>{args.min_hours_before:.0f}h before resolution): "
          f"{len(candidates)} (dropped {n_late_dropped} late bets)", file=sys.stderr)

    # 2) fetch unique traders' history (for prior-trade counts)
    wallets = sorted({c[1] for c in candidates})
    print(f"unique traders to profile: {len(wallets)}", file=sys.stderr)
    hist: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(fetch_activity, w): w for w in wallets}
        done = 0
        for f in as_completed(futs):
            hist[futs[f]] = f.result() or []
            done += 1
            if done % 100 == 0:
                print(f"  profiled {done}/{len(wallets)}", file=sys.stderr)

    # 3) classify + simulate copy PnL
    ins_pnl, ins_win = [], 0
    vet_pnl, vet_win = [], 0
    all_pnl, all_win = [], 0
    for cid, w, ts, price, oi, usd in candidates:
        won = (oi == winners.get(cid))
        pnl = copy_pnl_per_dollar(price, won)
        prior = prior_trade_count(hist.get(w, []), ts)
        is_geo = True  # candidates are only from geo markets
        insider = is_insider_shaped(prior_count=prior, bet_usd=usd, is_geo=is_geo,
                                    max_prior=args.max_prior, min_bet=args.min_bet)
        all_pnl.append(pnl); all_win += won
        if insider:
            ins_pnl.append(pnl); ins_win += won
        else:
            vet_pnl.append(pnl); vet_win += won

    groups = [
        _summary("insider-shaped (young+large+geo)", ins_pnl, ins_win),
        _summary("veteran large (control)", vet_pnl, vet_win),
        _summary("all large geo BUYs", all_pnl, all_win),
    ]
    print("\n" + "=" * 70)
    print("  Strategy 1a — Insider Trade-Shape Backtest")
    print("=" * 70)
    print(f"  markets={len(markets)}  min_bet=${args.min_bet:.0f}  "
          f"max_prior_trades={args.max_prior}")
    for g in groups:
        if g["n"] == 0:
            print(f"\n  {g['group']}: n=0")
            continue
        print(f"\n  {g['group']}")
        print(f"    n={g['n']}  EV/$ staked={g['ev_per_dollar']:+.3f}  "
              f"hit={g['hit_rate']:.1%} (95% CI {g['hit_ci95'][0]:.0%}-{g['hit_ci95'][1]:.0%})")
    print("\n  Interpretation: positive EV/$ with a hit-rate CI clearly above the")
    print("  break-even win prob = mean entry price => real informed-trader edge.")

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        json.dump({"generated": int(time.time()),
                   "params": vars(args), "groups": groups},
                  open(args.output, "w"), indent=2)
        print(f"\nwrote {args.output}")


if __name__ == "__main__":
    main()
