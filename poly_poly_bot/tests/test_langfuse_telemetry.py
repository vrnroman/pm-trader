"""Langfuse telemetry — wire format + opt-in/defensive behavior (no real network)."""

from __future__ import annotations

import base64
import json
import re
from types import SimpleNamespace

import pytest

from src.copy_trading import langfuse_telemetry as lt

_ENVELOPE_USAGE = {
    "input_tokens": 3000, "output_tokens": 40,
    "cache_read_input_tokens": 12000, "cache_creation_input_tokens": 500,
}


def _only_span(body):
    """The payload is exactly ONE resource → ONE scope → ONE span."""
    (rs,) = body["resourceSpans"]
    (ss,) = rs["scopeSpans"]
    (span,) = ss["spans"]
    return span


def _attrs(span):
    return {a["key"]: a["value"] for a in span["attributes"]}


def _json_attr(attrs, key):
    return json.loads(attrs[key]["stringValue"])


def _meta(attrs, key):
    return attrs[f"langfuse.observation.metadata.{key}"]


def _tags(attrs):
    return [v["stringValue"]
            for v in attrs["langfuse.trace.tags"]["arrayValue"]["values"]]


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


def test_record_generation_posts_one_otlp_root_generation_span(monkeypatch):
    _enable(monkeypatch)
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(url=url, body=json, headers=headers, timeout=timeout)
        return SimpleNamespace(status_code=200, text="", json=lambda: {})

    monkeypatch.setattr(lt.requests, "post", fake_post)
    lt.record_generation(
        name="wallet-gate", input="the prompt", output='{"verdict":"skip"}',
        model="claude-opus-4-8", start=1000.0, end=1024.5,
        usage=_ENVELOPE_USAGE, cost_usd=0.037, duration_ms=4490,
        metadata={"wallet": "0xABC", "verdict": "skip", "kept": True},
        tags=["wallet-gate"], error=None,
    )

    # The v4 OTLP endpoint — and never the removed legacy ingestion API.
    assert captured["url"] == "https://jp.cloud.langfuse.com/api/public/otel/v1/traces"
    assert "/api/public/ingestion" not in captured["url"]
    # Basic auth = base64(public:secret)
    assert captured["headers"]["Authorization"] == "Basic " + base64.b64encode(
        b"pk-test:sk-test").decode()
    assert captured["headers"]["x-langfuse-ingestion-version"] == "4"
    assert captured["headers"]["Content-Type"] == "application/json"
    assert captured["timeout"] == lt._TIMEOUT_S
    assert "batch" not in captured["body"]     # not the legacy event batch

    span = _only_span(captured["body"])
    # OTLP/JSON to the letter: hex ids of the right width, no parent (root),
    # int64 nanos as decimal strings with no float noise.
    assert re.fullmatch(r"[0-9a-f]{32}", span["traceId"])
    assert re.fullmatch(r"[0-9a-f]{16}", span["spanId"])
    assert "parentSpanId" not in span
    assert span["name"] == "wallet-gate"
    assert span["startTimeUnixNano"] == "1000000000000"
    assert span["endTimeUnixNano"] == "1024500000000"
    assert span["status"] == {"code": 1}

    attrs = _attrs(span)
    assert attrs["langfuse.observation.type"] == {"stringValue": "generation"}
    assert attrs["langfuse.trace.name"] == {"stringValue": "wallet-gate"}
    assert _tags(attrs) == ["wallet-gate"]
    assert attrs["langfuse.observation.model.name"] == {"stringValue": "claude-opus-4-8"}
    assert attrs["langfuse.observation.level"] == {"stringValue": "DEFAULT"}
    assert "langfuse.observation.status_message" not in attrs
    # overall input/output live on the ROOT OBSERVATION; trace i/o is deprecated
    assert attrs["langfuse.observation.input"] == {"stringValue": "the prompt"}
    assert attrs["langfuse.observation.output"] == {"stringValue": '{"verdict":"skip"}'}
    assert "langfuse.trace.input" not in attrs
    assert "langfuse.trace.output" not in attrs
    # P2-6: usage_details.input is the FULL prompt size (input + cache_read +
    # cache_creation), not the uncached remainder — Langfuse derives its
    # displayed input usage from usage_details. Rides as a JSON STRING.
    assert _json_attr(attrs, "langfuse.observation.usage_details") == {
        "input": 15500, "output": 40,
        "cache_read": 12000, "cache_creation": 500, "total": 15540,
    }
    assert _json_attr(attrs, "langfuse.observation.cost_details") == {"total": 0.037}
    # typed values: str / bool (NOT int) / int64-as-string / double
    assert _meta(attrs, "wallet") == {"stringValue": "0xABC"}
    assert _meta(attrs, "kept") == {"boolValue": True}
    assert _meta(attrs, "durationMs") == {"intValue": "4490"}
    assert _meta(attrs, "costUsd") == {"doubleValue": 0.037}
    assert _meta(attrs, "costSource") == {"stringValue": "envelope"}


