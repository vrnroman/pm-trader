"""Copy-trading lag-sweep kill-test — the keystone backtest behind the
winning-markets / cost-floor / conviction-sizing / exit-following changes.

It answers the question a forward paper book can't isolate: **how much of the
copy book's loss is execution lag, and how much is that copy-and-hold is simply
−EV on the wallets/markets we picked?** It replays each historically-copied BUY
filled at the price prevailing ``L`` seconds after the target traded
(``price_at(their_ts + L)``), held to resolution, and sweeps ``L``. Because it
fills off real CLOB price history (not the target's own clean price), it
reproduces the live ledger's realized ROI at the live detection lag — which is
what makes the counterfactuals (shorter L, exit-following, per-category) trustworthy.

Findings that drove the surrounding code (run on the live ledger's 273 positions):
  * At the target's OWN entry price, zero lag, held to resolution: **−27.8%**
    (t=−4.95). Lag is NOT the cause — copy-and-hold is −EV at every lag 0..2h.
  * Reproduce check: gross @35m (the live median detection lag) = −22.1% vs the
    live ledger's −22.5%. The rig matches reality.
  * Categorical: sports −27%/−30%, research −62%, other −24%, only crypto +EV
    (n=10, too thin to bank) → the winning-markets-by-category gate.
  * Exit-following: the target exited early on only 7% of positions, but on those
    mirroring the sell returned +287% vs −35% held → reliable exit-mirroring.

The core functions are pure (data injected) so they unit-test offline; the CLI
loads a data dir built by the companion fetch scripts (see ``--data-dir``).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from src.copy_trading.copy_cost import CostModel
from src.copy_trading.lead_lag import price_at
from src.copy_trading.trader_scoring import tstat

# (label, lag-seconds) grid. 35m ≈ the live median detection lag; 6h ≈ the old
# COPY_PAPER_MAX_AGE_S cap (its prices sit near resolution → 1/p blows up, so it
# is reported but not trusted).
DEFAULT_LAGS = [("their", 0), ("2m", 120), ("5m", 300), ("15m", 900),
                ("35m", 2100), ("1h", 3600), ("2h", 7200)]


@dataclass
class LagCell:
    """Aggregate copy-and-hold result at one fill-lag."""
    label: str
    lag_s: int
    n: int = 0
    gross_roi: float = 0.0
    net_roi: float = 0.0
    tstat: float = 0.0
    hit_rate: float = 0.0


@dataclass
class LagSweepResult:
    cells: list = field(default_factory=list)              # list[LagCell]
    by_category: dict = field(default_factory=dict)        # cat -> {label: gross_roi}


def _roi_hold(fill_price: float, won: bool) -> float:
    """Copy-and-hold ROI-per-$1: buy at ``fill_price``, settle to 0/1."""
    return (1.0 / fill_price - 1.0) if won else -1.0


def _agg(rois: list) -> tuple:
    if not rois:
        return (0, 0.0, 0.0, 0.0)
    return (len(rois), statistics.mean(rois), tstat(rois),
            sum(1 for r in rois if r > 0) / len(rois))


def lag_sweep(
    events: list,
    series_by_token: dict,
    cost_model: CostModel,
    lags: Optional[list] = None,
) -> LagSweepResult:
    """Sweep copy-and-hold ROI across fill-lags.

    ``events``: dicts with ``token``, ``their_ts``, ``won`` (bool), ``cat``.
    ``series_by_token``: token -> sorted [(ts, price)]. Net ROI deducts the
    category's round-trip cost. Buys whose lagged fill price is missing or out of
    (0,1) are skipped for that lag."""
    lags = lags or DEFAULT_LAGS
    res = LagSweepResult()
    bycat = defaultdict(lambda: defaultdict(list))
    for label, L in lags:
        gross, net = [], []
        for e in events:
            fp = price_at(series_by_token.get(e["token"], []), e["their_ts"] + L)
            if fp is None or fp <= 0 or fp >= 1:
                continue
            g = _roi_hold(fp, e["won"])
            gross.append(g)
            net.append(cost_model.net_roi(g, e.get("cat", "other")))
            bycat[e.get("cat", "other")][label].append(g)
        n, gm, gt, gh = _agg(gross)
        res.cells.append(LagCell(label, L, n, round(gm, 4),
                                 round(statistics.mean(net), 4) if net else 0.0,
                                 round(gt, 3), round(gh, 4)))
    res.by_category = {c: {lab: round(statistics.mean(v), 4) for lab, v in d.items()}
                       for c, d in bycat.items()}
    return res


def exit_follow_compare(
    events: list,
    sells_by_wallet_token: dict,
    series_by_token: dict,
    lag_s: int = 2100,
) -> dict:
    """Hold-to-resolution vs mirror-the-target's-exit, at a realistic fill lag.

    ``sells_by_wallet_token``: (wallet, token) -> list[(ts, price, size)]. On a
    position the target later sold, we exit at their size-weighted avg sell price;
    otherwise we hold to resolution. Returns aggregate + the they-exited subset."""
    hold, follow = [], []
    sub_hold, sub_follow = [], []
    n_exited = 0
    for e in events:
        entry = price_at(series_by_token.get(e["token"], []), e["their_ts"] + lag_s)
        if entry is None or entry <= 0 or entry >= 1:
            continue
        h = _roi_hold(entry, e["won"])
        hold.append(h)
        later = [s for s in sells_by_wallet_token.get((e["wallet"], e["token"]), [])
                 if s[0] >= e["their_ts"]]
        if later:
            tot = sum(s[2] for s in later) or 1.0
            xp = sum(s[1] * s[2] for s in later) / tot
            f = xp / entry - 1.0
            follow.append(f)
            n_exited += 1
            sub_hold.append(h)
            sub_follow.append(f)
        else:
            follow.append(h)
    return {
        "n": len(hold), "n_exited": n_exited,
        "hold": _agg(hold), "follow": _agg(follow),
        "subset_hold": _agg(sub_hold), "subset_follow": _agg(sub_follow),
    }


def realized_roi(ledger_rows: list) -> tuple:
    """The live ledger's realized cost-weighted ROI over closed non-dust rows —
    the number the rig must reproduce. Returns (roi, n)."""
    def dust(r):
        tp, ep = r.get("their_price", 0) or 0, r.get("entry_price", 0) or 0
        return tp > 0 and 0 < ep < tp * 0.5
    cl = [r for r in ledger_rows if r.get("closed") and not dust(r)]
    cost = sum(r.get("spent", 0.0) for r in cl)
    pnl = sum(r.get("pnl", 0.0) for r in cl)
    return (pnl / cost if cost else 0.0, len(cl))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _load_dir(data_dir: str):
    events = json.load(open(os.path.join(data_dir, "ledger_events.json")))
    pc = os.path.join(data_dir, "pcache")
    series = {}
    for e in events:
        p = os.path.join(pc, f"{e['token']}.json")
        if e["token"] not in series and os.path.exists(p):
            series[e["token"]] = [tuple(x) for x in json.load(open(p))]
    return events, series


def main(argv=None):
    ap = argparse.ArgumentParser(description="Copy-trading lag-sweep kill-test")
    ap.add_argument("--data-dir", required=True,
                    help="dir with ledger_events.json + pcache/<token>.json")
    ap.add_argument("--ledger", help="copy_paper_ledger.jsonl for the reproduce check")
    args = ap.parse_args(argv)

    events, series = _load_dir(args.data_dir)
    cost = CostModel.from_env()
    res = lag_sweep(events, series, cost)

    print(f"events={len(events)}  cost={cost.category_cost}\n")
    print(f"{'lag':>6} | {'n':>4} {'grossROI%':>9} {'tstat':>6} {'hit%':>5} | {'netROI%':>8}")
    print("-" * 60)
    for c in res.cells:
        print(f"{c.label:>6} | {c.n:>4} {c.gross_roi*100:>9.1f} {c.tstat:>6.2f} "
              f"{c.hit_rate*100:>5.0f} | {c.net_roi*100:>8.1f}")

    if args.ledger and os.path.exists(args.ledger):
        rows = [json.loads(l) for l in open(args.ledger) if l.strip()]
        roi, n = realized_roi(rows)
        g35 = next((c.gross_roi for c in res.cells if c.label == "35m"), 0.0)
        print(f"\nreproduce: live realized={roi*100:.1f}% (n={n}) vs rig @35m={g35*100:.1f}%")

    print("\nby category (gross ROI% / lag):")
    for cat, d in sorted(res.by_category.items()):
        print(f"  {cat:9} " + " ".join(f"{lab}:{v*100:.0f}" for lab, v in d.items()))


if __name__ == "__main__":
    main()
