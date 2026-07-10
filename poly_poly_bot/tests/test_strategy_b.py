"""Strategy B — the borrowed-clock (instant-copy) paper book.

Covers the engine's fill-at-their-price mode, the cap-bind autopsy detail, the
runner's per-strategy blacklist provider, and B-regime exit mirroring (the
2026-07 A-vs-B race: two paper books, one lagged/censored, one instant)."""

from __future__ import annotations

import json
import os
import tempfile

from src.copy_trading.copy_paper import CopyPaperEngine, PaperCopyLedger
from src.copy_trading.copy_paper_runner import CopyPaperRunner


def _trade(copy_id, token, oi=0, their_price=0.50, their_usd=1000, target="0xT",
           category="sports"):
    return dict(copy_id=copy_id, target=target, condition_id="0xC", token_id=token,
                outcome_index=oi, category=category, their_price=their_price,
                their_usd=their_usd)


# --------------------------------------------------------------------------- #
# fill_at_their_price_bps — the borrowed-clock fill
# --------------------------------------------------------------------------- #

def test_borrowed_clock_fills_at_their_price_plus_bps():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        eng = CopyPaperEngine(
            led, detector=lambda: [_trade("t1", "TOK", their_price=0.50)],
            # a live book far above their price — must be IGNORED in this mode
            book_fetcher=lambda t: [(0.90, 10000)],
            resolver=lambda c: None, max_copy_usd=50,
            fill_at_their_price_bps=100,
        )
        s = eng.run_cycle(now=1)
        assert s.opened == 1
        p = led.open_positions()[0]
        assert abs(p.entry_price - 0.505) < 1e-9   # 0.50 * 1.01
        assert p.drag_bps == 100
        assert abs(p.spent - 50.0) < 1e-9
        assert abs(p.shares - 50.0 / 0.505) < 1e-9


def test_borrowed_clock_zero_bps_is_exactly_their_price():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        eng = CopyPaperEngine(
            led, detector=lambda: [_trade("t1", "TOK", their_price=0.43)],
            book_fetcher=lambda t: [],          # even an EMPTY book fills
            resolver=lambda c: None, max_copy_usd=21,
            fill_at_their_price_bps=0,
        )
        s = eng.run_cycle(now=1)
        assert s.opened == 1 and s.skipped_unfilled == 0
        assert abs(led.open_positions()[0].entry_price - 0.43) < 1e-9


def test_borrowed_clock_price_capped_below_one():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        eng = CopyPaperEngine(
            led, detector=lambda: [_trade("t1", "TOK", their_price=0.999)],
            book_fetcher=lambda t: [], resolver=lambda c: None,
            fill_at_their_price_bps=500,
        )
        eng.run_cycle(now=1)
        assert led.open_positions()[0].entry_price <= 0.999


def test_borrowed_clock_zero_price_row_skipped_not_crash():
    # belt-and-braces: a malformed feed row (their_price=0) must be skipped as
    # unfilled, never zero-divide the cycle.
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        eng = CopyPaperEngine(
            led, detector=lambda: [_trade("t1", "TOK", their_price=0.0)],
            book_fetcher=lambda t: [], resolver=lambda c: None,
            fill_at_their_price_bps=100,
        )
        s = eng.run_cycle(now=1)
        assert s.opened == 0 and s.skipped_unfilled == 1


def test_default_engine_unchanged_walks_the_book():
    # No fill_at_their_price_bps -> legacy behaviour: the live book decides.
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        eng = CopyPaperEngine(
            led, detector=lambda: [_trade("t1", "TOK", their_price=0.50)],
            book_fetcher=lambda t: [(0.51, 10000)],
            resolver=lambda c: None,
        )
        eng.run_cycle(now=1)
        assert abs(led.open_positions()[0].entry_price - 0.51) < 1e-9


def test_borrowed_clock_resolution_economics():
    # win at their price: $50 at 0.50 -> 100 shares -> +$50; loss -> -$50
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        resolved = {}
        eng = CopyPaperEngine(
            led, detector=lambda: [_trade("t1", "TOK", their_price=0.50, oi=0)],
            book_fetcher=lambda t: [], resolver=lambda c: resolved.get(c),
            max_copy_usd=50, fill_at_their_price_bps=0,
        )
        eng.run_cycle(now=1)
        resolved["0xC"] = 0
        s = eng.run_cycle(now=2)
        assert s.resolved == 1
        assert abs(led.closed_positions()[0].pnl - 50.0) < 1e-9


# --------------------------------------------------------------------------- #
# cap-bind autopsy detail
# --------------------------------------------------------------------------- #

