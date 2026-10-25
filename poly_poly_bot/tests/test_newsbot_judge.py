"""newsbot.judge: the prompt shows the candidates and the tape, the reply is
parsed and checked against what was offered, the budget and the rate limit are
honoured, nothing raises (2026-10-25). The runner is a fake; no wall clock."""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from src.newsbot import judge as judge_mod
from src.newsbot.index import Candidate
from src.newsbot.judge import Judgement, build_prompt, judge, parse_judgement_text, validate_judgement

NOW = datetime(2026, 10, 25, 14, 0, tzinfo=timezone.utc).timestamp()


@dataclass
class Item:
    id: str = "rss:ft:abc"
    source: str = "rss:ft"
    domains: tuple = ("corp",)
    published_ts: float = NOW - 90
    seen_ts: float = NOW
    title: str = "Anthropic files confidentially for IPO"
    text: str = "Anthropic has filed confidentially with the SEC for an initial public offering, two people familiar said."
    url: str = "https://ft.com/x"


FED = Candidate(market_id="2589811", condition_id="0xfed", question="Will the Fed decrease interest rates by 25 bps after the October 2026 meeting?",
                event_title="Fed Decision in October?", tags=("Fed", "fomc"), domains=("corp",),
                outcomes=["Yes", "No"], token_ids=["t-fed-yes", "t-fed-no"], best_bid=0.21, best_ask=0.22,
                end_ts=datetime(2026, 10, 29, 3, 59, tzinfo=timezone.utc).timestamp(), is_sports=False)
IPO = Candidate(market_id="9000001", condition_id="0xipo", question="Will Anthropic announce an IPO by December 31, 2026?",
                event_title="Anthropic IPO by...?", tags=("Tech", "IPO"), domains=("corp",),
                outcomes=["Yes", "No"], token_ids=["t-ipo-yes", "t-ipo-no"], best_bid=0.12, best_ask=0.14,
                end_ts=datetime(2027, 1, 1, 4, 59, tzinfo=timezone.utc).timestamp(), is_sports=False)
CANDS = [FED, IPO]
FRESH = {"t-ipo-yes": ("fresh", "no move 15m, ask 0.14 vs mid 0.13"), "t-fed-yes": "moving"}


class Budget:
    def __init__(self, allow=True, limit=150):
        self.allow, self.limit, self.taken = allow, limit, 0

    def take(self):
        if not self.allow:
            return False
        self.taken += 1
        return True

    def count_today(self):
        return self.limit if not self.allow else self.taken


def _runner_returning(text, **extra):
    env = {"type": "result", "subtype": "success", "is_error": False, "result": text, "duration_ms": 5900}
    env.update(extra)

    def runner(cmd, *, timeout_s):
        runner.calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(env), stderr="")
    runner.calls = []
    return runner


GOOD = {"material": True, "market_id": "9000001", "outcome_index": 0, "direction": "yes",
        "implied_prob": 0.45, "confidence": 0.8, "why": "A confidential S-1 is new and specific.",
        "already_priced": False}


# -- prompt ----------------------------------------------------------------------

def test_prompt_carries_item_candidates_quotes_and_freshness():
    p = build_prompt(Item(), CANDS, FRESH)
    assert "source: rss:ft | published: 2026-10-25T13:58Z | domains: corp" in p
    assert "title: Anthropic files confidentially for IPO" in p
    assert "url: https://ft.com/x" in p
    assert "market_id=2589811 | event: Fed Decision in October? | question: Will the Fed decrease" in p
    assert "ends 2026-10-29T03:59Z" in p
    assert "market_id=9000001" in p
    # per-outcome quotes: Gamma's for Yes, the complement for No
    assert 'outcome_index=0 "Yes": bid 0.12 ask 0.14 | tape: fresh (no move 15m, ask 0.14 vs mid 0.13)' in p
    assert 'outcome_index=1 "No": bid 0.86 ask 0.88 | tape: unknown' in p
    assert 'outcome_index=0 "Yes": bid 0.21 ask 0.22 | tape: moving' in p
    # the instructions: schema, one market, 5 points, no fences
    assert "at least 5 points" in p and "pick at most one" in p
    for key in ("material", "market_id", "outcome_index", "direction", "implied_prob", "confidence", "why", "already_priced"):
        assert f'"{key}"' in p
    assert "no code fences" in p


