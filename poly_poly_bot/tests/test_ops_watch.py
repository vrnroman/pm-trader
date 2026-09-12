"""The watcher (run s-g8int5): receipts, the push policy, the absence clocks,
self re-arm with a cap, escalation delivery, probation, auto-admission."""
from __future__ import annotations

import json
import time

import pytest

from src.config import CONFIG
from src.copy_trading import ops_watch as ow


@pytest.fixture
def ops_env(tmp_path, monkeypatch):
    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(ow.CONFIG, "data_dir", str(tmp_path))
    return tmp_path


def _ledger(tmp_path):
    p = tmp_path / ow.LEDGER_FILE
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_the_split_is_one_regex_and_keeps_the_money_lines():
    keep = ["[LIVE] BUY $5.50 on 'x' @ 0.4500, order 0x4ec7", "[verify] FILLED: BUY 12.22 shares",
            "[live] DISARMED by canary, back to paper", "[exec] Tier 1b skip: Tier 1b exposure full: remaining=$-5.96",
            "[guard] could not read equity for the floor: x", "[disk-watch] TRIPPED: free 6.8G",
            "[AB-RACE] rehearsal line sent, real-money line SEND FAILED", "[tiered-risk] tier 1b: released $54.00",
            "ERROR [redeemer] cannot", "Traceback (most recent call last):"]
    drop = ["[exec] Tier 1b skip: Trader bet $31.73 < min_trader_bet $300.00 for tier 1b: BUY",
            "[DISCOVERY] LLM gate REJECTED 0xb1cab", "[guard] 61 resolved position(s) worth under $1 excluded",
            "[queue] Enqueued pending order", "[telegram] research message held (#19)"]
    assert all(ow.is_important(l) for l in keep), [l for l in keep if not ow.is_important(l)]
    assert not any(ow.is_important(l) for l in drop), [l for l in drop if ow.is_important(l)]


def test_a_receipt_is_one_factual_row(ops_env):
    ow.receipt("rearm", before="disarmed", after="armed", detail="feed clear 15 min", now=1000.0)
    rows = _ledger(ops_env)
    assert rows == [{"ts": 1000.0, "day": "1970-01-01", "kind": "rearm", "before": "disarmed",
                     "after": "armed", "detail": "feed clear 15 min", "push": None}]


def test_the_push_policy_at_a_67_dollar_bankroll(ops_env, monkeypatch):
    sent: list = []
    S = ow.Settlement
    # a $5 loss is under 15% of $67: ledger only
    out = ow.record_settlements([S("t1", "0xaaa", 5.5, 0.0, "1b", "Cruzeiro")],
                                equity=67.0, stated=80.0, floor=56.0, send=sent.append, now=1000.0)
    assert out == [] and sent == []
    # a $12 loss crosses 15%: push, and it also crosses the 10% day line: push once
    out = ow.record_settlements([S("t2", "0xaaa", 12.0, 0.0, "1b", "Big one")],
                                equity=67.0, stated=80.0, floor=56.0, send=sent.append, now=1100.0)
    assert any("Loss of $12.00" in m for m in sent) and any("Today's losses" in m for m in sent)
    n = len(sent)
    # four losses in a row (two already): third and fourth
    ow.record_settlements([S("t3", "0xbbb", 5.0, 0.0), S("t4", "0xbbb", 5.0, 0.0)],
                          equity=67.0, stated=80.0, floor=56.0, send=sent.append, now=1200.0)
    assert any("4 losing copies in a row" in m for m in sent[n:])
    # a win resets the streak and books a positive row
    ow.record_settlements([S("t5", "0xaaa", 5.0, 9.4, "1b", "Kuopion")],
                          equity=67.0, stated=80.0, floor=56.0, send=sent.append, now=1300.0)
    rows = [r for r in _ledger(ops_env) if r["kind"] == "settled"]
    assert rows[-1]["won"] is True and rows[-1]["pnl"] == 4.4
    st = json.loads((ops_env / ow.STATE_FILE).read_text())
    assert st["loss_streak"] == 0
    # no confidence numbers in any message
    assert not any("confidence" in m.lower() for m in sent)