def test_slate_cap_binds_carry_who_and_which_cap():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        feed = [_trade("t1", "A"), _trade("t2", "B"), _trade("t3", "C")]
        eng = CopyPaperEngine(
            led, detector=lambda: feed, book_fetcher=lambda t: [(0.50, 10000)],
            resolver=lambda c: None, max_copies_per_wallet_day=2,
        )
        s = eng.run_cycle(now=1)
        assert s.opened == 2 and s.skipped_slate_cap == 1
        assert s.slate_cap_binds == [("0xT", "sports", "wallet-day")]


def test_category_cap_bind_detail():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        feed = [_trade("t1", "A", target="0x1"), _trade("t2", "B", target="0x2")]
        eng = CopyPaperEngine(
            led, detector=lambda: feed, book_fetcher=lambda t: [(0.50, 10000)],
            resolver=lambda c: None, max_copies_per_category_day=1,
        )
        s = eng.run_cycle(now=1)
        assert s.skipped_slate_cap == 1
        assert s.slate_cap_binds == [("0x2", "sports", "category-day")]


# --------------------------------------------------------------------------- #
# per-strategy blacklist provider + B exit mirroring
# --------------------------------------------------------------------------- #

def _watchlist(tmp, wallets):
    p = os.path.join(tmp, "wl.json")
    with open(p, "w") as f:
        json.dump({"targets": [{"wallet": w} for w in wallets]}, f)
    return p


def test_runner_blacklist_provider_scopes_the_blacklist():
    with tempfile.TemporaryDirectory() as d:
        wl = _watchlist(d, ["0xAAA", "0xBBB"])
        r = CopyPaperRunner(
            ledger_path=os.path.join(d, "l.jsonl"), watchlist_path=wl,
            blacklist_provider=lambda: {"0xaaa"},
        )
        assert r.wallets() == ["0xBBB"]


def test_runner_default_blacklist_still_global(monkeypatch):
    from src.copy_trading import copy_paper_runner as cpr
    with tempfile.TemporaryDirectory() as d:
        wl = _watchlist(d, ["0xAAA", "0xBBB"])
        monkeypatch.setattr(cpr.promotion_state, "active_blacklist",
                            lambda: {"0xbbb"})
        r = CopyPaperRunner(ledger_path=os.path.join(d, "l.jsonl"),
                            watchlist_path=wl)
        assert r.wallets() == ["0xAAA"]


# --------------------------------------------------------------------------- #
# cross-strategy routing (A exits -> B extras)
# --------------------------------------------------------------------------- #

def _b_ledger(tmp_path, wallet="0xW", n=6, pnl=10.0):
    p = tmp_path / "ledger_b.jsonl"
    rows = [dict(copy_id=f"c{i}", target=wallet, condition_id=f"m{i}",
                 token_id=f"t{i}", outcome_index=0, category="sports",
                 their_price=0.5, entry_price=0.5, shares=100, spent=50,
                 drag_bps=0, opened_ts=1.0, closed=True, won=pnl > 0, pnl=pnl,
                 closed_ts=2.0) for i in range(n)]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return str(p)


def test_seed_extras_creates_once(tmp_path):
    from src.copy_trading import cross_route
    path = str(tmp_path / "extra.json")
    assert cross_route.seed_extras(path, "0xAAA, 0xBBB", now=5.0) is True
    targets = json.load(open(path))["targets"]
    assert [t["wallet"] for t in targets] == ["0xAAA", "0xBBB"]
    assert all(t["source"] == "seed" for t in targets)
    # second call is a no-op — cross-routed history must survive restarts
    assert cross_route.seed_extras(path, "0xCCC", now=6.0) is False
    assert len(json.load(open(path))["targets"]) == 2


def test_route_to_b_replay_fit(tmp_path):
    from src.copy_trading import cross_route
    extras = str(tmp_path / "extra.json")
    routed, why = cross_route.route_to_b(
        "0xGOOD", extras_path=extras, b_ledger_path=str(tmp_path / "none.jsonl"),
        reason="A auto-demote", replay_n=50, replay_roi=0.09,
        watchlist_entry={"approved_categories": ["sports"], "median_usd": 800.0},
        now=10.0)
    assert routed and why == "replay-fit"
    t = json.load(open(extras))["targets"][0]
    assert t["wallet"] == "0xGOOD" and t["source"] == "cross-route"
    assert t["approved_categories"] == ["sports"] and t["median_usd"] == 800.0
    # idempotent
    routed2, why2 = cross_route.route_to_b(
        "0xgood", extras_path=extras, b_ledger_path=str(tmp_path / "none.jsonl"),
        reason="again", replay_n=50, replay_roi=0.09, now=11.0)
    assert not routed2 and why2 == "already routed"


