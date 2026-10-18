"""The execution-path review of 2026-10-18 (scratchpad exec/REPORT.md, parts
5 and 6): the live fills were selected by latency, and the max-copies counter
counted every history row. Four plain bugs on the money path, each pinned.

1. The counter counts distinct PLACED copies, never refusals.
2. A SELL is an exit: no exposure-full, no price band, no drift rail, no
   reservation at the post (and nothing to give back when it does not fill).
3. The flip gate's remote read runs BEFORE the book snapshot, one try, 3 s.
4. The phone is told off the loop: a slow Telegram holds no post.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import pytest

from src.config import CONFIG
from src.copy_trading import trade_store
from tests.test_golive_month_one import W1, _Harness, _noop_async, _run


# --------------------------------------------------------------------------- #
# 1. The max-copies counter
# --------------------------------------------------------------------------- #

def _history(tmp_path, monkeypatch):
    path = tmp_path / "trade-history.jsonl"
    monkeypatch.setattr(trade_store, "_HISTORY_FILE", str(path))
    monkeypatch.setattr(trade_store, "_dup_index",
                        {"path": None, "ino": None, "head": b"", "offset": 0, "counts": {}})
    monkeypatch.setattr(CONFIG, "preview_mode", False)
    return path


def _row(path, **kw):
    kw.setdefault("side", "BUY")
    kw.setdefault("market", "Will X?")
    kw.setdefault("condition_id", "0xc1")
    kw.setdefault("timestamp", "2026-10-18T00:00:00+00:00")
    kw.setdefault("trader_address", W1)
    with open(path, "a") as f:
        f.write(json.dumps(kw) + "\n")


def test_one_filled_copy_is_one_not_two(tmp_path, monkeypatch):
    """PLACED + FILLED for the same order used to read 2, the cap of 2, so one
    copy closed the market to every wallet."""
    path = _history(tmp_path, monkeypatch)
    _row(path, status="PLACED", order_id="ord-1")
    assert trade_store.get_duplicate_count("Will X?", "BUY") == 1
    _row(path, status="FILLED", order_id="ord-1")
    assert trade_store.get_duplicate_count("Will X?", "BUY") == 1
    assert trade_store.get_duplicate_count("0xc1", "BUY") == 1, "by condition id too"
    assert trade_store.get_duplicate_count("Will X?", "SELL") == 0


def test_two_refusals_and_nothing_held_is_zero(tmp_path, monkeypatch):
    """Two SKIPPED rows closed a market forever: the refusal wrote the row
    that caused the next refusal."""
    path = _history(tmp_path, monkeypatch)
    _row(path, status="SKIPPED", reason="market quality: drift")
    _row(path, status="SKIPPED", reason="max copies reached (2/2)", timestamp="2026-10-18T00:01:00+00:00")
    for st in ("FAILED", "UNFILLED", "DISARMED", "ALERT_ONLY", "ABANDONED"):
        _row(path, status=st, order_id=f"ord-{st}")
    assert trade_store.get_duplicate_count("Will X?", "BUY") == 0
    assert trade_store.get_duplicate_count("0xc1", "BUY") == 0


def test_two_different_orders_are_two(tmp_path, monkeypatch):
    path = _history(tmp_path, monkeypatch)
    _row(path, status="PLACED", order_id="ord-1")
    _row(path, status="FILLED", order_id="ord-1")
    _row(path, status="PLACED", order_id="ord-2", trader_address="0x" + "2" * 40)
    _row(path, status="PARTIAL", order_id="ord-2", trader_address="0x" + "2" * 40)
    assert trade_store.get_duplicate_count("Will X?", "BUY") == 2
    # appended later, still incremental
    _row(path, status="SKIPPED", reason="max copies reached (2/2)")
    assert trade_store.get_duplicate_count("Will X?", "BUY") == 2


def test_paper_copies_count_in_a_paper_process_only(tmp_path, monkeypatch):
    """A PREVIEW row has no order id: one per (timestamp, trader). The live
    ledger must not be closed by the paper era's rows in the same file."""
    path = _history(tmp_path, monkeypatch)
    _row(path, status="PREVIEW", timestamp="2026-10-01T00:00:00+00:00")
    _row(path, status="PREVIEW", timestamp="2026-10-01T00:00:00+00:00")  # the same detection twice
    _row(path, status="PREVIEW", timestamp="2026-10-02T00:00:00+00:00")
    assert trade_store.get_duplicate_count("Will X?", "BUY") == 0, "live process: paper rows do not count"
    monkeypatch.setattr(CONFIG, "preview_mode", True)
    assert trade_store.get_duplicate_count("Will X?", "BUY") == 2


