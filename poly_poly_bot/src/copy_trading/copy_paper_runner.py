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
    load_watchlist_flagged_by,
    load_watchlist_wallets,
    make_detector,
    make_exit_detector,
    make_horizon_resolver,
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
        # entry guardrails (forwarded to the engine; see CopyPaperEngine)
        fill_gate_bps: Optional[int] = None,
        first_entry_only: bool = False,
        max_copies_per_wallet_day: Optional[int] = None,
        max_copies_per_category_day: Optional[int] = None,
        # --- bet-horizon routing (Strategy 1 near-term vs 4 long-horizon) ---
        # When set, every detected BUY is routed by its market's resolution date.
        # The near-term book passes ``max_horizon_days`` (skip far-future bets);
        # the long-horizon book passes ``min_horizon_days`` (take only them) plus a
        # ``mark_fetcher`` and ``strategy="4"``. Both None = horizon-blind (the
        # original copier). ``extra_watchlist_paths`` unions extra watchlists into
        # the watched set (the long-horizon book watches S1 ∪ S4 wallets).
        min_horizon_days: Optional[float] = None,
        max_horizon_days: Optional[float] = None,
        mark_fetcher: Optional[Callable[[str], Optional[float]]] = None,
        strategy: str = "1",
        extra_watchlist_paths: Optional[list[str]] = None,
        # injectable dependencies (defaults are the live ones)
        detector_factory: Optional[Callable[..., Callable]] = None,
        book_fetcher: Optional[Callable[[str], list[tuple[float, float]]]] = None,
        resolver: Optional[Callable[[str], Optional[int]]] = None,
        exit_detector_factory: Optional[Callable[[list[str], float], Callable]] = None,
        bid_fetcher: Optional[Callable[[str], list[tuple[float, float]]]] = None,
        horizon_resolver: Optional[Callable[[str], Optional[float]]] = None,
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
        self.fill_gate_bps = fill_gate_bps
        self.first_entry_only = first_entry_only
        self.max_copies_per_wallet_day = max_copies_per_wallet_day
        self.max_copies_per_category_day = max_copies_per_category_day
        self.min_horizon_days = min_horizon_days
        self.max_horizon_days = max_horizon_days
        self.strategy = strategy
        self._mark_fetcher = mark_fetcher
        self._extra_watchlist_paths = list(extra_watchlist_paths or [])
        self._detector_factory = detector_factory or make_detector
        self._book_fetcher = book_fetcher or fetch_asks
        self._resolver = resolver or resolve
        # exit-following: mirror the target's SELLs instead of only resolving
        self._exit_detector_factory = exit_detector_factory or make_exit_detector
        self._bid_fetcher = bid_fetcher or fetch_bids
        self._on_cycle = on_cycle
        # One horizon resolver, built once so its end-date cache persists across
        # cycles (one Gamma call per new market, not per cycle). Only needed when a
        # horizon band is set; otherwise routing is blind and we never look dates up.
        horizon_enabled = min_horizon_days is not None or max_horizon_days is not None
        self._horizon_resolver = horizon_resolver or (
            make_horizon_resolver() if horizon_enabled else None)

    def wallets(self) -> list[str]:
        if self._explicit_wallets:
            return self._explicit_wallets
        # Union the primary watchlist with any extras (the long-horizon book
        # watches both the copy watchlist and the long-horizon watchlist), keeping
        # first-seen order and de-duping case-insensitively.
        seen: set[str] = set()
        out: list[str] = []
        for path in [self.watchlist_path or ""] + self._extra_watchlist_paths:
            for w in load_watchlist_wallets(path):
                key = w.lower()
                if key not in seen:
                    seen.add(key)
                    out.append(w)
        return out

    def flagged_by_map(self) -> dict:
        """Wallet -> discovery theories, reloaded from the watchlist each cycle
        so newly-flagged wallets are attributed without a restart. Empty when
        running on an explicit wallet list (no watchlist file)."""
        if self._explicit_wallets or not self.watchlist_path:
            return {}
        out = load_watchlist_flagged_by(self.watchlist_path)
        for path in self._extra_watchlist_paths:
            for w, fb in load_watchlist_flagged_by(path).items():
                out.setdefault(w, fb)
        return out

    def run_once(self) -> CycleSummary:
        wallets = self.wallets()
        if not wallets:
            return CycleSummary()
        det_kwargs = {}
        if self._horizon_resolver is not None:
            det_kwargs["horizon_resolver"] = self._horizon_resolver
        detector = self._detector_factory(
            wallets, self.max_age_s, self.min_usd, self.flagged_by_map(), **det_kwargs
        )
        exit_detector = self._exit_detector_factory(wallets, self.max_age_s)
        engine = CopyPaperEngine(
            self.ledger, detector=detector, book_fetcher=self._book_fetcher,
            resolver=self._resolver, copy_pct=self.copy_pct,
            max_copy_usd=self.max_copy_usd, max_slippage_bps=self.max_slippage_bps,
            exit_detector=exit_detector, bid_fetcher=self._bid_fetcher,
            fill_gate_bps=self.fill_gate_bps, first_entry_only=self.first_entry_only,
            max_copies_per_wallet_day=self.max_copies_per_wallet_day,
            max_copies_per_category_day=self.max_copies_per_category_day,
            min_horizon_days=self.min_horizon_days,
            max_horizon_days=self.max_horizon_days,
            mark_fetcher=self._mark_fetcher, strategy=self.strategy,
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