def test_route_to_b_rejects_replay_negative_without_b_record(tmp_path):
    from src.copy_trading import cross_route
    extras = str(tmp_path / "extra.json")
    routed, why = cross_route.route_to_b(
        "0xBAD", extras_path=extras, b_ledger_path=str(tmp_path / "none.jsonl"),
        reason="cull", replay_n=112, replay_roi=-0.058, now=10.0)
    assert not routed and "not B-fit" in why


def test_route_to_b_accepts_on_positive_b_record(tmp_path):
    from src.copy_trading import cross_route
    extras = str(tmp_path / "extra.json")
    ledger = _b_ledger(tmp_path, wallet="0xW", n=6, pnl=10.0)
    routed, why = cross_route.route_to_b(
        "0xW", extras_path=extras, b_ledger_path=ledger,
        reason="cull", replay_n=0, replay_roi=0.0, now=10.0)
    assert routed and why == "B-record-fit"


def test_route_to_b_blocked_by_b_blacklist(tmp_path, monkeypatch):
    from src.copy_trading import cross_route, promotion_state as ps
    monkeypatch.setenv("COPY_BLACKLIST_STORE", str(tmp_path / "blacklist.json"))
    ps.clear_cache()
    ps.add_blacklist("0xGOOD", until=10_000, now=1.0, scope="b")
    routed, why = cross_route.route_to_b(
        "0xGOOD", extras_path=str(tmp_path / "extra.json"),
        b_ledger_path=str(tmp_path / "none.jsonl"),
        reason="demote", replay_n=50, replay_roi=0.09, now=5.0)
    assert not routed and "B-blacklisted" in why


def test_discovery_on_removed_hook_fires_per_removed_wallet(tmp_path):
    from src.copy_trading.discovery import DiscoveryConfig, Eval
    from src.copy_trading.discovery_runner import DiscoveryRunner
    cfg = DiscoveryConfig(min_capture_cents=1.5, min_tstat=10.0,
                          drop_capture_cents=1.0, watchlist_cap=5,
                          auto_remove=True)
    calls = []
    good = Eval(wallet="0xa", capture_cents=2.0, tstat=12.0, roi=0.5,
                hit_rate=0.6, n=20)
    r = DiscoveryRunner(
        config=cfg,
        watchlist_path=str(tmp_path / "wl.json"),
        state_path=str(tmp_path / "state.json"),
        notify=lambda _m: None,
        evaluate=lambda *a, **k: dict(calls_eval[0]),
        now=lambda: 1000.0,
        on_removed=lambda w, ev: calls.append((w, ev)),
    )
    calls_eval = [{"0xa": good, "0xdead": Eval(wallet="0xdead", capture_cents=2.0,
                                               tstat=12.0, roi=0.5, hit_rate=0.6,
                                               n=20)}]
    r.run_once()          # both qualify
    assert calls == []
    calls_eval[0] = {"0xa": good,
                     "0xdead": Eval(wallet="0xdead", capture_cents=0.0, tstat=0.0,
                                    roi=0.0, hit_rate=0.0, n=20, copy_n=30,
                                    copy_roi=0.08)}
    r.run_once()          # 0xdead decays off -> hook fires with its Eval
    assert len(calls) == 1
    assert calls[0][0] == "0xdead"
    assert calls[0][1] is not None and calls[0][1].copy_roi == 0.08


# --------------------------------------------------------------------------- #
# per-strategy promotion state (scope="b")
# --------------------------------------------------------------------------- #

def test_promotion_state_scopes_are_independent(tmp_path, monkeypatch):
    from src.copy_trading import promotion_state as ps
    monkeypatch.setenv("PROMOTED_WALLETS_STORE", str(tmp_path / "promoted.json"))
    monkeypatch.setenv("COPY_BLACKLIST_STORE", str(tmp_path / "blacklist.json"))
    monkeypatch.setenv("PROMOTION_OFFERS_STORE", str(tmp_path / "offers.json"))
    ps.clear_cache()

    ps.add_blacklist("0xA", until=10_000, now=1.0)               # A store
    ps.add_blacklist("0xB", until=10_000, now=1.0, scope="b")    # B store
    assert ps.active_blacklist(now=2.0) == {"0xa"}
    assert ps.active_blacklist(now=2.0, scope="b") == {"0xb"}
    assert ps.blacklist_path("b").endswith("blacklist_b.json")

    ps.add_promoted("0xP", tier="1b", now=1.0, scope="b")
    assert ps.promoted_set(scope="b") == {"0xp"}
    assert ps.promoted_set() == set()

    ps.record_offer("0xO", status="offered", now=1.0, scope="b")
    assert ps.offer_status("0xO", scope="b") == "offered"
    assert ps.offer_status("0xO") is None


