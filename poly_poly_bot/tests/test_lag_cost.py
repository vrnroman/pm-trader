"""Lag Has a Price (s-qbzbrw phase 2): the chain's stamp of a fill is quoted
through the same shadow observer as the api's, under its own copy_id, and
the delay between the two quotes has a price, an estimate, one line under
the 08:00 message."""
from __future__ import annotations

import json
import time

import pytest

from src.config import CONFIG
from src.copy_trading import ops_watch, shadow_quote, two_clocks as tc

NOW = 1_789_900_000.0


@pytest.fixture
def lag_env(tmp_path, monkeypatch):
    for mod in (CONFIG, shadow_quote.CONFIG, tc.CONFIG, ops_watch.CONFIG):
        monkeypatch.setattr(mod, "data_dir", str(tmp_path))
    monkeypatch.setattr(shadow_quote, "_sinks", [])
    monkeypatch.setattr(tc, "_noted", None)
    return tmp_path


def _shadow_row(copy_id, *, our_price, detected_at, their_ts, source, target="0xz", token="tok1"):
    return {"copy_id": copy_id, "target": target, "token_id": token, "source": source, "their_price": 0.5,
            "their_usd": 500.0, "their_ts": their_ts, "detected_at": detected_at,
            "notify_latency_s": detected_at - their_ts, "quoted_at": detected_at + 1, "quote_lag_s": 1.0,
            "boot_flush": False, "our_price": our_price, "penalty_bps": 0, "best_bid": our_price - 0.01,
            "best_ask": our_price, "spread_bps": 100, "category": "sports", "title": "m"}