def test_floor_distance_and_milestones_say_once(ops_env):
    sent: list = []
    ow.check_bankroll(equity=70.0, floor=56.0, send=sent.append, now=1.0)
    assert sent == []
    ow.check_bankroll(equity=66.0, floor=56.0, send=sent.append, now=2.0)  # within 20% of 56 (67.2)
    assert len(sent) == 1 and "within 20%" in sent[0] and "top-up" in sent[0]
    ow.check_bankroll(equity=65.0, floor=56.0, send=sent.append, now=3.0)
    assert len(sent) == 1, "said once"
    # hovering around the band edge does not flap: clear needs floor x 1.3
    ow.check_bankroll(equity=68.0, floor=56.0, send=sent.append, now=4.0)
    ow.check_bankroll(equity=66.0, floor=56.0, send=sent.append, now=5.0)
    assert len(sent) == 1, "still inside the hysteresis band"
    ow.check_bankroll(equity=74.0, floor=56.0, send=sent.append, now=6.0)   # clear
    ow.check_bankroll(equity=66.0, floor=56.0, send=sent.append, now=7.0)   # back in, same day: no push
    assert len(sent) == 1
    ow.check_bankroll(equity=74.0, floor=56.0, send=sent.append, now=90000.0)
    ow.check_bankroll(equity=66.0, floor=56.0, send=sent.append, now=90001.0)  # next day: one push
    assert len(sent) == 2
    ow.check_bankroll(equity=49.0, floor=40.0, send=sent.append, now=4.0)
    assert any("fell under $50" in m for m in sent)
    ow.check_bankroll(equity=101.0, floor=40.0, send=sent.append, now=5.0)
    assert any("crossed $100" in m for m in sent) and any("crossed $50" in m for m in sent)


def test_a_guard_loop_that_keeps_failing_is_escalated_once(ops_env):
    sent: list = []
    for i in range(ow.GUARD_FAIL_STREAK + 3):
        ow.note_guard_pass(False, "module has no attribute note_collectable", now=float(i), send=sent.append)
    assert len(sent) == 1 and "failed 6 passes" in sent[0] and "note_collectable" in sent[0]
    ow.note_guard_pass(True, now=99.0, send=sent.append)
    assert [r["kind"] for r in _ledger(ops_env)][-1] == "guard_recovered"


def test_no_copy_for_days_while_wallets_traded_is_escalated_once(ops_env):
    sent: list = []
    ow.check_absences(followed_signals_3d=7, copies_3d=0, armed=True, send=sent.append, now=1000.0)
    ow.check_absences(followed_signals_3d=9, copies_3d=0, armed=True, send=sent.append, now=2000.0)
    assert len(sent) == 1 and "No copy in 3 days" in sent[0]
    ow.check_absences(followed_signals_3d=9, copies_3d=1, armed=True, send=sent.append, now=3000.0)
    ow.check_absences(followed_signals_3d=9, copies_3d=0, armed=False, send=sent.append, now=4000.0)
    assert len(sent) == 1, "not while disarmed, not while copies land"


def test_a_missing_daily_line_is_noticed_by_nine_utc(ops_env):
    sent: list = []
    day0 = 1_788_652_800.0  # 2026-09-06 00:00 UTC
    ow.note_daily_line(True, now=day0 + 8 * 3600)
    ow.check_absences(followed_signals_3d=0, copies_3d=0, armed=True, send=sent.append, now=day0 + 86400 + 8.5 * 3600)
    assert sent == [], "before 09:00 nothing"
    ow.check_absences(followed_signals_3d=0, copies_3d=0, armed=True, send=sent.append, now=day0 + 86400 + 9.2 * 3600)
    assert len(sent) == 1 and "No 08:00 real-money line" in sent[0]
    ow.check_absences(followed_signals_3d=0, copies_3d=0, armed=True, send=sent.append, now=day0 + 86400 + 10 * 3600)
    assert len(sent) == 1, "once per day"


