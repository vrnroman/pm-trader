"""Abstract base class for odds providers."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from src.odds.models import MatchOdds, PriceChange

logger = logging.getLogger("odds.base")


def synthetic_event_id(odds: MatchOdds) -> str:
    """Stable id for a MatchOdds when the provider has no native event id.

    Mirrors the discovery cache's ``_match_key`` tuple so a synthesized
    stream and the PM↔sharp link agree on identity.
    """
    mt = odds.match_time.isoformat() if odds.match_time else ""
    return f"{odds.player_a}|{odds.player_b}|{mt}"


class OddsProvider(ABC):
    """Interface for fetching sharp sportsbook odds.

    Providers that only expose REST snapshots inherit the default
    :meth:`stream_price_changes` polling loop below, which diffs successive
    snapshots and synthesizes :class:`PriceChange` events. Real polling
    providers (BetsAPI, RapidAPI Pinnacle) override it with their fastest
    available delta path.
    """

    # Cadence for the synthesized-stream fallback, in seconds. Real providers
    # override the stream and ignore this.
    poll_interval_sec: float = 5.0

    @abstractmethod
    def fetch_tennis_odds(self, tours: list[str] | None = None) -> list[MatchOdds]:
        """Fetch current tennis match odds.

        Args:
            tours: Filter by tour, e.g. ["ATP", "WTA"]. None = all.

        Returns:
            List of MatchOdds for upcoming tennis matches.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        ...

    def get_match_odds(self, event_id: str) -> MatchOdds | None:
        """Return the most recently streamed MatchOdds for ``event_id``.

        The event-driven eval loop calls this when a PriceChange fires to get
        a both-sides, de-vigged snapshot for divergence math. The default
        reads the snapshot maintained by the default
        :meth:`stream_price_changes`; real providers maintain their own
        snapshot keyed on the provider-native id.
        """
        snap = getattr(self, "_stream_snapshot", None)
        if isinstance(snap, dict):
            return snap.get(event_id)
        return None

    async def stream_price_changes(
        self, sports: list[str]
    ) -> AsyncIterator[PriceChange]:
        """Default impl: poll ``fetch_tennis_odds`` on a loop and synthesise
        deltas. Overridden by real providers with their fastest delta path.

        Yields one PriceChange per changed decimal price (home + away of each
        match) relative to the previous snapshot, and keeps a per-provider
        ``_stream_snapshot`` so :meth:`get_match_odds` can answer lookups.
        Tennis-only: other sports are ignored by the default.
        """
        last_prices: dict[tuple[str, str], float] = {}
        snapshot: dict[str, MatchOdds] = {}
        self._stream_snapshot = snapshot  # type: ignore[attr-defined]
        loop = asyncio.get_event_loop()

        if "tennis" not in [s.lower() for s in sports]:
            logger.info(
                "%s: default stream has no tennis in %s — idling", self.name, sports
            )

        while True:
            try:
                odds = await loop.run_in_executor(None, self.fetch_tennis_odds)
            except Exception as exc:  # noqa: BLE001 — never let a poll kill the stream
                logger.warning("%s: snapshot poll failed: %s", self.name, exc)
                await asyncio.sleep(self.poll_interval_sec)
                continue

            now = time.time()
            for mo in odds:
                ev = synthetic_event_id(mo)
                snapshot[ev] = mo
                for side, price in (("home", mo.odds_a), ("away", mo.odds_b)):
                    key = (ev, side)
                    old = last_prices.get(key)
                    if old is None or old != price:
                        yield PriceChange(
                            provider=self.name,
                            sport="tennis",
                            event_id=ev,
                            market_key="match_winner",
                            side=side,
                            old_price=old,
                            new_price=price,
                            source_ts=now,
                            received_ts=now,
                        )
                        last_prices[key] = price

            await asyncio.sleep(self.poll_interval_sec)
