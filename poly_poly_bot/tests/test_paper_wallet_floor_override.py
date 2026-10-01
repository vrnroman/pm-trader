"""A paper-only floor per wallet (the owner, 2026-10-02): "ignore deal size
for this wallet only". The paper detectors copy the named wallet from its own
floor; the live floor never reads it."""
from __future__ import annotations

import pathlib

import pytest

from src.copy_trading import copy_paper_live as live

FRIEND = "0x5a8f802ebad4f45e85d68ac1cbde86579fc9a6f5"
OTHER = "0x1111111111111111111111111111111111111111"
NOW = 1_790_900_000.0


def _act(wallet, usd, tx, price=0.6, ts=None):
    return {"type": "TRADE", "side": "BUY", "price": price, "usdcSize": usd, "size": usd / price,
            "timestamp": NOW - 30 if ts is None else ts, "transactionHash": tx, "asset": "TOK" + tx,
            "conditionId": "0xC" + tx, "outcomeIndex": 0, "title": "Bitcoin Up or Down - October 2, 5:05AM-5:10AM",
            "eventSlug": "btc-updown", "proxyWallet": wallet}


class _StubFeed:
    def __init__(self, rows):
        self.rows = rows

    def recent(self, min_usd, max_age_s):
        return self.rows


# --------------------------------------------------------------------------- #
# The env knob
# --------------------------------------------------------------------------- #

def test_the_env_parses_wallet_colon_dollars_and_skips_junk(monkeypatch):
    from src import config
    monkeypatch.setenv("X_FLOORS", f"{FRIEND.upper()}:1, 0xdeadbeef:5, {OTHER}:abc, nonsense, {OTHER}:2.5")
    assert config._opt_wallet_floors("X_FLOORS") == {FRIEND: 1.0, OTHER: 2.5}
    monkeypatch.delenv("X_FLOORS")
    assert config._opt_wallet_floors("X_FLOORS") == {}


# --------------------------------------------------------------------------- #
# Per-wallet polling honours the override
# --------------------------------------------------------------------------- #

def test_make_detector_copies_the_override_wallet_from_its_own_floor(monkeypatch):
    acts = {FRIEND: [_act(FRIEND, 4.8, "f1")], OTHER: [_act(OTHER, 4.8, "o1"), _act(OTHER, 400.0, "o2")]}
    monkeypatch.setattr(live, "_get", lambda base, path, **p: acts.get(p.get("user"), []))
    monkeypatch.setattr(live.time, "time", lambda: NOW)
    det = live.make_detector([FRIEND, OTHER], 3600.0, 300.0, wallet_min_usd={FRIEND: 1.0})
    out = det()
    assert sorted(r["copy_id"] for r in out) == ["f1-TOKf1", "o2-TOKo2"]
    assert det.stats["below_min_usd"] == 1          # the other wallet's $4.80, not the friend's
    assert [r["their_usd"] for r in out if r["target"] == FRIEND] == [4.8]


def test_without_an_override_the_book_floor_applies_to_everyone(monkeypatch):
    acts = {FRIEND: [_act(FRIEND, 4.8, "f1")]}
    monkeypatch.setattr(live, "_get", lambda base, path, **p: acts.get(p.get("user"), []))
    monkeypatch.setattr(live.time, "time", lambda: NOW)
    det = live.make_detector([FRIEND], 3600.0, 300.0)
    assert det() == [] and det.stats["below_min_usd"] == 1


# --------------------------------------------------------------------------- #
# The feed detector polls the override wallet itself and merges once
# --------------------------------------------------------------------------- #

