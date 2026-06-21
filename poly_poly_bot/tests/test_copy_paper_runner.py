"""Tests for the in-bot paper-copy runner (Strategy 1b)."""

from __future__ import annotations

import json
import os
import tempfile
import threading

from src.copy_trading.copy_paper_runner import CopyPaperRunner


def _trade(copy_id="t1"):
    return dict(copy_id=copy_id, target="0xT", condition_id="0xC", token_id="TOK",
                outcome_index=0, category="research", their_price=0.50, their_usd=1000)


def _runner(tmp, wallets=None, watchlist_path=None, feed=None, on_cycle=None,
            exits=None, bid=None):
    feed = feed if feed is not None else [_trade()]
    return CopyPaperRunner(
        ledger_path=os.path.join(tmp, "l.jsonl"),
        watchlist_path=watchlist_path,
        wallets=wallets,
        detector_factory=lambda w, age, usd, fb=None: (lambda: feed),
        book_fetcher=lambda t: [(0.51, 10000)],
        resolver=lambda c: None,
        exit_detector_factory=lambda w, age: (lambda: exits or []),
        bid_fetcher=lambda t: (bid if bid is not None else []),
        on_cycle=on_cycle,
        cycle_interval_s=0,
    )


def test_exit_following_closes_open_copy_when_target_sells():
    with tempfile.TemporaryDirectory() as d:
        # cycle 1: open a copy of 0xT's BUY on TOK
        r = _runner(d, wallets=["0xT"])
        assert r.run_once().opened == 1
        # cycle 2: target sells TOK; no fresh buys -> we exit at the 0.60 bid
        r._detector_factory = lambda w, age, usd, fb=None: (lambda: [])
        r._exit_detector_factory = lambda w, age: (
            lambda: [{"target": "0xT", "token_id": "TOK", "their_price": 0.60}])
        r._bid_fetcher = lambda t: [(0.60, 5000)]
        s = r.run_once()
        assert s.exited == 1 and not r.ledger.open_positions()
        assert r.ledger.closed_positions()[0].exited_early is True


def test_run_once_opens_position_with_explicit_wallets():
    with tempfile.TemporaryDirectory() as d:
        r = _runner(d, wallets=["0xT"])
        s = r.run_once()
        assert s.opened == 1
        assert len(r.ledger.open_positions()) == 1


def test_run_once_noop_when_no_wallets():
    with tempfile.TemporaryDirectory() as d:
        r = _runner(d, wallets=[])
        s = r.run_once()
        assert s.detected == 0 and s.opened == 0


def test_wallets_loaded_from_watchlist_file():
    with tempfile.TemporaryDirectory() as d:
        wl = os.path.join(d, "wl.json")
        json.dump({"targets": [{"wallet": "0xAAA"}, {"wallet": "0xBBB"}]}, open(wl, "w"))
        r = _runner(d, watchlist_path=wl)
        assert r.wallets() == ["0xAAA", "0xBBB"]


def test_run_forever_stops_on_shutdown():
    with tempfile.TemporaryDirectory() as d:
        ev = threading.Event()

        # stop after the first cycle
        def stop(summary, ledger):
            ev.set()

        r = _runner(d, wallets=["0xT"], on_cycle=stop)
        r.run_forever(ev)  # must return promptly, not hang
        assert len(r.ledger.open_positions()) == 1


def test_runner_long_horizon_book_unions_watchlists_and_routes_by_horizon():
    # The S4 book watches BOTH watchlists (S1 ∪ S4 wallets) and, of the detected
    # bets, books only the long-horizon one — marked to market, stamped "4".
    with tempfile.TemporaryDirectory() as d:
        s1wl, s4wl = os.path.join(d, "s1.json"), os.path.join(d, "s4.json")
        json.dump({"targets": [{"wallet": "0xS1"}]}, open(s1wl, "w"))
        json.dump({"targets": [{"wallet": "0xS4"}]}, open(s4wl, "w"))

        feed = [
            dict(copy_id="short", target="0xS1", condition_id="0xCS", token_id="TOKS",
                 outcome_index=0, category="research", their_price=0.50,
                 their_usd=1000, horizon_days=10),
            dict(copy_id="long", target="0xS4", condition_id="0xCL", token_id="TOKL",
                 outcome_index=0, category="research", their_price=0.50,
                 their_usd=1000, horizon_days=300),
        ]
        captured = {}

        def det_factory(w, age, usd, fb=None, horizon_resolver=None):
            captured["horizon_resolver"] = horizon_resolver
            return lambda: feed

        r = CopyPaperRunner(
            ledger_path=os.path.join(d, "s4led.jsonl"),
            watchlist_path=s1wl, extra_watchlist_paths=[s4wl],
            min_horizon_days=180, strategy="4", mark_fetcher=lambda t: 0.55,
            detector_factory=det_factory, book_fetcher=lambda t: [(0.50, 10000)],
            resolver=lambda c: None,
            exit_detector_factory=lambda w, age: (lambda: []),
            horizon_resolver=lambda cid: None,   # inject so no live Gamma call
            cycle_interval_s=0,
        )
        assert set(r.wallets()) == {"0xS1", "0xS4"}      # union watched
        s = r.run_once()
        assert s.opened == 1 and s.skipped_horizon == 1  # short bet skipped
        pos = r.ledger.open_positions()[0]
        assert pos.copy_id == "long" and pos.strategy == "4"
        assert pos.mark_price == 0.55                    # marked to market
        assert captured["horizon_resolver"] is not None  # resolver forwarded


def test_run_forever_survives_cycle_exception():
    with tempfile.TemporaryDirectory() as d:
        ev = threading.Event()
        calls = {"n": 0}

        def boom(w, age, usd, fb=None):
            def detect():
                calls["n"] += 1
                ev.set()
                raise RuntimeError("transient")
            return detect

        r = CopyPaperRunner(
            ledger_path=os.path.join(d, "l.jsonl"), wallets=["0xT"],
            detector_factory=boom, book_fetcher=lambda t: [], resolver=lambda c: None,
            cycle_interval_s=0,
        )
        r.run_forever(ev)  # exception inside cycle must not escape the loop
        assert calls["n"] == 1
