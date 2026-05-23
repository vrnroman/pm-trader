"""BetsAPI (b365api.com) tennis odds provider.

BetsAPI is a polling REST API — it has no push/websocket feed for odds, so we
synthesise a per-event stream by polling each active match's money-line at
``poll_hz_per_event`` Hz (default 1 Hz) and emitting a :class:`PriceChange`
whenever the book's ``last_update`` timestamp advances and the decimal odds
actually move.

Latency target: p95 (received_ts − source_ts) < 1500 ms. Because this is a
REST poll the floor is the poll cadence (1 s) plus one round-trip; the
``last_update`` field on each odds row lets us attribute the true book ts as
``source_ts`` so the divergence math isn't fooled by our own polling lag.

EVERY wire-format assumption below is flagged ``# ASSUMPTION:`` and parsed
defensively: a schema mismatch degrades to an empty result + a warning, never
a crash. These are to be confirmed against the live API on day 1 (§11).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import requests

from src.config import CONFIG
from src.odds.base import OddsProvider
from src.odds.models import MatchOdds, PriceChange

logger = logging.getLogger("odds.betsapi")

# ASSUMPTION: sport_id 13 = tennis; BetsAPI has no metadata endpoint to resolve
# this — surface in PR (§11).
_BETSAPI_TENNIS_SPORT_ID = 13

# How often the in-play/upcoming event list is re-discovered, in seconds.
_DISCOVERY_REFRESH_SEC = 30.0

# Fallback book to try when the primary book has no odds for an event.
_FALLBACK_BOOK = "bet365"

# Default tours we care about (upper-cased set membership).
_DEFAULT_TOURS = ["ATP", "WTA"]

# 429 exponential-backoff schedule (seconds), capped.
_BACKOFF_START = 1.0
_BACKOFF_CAP = 16.0

# Tick between stream iterations so the loop isn't a busy-spin.
_STREAM_TICK_SEC = 0.2


class BetsApiProvider(OddsProvider):
    """Polling tennis-odds provider over the BetsAPI v3 REST endpoints.

    The synthesised stream keys ``self._stream_snapshot`` by the *native*
    BetsAPI event id (not the synthetic id) so the eval loop's
    :meth:`get_match_odds` lookup — which fires off a PriceChange carrying the
    native id — resolves correctly.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str | None = None,
        poll_hz_per_event: float | None = None,
        primary_book: str | None = None,
        session: requests.Session | None = None,
        discovery_cache: Any = None,
        sport_id: int | None = None,
    ):
        self._token = token if token is not None else CONFIG.betsapi_token
        base = base_url if base_url is not None else CONFIG.betsapi_base_url
        self._base_url = base.rstrip("/")
        self._poll_hz = (
            poll_hz_per_event
            if poll_hz_per_event is not None
            else CONFIG.betsapi_poll_hz_per_event
        )
        self._primary_book = (
            primary_book if primary_book is not None else CONFIG.betsapi_primary_book
        )
        self._session = session if session is not None else requests.Session()
        # Duck-typed; may be None. Reserved for PM↔sharp linking parity.
        self._discovery_cache = discovery_cache
        self._sport_id = sport_id if sport_id is not None else _BETSAPI_TENNIS_SPORT_ID

        # Snapshot keyed by NATIVE BetsAPI event id (see class docstring).
        self._stream_snapshot: dict[str, MatchOdds] = {}
        # event_id -> last observed book last_update (unix seconds).
        self._last_update: dict[str, float] = {}
        # event_id -> last yielded decimal odds, per side, for delta detection.
        self._last_prices: dict[tuple[str, str], float] = {}
        # event_id -> next monotonic time the event is due for a poll.
        self._next_poll_at: dict[str, float] = {}

        # Discovery cache of {event_id: event_meta}.
        self._events: dict[str, dict] = {}
        self._events_refreshed_at: float = 0.0

    @property
    def name(self) -> str:
        return "betsapi"

    # ------------------------------------------------------------------ #
    # HTTP helpers
    # ------------------------------------------------------------------ #

    def _auth_params(self, extra: dict | None = None) -> dict:
        # ASSUMPTION: auth via ?token= query param — confirm BetsAPI docs day 1 (§11).
        params = {"token": self._token}
        if extra:
            params.update(extra)
        return params

    def _get_json(self, path: str, params: dict | None = None) -> Any:
        """GET ``path`` and return parsed JSON, with exponential backoff on 429.

        Backoff schedule: 1 → 2 → 4 → 8 → 16 s (capped), reset on success.
        Returns ``{}`` on any non-retryable failure (so callers degrade to an
        empty result rather than crashing).
        """
        url = f"{self._base_url}{path}"
        backoff = _BACKOFF_START
        while True:
            try:
                resp = self._session.get(url, params=self._auth_params(params), timeout=10)
            except Exception as exc:  # noqa: BLE001 — network errors degrade to empty
                logger.warning("betsapi: GET %s failed: %s", path, exc)
                return {}

            status = getattr(resp, "status_code", 200)
            if status == 429:
                logger.warning("betsapi: 429 on %s — backing off %.0fs", path, backoff)
                time.sleep(backoff)
                if backoff >= _BACKOFF_CAP:
                    # Give up after we've hit the cap once; degrade to empty.
                    logger.warning("betsapi: 429 backoff hit cap on %s — giving up", path)
                    return {}
                backoff = min(backoff * 2, _BACKOFF_CAP)
                continue
            if status != 200:
                logger.warning("betsapi: HTTP %s on %s", status, path)
                return {}
            try:
                return resp.json()
            except Exception as exc:  # noqa: BLE001
                logger.warning("betsapi: bad JSON on %s: %s", path, exc)
                return {}

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    def _discover_events(self, force: bool = False) -> dict[str, dict]:
        """Return ``{event_id: event_meta}`` for live + upcoming tennis events.

        Cached for ``_DISCOVERY_REFRESH_SEC``; pass ``force=True`` to bypass.
        """
        now = time.monotonic()
        if (
            not force
            and self._events
            and (now - self._events_refreshed_at) < _DISCOVERY_REFRESH_SEC
        ):
            return self._events

        events: dict[str, dict] = {}
        # ASSUMPTION: /v3/events/inplay & /v3/events/upcoming take
        # ?sport_id=&token= and return {"results": [ {...event...}, ... ]} — §11.
        for path in ("/v3/events/inplay", "/v3/events/upcoming"):
            data = self._get_json(path, {"sport_id": self._sport_id})
            results = data.get("results") if isinstance(data, dict) else None
            if not isinstance(results, list):
                continue
            for ev in results:
                if not isinstance(ev, dict):
                    continue
                ev_id = ev.get("id")
                if ev_id is None:
                    continue
                events[str(ev_id)] = ev

        self._events = events
        self._events_refreshed_at = now
        return events

    # ------------------------------------------------------------------ #
    # Odds
    # ------------------------------------------------------------------ #

    def _parse_odds_payload(self, data: Any) -> dict | None:
        """Extract the most-recent money-line row from an /events/odds payload.

        Returns ``{"home_odds": float, "away_odds": float, "last_update": float}``
        or None if no usable money-line row is present.
        """
        if not isinstance(data, dict):
            return None
        results = data.get("results")
        if not isinstance(results, dict):
            return None
        # ASSUMPTION: results.odds is {"<market_key>": [ {row}, ... ]}; the
        # match-winner money-line is the market whose rows carry home_od/away_od.
        # BetsAPI keys money-line markets like "13_1" for tennis — we don't
        # hardcode the key, we pick the first market whose rows parse as a
        # two-way price. Confirm exact key day 1 (§11).
        odds_block = results.get("odds")
        if not isinstance(odds_block, dict):
            return None

        best: dict | None = None
        for _market_key, rows in odds_block.items():
            if not isinstance(rows, list) or not rows:
                continue
            # Pick the most-recent row by last_update (fallback add_time).
            for row in rows:
                if not isinstance(row, dict):
                    continue
                home = _to_float(row.get("home_od"))
                away = _to_float(row.get("away_od"))
                if home is None or away is None or home <= 0 or away <= 0:
                    continue
                lu = _to_float(row.get("last_update")) or _to_float(row.get("add_time")) or 0.0
                if best is None or lu > best["last_update"]:
                    best = {"home_odds": home, "away_odds": away, "last_update": lu}
            if best is not None:
                # First market that yielded a valid two-way row wins.
                break
        return best

    def _fetch_event_odds(self, event_id: str) -> dict | None:
        """Fetch normalized money-line odds for one event.

        Tries the primary book first; on empty, retries once with bet365.
        Returns ``{"home_odds", "away_odds", "last_update", "book"}`` or None.
        """
        for book in (self._primary_book, _FALLBACK_BOOK):
            # ASSUMPTION: /v3/events/odds takes ?event_id=&source=&token= — §11.
            data = self._get_json(
                "/v3/events/odds", {"event_id": event_id, "source": book}
            )
            parsed = self._parse_odds_payload(data)
            if parsed is not None:
                parsed["book"] = book
                return parsed
            if book == _FALLBACK_BOOK:
                break
        return None

    # ------------------------------------------------------------------ #
    # Tour inference
    # ------------------------------------------------------------------ #

    @staticmethod
    def _infer_tour(event_meta: dict) -> str:
        """Infer ATP/WTA/Challenger/ITF/"" from the league name.

        WTA is checked before ATP so a "WTA ..." league with an "atp" substring
        elsewhere doesn't misclassify.
        """
        league = event_meta.get("league") if isinstance(event_meta, dict) else None
        name = ""
        if isinstance(league, dict):
            name = str(league.get("name") or "")
        elif isinstance(league, str):
            name = league
        upper = name.upper()
        if "WTA" in upper:
            return "WTA"
        if "ATP" in upper:
            return "ATP"
        if "CHALLENGER" in upper:
            return "Challenger"
        if "ITF" in upper:
            return "ITF"
        return ""

    @staticmethod
    def _event_players(event_meta: dict) -> tuple[str, str]:
        # ASSUMPTION: home/away are {"name": "..."} objects — §11.
        def _name(node: Any) -> str:
            if isinstance(node, dict):
                return str(node.get("name") or "")
            if isinstance(node, str):
                return node
            return ""

        return _name(event_meta.get("home")), _name(event_meta.get("away"))

    @staticmethod
    def _event_time(event_meta: dict) -> datetime | None:
        # ASSUMPTION: event "time" is a unix-seconds string/int — §11.
        ts = _to_float(event_meta.get("time"))
        if ts is None or ts <= 0:
            return None
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None

    def _build_match_odds(self, event_meta: dict, odds: dict) -> MatchOdds | None:
        player_a, player_b = self._event_players(event_meta)
        if not player_a or not player_b:
            return None
        tour = self._infer_tour(event_meta)
        league = event_meta.get("league") if isinstance(event_meta, dict) else None
        tournament = ""
        if isinstance(league, dict):
            tournament = str(league.get("name") or "")
        if not tournament:
            tournament = f"{tour} Tennis" if tour else "Tennis"
        return MatchOdds.from_decimal_odds(
            source=self.name,
            tournament=tournament,
            tour=tour,
            player_a=player_a,
            player_b=player_b,
            odds_a=odds["home_odds"],
            odds_b=odds["away_odds"],
            match_time=self._event_time(event_meta),
        )

    # ------------------------------------------------------------------ #
    # Snapshot fetch
    # ------------------------------------------------------------------ #

    def fetch_tennis_odds(self, tours: list[str] | None = None) -> list[MatchOdds]:
        """Discover events, fetch each money-line, build de-vigged MatchOdds.

        On any top-level failure, logs a warning and returns ``[]``.
        """
        try:
            target = {t.upper() for t in (tours or _DEFAULT_TOURS)}
            events = self._discover_events()
            out: list[MatchOdds] = []
            for ev_id, meta in events.items():
                if self._infer_tour(meta).upper() not in target:
                    continue
                odds = self._fetch_event_odds(ev_id)
                if odds is None:
                    continue
                mo = self._build_match_odds(meta, odds)
                if mo is None:
                    continue
                # Snapshot keyed by native id for the eval-loop lookup, and we
                # also expose the synthetic id (mirrors base default behavior).
                self._stream_snapshot[ev_id] = mo
                from src.odds.base import synthetic_event_id

                self._stream_snapshot[synthetic_event_id(mo)] = mo
                out.append(mo)
            return out
        except Exception as exc:  # noqa: BLE001 — never crash the scan
            logger.warning("betsapi: fetch_tennis_odds failed: %s", exc)
            return []

    # ------------------------------------------------------------------ #
    # Synthesised stream
    # ------------------------------------------------------------------ #

    async def stream_price_changes(
        self, sports: list[str]
    ) -> AsyncIterator[PriceChange]:
        """Synthesise a per-event price-change stream by polling each match.

        Each iteration: refresh discovery every 30 s; for every active tennis
        event whose per-event poll is due (cadence = 1/poll_hz seconds), fetch
        its money-line. If the book ``last_update`` advanced (or it's the first
        observation), rebuild the snapshot (keyed by native id) and yield one
        :class:`PriceChange` per side whose decimal odds changed.
        """
        loop = asyncio.get_event_loop()
        if "tennis" not in [s.lower() for s in sports]:
            logger.info("betsapi: stream has no tennis in %s — idling", sports)

        cadence = 1.0 / self._poll_hz if self._poll_hz > 0 else 1.0

        # Prime discovery once up front.
        await loop.run_in_executor(None, self._discover_events, True)

        while True:
            now_mono = time.monotonic()
            # (a) periodic discovery refresh
            if (now_mono - self._events_refreshed_at) >= _DISCOVERY_REFRESH_SEC:
                await loop.run_in_executor(None, self._discover_events, True)

            # (b) poll each due event
            for ev_id, meta in list(self._events.items()):
                if self._infer_tour(meta).upper() not in {t.upper() for t in _DEFAULT_TOURS}:
                    continue
                due_at = self._next_poll_at.get(ev_id, 0.0)
                if time.monotonic() < due_at:
                    continue
                self._next_poll_at[ev_id] = time.monotonic() + cadence

                odds = await loop.run_in_executor(None, self._fetch_event_odds, ev_id)
                if odds is None:
                    continue

                received_ts = time.time()
                source_ts = odds["last_update"]
                prev_lu = self._last_update.get(ev_id)
                first_obs = prev_lu is None
                if not first_obs and source_ts <= prev_lu:
                    # No fresh book update — skip.
                    continue
                self._last_update[ev_id] = source_ts

                mo = self._build_match_odds(meta, odds)
                if mo is None:
                    continue
                self._stream_snapshot[ev_id] = mo

                for side, price in (("home", mo.odds_a), ("away", mo.odds_b)):
                    key = (ev_id, side)
                    old = self._last_prices.get(key)
                    if old is None or old != price:
                        self._last_prices[key] = price
                        yield PriceChange(
                            provider=self.name,
                            sport="tennis",
                            event_id=ev_id,
                            market_key="match_winner",
                            side=side,
                            old_price=old,
                            new_price=price,
                            source_ts=source_ts,
                            received_ts=received_ts,
                        )

            await asyncio.sleep(_STREAM_TICK_SEC)


def _to_float(v: Any) -> float | None:
    """Best-effort parse of a wire value (str/int/float) into a float."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
