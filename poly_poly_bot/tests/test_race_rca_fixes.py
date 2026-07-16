"""2026-07-16 "trading in minus" RCA fixes.

Covers the four structural changes that came out of the A-vs-B race-week RCA:

  * per-(wallet, event) concurrent-exposure cap — correlated same-match props
    (0xa6fa: 3-4 props on ONE game, -$345 across both books) passed the
    per-wallet-DAY slate cap because the day cap can't see that they settle
    together;
  * confidence-tiered stake, downward only — a band=low n=6 LLM admit was
    staked like a proven wallet;
  * LLM-gate bounded retry + defer — intermittent bare `claude -p exit 1`
    fail-opened (admitted unvetted) six times in four days;
  * legacy-A P&L segregation — the 2026-07-11 preview-realization sweep booked
    61 dead MAY-era positions (-$575) into the same headline net as the live
    strategies.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

from src.copy_trading.copy_paper import (
    CopyPaperEngine,
    PaperCopyLedger,
    PaperPosition,
)
from src.copy_trading.gate_history import latest_band_by_wallet
from src.copy_trading.pnl_unified import (
    LEGACY_A,
    UNTAGGED_A,
    aggregate_system_a,
    build_unified,
)


def _trade(copy_id, token, target="0xT", slug="event-1", their_price=0.50,
           their_usd=1000, category="sports"):
    return dict(copy_id=copy_id, target=target, condition_id=f"c-{token}",
                token_id=token, outcome_index=0, category=category,
                their_price=their_price, their_usd=their_usd, slug=slug)


def _engine(led, feed, **kw):
    return CopyPaperEngine(
        led, detector=lambda: feed,
        book_fetcher=lambda t: [(0.50, 10000)],
        resolver=lambda c: None, max_copy_usd=50, **kw)


# --------------------------------------------------------------------------- #
# per-(wallet, event) cap
# --------------------------------------------------------------------------- #

def test_event_cap_blocks_second_prop_on_same_event():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        feed = [_trade("t1", "T1", slug="fra-esp"),
                _trade("t2", "T2", slug="fra-esp")]   # second prop, same match
        s = _engine(led, feed, max_copies_per_wallet_event=1).run_cycle(now=1e9)
        assert s.opened == 1
        assert s.skipped_event_cap == 1
        assert ("0xT", "sports", "wallet-event") in s.slate_cap_binds


def test_event_cap_allows_distinct_events():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        feed = [_trade("t1", "T1", slug="fra-esp"),
                _trade("t2", "T2", slug="eng-arg")]
        s = _engine(led, feed, max_copies_per_wallet_event=1).run_cycle(now=1e9)
        assert s.opened == 2 and s.skipped_event_cap == 0


def test_event_cap_is_per_wallet():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        feed = [_trade("t1", "T1", target="0xA", slug="fra-esp"),
                _trade("t2", "T2", target="0xB", slug="fra-esp")]
        s = _engine(led, feed, max_copies_per_wallet_event=1).run_cycle(now=1e9)
        assert s.opened == 2 and s.skipped_event_cap == 0


def test_event_cap_seeded_from_open_ledger_positions():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        led.add(PaperPosition(
            copy_id="old", target="0xT", condition_id="c0", token_id="T0",
            outcome_index=0, category="sports", their_price=0.5,
            entry_price=0.5, shares=10, spent=5.0, drag_bps=0,
            opened_ts=1.0, slug="fra-esp"))
        s = _engine(led, [_trade("t1", "T1", slug="fra-esp")],
                    max_copies_per_wallet_event=1).run_cycle(now=1e9)
        assert s.opened == 0 and s.skipped_event_cap == 1


def test_event_cap_slot_freed_after_resolution():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        led.add(PaperPosition(
            copy_id="old", target="0xT", condition_id="c0", token_id="T0",
            outcome_index=0, category="sports", their_price=0.5,
            entry_price=0.5, shares=10, spent=5.0, drag_bps=0,
            opened_ts=1.0, slug="fra-esp", closed=True, won=True, pnl=1.0,
            closed_ts=2.0))
        s = _engine(led, [_trade("t1", "T1", slug="fra-esp")],
                    max_copies_per_wallet_event=1).run_cycle(now=1e9)
        assert s.opened == 1 and s.skipped_event_cap == 0


def test_event_cap_ignores_empty_slug_and_off_by_default():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        # empty slug: can't group -> uncapped even with the cap on
        feed = [_trade("t1", "T1", slug=""), _trade("t2", "T2", slug="")]
        s = _engine(led, feed, max_copies_per_wallet_event=1).run_cycle(now=1e9)
        assert s.opened == 2 and s.skipped_event_cap == 0
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        # cap off (None, the default): same-event stacking allowed (legacy)
        feed = [_trade("t1", "T1", slug="fra-esp"),
                _trade("t2", "T2", slug="fra-esp")]
        s = _engine(led, feed).run_cycle(now=1e9)
        assert s.opened == 2 and s.skipped_event_cap == 0


# --------------------------------------------------------------------------- #
# downward-only stake fraction
# --------------------------------------------------------------------------- #

def test_stake_frac_halves_low_confidence_wallet():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        s = _engine(led, [_trade("t1", "T1")],
                    stake_frac={"0xt": 0.5}).run_cycle(now=1e9)
        assert s.opened == 1
        pos = next(iter(led.positions.values()))
        assert abs(pos.spent - 25.0) < 1e-6      # 50 * 0.5


def test_stake_frac_never_raises_and_defaults_full():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        # a >1 multiplier is clamped to 1.0 (downward only) and an absent
        # wallet stakes full size
        feed = [_trade("t1", "T1", target="0xClamped"),
                _trade("t2", "T2", target="0xAbsent", slug="e2")]
        s = _engine(led, feed,
                    stake_frac={"0xclamped": 2.0}).run_cycle(now=1e9)
        assert s.opened == 2
        spent = {p.target: p.spent for p in led.positions.values()}
        assert abs(spent["0xClamped"] - 50.0) < 1e-6
        assert abs(spent["0xAbsent"] - 50.0) < 1e-6


def test_already_copied_feed_reemit_is_counted():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        eng = _engine(led, [_trade("t1", "T1")])
        eng.run_cycle(now=1e9)
        s2 = eng.run_cycle(now=1e9 + 60)         # feed re-emits the same trade
        assert s2.skipped_already_copied == 1 and s2.opened == 0


# --------------------------------------------------------------------------- #
# gate-history band lookup (feeds the runner's stake map)
# --------------------------------------------------------------------------- #

def test_latest_band_by_wallet_last_decided_row_wins():
    rows = [
        {"wallet": "0xA", "confidence_band": "low"},
        {"wallet": "0xA", "confidence_band": "high"},          # newer -> wins
        {"wallet": "0xB", "confidence_band": "low", "requeued": True},  # provisional
        {"wallet": "0xC"},                                     # pre-band row
    ]
    bands = latest_band_by_wallet(rows)
    assert bands == {"0xa": "high"}


def test_runner_stake_map_respects_band_and_settled_floor():
    from src.copy_trading.copy_paper_runner import CopyPaperRunner
    with tempfile.TemporaryDirectory() as d:
        gh = os.path.join(d, "gate-history.jsonl")
        with open(gh, "w") as f:
            f.write('{"wallet": "0xLow", "confidence_band": "low"}\n')
            f.write('{"wallet": "0xProven", "confidence_band": "low"}\n')
            f.write('{"wallet": "0xHigh", "confidence_band": "high"}\n')
        runner = CopyPaperRunner(
            ledger_path=os.path.join(d, "l.jsonl"), wallets=["0xLow"],
            low_conf_stake_frac=0.5, low_conf_until_n=2, gate_history_path=gh)
        # 0xProven already has 2 settled copies -> graduates to full stake
        for i in range(2):
            runner.ledger.add(PaperPosition(
                copy_id=f"p{i}", target="0xProven", condition_id=f"c{i}",
                token_id=f"T{i}", outcome_index=0, category="sports",
                their_price=0.5, entry_price=0.5, shares=10, spent=5.0,
                drag_bps=0, opened_ts=1.0, closed=True, won=True, pnl=1.0,
                closed_ts=2.0))
        m = runner._stake_frac_map()
        assert m == {"0xlow": 0.5}


def test_runner_stake_map_off_when_unconfigured():
    from src.copy_trading.copy_paper_runner import CopyPaperRunner
    with tempfile.TemporaryDirectory() as d:
        runner = CopyPaperRunner(
            ledger_path=os.path.join(d, "l.jsonl"), wallets=["0xW"])
        assert runner._stake_frac_map() is None


# --------------------------------------------------------------------------- #
# detector-funnel stats reach the cycle summary
# --------------------------------------------------------------------------- #

def test_runner_attaches_detector_stats_to_summary():
    from src.copy_trading.copy_paper_runner import CopyPaperRunner

    def detector_factory(wallets, max_age_s, min_usd, flagged_by_map=None, **kw):
        def detect():
            detect.stats = {"rows": 3, "below_min_usd": 3, "emitted": 0}
            return []
        detect.stats = {}
        return detect

    with tempfile.TemporaryDirectory() as d:
        runner = CopyPaperRunner(
            ledger_path=os.path.join(d, "l.jsonl"), wallets=["0xW"],
            detector_factory=detector_factory,
            exit_detector_factory=lambda wallets, max_age_s: (lambda: []),
            book_fetcher=lambda t: [], resolver=lambda c: None)
        summary = runner.run_once()
        assert summary.detector_rejects == {"rows": 3, "below_min_usd": 3,
                                            "emitted": 0}


def test_feed_detector_counts_watched_rejects():
    from src.copy_trading.copy_paper_live import make_feed_detector

    class FakeFeed:
        def recent(self, floor, max_age_s):
            import time as _t
            now = _t.time()
            return [
                # watched, SELL -> not_buy
                {"proxyWallet": "0xW", "side": "SELL", "timestamp": now,
                 "price": 0.5, "usdcSize": 900, "transactionHash": "h1",
                 "asset": "T1"},
                # watched, BUY below min_usd
                {"proxyWallet": "0xW", "side": "BUY", "timestamp": now,
                 "price": 0.5, "usdcSize": 10, "transactionHash": "h2",
                 "asset": "T2"},
                # watched, copyable BUY -> emitted
                {"proxyWallet": "0xW", "side": "BUY", "timestamp": now,
                 "price": 0.5, "usdcSize": 900, "transactionHash": "h3",
                 "asset": "T3", "conditionId": "c3", "title": "M",
                 "eventSlug": "ev"},
                # NOT watched -> not counted at all
                {"proxyWallet": "0xZ", "side": "BUY", "timestamp": now,
                 "price": 0.5, "usdcSize": 900, "transactionHash": "h4",
                 "asset": "T4"},
            ]

    detect = make_feed_detector(["0xW"], max_age_s=3600, min_usd=500,
                                feed=FakeFeed())
    out = detect()
    assert len(out) == 1
    assert detect.stats["rows"] == 3
    assert detect.stats["not_buy"] == 1
    assert detect.stats["below_min_usd"] == 1
    assert detect.stats["emitted"] == 1


# --------------------------------------------------------------------------- #
# LLM gate: bounded retry, then DEFER (never silently fail-open)
# --------------------------------------------------------------------------- #

class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_cli_runner_defers_after_two_generic_failures(monkeypatch):
    from src.copy_trading import llm_review

    calls = []
    monkeypatch.setattr(llm_review.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(
        llm_review.subprocess, "run",
        lambda *a, **k: calls.append(1) or _Proc(returncode=1))
    res = llm_review._claude_cli_runner("p", model="m", timeout_s=5)
    assert res is llm_review.RATE_LIMITED     # deferred, NOT fail-open None
    assert len(calls) == 2                    # exactly one retry


def test_cli_runner_retry_recovers_on_second_attempt(monkeypatch):
    from src.copy_trading import llm_review

    ok = ('{"is_error": false, "subtype": "success", "result": "{}"}')
    procs = [_Proc(returncode=1), _Proc(returncode=0, stdout=ok)]
    monkeypatch.setattr(llm_review.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(llm_review.subprocess, "run",
                        lambda *a, **k: procs.pop(0))
    res = llm_review._claude_cli_runner("p", model="m", timeout_s=5)
    assert isinstance(res, dict) and res.get("subtype") == "success"


def test_cli_runner_defers_after_repeated_timeouts(monkeypatch):
    from src.copy_trading import llm_review

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=5)

    monkeypatch.setattr(llm_review.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(llm_review.subprocess, "run", boom)
    res = llm_review._claude_cli_runner("p", model="m", timeout_s=5)
    assert res is llm_review.RATE_LIMITED


def test_cli_runner_rate_limit_short_circuits_without_retry(monkeypatch):
    from src.copy_trading import llm_review

    calls = []
    monkeypatch.setattr(llm_review.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(
        llm_review.subprocess, "run",
        lambda *a, **k: calls.append(1) or _Proc(
            returncode=1, stderr="You've hit your monthly spend limit"))
    res = llm_review._claude_cli_runner("p", model="m", timeout_s=5)
    assert res is llm_review.RATE_LIMITED
    assert len(calls) == 1                    # limit -> no same-sweep retry


# --------------------------------------------------------------------------- #
# legacy-A P&L segregation
# --------------------------------------------------------------------------- #

def _row(pnl, cost, tier="", trader="", won=False):
    return {"pnl": pnl, "cost_basis": cost, "tier": tier,
            "trader_address": trader, "won": won}


def test_unattributed_rows_land_in_legacy_track():
    wallets = aggregate_system_a(
        [_row(-575.0, 575.0),                       # the 07-11 sweep shape
         _row(10.0, 20.0, tier="1b", trader="0xW", won=True)],
        open_positions=[])
    by_label = {lbl: w for w in wallets for lbl in w.strategies}
    assert LEGACY_A in by_label
    assert by_label[LEGACY_A].realized_pnl == -575.0
    assert by_label["A:1b"].realized_pnl == 10.0


def test_untagged_with_known_wallet_stays_untagged_not_legacy():
    wallets = aggregate_system_a(
        [_row(-5.0, 10.0, trader="0xKnown")], open_positions=[])
    labels = {lbl for w in wallets for lbl in w.strategies}
    assert labels == {UNTAGGED_A}


def test_legacy_track_sorts_last_and_totals_reconcile():
    wallets = aggregate_system_a(
        [_row(-575.0, 575.0),
         _row(10.0, 20.0, tier="1b", trader="0xW", won=True)],
        open_positions=[])
    unified = build_unified(wallets, [])
    assert unified.strategies[-1].label == LEGACY_A
    assert unified.strategies[-1].system == "A"
    assert abs(unified.total_realized - (-565.0)) < 1e-6   # nothing dropped
