"""The exchange's fee, read not assumed (run s-k7m2qa)."""
from __future__ import annotations

import json

import pytest

from src.config import CONFIG
from src.copy_trading import fee_rate as fr


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(fr.CONFIG, "data_dir", str(tmp_path))
    fr.reset_for_tests()
    monkeypatch.setattr(fr, "reader", None)
    yield tmp_path
    fr.reset_for_tests()
    fr.reader = None


def test_a_read_rate_is_cached_on_disk_for_a_day(env, monkeypatch):
    calls = []
    monkeypatch.setattr(fr, "reader", lambda tok: calls.append(tok) or 250)
    assert fr.fee_bps("T1", now=1000.0) == 250
    assert fr.fee_bps("T1", now=2000.0) == 250
    assert calls == ["T1"]
    on_disk = json.loads((env / fr.CACHE_FILE).read_text())
    assert on_disk["T1"]["bps"] == 250
    # a day later it is asked again
    monkeypatch.setattr(fr, "reader", lambda tok: 300)
    assert fr.fee_bps("T1", now=1000.0 + fr.CACHE_TTL_S + 1) == 300


def test_the_cache_survives_a_restart(env, monkeypatch):
    monkeypatch.setattr(fr, "reader", lambda tok: 175)
    fr.fee_bps("T1", now=1000.0)
    fr.reset_for_tests()
    monkeypatch.setattr(fr, "reader", lambda tok: pytest.fail("should not re-read inside the TTL"))
    assert fr.fee_bps("T1", now=5000.0) == 175


def test_an_unreadable_rate_is_none_and_a_stale_cache_beats_nothing(env, monkeypatch):
    monkeypatch.setattr(fr, "reader", lambda tok: None)
    assert fr.fee_bps("T9", now=1000.0) is None
    monkeypatch.setattr(fr, "reader", lambda tok: 200)
    fr.fee_bps("T9", now=1000.0)
    monkeypatch.setattr(fr, "reader", lambda tok: None)
    assert fr.fee_bps("T9", now=1000.0 + fr.CACHE_TTL_S + 1) == 200


def test_a_raising_client_is_none_not_a_crash(env, monkeypatch):
    class Bad:
        def get_fee_rate_bps(self, tok):
            raise RuntimeError("502")
    monkeypatch.setattr(fr, "_client", Bad())
    assert fr.fee_bps("T", now=1.0) is None


def test_a_raising_injected_reader_is_none_too(env, monkeypatch):
    def boom(tok):
        raise RuntimeError("502")
    monkeypatch.setattr(fr, "reader", boom)
    assert fr.fee_bps("T", now=1.0) is None


def test_the_effective_price_and_break_even_read_like_the_real_fill():
    # The 10-01 Safiullin fill: 13.33 shares at 0.48 for $6.56 paid on a $6.40 order.
    assert fr.effective_price(0.90, 250) == pytest.approx(0.9225)
    assert fr.effective_price(0.90, None) == 0.90
    b = fr.break_even(0.48, 257, 6.40)
    assert b["payout"] == pytest.approx(13.33, abs=0.01)
    assert b["paid"] == pytest.approx(6.56, abs=0.01)
    assert b["net"] == pytest.approx(6.77, abs=0.01)
    assert b["be_win"] == pytest.approx(0.4923, abs=0.001)
    line = fr.break_even_line(0.48, 257, 6.40)
    assert "+6.77" in line and "fee 2.6%" in line and "break-even 49%" in line
    assert "fee unread" in fr.break_even_line(0.48, None, 6.40)
    assert "no fee" in fr.break_even_line(0.48, 0, 6.40)


def test_an_empty_token_is_never_asked(env, monkeypatch):
    monkeypatch.setattr(fr, "reader", lambda tok: pytest.fail("asked for an empty token"))
    assert fr.fee_bps("", now=1.0) is None
