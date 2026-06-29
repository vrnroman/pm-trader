"""Langfuse telemetry — wire format + opt-in/defensive behavior (no real network)."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

from src.copy_trading import langfuse_telemetry as lt

_ENVELOPE_USAGE = {
    "input_tokens": 3000, "output_tokens": 40,
    "cache_read_input_tokens": 12000, "cache_creation_input_tokens": 500,
}


def _enable(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_HOST", "https://jp.cloud.langfuse.com")


def test_disabled_is_noop_when_keys_absent(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    posted = []
    monkeypatch.setattr(lt.requests, "post", lambda *a, **k: posted.append((a, k)))
    assert lt.enabled() is False
    lt.record_generation(name="wallet-gate", input="p", output="o", model="m",
                         start=1.0, end=2.0)
    assert posted == []                       # nothing sent


def test_record_generation_posts_trace_and_generation(monkeypatch):
    _enable(monkeypatch)
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(url=url, body=json, headers=headers, timeout=timeout)
        return SimpleNamespace(status_code=207, text="")

    monkeypatch.setattr(lt.requests, "post", fake_post)
    lt.record_generation(
        name="wallet-gate", input="the prompt", output='{"verdict":"skip"}',
        model="claude-opus-4-8", start=1000.0, end=1024.0,
        usage=_ENVELOPE_USAGE, cost_usd=0.037, duration_ms=4490,
        metadata={"wallet": "0xABC", "verdict": "skip"},
        tags=["wallet-gate"], error=None,
    )

    assert captured["url"].endswith("/api/public/ingestion")
    # Basic auth = base64(public:secret)
    assert captured["headers"]["Authorization"] == "Basic " + base64.b64encode(
        b"pk-test:sk-test").decode()

    batch = captured["body"]["batch"]
    types = [e["type"] for e in batch]
    assert types == ["trace-create", "generation-create"]

    gen = next(e for e in batch if e["type"] == "generation-create")["body"]
    assert gen["model"] == "claude-opus-4-8"
    assert gen["level"] == "DEFAULT"
    # usage maps Anthropic shape → prompt = input + cache_read + cache_creation
    assert gen["usage"] == {"input": 15500, "output": 40, "total": 15540, "unit": "TOKENS"}
    assert gen["usageDetails"]["cache_read"] == 12000
    assert gen["costDetails"]["total"] == 0.037
    assert gen["metadata"]["wallet"] == "0xABC"
    # trace + generation share a traceId
    trace = next(e for e in batch if e["type"] == "trace-create")["body"]
    assert gen["traceId"] == trace["id"]


def test_record_generation_marks_error_level(monkeypatch):
    _enable(monkeypatch)
    captured = {}
    monkeypatch.setattr(lt.requests, "post", lambda url, json=None, **k: (
        captured.update(body=json) or SimpleNamespace(status_code=207, text="")))
    lt.record_generation(name="wallet-gate", input="p", output="", model="m",
                         start=1.0, end=2.0, error="unparseable verdict")
    gen = next(e for e in captured["body"]["batch"]
               if e["type"] == "generation-create")["body"]
    assert gen["level"] == "ERROR"
    assert gen["statusMessage"] == "unparseable verdict"
    assert "usage" not in gen                  # no usage block when none supplied


def test_record_generation_never_raises(monkeypatch):
    _enable(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(lt.requests, "post", boom)
    # must swallow the exception
    lt.record_generation(name="wallet-gate", input="p", output="o", model="m",
                         start=1.0, end=2.0, usage=_ENVELOPE_USAGE)
