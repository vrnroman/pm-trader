"""The one LLM call per news item (DESIGN.md, `judge.py`).

Input: an ``Item`` plus the index's FTS candidates with their current quotes and
the tape's freshness verdict per outcome token. Output: DESIGN.md's strict JSON
object, validated against the candidates that were offered — the model may only
pick a market and an outcome it was shown. The call is bounded by the daily
budget, treats a rate limit as "no verdict", and never raises into the caller:
a judge that crashes the poller would silence every source at once.

``already_priced`` is advisory; the tape rule in ``freshness.py`` decides.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from src.newsbot.llm import RATE_LIMITED, run_claude

logger = logging.getLogger("poly_poly_bot")

TEXT_CHARS = 1200
MATERIAL_POINTS = 5
RATE_LIMIT_LOG_EVERY_S = 3600.0

_FENCE = re.compile(r"```[a-zA-Z]*\s*|```")


@dataclass(frozen=True)
class Judgement:
    material: bool
    market_id: str | None
    outcome_index: int | None
    direction: str | None        # "yes" | "no" | None
    implied_prob: float | None
    confidence: float
    why: str
    already_priced: bool
    llm_ms: int
    model: str
    prompt_chars: int


def _iso(ts: float | None) -> str:
    if ts is None:
        return "unknown"
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    except (OverflowError, OSError, ValueError):
        return "unknown"


def _fmt_px(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.3f}".rstrip("0").rstrip(".")


def _quotes_for(cand, i: int, quotes_by_token: Mapping[str, Any] | None) -> tuple[float | None, float | None]:
    """Bid/ask for outcome ``i``: the CLOB's own quote for that token when the
    tape has one, else Gamma's market quote (outcome 0) and its complement for
    outcome 1 — a Polymarket market is binary, so 1-ask/1-bid is exact."""
    tok = cand.token_ids[i] if i < len(cand.token_ids) else None
    if quotes_by_token and tok in quotes_by_token:
        q = quotes_by_token[tok]
        try:
            if isinstance(q, Mapping):
                return q.get("bid"), q.get("ask")
            return q[0], q[1]
        except (TypeError, IndexError, KeyError):
            pass
    bid, ask = cand.best_bid, cand.best_ask
    if i == 0 or len(cand.outcomes) != 2:
        return (bid, ask) if i == 0 else (None, None)
    return ((None if ask is None else round(1 - ask, 4)),
            (None if bid is None else round(1 - bid, 4)))


def _freshness_line(tok: str | None, freshness_by_token: Mapping[str, Any] | None) -> str:
    v = freshness_by_token.get(tok) if (freshness_by_token and tok) else None
    if v is None:
        return "unknown"
    if isinstance(v, (tuple, list)):
        verdict = str(v[0]) if v else "unknown"
        detail = str(v[1]) if len(v) > 1 and v[1] else ""
        return f"{verdict} ({detail})" if detail else verdict
    return str(v)


def build_prompt(item, candidates: Iterable, freshness_by_token: Mapping[str, Any] | None,
                 *, quotes_by_token: Mapping[str, Any] | None = None) -> str:
    cands = list(candidates)
    text = (getattr(item, "text", "") or "").strip()
    if len(text) > TEXT_CHARS:
        text = text[:TEXT_CHARS].rstrip() + " [...]"
    domains = ",".join(getattr(item, "domains", ()) or ()) or "-"
    lines = [
        "You judge news for a Polymarket paper trader. Decide whether this item is NEW, "
        "MATERIAL information for exactly one of the candidate markets below.",
        "",
        "ITEM",
        f"source: {getattr(item, 'source', '') or '?'} | published: {_iso(getattr(item, 'published_ts', None))}"
        f" | domains: {domains}",
        f"title: {(getattr(item, 'title', '') or '').strip()}",
        f"text: {text or '-'}",
        f"url: {getattr(item, 'url', '') or '-'}",
        "",
        "CANDIDATE MARKETS (pick at most one, by market_id; quotes are the current best bid/ask "
        "of each outcome's token; tape is the price-feed verdict for that token: fresh = no "
        "recent move, moving = a move is under way now, late = it already moved, unknown = no tape)",
    ]
    for c in cands:
        # No "[n]" list numbers: on 2026-10-25 the model answered market_id
        # "1" (the label) for the day's only material call and it was lost.
        lines.append(f"- market_id={c.market_id} | event: {c.event_title or '-'} | "
                     f"question: {c.question} | ends {_iso(c.end_ts)}"
                     + (" | SPORTS" if getattr(c, "is_sports", False) else ""))
        for i, outcome in enumerate(c.outcomes):
            bid, ask = _quotes_for(c, i, quotes_by_token)
            tok = c.token_ids[i] if i < len(c.token_ids) else None
            lines.append(f"    outcome_index={i} \"{outcome}\": bid {_fmt_px(bid)} ask {_fmt_px(ask)}"
                         f" | tape: {_freshness_line(tok, freshness_by_token)}")
    lines += [
        "",
        "RULES",
        f"- material=true ONLY if the item is NEW information that should move the chosen market's "
        f"probability by at least {MATERIAL_POINTS} points from the quotes shown. Old news, rumours "
        "already reflected in the price, vague commentary, or an item that fits no candidate -> "
        "material=false with market_id=null.",
        "- outcome_index is the outcome to BUY: the one the item makes MORE likely. direction is "
        "\"yes\" for that outcome; answer \"no\" only if you name the outcome the item makes LESS "
        "likely, and then the other outcome is bought. market_id and outcome_index must come from "
        "the list above.",
        "- implied_prob: your probability (0..1) that the chosen outcome resolves YES after this item. "
        "confidence: 0..1 in your own call. already_priced: true if the quotes already reflect the item.",
        "- Do not use tools or search. Answer with ONLY this JSON object, no prose, no code fences:",
        '{"material": true|false, "market_id": "<id>"|null, "outcome_index": <int>|null, '
        '"direction": "yes"|"no"|null, "implied_prob": <0..1>|null, "confidence": <0..1>, '
        '"why": "<one sentence>", "already_priced": true|false}',
    ]
    return "\n".join(lines)


def parse_judgement_text(text: str | None) -> dict | None:
    """The model's reply as a dict: strips code fences, then the first {...}."""
    if not text or not isinstance(text, str):
        return None
    cleaned = _FENCE.sub("", text).strip()
    for attempt in (cleaned,):
        try:
            data = json.loads(attempt)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(cleaned[start:i + 1])
                        if isinstance(data, dict):
                            return data
                    except json.JSONDecodeError:
                        pass
                    break
        start = cleaned.find("{", start + 1)
    return None


