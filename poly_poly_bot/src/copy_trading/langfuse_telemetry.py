"""Minimal Langfuse telemetry for the `claude -p` wallet gate.

Posts ONE complete OTLP/HTTP JSON span — a root observation of type
``generation`` — straight to the Langfuse OpenTelemetry endpoint
(``/api/public/otel/v1/traces``, HTTP Basic auth,
``x-langfuse-ingestion-version: 4``) — no ``langfuse`` SDK dependency,
mirroring the echo-v0 project's approach (keeps the image lean and the deploy
simple). Langfuse v4 is observations-first: there is no separate trace entity
to create, and the legacy event-batch ingestion API this module used to post
to is removed on Langfuse Cloud on 2026-11-16. One finished gate call is one
span, built in memory and exported exactly once (a re-sent span id would
duplicate the observation). The ``claude -p`` JSON envelope already carries
token usage, USD cost and latency, so we forward it — with two corrections
learned the hard way (P2-6, 2026-07-28):

- ``usage_details.input`` is the FULL prompt size (uncached + cache read +
  cache creation). Langfuse derives its displayed input usage from
  ``usage_details``, and the 2026-07-11 CLI update moved the bulk of the prompt
  into the cache keys, so forwarding ``input_tokens`` raw dropped displayed
  input to 2-6 tokens/call (was ~3,000-5,000).
- When a call burned tokens but the envelope carries no ``total_cost_usd``,
  cost is COMPUTED from the token counts (price table below) instead of
  silently landing as $0.00 — the 07-11..14 CLI outage produced exactly such a
  window before anyone noticed.

Fully opt-in and defensive: a no-op unless ``LANGFUSE_PUBLIC_KEY`` and
``LANGFUSE_SECRET_KEY`` are set, and it NEVER raises — a telemetry outage must
not break a discovery sweep. Fire-and-forget with a short timeout.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import uuid
from typing import Any

import requests

logger = logging.getLogger("poly_poly_bot")

_DEFAULT_HOST = "https://cloud.langfuse.com"
_TIMEOUT_S = 8


def _price_per_mtok(name: str, fallback: float) -> float:
    """USD per million tokens, env-overridable; read at call time (test-friendly).
    A malformed override falls back LOUDLY — env drift must not drop rows at
    DEBUG the way envelope drift used to."""
    v = (os.getenv(name) or "").strip()
    if not v:
        return fallback
    try:
        return float(v)
    except ValueError:
        logger.warning("[LANGFUSE] ignoring malformed %s=%r (using %.4g)",
                       name, v, fallback)
        return fallback


def _computed_cost_usd(u: dict) -> float:
    """Fallback USD cost from token counts when the envelope reports none.

    claude-opus-4-8 list prices (the only model this bot gates with). Anthropic
    cache pricing: read = 0.1x input, 5m write = 1.25x, 1h write = 2x. Uses the
    envelope's ephemeral split when present; without it, cache writes are priced
    as 5m (the cheaper bucket — a fallback errs low, never invents spend).
    Calibrated against the live envelope 2026-07-28: $0.0504 computed vs
    $0.0510 reported on a 19.5k-token call."""
    in_base = int(u.get("input_tokens") or 0)
    cache_read = int(u.get("cache_read_input_tokens") or 0)
    cache_creation = int(u.get("cache_creation_input_tokens") or 0)
    out_tok = int(u.get("output_tokens") or 0)
    split = u.get("cache_creation") or {}
    w1h = int(split.get("ephemeral_1h_input_tokens") or 0)
    w5m = int(split.get("ephemeral_5m_input_tokens") or 0)
    if w1h + w5m <= 0:
        w5m, w1h = cache_creation, 0
    micros = (
        in_base * _price_per_mtok("LANGFUSE_PRICE_INPUT_PER_MTOK", 5.0)
        + out_tok * _price_per_mtok("LANGFUSE_PRICE_OUTPUT_PER_MTOK", 25.0)
        + cache_read * _price_per_mtok("LANGFUSE_PRICE_CACHE_READ_PER_MTOK", 0.5)
        + w5m * _price_per_mtok("LANGFUSE_PRICE_CACHE_WRITE_5M_PER_MTOK", 6.25)
        + w1h * _price_per_mtok("LANGFUSE_PRICE_CACHE_WRITE_1H_PER_MTOK", 10.0)
    )
    return micros / 1e6


def _config() -> tuple[str, str, str] | None:
    """(public_key, secret_key, host) or None when telemetry is unconfigured."""
    pub = (os.getenv("LANGFUSE_PUBLIC_KEY") or "").strip()
    sec = (os.getenv("LANGFUSE_SECRET_KEY") or "").strip()
    if not pub or not sec:
        return None
    host = (os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL")
            or _DEFAULT_HOST).strip().rstrip("/")
    return pub, sec, host


def enabled() -> bool:
    return _config() is not None


def _unix_nano(ts: float) -> str:
    """OTLP JSON carries int64 nanoseconds as a decimal string. Integer math
    from milliseconds — ``ts * 1e9`` in floating point invents nano noise."""
    return str(int(round(ts * 1e3)) * 1_000_000)


def _otlp_value(v: Any) -> dict:
    """One typed OTLP AnyValue. ``bool`` is checked BEFORE ``int`` (a Python
    bool IS an int); an int64 rides as a decimal string, per OTLP/JSON."""
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, str):
        return {"stringValue": v}
    if isinstance(v, (list, tuple)) and all(isinstance(x, str) for x in v):
        return {"arrayValue": {"values": [{"stringValue": x} for x in v]}}
    # OTLP attributes cannot nest: anything structured rides as a JSON string.
    return {"stringValue": json.dumps(v, default=str)}


def _io_value(v: Any) -> str | None:
    """Observation input/output: a string as-is, anything else as JSON."""
    if v is None:
        return None
    return v if isinstance(v, str) else json.dumps(v, default=str)


def record_generation(
    *,
    name: str,
    input: Any,
    output: Any,
    model: str,
    start: float,
    end: float,
    usage: dict | None = None,        # the claude -p envelope's `usage` block
    cost_usd: float | None = None,
    duration_ms: float | None = None,
    metadata: dict | None = None,
    tags: list[str] | None = None,
    error: str | None = None,
) -> None:
    """Emit one root generation span to Langfuse. No-op if unconfigured; never raises.

    ``usage`` is forwarded in the Anthropic shape (input_tokens, output_tokens,
    cache_read_input_tokens, cache_creation_input_tokens) exactly as the
    ``claude -p`` envelope returns it; we map it to Langfuse ``usage_details``.
    ``usage_details.input`` is the full prompt size (see module docstring, P2-6);
    cost falls back to a computed value when the envelope carries none.
    """
    cfg = _config()
    if cfg is None:
        return
    pub, sec, host = cfg
    try:
        u = usage or {}
        try:
            in_base = int(u.get("input_tokens") or 0)
            cache_read = int(u.get("cache_read_input_tokens") or 0)
            cache_creation = int(u.get("cache_creation_input_tokens") or 0)
            out_tok = int(u.get("output_tokens") or 0)
            split = u.get("cache_creation") or {}
            w1h = int(split.get("ephemeral_1h_input_tokens") or 0)
            w5m = int(split.get("ephemeral_5m_input_tokens") or 0)
        except (TypeError, ValueError, AttributeError) as e:
            # Unparseable usage shape: drop the row, but LOUDLY — the
            # 2026-07-11 regression was a silent envelope shape change, and a
            # wholesale provider-side change SHOULD flood WARNINGs. (Still
            # never raises: telemetry must not break a sweep.)
            desc = ({k: type(v).__name__ for k, v in u.items()}
                    if isinstance(u, dict) else type(u).__name__)
            logger.warning(
                "[LANGFUSE] dropping %s generation: unparseable usage block "
                "(%r); keys/types: %s", name, e, desc)
            return
        prompt_tok = in_base + cache_read + cache_creation
        has_usage = prompt_tok > 0 or out_tok > 0

        # Cost: the envelope's own figure wins; when it's absent/0 but tokens
        # were burned, compute from the price table so cost never lands as a
        # silent $0.00 (P2-6). `cost_details` must ALWAYS ride a success row —
        # with usage_details.input now the full prompt size, a missing
        # cost_details would let Langfuse's own calc price the cache tokens
        # twice.
        if cost_usd:
            cost, cost_source = cost_usd, "envelope"
        elif has_usage:
            cost, cost_source = _computed_cost_usd(u), "computed"
        else:
            cost, cost_source = None, "none"

        meta = dict(metadata or {})
        if cost_usd is not None:
            meta["costUsd"] = cost_usd
        meta["costSource"] = cost_source
        if duration_ms is not None:
            meta["durationMs"] = duration_ms

        # I4 watchdog: a successful generation with zero usage means the
        # envelope shape drifted under us (the 2026-07-11 regression class) —
        # make it loud instead of letting bad accounting sit invisible.
        tags_out = list(tags or [])
        if error is None and not has_usage:
            logger.warning(
                "[LANGFUSE] %s generation succeeded but carries zero usage — "
                "envelope shape drift?", name)
            tags_out.append("telemetry-suspect")

        level = "ERROR" if error else "DEFAULT"

        attrs: dict[str, Any] = {
            "langfuse.observation.type": "generation",
            "langfuse.trace.name": name,
            "langfuse.trace.tags": tags_out,
            "langfuse.observation.input": _io_value(input),
            "langfuse.observation.output": _io_value(output),
            "langfuse.observation.model.name": model,
            # P1-4: the ERROR level must be visible in Langfuse's error
            # views/filters — ~13-15% of gate calls could fail open with "zero
            # error traces" (§1.7a) while the level rode only a child
            # generation. v4 has no trace entity: a trace is its observations,
            # and its level is read off the ROOT observation. This single span
            # IS the root, so the level rides here — and the OTLP span status
            # (below) says the same thing, so either mapping catches it.
            "langfuse.observation.level": level,
            "langfuse.observation.status_message": error or None,
        }
        if has_usage:
            details = {
                # input = FULL prompt tokens (uncached + cache read + cache
                # creation), not the envelope's uncached remainder — Langfuse
                # derives displayed input from usage_details, which is how it
                # collapsed to 2-6 tokens on 2026-07-11 (P2-6). (The legacy
                # `usage` {unit: TOKENS} block has no OTLP equivalent;
                # usage_details carries the numbers.)
                "input": prompt_tok, "output": out_tok,
                "cache_read": cache_read, "cache_creation": cache_creation,
                "total": prompt_tok + out_tok,
            }
            if w1h or w5m:
                details["cache_creation_5m"] = w5m
                details["cache_creation_1h"] = w1h
            attrs["langfuse.observation.usage_details"] = json.dumps(details)
        if cost is not None:
            # `is not None`, not truthiness: an operator zeroing every
            # LANGFUSE_PRICE_* override yields computed cost 0.0, and omitting
            # cost_details then would let Langfuse's own calc price the
            # full-prompt input AND the cache keys twice.
            attrs["langfuse.observation.cost_details"] = json.dumps({"total": cost})
        for k, v in meta.items():
            attrs[f"langfuse.observation.metadata.{k}"] = v

        span = {
            "traceId": uuid.uuid4().hex,          # 32 hex chars
            "spanId": secrets.token_hex(8),       # 16 hex chars
            "name": name,
            "kind": 1,                            # SPAN_KIND_INTERNAL
            "startTimeUnixNano": _unix_nano(start),
            "endTimeUnixNano": _unix_nano(end),
            "attributes": [{"key": k, "value": _otlp_value(v)}
                           for k, v in attrs.items() if v is not None],
            "status": ({"code": 2, "message": error} if error else {"code": 1}),
        }
        payload = {"resourceSpans": [{
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": "poly-poly-bot"}}]},
            "scopeSpans": [{"scope": {"name": "langfuse-telemetry"},
                            "spans": [span]}],
        }]}

        auth = base64.b64encode(f"{pub}:{sec}".encode()).decode()
        resp = requests.post(
            f"{host}/api/public/otel/v1/traces",
            json=payload,
            headers={"Authorization": f"Basic {auth}",
                     "Content-Type": "application/json",
                     "x-langfuse-ingestion-version": "4"},
            timeout=_TIMEOUT_S,
        )
        if not 200 <= resp.status_code < 300:
            # WARNING, not debug: the app logger's DEBUG reaches only the
            # docker console, so a 401 (rotated key), a 404 (wrong host or
            # path) or a 5xx storm after the 2026-11-16 cutover would be the
            # exact "went dark silently" this rewrite exists to prevent — and
            # the I4 watchdog cannot see it, it only reads rows that landed.
            logger.warning("[LANGFUSE] Langfuse refused the %s span: HTTP %s %s",
                           name, resp.status_code, resp.text[:200])
            return
        # OTLP answers 200 even when it refuses spans; the refusal rides the
        # body. An empty/unparseable body is a clean accept. A rejection is
        # LOUD — a silently refused span is the same invisible-bad-accounting
        # class as envelope drift.
        try:
            rejected = int((resp.json().get("partialSuccess") or {})
                           .get("rejectedSpans") or 0)
        except Exception:
            rejected = 0
        if rejected > 0:
            logger.warning("[LANGFUSE] Langfuse rejected the %s span "
                           "(partialSuccess.rejectedSpans=%s)", name, rejected)
    except Exception as exc:  # telemetry must never break the gate
        # Same reasoning as the non-2xx branch: a dead host or a serializer
        # bug on every call is telemetry gone dark, and DEBUG would hide it.
        logger.warning("[LANGFUSE] telemetry post failed for %s: %r", name, exc)
        logger.debug("[LANGFUSE] telemetry post traceback", exc_info=True)
