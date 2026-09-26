"""The AI SRE on the box (s-qbzbrw): wakes on fingerprints, acts inside the
envelope, writes down what it did, and a second cycle over the same lines
does nothing twice."""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib

import pytest

from src.config import CONFIG
from src.copy_trading import live_mode, ops_fingerprint as fpm, ops_watch

NOW = 1_789_600_000.0
_SPEC = importlib.util.spec_from_file_location(
    "ai_sre", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "ai_sre.py")
sre = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sre)


@pytest.fixture
def box(tmp_path, monkeypatch):
    data = tmp_path / "data"; logs = tmp_path / "logs"
    data.mkdir(); logs.mkdir()
    for mod in (CONFIG, sre.CONFIG, fpm.CONFIG, ops_watch.CONFIG, live_mode.CONFIG):
        monkeypatch.setattr(mod, "data_dir", str(data))
    monkeypatch.setattr(fpm, "RATE_HITS", 50)
    (logs / "important-2026-09-22.log").write_text("")
    return {"data": data, "logs": logs, "log": logs / "important-2026-09-22.log"}


def _append(box, *lines):
    with open(box["log"], "a", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln + "\n")


def _runner_for(verdict: dict, cost=0.05):
    calls = []
    def runner(prompt):
        calls.append(prompt)
        return {"result": json.dumps(verdict), "total_cost_usd": cost, "subtype": "success"}
    runner.calls = calls
    return runner


def _sender():
    sent = []
    def send(text):
        sent.append(text)
        return True
    send.sent = sent
    return send


LINE = "2026-09-22 12:00:00 ERROR [exec] Order placement returned None for 'Will X win?'"
NOISE = "2026-09-22 12:00:01 INFO [exec] Tier 1b skip: Trade too old: 9.8h > 1.0h"


def test_only_important_lines_wake_and_the_second_cycle_is_silent(box):
    _append(box, NOISE, LINE)
    runner = _runner_for({"kind": "nothing", "reasoning": "benign"})
    s = sre.cycle(NOW, logs_dir=str(box["logs"]), runner=runner, send=_sender())
    assert s["lines"] == 1 and len(s["wake"]) == 1 and len(runner.calls) == 1
    assert s["acted"] == "nothing"
    s2 = sre.cycle(NOW + 120, logs_dir=str(box["logs"]), runner=runner, send=_sender())
    assert s2["lines"] == 0 and s2["wake"] == [] and len(runner.calls) == 1, "nothing read twice, nothing asked twice"
    _append(box, LINE)  # the same fault again: counted, not a wake
    s3 = sre.cycle(NOW + 240, logs_dir=str(box["logs"]), runner=runner, send=_sender())
    assert s3["lines"] == 1 and s3["wake"] == [] and len(runner.calls) == 1
    rows = sre.thoughts()
    assert len(rows) == 1 and rows[0]["kind"] == "nothing" and rows[0]["woke_because"]


def test_the_prompt_carries_the_evidence_not_the_raw_log(box):
    _append(box, LINE)
    runner = _runner_for({"kind": "note", "reasoning": "seen"})
    sre.cycle(NOW, logs_dir=str(box["logs"]), runner=runner, send=_sender())
    p = runner.calls[0]
    assert "Fingerprints that woke you" in p and "Order placement returned None for 'S'" in p
    assert "money:" in p and "arm:" in p and "two clocks" in p.lower()
    assert "—" not in p


def test_escalate_sends_one_line_and_a_receipt(box):
    _append(box, LINE)
    send = _sender()
    sre.cycle(NOW, logs_dir=str(box["logs"]), runner=_runner_for({"kind": "escalate", "message": "orders are not posting, 3 in a row"}), send=send)
    assert len(send.sent) == 1 and "AI SRE" in send.sent[0] and "3 in a row" in send.sent[0]
    kinds = [r["kind"] for r in ops_watch.ledger_rows()]
    assert kinds.count("sre_escalate") == 1
    assert all("—" not in m and "–" not in m for m in send.sent)


