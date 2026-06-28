"""Resolve a market's outcome index to its human name (e.g. ``Yes``/``No`` or
``Lakers``), cached. Shared by the trade-signal / consensus / resolution alerts so
every message can say *exactly which side* is being traded.

Correctness rule (load-bearing): NEVER fabricate the name. Polymarket's outcome
order is not fixed — ``index 0`` is not always ``Yes`` — so a positional guess can
show the wrong side of a binary, worse than showing nothing. We map the index
through the market's ACTUAL ``outcomes`` array (Gamma ``/markets``) and return
``None`` when we can't resolve it; callers then show an honest ``Outcome #idx``
fallback rather than a guess.
"""

from __future__ import annotations

import json
import os
import time
from collections import OrderedDict
from typing import Callable, Optional

import requests

GAMMA = os.environ.get("GAMMA_API_URL", "https://gamma-api.polymarket.com")


def parse_outcomes(market: dict) -> list[str]:
    """The ``outcomes`` name array from a Gamma market dict (JSON-string or list).

    Returns [] when absent/malformed — callers treat that as "unresolved"."""
    raw = market.get("outcomes")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw]


def _gamma_fetch_outcomes(condition_id: str) -> Optional[list[str]]:
    """Live fetch of a market's outcome names via Gamma, or None if unresolved.

    Gamma's ``/markets`` returns only OPEN markets unless ``closed=true``, but a
    market we name can be either OPEN (a fresh consensus signal) or CLOSED (a
    resolution alert on a settled copy). So we try the default (open) variant
    first, then the ``closed=true`` variant — without this, every resolution-alert
    lookup hit a closed market, got zero rows, and fell back to "Outcome #idx".

    Returns: the names (non-empty list) when resolved; ``[]`` when Gamma DEFINITIVELY
    has no names for it (a real 200 response with no outcomes — a not-yet-indexed or
    broken market, safe to negative-cache); or ``None`` when every attempt failed
    (timeout / connection error / non-200) — a TRANSIENT failure the caller must NOT
    negative-cache, so it retries on the next lookup. Two attempts per variant at a
    tight 5s timeout absorb a blip; bounded (~20s worst case) for the synchronous
    copy-paper cycle thread."""
    if not condition_id:
        return None
    saw_200 = False  # did Gamma actually answer? distinguishes "no names" from "blip"
    for params in ({"condition_ids": condition_id},
                   {"condition_ids": condition_id, "closed": "true"}):
        for attempt in range(2):
            try:
                r = requests.get(f"{GAMMA}/markets", params=params, timeout=5)
                if r.status_code == 200:
                    saw_200 = True
                    j = r.json()
                    rows = j if isinstance(j, list) else (j or {}).get("data") or []
                    outs = parse_outcomes(rows[0]) if rows else []
                    if outs:
                        return outs
                    break          # 200 but no names for this variant -> next variant
            except requests.RequestException:
                pass
            # back off before the single retry on ANY non-success (connection error
            # OR an HTTP 429/5xx) — don't hammer a rate-limited/struggling Gamma.
            if attempt == 0:
                time.sleep(0.3)
    # a real 200 with no names -> [] (definitive, cacheable); all attempts failed
    # -> None (transient, don't cache, retry next lookup).
    return [] if saw_200 else None


class OutcomeNameResolver:
    """``(condition_id, outcome_index) -> name`` with a per-condition cache.

    ``fetcher(condition_id) -> list[str] | None`` is injected for tests; the
    default hits Gamma. A NON-EMPTY result is cached for the process. A DEFINITIVE
    empty result (``[]`` — Gamma answered but the market has no names yet / is
    broken) is NEGATIVE-cached for ``neg_ttl_s`` so it doesn't re-pay a blocking
    fetch every lookup, while still recovering once the TTL lapses. A TRANSIENT
    failure (``None`` — the fetch errored) is NOT cached at all, so the very next
    lookup retries (a brief Gamma blip mustn't suppress a name for the whole TTL).
    ``now`` is injected for tests."""

    def __init__(self, fetcher: Optional[Callable[[str], Optional[list[str]]]] = None,
                 max_cache: int = 5000, neg_ttl_s: float = 600.0,
                 now: Callable[[], float] = time.time):
        self._fetch = fetcher or _gamma_fetch_outcomes
        self._cache: "OrderedDict[str, list[str]]" = OrderedDict()
        self._neg_cache: "OrderedDict[str, float]" = OrderedDict()  # cid -> expiry ts
        self._max_cache = max_cache
        self._neg_ttl_s = neg_ttl_s
        self._now = now

    def outcomes(self, condition_id: str) -> list[str]:
        if not condition_id:
            return []
        if condition_id in self._cache:
            return self._cache[condition_id]
        exp = self._neg_cache.get(condition_id)
        if exp is not None:
            if self._now() < exp:             # recently unresolvable -> don't re-fetch
                return []
            del self._neg_cache[condition_id]  # TTL lapsed -> allow a retry
        got = self._fetch(condition_id)
        if got is None:                       # transient fetch failure -> DON'T cache
            return []                          # (retry on the very next lookup)
        if not got:                           # definitive [] -> negative-cache for TTL
            self._neg_cache[condition_id] = self._now() + self._neg_ttl_s
            if len(self._neg_cache) > self._max_cache:
                self._neg_cache.popitem(last=False)
            return []
        self._cache[condition_id] = got
        # DEFAULT_RESOLVER lives for the whole process; bound the cache so a
        # long-running bot can't grow it without limit (FIFO eviction).
        if len(self._cache) > self._max_cache:
            self._cache.popitem(last=False)
        return got

    def name(self, condition_id: str, outcome_index) -> Optional[str]:
        """The outcome's name, or None if it can't be resolved (out of range /
        unknown market). Never guesses."""
        try:
            idx = int(outcome_index)
        except (TypeError, ValueError):
            return None
        outs = self.outcomes(condition_id)
        if 0 <= idx < len(outs):
            return outs[idx]
        return None

    def label(self, condition_id, outcome_index) -> str:
        """A display label for the outcome: its real name, else an honest
        ``Outcome #idx`` (never a fabricated YES/NO)."""
        name = self.name(condition_id, outcome_index)
        if name:
            return name
        try:
            return f"Outcome #{int(outcome_index)}"
        except (TypeError, ValueError):
            return "Outcome #?"


# Shared default resolver so all alert formatters reuse one cache.
DEFAULT_RESOLVER = OutcomeNameResolver()
