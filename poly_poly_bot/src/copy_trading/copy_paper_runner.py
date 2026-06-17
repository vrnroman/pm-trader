"""In-bot runner for the forward paper-copy harness (Strategy 1b).

Wraps `CopyPaperEngine` with watchlist loading and a cycle loop so `main.py`
can start it as a daemon thread. It reloads the watchlist each cycle (so
regenerating the watchlist file takes effect without a restart) and places NO
real orders — it only accumulates the paper ledger whose net-of-drag PnL gates
real capital.

Live data access (detection/books/resolution) is injected from
`copy_paper_live` by default but overridable for tests.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from src.copy_trading.copy_paper import CopyPaperEngine, CycleSummary, PaperCopyLedger
from src.copy_trading.copy_paper_live import (
    fetch_asks,
    fetch_bids,
    load_watchlist_wallets,
    make_detector,
    make_exit_detector,
    resolve,
)


class CopyPaperRunner:
    def __init__(
        self,
        *,
        ledger_path: str,
        watchlist_path: Optional[str] = None,
        wallets: Optional[list[str]] = None,
        max_copy_usd: float = 50.0,
        copy_pct: float = 1.0,
        max_slippage_bps: int = 200,
        max_age_s: float = 21600,
        min_usd: float = 500.0,
        cycle_interval_s: int = 120,
        # injectable dependencies (defaults are the live ones)
        detector_factory: Optional[Callable[[list[str], float, float], Callable]] = None,
        book_fetcher: Optional[Callable[[str], list[tuple[float, float]]]] = None,
        resolver: Optional[Callable[[str], Optional[int]]] = None,
        exit_detector_factory: Optional[Callable[[list[str], float], Callable]] = None,
        bid_fetcher: Optional[Callable[[str], list[tuple[float, float]]]] = None,
        on_cycle: Optional[Callable[[CycleSummary, "PaperCopyLedger"], None]] = None,
    ):
        self.ledger = PaperCopyLedger(ledger_path)
        self.watchlist_path = watchlist_path
        self._explicit_wallets = wallets
        self.max_copy_usd = max_copy_usd
        self.copy_pct = copy_pct
        self.max_slippage_bps = max_slippage_bps
        self.max_age_s = max_age_s
        self.min_usd = min_usd
        self.cycle_interval_s = cycle_interval_s
        self._detector_factory = detector_factory or make_detector
        self._book_fetcher = book_fetcher or fetch_asks
        self._resolver = resolver or resolve
        # exit-following: mirror the target's SELLs instead of only resolving
        self._exit_detector_factory = exit_detector_factory or make_exit_detector
        self._bid_fetcher = bid_fetcher or fetch_bids
        self._on_cycle = on_cycle

    def wallets(self) -> list[str]:
        if self._explicit_wallets:
            return self._explicit_wallets
        return load_watchlist_wallets(self.watchlist_path or "")

    def run_once(self) -> CycleSummary:
        wallets = self.wallets()
        if not wallets:
            return CycleSummary()
        detector = self._detector_factory(wallets, self.max_age_s, self.min_usd)
        exit_detector = self._exit_detector_factory(wallets, self.max_age_s)
        engine = CopyPaperEngine(
            self.ledger, detector=detector, book_fetcher=self._book_fetcher,
            resolver=self._resolver, copy_pct=self.copy_pct,
            max_copy_usd=self.max_copy_usd, max_slippage_bps=self.max_slippage_bps,
            exit_detector=exit_detector, bid_fetcher=self._bid_fetcher,
        )
        summary = engine.run_cycle()
        if self._on_cycle:
            self._on_cycle(summary, self.ledger)
        return summary

    def run_forever(self, shutdown_event: threading.Event) -> None:
        while not shutdown_event.is_set():
            try:
                self.run_once()
            except Exception:  # pragma: no cover - defensive; loop must survive
                pass
            shutdown_event.wait(self.cycle_interval_s)