def test_structured_io_and_metadata_ride_as_json_strings(monkeypatch):
    attrs, _ = _posted_gen(monkeypatch, usage=_ENVELOPE_USAGE, cost_usd=0.01,
                           metadata={"scores": {"roi": 0.5}})
    assert json.loads(_meta(attrs, "scores")["stringValue"]) == {"roi": 0.5}
    _enable(monkeypatch)
    captured = {}
    monkeypatch.setattr(lt.requests, "post", lambda url, json=None, **k: (
        captured.update(body=json) or SimpleNamespace(status_code=200, text="")))
    lt.record_generation(name="wallet-gate", input={"q": [1, 2]}, output=None,
                         model="m", start=1.0, end=2.0, usage=_ENVELOPE_USAGE)
    a = _attrs(_only_span(captured["body"]))
    assert json.loads(a["langfuse.observation.input"]["stringValue"]) == {"q": [1, 2]}
    assert "langfuse.observation.output" not in a      # None is skipped, not "null"


def test_every_call_gets_fresh_ids(monkeypatch):
    # v4 does not deduplicate: a re-sent span id would duplicate the observation.
    _, one = _posted_gen(monkeypatch, usage=_ENVELOPE_USAGE, cost_usd=0.01)
    _, two = _posted_gen(monkeypatch, usage=_ENVELOPE_USAGE, cost_usd=0.01)
    assert one["traceId"] != two["traceId"]
    assert one["spanId"] != two["spanId"]


# The shape the claude CLI actually returns since 2026-07-11 (2.1.x): the whole
# prompt lives in the cache keys, input_tokens is a 2-token remainder, and the
# cache_creation block splits ephemeral 5m/1h writes.
_CURRENT_ENVELOPE_USAGE = {
    "input_tokens": 2, "output_tokens": 738,
    "cache_read_input_tokens": 15240, "cache_creation_input_tokens": 5764,
    "cache_creation": {"ephemeral_1h_input_tokens": 5764,
                       "ephemeral_5m_input_tokens": 0},
}


def _posted_gen(monkeypatch, **kwargs):
    """(attribute map, span) of the single span one record_generation posts."""
    _enable(monkeypatch)
    captured = {}
    monkeypatch.setattr(lt.requests, "post", lambda url, json=None, **k: (
        captured.update(body=json) or SimpleNamespace(status_code=200, text="")))
    lt.record_generation(name="wallet-gate", input="p", output="o",
                         model="claude-opus-4-8", start=1.0, end=2.0, **kwargs)
    span = _only_span(captured["body"])
    return _attrs(span), span


def _cost(attrs):
    return _json_attr(attrs, "langfuse.observation.cost_details")["total"]


def test_current_envelope_maps_full_prompt_and_ephemeral_split(monkeypatch):
    attrs, _ = _posted_gen(monkeypatch, usage=_CURRENT_ENVELOPE_USAGE,
                           cost_usd=0.0854)
    details = _json_attr(attrs, "langfuse.observation.usage_details")
    assert details["input"] == 21006               # 2 + 15240 + 5764
    assert details["cache_creation_1h"] == 5764
    assert details["cache_creation_5m"] == 0
    assert _cost(attrs) == 0.0854
    assert _meta(attrs, "costSource") == {"stringValue": "envelope"}