def test_the_feed_detector_polls_the_override_wallet_and_merges_without_doubles(monkeypatch):
    # The shared feed (server floor $100) carries the other wallet's big trade
    # and, as it happens, one of the friend's (as it would if the feed floor
    # were ever lowered); the friend's small trades only come from his own poll.
    feed = _StubFeed([_act(OTHER, 400.0, "o2"), _act(FRIEND, 120.0, "f9")])
    acts = {FRIEND: [_act(FRIEND, 4.8, "f1"), _act(FRIEND, 120.0, "f9"), _act(FRIEND, 0.5, "f0")]}
    calls = []

    def fake_get(base, path, **p):
        calls.append(p.get("user"))
        return acts.get(p.get("user"), [])
    monkeypatch.setattr(live, "_get", fake_get)
    monkeypatch.setattr(live.time, "time", lambda: NOW)
    det = live.make_feed_detector([FRIEND, OTHER], 3600.0, 300.0, feed=feed, feed_min_usd=100.0,
                                  wallet_min_usd={FRIEND: 1.0, "0x9999999999999999999999999999999999999999": 1.0})
    out = det()
    ids = sorted(r["copy_id"] for r in out)
    assert ids == ["f1-TOKf1", "f9-TOKf9", "o2-TOKo2"], ids
    assert calls == [FRIEND], "only the watched override wallet is polled; an unwatched override is ignored"
    assert det.stats["emitted"] == 3
    assert det.stats["below_min_usd"] == 2        # the friend's $0.50 (own floor $1) + the feed's $120 friend row under $300 before the merge
    friend_rows = [r for r in out if r["target"] == FRIEND]
    assert {r["their_usd"] for r in friend_rows} == {4.8, 120.0}
    assert all(r["detected_at"] == NOW for r in friend_rows)


def test_a_failing_poll_of_the_override_wallet_never_stalls_the_feed(monkeypatch):
    feed = _StubFeed([_act(OTHER, 400.0, "o2")])

    def boom(base, path, **p):
        raise RuntimeError("data api 502")
    monkeypatch.setattr(live, "_get", boom)
    monkeypatch.setattr(live.time, "time", lambda: NOW)
    det = live.make_feed_detector([FRIEND, OTHER], 3600.0, 300.0, feed=feed, feed_min_usd=100.0,
                                  wallet_min_usd={FRIEND: 1.0})
    out = det()
    assert [r["copy_id"] for r in out] == ["o2-TOKo2"]


def test_no_override_means_the_feed_detector_is_unchanged(monkeypatch):
    feed = _StubFeed([_act(OTHER, 400.0, "o2")])
    monkeypatch.setattr(live, "_get", lambda base, path, **p: pytest.fail("nobody should be polled"))
    monkeypatch.setattr(live.time, "time", lambda: NOW)
    det = live.make_feed_detector([FRIEND, OTHER], 3600.0, 300.0, feed=feed, feed_min_usd=100.0)
    assert [r["copy_id"] for r in det()] == ["o2-TOKo2"]


# --------------------------------------------------------------------------- #
# Paper only: the live floor never reads the override
# --------------------------------------------------------------------------- #

def test_the_live_floor_ignores_the_paper_override(monkeypatch):
    from src.config import CONFIG
    from src.copy_trading import wallet_floor
    monkeypatch.setattr(CONFIG, "copy_paper_wallet_min_usd", {FRIEND: 1.0})
    floor, why = wallet_floor.live_floor_why(FRIEND, 300.0)
    assert floor == 300.0 and "global floor" in why


def test_the_tier_floor_still_refuses_the_friends_five_dollar_bet(monkeypatch):
    from datetime import datetime, timezone
    from src.config import CONFIG
    from src.copy_trading import tiered_risk_manager as trm
    from src.copy_trading.strategy_config import TierConfig
    from src.models import DetectedTrade
    monkeypatch.setattr(CONFIG, "copy_paper_wallet_min_usd", {FRIEND: 1.0})
    t = DetectedTrade(id="tx", trader_address=FRIEND, market="Bitcoin Up or Down", side="BUY", size=4.8,
                      price=0.6, timestamp=datetime.now(timezone.utc).isoformat(), condition_id="0xc",
                      token_id="TOK", outcome="Down")
    cfg = TierConfig(tier="1b", enabled=True, copy_percentage=10.0, max_bet=50.0, min_bet=5.0,
                     max_total_exposure=500.0, max_price=0.9, min_price=0.0, min_trader_bet=300.0)
    d = trm._evaluate_tiered_trade_with_state(t, "1b", trm.TierExposure(), cfg)
    assert d.should_copy is False and "min_trader_bet" in d.reason


# --------------------------------------------------------------------------- #
# The production wiring
# --------------------------------------------------------------------------- #

def test_main_hands_the_overrides_to_every_paper_book_and_the_deploy_names_the_wallet():
    root = pathlib.Path(__file__).resolve().parents[1]
    src = (root / "main.py").read_text()
    assert src.count("wallet_min_usd=CONFIG.copy_paper_wallet_min_usd") >= 3, "A's factory, B's factory, and the feed-off path"
    dy = (root.parent / ".github" / "workflows" / "deploy.yml").read_text()
    assert f"ensure_env COPY_PAPER_WALLET_MIN_USD {FRIEND}:1" in dy