def test_governance_cycle_writes_scoped_stores(tmp_path, monkeypatch):
    from src.copy_trading import governance, promotion_state as ps
    monkeypatch.setenv("COPY_BLACKLIST_STORE", str(tmp_path / "blacklist.json"))
    monkeypatch.setenv("PROMOTION_OFFERS_STORE", str(tmp_path / "offers.json"))
    monkeypatch.setenv("PROMOTED_WALLETS_STORE", str(tmp_path / "promoted.json"))
    monkeypatch.setenv("COPY_RETIRED_STORE", str(tmp_path / "retired.json"))
    ps.clear_cache()

    from src.copy_trading.copy_paper import PaperPosition
    # a proven loser: 15 settled, all lost
    losers = [
        PaperPosition(copy_id=f"c{i}", target="0xLOSER", condition_id=f"m{i}",
                      token_id=f"t{i}", outcome_index=0, category="sports",
                      their_price=0.5, entry_price=0.5, shares=100, spent=50,
                      drag_bps=0, opened_ts=1.0, closed=True, won=False,
                      pnl=-50.0, closed_ts=2.0)
        for i in range(15)
    ]
    governance.run_governance_cycle(
        losers, now=100.0, promote_min_n=15, promote_min_roi=0.10,
        promote_min_tstat=0.0, promote_min_second_half_roi=-1.0,
        promote_min_conditions=0, promote_min_categories=0,
        demote_min_n=15, demote_max_roi=-0.10, demote_min_abs_loss=10.0,
        demote_max_wilson=1.0, cooldown_s=1000.0, default_tier="1b",
        send_offer=lambda o: True, state_scope="b",
    )
    assert ps.active_blacklist(now=200.0, scope="b") == {"0xloser"}
    assert ps.active_blacklist(now=200.0) == set()   # A store untouched


# --------------------------------------------------------------------------- #
# strategy_compare — the race's verdict machinery
# --------------------------------------------------------------------------- #

def _ledger_file(tmp_path, name, rows):
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return str(p)


def _row(target, pnl, opened_ts, closed_ts=None, closed=True, spent=50.0, i=[0]):
    i[0] += 1
    return dict(copy_id=f"c{i[0]}", target=target, condition_id=f"m{i[0]}",
                token_id=f"t{i[0]}", outcome_index=0, category="sports",
                their_price=0.5, entry_price=0.5, shares=spent / 0.5, spent=spent,
                drag_bps=0, opened_ts=opened_ts, closed=closed, won=pnl > 0,
                pnl=pnl if closed else 0.0,
                closed_ts=closed_ts if closed_ts is not None else opened_ts + 100)


def test_compare_era_windows_a_and_routes_wallets(tmp_path, monkeypatch):
    from src.copy_trading.strategy_compare import compare
    monkeypatch.setenv("PROMOTED_WALLETS_STORE", str(tmp_path / "p.json"))
    monkeypatch.setenv("COPY_BLACKLIST_STORE", str(tmp_path / "bl.json"))
    monkeypatch.setenv("PROMOTION_OFFERS_STORE", str(tmp_path / "o.json"))
    from src.copy_trading import promotion_state as ps
    ps.clear_cache()

    T = 1_000_000.0
    a_rows = (
        [_row("0xOLD", 10.0, T - 5000) for _ in range(3)]      # pre-era: excluded
        + [_row("0xX", 10.0, T + 100 + k) for k in range(6)]   # in-era, A-positive
        + [_row("0xY", -50.0, T + 200 + k) for k in range(6)]  # in-era, A-negative
    )
    b_rows = (
        [_row("0xY", 20.0, T + k) for k in range(6)]           # B-positive (era anchor)
        + [_row("0xX", -50.0, T + 300 + k) for k in range(6)]  # B-negative
    )
    a_path = _ledger_file(tmp_path, "a.jsonl", a_rows)
    b_path = _ledger_file(tmp_path, "b.jsonl", b_rows)

    cmp_ = compare(a_path, b_path, b_slippage_bps=100, now=T + 4000)
    assert cmp_["era_start"] == T
    assert cmp_["a"]["n_settled"] == 12          # era-windowed, 0xOLD excluded
    assert cmp_["a_all_time"]["n_settled"] == 15
    assert cmp_["b"]["n_settled"] == 12
    routes = {r["wallet"]: r["route"] for r in cmp_["routing"]}
    assert routes["0xx"] == "A"                  # +A, -B
    assert routes["0xy"] == "B"                  # -A, +B
    assert cmp_["validity"]["valid"] is True     # opens spread inside a 4000s era