def test_disarm_uses_the_bots_own_path_and_never_arms(box):
    # The arm record as the bot writes it (arm() itself needs the interlock
    # keys the test box does not turn); the SRE's lever is this file.
    with open(live_mode._path(), "w", encoding="utf-8") as f:
        json.dump({"armed": True, "ts": NOW - 100, "by": "telegram", "reason": ""}, f)
    assert live_mode.read_arm()["armed"] is True
    _append(box, LINE)
    send = _sender()
    sre.cycle(NOW, logs_dir=str(box["logs"]), runner=_runner_for({"kind": "disarm", "reason": "orders may double"}), send=send)
    assert live_mode.is_armed() is False
    arm = live_mode.read_arm()
    assert arm["armed"] is False
    assert arm["by"] == "ai-sre" and "double" in arm["reason"]
    assert any("disarmed real money" in m for m in send.sent)
    assert [r["kind"] for r in ops_watch.ledger_rows()].count("sre_disarm") == 1
    # a second disarm verdict on an already-off bot changes nothing and says so
    _append(box, "2026-09-22 12:05:00 ERROR [x] another fault")
    sre.cycle(NOW + 200, logs_dir=str(box["logs"]), runner=_runner_for({"kind": "disarm", "reason": "again"}), send=send)
    assert live_mode.is_armed() is False and any("already off" in m for m in send.sent)
    assert not hasattr(sre, "arm"), "the SRE has no arm path at all"


SAFE_DIFF = ("--- a/poly_poly_bot/src/copy_trading/patterns.py\n+++ b/poly_poly_bot/src/copy_trading/patterns.py\n"
             "@@ -1 +1 @@\n-a\n+b\n")
MONEY_DIFF = ("--- a/poly_poly_bot/src/copy_trading/trade_executor.py\n+++ b/poly_poly_bot/src/copy_trading/trade_executor.py\n"
              "@@ -1 +1 @@\n-a\n+b\n")
FORBIDDEN_DIFF = ("--- a/poly_poly_bot/scripts/ai_sre.py\n+++ b/poly_poly_bot/scripts/ai_sre.py\n@@ -1 +1 @@\n-a\n+b\n")
TEST_EDIT_DIFF = ("--- a/poly_poly_bot/tests/test_x.py\n+++ b/poly_poly_bot/tests/test_x.py\n@@ -1 +1 @@\n-a\n+b\n")


def _fakes():
    calls = {"apply": [], "push": [], "revert": []}
    def apply(diff, *, fp, message, **kw):
        calls["apply"].append((fp, diff)); return (True, "abc1234", "1500 passed at abc1234")
    def push(fp, *, branch, **kw):
        calls["push"].append((fp, branch)); return (True, branch or "main")
    def revert(sha, *, fp, **kw):
        calls["revert"].append((sha, fp)); return (True, "def5678")
    return calls, apply, push, revert


def test_a_safe_fix_is_tested_pushed_to_main_and_announced(box, monkeypatch):
    monkeypatch.setattr(sre, "PUSH_MAIN", True)   # the owner's switch; off by default (next test)
    _append(box, LINE)
    calls, apply, push, revert = _fakes()
    send = _sender()
    s = sre.cycle(NOW, logs_dir=str(box["logs"]), send=send, apply=apply, push=push, revert=revert,
                  runner=_runner_for({"kind": "fix", "reasoning": "the None return is a missing await", "diff": SAFE_DIFF,
                                      "path_marker": "[exec] placed", "message": "fix(exec): await the post"}))
    assert calls["apply"] and calls["push"] == [(s["wake"][0], None)]
    assert "fix pushed to main (abc1234)" in s["acted"]
    assert any("pushed a fix" in m for m in send.sent)
    fp = s["wake"][0]
    st = sre._read_json(sre._p(sre.STATE_FILE))
    assert st["own_pushes"][fp]["sha"] == "abc1234" and st["markers"][fp] == "[exec] placed"
    assert fpm.proof(fp, NOW + 60)[0] == "unproven"


def test_by_default_every_fix_goes_to_a_branch_even_off_the_money_path(box):
    """Manager ruling s-qbzbrw round 2: a standing process pushing to main is
    a self-graded deploy check on a live-money box; SRE_PUSH_MAIN is off."""
    assert sre.PUSH_MAIN is False
    _append(box, LINE)
    calls, apply, push, revert = _fakes()
    send = _sender()
    s = sre.cycle(NOW, logs_dir=str(box["logs"]), send=send, apply=apply, push=push, revert=revert,
                  runner=_runner_for({"kind": "fix", "reasoning": "x", "diff": SAFE_DIFF, "path_marker": "[exec] placed"}))
    fp = s["wake"][0]
    assert calls["push"] == [(fp, f"sre/{fp}")] and "owner asked to merge" in s["acted"]
    assert any("SRE_PUSH_MAIN is off" in m and "compare/main..." in m for m in send.sent)


