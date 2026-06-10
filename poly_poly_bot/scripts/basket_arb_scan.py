#!/usr/bin/env python3
"""Live depth-aware basket-arbitrage scanner (Strategy 3, measurement).

Scans Polymarket neg-risk multi-outcome events for risk-free buy-all-outcomes
baskets (assemble one share of every mutually-exclusive outcome for < $1 net of
fees -> guaranteed $1 payout, realisable immediately via the neg-risk merge).

Unlike a naive "sum of best asks < 1" probe, it walks each leg's full order book
so the reported profit reflects the size you could actually fill. Optionally it
re-polls flagged opportunities to measure how long the window stays open (are
they fillable before existing bots take them?).

This is a measurement tool — it places no orders. Findings feed the decision on
whether the basket strategy clears fees + execution risk at meaningful size.

Usage:
    python -m scripts.basket_arb_scan --min-liquidity 1000000 --max-events 25
    python -m scripts.basket_arb_scan --persist-secs 60   # re-poll openers
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from src.basket_arb.edge import basket_buy_edge, top_of_book_sum  # noqa: E402

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


def fetch_negrisk_events(max_events: int, min_liquidity: float) -> list[dict]:
    j = _get(GAMMA, "/events", closed="false", active="true",
             order="liquidity", ascending="false", limit=120)
    out = []
    for e in j or []:
        if len(e.get("markets", [])) < 3:
            continue
        if not (e.get("negRisk") or e.get("negRiskAugmented")):
            continue
        try:
            if float(e.get("liquidity") or 0) < min_liquidity:
                continue
        except (ValueError, TypeError):
            continue
        out.append(e)
        if len(out) >= max_events:
            break
    return out


def _yes_token(market: dict):
    ct = market.get("clobTokenIds")
    if isinstance(ct, str):
        try:
            ct = json.loads(ct)
        except json.JSONDecodeError:
            return None
    return ct[0] if ct else None


def _fee_rate(market: dict) -> float:
    for key in ("fee_rate_bps", "feeRateBps"):
        v = market.get(key)
        if v is not None:
            try:
                return max(0.0, float(v) / 10000.0)
            except (ValueError, TypeError):
                pass
    return 0.0


def fetch_book(token_id: str):
    b = _get(CLOB, "/book", token_id=token_id)
    if not b:
        return [], []
    asks = [(float(a["price"]), float(a["size"])) for a in (b.get("asks") or [])]
    bids = [(float(x["price"]), float(x["size"])) for x in (b.get("bids") or [])]
    return asks, bids


def eval_event(event: dict) -> dict | None:
    markets = event.get("markets", [])
    tokens, fee = [], 0.0
    for m in markets:
        t = _yes_token(m)
        if t:
            tokens.append(t)
            fee = max(fee, _fee_rate(m))
    if len(tokens) < 3:
        return None
    legs = [None] * len(tokens)
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(fetch_book, t): i for i, t in enumerate(tokens)}
        for f in as_completed(futs):
            asks, _bids = f.result()
            legs[futs[f]] = asks
    legs = [a if a else [] for a in legs]
    edge = basket_buy_edge(legs, fee_rate=fee)
    return {
        "title": event.get("title", ""),
        "legs": len(tokens),
        "fee_rate": fee,
        "tob_sum": round(top_of_book_sum(legs), 4),
        "best_size": round(edge.best_size, 1),
        "cost": round(edge.cost, 2),
        "profit": round(edge.profit, 2),
        "roi": round(edge.roi, 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-events", type=int, default=25)
    ap.add_argument("--min-liquidity", type=float, default=1_000_000)
    ap.add_argument("--persist-secs", type=int, default=0,
                    help="re-poll profitable openers after N seconds")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    events = fetch_negrisk_events(args.max_events, args.min_liquidity)
    print(f"scanning {len(events)} neg-risk events (liq >= ${args.min_liquidity:,.0f})\n")
    rows = []
    for e in events:
        r = eval_event(e)
        if not r:
            continue
        rows.append(r)
        flag = ""
        if r["profit"] > 0:
            flag = f"  <<< ARB profit=${r['profit']} size={r['best_size']} roi={r['roi']:+.2%}"
        print(f"{r['title'][:46]:46} legs={r['legs']:>2} fee={r['fee_rate']:.2%} "
              f"tob_sum={r['tob_sum']:.3f} bestProfit=${r['profit']:>7.2f}{flag}")

    openers = [r for r in rows if r["profit"] > 0]
    print(f"\nprofitable baskets: {len(openers)} / {len(rows)} events")
    if openers:
        tot = sum(r["profit"] for r in openers)
        print(f"total instantaneous risk-free profit available: ${tot:,.2f}")

    if args.persist_secs and openers:
        print(f"\nre-polling {len(openers)} openers after {args.persist_secs}s "
              f"to measure window persistence...")
        time.sleep(args.persist_secs)
        ev_by_title = {e.get("title", ""): e for e in events}
        for r in openers:
            e = ev_by_title.get(r["title"])
            r2 = eval_event(e) if e else None
            still = r2["profit"] if r2 else 0.0
            verdict = "STILL OPEN" if still > 0 else "closed"
            print(f"  {r['title'][:46]:46} was ${r['profit']:.2f} -> now ${still:.2f}  [{verdict}]")

    if args.output:
        json.dump({"generated": int(time.time()), "events": rows},
                  open(args.output, "w"), indent=2)
        print(f"\nwrote {args.output}")


if __name__ == "__main__":
    main()
