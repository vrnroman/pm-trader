"""PnL-curve shape metrics (Strategy 1b feeder).

The user-pnl endpoint gives a wallet's *cumulative* PnL over its whole life,
which is how we judge heavy traders the /activity cap can't fully replay. These
tests pin the shape math (drawdown, up-ratio, slope, sharpe) and the
steady-earner filter on synthetic curves with known properties.
"""

from __future__ import annotations

import math

from src.copy_trading import pnl_curve as pc
from src.copy_trading.pnl_curve import CurveMetrics, curve_metrics


def _curve(values):
    return [(float(i), float(v)) for i, v in enumerate(values)]


def test_empty_and_singleton_curves():
    assert curve_metrics([]) == CurveMetrics()
    one = curve_metrics(_curve([5]))
    assert one.n == 1 and one.peak == 5.0 and one.net_pnl == 0.0


def test_monotonic_rising_curve_is_clean():
    m = curve_metrics(_curve([0, 1, 2, 3, 4, 5]))
    assert m.net_pnl == 5.0
    assert m.max_drawdown == 0.0          # never declines
    assert m.max_drawdown_frac == 0.0
    assert m.up_ratio == 1.0              # every step up
    assert m.slope_per_period == 1.0
    assert m.sharpe == pc._MAX_SHARPE     # zero-variance steady rise → maximal
    assert m.is_steady_earner()


def test_drawdown_is_largest_peak_to_trough():
    # rises to 10, craters to 2 (dd=8 off peak 10 → 0.8), partial recovery to 6
    m = curve_metrics(_curve([0, 10, 2, 6]))
    assert m.peak == 10.0
    assert m.max_drawdown == 8.0
    assert math.isclose(m.max_drawdown_frac, 0.8)
    # 0.8 drawdown exceeds the default 0.5 cap → not a steady earner
    assert not m.is_steady_earner()


def test_volatile_but_net_positive_curve_flagged_by_drawdown():
    m = curve_metrics(_curve([0, 5, -3, 8, -1, 12]))
    assert m.net_pnl == 12.0              # ends up
    assert m.up_ratio < 1.0               # but bounces around
    # sawtooth: should be rejected by the drawdown cap even though net>0
    assert not m.is_steady_earner(max_drawdown_frac=0.3)


def test_steady_earner_thresholds():
    gentle = curve_metrics(_curve([0, 1, 1, 2, 3, 3, 4]))   # mostly up, no drawdown
    assert gentle.is_steady_earner(min_up_ratio=0.5)
    # raising the up-ratio bar past its actual value rejects it
    assert not gentle.is_steady_earner(min_up_ratio=0.99)
    # too few points is always rejected
    assert not curve_metrics(_curve([0, 1])).is_steady_earner()


def test_fetch_pnl_curve_parses_and_sorts(monkeypatch):
    def fake_get(session, base, path, **params):
        assert path == "/user-pnl"
        assert params["user_address"] == "0xabc"
        return [{"t": 30, "p": 3.0}, {"t": 10, "p": 1.0}, {"t": 20, "p": 2.0},
                {"t": 40}]  # missing p → skipped
    monkeypatch.setattr(pc, "_get", fake_get)
    pts = pc.fetch_pnl_curve("0xabc")
    assert pts == [(10.0, 1.0), (20.0, 2.0), (30.0, 3.0)]


def test_fetch_pnl_curve_empty_on_error(monkeypatch):
    monkeypatch.setattr(pc, "_get", lambda *a, **k: None)
    assert pc.fetch_pnl_curve("0xabc") == []


def test_fetch_portfolio_value_list_and_dict(monkeypatch):
    monkeypatch.setattr(pc, "_get",
                        lambda *a, **k: [{"user": "0xabc", "value": 1234.5}])
    assert pc.fetch_portfolio_value("0xabc") == 1234.5
    monkeypatch.setattr(pc, "_get", lambda *a, **k: {"value": 99.0})
    assert pc.fetch_portfolio_value("0xabc") == 99.0
    monkeypatch.setattr(pc, "_get", lambda *a, **k: None)
    assert pc.fetch_portfolio_value("0xabc") is None