# --------------------------------------------------------------------------- #
# 2. A SELL is judged as an exit
# --------------------------------------------------------------------------- #

def _trade(side="BUY", price=0.5, size=1000.0):
    from src.models import DetectedTrade
    return DetectedTrade(id="t", trader_address=W1, timestamp=datetime.now(timezone.utc).isoformat(),
                         market="m", token_id="tok", condition_id="c", side=side, size=size, price=price)


def _cfg(**over):
    from src.copy_trading.strategy_config import TierConfig
    d = dict(tier="1b", enabled=True, wallets=[], copy_percentage=5.0, max_bet=25.0, min_bet=5.0,
             max_total_exposure=100.0, max_price=0.90, min_price=0.35, min_trader_bet=100.0,
             hold_to_settlement=False, alert_only=False)
    d.update(over)
    return TierConfig(**d)


def test_exposure_full_does_not_refuse_an_exit(monkeypatch):
    """(a) At the floor every mirrored SELL was 'exposure full' and the
    positions sat held while the target had left."""
    from src.copy_trading.tiered_risk_manager import TierExposure, _evaluate_tiered_trade_with_state
    monkeypatch.setattr(CONFIG, "max_trade_age_hours", 1.0)
    monkeypatch.setenv("LIVE_MAX_OPEN_PER_WALLET", "0")
    full = TierExposure(open_total=99.0)
    buy = _evaluate_tiered_trade_with_state(_trade("BUY"), "1b", full, _cfg())
    assert buy.should_copy is False and "exposure full" in buy.reason
    sell = _evaluate_tiered_trade_with_state(_trade("SELL"), "1b", full, _cfg())
    assert sell.should_copy is True, sell.reason


def test_the_price_band_does_not_refuse_an_exit(monkeypatch):
    """(b) A position that fell under min_price is the one we most need to
    leave; a SELL at 0.97 is the target cashing a winner we hold."""
    from src.copy_trading.tiered_risk_manager import TierExposure, _evaluate_tiered_trade_with_state
    monkeypatch.setattr(CONFIG, "max_trade_age_hours", 1.0)
    monkeypatch.setenv("LIVE_MAX_OPEN_PER_WALLET", "0")
    for p in (0.05, 0.97):
        buy = _evaluate_tiered_trade_with_state(_trade("BUY", price=p), "1b", TierExposure(), _cfg())
        assert buy.should_copy is False, p
        sell = _evaluate_tiered_trade_with_state(_trade("SELL", price=p), "1b", TierExposure(), _cfg())
        assert sell.should_copy is True, (p, sell.reason)


def test_drift_and_spread_do_not_refuse_an_exit_but_no_book_still_does(monkeypatch):
    """(c) An exit after a price drop is the normal case."""
    from src.copy_trading import trade_executor as te
    monkeypatch.setattr(te.CONFIG, "max_price_drift_bps", 300)
    monkeypatch.setattr(te.CONFIG, "max_spread_bps", 500)
    drifted = {"midpoint": 0.30, "spread_bps": 2000}
    assert "Price drift too high" in te._check_market_quality(_trade("BUY"), drifted)
    assert te._check_market_quality(_trade("SELL"), drifted) is None
    assert te._check_market_quality(_trade("SELL"), None) == "Could not fetch order book"


def _sell_harness(tmp_path, monkeypatch):
    """The money path with the wallet holding the token and the exit share
    answered locally (no positions read)."""
    from src.copy_trading import flip_gate
    h = _Harness(tmp_path, monkeypatch)
    monkeypatch.setattr(h.te, "_inventory", lambda: (
        lambda *a, **k: h.bought.append(a), lambda *a, **k: None, lambda t: True, _noop_async))
    monkeypatch.setattr(flip_gate, "exit_share", lambda *a, **k: (1.0, "test"))
    h.reserved: list = []
    from src.models import TieredCopyDecision
    monkeypatch.setattr(h.te, "_tiered_risk", lambda: (
        lambda t, tier: TieredCopyDecision(should_copy=True, copy_size=25.0, tier=tier, alert_only=False),
        lambda tier, size, **k: h.reserved.append((tier, size, k.get("token_id"))),
        lambda *a, **k: None))
    return h