def test_the_sre_has_no_arm_path_and_writes_no_bot_ledger():
    """The envelope, pinned in CI (manager s-qbzbrw round 2): the sidecar's
    data mount is read-write because disarm is the bot's own path, so the
    file itself must prove it never arms and never writes a bot ledger."""
    import pathlib, re
    src = (pathlib.Path(__file__).resolve().parents[1] / "scripts" / "ai_sre.py").read_text()
    assert "live_mode.arm(" not in src and ".arm(" not in src.replace("disarm(", "")
    assert "hard_disarm" not in src or "hard_disarm(" not in src
    for ledger in ("trade-history.jsonl", "ops-ledger.jsonl", "seen-trades.json", "inventory.json",
                   "promoted_wallets_z.json", "copy_retired_z.json", "live_arm.json", "daily-spend.json"):
        # named in prose is fine; opened, joined or resolved as a path is not
        assert re.search(r"(open|os\.path\.join|_p)\([^\n]*" + re.escape(ledger), src) is None, \
            f"the SRE touches {ledger} directly; it must go through the bot's own functions or not at all"
    # its own files only, opened for append or write
    for m in re.finditer(r'open\(([^,]+),\s*"(a|w)"', src):
        assert "THOUGHTS_FILE" in m.group(1) or "tmp" in m.group(1) or "sre.patch" in m.group(1), m.group(0)


def test_a_money_path_fix_goes_to_a_branch_and_the_owner(box):
    _append(box, LINE)
    calls, apply, push, revert = _fakes()
    send = _sender()
    s = sre.cycle(NOW, logs_dir=str(box["logs"]), send=send, apply=apply, push=push, revert=revert,
                  runner=_runner_for({"kind": "fix", "reasoning": "sizing", "diff": MONEY_DIFF}))
    fp = s["wake"][0]
    assert calls["push"] == [(fp, f"sre/{fp}")]
    assert "owner asked to merge" in s["acted"]
    assert any("compare/main..." in m and "not pushed to main" in m for m in send.sent)


@pytest.mark.parametrize("diff,why", [(FORBIDDEN_DIFF, "forbidden"), (TEST_EDIT_DIFF, "forbidden"), ("", "empty")])
def test_forbidden_or_empty_diffs_are_refused_without_a_push(box, diff, why):
    _append(box, LINE)
    calls, apply, push, revert = _fakes()
    s = sre.cycle(NOW, logs_dir=str(box["logs"]), send=_sender(), apply=apply, push=push, revert=revert,
                  runner=_runner_for({"kind": "fix", "reasoning": "x", "diff": diff}))
    assert calls["apply"] == [] and calls["push"] == [] and "fix refused" in s["acted"]
    assert [r["kind"] for r in ops_watch.ledger_rows()].count("sre_fix_refused") == 1


def test_a_red_suite_never_pushes(box):
    _append(box, LINE)
    calls, apply, push, revert = _fakes()
    def red(diff, *, fp, message, **kw):
        return (False, "", "suite red: 1 failed")
    s = sre.cycle(NOW, logs_dir=str(box["logs"]), send=_sender(), apply=red, push=push, revert=revert,
                  runner=_runner_for({"kind": "fix", "reasoning": "x", "diff": SAFE_DIFF}))
    assert calls["push"] == [] and "suite red" in s["acted"]