def test_transient_disarms_self_clear_after_fifteen_minutes_with_a_cap(ops_env, monkeypatch):
    sent: list = []
    arms: list = []
    arm_fn = lambda reason="", by="": (arms.append((reason, by)) or (True, "armed"))
    arm = {"armed": False, "by": "live-guard", "ts": 0.0}
    gs = {"self_disarm_reason": "no trade data for 20 minutes: the poller is dead"}
    assert ow.maybe_rearm(arm=arm, guard_state=gs, condition_clear=True, now=0.0, send=sent.append, arm_fn=arm_fn) is None
    assert ow.maybe_rearm(arm=arm, guard_state=gs, condition_clear=True, now=600.0, send=sent.append, arm_fn=arm_fn) is None
    row = ow.maybe_rearm(arm=arm, guard_state=gs, condition_clear=True, now=1000.0, send=sent.append, arm_fn=arm_fn)
    assert row and row["after"] == "armed" and len(arms) == 1 and arms[0][1].startswith("watcher:")
    assert "Re-armed" in sent[-1] and "1 of 3" in sent[-1]
    # a flap resets the clock
    assert ow.maybe_rearm(arm=arm, guard_state=gs, condition_clear=False, now=1100.0, send=sent.append, arm_fn=arm_fn) is None
    for t in (1200.0, 2200.0):
        ow.maybe_rearm(arm=arm, guard_state=gs, condition_clear=True, now=t, send=sent.append, arm_fn=arm_fn)
    for t in (2300.0, 3300.0):
        ow.maybe_rearm(arm=arm, guard_state=gs, condition_clear=True, now=t, send=sent.append, arm_fn=arm_fn)
    assert len(arms) == 3
    for t in (3400.0, 4400.0, 4500.0):
        ow.maybe_rearm(arm=arm, guard_state=gs, condition_clear=True, now=t, send=sent.append, arm_fn=arm_fn)
    assert len(arms) == 3 and any("keeps coming back" in m for m in sent)
    # the floor never self-clears; the owner's own disarm is his
    assert ow.maybe_rearm(arm={"armed": False, "by": "live-guard:floor"}, guard_state={"self_disarm_reason": "bankroll $50 is under the floor"},
                          condition_clear=True, now=99999.0, send=sent.append, arm_fn=arm_fn) is None
    assert ow.maybe_rearm(arm={"armed": False, "by": "telegram"}, guard_state=gs, condition_clear=True, now=99999.0, send=sent.append, arm_fn=arm_fn) is None
    assert len(arms) == 3


def test_an_escalation_from_the_routine_is_sent_once_and_moved_aside(ops_env):
    sent: list = []
    (ops_env / ow.ESCALATION_FILE).write_text(json.dumps({"id": "v-001", "kind": "escalation", "message": "the fills stopped at 14:00"}))
    row = ow.deliver_escalation(send=sent.append, now=1.0)
    assert row and len(sent) == 1 and "fills stopped" in sent[0]
    assert not (ops_env / ow.ESCALATION_FILE).exists()
    (ops_env / ow.ESCALATION_FILE).write_text(json.dumps({"id": "v-001", "kind": "escalation", "message": "again"}))
    assert ow.deliver_escalation(send=sent.append, now=2.0) is None and len(sent) == 1, "same id, not resent"
    (ops_env / ow.ESCALATION_FILE).write_text("{broken")
    assert ow.deliver_escalation(send=sent.append, now=3.0) is None


