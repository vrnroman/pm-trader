"""Background-refreshed map of active Polymarket tennis markets.

The scan loop only needs to know which (condition_id → token_ids, …)
markets are "in play" right now and which sharp Smarkets fixture each
one maps to. Both pieces of data are essentially static over a 10-minute
window: market metadata doesn't change, and the Smarkets fixture list
churns slowly. Pulling them every 20s is wasted I/O and the source of
the stale-Gamma-price problem (we'd derive divergence off a 5-second-old
mid). This module hoists those fetches into a 10-minute background
refresh; the per-scan loop just reads the cache and queries live CLOB
books for prices.

Refresh cadence (default 600s) is configurable so the integration test
can drive it deterministically.

Threading: refresh() and the reader methods take the same RLock.
``start()`` does a synchronous initial hydrate so the first scan after
start sees populated data.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from src.odds.models import MatchOdds
from src.tennis.tennis_arb import (
    _match_player_to_odds,
    _validate_same_event,
    fetch_pm_tennis_markets_raw,
)

logger = logging.getLogger("strategy.tennis_arb.discovery")


_NO_LINK = "no_link"


def _match_key(odds: MatchOdds) -> tuple[str, str, str]:
    """Stable hash key for a Smarkets MatchOdds row.

    MatchOdds has no Smarkets market_id today, so we key on the tuple
    (player_a, player_b, match_time_iso). Stable across the 10-min
    refresh window even if a player changes seed or tournament name.
    """
    mt = odds.match_time.isoformat() if odds.match_time else ""
    return (odds.player_a, odds.player_b, mt)


class PMDiscoveryCache:
    """Polymarket tennis market discovery + Smarkets pre-warmed matching."""

    def __init__(
        self,
        smarkets_provider,
        tours: list[str],
        max_event_date_delta_days: float = 3.0,
        refresh_interval_s: float = 600.0,
        fetch_pm_fn: Callable[[float, float], list[dict]] | None = None,
    ):
        self._provider = smarkets_provider
        self._tours = tours
        self._max_delta = max_event_date_delta_days
        self._refresh_interval = refresh_interval_s
        # Injection seam for tests; production calls fetch_pm_tennis_markets_raw
        # with no vol/liq gate so the cache is the widest superset.
        self._fetch_pm = fetch_pm_fn or (
            lambda: fetch_pm_tennis_markets_raw(min_volume=0, min_liquidity=0)
        )
        self._lock = threading.RLock()
        self._entries: dict[str, dict] = {}
        self._last_refresh_at: float = 0.0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    def refresh(self) -> dict:
        """Hydrate the cache from Gamma + Smarkets. Returns telemetry."""
        t0 = time.monotonic()
        try:
            pm_markets = self._fetch_pm()
        except Exception as exc:
            logger.exception(f"Discovery cache: Gamma fetch failed: {exc}")
            pm_markets = []

        try:
            sharp_odds = self._provider.fetch_tennis_odds(tours=self._tours)
        except Exception as exc:
            logger.exception(f"Discovery cache: Smarkets fetch failed: {exc}")
            sharp_odds = []

        # Build a key → odds index once so per-PM rematching is O(N) over
        # sharp odds, not O(N²) over (PM, sharp) pairs.
        sharp_by_key: dict[tuple[str, str, str], MatchOdds] = {
            _match_key(o): o for o in sharp_odds
        }

        with self._lock:
            prev_entries = dict(self._entries)

        new_entries: dict[str, dict] = {}
        relinked_count = 0
        retried_nolink_count = 0

        for pm in pm_markets:
            cid = (pm.get("condition_id") or "").strip()
            if not cid:
                continue
            entry = dict(pm)
            prev = prev_entries.get(cid) or {}
            prev_link = prev.get("linked_match_key")

            # Carry over the link if it still resolves to a current sharp
            # fixture; otherwise force a rematch. Sharp fixtures sometimes
            # disappear (event removed, players changed) — if so, the link
            # would be a dangling pointer.
            link: tuple[str, str, str] | str | None = None
            if (
                isinstance(prev_link, tuple)
                and prev_link in sharp_by_key
            ):
                link = prev_link

            if link is None:
                if prev_link == _NO_LINK:
                    retried_nolink_count += 1
                # Try to match this PM market against the current sharp set.
                pm_player = (pm.get("player") or "").strip()
                if pm_player:
                    for odds in sharp_odds:
                        side, _ = _match_player_to_odds(
                            pm_player,
                            odds.player_a,
                            odds.player_b,
                            odds.implied_prob_a,
                            odds.implied_prob_b,
                        )
                        if side is None:
                            continue
                        ok, _reason = _validate_same_event(
                            pm,
                            odds.player_a,
                            odds.player_b,
                            odds.match_time,
                            self._max_delta,
                        )
                        if not ok:
                            continue
                        link = _match_key(odds)
                        break
                if link is None:
                    link = _NO_LINK
                elif prev_link == _NO_LINK:
                    relinked_count += 1

            entry["linked_match_key"] = link
            new_entries[cid] = entry

        elapsed = time.monotonic() - t0
        with self._lock:
            self._entries = new_entries
            self._last_refresh_at = time.time()

        linked = sum(
            1
            for e in new_entries.values()
            if e.get("linked_match_key") not in (None, _NO_LINK)
        )
        stats = {
            "pm_markets": len(pm_markets),
            "cache_size": len(new_entries),
            "linked": linked,
            "no_link": len(new_entries) - linked,
            "relinked_this_cycle": relinked_count,
            "retried_nolink": retried_nolink_count,
            "sharp_odds": len(sharp_odds),
            "elapsed_s": round(elapsed, 3),
        }
        logger.info(
            f"PM discovery cache: {stats['cache_size']} entries "
            f"({stats['linked']} linked, {stats['no_link']} no_link, "
            f"+{stats['relinked_this_cycle']} new links from "
            f"{stats['retried_nolink']} retries) in {stats['elapsed_s']}s"
        )
        return stats

    # ------------------------------------------------------------------
    # Thread lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Synchronous initial hydrate, then launch background refresh thread.

        Idempotent: calling start() twice is a no-op.
        """
        if self._thread is not None:
            return
        try:
            self.refresh()
        except Exception as exc:
            logger.exception(f"Initial discovery cache hydrate failed: {exc}")

        def _loop() -> None:
            while not self._stop_event.is_set():
                if self._stop_event.wait(self._refresh_interval):
                    return
                try:
                    self.refresh()
                except Exception as exc:
                    logger.exception(f"Discovery cache refresh failed: {exc}")

        self._thread = threading.Thread(
            target=_loop, daemon=True, name="pm-discovery"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------
    def get_entry(self, condition_id: str) -> Optional[dict]:
        with self._lock:
            e = self._entries.get(condition_id)
            return dict(e) if e is not None else None

    def snapshot(self) -> dict[str, dict]:
        """Full cache copy (entries are shallow copies)."""
        with self._lock:
            return {cid: dict(e) for cid, e in self._entries.items()}

    def active_set(
        self,
        *,
        now: Optional[datetime] = None,
        window_back_s: float = 7200.0,
        window_fwd_s: float = 1200.0,
        min_liquidity: float = 0.0,
        require_link: bool = True,
    ) -> list[dict]:
        """Filter cache to entries within the live-match window.

        Default window: gameStartTime ∈ [now - 2h, now + 20min]. Entries
        without a parseable gameStartTime are kept iff they have a sharp
        link (the link gates non-h2h markets, so a missing timestamp on a
        linked market is still safe to scan).
        """
        ref_now = now if now is not None else datetime.now(timezone.utc)
        out: list[dict] = []
        with self._lock:
            entries_view = list(self._entries.values())

        for e in entries_view:
            link = e.get("linked_match_key")
            if require_link and link in (None, _NO_LINK):
                continue
            if float(e.get("liquidity", 0.0) or 0.0) < min_liquidity:
                continue
            gst_raw = (e.get("pm_match_time") or "").strip()
            if not gst_raw:
                out.append(dict(e))
                continue
            try:
                iso = gst_raw.replace(" ", "T").replace("Z", "+00:00")
                gst = datetime.fromisoformat(iso)
                if gst.tzinfo is None:
                    gst = gst.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            delta_s = (gst - ref_now).total_seconds()
            if -window_back_s <= delta_s <= window_fwd_s:
                out.append(dict(e))
        return out

    def stats(self) -> dict:
        with self._lock:
            entries = self._entries
            last = self._last_refresh_at
            linked = sum(
                1
                for e in entries.values()
                if e.get("linked_match_key") not in (None, _NO_LINK)
            )
            return {
                "size": len(entries),
                "linked": linked,
                "no_link": len(entries) - linked,
                "last_refresh_at": last,
                "age_s": (time.time() - last) if last else None,
            }
