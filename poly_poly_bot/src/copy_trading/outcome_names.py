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

    Returns the names only when non-empty; otherwise None — never an empty list —
    so a not-yet-indexed market (Gamma lag) isn't cached as permanently nameless
    and recovers on a later lookup. Bounded retries/timeout so a Gamma outage
    can't block the caller (the resolution alert runs in the copy-paper thread)."""
    if not condition_id:
        return None
    # One attempt per (open, closed) variant with a tight timeout: the resolution
    # alert resolves this synchronously in the copy-paper cycle thread, so a Gamma
    # outage must not stall the loop. An empty result isn't cached, so a transient
    # miss just shows "Outcome #idx" once and recovers on the next lookup.
    for params in ({"condition_ids": condition_id},
                   {"condition_ids": condition_id, "closed": "true"}):
        try:
            r = requests.get(f"{GAMMA}/markets", params=params, timeout=6)
            if r.status_code == 200:
                j = r.json()
                rows = j if isinstance(j, list) else (j or {}).get("data") or []
                outs = parse_outcomes(rows[0]) if rows else []
                if outs:
                    return outs
        except requests.RequestException:
            pass
    return None


class OutcomeNameResolver:
    """``(condition_id, outcome_index) -> name`` with a per-condition cache.

    ``fetcher(condition_id) -> list[str] | None`` is injected for tests; the
    default hits Gamma. Only a NON-EMPTY result is cached, so repeated alerts on
    the same market cost one call; a None (transient failure) OR an empty result
    (a market Gamma hasn't indexed yet) is NOT cached, so a later alert retries and
    the market's name recovers once Gamma returns it."""

    def __init__(self, fetcher: Optional[Callable[[str], Optional[list[str]]]] = None,
                 max_cache: int = 5000):
        self._fetch = fetcher or _gamma_fetch_outcomes
        self._cache: "OrderedDict[str, list[str]]" = OrderedDict()
        self._max_cache = max_cache

    def outcomes(self, condition_id: str) -> list[str]:
        if not condition_id:
            return []
        if condition_id in self._cache:
            return self._cache[condition_id]
        got = self._fetch(condition_id)
        if not got:                           # None (transient) OR [] (not indexed
            return []                          # yet) -> don't cache, retry next time
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
