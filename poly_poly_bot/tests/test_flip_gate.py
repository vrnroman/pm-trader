"""The flip gate and the scalper rail (docs/REQUIREMENTS-2026-09-24.md, part 2 D)."""
from __future__ import annotations

import pytest

from src.config import CONFIG
from src.copy_trading import flip_gate, scalper

T0 = 1_790_300_000.0


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    flip_gate.clear()
    monkeypatch.setattr(CONFIG, "copy_flip_exit_frac", 0.5)
    yield
    flip_gate.clear()


def test_a_buy_the_target_sold_a_second_later_is_refused_from_the_local_record():
    flip_gate.note_detected("0xW", "tok", "BUY", 1121.34, T0)
    flip_gate.note_detected("0xW", "tok", "SELL", 1121.33, T0 + 1)
    exited, why = flip_gate.target_already_exited("0xw", "tok", T0, 1121.34, now=T0 + 30, fetch=lambda w: pytest.fail("no fetch needed"))
    assert exited and why == "target already sold 100% of this buy 1s later"


def test_a_trim_under_the_bar_is_copied_and_the_bar_is_the_owners_knob(monkeypatch):
    flip_gate.note_detected("0xW", "tok", "BUY", 100.0, T0)
    flip_gate.note_detected("0xW", "tok", "SELL", 30.0, T0 + 5)
    assert flip_gate.target_already_exited("0xW", "tok", T0, 100.0, now=T0 + 30, fetch=lambda w: [])[0] is False
    monkeypatch.setattr(CONFIG, "copy_flip_exit_frac", 0.25)
    assert flip_gate.target_already_exited("0xW", "tok", T0, 100.0, now=T0 + 30, fetch=lambda w: [])[0] is True
    # a sell of ANOTHER token, or one before the buy, is not an exit of this buy
    flip_gate.clear()
    flip_gate.note_detected("0xW", "other", "SELL", 100.0, T0 + 5)
    flip_gate.note_detected("0xW", "tok", "SELL", 100.0, T0 - 60)
    assert flip_gate.target_already_exited("0xW", "tok", T0, 100.0, now=T0 + 30, fetch=lambda w: [])[0] is False


def test_the_data_api_is_asked_once_when_the_record_has_nothing_newer_and_the_answer_is_cached():
    calls = []

    def fetch(w):
        calls.append(w)
        return [{"token": "tok", "side": "BUY", "shares": 50.0, "ts": T0},
                {"token": "tok", "side": "SELL", "shares": 50.0, "ts": T0 + 2}]
    assert flip_gate.target_already_exited("0xW", "tok", T0, 50.0, now=T0 + 30, fetch=fetch)[0] is True
    assert flip_gate.target_already_exited("0xW", "tok", T0, 50.0, now=T0 + 40, fetch=fetch)[0] is True
    assert calls == ["0xW"], "cached for COPY_FLIP_FETCH_TTL_S"
    flip_gate.clear()
    assert flip_gate.target_already_exited("0xW", "tok", T0, 50.0, now=T0 + 30, fetch=lambda w: None) == (False, "")
    assert flip_gate.target_already_exited("0xW", "tok", T0, 0.0, now=T0, fetch=lambda w: pytest.fail("x")) == (False, "")


def test_the_scalper_rail_counts_exits_inside_the_window():
    acts = []
    for i in range(12):
        acts.append({"type": "TRADE", "side": "BUY", "conditionId": f"c{i}", "timestamp": T0 + i * 3600, "usdcSize": 400})
        acts.append({"type": "TRADE", "side": "SELL", "conditionId": f"c{i}", "timestamp": T0 + i * 3600 + (60 if i < 3 else 7200), "usdcSize": 400})
    acts.append({"type": "TRADE", "side": "BUY", "conditionId": "held", "timestamp": T0, "usdcSize": 400})
    assert scalper.flip_stats_from_acts(acts, since=T0 - 1, floor=300) == (12, 3)
    scalp, why = scalper.is_scalper(12, 3)
    assert scalp and why == "scalper: 25% of exits within 10 min; uncopyable at our latency"
    assert scalper.is_scalper(10, 1) == (False, "10% of 10 exits within 10 min")
    assert scalper.is_scalper(9, 9)[0] is False, "under the minimum, nothing is said"

    class T:
        def __init__(self, a, b):
            self.entry_ts, self.exit_ts = a, b
    assert scalper.flip_stats_from_trips([T(0, 30), T(0, 900), T(0, 600)]) == (3, 2)
