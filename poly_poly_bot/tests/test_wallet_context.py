"""WalletContext feature extraction — buys (resolution-enriched) + round-trips.

Round-trips model early exits: a position bought then fully sold before any
redeem is a swing the copier should mirror. A redeemed position is held to
resolution and is NOT a round trip (it's covered by closed-ROI).
"""

from __future__ import annotations

from src.copy_trading.wallet_context import (
    MarketResolution,
    build_context,
)


def _trade(side, cid, oi, price, size, ts, title="Generic market"):
    return {"type": "TRADE", "side": side, "conditionId": cid, "outcomeIndex": oi,
            "price": price, "size": size, "usdcSize": price * size,
            "timestamp": ts, "title": title, "asset": f"{cid}-{oi}"}


def test_buys_enriched_with_resolution_outcome_and_timing():
    acts = [_trade("BUY", "m1", 0, 0.20, 100, ts=1000)]
    res = {"m1": MarketResolution(winning_index=0, end_ts=1000 + 3600 * 48)}
    ctx = build_context("0xw", acts, now=2000, resolutions=res)
    assert len(ctx.buys) == 1
    b = ctx.buys[0]
    assert b.won is True                        # bought outcome 0, which won
    assert abs(b.hours_before_resolution - 48) < 1e-6
    assert b.category == "other"


def test_buy_marked_lost_when_other_outcome_won():
    acts = [_trade("BUY", "m1", 1, 0.20, 100, ts=1000)]
    res = {"m1": MarketResolution(winning_index=0, end_ts=1000)}
    ctx = build_context("0xw", acts, now=2000, resolutions=res)
    assert ctx.buys[0].won is False


def test_round_trip_from_full_exit_not_redeemed():
    acts = [
        _trade("BUY", "m1", 0, 0.30, 100, ts=1000),
        _trade("SELL", "m1", 0, 0.50, 100, ts=1000 + 7200),  # sold out at a profit
    ]
    ctx = build_context("0xw", acts, now=5000)
    assert len(ctx.round_trips) == 1
    t = ctx.round_trips[0]
    assert abs(t.entry_price - 0.30) < 1e-9 and abs(t.exit_price - 0.50) < 1e-9
    assert abs(t.pnl - (50 - 30)) < 1e-9         # 100*0.5 - 100*0.3
    assert abs(t.held_s - 7200) < 1e-9
    assert t.roi > 0


def test_redeemed_position_is_not_a_round_trip():
    acts = [
        _trade("BUY", "m1", 0, 0.30, 100, ts=1000),
        {"type": "REDEEM", "conditionId": "m1", "outcomeIndex": 0,
         "usdcSize": 100, "size": 100, "timestamp": 2000},
    ]
    ctx = build_context("0xw", acts, now=5000)
    assert ctx.round_trips == []                 # held to resolution, not a swing


def test_partial_exit_is_not_counted_as_round_trip():
    acts = [
        _trade("BUY", "m1", 0, 0.30, 100, ts=1000),
        _trade("SELL", "m1", 0, 0.50, 40, ts=2000),  # only sold 40 of 100
    ]
    ctx = build_context("0xw", acts, now=5000)
    assert ctx.round_trips == []