def test_prompt_truncates_text_and_uses_tape_quotes_when_given():
    item = Item(text="x" * 5000)
    p = build_prompt(item, [IPO], {}, quotes_by_token={"t-ipo-no": (0.80, 0.81)})
    assert "x" * 1200 + " [...]" in p and "x" * 1201 not in p
    assert 'outcome_index=1 "No": bid 0.8 ask 0.81' in p
    sport = Candidate(**{**IPO.__dict__, "is_sports": True, "market_id": "s1"})
    assert "| SPORTS" in build_prompt(item, [sport], None)


# -- parsing / validation ----------------------------------------------------------

def test_parse_fenced_and_prosed_json():
    assert parse_judgement_text("```json\n" + json.dumps(GOOD) + "\n```") == GOOD
    assert parse_judgement_text("Sure, here is the verdict:\n" + json.dumps(GOOD) + "\nHope that helps") == GOOD
    assert parse_judgement_text(json.dumps(GOOD)) == GOOD
    nested = {"material": False, "market_id": None, "why": "nothing {fits}", "confidence": 0.3}
    assert parse_judgement_text("```\n" + json.dumps(nested) + "```") == nested
    assert parse_judgement_text("not json at all") is None
    assert parse_judgement_text("") is None and parse_judgement_text(None) is None
    assert parse_judgement_text("[1,2]") is None


def test_validate_accepts_good_and_normalises_types():
    v = validate_judgement({**GOOD, "market_id": 9000001, "outcome_index": "0", "confidence": "0.8"}, CANDS)
    assert v["market_id"] == "9000001" and v["outcome_index"] == 0 and v["confidence"] == 0.8
    v = validate_judgement({"material": False, "market_id": None, "outcome_index": None, "direction": None,
                            "implied_prob": None, "confidence": 0.6, "why": "old news", "already_priced": True}, CANDS)
    assert v["material"] is False and v["already_priced"] is True and v["market_id"] is None


@pytest.mark.parametrize("bad", [
    {**GOOD, "market_id": "123456"},                 # not offered
    {**GOOD, "outcome_index": 2},                    # no such outcome
    {**GOOD, "outcome_index": -1},
    {**GOOD, "direction": "long"},
    {**GOOD, "confidence": 1.7},
    {**GOOD, "confidence": None},
    {**GOOD, "implied_prob": "high"},
    {**GOOD, "material": "maybe"},
    {**GOOD, "market_id": None},                     # material needs a market
    {**GOOD, "direction": None},                     # ... and a direction
    {"material": False, "market_id": "123456", "confidence": 0.2},   # a market_id must still be ours
    {"material": False, "market_id": "9000001", "outcome_index": 5, "confidence": 0.2},
])
def test_validate_rejects(bad):
    assert validate_judgement(bad, CANDS) is None


# -- judge -------------------------------------------------------------------------

def test_judge_happy_path_fenced_reply():
    budget = Budget()
    runner = _runner_returning("```json\n" + json.dumps(GOOD) + "\n```")
    j = judge(Item(), CANDS, FRESH, budget=budget, model="claude-sonnet-4-5", runner=runner, now=NOW)
    assert isinstance(j, Judgement)
    assert (j.material, j.market_id, j.outcome_index, j.direction) == (True, "9000001", 0, "yes")
    assert j.implied_prob == 0.45 and j.confidence == 0.8 and j.already_priced is False
    assert j.llm_ms == 5900 and j.model == "claude-sonnet-4-5"
    assert j.prompt_chars == len(build_prompt(Item(), CANDS, FRESH)) > 500
    assert budget.taken == 1
    cmd = runner.calls[0]
    assert cmd[:2] == ["claude", "-p"] and cmd[-4:] == ["--output-format", "json", "--model", "claude-sonnet-4-5"]
    assert "market_id=9000001" in cmd[2]


def test_judge_not_material_is_a_judgement_too():
    reply = {"material": False, "market_id": None, "outcome_index": None, "direction": None,
             "implied_prob": None, "confidence": 0.7, "why": "Already reported yesterday.", "already_priced": True}
    j = judge(Item(), CANDS, FRESH, budget=Budget(), model="m", runner=_runner_returning(json.dumps(reply)), now=NOW)
    assert j is not None and j.material is False and j.market_id is None and j.already_priced is True


def test_judge_rejects_market_not_in_candidates(caplog):
    runner = _runner_returning(json.dumps({**GOOD, "market_id": "424242"}))
    with caplog.at_level(logging.WARNING):
        assert judge(Item(), CANDS, FRESH, budget=Budget(), model="m", runner=runner, now=NOW) is None
    assert "candidate check" in caplog.text


