"""The AI analyst (s-qbzbrw): once a day, priced proposals, limits inside
their bands, code to a branch and the owner, never to main."""
from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

from src.config import CONFIG
from src.copy_trading import live_limits, ops_watch

NOW = 1_789_800_000.0        # 2026-09-22 ~ 16:53 UTC? (a fixed instant; hour computed from it)
_SPEC = importlib.util.spec_from_file_location(
    "ai_analyst", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "ai_analyst.py")
an = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(an)


@pytest.fixture
def desk(tmp_path, monkeypatch):
    data = tmp_path / "data"; data.mkdir()
    for mod in (CONFIG, an.CONFIG, live_limits.CONFIG, ops_watch.CONFIG):
        monkeypatch.setattr(mod, "data_dir", str(data))
    monkeypatch.setattr(CONFIG, "live_max_per_wallet_day", 3)
    monkeypatch.setattr(CONFIG, "copy_paper_b_ledger", str(data / "book_b.jsonl"))
    monkeypatch.setenv("ANALYST_ENABLED", "true")
    monkeypatch.setattr(an, "HOUR_UTC", 0)
    (data / "book_b.jsonl").write_text("")
    return data


def _history(data, rows):
    with open(data / "trade-history.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _book_b(data, rows):
    with open(data / "book_b.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            base = {"copy_id": r["copy_id"], "target": r["target"], "condition_id": "c", "token_id": r["token_id"],
                    "outcome_index": 0, "category": "sports", "their_price": 0.5, "entry_price": 0.5, "shares": 40.0,
                    "spent": 20.0, "drag_bps": 100, "opened_ts": NOW - 86400, "closed": True, "won": r["pnl"] > 0,
                    "pnl": r["pnl"], "ideal_pnl": r["pnl"], "closed_ts": NOW - 3600}
            f.write(json.dumps(base) + "\n")


def _runner_for(obj, cost=0.3):
    calls = []
    def runner(prompt):
        calls.append(prompt)
        return {"result": json.dumps(obj), "total_cost_usd": cost, "subtype": "success"}
    runner.calls = calls
    return runner


def _sender():
    sent = []
    def send(t):
        sent.append(t); return True
    send.sent = sent
    return send


def _fakes():
    calls = {"apply": [], "push": []}
    def apply(diff, *, fp, message, **kw):
        calls["apply"].append((fp, message)); return (True, "abc1234", "1500 passed at abc1234")
    def push(fp, *, branch, **kw):
        calls["push"].append((fp, branch)); return (True, branch or "main")
    return calls, apply, push


def test_the_counterfactual_prices_declined_copies_from_the_paper_book(desk):
    ms = (NOW - 100) * 1000
    _history(desk, [
        {"status": "SKIPPED", "side": "BUY", "reason": "0xabc wallet out of form: form record stale (157 h)", "trader_address": "0xW1", "token_id": "t1", "received_at_ms": ms},
        {"status": "SKIPPED", "side": "BUY", "reason": "0xabc wallet out of form: form record stale (159 h)", "trader_address": "0xW1", "token_id": "t2", "received_at_ms": ms},
        {"status": "SKIPPED", "side": "BUY", "reason": "probation share: 2 of 2", "trader_address": "0xW2", "token_id": "t3", "received_at_ms": ms},
        {"status": "SKIPPED", "side": "SELL", "reason": "SELL skipped", "trader_address": "0xW2", "token_id": "t3", "received_at_ms": ms},
        {"status": "PLACED", "side": "BUY", "reason": "", "trader_address": "0xW3", "token_id": "t4", "received_at_ms": ms},
    ])
    _book_b(desk, [{"copy_id": "a", "target": "0xw1", "token_id": "t1", "pnl": 20.0},     # +100% at $20 spent
                   {"copy_id": "b", "target": "0xw1", "token_id": "t2", "pnl": -20.0}])   # -100%
    cf = an.counterfactual(NOW - 86400, stake_usd=6.4)
    assert cf["declined_total"] == 3 and cf["placed_total"] == 1
    form = cf["by_reason"]["<hex> wallet out of form: form record stale (N h)"]
    assert form["declined"] == 2 and form["priced"] == 2 and form["won"] == 1 and form["pnl_usd"] == 0.0
    prob = cf["by_reason"]["probation share: N of N"]
    assert prob["declined"] == 1 and prob["priced"] == 0
    lines = an.counterfactual_lines(cf)
    assert lines[0].startswith("declined BUY signals: 3, placed: 1")
    assert any("2 priced at their price: 1 would have won, +0.00 USD" in l for l in lines)
    assert any("none settled in book B yet (unpriced)" in l for l in lines)
    assert all("—" not in l for l in lines)


def test_off_by_default_and_once_a_day(desk, monkeypatch):
    monkeypatch.setenv("ANALYST_ENABLED", "false")
    runner = _runner_for({"proposals": [], "summary": "quiet"})
    assert an.maybe_run(NOW, runner=runner, send=_sender()) is None and runner.calls == []
    monkeypatch.setenv("ANALYST_ENABLED", "true")
    s = an.maybe_run(NOW, runner=runner, send=_sender())
    assert s == {"proposals": 0, "acted": [], "cost_usd": 0.3} and len(runner.calls) == 1
    assert an.maybe_run(NOW + 3600, runner=runner, send=_sender()) is None and len(runner.calls) == 1, "once a day"
    assert an.maybe_run(NOW + 86400, runner=runner, send=_sender()) is not None and len(runner.calls) == 2
    rows = ops_watch.watcher_thoughts()
    assert rows and rows[-1]["kind"] == "analyst" and rows[-1]["concluded"] == "quiet"


def test_the_prompt_carries_the_counterfactual_and_the_bands(desk):
    runner = _runner_for({"proposals": [], "summary": "s"})
    an.maybe_run(NOW, runner=runner, send=_sender())
    p = runner.calls[0]
    assert "LIVE_MAX_PER_WALLET_DAY: band 1..3 (money)" in p and "declined BUY signals" in p
    assert "never propose raising exposure" in p and "—" not in p


def test_a_limit_proposal_is_bounded_by_the_band_and_announced(desk):
    send = _sender()
    v = {"proposals": [
        {"kind": "limit", "name": "LIVE_MAX_PER_WALLET_DAY", "value": 2, "why": "2 of 5 copies from one wallet lost", "counterfactual": "-12.80 USD"},
        {"kind": "limit", "name": "LIVE_BUDGET_USD", "value": 200, "why": "more", "counterfactual": "x"},
    ], "summary": "one limit"}
    s = an.maybe_run(NOW, runner=_runner_for(v), send=send)
    assert s["proposals"] == 2
    assert live_limits.current("LIVE_MAX_PER_WALLET_DAY", NOW + 1) == 2
    assert "limit applied" in s["acted"][0] and "limit refused" in s["acted"][1]
    assert len(send.sent) == 1 and "moved a limit for a day" in send.sent[0] and "—" not in send.sent[0]
    kinds = [r["kind"] for r in ops_watch.ledger_rows()]
    assert kinds.count("analyst_limit") == 1 and kinds.count("analyst_limit_refused") == 1


SAFE = "--- a/poly_poly_bot/src/copy_trading/patterns.py\n+++ b/poly_poly_bot/src/copy_trading/patterns.py\n@@ -1 +1 @@\n-a\n+b\n"
MONEY = "--- a/poly_poly_bot/src/copy_trading/trade_executor.py\n+++ b/poly_poly_bot/src/copy_trading/trade_executor.py\n@@ -1 +1 @@\n-a\n+b\n"
FORBID = "--- a/poly_poly_bot/scripts/ai_analyst.py\n+++ b/poly_poly_bot/scripts/ai_analyst.py\n@@ -1 +1 @@\n-a\n+b\n"


@pytest.mark.parametrize("diff", [SAFE, MONEY])
def test_every_code_proposal_goes_to_a_branch_never_main(desk, diff):
    calls, apply, push = _fakes()
    send = _sender()
    v = {"proposals": [{"kind": "pr", "title": "feat(x): try it", "diff": diff, "why": "3 fills a day", "counterfactual": "+4.10 USD"}], "summary": "s"}
    s = an.maybe_run(NOW, runner=_runner_for(v), send=send, apply=apply, push=push)
    assert calls["push"] and calls["push"][0][1].startswith("analyst/") and calls["push"][0][1] != "main"
    assert "owner asked to merge" in s["acted"][0]
    assert any("compare/main...analyst/" in m and "+4.10 USD" in m for m in send.sent)


def test_a_forbidden_diff_is_refused_and_the_model_is_asked_once(desk):
    calls, apply, push = _fakes()
    v = {"proposals": [{"kind": "pr", "title": "x", "diff": FORBID, "why": "w", "counterfactual": "c"}], "summary": "s"}
    runner = _runner_for(v)
    s = an.maybe_run(NOW, runner=runner, send=_sender(), apply=apply, push=push)
    assert calls["apply"] == [] and "pr refused" in s["acted"][0] and len(runner.calls) == 1


def test_an_expensive_study_does_nothing(desk, monkeypatch):
    monkeypatch.setattr(an, "MAX_USD", 1.0)
    calls, apply, push = _fakes()
    v = {"proposals": [{"kind": "limit", "name": "LIVE_MAX_PER_WALLET_DAY", "value": 1, "why": "w"}], "summary": "s"}
    s = an.maybe_run(NOW, runner=_runner_for(v, cost=3.0), send=_sender(), apply=apply, push=push)
    assert s["proposals"] == 0 and live_limits.current("LIVE_MAX_PER_WALLET_DAY", NOW + 1) == 3


def test_garbage_from_the_model_is_a_ledger_row(desk):
    s = an.maybe_run(NOW, runner=lambda p: {"result": "nope", "total_cost_usd": 0.1}, send=_sender())
    assert s["proposals"] == 0 and ops_watch.watcher_thoughts()[-1]["concluded"] == "no usable answer"
    assert an.parse({"result": '{"proposals": "not a list"}'}) is None


# --------------------------------------------------------------------------- #
# s-ye5990: studies and experiments
# --------------------------------------------------------------------------- #

from src.copy_trading import exp_cards  # noqa: E402

CARD = {"kind": "experiment", "id": "min150", "title": "slice floor 150", "hypothesis": "37 declined winners at 150..300",
        "knobs": {"min_usd": 150}, "win_bar": {"roi_pp": 2.0, "min_n": 10}, "kill_bar": {"roi_pp": -3.0, "min_n": 10}, "max_days": 14}


def test_an_experiment_proposal_writes_the_card_and_goes_live_the_second_queues(desk):
    calls, apply, push = _fakes()
    send = _sender()
    s = an.maybe_run(NOW, runner=_runner_for({"proposals": [CARD], "summary": "s"}), send=send, apply=apply, push=push)
    assert "experiment min150 live" in s["acted"][0] and exp_cards.live_card()["id"] == "min150"
    assert calls["apply"] == [] and calls["push"] == [], "a knob-only card needs no code"
    assert any("experiment <code>min150</code> live" in m and "<blockquote expandable>" in m for m in send.sent)
    second = {**CARD, "id": "min150-first", "knobs": {"min_usd": 150, "first_entry_only": True}, "parent_id": "min150"}
    s2 = an.maybe_run(NOW + 86400, runner=_runner_for({"proposals": [second], "summary": "s"}), send=send, apply=apply, push=push)
    assert "experiment min150-first queued" in s2["acted"][0] and exp_cards.next_queued()["id"] == "min150-first"
    assert ops_watch.ledger_rows()[-1]["kind"] == "analyst_experiment"


def test_a_bad_card_is_refused_and_only_one_study_or_experiment_a_day(desk):
    calls, apply, push = _fakes()
    bad = {**CARD, "win_bar": {"roi_pp": 0.5, "min_n": 10}}
    v = {"proposals": [bad, {**CARD, "id": "second"}], "summary": "s"}
    s = an.maybe_run(NOW, runner=_runner_for(v), send=_sender(), apply=apply, push=push)
    assert s["proposals"] == 1 and "experiment refused: win bar" in s["acted"][0] and exp_cards.cards() == []


def test_a_code_experiment_lands_on_its_branch_and_never_on_main(desk):
    calls, apply, push = _fakes()
    cloned = []
    diff = ("--- a/poly_poly_bot/src/copy_trading/trade_executor.py\n+++ b/poly_poly_bot/src/copy_trading/trade_executor.py\n"
            "@@ -1 +1 @@\n-a\n+if exp_flag.on(\"wide_band\"): b\n")
    card = {**CARD, "id": "wide-band", "knobs": {}, "diff": diff, "flag": "wide_band"}
    s = an.maybe_run(NOW, runner=_runner_for({"proposals": [card], "summary": "s"}), send=_sender(), apply=apply, push=push,
                     clone=lambda b, d: (cloned.append((b, d)) or (True, "cloned")))
    assert calls["push"] == [("exp-wide-band", "exp/wide-band")] and cloned[0][0] == "exp/wide-band"
    c = exp_cards.load("wide-band")
    assert c["branch"] == "exp/wide-band" and c["diff_class"] == "money" and c["status"] == "live"
    assert "live" in s["acted"][0]
    forbidden = {**card, "id": "no-deploy", "diff": diff.replace("src/copy_trading/trade_executor.py", "deploy.sh")}
    s2 = an.maybe_run(NOW + 86400, runner=_runner_for({"proposals": [forbidden], "summary": "s"}), send=_sender(), apply=apply, push=push)
    assert "experiment refused: forbidden path" in s2["acted"][0] and exp_cards.load("no-deploy") is None


def test_code_that_does_not_land_voids_the_card(desk):
    calls, apply, push = _fakes()
    diff = "--- a/poly_poly_bot/src/copy_trading/patterns.py\n+++ b/poly_poly_bot/src/copy_trading/patterns.py\n@@ -1 +1 @@\n-a\n+if exp_flag.on(\"f\"): b\n"
    card = {**CARD, "id": "red", "knobs": {}, "diff": diff, "flag": "f"}
    s = an.maybe_run(NOW, runner=_runner_for({"proposals": [card], "summary": "s"}), send=_sender(),
                     apply=lambda *a, **k: (False, "", "suite red: 1 failed"), push=push)
    assert "experiment red void: suite red" in s["acted"][0] and exp_cards.load("red")["status"] == "void"
    assert exp_cards.live_card() is None


def _study_stub(kind, params, *, now, question=""):
    rec = {"id": f"2026-09-25-{kind}-abcd1234", "kind": kind, "params": params, "question": question, "ts": now, "inputs_hash": "abcd",
           "settings": {"from": {}, "to": {}}, "rows": [],
           "totals": {"wallets_in_from": 11, "wallets_in_to": 19, "copies_from": 61, "copies_to": 104, "roi_from": 0.031, "roi_to": 0.014,
                      "stay": 11, "enter": 8, "leave": 0, "out": 11, "unread": 0},
           "totals_line": "wallets in 11 -> 19; copies 61 -> 104; ROI +3.1% -> +1.4%",
           "caveat": "estimate: 30 of 41 wallets studied"}
    p, w = exp_cards.freeze_study(rec["id"], "# study\n", rec)
    return rec, p, w


def test_a_study_runs_freezes_goes_to_the_phone_and_is_read_back_once(desk):
    calls, apply, push = _fakes()
    send = _sender()
    answers = [{"proposals": [{"kind": "study", "study": "min_usd", "params": {"from": 300, "to": 150}, "question": "300 to 150?"}], "summary": "s"},
               {"conclusion": "19 wallets at 150, 8 more; ROI falls to +1.4%.", "card": {**CARD, "id": "min150"}}]
    prompts = []

    def runner(prompt):
        prompts.append(prompt)
        return {"result": json.dumps(answers[len(prompts) - 1]), "total_cost_usd": 4.0, "subtype": "success"}
    s = an.maybe_run(NOW, runner=runner, send=send, apply=apply, push=push, study=_study_stub)
    assert len(prompts) == 2 and "wallets in 11 -> 19" in prompts[1] and "study_ref" in prompts[1]
    assert s["cost_usd"] == 8.0 and s["proposals"] == 2
    assert "study 2026-09-25-min_usd-abcd1234 frozen" in s["acted"][0]
    assert any("<blockquote expandable>" in m and "estimate: 30 of 41" in m for m in send.sent)
    assert any("on study <code>2026-09-25-min_usd-abcd1234</code>: 19 wallets" in m for m in send.sent)
    live = exp_cards.live_card()
    assert live["id"] == "min150" and live["study_ref"] == "2026-09-25-min_usd-abcd1234"
    st = json.loads((desk / "ops-analyst-state.json").read_text())
    import time as _t
    assert st["spent"][_t.strftime("%Y-%m-%d", _t.gmtime(NOW))] == 8.0
    kinds = [r["kind"] for r in ops_watch.ledger_rows()]
    assert "analyst_study" in kinds and "analyst_experiment" in kinds
    assert "min_usd: params" in prompts[0] and "# Experiment in flight" in prompts[0]


def test_the_days_budget_stops_the_read_back(desk, monkeypatch):
    monkeypatch.setattr(an, "MAX_USD", 5.0)
    prompts = []

    def runner(prompt):
        prompts.append(prompt)
        return {"result": json.dumps({"proposals": [{"kind": "study", "study": "min_usd", "params": {"to": 150}}], "summary": "s"}),
                "total_cost_usd": 4.0, "subtype": "success"}
    an.maybe_run(NOW, runner=runner, send=_sender(), study=_study_stub)
    assert len(prompts) == 1, "the second call would cross the day's cap"


def _books(desk, exp_id, rows_c, rows_t):
    d = desk / "exp" / exp_id
    for name, rows in (("control.jsonl", rows_c), ("treatment.jsonl", rows_t), ("../../book_b.jsonl", rows_c)):
        with open(d / name, "w", encoding="utf-8") as f:
            for i, (target, roi, opened) in enumerate(rows):
                f.write(json.dumps({"copy_id": f"{name}-{i}", "target": target, "condition_id": f"c{i}", "token_id": f"t{i}",
                                    "outcome_index": 0, "category": "sports", "their_price": 0.5, "entry_price": 0.5, "shares": 40.0,
                                    "spent": 20.0, "drag_bps": 100, "opened_ts": opened, "closed": True, "won": roi > 0,
                                    "pnl": roi * 20, "ideal_pnl": roi * 20, "closed_ts": opened + 7200}) + "\n")


def test_the_daily_check_wins_to_a_branch_for_the_owner_never_main(desk):
    calls, apply, push = _fakes()
    send = _sender()
    exp_cards.create({k: v for k, v in CARD.items() if k != "kind"}, NOW); exp_cards.launch("min150", NOW)
    rows = [("0xw1" if i % 2 else "0xw2", 0.3 if i % 3 else -1.0, NOW + 8 * 3600 * i) for i in range(12)]
    _books(desk, "min150", rows, [(t, r + 0.2, o) for t, r, o in rows])
    day = NOW + 5 * 86400
    s = an.maybe_run(day, runner=_runner_for({"proposals": [], "summary": "quiet"}), send=send, apply=apply, push=push)
    assert calls["push"] == [("exp-min150-win", "analyst/exp-min150")]
    fp, message = calls["apply"][0]
    assert fp == "exp-min150-win" and "won its bars" in message
    assert any("WON" in m and "compare/main...analyst/exp-min150" in m and "Merge it" in m for m in send.sent)
    assert exp_cards.load("min150")["status"] == "win"
    rows_ = [r for r in ops_watch.watcher_thoughts() if r.get("proposal") == "experiment"]
    assert rows_ and "branch analyst/exp-min150 pushed" in rows_[-1]["did"]
    assert exp_cards.line(day + 60).startswith("\U0001f9ea exp min150 WIN")
    assert an.maybe_run(day + 3600, runner=_runner_for({"proposals": [], "summary": "q"}), send=send, apply=apply, push=push) is None
    assert len(calls["push"]) == 1, "concluded once"


def test_the_daily_check_kills_with_one_line_and_frees_the_queue(desk):
    calls, apply, push = _fakes()
    send = _sender()
    exp_cards.create({k: v for k, v in CARD.items() if k != "kind"}, NOW); exp_cards.launch("min150", NOW)
    exp_cards.create({**{k: v for k, v in CARD.items() if k != "kind"}, "id": "next-one"}, NOW + 1)
    rows = [("0xw1" if i % 2 else "0xw2", 0.3 if i % 3 else -1.0, NOW + 8 * 3600 * i) for i in range(12)]
    _books(desk, "min150", rows, [(t, r - 0.2, o) for t, r, o in rows])
    an.maybe_run(NOW + 5 * 86400, runner=_runner_for({"proposals": [], "summary": "quiet"}), send=send, apply=apply, push=push)
    assert calls["push"] == [] and exp_cards.load("min150")["status"] == "kill"
    assert any("experiment <code>min150</code> KILL:" in m for m in send.sent)
    sv = an.supervise(NOW + 5 * 86400 + 120, spawn=lambda c: 4242, alive=lambda p: False, stop=lambda p: None)
    assert sv["live"] == "next-one" and "started next-one" in sv["did"]


def test_the_supervisor_keeps_one_process_up_and_voids_a_card_that_will_not_stay_up(desk, monkeypatch):
    exp_cards.create({k: v for k, v in CARD.items() if k != "kind"}, NOW); exp_cards.launch("min150", NOW)
    spawned, stopped = [], []
    up = {"alive": False}
    spawn = lambda c: spawned.append(c["id"]) or 100 + len(spawned)
    alive = lambda pid: up["alive"]
    sv = an.supervise(NOW, spawn=spawn, alive=alive, stop=stopped.append)
    assert spawned == ["min150"] and "pid 101" in sv["did"]
    up["alive"] = True
    assert an.supervise(NOW + 60, spawn=spawn, alive=alive, stop=stopped.append)["did"] == "", "up: nothing to do"
    up["alive"] = False
    assert an.supervise(NOW + 120, spawn=spawn, alive=alive, stop=stopped.append)["did"] == "", "too soon to restart"
    an.supervise(NOW + an.SPAWN_MIN_GAP_S + 1, spawn=spawn, alive=alive, stop=stopped.append)
    assert spawned == ["min150", "min150"]
    # a heartbeat gone stale while the pid is alive: stop and restart
    up["alive"] = True
    exp_cards.write_heartbeat("min150", pid=102, cycles=3, rss_mb=120.0, now=NOW + an.SPAWN_MIN_GAP_S + 2)
    t = NOW + 2 * an.SPAWN_MIN_GAP_S + an.HEARTBEAT_STALE_S + 10
    an.supervise(t, spawn=spawn, alive=alive, stop=stopped.append)
    assert stopped == [102] and len(spawned) == 3
    # the fifth start in a day is the last: the card voids and the phone hears
    monkeypatch.setattr(an, "MAX_SPAWNS_PER_DAY", 3)
    up["alive"] = False
    send = _sender()
    sv = an.supervise(t + an.SPAWN_MIN_GAP_S + 1, spawn=spawn, alive=alive, stop=stopped.append, send=send)
    assert "void" in sv["did"] and exp_cards.load("min150")["status"] == "void" and len(spawned) == 3
    assert any("VOID" in m and "would not stay up" in m for m in send.sent)
    # a concluded card's process is stopped
    up["alive"] = True
    st = json.loads((desk / "ops-analyst-state.json").read_text())
    st["exp"]["min150"]["pid"] = 103
    (desk / "ops-analyst-state.json").write_text(json.dumps(st))
    an.supervise(t + 2 * an.SPAWN_MIN_GAP_S, spawn=spawn, alive=alive, stop=stopped.append)
    assert stopped[-1] == 103


def test_supervise_is_off_with_the_analyst(desk, monkeypatch):
    monkeypatch.setenv("ANALYST_ENABLED", "false")
    assert an.supervise(NOW, spawn=lambda c: 1, alive=lambda p: False, stop=lambda p: None) == {"live": None, "did": "off"}


def test_the_child_environment_has_no_key_and_writes_under_the_card(desk, monkeypatch):
    monkeypatch.setenv("PRIVATE_KEY", "0xsecret"); monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    env = an._child_env({"id": "min150"}, str(desk / "exp" / "min150"))
    assert "PRIVATE_KEY" not in env and "TELEGRAM_BOT_TOKEN" not in env
    assert env["DATA_DIR"] == str(desk / "exp" / "min150" / "scratch") and env["LIVE_ARM_ENABLED"] == "false"
    assert env["EXP_REAL_DATA_DIR"] == str(desk) and env["LOGS_DIR"].endswith("/exp/min150")
