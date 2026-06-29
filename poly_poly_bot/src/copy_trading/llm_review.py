"""Claude gate on newly-qualified wallet candidates (Strategy 1c).

The statistical funnel (closed-position t-stat, lead-lag capture, entry
discipline, PnL-curve shape, copy-replay) is the gate that *narrows* the
universe. For the handful of wallets that survive it, this module assembles a
compact dossier and asks Claude for the qualitative judgment the heuristics
can't make — "is this a genuine informed/consistent trader worth copying, or an
artifact?" — plus its reasoning. The caller uses a ``skip`` verdict to block the
wallet from the paper watchlist (the final admission gate).

The call goes through the ``claude -p`` CLI, which runs on the operator's Claude
subscription (auth via ``CLAUDE_CODE_OAUTH_TOKEN`` — see ``claude setup-token``)
so no ``ANTHROPIC_API_KEY`` is required. It is deliberately defensive: it
degrades to ``None`` on any failure (CLI missing, not authenticated, timeout,
non-JSON output) and the caller treats ``None`` as fail-open (admit) so a broken
CLI never freezes discovery. The subprocess runner is injectable for tests, so
the suite never shells out.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger("poly_poly_bot")

DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_TIMEOUT_S = 180

_SYSTEM = (
    "You are a quantitative analyst vetting Polymarket wallets for a paper-trading "
    "copy bot. You are given a dossier of a wallet that already passed statistical "
    "filters (realized closed-position edge, delayed-copy capture, entry-price "
    "discipline, PnL-curve shape). Judge whether it is a genuine, *copyable* "
    "informed/consistent trader or a likely artifact (variance, settlement-lag "
    "scooping near $1, in-play markets that move before a copier can follow). "
    "Be skeptical: a high ROI from a few lucky bets, tail-price entries, or a "
    "spiky PnL curve should lower the verdict. Reward steady, low-drawdown edge "
    "captured at copyable prices."
)

_INSTRUCTION = (
    "Respond with ONLY a single JSON object (no prose, no markdown fences) with "
    "exactly these keys:\n"
    '{"verdict": "follow"|"watch"|"skip", '
    '"insider_likelihood": "low"|"medium"|"high", '
    '"copyable": true|false, '
    '"confidence": <number 0.0-1.0>, '
    '"reasoning": "<one or two sentences>"}\n'
    "Use \"skip\" only when the wallet looks like an artifact the bot should not "
    "add. Do not use any tools; answer directly from the dossier."
)


@dataclass(frozen=True)
class LLMVerdict:
    verdict: str            # follow | watch | skip
    insider_likelihood: str  # low | medium | high
    copyable: bool
    confidence: float
    reasoning: str


def build_dossier(
    wallet: str,
    *,
    metrics: Any = None,        # WalletMetrics-like (roi, tstat, n_closed, capital, hit_rate, concentration)
    evaluation: Any = None,     # Eval-like (capture_cents, lead_cents, hit_rate, n)
    entry: Any = None,          # EntryProfile-like (mean_entry, tail_ratio, copyable_ratio)
    curve: Any = None,          # CurveMetrics-like (net_pnl, max_drawdown_frac, up_ratio, sharpe)
    portfolio_value: float | None = None,
    recent_bets: list[dict] | None = None,
) -> dict:
    """Assemble the compact, JSON-serializable dossier for one wallet.

    Pure (no network): every field is pulled defensively via getattr so callers
    can pass whatever signals they have. Missing pieces are simply omitted.
    """
    def g(obj, name):
        return getattr(obj, name, None) if obj is not None else None

    d: dict = {"wallet": wallet}
    if metrics is not None:
        d["skill"] = {
            "roi": _round(g(metrics, "roi")),
            "tstat": _round(g(metrics, "tstat"), 2),
            "n_closed": g(metrics, "n_closed"),
            "capital": _round(g(metrics, "capital"), 0),
            "hit_rate": _round(g(metrics, "hit_rate")),
            "concentration": _round(g(metrics, "concentration")),
        }
    if evaluation is not None:
        d["copyability"] = {
            "capture_cents": _round(g(evaluation, "capture_cents"), 2),
            "lead_cents": _round(g(evaluation, "lead_cents"), 2),
            "hit_rate": _round(g(evaluation, "hit_rate")),
            "n_trades": g(evaluation, "n"),
        }
    if entry is not None:
        d["entry_profile"] = {
            "mean_entry_price": _round(g(entry, "mean_entry")),
            "tail_ratio": _round(g(entry, "tail_ratio")),
            "copyable_ratio": _round(g(entry, "copyable_ratio")),
        }
    if curve is not None:
        d["pnl_curve"] = {
            "net_pnl": _round(g(curve, "net_pnl"), 0),
            "max_drawdown_frac": _round(g(curve, "max_drawdown_frac")),
            "up_ratio": _round(g(curve, "up_ratio")),
            "sharpe": _round(g(curve, "sharpe"), 2),
        }
    if portfolio_value is not None:
        d["portfolio_value"] = round(float(portfolio_value), 0)
    if recent_bets:
        d["recent_bets"] = recent_bets[:15]
    return d


def _round(v, ndigits: int = 4):
    return round(float(v), ndigits) if isinstance(v, (int, float)) else v


def _build_prompt(dossier: dict) -> str:
    return (
        f"{_SYSTEM}\n\n"
        "Vet this wallet dossier and decide whether the paper bot should add it:\n"
        f"{json.dumps(dossier, indent=2)}\n\n"
        f"{_INSTRUCTION}"
    )


def _claude_cli_runner(prompt: str, *, model: str, timeout_s: int) -> str | None:
    """Run one ``claude -p`` call on the Claude subscription, return its text.

    Uses ``--output-format json`` (a stable envelope with a ``result`` string)
    and runs in a throwaway temp dir so it never loads the bot's own project
    context (CLAUDE.md, tools). Auth comes from the inherited environment
    (``CLAUDE_CODE_OAUTH_TOKEN``). Returns ``None`` on any non-success.
    """
    exe = shutil.which("claude")
    if not exe:
        logger.warning("[LLM-GATE] `claude` CLI not found on PATH — skipping (fail-open)")
        return None
    cmd = [exe, "-p", prompt, "--output-format", "json", "--model", model]
    with tempfile.TemporaryDirectory(prefix="llm-gate-") as cwd:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s,
            cwd=cwd, env=os.environ.copy(),
        )
    if proc.returncode != 0:
        logger.warning("[LLM-GATE] claude -p exit %s: %s",
                       proc.returncode, (proc.stderr or "")[:300])
        return None
    envelope = json.loads(proc.stdout)
    if envelope.get("is_error") or envelope.get("subtype") != "success":
        logger.warning("[LLM-GATE] claude -p returned error envelope: %s",
                       str(envelope.get("subtype")))
        return None
    return envelope.get("result")


def _parse_verdict(text: str) -> dict | None:
    """Pull the verdict JSON object out of the model's reply (tolerant of
    stray prose or ```json fences)."""
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)  # first balanced-ish object
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def review_wallet(
    dossier: dict,
    *,
    runner: Callable[..., str | None] | None = None,
    model: str = DEFAULT_MODEL,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> LLMVerdict | None:
    """Ask Claude (via ``claude -p``) for a verdict on a dossier.

    Returns ``None`` on any failure so the caller can fail open. ``runner`` is
    injectable for tests; in production it shells out to the ``claude`` CLI.
    """
    runner = runner or _claude_cli_runner
    try:
        text = runner(_build_prompt(dossier), model=model, timeout_s=timeout_s)
        data = _parse_verdict(text) if text else None
        if not data:
            return None
        return LLMVerdict(
            verdict=str(data["verdict"]),
            insider_likelihood=str(data["insider_likelihood"]),
            copyable=bool(data["copyable"]),
            confidence=float(data["confidence"]),
            reasoning=str(data["reasoning"]),
        )
    except Exception:  # never let the gate call break the sweep
        logger.warning("[LLM-GATE] failed for %s", dossier.get("wallet"), exc_info=True)
        return None
