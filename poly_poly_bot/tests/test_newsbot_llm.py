"""newsbot.llm: the ``claude -p`` envelope call with a fake runner, and the
per-UTC-day budget with an injected clock (2026-10-25). No subprocess, no wall clock."""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone


from src.copy_trading import llm_review
from src.newsbot import llm
from src.newsbot.llm import RATE_LIMITED, DailyBudget, run_claude


def _proc(stdout="", stderr="", code=0):
    return subprocess.CompletedProcess(args=["claude"], returncode=code, stdout=stdout, stderr=stderr)


def _envelope(result, **extra):
    env = {"type": "result", "subtype": "success", "is_error": False, "result": result,
           "duration_ms": 6100, "total_cost_usd": 0.01}
    env.update(extra)
    return json.dumps(env)


class Script:
    """A runner that replays a script of CompletedProcess / exceptions and records argv."""

    def __init__(self, *steps):
        self.steps, self.calls = list(steps), []

    def __call__(self, cmd, *, timeout_s):
        self.calls.append((cmd, timeout_s))
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


def test_sentinel_is_shared_with_the_copy_bot_gate():
    assert RATE_LIMITED is llm_review.RATE_LIMITED


def test_success_envelope_and_argv():
    r = Script(_proc(_envelope('{"material": false}')))
    env = run_claude("hello", model="claude-sonnet-4-5", timeout_s=42, runner=r)
    assert isinstance(env, dict) and env["result"] == '{"material": false}' and env["duration_ms"] == 6100
    (cmd, timeout), = r.calls
    assert cmd == ["claude", "-p", "hello", "--output-format", "json", "--model", "claude-sonnet-4-5"]
    assert timeout == 42


def test_rate_limit_text_on_nonzero_exit_is_the_sentinel_without_retry():
    r = Script(_proc("", "You've hit your monthly spend limit · raise it at claude.ai/settings/usage", code=1))
    assert run_claude("p", model="m", runner=r) is RATE_LIMITED
    assert len(r.calls) == 1


def test_rate_limit_text_on_zero_exit_plain_text():
    r = Script(_proc("Usage limit reached. Try again later."))
    assert run_claude("p", model="m", runner=r) is RATE_LIMITED


def test_rate_limit_inside_error_envelope():
    r = Script(_proc(json.dumps({"subtype": "error_during_execution", "is_error": True,
                                 "result": "rate limit exceeded"})))
    assert run_claude("p", model="m", runner=r) is RATE_LIMITED


def test_error_envelope_without_limit_is_none(caplog):
    r = Script(_proc(json.dumps({"subtype": "error_max_turns", "is_error": True, "result": "x"})))
    with caplog.at_level(logging.WARNING):
        assert run_claude("p", model="m", runner=r) is None
    assert "error envelope" in caplog.text


def test_garbage_json_is_none_and_logged(caplog):
    r = Script(_proc("<html>502 bad gateway</html>"))
    with caplog.at_level(logging.WARNING):
        assert run_claude("p", model="m", runner=r) is None
    assert "non-JSON" in caplog.text
    assert run_claude("p", model="m", runner=Script(_proc("[1, 2]"))) is None


def test_generic_failure_retries_once_then_defers():
    r = Script(_proc("", "", code=1), _proc(_envelope("ok")))
    assert run_claude("p", model="m", runner=r)["result"] == "ok"
    assert len(r.calls) == 2

    r = Script(_proc("", "boom", code=1), _proc("", "boom", code=1))
    assert run_claude("p", model="m", runner=r) is RATE_LIMITED
    assert len(r.calls) == 2


def test_timeout_twice_is_rate_limited_sentinel(caplog):
    r = Script(subprocess.TimeoutExpired(cmd="claude", timeout=60), subprocess.TimeoutExpired(cmd="claude", timeout=60))
    with caplog.at_level(logging.WARNING):
        assert run_claude("p", model="m", timeout_s=60, runner=r) is RATE_LIMITED
    assert len(r.calls) == 2 and "failed to run" in caplog.text


def test_timeout_then_success():
    r = Script(OSError("exec"), _proc(_envelope("late but fine")))
    assert run_claude("p", model="m", runner=r)["result"] == "late but fine"


def test_missing_cli_is_none(monkeypatch, caplog):
    monkeypatch.setattr(llm.shutil, "which", lambda _: None)
    with caplog.at_level(logging.WARNING):
        assert run_claude("p", model="m") is None
    assert "not found" in caplog.text


# -- DailyBudget -------------------------------------------------------------------

def _ts(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc).timestamp()


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def test_budget_counts_persists_and_caps(tmp_path):
    path = tmp_path / "data" / "news" / "llm-budget.json"
    clock = Clock(_ts(2026, 10, 25, 12))
    b = DailyBudget(path, 3, clock=clock)
    assert b.count_today() == 0 and b.remaining() == 3
    assert b.take() and b.take() and b.take()
    assert b.take() is False and b.take() is False
    assert b.count_today() == 3 and b.remaining() == 0
    assert json.loads(path.read_text()) == {"day": "2026-10-25", "count": 3}
    # a restart reads the same file
    b2 = DailyBudget(path, 3, clock=clock)
    assert b2.count_today() == 3 and b2.take() is False
    # raising the limit later in the day frees the difference
    assert DailyBudget(path, 4, clock=clock).take() is True


def test_budget_rolls_over_at_utc_midnight(tmp_path):
    path = tmp_path / "llm-budget.json"
    clock = Clock(_ts(2026, 10, 25, 23, 59))
    b = DailyBudget(path, 1, clock=clock)
    assert b.take() and not b.take()
    clock.t = _ts(2026, 10, 26, 0, 0)          # one minute later, a new UTC day
    assert b.count_today() == 0
    assert b.take() is True and b.count_today() == 1
    assert json.loads(path.read_text())["day"] == "2026-10-26"
    clock.t = _ts(2026, 10, 25, 23, 59)        # a clock stepping back is just "another day": 0 used
    assert b.count_today() == 0


def test_budget_zero_limit_and_garbage_file(tmp_path, caplog):
    path = tmp_path / "b.json"
    clock = Clock(_ts(2026, 10, 25))
    assert DailyBudget(path, 0, clock=clock).take() is False
    path.write_text("{not json")
    with caplog.at_level(logging.WARNING):
        b = DailyBudget(path, 2, clock=clock)
        assert b.count_today() == 0 and b.take() is True
    assert "unreadable" in caplog.text
    assert json.loads(path.read_text()) == {"day": "2026-10-25", "count": 1}


def test_default_budget_path():
    assert llm.default_budget_path("/srv/data") == "/srv/data/news/llm-budget.json"