def test_probation_caps_a_new_wallet_until_five_settled(ops_env):
    ow.probation_start("0xNEW", now=1.0)
    assert ow.probation_cap("0xnew") == 1 and ow.probation_cap("0xold") is None
    for i in range(4):
        ow.record_settlements([ow.Settlement(f"t{i}", "0xNEW", 5.0, 9.0)], equity=67.0, stated=80.0, floor=56.0, send=None, now=10.0 + i)
    assert ow.probation_cap("0xnew") == 1
    ow.record_settlements([ow.Settlement("t9", "0xNEW", 5.0, 0.0)], equity=67.0, stated=80.0, floor=56.0, send=None, now=20.0)
    assert ow.probation_cap("0xnew") is None
    assert any(r["kind"] == "probation_over" for r in _ledger(ops_env))


def test_the_weekly_line_is_computed_from_the_ledger(ops_env):
    ow.record_settlements([ow.Settlement("a", "0x1", 5.0, 9.0), ow.Settlement("b", "0x1", 6.0, 0.0)],
                          equity=67.0, stated=80.0, floor=56.0, send=None, now=time.time())
    ow.receipt("auto_admit", before="x", after="y", now=time.time())
    line = ow.weekly_line()
    assert "2 settled (1 won)" in line and "realized -2.00" in line and "1 auto-admission" in line
    assert "—" not in line and "–" not in line


def test_auto_admission_goes_through_the_gate_and_starts_probation(ops_env, monkeypatch):
    from src.copy_trading import ops_admit, zset, zset_candidates as zc
    class C:
        def __init__(self, w): self.wallet, self.ok, self.settled, self.paper_roi = w, True, [1] * 34, 0.091
    monkeypatch.setattr(zc, "load_books", lambda: (0.0, [], []))
    monkeypatch.setattr(zc, "candidates", lambda b, a, era, now, wallets=None: ([C("0xAAA"), C("0xBBB"), C("0xCCC")], [], None))
    monkeypatch.setattr(zset, "wallet_set", lambda: {"0xbbb"})
    monkeypatch.setattr(zset, "evicted_set", lambda: {"0xccc"})
    admitted_calls: list = []
    def admit(w, *, era, b_positions, a_positions, now=None):
        admitted_calls.append(w); return (True, [], C(w))
    monkeypatch.setattr(zc, "admit", admit)
    sent: list = []
    got = ops_admit.scan(send=lambda text, kb: sent.append((text, kb)), now=5.0)
    assert got == ["0xaaa"] and admitted_calls == ["0xaaa"], "in Z and evicted are skipped; the door is zc.admit"
    assert ow.probation_cap("0xaaa") == 1
    assert sent and "Admitted to set Z on its own" in sent[0][0] and sent[0][1]["inline_keyboard"][0][0]["callback_data"] == "zevict:0xaaa"
    assert "34 settled paper copies" in sent[0][0] and "paper ROI +9.1%" in sent[0][0]
    rows = _ledger(ops_env)
    assert rows[-1]["kind"] == "auto_admit" and rows[-1]["push"] == "WALLET"
    monkeypatch.setenv("ZSET_AUTO_ADMIT", "false")
    assert ops_admit.scan(send=None, now=6.0) == []


def test_a_refused_admission_is_a_receipt_not_a_push(ops_env, monkeypatch):
    from src.copy_trading import ops_admit, zset, zset_candidates as zc
    class C:
        def __init__(self, w): self.wallet, self.ok, self.settled = w, True, []
    monkeypatch.setattr(zc, "load_books", lambda: (0.0, [], []))
    monkeypatch.setattr(zc, "candidates", lambda b, a, era, now, wallets=None: ([C("0xAAA")], [], None))
    monkeypatch.setattr(zset, "wallet_set", lambda: set())
    monkeypatch.setattr(zset, "evicted_set", lambda: set())
    monkeypatch.setattr(zc, "admit", lambda w, **k: (False, [("real-quote ROI above the bar", False, "+2%")], None))
    sent: list = []
    assert ops_admit.scan(send=lambda t, kb: sent.append(t), now=5.0) == [] and sent == []
    assert _ledger(ops_env)[-1]["kind"] == "auto_admit_refused"