def test_a_sell_post_reserves_no_exposure_and_a_buy_post_does(tmp_path, monkeypatch):
    """(d) record_tiered_placement is for entries; the release sites match."""
    h = _sell_harness(tmp_path, monkeypatch)
    q = h.trades(2)
    q[0].trade.side = "SELL"
    placed = h.run(q)
    assert placed == 2 and len(h.posted) == 2
    assert h.reserved == [("1b", 7.75, "tok1")], "the BUY reserved; the SELL did not"


def _po(side, tier="1b", copy_size=10.0):
    from src.models import DetectedTrade, PendingOrder
    trade = DetectedTrade(id=f"p-{side}", trader_address=W1, timestamp="2026-10-18T00:00:00+00:00",
                          market="m", condition_id="c", token_id="tokS", side=side, size=100.0, price=0.5)
    return PendingOrder(trade=trade, order_id=f"ord-{side}", order_price=0.5, copy_size=copy_size,
                        placed_at=1.0, market_key="c", side=side, source_detected_at=1.0,
                        enqueued_at=1.0, order_submitted_at=1.0, tier=tier)


def test_an_unfilled_sell_releases_nothing_and_an_unfilled_buy_its_reservation(monkeypatch):
    """(d) Giving a SELL's copy_size back off its token would take it out of
    the BUY row for the same token, which is still held."""
    from src.copy_trading import canary, trade_executor

    class _Fill:
        status, fill_price, filled_shares, filled_usd = "UNFILLED", 0.0, 0.0, 0.0

    async def _verify(clob, order_id):
        return _Fill()

    async def _cancel(clob, order_id):
        return True

    released: list = []
    legacy: list = []
    monkeypatch.setattr(trade_executor, "_verify_order_fill", _verify)
    monkeypatch.setattr(trade_executor, "_cancel_order", _cancel)
    monkeypatch.setattr(trade_executor, "_tiered_risk", lambda: (
        None, None, lambda tier, amount, token_id=None: released.append((tier, amount, token_id))))
    monkeypatch.setattr(trade_executor, "_risk_manager", lambda: (None, None, lambda t, a: legacy.append(a)))
    monkeypatch.setattr(trade_executor, "_strategy_config", lambda: (False, None, None))
    monkeypatch.setattr(trade_executor, "_trade_queue", lambda: (None, lambda oid: None, None))
    monkeypatch.setattr(trade_executor, "_inventory", lambda: (None, None, None, None))
    monkeypatch.setattr(trade_executor, "_trade_store", lambda: (
        None, lambda tid: None, None, None, lambda rec: None, None))

    class _TG:
        async def trade_unfilled(self, *a, **k): pass
    monkeypatch.setattr(trade_executor, "_telegram", lambda: _TG())
    monkeypatch.setattr(canary, "record_fill", lambda oid, fill: None)
    monkeypatch.setattr(canary, "record_test_fill", lambda oid, fill: None)
    _run(trade_executor.process_verifications([_po("SELL"), _po("BUY"), _po("SELL", tier=None)], clob_client=None))
    assert released == [("1b", 10.0, "tokS")], "only the BUY had reserved"
    assert legacy == [-10.0], "the legacy ledger keeps its own rule"


# --------------------------------------------------------------------------- #
# 3. The flip gate runs before the snapshot, one try, 3 s
# --------------------------------------------------------------------------- #

def test_the_flip_gate_runs_before_the_book_is_read_and_with_the_hot_path_budget(tmp_path, monkeypatch):
    from src.copy_trading import flip_gate
    h = _Harness(tmp_path, monkeypatch)
    order: list = []

    def gate(trader, token_id, buy_ts, shares, **kw):
        order.append(("flip", kw.get("timeout_s")))
        return (False, "")

    async def snap(client, token_id):
        order.append(("snap", None))
        return {"best_bid": 0.49, "best_ask": 0.51, "midpoint": 0.50, "spread_bps": 400}
    monkeypatch.setattr(flip_gate, "target_already_exited", gate)
    monkeypatch.setattr(h.te, "_get_market_snapshot", snap)
    assert h.run(h.trades(1)) == 1
    assert order == [("flip", flip_gate.HOT_PATH_TIMEOUT_S), ("snap", None)]
    assert flip_gate.HOT_PATH_TIMEOUT_S == 3.0


