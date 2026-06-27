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
    """Live fetch of a market's outcome names via Gamma, or None on failure.

    No ``closed`` filter so it resolves names for OPEN markets too (a fresh signal
    is on a market that hasn't settled). Returns [] only when the field is genuinely
    absent; None on a network/HTTP miss so the resolver doesn't cache a transient
    failure as "unresolved"."""
    if not condition_id:
        return None
    for _ in range(3):
        try:
            r = requests.get(f"{GAMMA}/markets",
                             params={"condition_ids": condition_id}, timeout=15)
            if r.status_code == 200:
                j = r.json()
                rows = j if isinstance(j, list) else (j or {}).get("data") or []
                if not rows:
                    return []
                return parse_outcomes(rows[0])
        except requests.RequestException:
            pass
        time.sleep(0.3)
    return None


class OutcomeNameResolver:
    """``(condition_id, outcome_index) -> name`` with a per-condition cache.

    ``fetcher(condition_id) -> list[str] | None`` is injected for tests; the
    default hits Gamma. A successful fetch (including an empty list) is cached so
    repeated alerts on the same market cost one call; a None (transient failure)
    is NOT cached, so a later alert retries."""

    def __init__(self, fetcher: Optional[Callable[[str], Optional[list[str]]]] = None):
        self._fetch = fetcher or _gamma_fetch_outcomes
        self._cache: dict[str, list[str]] = {}

    def outcomes(self, condition_id: str) -> list[str]:
        if not condition_id:
            return []
        if condition_id in self._cache:
            return self._cache[condition_id]
        got = self._fetch(condition_id)
        if got is None:                       # transient miss -> don't cache
            return []
        self._cache[condition_id] = got
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
