"""Tests for trader_scoring — the copy-target selection logic (Strategy 1b)."""

from __future__ import annotations

from src.copy_trading.trader_scoring import (
    MarketResult,
    WalletScore,
    classify_market,
    realized_market_results,
    score_wallet,
    select_copy_targets,
)


def _trade(cid, oi, side, size, usd, ts, title="Some Market"):
    return {
        "type": "TRADE", "conditionId": cid, "outcomeIndex": oi, "side": side,
        "size": size, "usdcSize": usd, "timestamp": ts, "title": title,
    }


def _redeem(cid, usd, ts, title="Some Market"):
    return {
        "type": "REDEEM", "conditionId": cid, "outcomeIndex": 999, "side": "",
        "size": usd, "usdcSize": usd, "timestamp": ts, "title": title,
    }


# --------------------------------------------------------------------------- #
# classify_market
# --------------------------------------------------------------------------- #

def test_classify_market_segments():
    assert classify_market("Lakers vs. Celtics") == "sports"
    assert classify_market("Will Bitcoin hit $150k?") == "crypto"
    assert classify_market("2028 Democratic Presidential Nominee") == "research"
    assert classify_market("Will it rain in Berlin tomorrow?") == "other"


def test_classify_crypto_beats_sports_keyword_collision():
    # "Bitcoin ... vs ..." must not be filed as sports
    assert classify_market("Bitcoin price vs Ethereum by Friday") == "crypto"


# --------------------------------------------------------------------------- #
# realized_market_results — closure detection & PnL
# --------------------------------------------------------------------------- #

def test_redeemed_winner_is_closed_with_profit():
    # buy 100 shares @0.40 ($40), redeem at $100 -> +$60, provably closed
    acts = [
        _trade("A", 0, "BUY", 100, 40, 1000),
        _redeem("A", 100, 2000),
    ]
    res = {r.condition_id: r for r in realized_market_results(acts)}
    a = res["A"]
    assert a.closed is True
    assert a.capital == 40
    assert a.pnl == 60
    assert abs(a.roi - 1.5) < 1e-9


def test_fully_exited_via_sell_is_closed():
    # buy 100 @0.50 ($50), sell 100 @0.55 ($55) -> +$5, net shares 0 -> closed
    acts = [
        _trade("B", 0, "BUY", 100, 50, 1000),
        _trade("B", 0, "SELL", 100, 55, 1500),
    ]
    b = realized_market_results(acts)[0]
    assert b.closed is True
    assert abs(b.pnl - 5) < 1e-9


def test_still_open_position_not_closed():
    # bought and still holding -> not closed, excluded from realized score
    acts = [_trade("C", 0, "BUY", 100, 50, 1000)]
    c = realized_market_results(acts)[0]
    assert c.closed is False


def test_losing_position_redeem_absent_but_fully_resolved_loss():
    # bought a loser, never sold, never redeemed -> residual shares remain,
    # so it is NOT auto-counted as closed (we require provable closure).
    acts = [_trade("D", 1, "BUY", 100, 50, 1000)]
    d = realized_market_results(acts)[0]
    assert d.closed is False


def test_rewards_excluded_from_pnl():
    acts = [
        _trade("E", 0, "BUY", 100, 40, 1000),
        _redeem("E", 100, 2000),
        {"type": "REWARD", "conditionId": "E", "usdcSize": 25, "timestamp": 2100},
    ]
    e = realized_market_results(acts)[0]
    assert e.pnl == 60  # reward income not added


def test_both_sides_traded_nets_to_closed():
    # buy YES then buy NO equally then both redeem/exit -> net shares zero
    acts = [
        _trade("F", 0, "BUY", 100, 50, 1000),
        _trade("F", 0, "SELL", 100, 60, 1100),
    ]
    f = realized_market_results(acts)[0]
    assert f.closed is True


# --------------------------------------------------------------------------- #
# score_wallet — windowing & category
# --------------------------------------------------------------------------- #

def test_score_wallet_window_filters_by_last_ts():
    acts = [
        _trade("A", 0, "BUY", 100, 40, 1000, "Lakers vs Celtics"),
        _redeem("A", 100, 1500, "Lakers vs Celtics"),       # closes at ts=1500
        _trade("B", 0, "BUY", 100, 50, 5000, "Knicks vs Heat"),
        _redeem("B", 0, 5500, "Knicks vs Heat"),            # closes at ts=5500, loss
    ]
    early = score_wallet(acts, start_ts=0, end_ts=3000)
    assert early.n_closed == 1
    assert early.pnl == 60
    late = score_wallet(acts, start_ts=3000, end_ts=9000)
    assert late.n_closed == 1
    assert late.pnl == -50


def test_score_wallet_category_filter():
    acts = [
        _trade("S", 0, "BUY", 100, 40, 1000, "Lakers vs Celtics"),
        _redeem("S", 100, 1500, "Lakers vs Celtics"),
        _trade("R", 0, "BUY", 100, 40, 1000, "2028 Presidential Nominee"),
        _redeem("R", 0, 1500, "2028 Presidential Nominee"),
    ]
    sports = score_wallet(acts, category="sports")
    assert sports.n_closed == 1 and sports.pnl == 60
    research = score_wallet(acts, category="research")
    assert research.n_closed == 1 and research.pnl == -40
    allcat = score_wallet(acts, category="ALL")
    assert allcat.n_closed == 2


def test_score_wallet_roi_and_hit_rate():
    acts = [
        _trade("A", 0, "BUY", 100, 50, 1000),
        _redeem("A", 100, 1500),   # win +50
        _trade("B", 0, "BUY", 100, 50, 1000),
        _trade("B", 0, "SELL", 100, 25, 1500),  # loss -25, closed
    ]
    s = score_wallet(acts)
    assert s.n_closed == 2
    assert s.capital == 100
    assert s.pnl == 25
    assert abs(s.roi - 0.25) < 1e-9
    assert abs(s.hit_rate - 0.5) < 1e-9


# --------------------------------------------------------------------------- #
# select_copy_targets — filtering & ranking
# --------------------------------------------------------------------------- #

def test_select_copy_targets_applies_reliability_filters():
    scored = {
        "0xhigh_roi_low_sample": WalletScore(capital=6000, pnl=3000, n_closed=4, wins=4),
        "0xreliable_good": WalletScore(capital=8000, pnl=1600, n_closed=20, wins=14),
        "0xreliable_mid": WalletScore(capital=9000, pnl=450, n_closed=30, wins=16),
        "0xtoo_small": WalletScore(capital=1000, pnl=900, n_closed=12, wins=10),
    }
    picks = select_copy_targets(scored, min_capital=5000, min_closed=10, top_k=10)
    addrs = [p.address for p in picks]
    # low-sample (n<10) and too-small-capital excluded
    assert "0xhigh_roi_low_sample" not in addrs
    assert "0xtoo_small" not in addrs
    # ranked by ROI: good (20%) before mid (5%)
    assert addrs == ["0xreliable_good", "0xreliable_mid"]


def test_select_copy_targets_top_k_cap():
    scored = {
        f"0x{i}": WalletScore(capital=10000, pnl=100 * i, n_closed=15, wins=8)
        for i in range(1, 6)
    }
    picks = select_copy_targets(scored, top_k=2)
    assert len(picks) == 2
    # highest pnl/roi first
    assert picks[0].address == "0x5"
