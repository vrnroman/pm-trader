"""In-bot daemon for continuous copyable-wallet discovery (Strategy 1b feeder).

Every ``cycle_interval_s`` it runs the discovery funnel (universe -> robust
skill -> lead-lag copyability), then:
  * writes the qualified wallets to ``watchlist_path`` (atomically) so the
    paper-copy harness picks them up on its next cycle — AUTO-PAPER;
  * Telegram-pings each *newly* qualified wallet so you can analyze it;
  * persists state so restarts don't re-ping and decayed wallets are dropped.

Places NO real orders and never touches the live ``.env`` tiers — promotion to
real capital stays a manual decision after you review the paper PnL.
"""

from __future__ import annotations

import ctypes
import gc
import json
import logging
import os
import threading
import time
from typing import Callable, Optional

from src.copy_trading.discovery import (
    DiscoveryConfig,
    DiscoveryState,
    Eval,
    run_discovery_cycle,
    watchlist_to_targets,
)
from src.copy_trading.discovery_data import evaluate_sweep

logger = logging.getLogger("poly_poly_bot")


def _release_freed_memory() -> None:
    """Hand the sweep's freed heap back to the OS.

    A sweep allocates large transient structures — the raw /activity per chunk
    plus lead-lag price series. Once ``evaluate_sweep`` returns those are
    unreferenced, but under glibc the freed blocks sit in per-thread arenas that
    ``free`` won't return without an explicit trim, so RSS would otherwise stay
    pinned at the sweep's high-water mark for the whole multi-day idle window
    until the next cycle. gc first (drop any cycles), then ``malloc_trim`` to
    actually release the arenas.
    """
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):  # non-glibc (e.g. macOS dev) / unavailable
        pass


def _atomic_write_json(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)  # atomic; the paper harness reads `path` concurrently


def _profile_url(wallet: str) -> str:
    return f"https://polymarket.com/profile/{wallet}"


def format_find(e: Eval) -> str:
    """Telegram body for a newly-qualified wallet."""
    return (
        "🔍 *New copyable wallet*\n"
        f"`{e.wallet}`\n"
        f"• capture *{e.capture_cents:+.2f}¢*/trade (hit {e.hit_rate:.0%}, n={e.n})\n"
        f"• ROI {e.roi:+.0%}  ·  t-stat {e.tstat:.1f}\n"
        f"• added to paper watchlist — measuring now\n"
        f"Analyze: {_profile_url(e.wallet)}"
    )


class DiscoveryRunner:
    def __init__(
        self,
        *,
        config: DiscoveryConfig,
        watchlist_path: str,
        state_path: str,
        cache_dir: Optional[str] = None,
        activity_ttl_s: float = 86400.0,
        cycle_interval_s: int = 21600,
        notify: Optional[Callable[[str], None]] = None,
        # injectable for tests
        evaluate: Callable[..., dict[str, Eval]] = evaluate_sweep,
        now: Callable[[], float] = time.time,
    ):
        self.cfg = config
        self.watchlist_path = watchlist_path
        self.state_path = state_path
        self.cache_dir = cache_dir
        self.activity_ttl_s = activity_ttl_s
        self.cycle_interval_s = cycle_interval_s
        self._notify = notify
        self._evaluate = evaluate
        self._now = now

    # ── state IO ──
    def _load_state(self) -> DiscoveryState:
        try:
            return DiscoveryState.from_json(json.load(open(self.state_path)))
        except (json.JSONDecodeError, OSError):
            return DiscoveryState()

    def _save_state(self, state: DiscoveryState) -> None:
        _atomic_write_json(self.state_path, state.to_json())

    def _send(self, text: str) -> None:
        if not self._notify:
            return
        try:
            self._notify(text)
        except Exception:  # pragma: no cover - notification must not break the loop
            logger.warning("[DISCOVERY] notification failed", exc_info=True)

    # ── one sweep ──
    def run_once(self, stop: Optional[threading.Event] = None) -> "CycleResultLike":
        prev = self._load_state()
        evaluated = self._evaluate(
            self.cfg, must_include=set(prev.on_watchlist),
            cache_dir=self.cache_dir, activity_ttl_s=self.activity_ttl_s, stop=stop,
        )
        if not evaluated:
            logger.info("[DISCOVERY] sweep produced no evaluations (stopped or empty)")
            return None
        result = run_discovery_cycle(evaluated, prev, self.cfg)

        # auto-paper: rewrite the watchlist the harness consumes
        _atomic_write_json(self.watchlist_path,
                           watchlist_to_targets(result.watchlist, self.cfg))

        # persist (stamp real time)
        result.new_state.last_run = self._now()
        self._save_state(result.new_state)

        # notify
        if result.first_init:
            top = ", ".join(f"{e.wallet[:8]}…({e.capture_cents:+.1f}¢)"
                            for e in result.watchlist[:5])
            self._send(
                f"🔍 *Discovery initialized* — {len(result.watchlist)} wallets on "
                f"the paper watchlist.\nTop: {top or '—'}"
            )
        else:
            for e in result.newly_qualified:
                self._send(format_find(e))

        logger.info(
            "[DISCOVERY] swept=%d qualified=%d new=%d removed=%d watchlist=%d",
            len(evaluated), len(result.watchlist), len(result.newly_qualified),
            len(result.removed), len(result.watchlist),
        )
        if result.removed:
            logger.info("[DISCOVERY] decayed off paper: %s", ", ".join(result.removed))
        return result

    def run_forever(self, shutdown_event: threading.Event) -> None:
        n = len(self._load_state().on_watchlist)
        logger.info(
            "[DISCOVERY] started (interval=%ds, bar: capture≥%.1f¢ & t-stat≥%.0f, "
            "cap=%d, auto_remove=%s, %d already on paper)",
            self.cycle_interval_s, self.cfg.min_capture_cents, self.cfg.min_tstat,
            self.cfg.watchlist_cap, self.cfg.auto_remove, n,
        )
        while not shutdown_event.is_set():
            try:
                self.run_once(stop=shutdown_event)
            except Exception:  # pragma: no cover - loop must survive any failure
                logger.warning("[DISCOVERY] sweep failed; continuing", exc_info=True)
            # Release the sweep's large transient heap before the multi-day
            # sleep, so RSS doesn't stay pinned at the peak the whole idle window.
            _release_freed_memory()
            shutdown_event.wait(self.cycle_interval_s)


# typing helper alias (run_once returns CycleResult | None)
CycleResultLike = object
