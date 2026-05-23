"""RapidAPI 'Pinnacle Odds' tennis provider — REST ``?since=`` delta poller.

This wraps the third-party RapidAPI listing at host
``pinnacle-odds.p.rapidapi.com`` (the "Pinnacle Odds" API by tipsters). It is
*not* an official Pinnacle product, so every wire detail below is an
ASSUMPTION to be confirmed at signup against the live RapidAPI docs/playground
(rewrite §11). Each assumption is flagged inline with ``# ASSUMPTION:`` and we
parse defensively (``.get`` chains, type coercion, None-returns) so that a
schema surprise degrades to "no odds this round" instead of a crash.

Architecture:
  * One-time ``/sports`` lookup resolves the Tennis sport id (never hardcoded).
  * ``/markets?sport_id=..&event_type={prematch|live}&since=<unix>`` returns
    only events that changed after ``since``; the response carries a ``last``
    high-watermark we feed back as the next ``since`` to get pure deltas.
  * ``fetch_tennis_odds`` does a full snapshot (since=0, both event_types).
  * ``stream_price_changes`` polls the delta endpoint at ``poll_interval_ms``
    cadence and emits one PriceChange per side whose decimal odds moved.

Tennis only — cricket / other sports are intentionally not implemented here.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator

import requests

from src.config import CONFIG
from src.odds.base import OddsProvider, synthetic_event_id
from src.odds.models import MatchOdds, PriceChange

logger = logging.getLogger("odds.pinnacle_rapidapi")

# ASSUMPTION: the RapidAPI "Pinnacle Odds" kit lives under /kit/v1/ (§11).
_API_BASE_PATH = "/kit/v1"

# Event types we poll. ASSUMPTION: the API distinguishes pre-match vs in-play
# books via an ``event_type`` query param taking these literal values (§11).
_EVENT_TYPES = ("prematch", "live")

# 429 backoff schedule (seconds), capped. Reset to the first step on success.
_BACKOFF_SCHEDULE = (1, 2, 4, 8, 16)

# COST NOTE (§11 PR surface): RapidAPI's cheaper Pinnacle-Odds tiers are often
# quota-capped (e.g. a few thousand calls/month) rather than rate-capped, which
# at a ~1 rps stream (2 event_types × 1/sec ≈ 2 rps → ~5M calls/month) blows
# past anything under ~50 SGD. If the chosen tier cannot sustain ≥1 rps within
# budget we must raise poll_interval_ms (or drop the 'live' poll) — flagged
# here rather than silently picking a cadence. Confirm tier limits at signup.


class PinnacleRapidApiProvider(OddsProvider):
    """Pinnacle-via-RapidAPI tennis odds provider (REST ``?since=`` poller)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        host: str | None = None,
        poll_interval_ms: float | None = None,
        session: requests.Session | None = None,
    ):
        self._api_key = api_key if api_key is not None else CONFIG.pinnacle_rapidapi_key
        self._host = host if host is not None else CONFIG.pinnacle_rapidapi_host
        self._poll_interval_ms = (
            poll_interval_ms
            if poll_interval_ms is not None
            else CONFIG.pinnacle_poll_interval_ms
        )
        self._session = session if session is not None else requests.Session()

        # Most-recent both-sides snapshot, keyed by native event_id (for stream)
        # and synthetic id (for full-snapshot fetch). get_match_odds reads this.
        self._stream_snapshot: dict[str, MatchOdds] = {}
        # Resolved Tennis sport id from /sports (never hardcoded).
        self._sport_id: int | None = None
        # Cached /leagues payload (optional tour scoping).
        self._leagues: dict | None = None
        # Per-event_type ``since`` high-watermark advanced from each response.
        self._last_since: dict[str, int] = {}

    @property
    def name(self) -> str:
        return "pinnacle"

    # ------------------------------------------------------------------ #
    # HTTP layer
    # ------------------------------------------------------------------ #

    def _headers(self) -> dict[str, str]:
        # ASSUMPTION: header names per RapidAPI docs (§11).
        return {
            "X-RapidAPI-Key": self._api_key,
            "X-RapidAPI-Host": self._host,
        }

    def _url(self, path: str) -> str:
        return f"https://{self._host}{_API_BASE_PATH}/{path.lstrip('/')}"

    def _get_json(self, path: str, params: dict | None = None) -> dict | list | None:
        """GET ``path`` and return parsed JSON, with 429 backoff.

        Retries on HTTP 429 using ``_BACKOFF_SCHEDULE`` (1→2→4→8→16s, capped),
        resetting to the first step on the next success. Any other error (or
        exhausted retries) logs a warning and returns None so callers can
        degrade to an empty result rather than crashing.
        """
        url = self._url(path)
        attempt = 0
        while True:
            try:
                resp = self._session.get(
                    url, params=params, headers=self._headers(), timeout=15
                )
            except Exception as exc:  # noqa: BLE001 — network hiccup, don't crash poller
                logger.warning("%s: GET %s failed: %s", self.name, path, exc)
                return None

            status = getattr(resp, "status_code", 200)
            if status == 429:
                delay = _BACKOFF_SCHEDULE[min(attempt, len(_BACKOFF_SCHEDULE) - 1)]
                logger.warning(
                    "%s: 429 on %s — backing off %ss (attempt %d)",
                    self.name,
                    path,
                    delay,
                    attempt + 1,
                )
                attempt += 1
                if attempt > len(_BACKOFF_SCHEDULE):
                    logger.warning("%s: giving up on %s after 429 retries", self.name, path)
                    return None
                time.sleep(delay)
                continue
            if status != 200:
                logger.warning("%s: GET %s returned HTTP %s", self.name, path, status)
                return None

            try:
                return resp.json()
            except Exception as exc:  # noqa: BLE001 — bad/empty body
                logger.warning("%s: bad JSON from %s: %s", self.name, path, exc)
                return None

    # ------------------------------------------------------------------ #
    # Metadata endpoints
    # ------------------------------------------------------------------ #

    def fetch_sport_id(self) -> int | None:
        """Resolve and cache the Tennis sport id from ``/sports``.

        Cached after the first successful resolve, so subsequent calls return
        the memoized id without re-hitting the API.
        """
        if self._sport_id is not None:
            return self._sport_id

        # ASSUMPTION: GET /sports → [{"id": 1, "name": "Tennis"}, ...] (§11).
        data = self._get_json("sports")
        if data is None:
            logger.warning("%s: /sports fetch failed", self.name)
            return None

        # Defensive: accept a bare list or a {"sports": [...]} envelope.
        sports = data if isinstance(data, list) else data.get("sports", []) if isinstance(data, dict) else []
        for sport in sports:
            if not isinstance(sport, dict):
                continue
            name = str(sport.get("name", ""))
            if name.strip().lower() == "tennis":
                sid = sport.get("id")
                try:
                    self._sport_id = int(sid)
                except (TypeError, ValueError):
                    logger.warning("%s: Tennis sport id not an int: %r", self.name, sid)
                    return None
                return self._sport_id

        logger.warning("%s: 'Tennis' not found in /sports response", self.name)
        return None

    def fetch_leagues(self) -> dict | None:
        """Fetch and cache ``/leagues`` for the resolved Tennis sport (optional)."""
        if self._leagues is not None:
            return self._leagues
        sport_id = self.fetch_sport_id()
        if sport_id is None:
            return None
        # ASSUMPTION: GET /leagues?sport_id=.. → {"leagues": [{"id","name"}]} (§11).
        data = self._get_json("leagues", params={"sport_id": sport_id})
        if isinstance(data, dict):
            self._leagues = data
            return data
        return None

    # ------------------------------------------------------------------ #
    # Parsing
    # ------------------------------------------------------------------ #

    @staticmethod
    def _infer_tour(name: str | None) -> str:
        """Map a league name to a tour tag. WTA checked before ATP because
        'WTA ...' strings never contain 'ATP', but the reverse ordering is a
        safe habit when adding women's-challenger style names later.
        """
        n = (name or "").upper()
        if "WTA" in n:
            return "WTA"
        if "ATP" in n:
            return "ATP"
        if "CHALLENGER" in n:
            return "Challenger"
        if "ITF" in n:
            return "ITF"
        return ""

    def _parse_market_event(self, ev: dict) -> MatchOdds | None:
        """Build a MatchOdds from one /markets event, or None if no money_line.

        ASSUMPTION (§11): event shape is
            {"event_id":.., "home":"A", "away":"B", "league_name":"ATP ..",
             "starts":"<iso>", "last":<unix>,
             "periods": {"num_0": {"money_line": {"home":1.85,"away":2.05}}}}
        ``num_0`` is the full-match period; money_line is two-way decimal odds.
        """
        if not isinstance(ev, dict):
            return None

        periods = ev.get("periods")
        if not isinstance(periods, dict):
            return None
        num0 = periods.get("num_0")
        if not isinstance(num0, dict):
            return None
        money_line = num0.get("money_line")
        if not isinstance(money_line, dict):
            return None

        odds_a = money_line.get("home")
        odds_b = money_line.get("away")
        try:
            odds_a = float(odds_a)
            odds_b = float(odds_b)
        except (TypeError, ValueError):
            return None
        if odds_a <= 0 or odds_b <= 0:
            return None

        player_a = str(ev.get("home", "")).strip()
        player_b = str(ev.get("away", "")).strip()
        if not player_a or not player_b:
            return None

        league_name = ev.get("league_name", "")
        tour = self._infer_tour(league_name)

        match_time = self._parse_starts(ev.get("starts"))

        return MatchOdds.from_decimal_odds(
            source=self.name,
            tournament=str(league_name or ""),
            tour=tour,
            player_a=player_a,
            player_b=player_b,
            odds_a=odds_a,
            odds_b=odds_b,
            match_time=match_time,
        )

    @staticmethod
    def _parse_starts(starts):
        """Best-effort parse of the event start time. ASSUMPTION: ISO-8601
        string in ``starts`` (§11). Returns a datetime or None — never raises.
        """
        if not starts:
            return None
        from datetime import datetime

        if isinstance(starts, (int, float)):
            try:
                return datetime.utcfromtimestamp(float(starts))
            except (OverflowError, OSError, ValueError):
                return None
        try:
            s = str(starts).replace("Z", "+00:00")
            return datetime.fromisoformat(s)
        except ValueError:
            return None

    # ------------------------------------------------------------------ #
    # Snapshot fetch
    # ------------------------------------------------------------------ #

    def fetch_tennis_odds(self, tours: list[str] | None = None) -> list[MatchOdds]:
        """Full both-event-type snapshot of tennis match odds.

        ``since=0`` asks for everything (not a delta). Parses, filters by tour
        (default ATP+WTA), seeds ``_stream_snapshot`` keyed by synthetic id,
        and returns the list. On any error → warns and returns []."""
        wanted = [t.upper() for t in (tours if tours is not None else ["ATP", "WTA"])]

        sport_id = self.fetch_sport_id()
        if sport_id is None:
            logger.warning("%s: cannot fetch odds — no Tennis sport id", self.name)
            return []

        results: list[MatchOdds] = []
        try:
            for event_type in _EVENT_TYPES:
                data = self._get_json(
                    "markets",
                    params={"sport_id": sport_id, "event_type": event_type, "since": 0},
                )
                if not isinstance(data, dict):
                    continue
                events = data.get("events")
                if not isinstance(events, list):
                    continue
                for ev in events:
                    mo = self._parse_market_event(ev)
                    if mo is None:
                        continue
                    if wanted and mo.tour.upper() not in wanted:
                        continue
                    results.append(mo)
                    self._stream_snapshot[synthetic_event_id(mo)] = mo
        except Exception as exc:  # noqa: BLE001 — degrade to empty, never crash scanner
            logger.warning("%s: fetch_tennis_odds failed: %s", self.name, exc)
            return []

        return results

    # ------------------------------------------------------------------ #
    # Streaming delta poller
    # ------------------------------------------------------------------ #

    async def stream_price_changes(
        self, sports: list[str]
    ) -> AsyncIterator[PriceChange]:
        """Poll the ``?since=`` delta endpoint and yield per-side price moves.

        Resolves the sport id once, then loops over both event_types each
        round, advancing ``_last_since[event_type]`` to the response ``last``
        high-watermark so the next round returns only newly-changed events.
        For each delta event we rebuild MatchOdds, store it in
        ``_stream_snapshot`` keyed by the NATIVE event_id, and emit a
        PriceChange for any side whose decimal odds differ from the prior
        stored value. Sleeps ``poll_interval_ms`` between rounds. Tennis only.
        """
        if "tennis" not in [s.lower() for s in sports]:
            logger.info(
                "%s: stream requested without tennis (%s) — idling", self.name, sports
            )

        loop = asyncio.get_event_loop()
        sport_id = await loop.run_in_executor(None, self.fetch_sport_id)
        if sport_id is None:
            logger.warning("%s: stream cannot start — no Tennis sport id", self.name)
            return

        # Last decimal price seen per (native_event_id, side) for delta diffing.
        last_prices: dict[tuple[str, str], float] = {}
        sleep_sec = max(0.0, self._poll_interval_ms / 1000.0)

        while True:
            for event_type in _EVENT_TYPES:
                since = self._last_since.get(event_type, 0)
                data = await loop.run_in_executor(
                    None,
                    self._get_json,
                    "markets",
                    {"sport_id": sport_id, "event_type": event_type, "since": since},
                )
                if not isinstance(data, dict):
                    continue

                events = data.get("events")
                if isinstance(events, list):
                    for ev in events:
                        native_id = ev.get("event_id") if isinstance(ev, dict) else None
                        mo = self._parse_market_event(ev)
                        if mo is None:
                            continue
                        key_id = str(native_id) if native_id is not None else synthetic_event_id(mo)
                        self._stream_snapshot[key_id] = mo

                        # ASSUMPTION: event ``last`` is a unix-second source ts (§11).
                        ev_last = ev.get("last") if isinstance(ev, dict) else None
                        try:
                            source_ts = float(ev_last)
                        except (TypeError, ValueError):
                            source_ts = time.time()
                        received_ts = time.time()

                        for side, price in (("home", mo.odds_a), ("away", mo.odds_b)):
                            pkey = (key_id, side)
                            old = last_prices.get(pkey)
                            if old is None or old != price:
                                yield PriceChange(
                                    provider=self.name,
                                    sport="tennis",
                                    event_id=key_id,
                                    market_key="match_winner",
                                    side=side,
                                    old_price=old,
                                    new_price=price,
                                    source_ts=source_ts,
                                    received_ts=received_ts,
                                )
                                last_prices[pkey] = price

                # Advance the high-watermark from the response ``last``.
                # ASSUMPTION: top-level ``last`` is the max source ts in the
                # batch and is the value to pass as the next ``since`` (§11).
                resp_last = data.get("last")
                if resp_last is not None:
                    try:
                        self._last_since[event_type] = int(resp_last)
                    except (TypeError, ValueError):
                        pass

            await asyncio.sleep(sleep_sec)
