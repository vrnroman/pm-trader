"""Tests for lead-lag / informed-money analysis."""

from __future__ import annotations

from src.copy_trading.lead_lag import (
    WalletLeadLag,
    analyze_buy,
    price_at,
)


def _series():
    # (ts, price) at 0,15,30,...,300 min; price ramps 0.40 -> 0.70
    pts = []
    for i in range(0, 21):
        pts.append((i * 900.0, 0.40 + i * 0.015))
    return pts


def test_price_at_uses_last_observation():
    s = [(0, 0.40), (900, 0.50), (1800, 0.60)]
    assert price_at(s, 0) == 0.40
    assert price_at(s, 950) == 0.50      # between points -> last <=
    assert price_at(s, 5000) == 0.60     # after end -> last known
    assert price_at(s, -1) is None       # before start -> unknown


def test_analyze_buy_measures_lead_capture_slippage():
    s = _series()
    # buy at t=0 (price 0.40); delay 15m -> price 0.415; +4h later
    r = analyze_buy(s, 0.0, delay_s=900, horizon_s=14400)
    assert r is not None
    assert abs(r.entry_price - 0.40) < 1e-9
    assert abs(r.delayed_price - 0.415) < 1e-9
    # future at 900+14400 = 15300s = 17 points * 900 -> 0.40+17*0.015=0.655
    assert abs(r.future_price - 0.655) < 1e-9
    assert abs(r.lead_move - (0.655 - 0.40)) < 1e-9
    assert abs(r.capture_move - (0.655 - 0.415)) < 1e-9
    assert abs(r.slippage - (0.415 - 0.40)) < 1e-9


def test_analyze_buy_insufficient_data():
    s = [(0, 0.5), (900, 0.5)]
    # horizon runs past the series end is OK (last-known), but pre-start is None
    assert analyze_buy(s, -100, delay_s=10, horizon_s=10) is None


def test_wallet_lead_lag_aggregation_buy_side():
    s = _series()
    w = WalletLeadLag()
    for ts in (0.0, 900.0, 1800.0):
        r = analyze_buy(s, ts, delay_s=900, horizon_s=3600)
        w.add(r, side_sign=1)
    assert w.n == 3
    # price always rises in this series, so every BUY leads positively
    assert w.lead_hit_rate == 1.0
    assert w.capture_hit_rate == 1.0
    assert w.avg_lead > 0
    assert w.informed_score == w.avg_lead


def test_side_sign_flips_direction():
    # falling price series; a SELL (side_sign=-1) should score as informed
    s = [(i * 900.0, 0.70 - i * 0.02) for i in range(10)]
    w = WalletLeadLag()
    r = analyze_buy(s, 0.0, delay_s=900, horizon_s=3600)
    w.add(r, side_sign=-1)
    assert w.lead_wins == 1          # price fell, sell-direction profited
    assert w.avg_lead > 0


def test_slippage_against_copier():
    # rising price: a delayed BUY pays more than the leader (positive slippage)
    s = _series()
    r = analyze_buy(s, 0.0, delay_s=1800, horizon_s=900)
    assert r.slippage > 0            # we entered higher than the wallet
    assert r.capture_move < r.lead_move  # we capture less than the leader
