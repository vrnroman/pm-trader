"""The owner's limits of 2026-09-26, pinned.

"Remove the 3 trades per address. The only limits: 1 trade a day per new
wallet for 7 days, 20 for the others. No limit on how much per day is bet,
only on how much is lost: more than 45 a day, disarm and wait for my
instructions." And the AI SRE, woken by an error, may read the whole log
before it concludes.
"""
from __future__ import annotations

import json
import os
import time

import pytest

from src.config import CONFIG
from src.copy_trading import daily_spend_guard as g, live_budget, live_guard, live_mode, zset

NOW = 1_790_400_000.0  # 2026-09-26 05:20 UTC
DAY = "2026-09-26"


@pytest.fixture
def box(tmp_path, monkeypatch):
    for mod in (CONFIG, live_mode.CONFIG, live_guard.CONFIG, zset.promotion_state.CONFIG):
        monkeypatch.setattr(mod, "data_dir", str(tmp_path))
    monkeypatch.setattr(g, "_STATE_FILE", str(tmp_path / "daily-spend.json"))
    g.reset_state()
    monkeypatch.setattr(CONFIG, "live_arm_enabled", True)
    monkeypatch.setattr(CONFIG, "live_budget_usd", 80.0)
    monkeypatch.setattr(live_budget, "DAILY_ABS", None)
    monkeypatch.setattr(live_budget, "FLOOR_ABS", None)
    return tmp_path


def _arm_record(tmp_path, **rec):
    with open(live_mode._path(), "w", encoding="utf-8") as f:
        json.dump(rec, f)


# ---- no daily spend cap, a daily LOSS stop instead ----

def test_the_loss_stop_switches_the_spend_cap_off_entirely(box, monkeypatch):
    monkeypatch.setattr(CONFIG, "live_daily_loss_usd", 0.0)
    assert live_budget.daily_loss_stop_usd() is None
    assert live_budget.daily_cap(live=False) < float("inf"), "without the stop the old spend cap stands"
    monkeypatch.setattr(CONFIG, "live_daily_loss_usd", 45.0)
    assert live_budget.daily_loss_stop_usd() == 45.0
    assert live_budget.daily_cap(live=False) == float("inf")
    assert live_budget.caps(live=False).daily_usd == float("inf")
    assert g.can_spend(10_000.0) == (True, "")
    ok, why = g.reserve_spend(10_000.0, source="test")
    assert ok and why == ""
    st = g.status()
    assert st["spent_usd"] == 10_000.0 and st["cap_usd"] is None and st["remaining_usd"] is None
    assert st["daily_loss_stop_usd"] == 45.0
    assert json.dumps(st), "the money state stays valid JSON (no Infinity)"
    assert g.cap_text(float("inf")) == "no spend cap (the day stops after $45 lost)"
    line = "\n".join(live_budget.status_lines(live=False))
    assert "per day: no spend cap, stops after $45 lost" in line and "$inf" not in line


def test_should_self_disarm_fires_on_more_than_the_daily_loss_only():
    assert live_guard.should_self_disarm(loss_today_usd=45.0, daily_loss_usd=45.0)[0] is False, "45 is not more than 45"
    fires, why = live_guard.should_self_disarm(loss_today_usd=45.01, daily_loss_usd=45.0)
    assert fires and why.startswith("lost $45.01 today") and "/live CONFIRM" in why
    assert live_guard.is_daily_loss_reason(why) and not live_guard.is_floor_reason(why)
    assert live_guard.should_self_disarm(loss_today_usd=None, daily_loss_usd=45.0)[0] is False, "unknown is not a loss"
    assert live_guard.should_self_disarm(loss_today_usd=90.0, daily_loss_usd=None)[0] is False, "no stop set"
    assert live_guard.should_self_disarm(loss_today_usd=-20.0, daily_loss_usd=45.0)[0] is False, "a gain"


def test_loss_today_is_measured_from_the_first_equity_of_the_utc_day():
    st: dict = {}
    assert live_guard.loss_today(st, None, NOW) is None and st == {}, "no equity, no baseline, no number"
    assert live_guard.loss_today(st, 119.29, NOW) == 0.0
    assert st["day_equity"]["day"] == DAY and st["day_equity"]["start"] == 119.29
    assert live_guard.loss_today(st, 70.0, NOW + 3600) == 49.29
    assert live_guard.loss_today(st, None, NOW + 7200) is None, "an unreadable pass says nothing"
    assert st["day_equity"]["start"] == 119.29, "the baseline holds all day"
    # 00:00 UTC next day: a new baseline from the first readable equity
    assert live_guard.loss_today(st, 70.0, NOW + 86400) == 0.0
    assert st["day_equity"]["day"] == "2026-09-27" and st["day_equity"]["start"] == 70.0