def test_no_split_keys_without_an_ephemeral_split(monkeypatch):
    attrs, _ = _posted_gen(monkeypatch, usage=_ENVELOPE_USAGE, cost_usd=0.01)
    details = _json_attr(attrs, "langfuse.observation.usage_details")
    assert "cache_creation_1h" not in details
    assert "cache_creation_5m" not in details


def test_cost_falls_back_to_computed_when_envelope_reports_none(monkeypatch):
    attrs, _ = _posted_gen(monkeypatch, usage=_CURRENT_ENVELOPE_USAGE,
                           cost_usd=None)
    # 2*5 + 738*25 + 15240*0.5 + 5764*10 (1h write) per Mtok = $0.08372
    assert _cost(attrs) == pytest.approx(0.08372)
    assert _meta(attrs, "costSource") == {"stringValue": "computed"}
    assert "langfuse.observation.metadata.costUsd" not in attrs   # none reported


def test_cost_fallback_treats_zero_envelope_cost_as_missing(monkeypatch):
    attrs, _ = _posted_gen(monkeypatch, usage=_CURRENT_ENVELOPE_USAGE,
                           cost_usd=0.0)
    assert _cost(attrs) > 0
    assert _meta(attrs, "costSource") == {"stringValue": "computed"}


def test_cost_fallback_no_ephemeral_split_prices_5m_writes(monkeypatch):
    usage = {"input_tokens": 100, "output_tokens": 10,
             "cache_creation_input_tokens": 1000}
    attrs, _ = _posted_gen(monkeypatch, usage=usage, cost_usd=None)
    # 100*5 + 10*25 + 1000*6.25 per Mtok = $0.007
    assert _cost(attrs) == pytest.approx(0.007)