def _write_shadow(path, rows):
    with open(path / "shadow-quotes.jsonl", "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_the_registry_hands_rows_to_every_sink_and_survives_a_bad_one(lag_env):
    got = []
    def good(rows):
        got.extend(rows)
    def bad(rows):
        raise RuntimeError("boom")
    shadow_quote.register_sink(bad)
    shadow_quote.register_sink(good)
    shadow_quote.register_sink(good)   # idempotent
    assert len(shadow_quote._sinks) == 2
    assert shadow_quote.emit([{"copy_id": "a"}]) == 1 and got == [{"copy_id": "a"}]


def test_the_chain_quotes_a_buy_fill_under_its_own_copy_id(lag_env, monkeypatch):
    import asyncio
    from src.copy_trading import onchain_source as oc, trade_queue, trade_store
    from tests.test_onchain_source import _Event, _source, TRACKED, OTHER
    monkeypatch.setattr(trade_queue, "enqueue_trade", lambda q: (_ for _ in ()).throw(AssertionError("no enqueue in shadow")))
    monkeypatch.setattr(trade_store, "is_seen_trade", lambda tid: False)
    monkeypatch.setattr(trade_store, "is_max_retries", lambda tid: False)
    monkeypatch.setattr("src.copy_trading.trade_store.record_poll_ok", lambda: None)
    got = []
    shadow_quote.register_sink(lambda rows: got.extend(rows))
    s = _source(); s._running = True
    class _Eth:
        # two 200-block chunks from cursor 5: the fake fetch stops the loop on
        # its second call; a head inside one chunk would spin at cursor >= head
        block_number = 406
    class _W3:
        eth = _Eth()
    s._w3 = _W3()
    # start() would rebuild the real provider and hit the network: keep the fake
    monkeypatch.setattr(s, "_init_web3", lambda: None)
    monkeypatch.setattr(s, "_get_block_timestamp", lambda n: int(NOW))
    monkeypatch.setattr(oc, "_load_cursor", lambda: 5)
    monkeypatch.setattr(oc, "_save_cursor", lambda b: None)
    monkeypatch.setattr(oc, "POLL_INTERVAL_S", 0.0)
    monkeypatch.setattr(s, "_refresh_tracked", lambda: None)
    calls = {"n": 0}
    def fetch(a, b):
        calls["n"] += 1
        if calls["n"] > 1:
            s._running = False
            return []
        return s._process_events([_Event(TRACKED, OTHER, 0, 123, 500_000, 1_000_000),    # a BUY
                                  _Event(TRACKED, OTHER, 123, 0, 1_000_000, 500_000)], "CTF")  # a SELL
    monkeypatch.setattr(s, "_fetch_events_range", fetch)
    asyncio.run(s.start())
    assert len(got) == 1, "the BUY only; the api side quotes BUYs only too"
    row = got[0]
    assert row["copy_id"] == "chain:0xtx-123" and row["source"] == "onchain" and row["token_id"] == "123"
    assert row["their_ts"] == int(NOW) and row["detected_at"] >= row["their_ts"] and row["their_price"] == 0.5
    assert len(tc.load_rows()) == 2, "both fills still stamped for the two-clocks report"


def test_lag_cost_pairs_the_two_quotes_and_prices_the_delay(lag_env):
    _write_shadow(lag_env, [
        _shadow_row("0xAB12-tok1", our_price=0.52, detected_at=NOW + 40, their_ts=NOW, source="fast-prober"),
        _shadow_row("chain:0xab12-tok1", our_price=0.50, detected_at=NOW + 10, their_ts=NOW, source="onchain"),
        _shadow_row("0xCD34-tok2", our_price=0.70, detected_at=NOW + 30, their_ts=NOW, source="fast-prober", token="tok2"),
        _shadow_row("chain:0xef56-tok3", our_price=0.30, detected_at=NOW + 5, their_ts=NOW, source="onchain", token="tok3"),
    ])
    r = tc.lag_cost(0.0, stake_usd=6.4, now=NOW + 100)
    assert (r["pairs"], r["priced"], r["api_only"], r["chain_only"]) == (1, 1, 1, 1)
    assert r["cost_usd"] == pytest.approx((0.52 - 0.50) * (6.4 / 0.50), abs=0.01)   # +0.26
    assert r["saved_p50_s"] == 30.0 and r["cost_p50"] == pytest.approx(0.256, abs=0.001)
    line = tc.lag_cost_line(0.0, stake_usd=6.4, now=NOW + 100)
    assert line.startswith("api lag cost, last 7d (estimate): +0.26 USD over 1 fills at $6.40 each")
    assert "chain earlier by 30.0s" in line and "—" not in line
    assert tc._api_key("nonsense") is None


def test_unpaired_quotes_are_counted_not_priced(lag_env):
    assert tc.lag_cost_line(0.0, stake_usd=6.4, now=NOW) == "api lag cost: collecting, n=0"
    _write_shadow(lag_env, [_shadow_row("0xAB12-tok1", our_price=0.52, detected_at=NOW + 40, their_ts=NOW, source="fast-prober")])
    line = tc.lag_cost_line(0.0, stake_usd=6.4, now=NOW + 100)
    assert line.startswith("api lag cost: collecting, n=0 (chain-quoted 0, api-quoted 1, paired 0)")


def test_the_daily_line_carries_the_lag_cost_when_priced(lag_env, monkeypatch):
    from src.copy_trading import live_budget
    monkeypatch.setattr(live_budget, "caps", lambda live=True: type("C", (), {"per_copy_usd": 6.4})())
    assert "api lag cost" not in ops_watch.daily_line(NOW), "nothing to pair yet: no line"
    _write_shadow(lag_env, [
        _shadow_row("0xAB12-tok1", our_price=0.52, detected_at=NOW - 40, their_ts=NOW - 80, source="fast-prober"),
        _shadow_row("chain:0xab12-tok1", our_price=0.50, detected_at=NOW - 70, their_ts=NOW - 80, source="onchain"),
    ])
    line = ops_watch.daily_line(NOW)
    assert "⏱ api lag cost, last 7d (estimate): +0.26 USD over 1 fills" in line
    assert "—" not in line


def test_main_registers_the_observer_as_a_sink():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert "shadow_quote.register_sink(fast_prober.make_shadow_sink(observer))" in src
