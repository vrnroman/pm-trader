"""The news bot's one way to call Claude (DESIGN.md, `llm.py`).

``run_claude`` shells out to ``claude -p --output-format json --model <model>``
exactly like the copy bot's wallet gate (``copy_trading.llm_review``): the call
runs on the owner's subscription (``CLAUDE_CODE_OAUTH_TOKEN`` inherited from
the environment), in a throwaway cwd so it never loads this repo's CLAUDE.md or
tools, with one bounded retry, and it returns the JSON envelope, the shared
``RATE_LIMITED`` sentinel, or ``None``. ``DailyBudget`` is the per-UTC-day cap
on those calls, persisted so a restart does not reset the meter.

The subprocess runner and the clock are injectable: the suite never shells out
and never reads the wall clock (2026-10-25).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from typing import Callable

# A sentinel no real envelope can be: the subscription is limited, try later.
RATE_LIMITED = object()

# Markers of a spend/usage/rate-limit reply (a real one: "You've hit your
# monthly spend limit · raise it at claude.ai/settings/usage"), matched
# case-insensitively across stderr, stdout and the envelope.
_RATE_LIMIT_MARKERS = ("spend limit", "usage limit", "rate limit", "claude.ai/settings/usage")


def _looks_rate_limited(*texts: str | None) -> bool:
    blob = " ".join(t for t in texts if t).lower()
    return any(m in blob for m in _RATE_LIMIT_MARKERS)

logger = logging.getLogger("poly_poly_bot")

__all__ = ["RATE_LIMITED", "run_claude", "DailyBudget", "default_budget_path",
           "subprocess_runner", "looks_rate_limited"]

looks_rate_limited = _looks_rate_limited

# A runner takes the argv and returns something with returncode/stdout/stderr
# (a CompletedProcess), or raises TimeoutExpired/OSError. Tests inject one.
Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def subprocess_runner(cmd: list[str], *, timeout_s: float) -> "subprocess.CompletedProcess[str]":
    with tempfile.TemporaryDirectory(prefix="news-llm-") as cwd:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s,
                              cwd=cwd, env=os.environ.copy())


def run_claude(prompt: str, *, model: str, timeout_s: int = 60,
               runner: Runner | None = None, tag: str = "news-llm") -> dict | object | None:
    """One ``claude -p`` call. Returns the parsed envelope dict (``result`` holds
    the model's text), ``RATE_LIMITED`` when the subscription is limited or the
    CLI failed twice (a transient worth retrying later), or ``None`` for the
    un-retriable (CLI missing, non-JSON or error envelope)."""
    if runner is None:
        exe = shutil.which("claude")
        if not exe:
            logger.warning("[%s] `claude` CLI not found on PATH — no judgement", tag)
            return None
        runner = subprocess_runner
    else:
        exe = "claude"
    cmd = [exe, "-p", prompt, "--output-format", "json", "--model", model]
    proc = None
    for attempt in (1, 2):
        try:
            proc = runner(cmd, timeout_s=timeout_s)
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.warning("[%s] claude -p attempt %d/2 failed to run: %r", tag, attempt, e)
            proc = None
            continue
        if proc.returncode == 0:
            break
        logger.warning("[%s] claude -p exit %s (attempt %d/2) stderr: %s | stdout: %s",
                       tag, proc.returncode, attempt,
                       (proc.stderr or "")[:300] or "<empty>",
                       (proc.stdout or "")[:300] or "<empty>")
        if _looks_rate_limited(proc.stderr, proc.stdout):
            logger.warning("[%s] claude -p is rate/spend-limited", tag)
            return RATE_LIMITED
    if proc is None or proc.returncode != 0:
        logger.warning("[%s] claude -p failed twice — treating as limited", tag)
        return RATE_LIMITED
    try:
        envelope = json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError):
        if _looks_rate_limited(proc.stdout, proc.stderr):
            return RATE_LIMITED
        logger.warning("[%s] claude -p emitted non-JSON stdout: %s", tag, (proc.stdout or "")[:200])
        return None
    if not isinstance(envelope, dict):
        logger.warning("[%s] claude -p envelope is not an object: %s", tag, type(envelope).__name__)
        return None
    if envelope.get("is_error") or envelope.get("subtype") != "success":
        if _looks_rate_limited(json.dumps(envelope), proc.stderr):
            logger.warning("[%s] claude -p error envelope is a rate/spend limit", tag)
            return RATE_LIMITED
        logger.warning("[%s] claude -p returned error envelope: %s", tag, str(envelope.get("subtype")))
        return None
    return envelope


def default_budget_path(data_dir: str) -> str:
    return os.path.join(data_dir, "news", "llm-budget.json")


class DailyBudget:
    """``limit`` LLM calls per UTC day, counted in a small JSON file.

    ``take()`` is the only mutator: it says whether this call may run and, if so,
    counts it. The day boundary is UTC midnight (the brief's clock too), read from
    the injectable ``clock`` so tests pin it."""

    def __init__(self, path: str | os.PathLike, limit: int, *,
                 clock: Callable[[], float] | None = None):
        self.path = str(path)
        self.limit = max(0, int(limit))
        self._clock = clock or time.time

    def _day(self) -> str:
        return datetime.fromtimestamp(self._clock(), tz=timezone.utc).strftime("%Y-%m-%d")

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("count"), int):
                return data
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            # A torn write must not fail the day closed — or open. Log, start the day at 0.
            logger.warning("[news-llm] budget file unreadable (%r) — counting from 0", e)
        return {"day": None, "count": 0}

    def _save(self, data: dict) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, self.path)

    def count_today(self) -> int:
        data = self._load()
        return int(data["count"]) if data.get("day") == self._day() else 0

    def remaining(self) -> int:
        return max(0, self.limit - self.count_today())

    def take(self) -> bool:
        today = self._day()
        data = self._load()
        count = int(data["count"]) if data.get("day") == today else 0
        if count >= self.limit:
            return False
        self._save({"day": today, "count": count + 1})
        return True
