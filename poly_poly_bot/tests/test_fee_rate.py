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


def test_a_failing_gamma_read_is_none_not_a_crash(env, monkeypatch):
    import httpx

    class Bad:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            raise httpx.ConnectError("502")
    monkeypatch.setattr(httpx, "Client", Bad)
    assert fr.fee_bps("T", now=1.0) is None


def test_the_gamma_read_takes_the_rate_off_the_token_s_own_market(env, monkeypatch):
    import httpx
    asked = []

    class Resp:
        def __init__(self, rows):
            self._rows = rows

        def raise_for_status(self):
            pass

        def json(self):
            return self._rows

    class C:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            asked.append(params)
            if "closed" not in params:
                return Resp([])  # Gamma hides a closed market without the flag
            return Resp([{"clobTokenIds": '["OTHER"]', "feeSchedule": {"rate": 0.07}},
                         {"clobTokenIds": '["T5", "T6"]', "feesEnabled": True,
                          "feeSchedule": {"rate": 0.03, "exponent": 1}}])
    monkeypatch.setattr(httpx, "Client", C)
    assert fr.fee_bps("T6", now=1.0) == 300
    assert [("closed" in p) for p in asked] == [False, True]


def test_the_market_rate_reads_from_the_fee_schedule_never_the_base_fee():
    # Every market carries base fee 1000 (the 10% the phone showed); the rate
    # actually charged is the schedule's.
    row = {"makerBaseFee": 1000, "takerBaseFee": 1000, "feesEnabled": True,
           "feeType": "sports_fees_v2", "feeSchedule": {"rate": 0.03}}
    assert fr.rate_bps_from_market(row) == 300
    assert fr.rate_bps_from_market({**row, "feeSchedule": {"rate": 0}}) == 0
    assert fr.rate_bps_from_market({**row, "feesEnabled": False}) == 0
    assert fr.rate_bps_from_market({"takerBaseFee": 1000}) is None
    assert fr.rate_bps_from_market({"feeSchedule": {"rate": "x"}}) is None


def test_a_raising_injected_reader_is_none_too(env, monkeypatch):
    def boom(tok):
        raise RuntimeError("502")
    monkeypatch.setattr(fr, "reader", boom)
    assert fr.fee_bps("T", now=1.0) is None


def test_the_fee_is_curved_by_the_price():
    # shares x rate x p x (1-p) over shares x p: rate x (1-p) of the stake
    assert fr.fee_share(0.80, 300) == pytest.approx(0.006)
    assert fr.fee_share(0.20, 300) == pytest.approx(0.024)
    assert fr.fee_share(0.50, 1000) == pytest.approx(0.05)
    assert fr.fee_share(0.80, None) == 0.0 and fr.fee_share(0.80, 0) == 0.0


def test_the_effective_price_and_break_even_read_like_the_real_fill():
    # The 10-01 Safiullin fill: 13.33 shares at 0.48 for $6.56 paid on a $6.40
    # order, on a 0.05 sports market: 13.33 x 0.05 x 0.48 x 0.52 = $0.17.
    assert fr.effective_price(0.90, 500) == pytest.approx(0.9045)
    assert fr.effective_price(0.90, None) == 0.90
    b = fr.break_even(0.48, 500, 6.40)
    assert b["payout"] == pytest.approx(13.33, abs=0.01)
    assert b["fee_usd"] == pytest.approx(0.17, abs=0.01)
    assert b["paid"] == pytest.approx(6.57, abs=0.01)
    assert b["net"] == pytest.approx(6.77, abs=0.01)
    assert b["be_win"] == pytest.approx(0.4925, abs=0.001)
    line = fr.break_even_line(0.48, 500, 6.40)
    assert "+6.77" in line and "fee $0.17 = 2.6%" in line and "break-even 49%" in line
    assert "fee unread" in fr.break_even_line(0.48, None, 6.40)
    assert "no fee" in fr.break_even_line(0.48, 0, 6.40)


def test_a_high_price_buy_never_reads_ten_percent():
    # The phone's "fee 10.0%" on a 0.80 buy: the real charge is 0.6%.
    line = fr.break_even_line(0.80, 300, 6.40)
    assert "10.0%" not in line and "fee $0.04 = 0.6%" in line


def test_an_empty_token_is_never_asked(env, monkeypatch):
    monkeypatch.setattr(fr, "reader", lambda tok: pytest.fail("asked for an empty token"))
    assert fr.fee_bps("", now=1.0) is None


def test_the_zset_fee_estimate_is_curved_and_never_guesses_a_loss(env):
    from src.copy_trading import ops_watch
    fr._mem.update({"W": (500, 1.0), "L": (500, 1.0), "Z": (0, 1.0)})
    rows = [
        # a win at 0.48: cost 6.40, paid 13.33 -> 6.40 x 0.05 x 0.52 = 0.17
        {"token_id": "W", "won": True, "cost": 6.40, "after": "paid $13.33"},
        {"token_id": "L", "won": False, "cost": 6.40, "after": "paid $0.00"},
        {"token_id": "Z", "won": False, "cost": 5.00, "after": "paid $0.00"},
        {"token_id": "U", "won": True, "cost": 5.00, "after": "paid $6.00"},
    ]
    fee, read, total = ops_watch._fee_paid_estimate(rows)
    assert fee == pytest.approx(0.17, abs=0.01)
    assert (read, total) == (2, 4)