def test_computed_cost_honors_env_price_override(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PRICE_INPUT_PER_MTOK", "50")
    attrs, _ = _posted_gen(monkeypatch,
                           usage={"input_tokens": 1000, "output_tokens": 0},
                           cost_usd=None)
    assert _cost(attrs) == pytest.approx(0.05)


def test_zeroed_price_overrides_still_send_cost_details(monkeypatch):
    # `is not None`, not truthiness: a computed cost of 0.0 must STILL ride,
    # or Langfuse's own calc would price the full-prompt input AND the cache
    # keys twice.
    for k in ("INPUT", "OUTPUT", "CACHE_READ", "CACHE_WRITE_5M", "CACHE_WRITE_1H"):
        monkeypatch.setenv(f"LANGFUSE_PRICE_{k}_PER_MTOK", "0")
    attrs, _ = _posted_gen(monkeypatch, usage=_CURRENT_ENVELOPE_USAGE,
                           cost_usd=None)
    assert _json_attr(attrs, "langfuse.observation.cost_details") == {"total": 0.0}
    assert _meta(attrs, "costSource") == {"stringValue": "computed"}


def test_watchdog_tags_success_with_zero_usage(monkeypatch, caplog):
    attrs, _ = _posted_gen(monkeypatch, usage=None, cost_usd=None)
    # cost_details is absent ONLY when no tokens were burned
    assert "langfuse.observation.usage_details" not in attrs
    assert "langfuse.observation.cost_details" not in attrs
    assert _meta(attrs, "costSource") == {"stringValue": "none"}
    assert "telemetry-suspect" in _tags(attrs)
    assert any("zero usage" in r.message for r in caplog.records
               if r.levelname == "WARNING")


def test_watchdog_quiet_on_a_normal_row(monkeypatch, caplog):
    attrs, _ = _posted_gen(monkeypatch, usage=_ENVELOPE_USAGE, cost_usd=0.01,
                           tags=["wallet-gate"])
    assert _tags(attrs) == ["wallet-gate"]          # no telemetry-suspect
    assert not any("zero usage" in r.message for r in caplog.records)


def test_watchdog_silent_on_failed_calls(monkeypatch, caplog):
    # failed calls truthfully carry no usage — that is not shape drift
    attrs, _ = _posted_gen(monkeypatch, usage=None, cost_usd=None,
                           error="rate-limited")
    assert attrs["langfuse.observation.level"] == {"stringValue": "ERROR"}
    assert "telemetry-suspect" not in _tags(attrs)
    assert not any("zero usage" in r.message for r in caplog.records)


def test_unparseable_usage_drops_row_with_warning(monkeypatch, caplog):
    _enable(monkeypatch)
    posted = []
    monkeypatch.setattr(lt.requests, "post", lambda *a, **k: posted.append((a, k)))
    lt.record_generation(name="wallet-gate", input="p", output="o",
                         model="m", start=1.0, end=2.0,
                         usage={"input_tokens": "lots"})
    assert posted == []                       # row dropped, never raised
    assert any("unparseable usage" in r.message for r in caplog.records
               if r.levelname == "WARNING")


def test_non_dict_usage_drops_row_with_warning(monkeypatch, caplog):
    _enable(monkeypatch)
    posted = []
    monkeypatch.setattr(lt.requests, "post", lambda *a, **k: posted.append((a, k)))
    lt.record_generation(name="wallet-gate", input="p", output="o",
                         model="m", start=1.0, end=2.0, usage="garbage")
    assert posted == []
    assert any("unparseable usage" in r.message for r in caplog.records
               if r.levelname == "WARNING")


def test_record_generation_marks_error_level(monkeypatch):
    attrs, span = _posted_gen(monkeypatch, error="unparseable verdict")
    assert attrs["langfuse.observation.level"] == {"stringValue": "ERROR"}
    assert attrs["langfuse.observation.status_message"] == {
        "stringValue": "unparseable verdict"}
    assert span["status"] == {"code": 2, "message": "unparseable verdict"}
    # no usage block when none supplied
    assert "langfuse.observation.usage_details" not in attrs

    # the other direction: a success is DEFAULT, status OK, no message
    attrs, span = _posted_gen(monkeypatch, usage=_ENVELOPE_USAGE, cost_usd=0.01)
    assert attrs["langfuse.observation.level"] == {"stringValue": "DEFAULT"}
    assert "langfuse.observation.status_message" not in attrs
    assert span["status"] == {"code": 1}


def _respond(monkeypatch, resp):
    _enable(monkeypatch)
    monkeypatch.setattr(lt.requests, "post", lambda *a, **k: resp)
    lt.record_generation(name="wallet-gate", input="p", output="o", model="m",
                         start=1.0, end=2.0, usage=_ENVELOPE_USAGE, cost_usd=0.01)


@pytest.mark.parametrize("rejected", [1, "2"])
def test_rejected_span_warns_and_never_raises(monkeypatch, caplog, rejected):
    # OTLP answers 200 even when it refuses the span; the refusal rides the body.
    _respond(monkeypatch, SimpleNamespace(
        status_code=200, text="",
        json=lambda: {"partialSuccess": {"rejectedSpans": rejected}}))
    assert any("rejected" in r.message for r in caplog.records
               if r.levelname == "WARNING")


def _bad_json():
    raise ValueError("no body")


@pytest.mark.parametrize("body", [
    lambda: {}, lambda: {"partialSuccess": {}},
    lambda: {"partialSuccess": {"rejectedSpans": 0}}, lambda: [], _bad_json,
])
def test_clean_accept_is_silent(monkeypatch, caplog, body):
    _respond(monkeypatch, SimpleNamespace(status_code=200, text="", json=body))
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_non_2xx_never_raises_and_stays_at_debug(monkeypatch, caplog):
    _respond(monkeypatch, SimpleNamespace(status_code=401, text="nope",
                                          json=_bad_json))
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_record_generation_never_raises(monkeypatch):
    _enable(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(lt.requests, "post", boom)
    # must swallow the exception
    lt.record_generation(name="wallet-gate", input="p", output="o", model="m",
                         start=1.0, end=2.0, usage=_ENVELOPE_USAGE)
