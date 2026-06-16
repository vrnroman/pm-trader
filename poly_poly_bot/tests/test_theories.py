"""Independent strategy theories — each fires on its own hypothesis, OR'd.

These pin that each detector flags the wallet it's meant to and stays silent
otherwise, that theories are independent (one can fire without the others), and
that evaluate_all returns calibratable, reasoned flags.
"""

from __future__ import annotations

from src.copy_trading.theories import REGISTRY, TheoryFlag, evaluate_all
from src.copy_trading.trader_scoring import MarketResult
from src.copy_trading.wallet_context import (
    Buy,
    CurveMetrics,
    RoundTrip,
    WalletContext,
)
from src.copy_trading.trader_scoring import WalletMetrics


def _ctx(**kw) -> WalletContext:
    base = dict(wallet="0xw", now=10_000.0)
    base.update(kw)
    return WalletContext(**base)


def _metrics(roi=0.0, tstat=0.0, n_closed=0, capital=0.0, hit=0.0,
             conc=1.0, pnls=None):
    m = WalletMetrics(capital=capital, pnl=roi * capital, n_closed=n_closed,
                      wins=int(hit * n_closed), pnls=pnls or [])
    return m


def test_1b_skill_fires_on_tstat_and_filters():
    m = WalletMetrics(capital=20000, pnl=8000, n_closed=15, wins=10,
                      pnls=[100, 200, 300, 150, 250] * 3)
    flags = evaluate_all(_ctx(metrics=m), enabled={"1b"})
    assert len(flags) == 1 and flags[0].theory == "1b"
    assert "consistent skill" in flags[0].reason
    # too few closed -> no flag
    m2 = WalletMetrics(capital=20000, pnl=8000, n_closed=3, wins=2, pnls=[100, 200, 300])
    assert evaluate_all(_ctx(metrics=m2), enabled={"1b"}) == []


def test_1e_longshot_calibration_edge():
    # 10 longshot buys @ 0.20; 6 resolved YES (60%) vs 20% implied -> +40% edge
    buys = [Buy("m%d" % i, 0, "t", 0.20, 500, ts=0, title="", category="other",
                won=(i < 6)) for i in range(10)]
    flags = evaluate_all(_ctx(buys=buys), enabled={"1e"})
    assert len(flags) == 1 and flags[0].theory == "1e"
    assert "longshot calibration" in flags[0].reason
    # if they resolve at the implied rate (2/10=20%), no edge
    buys_fair = [Buy("m%d" % i, 0, "t", 0.20, 500, ts=0, title="", category="other",
                     won=(i < 2)) for i in range(10)]
    assert evaluate_all(_ctx(buys=buys_fair), enabled={"1e"}) == []


def test_1f_swing_fires_on_profitable_round_trips():
    trips = [RoundTrip("m%d" % i, "other", entry_price=0.30, exit_price=0.45,
                       shares=100, pnl=15, entry_ts=0, exit_ts=3600, held_s=3600)
             for i in range(10)]
    flags = evaluate_all(_ctx(round_trips=trips), enabled={"1f"})
    assert len(flags) == 1 and flags[0].theory == "1f"
    assert "early-exit swing" in flags[0].reason


def test_1d_steady_compounder_curve():
    curve = CurveMetrics(n=30, net_pnl=50000, peak=60000, max_drawdown=6000,
                         max_drawdown_frac=0.1, up_ratio=0.7, slope_per_period=100,
                         sharpe=1.2)
    flags = evaluate_all(_ctx(curve=curve), enabled={"1d"})
    assert len(flags) == 1 and flags[0].theory == "1d"
    # a spiky, deep-drawdown curve is rejected
    bad = CurveMetrics(n=30, net_pnl=50000, max_drawdown_frac=0.8, up_ratio=0.4, sharpe=0.05)
    assert evaluate_all(_ctx(curve=bad), enabled={"1d"}) == []


def test_1g_category_specialist():
    closed = ([MarketResult("s%d" % i, "sports", capital=1000, pnl=400, closed=True, last_ts=0)
               for i in range(12)]
              + [MarketResult("o%d" % i, "other", capital=1000, pnl=-50, closed=True, last_ts=0)
                 for i in range(3)])
    flags = evaluate_all(_ctx(closed=closed), enabled={"1g"})
    assert len(flags) == 1 and flags[0].theory == "1g" and "sports specialist" in flags[0].reason


def test_1a_news_early_requires_early_nontail_geo_bet():
    early = Buy("m1", 0, "t", 0.40, 5000, ts=0, title="Russia ceasefire by June?",
                category="research", won=True, hours_before_resolution=72)
    assert evaluate_all(_ctx(buys=[early]), enabled={"1a"})[0].theory == "1a"
    # last-minute (settlement-lag) -> rejected
    late = Buy("m1", 0, "t", 0.40, 5000, ts=0, title="Russia ceasefire by June?",
               category="research", won=True, hours_before_resolution=2)
    assert evaluate_all(_ctx(buys=[late]), enabled={"1a"}) == []


def test_1c_and_1h_use_capture_and_lead():
    # low-variance positive per-market PnL -> high t-stat (1c needs tstat>=10)
    skilled = WalletMetrics(pnls=[100, 105, 95, 100, 102] * 4)
    ctx = _ctx(capture_cents=2.5, lead_cents=6.0, capture_hit_rate=0.7, n_capture=20,
               metrics=skilled)
    by = {f.theory for f in evaluate_all(ctx, enabled={"1c", "1h"})}
    assert by == {"1c", "1h"}


def test_1i_whale_and_1j_sniper():
    m = WalletMetrics(capital=120000, pnl=6000, n_closed=40, wins=28,
                      pnls=[100, -50, 120, 80, -30] * 8)
    assert evaluate_all(_ctx(metrics=m), enabled={"1i"})[0].theory == "1i"
    young = [Buy("m1", 0, "t", 0.4, 5000, ts=0, title="", category="other")]
    assert evaluate_all(_ctx(buys=young), enabled={"1j"})[0].theory == "1j"


def test_theories_are_independent_and_ranked():
    # a wallet that trips multiple theories returns multiple flags, strongest first
    m = WalletMetrics(capital=120000, pnl=24000, n_closed=40, wins=30,
                      pnls=[300, 200, 400, 250, 350] * 8)
    flags = evaluate_all(_ctx(metrics=m))
    ids = {f.theory for f in flags}
    assert {"1b", "1i"} <= ids                  # both skill and whale fire
    scores = [f.score for f in flags]
    assert scores == sorted(scores, reverse=True)
    assert all(isinstance(f, TheoryFlag) and f.reason for f in flags)


def test_registry_metadata_complete():
    assert set(REGISTRY) == {f"1{c}" for c in "abcdefghij"}
    for t in REGISTRY.values():
        assert t.defaults and t.desc and callable(t.fn)
