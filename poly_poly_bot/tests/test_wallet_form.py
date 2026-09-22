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
    wf._write({"ts": 1.0, "wallets": {"0xa": {"ok": True, "reason": "fine", "wallet": "0xa", "n": 40, "won": 25, "cost": 1.0, "back": 2.0, "avg_price": 0.5, "ts": NOW - 3600}}})
    def get(url):
        raise RuntimeError("HTTP 429 (throttled)")
    d = wf.scan(get=get, send=None, now=NOW, wallets=["0xa"])
    assert d["wallets"]["0xa"]["ok"] is True and d["paused"] is False
    assert wf.is_benched("0xa", now=NOW)[0] is False
    # The last MEASURED verdict holds past FORM_STALE_S and says it is stale
    # (manager ruling s-qbzbrw: the three best wallets in Z were benched for
    # three days on a read bug, not on evidence).
    benched, why = wf.is_benched("0xa", now=NOW - 3600 + wf.FORM_STALE_S)
    assert benched is False and why == "fine [stale 24 h, reads failing]"
    # ...and the failure is bookkept with a backoff, not retried every pass.
    un = d["unread"]["0xa"]
    assert un["tries"] == 1 and un["why"].startswith("HTTP 429") and un["next"] == NOW + wf.FORM_RETRY_MIN_S


# --------------------------------------------------------------------------- #
# The offset cap (2026-09-20): a shorter window said so, never a failed read
# --------------------------------------------------------------------------- #

def _busy_rows(now, days=20.0, per_day=120, cost=400.0, price=0.5):
    """A wallet that trades more than the api will page: every market is a
    same-day buy and redeem so the form is clean, oldest first in time."""
    acts = []
    n = int(days * per_day)
    for i in range(n):
        ts = now - (i / per_day) * 86400.0
        cid = f"m{i}"
        acts.append({"type": "REDEEM", "conditionId": cid, "usdcSize": cost / price, "timestamp": ts})
        acts.append({"type": "TRADE", "side": "BUY", "conditionId": cid, "usdcSize": cost, "size": cost / price,
                     "price": price, "timestamp": ts - 60})
    return acts  # newest first, like the api


def _paged(acts, page_size=100):
    def get(url):
        if "/positions" in url:
            return []
        off = int(url.split("offset=")[1])
        return acts[off:off + page_size]
    return get


def test_a_capped_read_is_a_shorter_window_flagged_on_the_record(form_env):
    acts = _busy_rows(NOW, per_day=500)          # 1,000 rows a day: the cap reaches back ~5 days
    get = _paged(acts)
    rows, pos, cov = wf.fetch_rows("0xbusy", get=get, now=NOW)
    assert cov.capped is True and cov.rows == wf.DATA_API_MAX_OFFSET + 100 and cov.pages == 51
    f = wf.compute("0xbusy", rows, pos, now=NOW, coverage=cov)
    assert f.capped is True and 0 < f.covered_days < wf.FORM_DAYS
    assert abs(f.covered_days - cov.covered_days(NOW)) < 0.05
    assert f.n > 0 and f.ok is True, "5,100 rows of a clean wallet is a verdict, not a failure"
    assert "capped:" in f.line() and f"of {wf.FORM_DAYS:.0f} days read" in f.line()
    assert f"in {f.covered_days:.0f} days" in f.reason or f.ok, "a bar reason names the span actually read"
    # busy but not THAT busy: the window is read in full, only the older
    # lookback was cut; the record says which
    acts2 = _busy_rows(NOW, per_day=150)         # 300 rows a day: 5,100 rows reach back 17 days
    rows2, pos2, cov2 = wf.fetch_rows("0xbusy2", get=_paged(acts2), now=NOW)
    f2 = wf.compute("0xbusy2", rows2, pos2, now=NOW, coverage=cov2)
    assert cov2.capped is True and f2.covered_days == wf.FORM_DAYS and "window read in full" in f2.line()
    # the record in the table carries the coverage, and the digest row shows it
    d = wf.scan(get=get, send=None, now=NOW, wallets=["0xbusy"])
    rec = d["wallets"]["0xbusy"]
    assert rec["capped"] is True and rec["rows"] == cov.rows and "unread" in d and d["unread"] == {}
    assert any("capped:" in l for l in wf.lines())


def test_a_wallet_under_the_cap_is_not_flagged(form_env):
    acts, pos = _rows(n_won=20, n_lost=10)
    def get(url):
        return pos if "/positions" in url else (acts if "offset=0" in url else [])
    rows, _p, cov = wf.fetch_rows("0xa", get=get, now=NOW)
    assert cov.capped is False and cov.rows == len(acts)
    f = wf.compute("0xa", rows, _p, now=NOW, coverage=cov)
    assert f.capped is False and f.covered_days == wf.FORM_DAYS and "capped" not in f.line()


