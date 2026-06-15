"""Gated Claude second-opinion (Strategy 1c).

The LLM review runs only on wallets that already passed the statistical funnel.
These tests pin the pure dossier assembly and the defensive call wrapper: a
fake client exercises the happy path, and every failure mode (refusal, bad
JSON, exception, no SDK) must degrade to None so a discovery sweep never breaks.
No network — the anthropic SDK is never imported here.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from src.copy_trading import llm_review as lr
from src.copy_trading.llm_review import LLMVerdict, build_dossier, review_wallet


def _fake_client(payload, *, stop_reason="end_turn"):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    resp = SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)],
    )

    class _Msgs:
        def create(self, **kw):
            _Msgs.last_kwargs = kw
            return resp

    return SimpleNamespace(messages=_Msgs())


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
    client = _fake_client({
        "verdict": "follow", "insider_likelihood": "high", "copyable": True,
        "confidence": 0.8, "reasoning": "Steady curve, copyable entries.",
    })
    v = review_wallet({"wallet": "0xabc"}, client=client)
    assert isinstance(v, LLMVerdict)
    assert v.verdict == "follow" and v.copyable is True and v.confidence == 0.8
    # adaptive thinking + structured output were requested
    kw = client.messages.last_kwargs
    assert kw["thinking"] == {"type": "adaptive"}
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["model"] == lr.DEFAULT_MODEL


def test_review_wallet_returns_none_on_refusal():
    client = _fake_client({"verdict": "skip"}, stop_reason="refusal")
    assert review_wallet({"wallet": "0xabc"}, client=client) is None


def test_review_wallet_returns_none_on_bad_json():
    client = _fake_client("not json at all")
    assert review_wallet({"wallet": "0xabc"}, client=client) is None


def test_review_wallet_returns_none_on_client_error():
    class _Boom:
        class messages:
            @staticmethod
            def create(**kw):
                raise RuntimeError("network down")
    assert review_wallet({"wallet": "0xabc"}, client=_Boom()) is None