def _as_bool(v) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().lower() in ("true", "false"):
        return v.strip().lower() == "true"
    return None


def _as_unit(v, *, allow_none: bool) -> tuple[bool, float | None]:
    if v is None:
        return allow_none, None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False, None
    if f != f or f < 0.0 or f > 1.0:
        return False, None
    return True, f


def validate_judgement(data: Mapping[str, Any], candidates: Iterable) -> dict | None:
    """DESIGN.md's schema, or None. A non-material answer needs only a sane
    confidence; a material one must name a candidate we offered and one of its
    outcomes, with a direction."""
    candidates = list(candidates)
    by_id = {str(c.market_id): c for c in candidates}
    material = _as_bool(data.get("material"))
    if material is None:
        return None
    ok, confidence = _as_unit(data.get("confidence"), allow_none=False)
    if not ok:
        return None
    already = _as_bool(data.get("already_priced"))
    if already is None:
        already = False
    why = data.get("why")
    why = "" if why is None else str(why).strip()[:500]

    market_id = data.get("market_id")
    market_id = None if market_id in (None, "", "null") else str(market_id)
    outcome_index = data.get("outcome_index")
    direction = data.get("direction")
    direction = None if direction in (None, "", "null") else str(direction).strip().lower()
    ok, implied = _as_unit(data.get("implied_prob"), allow_none=True)
    if not ok:
        return None

    if market_id is not None and market_id not in by_id:
        # An answer that names a list position instead of the id ("1" for the
        # first market) is mapped when it is in range and no real id.
        if market_id.isdigit() and 1 <= int(market_id) <= len(candidates):
            market_id = str(candidates[int(market_id) - 1].market_id)
        else:
            return None
    if outcome_index is not None:
        if isinstance(outcome_index, bool) or not isinstance(outcome_index, (int, float, str)):
            return None
        try:
            outcome_index = int(outcome_index)
        except (TypeError, ValueError):
            return None
        if market_id is None or not (0 <= outcome_index < len(by_id[market_id].outcomes)):
            return None
    if direction is not None and direction not in ("yes", "no"):
        return None
    if material and (market_id is None or outcome_index is None or direction is None):
        return None
    # "This outcome, direction no" means buy the other side. The runner buys
    # outcome_index as given, so a "no" is turned into the complement here:
    # the backtest of 2026-10-25 bought YES on "Eby next Premier" from a
    # "Conservatives win a landslide" flash with implied_prob 0.02.
    if direction == "no" and outcome_index is not None and market_id is not None:
        outs = by_id[market_id].outcomes
        if len(outs) == 2:
            outcome_index = 1 - outcome_index
            direction = "yes"
            if implied is not None:
                implied = round(1.0 - implied, 4)
        elif material:
            return None    # no single complement to buy
    return {
        "material": material, "market_id": market_id, "outcome_index": outcome_index,
        "direction": direction, "implied_prob": implied, "confidence": confidence,
        "why": why, "already_priced": already,
    }