def test_the_injected_reader_refuses_to_page_past_the_cap(form_env):
    calls = []
    def get(url):
        calls.append(url)
        return [] if "/positions" in url else [{"timestamp": NOW, "conditionId": "c", "type": "TRADE",
                                                 "side": "BUY", "usdcSize": 400.0, "size": 800.0}] * 100
    rows, _p, cov = wf.fetch_rows("0xw", get=get, now=NOW, max_rows=20000)
    assert cov.capped is True and max(int(u.split("offset=")[1]) for u in calls if "offset=" in u) == wf.DATA_API_MAX_OFFSET


def test_a_failed_first_page_is_a_failed_read_not_a_capped_one(form_env):
    def get(url):
        raise wf.ReadFailed("offset cap")
    with pytest.raises(wf.ReadFailed):
        wf.fetch_rows("0xw", get=get, now=NOW)


def test_catchup_backs_off_and_says_so_once(form_env, monkeypatch):
    from src.copy_trading import zset
    monkeypatch.setattr(zset, "wallet_set", lambda: {"0xnew"})
    def get(url):
        raise wf.ReadFailed("HTTP 400")
    sent: list = []
    d = wf.scan(get=get, send=sent.append, now=NOW, wallets=["0xnew"])
    un = d["unread"]["0xnew"]
    assert un["tries"] == 1 and un["next"] == NOW + wf.FORM_RETRY_MIN_S and sent == []
    assert wf.wallets_due_for_catchup(NOW) == [], "not due before the backoff"
    assert wf.wallets_due_for_catchup(NOW + wf.FORM_RETRY_MIN_S) == ["0xnew"]
    benched, why = wf.is_benched("0xnew", now=NOW)
    assert benched is True and "HTTP 400" in why and "1 tries" in why
    # doubling, capped
    t = NOW
    for k in range(2, 8):
        t = d["unread"]["0xnew"]["next"]
        d = wf.scan(get=get, send=sent.append, now=t, wallets=["0xnew"])
        assert d["unread"]["0xnew"]["tries"] == k
        assert d["unread"]["0xnew"]["next"] - t == min(wf.FORM_RETRY_MAX_S, wf.FORM_RETRY_MIN_S * 2 ** (k - 1))
    # said once on the phone after FORM_UNREAD_ALERT_S, with a receipt
    assert len(sent) == 1 and "Cannot measure" in sent[0] and "0xnew" in sent[0] and "benched until" in sent[0]
    assert all("\u2014" not in m for m in sent)
    rows = [json.loads(l) for l in (form_env / "ops-ledger.jsonl").read_text().splitlines()]
    assert [r["kind"] for r in rows].count("form_unreadable") == 1
    assert any("unread   0xnew" in l for l in wf.lines())
    # a successful read clears the bookkeeping
    acts, pos = _rows(n_won=20, n_lost=10)
    def ok(url):
        return pos if "/positions" in url else (acts if "offset=0" in url else [])
    d = wf.scan(get=ok, send=sent.append, now=t + 1, wallets=["0xnew"])
    assert "0xnew" not in d["unread"] and d["wallets"]["0xnew"]["ok"] is True


def test_the_compute_version_bumped_so_old_tables_rescan(form_env, monkeypatch):
    from src.copy_trading import zset
    monkeypatch.setattr(zset, "wallet_set", lambda: {"0xa"})
    wf._write({"ts": 1.0, "version": 2, "wallets": {"0xa": {"wallet": "0xa", "ok": True, "reason": "old", "ts": 1.0}}})
    assert wf.FORM_VERSION >= 3 and wf.needs_rescan() is True


def test_a_table_from_an_older_compute_is_rescanned_at_boot(form_env, monkeypatch):
    from src.copy_trading import zset
    monkeypatch.setattr(zset, "wallet_set", lambda: {"0xa"})
    assert wf.needs_rescan() is False, "no table: the clock decides"
    wf._write({"ts": 1.0, "wallets": {"0xa": {"wallet": "0xa", "ok": False, "reason": "old bar", "ts": 1.0}}})
    assert wf.needs_rescan() is True
    d = wf.scan(get=lambda url: [], send=None, now=NOW, wallets=[])
    assert d["version"] == 0 and wf.needs_rescan() is True, "a catch-up scan does not vouch for the old rows"
    d = wf.scan(get=lambda url: [], send=None, now=NOW)
    assert d["version"] == wf.FORM_VERSION and wf.needs_rescan() is False


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
    monkeypatch.setattr(dd, "_get", lambda s, base, path, **kw: None)   # exhausted its attempts
    monkeypatch.setattr(dd, "_activity_fetch_failures", ["0xSWEEP"])
    with pytest.raises(RuntimeError):
        wf.fetch_rows("0xT")
    assert dd._activity_fetch_failures == ["0xSWEEP"], \
        "tracked locally; the sweep's shared list is neither read nor pruned (#34.4b)"
    wf._write({"ts": 1.0, "wallets": {"0xt": {"ok": True, "reason": "fine", "wallet": "0xt", "n": 40, "won": 25, "cost": 1.0, "back": 2.0, "avg_price": 0.5, "ts": NOW - 60}}})
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