# ---- the wiring: the seams the watcher hangs on ----

def test_release_by_token_takes_that_orders_row(monkeypatch, tmp_path):
    """Verifier r5 caveat 1: an unfilled copy released the OLDEST row, not its
    own, and the reconcile then dropped its token too (under-count)."""
    from src.copy_trading import tiered_risk_manager as trm
    monkeypatch.setattr(trm, "_STATE_FILE", str(tmp_path / "t.json"))
    trm.reset_state()
    trm.record_tiered_placement("1b", 6.0, token_id="tokA", now=1.0, trader="0xA", title="a")
    trm.record_tiered_placement("1b", 5.0, token_id="tokB", now=2.0, trader="0xB", title="b")
    trm.release_tiered_exposure("1b", 5.0, token_id="tokB")
    exp = trm._tier_exposures["1b"]
    assert [r["token_id"] for r in exp.placements] == ["tokA"] and exp.open_total == 6.0
    assert exp.placements[0]["trader"] == "0xa" and exp.placements[0]["title"] == "a"
    rows: list = []
    trm.reconcile_tiered_exposure(resolved_tokens={"tokB"}, live_tokens={"tokA"}, now=3.0, rows_out=rows)
    assert exp.open_total == 6.0 and rows == []


def test_probation_caps_through_the_real_per_wallet_check(ops_env, monkeypatch):
    from src.copy_trading import daily_spend_guard as g
    monkeypatch.setattr(g, "_STATE_FILE", str(ops_env / "d.json"))
    monkeypatch.setattr(CONFIG, "live_max_per_wallet_day", 2)
    g.reset_state()
    ow.probation_start("0xNEW", now=1.0)
    g.record_wallet_copy("0xNEW")
    ok, why = g.can_copy_wallet("0xNEW")
    assert ok is False and "probation cap: 1 of 1" in why
    g.record_wallet_copy("0xOLD")
    assert g.can_copy_wallet("0xOLD") == (True, "")


def test_the_evict_button_evicts_and_receipts(ops_env, monkeypatch):
    from src import telegram_bot as tb
    from src.copy_trading import zset
    calls: list = []
    monkeypatch.setattr(zset, "evict", lambda w, reason="": calls.append((w, reason)) or True)
    toast, text = tb._handle_callback("zevict:0xabc")
    assert toast == "Evicted" and "Evicted from set Z" in text and calls == [("0xabc", "owner tap (Evict button)")]
    rows = _ledger(ops_env)
    assert rows[-1]["kind"] == "evict" and rows[-1]["wallet"] == "0xabc"
    assert "—" not in text


def test_the_important_file_receives_only_important_lines(tmp_path, monkeypatch):
    import logging

    from src import logger as lg
    monkeypatch.setenv("LOGS_DIR", str(tmp_path))
    bl = lg.BotLogger()
    bl.info("[LIVE] BUY $5.50 on 'x' @ 0.4500, order 0xabc")
    bl.info("[queue] Enqueued pending order 0xabc")
    bl.warn("[live] DISARMED by canary, back to paper")
    for h in bl._logger.handlers:
        try:
            h.flush()
        except Exception:
            pass
    files = list(tmp_path.glob("important-*.log"))
    assert len(files) == 1, files
    text = files[0].read_text()
    assert "[LIVE] BUY" in text and "DISARMED" in text and "Enqueued" not in text
    for h in list(bl._logger.handlers):
        bl._logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass


def test_the_guard_reports_whether_the_disarm_condition_holds(tmp_path, monkeypatch):
    from src.copy_trading import live_guard, live_mode
    for mod in (live_guard, live_mode):
        monkeypatch.setattr(mod.CONFIG, "data_dir", str(tmp_path))
    out = live_guard.run_once(feed_stale_s=3600, now=1000.0)
    assert out["disarm_condition"] is True
    out = live_guard.run_once(feed_stale_s=10, now=2000.0)
    assert out["disarm_condition"] is False


