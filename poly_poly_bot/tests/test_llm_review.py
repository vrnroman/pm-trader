"""Claude gate (Strategy 1c) — dossier assembly + the `claude -p` call wrapper.

These tests pin the pure dossier assembly and the defensive subprocess wrapper:
an injected runner exercises the happy path, and every failure mode (runner
returns None, bad JSON, exception) degrades to None so the gate fails open. No
real subprocess is spawned except the explicitly monkeypatched CLI-runner tests.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from src.copy_trading import llm_review as lr
from src.copy_trading.llm_review import LLMVerdict, build_dossier, review_wallet


def _runner_returning(text):
    """A fake `claude -p` runner that records its call and returns `text`."""
    captured: dict = {}

    def runner(prompt, *, model, timeout_s):
        captured.update(prompt=prompt, model=model, timeout_s=timeout_s)
        return text

    runner.captured = captured
    return runner


def test_build_dossier_pulls_signals_defensively():
    metrics = SimpleNamespace(roi=0.42, tstat=12.3, n_closed=25, capital=50000.0,
                              hit_rate=0.66, concentration=0.3)
    evaluation = SimpleNamespace(capture_cents=2.1, lead_cents=4.0, hit_rate=0.7, n=18)
    entry = SimpleNamespace(mean_entry=0.45, tail_ratio=0.1, copyable_ratio=0.9)
    curve = SimpleNamespace(net_pnl=125000.0, max_drawdown_frac=0.18, up_ratio=0.62, sharpe=1.4)

    d = build_dossier("0xabc", metrics=metrics, evaluation=evaluation, entry=entry,
                      curve=curve, portfolio_value=3_000_000.0,
                      recent_bets=[{"title": "X", "usd": 5000, "price": 0.4}] * 20)

    assert d["wallet"] == "0xabc"
    assert d["skill"]["tstat"] == 12.3 and d["skill"]["n_closed"] == 25
    assert d["copyability"]["capture_cents"] == 2.1
    assert d["entry_profile"]["copyable_ratio"] == 0.9
    assert d["pnl_curve"]["max_drawdown_frac"] == 0.18
    assert d["portfolio_value"] == 3_000_000.0
    assert len(d["recent_bets"]) == 15            # capped


def test_build_dossier_omits_missing_pieces():
    d = build_dossier("0xabc")
    assert d == {"wallet": "0xabc"}               # nothing fabricated


def test_review_wallet_happy_path_parses_verdict():
    runner = _runner_returning(json.dumps({
        "verdict": "follow", "insider_likelihood": "high", "copyable": True,
        "confidence": 0.8, "reasoning": "Steady curve, copyable entries.",
    }))
    v = review_wallet({"wallet": "0xabc"}, runner=runner, model="claude-opus-4-8")
    assert isinstance(v, LLMVerdict)
    assert v.verdict == "follow" and v.copyable is True and v.confidence == 0.8
    # the dossier and model are threaded into the CLI prompt
    assert "0xabc" in runner.captured["prompt"]
    assert runner.captured["model"] == "claude-opus-4-8"


def test_review_wallet_tolerates_prose_and_fences():
    payload = {"verdict": "skip", "insider_likelihood": "low", "copyable": False,
               "confidence": 0.3, "reasoning": "spiky curve"}
    runner = _runner_returning("Here's my call:\n```json\n" + json.dumps(payload) + "\n```")
    v = review_wallet({"wallet": "0xabc"}, runner=runner)
    assert v is not None and v.verdict == "skip" and v.copyable is False


def test_review_wallet_returns_none_on_bad_json():
    assert review_wallet({"wallet": "0xabc"}, runner=_runner_returning("not json")) is None


def test_review_wallet_returns_none_when_runner_returns_none():
    assert review_wallet({"wallet": "0xabc"}, runner=_runner_returning(None)) is None


def test_review_wallet_returns_none_on_runner_error():
    def boom(prompt, *, model, timeout_s):
        raise RuntimeError("cli missing")
    assert review_wallet({"wallet": "0xabc"}, runner=boom) is None


def test_cli_runner_parses_success_envelope(monkeypatch):
    monkeypatch.setattr(lr.shutil, "which", lambda _: "/usr/bin/claude")

    def fake_run(cmd, **kw):
        assert "-p" in cmd and "--output-format" in cmd and "json" in cmd
        assert "--model" in cmd
        return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps(
            {"subtype": "success", "is_error": False, "result": '{"verdict":"watch"}'}))

    monkeypatch.setattr(lr.subprocess, "run", fake_run)
    out = lr._claude_cli_runner("prompt", model="claude-opus-4-8", timeout_s=5)
    assert out == '{"verdict":"watch"}'


def test_cli_runner_none_when_cli_absent(monkeypatch):
    monkeypatch.setattr(lr.shutil, "which", lambda _: None)
    assert lr._claude_cli_runner("p", model="m", timeout_s=5) is None


def test_cli_runner_none_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(lr.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(lr.subprocess, "run", lambda cmd, **kw: SimpleNamespace(
        returncode=1, stdout="", stderr="not authenticated"))
    assert lr._claude_cli_runner("p", model="m", timeout_s=5) is None


def test_cli_runner_none_on_error_envelope(monkeypatch):
    monkeypatch.setattr(lr.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(lr.subprocess, "run", lambda cmd, **kw: SimpleNamespace(
        returncode=0, stderr="", stdout=json.dumps(
            {"subtype": "error_during_execution", "is_error": True, "result": None})))
    assert lr._claude_cli_runner("p", model="m", timeout_s=5) is None
