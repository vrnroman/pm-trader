"""Tests for the copy-trading lag-sweep kill-test core (pure functions)."""
from __future__ import annotations

from src.copy_trading.copy_cost import CostModel
from backtest.copy_lag_backtest import (
    exit_follow_compare,
    lag_sweep,
    realized_roi,
)

# price series: flat at 0.50 from t=0, jumps to 0.60 at t=1000.
SERIES = {"TOK": [(0.0, 0.50), (1000.0, 0.60)]}


def _ev(token="TOK", their_ts=0.0, won=True, cat="crypto", wallet="0xW"):
    return {"token": token, "their_ts": their_ts, "won": won, "cat": cat, "wallet": wallet}


def test_lag_sweep_fills_at_lagged_price():
    # at L=0 fill 0.50 (win -> +1.0); at a lag crossing t=1000 fill 0.60 (+0.667)
    cost = CostModel(category_cost={"crypto": 0.0}, fallback=0.0, margin=0.0)
    res = lag_sweep([_ev(their_ts=0.0)], SERIES, cost,
                    lags=[("L0", 0), ("L2k", 2000)])
    c0 = next(c for c in res.cells if c.label == "L0")
    c2 = next(c for c in res.cells if c.label == "L2k")
    assert c0.gross_roi == 1.0                      # 1/0.50 - 1
    assert round(c2.gross_roi, 3) == 0.667          # 1/0.60 - 1


def test_lag_sweep_net_deducts_cost():
    cost = CostModel(category_cost={"crypto": 0.10}, fallback=0.10, margin=0.0)
    res = lag_sweep([_ev()], SERIES, cost, lags=[("L0", 0)])
    c0 = res.cells[0]
    assert c0.gross_roi == 1.0
    assert round(c0.net_roi, 3) == 0.90             # 1.0 - 0.10 cost


def test_lag_sweep_loss_is_minus_one():
    cost = CostModel(fallback=0.0, margin=0.0)
    res = lag_sweep([_ev(won=False)], SERIES, cost, lags=[("L0", 0)])
    assert res.cells[0].gross_roi == -1.0


def test_lag_sweep_skips_missing_price():
    # their_ts before the series start -> price_at None -> skipped for that lag
    cost = CostModel(fallback=0.0, margin=0.0)
    res = lag_sweep([_ev(their_ts=-100.0)], SERIES, cost, lags=[("L0", 0)])
    assert res.cells[0].n == 0


def test_lag_sweep_by_category():
    cost = CostModel(fallback=0.0, margin=0.0)
    evs = [_ev(cat="crypto", won=True), _ev(cat="sports", won=False)]
    res = lag_sweep(evs, SERIES, cost, lags=[("L0", 0)])
    assert res.by_category["crypto"]["L0"] == 1.0
    assert res.by_category["sports"]["L0"] == -1.0


def test_exit_follow_beats_hold_when_they_sell_high():
    # entry 0.50, won=False -> hold loses -1.0; but they SOLD at 0.80 -> +0.6
    sells = {("0xW", "TOK"): [(500.0, 0.80, 100.0)]}
    out = exit_follow_compare([_ev(won=False)], sells, SERIES, lag_s=0)
    assert out["n_exited"] == 1
    assert out["hold"][1] == -1.0                   # mean hold ROI
    assert round(out["follow"][1], 3) == 0.6        # mean exit-follow ROI


def test_exit_follow_holds_when_no_sell():
    out = exit_follow_compare([_ev(won=True)], {}, SERIES, lag_s=0)
    assert out["n_exited"] == 0
    assert out["follow"][1] == out["hold"][1] == 1.0  # falls back to hold


def test_realized_roi_cost_weighted_and_dust_excluded():
    rows = [
        {"closed": True, "spent": 100.0, "pnl": -50.0, "their_price": 0.5, "entry_price": 0.5},
        {"closed": True, "spent": 100.0, "pnl": 10.0, "their_price": 0.5, "entry_price": 0.5},
        # dust (entry far below their price) -> excluded
        {"closed": True, "spent": 100.0, "pnl": -100.0, "their_price": 0.5, "entry_price": 0.001},
        {"closed": False, "spent": 100.0, "pnl": 0.0, "their_price": 0.5, "entry_price": 0.5},
    ]
    roi, n = realized_roi(rows)
    assert n == 2
    assert round(roi, 3) == round(-40.0 / 200.0, 3)   # (-50+10)/(100+100)
