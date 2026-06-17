"""Gated Claude second-opinion on top wallet candidates (Strategy 1c).

The statistical funnel (closed-position t-stat, lead-lag capture, entry
discipline, PnL-curve shape) is the gate that *narrows* the universe. For the
handful of wallets that survive it, this module assembles a compact dossier and
asks Claude for a qualitative judgment the heuristics can't make — "does this
look like a genuine informed/consistent trader worth copying, or an artifact?"
— plus its reasoning.

It is deliberately defensive: alert-only, never auto-trades, gated behind a
config flag and a small top-N, and degrades to ``None`` on any error (missing
API key, network failure, safety refusal) so a discovery sweep never breaks
because the LLM call did. The ``anthropic`` SDK is imported lazily so the rest
of the bot — and the test suite — runs whether or not it's installed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("poly_poly_bot")

DEFAULT_MODEL = "claude-opus-4-8"

# Structured-output schema: a small, gradeable verdict (no free-form sprawl).
_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["follow", "watch", "skip"]},
        "insider_likelihood": {"type": "string", "enum": ["low", "medium", "high"]},
        "copyable": {"type": "boolean"},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
    },
    "required": ["verdict", "insider_likelihood", "copyable", "confidence", "reasoning"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are a quantitative analyst vetting Polymarket wallets for a paper-trading "
    "copy bot. You are given a dossier of a wallet that already passed statistical "
    "filters (realized closed-position edge, delayed-copy capture, entry-price "
    "discipline, PnL-curve shape). Judge whether it is a genuine, *copyable* "
    "informed/consistent trader or a likely artifact (variance, settlement-lag "
    "scooping near $1, in-play markets that move before a copier can follow). "
    "Be skeptical: a high ROI from a few lucky bets, tail-price entries, or a "
    "spiky PnL curve should lower the verdict. Reward steady, low-drawdown edge "
    "captured at copyable prices. Return only the structured verdict."
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


def review_wallet(
    dossier: dict,
    *,
    client: Any = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 3000,
) -> LLMVerdict | None:
    """Ask Claude for a verdict on a dossier. Returns ``None`` on any failure.

    ``client`` is injectable for tests; in production it's lazily constructed
    (reads ANTHROPIC_API_KEY from the environment).
    """
    try:
        if client is None:
            import anthropic  # lazy: keeps the bot importable without the SDK
            client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": _VERDICT_SCHEMA}},
            system=_SYSTEM,
            messages=[{"role": "user",
                       "content": "Vet this wallet dossier:\n"
                                  + json.dumps(dossier, indent=2)}],
        )
        if getattr(resp, "stop_reason", None) == "refusal":
            logger.info("[LLM-REVIEW] refusal for %s", dossier.get("wallet"))
            return None
        text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), None)
        if not text:
            return None
        data = json.loads(text)
        return LLMVerdict(
            verdict=str(data["verdict"]),
            insider_likelihood=str(data["insider_likelihood"]),
            copyable=bool(data["copyable"]),
            confidence=float(data["confidence"]),
            reasoning=str(data["reasoning"]),
        )
    except Exception:  # never let a second-opinion call break the sweep
        logger.warning("[LLM-REVIEW] failed for %s", dossier.get("wallet"), exc_info=True)
        return None