def test_judge_honours_budget(caplog):
    budget = Budget(allow=False, limit=150)
    runner = _runner_returning(json.dumps(GOOD))
    with caplog.at_level(logging.INFO):
        assert judge(Item(), CANDS, FRESH, budget=budget, model="m", runner=runner, now=NOW) is None
    assert "[news-judge] budget exhausted" in caplog.text and "skipped:budget" in caplog.text
    assert runner.calls == []                         # no call was made


def test_judge_rate_limited_returns_none_and_logs_once_per_hour(monkeypatch, caplog):
    monkeypatch.setattr(judge_mod, "_rate_limit_logged_at", None)

    def limited(cmd, *, timeout_s):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="You've hit your usage limit")

    with caplog.at_level(logging.WARNING, logger="poly_poly_bot"):
        for i in range(3):
            assert judge(Item(), CANDS, FRESH, budget=Budget(), model="m", runner=limited, now=NOW + i) is None
        n_first_hour = caplog.text.count("[news-judge] claude is rate-limited")
        assert judge(Item(), CANDS, FRESH, budget=Budget(), model="m", runner=limited, now=NOW + 3601) is None
    assert n_first_hour == 1
    assert caplog.text.count("[news-judge] claude is rate-limited") == 2


def test_judge_rate_limited_envelope_text_path(monkeypatch):
    monkeypatch.setattr(judge_mod, "_rate_limit_logged_at", None)
    runner = _runner_returning("rate limit exceeded", subtype="error", is_error=True)
    assert judge(Item(), CANDS, FRESH, budget=Budget(), model="m", runner=runner, now=NOW) is None


def test_judge_no_candidates_costs_nothing():
    budget = Budget()
    runner = _runner_returning(json.dumps(GOOD))
    assert judge(Item(), [], FRESH, budget=budget, model="m", runner=runner, now=NOW) is None
    assert budget.taken == 0 and runner.calls == []


def test_judge_garbage_reply_and_timeout_are_none(caplog):
    with caplog.at_level(logging.WARNING):
        assert judge(Item(), CANDS, FRESH, budget=Budget(), model="m",
                     runner=_runner_returning("I cannot determine this."), now=NOW) is None
    assert "not JSON" in caplog.text

    def timeout(cmd, *, timeout_s):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout_s)
    assert judge(Item(), CANDS, FRESH, budget=Budget(), model="m", runner=timeout, timeout_s=5, now=NOW) is None


def test_judge_never_raises(caplog):
    class ExplodingBudget:
        limit = 1

        def take(self):
            raise RuntimeError("disk gone")

        def count_today(self):
            return 0

    with caplog.at_level(logging.ERROR):
        assert judge(Item(), CANDS, FRESH, budget=ExplodingBudget(), model="m",
                     runner=_runner_returning(json.dumps(GOOD)), now=NOW) is None
    assert "unexpected failure" in caplog.text

    def exploding_runner(cmd, *, timeout_s):
        raise ValueError("weird")
    assert judge(Item(), CANDS, FRESH, budget=Budget(), model="m", runner=exploding_runner, now=NOW) is None


def test_judge_llm_ms_falls_back_to_measured_when_envelope_lacks_it():
    def runner(cmd, *, timeout_s):
        env = {"subtype": "success", "is_error": False, "result": json.dumps(GOOD)}
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(env), stderr="")
    j = judge(Item(), CANDS, FRESH, budget=Budget(), model="m", runner=runner, now=NOW)
    assert j is not None and isinstance(j.llm_ms, int) and j.llm_ms >= 0


def test_an_answer_naming_the_list_position_maps_to_that_market():
    # 2026-10-25: the day's only material call came back as market_id "1"
    v = validate_judgement({**GOOD, "market_id": "1"}, CANDS)
    assert v is not None and v["market_id"] == str(CANDS[0].market_id)
    assert validate_judgement({**GOOD, "market_id": str(len(CANDS) + 1)}, CANDS) is None


def test_the_prompt_carries_no_list_numbers():
    p = build_prompt(Item(), CANDS, FRESH)
    assert "[1]" not in p and f"market_id={CANDS[0].market_id}" in p


def test_direction_no_buys_the_other_outcome():
    # backtest 2026-10-25: "Conservatives win a landslide" -> YES on "Eby next Premier", implied 0.02
    v = validate_judgement({**GOOD, "outcome_index": 0, "direction": "no", "implied_prob": 0.02}, CANDS)
    assert v["outcome_index"] == 1 and v["direction"] == "yes" and v["implied_prob"] == 0.98
    same = validate_judgement({**GOOD, "outcome_index": 1, "direction": "yes", "implied_prob": 0.98}, CANDS)
    assert same["outcome_index"] == 1 and same["implied_prob"] == 0.98