_rate_limit_logged_at: float | None = None


def judge(item, candidates: Iterable, freshness_by_token: Mapping[str, Any] | None, *,
          budget, model: str, runner=None, timeout_s: int = 60,
          quotes_by_token: Mapping[str, Any] | None = None,
          now: float | None = None) -> Judgement | None:
    """One judgement, or None (no candidates, budget spent, limited, unusable
    reply). Never raises."""
    global _rate_limit_logged_at
    try:
        cands = list(candidates or ())
        item_id = getattr(item, "id", None) or getattr(item, "title", "")[:60]
        if not cands:
            logger.debug("[news-judge] %s: no candidates — not judged", item_id)
            return None
        prompt = build_prompt(item, cands, freshness_by_token, quotes_by_token=quotes_by_token)
        if not budget.take():
            logger.info("[news-judge] budget exhausted (%d/%d today) — %s skipped:budget",
                        budget.count_today(), budget.limit, item_id)
            return None
        t0 = time.monotonic()
        res = run_claude(prompt, model=model, timeout_s=timeout_s, runner=runner, tag="news-judge")
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        if res is RATE_LIMITED:
            now_ts = time.time() if now is None else float(now)
            if _rate_limit_logged_at is None or now_ts - _rate_limit_logged_at >= RATE_LIMIT_LOG_EVERY_S:
                _rate_limit_logged_at = now_ts
                logger.warning("[news-judge] claude is rate-limited — items go unjudged "
                               "(next notice in an hour)")
            return None
        if not isinstance(res, dict):
            logger.warning("[news-judge] %s: no envelope from claude", item_id)
            return None
        data = parse_judgement_text(res.get("result"))
        if data is None:
            logger.warning("[news-judge] %s: reply was not JSON: %s", item_id,
                           str(res.get("result"))[:200])
            return None
        valid = validate_judgement(data, cands)
        if valid is None:
            logger.warning("[news-judge] %s: reply failed schema/candidate check: %s", item_id,
                           json.dumps(data)[:300])
            return None
        llm_ms = res.get("duration_ms")
        try:
            llm_ms = int(llm_ms) if llm_ms is not None else elapsed_ms
        except (TypeError, ValueError):
            llm_ms = elapsed_ms
        return Judgement(**valid, llm_ms=llm_ms, model=model, prompt_chars=len(prompt))
    except Exception as e:  # noqa: BLE001 - the judge never takes the poller down
        logger.exception("[news-judge] unexpected failure: %r", e)
        return None