def test_the_guard_disarms_on_the_daily_loss_and_the_owners_arm_silences_it_for_the_day(box, monkeypatch):
    monkeypatch.setattr(CONFIG, "live_daily_loss_usd", 45.0)
    sent: list = []
    _arm_record(box, armed=True, ts=NOW - 60, by="telegram", reason="", first_armed_ts=NOW - 60)
    out = live_guard.run_once(redeemable=[], equity_usd=119.29, floor_usd=30.0, send=sent.append, now=NOW)
    assert out["armed"] and not out["self_disarmed"], "the first pass sets the day's baseline"
    out = live_guard.run_once(redeemable=[], equity_usd=80.0, floor_usd=30.0, send=sent.append, now=NOW + 600)
    assert not out["self_disarmed"], "down 39.29: under the stop"
    out = live_guard.run_once(redeemable=[], equity_usd=70.0, floor_usd=30.0, send=sent.append, now=NOW + 1200)
    assert out["self_disarmed"] and out["disarm_reason"].startswith("lost $49.29 today")
    arm = live_mode.read_arm()
    assert arm["armed"] is False and arm["by"] == live_mode.DAILY_LOSS_DISARM_BY
    assert any("Self-disarmed" in m and "lost $49.29" in m for m in sent)
    # the stop is the owner's to override: it does not block his arm...
    assert live_guard.active_block() is None
    # ...and the watcher never arms it back on its own
    from src.copy_trading import ops_watch
    assert ops_watch.maybe_rearm(arm=arm, guard_state=live_guard._read_state(), condition_clear=True, now=NOW + 5000) is None
    # the owner arms again (his instruction): the arm record carries the day
    monkeypatch.setattr(CONFIG, "preview_mode", False)
    monkeypatch.setattr(CONFIG, "strategy1_enabled", True)
    ok, detail = live_mode.arm(reason="owner: go on", by="telegram", now=NOW + 1800)
    assert ok, detail
    assert live_mode.read_arm()["daily_loss_override_day"] == DAY
    out = live_guard.run_once(redeemable=[], equity_usd=60.0, floor_usd=30.0, send=sent.append, now=NOW + 2400)
    assert out["armed"] and not out["self_disarmed"], "quiet for the rest of the day, at his word"
    # the next UTC day counts from its own 00:00 and the stop is live again
    out = live_guard.run_once(redeemable=[], equity_usd=60.0, floor_usd=30.0, send=sent.append, now=NOW + 86400)
    assert not out["self_disarmed"] and live_guard._read_state()["day_equity"]["start"] == 60.0
    out = live_guard.run_once(redeemable=[], equity_usd=10.0, floor_usd=5.0, send=sent.append, now=NOW + 86400 + 600)
    assert out["self_disarmed"] and out["disarm_reason"].startswith("lost $50.00 today")


def test_an_ordinary_arm_carries_no_override(box, monkeypatch):
    monkeypatch.setattr(CONFIG, "preview_mode", False)
    monkeypatch.setattr(CONFIG, "strategy1_enabled", True)
    _arm_record(box, armed=False, ts=NOW, by="telegram", reason="")
    ok, _ = live_mode.arm(reason="", by="telegram")
    assert ok and live_mode.read_arm()["daily_loss_override_day"] is None


# ---- the per-wallet rule ----

def test_a_wallet_is_new_for_seven_days_from_its_z_admission(box, monkeypatch):
    w = "0x" + "a" * 40
    # The record as the gate writes it (see zset.admit): wallet, source, ts.
    monkeypatch.setattr(zset.promotion_state, "promoted_map",
                        lambda scope: {w: {"wallet": w, "source": "gate", "tier": "1b", "ts": NOW},
                                       "0xhand": {"wallet": "0xhand", "source": "hand", "ts": NOW},
                                       "0xnots": {"wallet": "0xnots", "source": "gate"}})
    monkeypatch.setattr(zset, "evicted_set", lambda: set())
    assert zset.admitted_ts("0xnobody") is None and not zset.is_new("0xnobody")
    assert zset.admitted_ts("0xhand") is None, "not the gate's record: not in Z, so not new"
    assert zset.admitted_ts("0xnots") is None and not zset.is_new("0xnots"), "no time on record: not new"
    ts = zset.admitted_ts(w)
    assert ts == NOW
    assert zset.is_new(w, now=ts + 6.9 * 86400)
    assert not zset.is_new(w, now=ts + 7.0 * 86400)
    monkeypatch.setattr(CONFIG, "zset_new_wallet_days", 3.0)
    assert not zset.is_new(w, now=ts + 4 * 86400)