def test_main_wires_the_watcher_into_the_guard_loop_and_the_daily_line():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "main.py").read_text()
    for needle in ("ops_watch.record_settlements(", "ops_watch.check_bankroll(", "ops_watch.check_absences(",
                   "ops_watch.maybe_rearm(", "ops_watch.deliver_escalation(", "ops_watch.note_guard_pass(",
                   "ops_admit.scan(", "ops_watch.write_money_state(", "_ow.daily_line()", "_ow.note_daily_line("):
        assert needle in src, needle
    i = src.index("rows_out=released_rows"); j = src.index("ops_watch.record_settlements(")
    assert i < j, "settlements are booked from the rows the reconcile released"


def test_followed_activity_counts_signals_and_copies(tmp_path, monkeypatch):
    import json as _json
    import main as app_main
    from src.copy_trading import trade_store, zset
    monkeypatch.setattr(trade_store, "_HISTORY_FILE", str(tmp_path / "h.jsonl"))
    monkeypatch.setattr(zset, "wallet_set", lambda: {"0xz"})
    monkeypatch.setattr(CONFIG, "copy_paper_min_usd", 300.0)
    now = 1_788_700_000.0
    rows = [
        {"trader_address": "0xZ", "side": "BUY", "status": "SKIPPED", "trader_size": 900.0, "received_at_ms": (now - 100) * 1000},
        {"trader_address": "0xZ", "side": "BUY", "status": "SKIPPED", "trader_size": 30.0, "received_at_ms": (now - 100) * 1000},
        {"trader_address": "0xZ", "side": "BUY", "status": "PLACED", "trader_size": 900.0, "received_at_ms": (now - 50) * 1000},
        {"trader_address": "0xother", "side": "BUY", "status": "SKIPPED", "trader_size": 900.0, "received_at_ms": (now - 50) * 1000},
        {"trader_address": "0xZ", "side": "BUY", "status": "SKIPPED", "trader_size": 900.0, "received_at_ms": (now - 4 * 86400) * 1000},
    ]
    (tmp_path / "h.jsonl").write_text("\n".join(_json.dumps(r) for r in rows) + "\n")
    assert app_main._followed_activity_3d(now) == (2, 1)


def test_the_wallet_ledger_is_an_aggregation_over_settled_rows(ops_env):
    S = ow.Settlement
    ow.record_settlements([S("a", "0xAAA", 5.0, 9.0), S("b", "0xAAA", 6.0, 0.0), S("c", "0xBBB", 5.5, 11.0)],
                          equity=67.0, stated=80.0, floor=56.0, send=None, now=time.time())
    rows = ow.wallet_ledger()
    assert rows == [{"wallet": "0xaaa", "settled": 2, "won": 1, "pnl": -2.0, "cost": 11.0},
                    {"wallet": "0xbbb", "settled": 1, "won": 1, "pnl": 5.5, "cost": 5.5}]
    lines = ow.wallet_ledger_lines()
    assert lines[0] == "0xaaa: 2 settled, 1 won, -2.00 on $11.00" and "\u2014" not in "".join(lines)
    from src import telegram_bot as tb
    sent: list = []
    import src.telegram_bot as _tbm
    orig = _tbm.send_message
    _tbm.send_message = lambda text, **k: sent.append(text) or True
    try:
        tb._handle_ops("/ops wallet 0xaaa")
    finally:
        _tbm.send_message = orig
    assert sent and "0xaaa: 2 settled, 1 won, -2.00 on $11.00" in sent[0] and "0xbbb" not in sent[0]


