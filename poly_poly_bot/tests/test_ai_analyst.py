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