def test_the_two_caps_and_nothing_else(box, monkeypatch):
    monkeypatch.setattr(CONFIG, "live_max_per_wallet_day", 20)
    monkeypatch.setattr(CONFIG, "zset_new_wallet_copies_per_day", 1)
    monkeypatch.setattr(zset, "is_new", lambda w, now=None: w.lower().startswith("0xnew"))
    g.record_wallet_copy("0xNEW1")
    ok, why = g.can_copy_wallet("0xNEW1")
    assert not ok and why == "new-wallet cap (first 7 days in set Z): 1 of 1 copies from 0xNEW1 already today"
    assert g.can_copy_wallet("0xNEW2") == (True, "")
    for _ in range(19):
        g.record_wallet_copy("0xOLD")
    assert g.can_copy_wallet("0xOLD") == (True, "")
    g.record_wallet_copy("0xOLD")
    ok, why = g.can_copy_wallet("0xOLD")
    assert not ok and why.startswith("per-wallet daily cap: 20 of 20")
    # an unreadable Z record reads as new: the tighter rule
    def boom(w, now=None):
        raise OSError("disk")
    monkeypatch.setattr(zset, "is_new", boom)
    g.record_wallet_copy("0xOTHER")
    assert g.can_copy_wallet("0xOTHER")[0] is False
    assert CONFIG.live_max_per_wallet_day == 20 or os.environ.get("LIVE_MAX_PER_WALLET_DAY")


# ---- the AI SRE reads the whole log ----

def test_the_sre_runner_hands_the_model_read_tools_over_the_bot_logs(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("ai_sre_t", os.path.join(os.path.dirname(__file__), "..", "scripts", "ai_sre.py"))
    sre = importlib.util.module_from_spec(spec); spec.loader.exec_module(sre)
    cmd = sre.runner_cmd("/usr/bin/claude", "hello", logs_dir=str(tmp_path))
    assert cmd[:3] == ["/usr/bin/claude", "-p", "hello"] and "--output-format" in cmd and "json" in cmd
    i = cmd.index("--allowedTools")
    tools = cmd[i + 1]
    assert "Read" in tools and "Grep" in tools and "Bash(grep:*)" in tools
    assert "Edit" not in tools and "Write" not in tools and "Bash(rm" not in tools, "read only"
    assert cmd[cmd.index("--add-dir") + 1] == str(tmp_path)
    assert cmd[cmd.index("--max-turns") + 1] == str(sre.MAX_TURNS) and sre.MAX_TURNS >= 10
    assert "--add-dir" not in sre.runner_cmd("/usr/bin/claude", "x", logs_dir=str(tmp_path / "missing"))


def test_the_log_census_counts_what_worked_next_to_what_failed(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("ai_sre_t2", os.path.join(os.path.dirname(__file__), "..", "scripts", "ai_sre.py"))
    sre = importlib.util.module_from_spec(spec); spec.loader.exec_module(sre)
    now = NOW
    lines = []
    for i in range(300):
        t = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now - 3000 + i * 10))
        lines.append(f"{t} INFO  Onchain: cursor 9447{i:04d}, head 9447{i:04d}, lag 0 block(s)")
    for i in range(6):
        t = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now - 2000 + i * 100))
        lines.append(f"{t} ERROR Error fetching CTF events [94469969-94469969]: {{'code': -32000}}")
    old = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now - 7200))
    lines.append(f"{old} ERROR ancient line outside the window")
    (tmp_path / f"bot-{DAY}.log").write_text("\n".join(lines) + "\n")
    assert sre.log_files(str(tmp_path), now) == [f"bot-{DAY}.log"]
    rows = sre.log_census(str(tmp_path), now, minutes=60)
    assert rows[0].startswith("306 lines in the last 60 min; 2 kinds")
    assert any("300  INFO Onchain: cursor N, head" in r for r in rows)
    assert any("  6  ERROR Error fetching CTF events" in r for r in rows)
    assert not any("ancient" in r for r in rows)
    assert sre.log_census(str(tmp_path / "none"), now) == ["(no bot-YYYY-MM-DD.log in the logs dir)"]