def test_rate_limits_hold_wakes_and_pushes(box, monkeypatch):
    monkeypatch.setattr(sre, "MAX_WAKES_PER_HOUR", 1)
    monkeypatch.setattr(sre, "MAX_PUSHES_PER_DAY", 1)
    calls, apply, push, revert = _fakes()
    runner = _runner_for({"kind": "fix", "reasoning": "x", "diff": SAFE_DIFF})
    _append(box, LINE)
    sre.cycle(NOW, logs_dir=str(box["logs"]), send=_sender(), apply=apply, push=push, revert=revert, runner=runner)
    _append(box, "2026-09-22 12:10:00 ERROR [y] second fault")
    s = sre.cycle(NOW + 60, logs_dir=str(box["logs"]), send=_sender(), apply=apply, push=push, revert=revert, runner=runner)
    assert "held" in s["held"] and len(runner.calls) == 1, "the second wake in the hour is held, the model not asked"
    _append(box, "2026-09-22 13:30:00 ERROR [z] third fault")
    s = sre.cycle(NOW + 3700, logs_dir=str(box["logs"]), send=_sender(), apply=apply, push=push, revert=revert, runner=runner)
    assert "1 pushes already today" in s["acted"] and len(calls["push"]) == 1


def test_an_expensive_diagnosis_does_nothing(box, monkeypatch):
    monkeypatch.setattr(sre, "MAX_USD_PER_DIAGNOSIS", 1.0)
    _append(box, LINE)
    calls, apply, push, revert = _fakes()
    s = sre.cycle(NOW, logs_dir=str(box["logs"]), send=_sender(), apply=apply, push=push, revert=revert,
                  runner=_runner_for({"kind": "fix", "reasoning": "x", "diff": SAFE_DIFF}, cost=4.0))
    assert calls["push"] == [] and s["acted"] == "nothing"
    assert sre.thoughts()[-1]["kind"] == "over-budget"


def test_a_recurrence_reverts_the_own_push_once(box, monkeypatch):
    monkeypatch.setattr(sre, "PUSH_MAIN", True)   # a revert only applies to its own push on main
    _append(box, LINE)
    calls, apply, push, revert = _fakes()
    send = _sender()
    s = sre.cycle(NOW, logs_dir=str(box["logs"]), send=send, apply=apply, push=push, revert=revert,
                  runner=_runner_for({"kind": "fix", "reasoning": "x", "diff": SAFE_DIFF, "path_marker": "[exec] placed"}))
    fp = s["wake"][0]
    # the path ran and the fault came back
    _append(box, "2026-09-22 12:30:00 TRADE [exec] placed order 0x1234567890", LINE)
    s2 = sre.cycle(NOW + 1800, logs_dir=str(box["logs"]), send=send, apply=apply, push=push, revert=revert,
                   runner=_runner_for({"kind": "nothing", "reasoning": "x"}))
    assert calls["revert"] == [("abc1234", fp)] and s2["reverts"] == 1
    assert any("reverted its own fix" in m for m in send.sent)
    assert fpm.read()[fp]["path_runs"] == 1
    s3 = sre.cycle(NOW + 3600, logs_dir=str(box["logs"]), send=send, apply=apply, push=push, revert=revert,
                   runner=_runner_for({"kind": "nothing", "reasoning": "x"}))
    assert calls["revert"] == [("abc1234", fp)] and s3["reverts"] == 0, "reverted once, never twice"


def test_no_verdict_is_a_ledger_row_not_a_crash(box):
    _append(box, LINE)
    s = sre.cycle(NOW, logs_dir=str(box["logs"]), send=_sender(), runner=lambda p: None)
    assert s["acted"] == "nothing" and sre.thoughts()[-1]["kind"] == "no-verdict"
    assert sre.parse_verdict({"result": "no json here"}) is None
    assert sre.parse_verdict({"result": '{"kind": "launch nukes"}'}) is None


def test_the_second_line_summarises_the_day(box):
    assert sre.second_line(NOW) == ""
    sre.thought({"woke_because": "a", "kind": "escalate", "concluded": "orders not posting", "did": "escalated", "cost_usd": 0.4}, NOW - 100)
    sre.thought({"woke_because": "b", "kind": "fix", "concluded": "await missing", "did": "fix pushed to main (abc)", "cost_usd": 0.6}, NOW - 50)
    line = sre.second_line(NOW)
    assert line.startswith("\U0001f916 watcher, last 24h: woke 2, acted 2, reverted 0, escalated 1, spent $1.00")
    assert "await missing" in line and "—" not in line
    assert ops_watch.watcher_line(NOW) == line, "the 08:00 line reads the same ledger"


