"""Tests for trader_scoring — the copy-target selection logic (Strategy 1b)."""

from __future__ import annotations

from src.copy_trading.trader_scoring import (
    MarketResult,
    WalletMetrics,
    WalletScore,
    classify_market,
    compute_wallet_metrics,
    realized_market_results,
    score_wallet,
    select_copy_targets,
    select_targets,
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


# --------------------------------------------------------------------------- #
# WalletMetrics — robust scoring (t-stat, concentration, recency)
# --------------------------------------------------------------------------- #

def test_metrics_tstat_rewards_consistency():
    steady = WalletMetrics(capital=1000, pnl=300, n_closed=10, pnls=[30] * 10)
    lucky = WalletMetrics(capital=1000, pnl=300, n_closed=10,
                          pnls=[-20] * 9 + [480])  # same total, one big hit
    assert steady.tstat > lucky.tstat
    # both have the same raw ROI
    assert abs(steady.roi - lucky.roi) < 1e-9


def test_metrics_concentration():
    spread = WalletMetrics(pnls=[10, 10, 10, 10])
    assert abs(spread.concentration - 0.25) < 1e-9
    onebet = WalletMetrics(pnls=[-5, -5, 100])
    assert onebet.concentration == 1.0  # all gross profit from one market


def test_metrics_recency_requires_recent_profit():
    ok = WalletMetrics(pnl=20, early_pnl=10, late_pnl=10, early_n=3, late_n=3)
    assert ok.recency_ok
    went_cold = WalletMetrics(pnl=5, early_pnl=40, late_pnl=-35, early_n=3, late_n=4)
    assert not went_cold.recency_ok


def test_compute_wallet_metrics_window_and_split():
    acts = [
        _trade("A", 0, "BUY", 100, 40, 1000), _redeem("A", 100, 1500),   # +60 early
        _trade("B", 0, "BUY", 100, 50, 8000),
        _trade("B", 0, "SELL", 100, 80, 8500),                            # +30 late
    ]
    m = compute_wallet_metrics(acts, start_ts=0, end_ts=10000, recency_split_ts=5000)
    assert m.n_closed == 2
    assert m.early_n == 1 and m.late_n == 1
    assert m.early_pnl == 60 and m.late_pnl == 30


def test_select_targets_robust_filters_then_ranks_by_tstat():
    scored = {
        "0xconsistent": WalletMetrics(capital=8000, pnl=800, n_closed=20,
                                      wins=14, pnls=[40] * 20,
                                      early_pnl=400, late_pnl=400, early_n=10, late_n=10),
        "0xonebet": WalletMetrics(capital=8000, pnl=2000, n_closed=20, wins=5,
                                  pnls=[-20] * 19 + [2380],  # huge ROI, all one bet
                                  early_pnl=2380, late_pnl=-380, early_n=10, late_n=10),
        "0xcold": WalletMetrics(capital=8000, pnl=100, n_closed=20, wins=10,
                                pnls=[20] * 10 + [-15] * 10,
                                early_pnl=400, late_pnl=-300, early_n=10, late_n=10),
    }
    picks = select_targets(scored, method="robust", top_k=10)
    addrs = [p.address for p in picks]
    # one-bet (concentration=1.0) and cold (late_pnl<0) are filtered out
    assert addrs == ["0xconsistent"]


def test_select_targets_roi_method_matches_legacy_ranking():
    scored = {
        "0xa": WalletMetrics(capital=10000, pnl=2000, n_closed=15, pnls=[i for i in range(15)]),
        "0xb": WalletMetrics(capital=10000, pnl=500, n_closed=15, pnls=[i for i in range(15)]),
    }
    picks = select_targets(scored, method="roi", top_k=2)
    assert picks[0].address == "0xa"  # higher ROI first