def test_a_slow_activity_read_is_cut_at_three_seconds_and_does_not_refuse(monkeypatch):
    import requests

    from src.copy_trading import discovery_data, flip_gate
    flip_gate.clear()
    seen: list = []
    slept: list = []

    class _Session:
        def get(self, url, params=None, timeout=None):
            seen.append(timeout)
            raise requests.exceptions.Timeout("the data-api took longer than that")
    monkeypatch.setattr(requests, "Session", lambda: _Session())
    monkeypatch.setattr(discovery_data.time, "sleep", lambda s: slept.append(s))
    t0 = 1_760_000_000.0
    out = flip_gate.target_already_exited("0xW", "tok", t0, 100.0, now=t0 + 5, timeout_s=flip_gate.HOT_PATH_TIMEOUT_S)
    assert out == (False, ""), "a gate that cannot read does not refuse"
    assert seen == [3.0] and slept == [], "one try inside 3 s, no backoff after it"
    # the sweep's patience is untouched
    seen.clear()
    assert discovery_data._get(_Session(), "http://x", "/activity", user="0xW") is None
    assert seen == [30.0] * 4 and slept == [0.25] * 3


# --------------------------------------------------------------------------- #
# 4. The phone is told off the loop
# --------------------------------------------------------------------------- #

class _Clob:
    def get_order_book(self, token_id):
        return {"min_order_size": "5"}


def test_a_slow_phone_does_not_hold_the_next_post(tmp_path, monkeypatch):
    from src.copy_trading import daily_spend_guard
    from src.models import OrderResult
    h = _Harness(tmp_path, monkeypatch)
    monkeypatch.setattr(daily_spend_guard, "can_copy_wallet", lambda w: (True, ""))
    # each _run is a fresh loop; earlier tests' finished tasks must not be gathered here
    monkeypatch.setattr(h.te, "_bg_sends", set())
    events: list = []
    gate = asyncio.Event()

    class _TG:
        async def trade_placed(s, market, *a, **k):
            await gate.wait()  # a Telegram that answers after the batch
            events.append(("msg", market))

        async def trade_failed(s, *a, **k):
            pass
    monkeypatch.setattr(h.te, "_telegram", lambda: _TG())

    async def post(client, trade, copy_size, snapshot):
        events.append(("post", trade.market))
        return OrderResult(order_id=f"ord-{trade.market}", shares=10.0, order_price=0.51)
    monkeypatch.setattr(h.te, "_execute_copy_order", post)

    async def drive():
        placed = await h.te.place_trade_orders(h.trades(2), _Clob())
        assert events == [("post", "m0"), ("post", "m1")], "both posts before any message was delivered"
        gate.set()
        await asyncio.gather(*list(h.te._bg_sends))
        await asyncio.sleep(0)  # the done callbacks run on the next turn
        return placed
    assert _run(drive()) == 2
    assert events == [("post", "m0"), ("post", "m1"), ("msg", "m0"), ("msg", "m1")]
    assert h.te._bg_sends == set(), "no task is kept once it is done"


def test_a_phone_that_raises_is_logged_never_raised_into_the_loop(tmp_path, monkeypatch, caplog):
    h = _Harness(tmp_path, monkeypatch)

    class _TG:
        async def trade_placed(s, *a, **k):
            raise RuntimeError("telegram down")

        async def trade_failed(s, *a, **k):
            pass
    monkeypatch.setattr(h.te, "_telegram", lambda: _TG())

    async def drive():
        placed = await h.te.place_trade_orders(h.trades(1), _Clob())
        await asyncio.sleep(0)  # let the send task finish
        return placed
    with caplog.at_level(logging.WARNING):
        assert _run(drive()) == 1
    assert any("live placed message failed: telegram down" in r.getMessage() for r in caplog.records)
    assert [r.status for r in h.history] == ["PLACED"], "the order was placed and recorded regardless"