def test_compare_validity_voids_on_48h_starved_book(tmp_path):
    from src.copy_trading.strategy_compare import compare
    T = 1_000_000.0
    a_path = _ledger_file(tmp_path, "a.jsonl",
                          [_row("0xX", 10.0, T + 10)])          # then silence
    b_path = _ledger_file(tmp_path, "b.jsonl",
                          [_row("0xY", 10.0, T + k * 3600) for k in range(72)])
    cmp_ = compare(a_path, b_path, now=T + 72 * 3600)           # 3-day era
    v = cmp_["validity"]
    assert v["valid"] is False
    assert any("book A" in r for r in v["reasons"])
    assert v["extend_days"] >= 2.0


def test_compare_no_era_when_b_empty(tmp_path):
    from src.copy_trading.strategy_compare import compare, format_verdict
    a_path = _ledger_file(tmp_path, "a.jsonl", [_row("0xX", 10.0, 100.0)])
    cmp_ = compare(a_path, str(tmp_path / "missing.jsonl"), now=200.0)
    assert cmp_["era_start"] is None
    assert cmp_["validity"]["valid"] is False
    format_verdict(cmp_)          # must render without raising


def test_snapshot_and_verdict_carry_slippage_assumption(tmp_path):
    from src.copy_trading.strategy_compare import (
        compare, format_snapshot, format_verdict)
    T = 1_000_000.0
    a_path = _ledger_file(tmp_path, "a.jsonl", [_row("0xX", 10.0, T + 5)])
    b_path = _ledger_file(tmp_path, "b.jsonl", [_row("0xX", 10.0, T)])
    cmp_ = compare(a_path, b_path, b_slippage_bps=100, now=T + 1000)
    assert "+100bps" in format_snapshot(cmp_)
    assert "+100bps" in format_verdict(cmp_)


def test_aggregate_paper_b_groups_under_one_track(tmp_path):
    from src.copy_trading.copy_paper import PaperPosition
    from src.copy_trading.pnl_unified import PAPER_B_LABEL, aggregate_paper_b
    pos = [PaperPosition(copy_id=f"c{i}", target="0xW", condition_id=f"m{i}",
                         token_id=f"t{i}", outcome_index=0, category="sports",
                         their_price=0.5, entry_price=0.5, shares=100, spent=50,
                         drag_bps=0, opened_ts=1.0, closed=True, won=True,
                         pnl=50.0, closed_ts=2.0, strategy="B")
           for i in range(3)]
    out = aggregate_paper_b(pos)
    assert len(out) == 1
    wp = out[0]
    assert wp.strategies == (PAPER_B_LABEL,)
    assert wp.realized_pnl == 150.0 and wp.n_closed == 3


def test_borrowed_clock_exit_mirrors_their_sell_price():
    # In B mode the runner must NOT wire a bid fetcher: the exit fills at the
    # target's own SELL price, one regime end to end.
    with tempfile.TemporaryDirectory() as d:
        wl = _watchlist(d, ["0xT"])
        cycle = {"n": 0}

        def detector(*a, **k):
            def detect():
                cycle["n"] += 1
                if cycle["n"] == 1:
                    return [_trade("t1", "TOK", their_price=0.50)]
                return []
            return detect

        def exit_detector(*a, **k):
            def detect():
                if cycle["n"] < 2:
                    return []
                return [dict(target="0xT", token_id="TOK", their_price=0.70)]
            return detect

        r = CopyPaperRunner(
            ledger_path=os.path.join(d, "l.jsonl"), watchlist_path=wl,
            fill_at_their_price_bps=0,
            detector_factory=detector,
            exit_detector_factory=exit_detector,
            book_fetcher=lambda t: [],
            bid_fetcher=lambda t: [(0.99, 10000)],   # must be ignored in B mode
            resolver=lambda c: None,
            max_copy_usd=50,
        )
        s1 = r.run_once()
        assert s1.opened == 1
        s2 = r.run_once()
        assert s2.exited == 1
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        p = led.closed_positions()[0]
        assert p.exited_early is True
        # 100 shares bought at 0.50, sold at THEIR 0.70 (not our 0.99 bid)
        assert abs(p.pnl - (100 * 0.70 - 50.0)) < 1e-6
