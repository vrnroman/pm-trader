"""The analyst explains every void before anything else (2026-09-25): on
the day min150 voided it wrote a note blaming the control's determinism
while the fault was its own 1.5 pp tolerance on a +-31 pp chance band, and
the owner fixed the rule by hand. Now a void gets one post-mortem that
names a cause; a machinery cause carries a fix to a branch and earns the
idea a rerun; an idea cause does neither."""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import ai_analyst as an  # noqa: E402
from src.config import CONFIG  # noqa: E402
from src.copy_trading import exp_cards, live_limits, ops_watch  # noqa: E402

NOW = 1_790_316_060.0      # 2026-09-25 06:01 UTC, a fixed instant
DIFF = ("--- a/poly_poly_bot/src/copy_trading/exp_cards.py\n+++ b/poly_poly_bot/src/copy_trading/exp_cards.py\n"
        "@@ -1 +1 @@\n-HARNESS_TOL_PP = 1.5\n+HARNESS_TOL_PP = 2.0\n")


@pytest.fixture
def desk(tmp_path, monkeypatch):
    data = tmp_path / "data"; data.mkdir()
    for mod in (CONFIG, an.CONFIG, live_limits.CONFIG, ops_watch.CONFIG):
        monkeypatch.setattr(mod, "data_dir", str(data))
    monkeypatch.setattr(CONFIG, "copy_paper_b_ledger", str(data / "book_b.jsonl"))
    monkeypatch.setenv("ANALYST_ENABLED", "true")
    return data


def _void(exp_id="min150", why="12 of 30 settled copies after 21 days, already extended: starved", retry=False):
    exp_cards.create({"id": exp_id, "title": "slice floor 150", "hypothesis": "h", "knobs": {"min_usd": 150},
                      "win_bar": {"roi_pp": 2.0, "min_n": 30}, "kill_bar": {"roi_pp": -3.0, "min_n": 20}, "max_days": 14}, NOW - 86400)
    exp_cards.launch(exp_id, NOW - 86400)
    exp_cards.apply_verdict(exp_cards.load(exp_id), {"status": "void", "retry": retry, "why": why}, NOW - 3600)


def _runner(answer, cost=0.4):
    calls = []

    def run(prompt):
        calls.append(prompt)
        return {"result": json.dumps(answer), "total_cost_usd": cost}
    run.calls = calls
    return run


def _io():
    sent, applied, pushed = [], [], []

    def send(t):
        sent.append(t); return True

    def apply(diff, *, fp, message, **kw):
        applied.append((fp, diff)); return (True, "abc1234", "1700 passed at abc1234")

    def push(fp, *, branch, **kw):
        pushed.append(branch); return (True, branch)
    return sent, applied, pushed, send, apply, push


def test_a_rule_fault_is_named_fixed_on_a_branch_and_the_idea_runs_again(desk):
    _void()
    assert not exp_cards.retryable(exp_cards.load("min150")), "starved: no rerun by the code alone"
    sent, applied, pushed, send, apply, push = _io()
    runner = _runner({"cause": "rule", "evidence": "31 pp chance band against a 1.5 pp tolerance.",
                      "pr": {"title": "fix(exp): tolerance outside the noise", "diff": DIFF, "why": "w", "counterfactual": "c"}})
    row, cost = an.run_postmortem(exp_cards.load("min150"), NOW, runner=runner, send=send, apply=apply, push=push, sre=an._sre())
    prompt = runner.calls[0]
    assert "def verdict(" in prompt and "HARNESS_TOL_PP" in prompt, "the model reads the rules that judged it"
    assert cost == pytest.approx(0.4) and "post-mortem: rule" in row["did"]
    assert pushed and pushed[0].startswith("analyst/") and pushed[0] != "main", "a fix goes to a branch, never main"
    pm = exp_cards.postmortem("min150")
    assert pm["cause"] == "rule" and pm["pr"] is True
    assert exp_cards.retryable(exp_cards.load("min150")), "a machinery cause earns the idea a rerun"
    assert any("post-mortem of <code>min150</code>: rule (it runs again)" in m for m in sent)
    assert exp_cards.pending_postmortems() == [], "explained once"


def test_an_idea_that_failed_on_its_merits_is_not_rerun_and_sends_no_code(desk):
    _void()
    sent, applied, pushed, send, apply, push = _io()
    runner = _runner({"cause": "idea", "evidence": "matched copies agree; the treatment lost 4 pp on 300 copies.",
                      "pr": {"title": "t", "diff": DIFF, "why": "w", "counterfactual": "c"}})
    an.run_postmortem(exp_cards.load("min150"), NOW, runner=runner, send=send, apply=apply, push=push, sre=an._sre())
    assert applied == [] and pushed == [], "no machinery fault, no code"
    assert not exp_cards.retryable(exp_cards.load("min150"))
    assert any("idea (no rerun)" in m for m in sent)


def test_the_daily_run_explains_a_void_first_once(desk):
    _void()
    sent, applied, pushed, send, apply, push = _io()
    answers = iter([{"cause": "rule", "evidence": "e"}, {"proposals": [], "summary": "quiet"}])
    prompts = []

    def runner(prompt):
        prompts.append(prompt)
        return {"result": json.dumps(next(answers)), "total_cost_usd": 0.2}
    an.maybe_run(NOW, runner=runner, send=send, apply=apply, push=push)
    assert "was VOIDED" in prompts[0] and len(prompts) == 2
    assert exp_cards.postmortem("min150")["cause"] == "rule"
    # the next day: nothing left to explain, only the daily study
    prompts.clear(); answers = iter([{"proposals": [], "summary": "quiet"}])
    an.maybe_run(NOW + 86400, runner=runner, send=send, apply=apply, push=push)
    assert len(prompts) == 1 and "was VOIDED" not in prompts[0]


def test_a_garbled_post_mortem_is_recorded_and_not_retried_daily(desk):
    _void()
    sent, applied, pushed, send, apply, push = _io()
    an.run_postmortem(exp_cards.load("min150"), NOW, runner=lambda p: {"result": "no json"}, send=send, apply=apply, push=push, sre=an._sre())
    assert exp_cards.postmortem("min150")["cause"] == "unknown"
    assert exp_cards.pending_postmortems() == [] and not exp_cards.retryable(exp_cards.load("min150"))


def test_a_study_that_answered_another_question_fixes_the_menu_on_a_branch(desk, monkeypatch):
    sent, applied, pushed, send, apply, push = _io()
    rec = {"id": "2026-09-25-wallet_cap-178163d7", "kind": "wallet_cap", "question": "3 vs 5", "rows": [], "totals": {},
           "caveat": "c", "settings": {"from": {"cap": 25}, "to": {"cap": 5}}}
    monkeypatch.setattr(exp_cards, "studies", lambda limit=50: [rec])
    monkeypatch.setattr(an, "_exp_module", lambda: type("M", (), {"markdown": staticmethod(lambda r: "table")}))
    study_diff = DIFF.replace("src/copy_trading/exp_cards.py", "scripts/exp_study.py")
    runner = _runner({"conclusion": "25 -> 5 cannot answer 3 vs 5.", "card": None,
                      "pr": {"title": "fix(study): baseline at the live cap", "diff": study_diff, "why": "w", "counterfactual": "c"}})
    row, _ = an.conclude_study(rec["id"], NOW, runner=runner, send=send, apply=apply, push=push, sre=an._sre())
    assert pushed and pushed[0].startswith("analyst/") and "pr pushed" in row["did"]