def test_the_deployed_sha_is_read_from_the_mounted_logs_dir(box, monkeypatch):
    (box["logs"] / "hygiene.log").write_text("20260922T180315Z build-manifest sha=a77ab27 image=x\n")
    monkeypatch.setenv("SRE_BOT_LOGS_DIR", str(box["logs"]))
    assert sre.box_snapshot(NOW)["deployed_sha"] == "a77ab27"


def test_a_fix_that_changes_the_risk_profile_goes_to_a_branch_even_with_main_open(box, monkeypatch):
    """Owner ruling 2026-09-24: main directly, unless the fix significantly
    changes the risk profile; then a PR and the change in risk to read."""
    monkeypatch.setattr(sre, "PUSH_MAIN", True)
    _append(box, LINE)
    calls, apply, push, revert = _fakes()
    send = _sender()
    s = sre.cycle(NOW, logs_dir=str(box["logs"]), send=send, apply=apply, push=push, revert=revert,
                  runner=_runner_for({"kind": "fix", "reasoning": "x", "diff": SAFE_DIFF,
                                      "risk_change": "copies now go out at twice the stake when the book is thin"}))
    fp = s["wake"][0]
    assert calls["push"] == [(fp, f"sre/{fp}")]
    assert any("it changes the risk profile" in m and "Risk change: copies now go out at twice" in m for m in send.sent)
    # "none" is not a risk change: main
    _append(box, "2026-09-22 12:30:00 ERROR [y] other fault")
    s2 = sre.cycle(NOW + 60, logs_dir=str(box["logs"]), send=send, apply=apply, push=push, revert=revert,
                   runner=_runner_for({"kind": "fix", "reasoning": "x", "diff": SAFE_DIFF, "risk_change": "none"}))
    assert calls["push"][-1] == (s2["wake"][0], None)


def test_the_prompt_carries_the_chain_readers_own_health_line(box):
    """The SRE saw only the refused-chunk ERROR lines (a good chunk logs
    nothing it reads) and disarmed real money twice for a 2% head race
    (2026-09-26). The reader's health line and its role ride in the prompt."""
    from src.copy_trading import onchain_source
    onchain_source._save_health({"ts": NOW, "ok_ts": NOW - 5, "cursor": 100, "head": 100, "lag": 0,
                                 "retries_1h": 4, "skipped_1h": 0, "tracked": 12})
    _append(box, "2026-09-22 12:00:00 ERROR Error fetching CTF events [94469969-94469969]: {'code': -32000, 'message': 'invalid block range params'}")
    runner = _runner_for({"kind": "nothing", "reasoning": "a head race, retried"})
    sre.cycle(NOW, logs_dir=str(box["logs"]), runner=runner, send=_sender())
    p = runner.calls[0]
    assert "chain reader: reading, last good read 5s ago" in p and "4 refused chunk(s) retried" in p
    assert "head race" in p and "not an outage" in p and "confirmed through the CLOB" in p


def test_the_prompt_tells_the_model_to_read_the_whole_log_and_carries_the_census(box):
    """Owner, 2026-09-26: woken by an error, the SRE must be able to read
    all the logs before it concludes. The prompt names the files, hands it
    the hour's census of the full log, and the runner grants read tools."""
    import time as _t
    day = _t.strftime("%Y-%m-%d", _t.gmtime(NOW))
    t = _t.strftime("%Y-%m-%d %H:%M:%S", _t.gmtime(NOW - 30))
    (box["logs"] / f"bot-{day}.log").write_text(
        "\n".join([f"{t} INFO  Onchain: cursor {i}, head {i}, lag 0 block(s)" for i in range(50)]
                  + [f"{t} ERROR Error fetching CTF events [1-2]: refused"]) + "\n")
    _append(box, LINE)
    runner = _runner_for({"kind": "nothing", "reasoning": "50 good chunks next to 1 refused"})
    sre.cycle(NOW, logs_dir=str(box["logs"]), runner=runner, send=_sender())
    p = runner.calls[0]
    assert "Look further before you conclude" in p and f"bot-{day}.log" in p and str(box["logs"]) in p
    assert "51 lines in the last" in p and "50  INFO Onchain: cursor N, head" in p
    assert "a component still logging" in p
    rows = sre.thoughts()
    assert "bot logs (read tools)" in rows[-1]["looked_at"]