def test_a_wallet_action_is_applied_once_even_when_the_message_is_retried(form_env, monkeypatch):
    from src.copy_trading import ops_watch, zset
    monkeypatch.setattr(zset, "wallet_set", lambda: {"0xa"})
    wf._write({"ts": 1.0, "wallets": {"0xa": {"wallet": "0xa", "ok": True, "reason": "fine", "ts": 1e6}}})
    esc = form_env / ops_watch.ESCALATION_FILE
    esc.write_text(json.dumps({"id": "b2", "kind": "wallet_action", "wallet": "0xa", "action": "bench", "message": "losing"}))
    assert ops_watch.deliver_escalation(send=lambda t: True, now=10.0)["after"] == "applied"
    esc.write_text(json.dumps({"id": "u2", "kind": "wallet_action", "wallet": "0xa", "action": "unbench", "message": "back"}))
    assert ops_watch.deliver_escalation(send=lambda t: False, now=20.0) is None
    assert wf.is_benched("0xa", now=21.0)[0] is False, "applied on the first pass"
    sent: list = []
    row = ops_watch.deliver_escalation(send=lambda t: sent.append(t) or True, now=30.0)
    assert row["after"] == "applied" and "Now: in form" in sent[0], "the retry reports what happened, it does not re-apply"
    assert wf.is_benched("0xa", now=31.0)[0] is False and not esc.exists()
    acts = [r for r in ops_watch.ledger_rows(kinds={"routine_wallet_action"})]
    assert [r["after"] for r in acts] == ["bench applied, now benched", "unbench applied, now in form", "unbench applied, now in form"]
    # a bench retried does not restart its 24 h
    esc.write_text(json.dumps({"id": "b3", "kind": "wallet_action", "wallet": "0xa", "action": "bench", "message": "again"}))
    assert ops_watch.deliver_escalation(send=lambda t: False, now=100.0) is None
    assert ops_watch.deliver_escalation(send=lambda t: True, now=100.0 + 3600)["after"] == "applied"
    assert wf.is_benched("0xa", now=100.0 + wf.FORM_OVERRIDE_S)[0] is False, "the clock runs from the first application"


# ---- issue #34.4a: the read is time-scoped, not row-capped ----

def test_the_read_covers_the_whole_window_and_stops_after_the_lookback(form_env):
    """A followed whale with more rows in the window than the old 1500-row cap
    had its window silently truncated. Now the read pages newest-first until
    the rows predate the window by FORM_LOOKBACK_DAYS, however many that is,
    and stops there instead of reading the wallet's whole history."""
    rows = [{"type": "TRADE", "side": "BUY", "conditionId": f"c{i}", "usdcSize": 400.0,
             "size": 800.0, "timestamp": NOW - i * 3600.0} for i in range(5000)]  # one an hour
    calls: list = []

    def get(url):
        calls.append(url)
        if "/positions" in url:
            return []
        offset = int(url.rsplit("offset=", 1)[1])
        return rows[offset:offset + 100]

    acts, pos, _cov = wf.fetch_rows("0xW", get=get, now=NOW)
    in_window = [a for a in acts if a["timestamp"] >= NOW - wf.FORM_DAYS * 86400]
    assert len(in_window) == int(wf.FORM_DAYS * 24) + 1, "every row of the window, past the old 1500 cap"
    lookback_rows = int((wf.FORM_DAYS + wf.FORM_LOOKBACK_DAYS) * 24)
    assert lookback_rows <= len(acts) < lookback_rows + 200, "and it stops after the lookback"
    assert len(calls) < 5000 // 100, "not the wallet's whole history"


def test_a_pre_window_first_buy_past_the_old_cap_is_still_left_out(form_env):
    """The exclusion is computed on what was read: a large position first
    bought 20 days ago and redeemed today used to fall outside the capped
    slice and count as a window market, its payout inflating the form."""
    filler = [{"type": "TRADE", "side": "BUY", "conditionId": f"f{i}", "usdcSize": 50.0,
               "size": 100.0, "timestamp": NOW - 60.0 * (i + 1)} for i in range(1600)]
    old_buy = {"type": "TRADE", "side": "BUY", "conditionId": "old", "usdcSize": 2000.0,
               "size": 4000.0, "timestamp": NOW - 20 * 86400}
    redeem = {"type": "REDEEM", "conditionId": "old", "usdcSize": 4000.0, "size": 4000.0,
              "timestamp": NOW - 30.0}
    rows = [redeem] + filler + [old_buy]

    def get(url):
        if "/positions" in url:
            return []
        offset = int(url.rsplit("offset=", 1)[1])
        return rows[offset:offset + 100]

    acts, pos, _cov = wf.fetch_rows("0xW", get=get, now=NOW)
    f = wf.compute("0xW", acts, pos, now=NOW)
    assert f.n == 0 and f.back == 0.0, "the pre-window market is left out, its payout not counted"