def test_the_graduation_receipt_carries_its_trial(ops_env):
    ow.probation_start("0xNEW", now=1.0)
    for i in range(5):
        ow.record_settlements([ow.Settlement(f"t{i}", "0xNEW", 5.0, 9.0 if i % 2 == 0 else 0.0, "1b", f"m{i}")],
                              equity=67.0, stated=80.0, floor=56.0, send=None, now=10.0 + i)
    row = [r for r in _ledger(ops_env) if r["kind"] == "probation_over"][-1]
    assert row["after"] == "5 settled live copies: 3 won, +2.00" and len(row["trial"]) == 5
    assert row["trial"][0]["token_id"] == "t0" and row["trial"][1]["won"] is False


def test_the_admit_scan_clock_survives_a_restart(ops_env):
    import pathlib
    ow.note_admit_scan(now=1234.0)
    assert json.loads((ops_env / ow.STATE_FILE).read_text())["admit_scan_ts"] == 1234.0
    src = (pathlib.Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert 'get("admit_scan_ts")' in src and "ops_watch.note_admit_scan(_now)" in src


def test_probationers_share_two_copies_a_day_between_them(ops_env, monkeypatch):
    """Manager r3: seven probationers at one copy a day each could take every
    slot of a four-copy day from the proven wallets; together they get two."""
    from src.copy_trading import daily_spend_guard as g
    monkeypatch.setattr(g, "_STATE_FILE", str(ops_env / "d.json"))
    monkeypatch.setattr(CONFIG, "live_max_per_wallet_day", 2)
    g.reset_state()
    for w in ("0xP1", "0xP2", "0xP3"):
        ow.probation_start(w, now=1.0)
    assert g.can_copy_wallet("0xP1") == (True, "")
    g.record_wallet_copy("0xP1")
    assert g.can_copy_wallet("0xP2") == (True, "")
    g.record_wallet_copy("0xP2")
    ok, why = g.can_copy_wallet("0xP3")
    assert ok is False and "probation share: 2 of 2" in why, why
    # a proven wallet is untouched by the share
    assert g.can_copy_wallet("0xOLD") == (True, "")
    # graduation frees the share
    monkeypatch.setattr(ow, "PROBATION_TOTAL_PER_DAY", 3)
    assert g.can_copy_wallet("0xP3") == (True, "")


def test_the_scan_admits_one_wallet_per_pass(ops_env, monkeypatch):
    from src.copy_trading import ops_admit, zset, zset_candidates as zc
    class C:
        def __init__(self, w): self.wallet, self.ok, self.settled, self.paper_roi = w, True, [1] * 34, 0.1
    monkeypatch.setattr(zc, "load_books", lambda: (0.0, [], []))
    monkeypatch.setattr(zc, "candidates", lambda b, a, era, now, wallets=None: ([C("0xA"), C("0xB")], [], None))
    monkeypatch.setattr(zset, "wallet_set", lambda: set())
    monkeypatch.setattr(zset, "evicted_set", lambda: set())
    monkeypatch.setattr(zc, "admit", lambda w, **k: (True, [], C(w)))
    assert ops_admit.scan(send=None, now=5.0) == ["0xa"]


# ---- verifier s-g8int5 r1: the two production seams ----

def test_self_rearm_fires_through_the_real_guard(ops_env, monkeypatch):
    """The guard pops its reason on the pass the condition clears, which is
    the pass the watcher runs on, so the re-arm never fired. The reason now
    rides on the arm record and stays in the guard's state."""
    from src.copy_trading import live_guard, live_mode
    for mod in (live_guard, live_mode):
        monkeypatch.setattr(mod.CONFIG, "data_dir", str(ops_env))
    monkeypatch.setattr(live_mode.CONFIG, "live_arm_enabled", True)
    monkeypatch.setattr(live_mode.CONFIG, "preview_mode", False)
    monkeypatch.setattr(live_mode.CONFIG, "strategy1_enabled", True)
    monkeypatch.setattr(live_mode, "_hard_disarmed", False)
    ok, why = live_mode.arm(reason="t", by="test")
    assert ok, why
    t0 = 1_788_700_000.0
    out = live_guard.run_once(feed_stale_s=3600, now=t0)
    assert out["self_disarmed"] is True and live_mode.read_arm()["by"] == "live-guard"
    assert "no trade data" in live_mode.read_arm()["reason"]
    arms: list = []
    sent: list = []
    def arm_fn(reason="", by=""):
        arms.append(by); return live_mode.arm(reason=reason, by=by)
    for k, t in enumerate((t0 + 300, t0 + 600, t0 + 900, t0 + 1200, t0 + 1500)):
        out = live_guard.run_once(feed_stale_s=10, now=t)
        ow.maybe_rearm(arm=live_mode.read_arm(), guard_state=live_guard._read_state(),
                       condition_clear=not out["disarm_condition"], now=t, send=sent.append, arm_fn=arm_fn)
    assert len(arms) == 1 and arms[0].startswith("watcher:") and live_mode.read_arm()["armed"] is True
    assert any("Re-armed" in m for m in sent)


def test_the_important_file_is_written_in_a_fresh_process(tmp_path):
    """The logger built its important handler from ops_watch, which imports
    the logger back; the circular import was swallowed and no file was ever
    written on the VM. The grammar is a leaf module now."""
    import os
    import subprocess
    import sys
    code = ("from src.logger import logger; logger.info('[LIVE] BUY $5 on x'); "
            "logger.info('[queue] Enqueued pending order'); "
            "import logging; [h.flush() for h in logging.getLogger('poly_poly_bot').handlers]")
    env = {**os.environ, "PREVIEW_MODE": "true", "LOGS_DIR": str(tmp_path)}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), env=env)
    assert out.returncode == 0, out.stderr[-500:]
    files = list(tmp_path.glob("important-*.log"))
    assert len(files) == 1, (files, out.stderr[-300:])
    text = files[0].read_text()
    assert "[LIVE] BUY" in text and "Enqueued" not in text


