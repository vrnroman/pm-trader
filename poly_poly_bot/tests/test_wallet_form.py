"""Form: is a followed wallet winning now, on its own money (s-g8int5 follow-up)."""
from __future__ import annotations

import json
import time

import pytest

from src.config import CONFIG
from src.copy_trading import wallet_form as wf


@pytest.fixture
def form_env(tmp_path, monkeypatch):
    from src.copy_trading import ops_watch
    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(wf.CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(ops_watch.CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(CONFIG, "copy_paper_min_usd", 300.0)
    return tmp_path


NOW = 1_789_300_000.0


def _rows(n_won, n_lost, price=0.5, cost=400.0, small=0, open_=0, unclaimed=0):
    acts, pos = [], []
    i = 0
    def buy(cid, c, p):
        acts.append({"type": "TRADE", "side": "BUY", "conditionId": cid, "usdcSize": c, "size": c / p, "price": p, "timestamp": NOW - 3600 * (i + 1)})
    for _ in range(n_won):
        cid = f"w{i}"; buy(cid, cost, price); acts.append({"type": "REDEEM", "conditionId": cid, "usdcSize": cost / price, "timestamp": NOW - 100}); i += 1
    for _ in range(n_lost):
        buy(f"l{i}", cost, price); i += 1
    for _ in range(small):
        buy(f"s{i}", 50.0, price); i += 1
    for _ in range(open_):
        cid = f"o{i}"; buy(cid, cost, price); pos.append({"conditionId": cid, "curPrice": 0.6, "currentValue": 300.0, "redeemable": False}); i += 1
    for _ in range(unclaimed):
        cid = f"u{i}"; buy(cid, cost, price); pos.append({"conditionId": cid, "curPrice": 1.0, "currentValue": cost / price, "redeemable": True}); i += 1
    return acts, pos


def test_compute_counts_markets_once_and_knows_won_lost_open(form_env):
    acts, pos = _rows(n_won=20, n_lost=10, price=0.5, small=5, open_=3, unclaimed=4)
    f = wf.compute("0xW", acts, pos, now=NOW)
    assert (f.n, f.won) == (34, 24), "small bets and open markets excluded; unclaimed winners count as won"
    assert abs(f.avg_price - 0.5) < 1e-9 and f.cost == 34 * 400.0 and f.back == 24 * 800.0
    assert f.ok is True and "71% came out ahead vs 50% needed" in f.reason


def test_bars_bench_thin_flat_and_negative_records(form_env):
    acts, pos = _rows(n_won=10, n_lost=5)
    f = wf.compute("0xT", acts, pos, now=NOW)
    assert f.ok is False and "only 15 settled" in f.reason
    acts, pos = _rows(n_won=16, n_lost=14, price=0.53)  # 53% hit vs 53% needed
    f = wf.compute("0xF", acts, pos, now=NOW)
    assert f.ok is False and "points" in f.reason
    acts, pos = _rows(n_won=17, n_lost=13, price=0.53)  # 57% vs 53%: +4 points but net?
    f = wf.compute("0xN", acts, pos, now=NOW)
    assert (f.ok, round(f.net_pct, 1)) == (True, 6.9)


def test_the_bench_defaults_to_benched_until_the_first_scan(form_env):
    assert wf.is_benched("0xnew")[0] is True
    wf._write({"ts": 1.0, "wallets": {"0xa": {"ok": True, "reason": "fine"}, "0xb": {"ok": False, "reason": "cold"}}})
    assert wf.is_benched("0xA") == (False, "fine") and wf.is_benched("0xb") == (True, "cold")
    assert wf.in_form_wallets() == ["0xa"]


def test_the_routine_override_holds_a_day_and_only_inside_set_z(form_env, monkeypatch):
    from src.copy_trading import zset
    monkeypatch.setattr(zset, "wallet_set", lambda: {"0xa"})
    wf._write({"ts": 1.0, "wallets": {"0xa": {"ok": True, "reason": "fine"}}})
    assert wf.apply_override("0xA", "bench", "losing on the big bets", now=1000.0) is True
    assert wf.is_benched("0xa", now=2000.0) == (True, "routine bench: losing on the big bets")
    assert wf.is_benched("0xa", now=1000.0 + wf.FORM_OVERRIDE_S + 1)[0] is False, "expires"
    assert wf.apply_override("0xZZ", "bench", "x") is False and wf.apply_override("0xa", "evict", "x") is False
    # monotone: it lifts only its own bench, never the bar's
    assert wf.apply_override("0xa", "unbench", "recovered", now=1500.0) is True
    assert wf.is_benched("0xa", now=1600.0)[0] is False
    wf._write({"ts": 1.0, "wallets": {"0xa": {"ok": False, "reason": "cold by the bar"}}})
    assert wf.apply_override("0xa", "unbench", "please", now=1700.0) is False
    assert wf.is_benched("0xa", now=1800.0) == (True, "cold by the bar")


def test_scan_receipts_changes_and_pauses_once(form_env, monkeypatch):
    from src.copy_trading import ops_watch
    data = {"0xa": _rows(n_won=20, n_lost=10), "0xb": _rows(n_won=10, n_lost=20)}

    def get(url):
        w = url.split("user=")[1].split("&")[0]
        acts, pos = data[w]
        return pos if "/positions" in url else (acts if "offset=0" in url else [])
    sent: list = []
    d = wf.scan(get=get, send=sent.append, now=NOW, wallets=["0xa", "0xb"])
    assert d["wallets"]["0xa"]["ok"] is True and d["wallets"]["0xb"]["ok"] is False and d["paused"] is False
    assert sent == [], "first scan: no change to announce, nobody paused"
    data["0xa"] = _rows(n_won=10, n_lost=20)
    d = wf.scan(get=get, send=sent.append, now=NOW + 100, wallets=["0xa", "0xb"])
    assert d["paused"] is True
    assert any("Benched" in m and "0xa" in m for m in sent) and any("Live copying paused" in m for m in sent)
    n = len(sent)
    wf.scan(get=get, send=sent.append, now=NOW + 200, wallets=["0xa", "0xb"])
    assert len(sent) == n, "paused once per episode"
    data["0xb"] = _rows(n_won=25, n_lost=5)
    d = wf.scan(get=get, send=sent.append, now=NOW + 300, wallets=["0xa", "0xb"])
    assert d["paused"] is False and any("resumes" in m for m in sent) and any("Back in form" in m for m in sent)
    rows = [json.loads(l) for l in (form_env / "ops-ledger.jsonl").read_text().splitlines()]
    kinds = [r["kind"] for r in rows]
    assert kinds.count("form_pause") == 1 and kinds.count("form_resume") == 1 and "form" in kinds
    assert all("—" not in m for m in sent)


def test_a_failed_read_keeps_the_last_verdict(form_env):
    wf._write({"ts": 1.0, "wallets": {"0xa": {"ok": True, "reason": "fine", "wallet": "0xa", "n": 40, "won": 25, "cost": 1.0, "back": 2.0, "avg_price": 0.5, "ts": 1.0}}})
    def get(url):
        raise RuntimeError("429")
    d = wf.scan(get=get, send=None, now=NOW, wallets=["0xa"])
    assert d["wallets"]["0xa"]["ok"] is True and d["paused"] is False


def test_the_sink_skips_a_benched_wallet_with_a_row(tmp_path, monkeypatch):
    from tests.test_golive_month_one import _Harness, W1
    h = _Harness(tmp_path, monkeypatch)
    monkeypatch.setattr(wf.CONFIG, "data_dir", str(tmp_path))
    wf._write({"ts": 1.0, "wallets": {W1.lower(): {"ok": False, "reason": "52% won vs 53% needed"}}})
    assert h.run(h.trades(1)) == 0 and h.posted == []
    rows = [r for r in h.history if r.status == "SKIPPED"]
    assert rows and "wallet out of form" in (rows[-1].reason or "")
    wf._write({"ts": 1.0, "wallets": {W1.lower(): {"ok": True, "reason": "fine"}}})
    h.seen.clear()
    assert h.run(h.trades(1)) == 1


def test_a_wallet_action_verdict_is_applied_not_sent(form_env, monkeypatch):
    from src.copy_trading import ops_watch, zset
    monkeypatch.setattr(zset, "wallet_set", lambda: {"0xa"})
    (form_env / ops_watch.ESCALATION_FILE).write_text(json.dumps({"id": "v7", "kind": "wallet_action", "wallet": "0xA", "action": "bench", "message": "cold this week"}))
    sent: list = []
    row = ops_watch.deliver_escalation(send=lambda t: sent.append(t) or True, now=5.0)
    assert row and row["after"] == "applied" and wf.is_benched("0xa", now=6.0)[0] is True
    assert sent and "benched" in sent[0]
    (form_env / ops_watch.ESCALATION_FILE).write_text(json.dumps({"id": "v8", "kind": "wallet_action", "wallet": "0xNOT", "action": "bench", "message": "x"}))
    row = ops_watch.deliver_escalation(send=lambda t: sent.append(t) or True, now=7.0)
    assert row and row["after"] == "refused"


# ---- code review of the form rail ----

def test_a_throttled_read_is_a_failure_not_an_empty_wallet(form_env, monkeypatch):
    """Finding 1: the discovery fetcher returns a truncated list and records
    the wallet in _activity_fetch_failures instead of raising."""
    from src.copy_trading import discovery_data as dd
    monkeypatch.setattr(dd, "fetch_activity", lambda w, c, ttl, cap=0: (dd._activity_fetch_failures.append(w) or []))
    with pytest.raises(RuntimeError):
        wf.fetch_rows("0xT")
    assert "0xT" not in dd._activity_fetch_failures, "the marker is consumed, not left for the sweep report"
    wf._write({"ts": 1.0, "wallets": {"0xt": {"ok": True, "reason": "fine", "wallet": "0xt", "n": 40, "won": 25, "cost": 1.0, "back": 2.0, "avg_price": 0.5, "ts": 1.0}}})
    d = wf.scan(send=None, now=NOW, wallets=["0xt"])
    assert d["wallets"]["0xt"]["ok"] is True and d["paused"] is False, "a throttled read keeps the last verdict"


def test_sells_are_inflow_and_pre_window_buys_are_left_out(form_env):
    acts = [{"type": "TRADE", "side": "BUY", "conditionId": "x", "usdcSize": 400.0, "size": 800.0, "timestamp": NOW - 3600},
            {"type": "TRADE", "side": "SELL", "conditionId": "x", "usdcSize": 680.0, "size": 800.0, "timestamp": NOW - 1800},
            {"type": "TRADE", "side": "BUY", "conditionId": "old", "usdcSize": 2000.0, "size": 4000.0, "timestamp": NOW - 20 * 86400},
            {"type": "TRADE", "side": "BUY", "conditionId": "old", "usdcSize": 350.0, "size": 700.0, "timestamp": NOW - 3 * 86400},
            {"type": "REDEEM", "conditionId": "old", "usdcSize": 4000.0, "size": 4000.0, "timestamp": NOW - 100},
            {"type": "REDEEM", "conditionId": "zero", "usdcSize": 0, "size": 1200.0, "timestamp": NOW - 100},
            {"type": "TRADE", "side": "BUY", "conditionId": "zero", "usdcSize": 500.0, "size": 1000.0, "timestamp": NOW - 7200}]
    f = wf.compute("0xS", acts, [], now=NOW)
    assert f.n == 2, "the exit market and the zero-payout market; the pre-window market is left out"
    assert f.won == 1 and f.cost == 900.0 and f.back == 680.0, "the sale is inflow; a zero-usdc redeem is not a win"


def test_the_slice_is_per_row_like_the_sink(form_env):
    acts = [{"type": "TRADE", "side": "BUY", "conditionId": "d", "usdcSize": 50.0, "size": 100.0, "timestamp": NOW - 3600 * k} for k in range(1, 9)]
    acts += [{"type": "TRADE", "side": "BUY", "conditionId": "b", "usdcSize": 350.0, "size": 700.0, "timestamp": NOW - 3600},
             {"type": "TRADE", "side": "BUY", "conditionId": "b", "usdcSize": 50.0, "size": 100.0, "timestamp": NOW - 1800},
             {"type": "REDEEM", "conditionId": "b", "usdcSize": 700.0, "timestamp": NOW - 100}]
    f = wf.compute("0xR", acts, [], now=NOW)
    assert f.n == 1 and f.cost == 350.0, "eight $50 clips on one market are not our slice; only the $350 row counts"


def test_the_pause_notice_is_stamped_only_when_delivered(form_env):
    data = {"0xa": _rows(n_won=20, n_lost=10)}
    def get(url):
        acts, pos = data["0xa"]
        return pos if "/positions" in url else (acts if "offset=0" in url else [])
    wf.scan(get=get, send=None, now=NOW, wallets=["0xa"])
    data["0xa"] = _rows(n_won=10, n_lost=20)
    calls = {"n": 0}
    def flaky(text):
        calls["n"] += 1
        return calls["n"] > 2  # the bench push and the first pause push fail, the retry lands
    d = wf.scan(get=get, send=flaky, now=NOW + 100, wallets=["0xa"])
    assert d["paused"] is True and d["paused_told"] is False
    d = wf.scan(get=get, send=flaky, now=NOW + 200, wallets=["0xa"])
    assert d["paused_told"] is True, "told on the retry"
    d = wf.scan(get=get, send=flaky, now=NOW + 300, wallets=["0xa"])
    assert calls["n"] == 3, "once told, silent"
    rows = [json.loads(l) for l in (form_env / "ops-ledger.jsonl").read_text().splitlines()]
    pauses = [r for r in rows if r["kind"] == "form_pause"]
    assert [r["push"] for r in pauses] == [None, "DEAL"]


def test_a_wallet_action_message_reports_the_state_after_and_waits_for_delivery(form_env, monkeypatch):
    from src.copy_trading import ops_watch, zset
    monkeypatch.setattr(zset, "wallet_set", lambda: {"0xa"})
    wf._write({"ts": 1.0, "wallets": {"0xa": {"ok": False, "reason": "cold by the bar"}}})
    (form_env / ops_watch.ESCALATION_FILE).write_text(json.dumps({"id": "u1", "kind": "wallet_action", "wallet": "0xa", "action": "unbench", "message": "recovered"}))
    sent: list = []
    row = ops_watch.deliver_escalation(send=lambda t: sent.append(t) or True, now=5.0)
    assert row["after"] == "refused" and "unchanged" in sent[0], "the bar's bench cannot be lifted by the routine"
    (form_env / ops_watch.ESCALATION_FILE).write_text(json.dumps({"id": "b1", "kind": "wallet_action", "wallet": "0xa", "action": "bench", "message": "losing days"}))
    assert ops_watch.deliver_escalation(send=lambda t: False, now=6.0) is None
    assert (form_env / ops_watch.ESCALATION_FILE).exists(), "not delivered: kept for the next pass"