def test_the_same_settlement_offered_twice_books_once(ops_env):
    rows = [ow.Settlement("tX", "0xA", 5.0, 9.0), ow.Settlement("tY", "0xA", 5.0, 0.0)]
    ow.record_settlements(rows, equity=67.0, stated=80.0, floor=56.0, send=None, now=1.0)
    ow.record_settlements(rows, equity=67.0, stated=80.0, floor=56.0, send=None, now=2.0)
    settled = [r for r in _ledger(ops_env) if r["kind"] == "settled"]
    assert len(settled) == 2
    assert json.loads((ops_env / ow.STATE_FILE).read_text())["day_pnl"] == -1.0


def test_a_corrupt_escalation_file_goes_aside_and_is_logged(ops_env, caplog):
    import logging
    (ops_env / ow.ESCALATION_FILE).write_text("{broken")
    with caplog.at_level(logging.DEBUG):
        assert ow.deliver_escalation(send=None, now=7.0) is None
    assert not (ops_env / ow.ESCALATION_FILE).exists()
    assert [p for p in ops_env.iterdir() if p.name.startswith(ow.ESCALATION_FILE + ".bad-")]
    assert any("escalation file unreadable" in r.getMessage() for r in caplog.records)


def test_the_probation_share_applies_even_when_the_per_wallet_cap_is_one(ops_env, monkeypatch):
    from src.copy_trading import daily_spend_guard as g
    monkeypatch.setattr(g, "_STATE_FILE", str(ops_env / "d.json"))
    monkeypatch.setattr(CONFIG, "live_max_per_wallet_day", 1)
    g.reset_state()
    for w in ("0xP1", "0xP2", "0xP3"):
        ow.probation_start(w, now=1.0)
    g.record_wallet_copy("0xP1"); g.record_wallet_copy("0xP2")
    ok, why = g.can_copy_wallet("0xP3")
    assert ok is False and "probation share" in why
