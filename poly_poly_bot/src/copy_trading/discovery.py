"""Continuous copyable-wallet discovery — pure core (state machine).

The bot runs a discovery funnel on a schedule (see ``discovery_runner``):
universe -> robust skill score -> lead-lag copyability. This module holds the
*pure* part: given the wallets evaluated this sweep and the previous state,
decide which wallets are on the paper watchlist now, which are newly qualified
(-> Telegram ping), and which decayed out (-> removed from paper).

Kept free of network/file/Telegram IO so it is fully unit-testable; the runner
injects the evaluated metrics and performs the side effects.

Qualification uses **hysteresis** so wallets hovering at the bar don't flap on
and off paper each sweep:
  * enter  : capture >= min_capture_cents AND tstat >= min_tstat
  * stay   : already on, capture >= drop_capture_cents AND tstat >= min_tstat
A capped top-N (by theory-agreement, then capture) becomes the live paper
watchlist, so "pinged" always equals "now on paper".
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DiscoveryConfig:
    # universe / scoring
    category: str = "ALL"
    universe: int = 850
    lookback_days: float = 120.0
    method: str = "robust"
    min_capital: float = 5000.0
    min_closed: int = 10
    skill_pool: int = 40
    # lead-lag copyability
    ll_lookback_days: float = 28.0
    delay_min: float = 15.0
    horizon_min: float = 240.0
    min_usd: float = 500.0
    min_ll_trades: int = 4
    # qualification bar (strict default) + hysteresis lower band
    min_capture_cents: float = 1.5
    min_tstat: float = 10.0
    drop_capture_cents: float = 1.0
    # entry-discipline gate: reject wallets whose buy $ is tail-dominated
    # (settlement-lag scooping near $1 — un-copyable). Lenient by default.
    max_tail_ratio: float = 0.5
    # independent strategy theories (1a..1j) that can qualify a wallet (OR'd with
    # the legacy capture+tstat gate). All ten run by default — discovery is
    # paper-only, so every theory earns or fails on measured paper PnL before any
    # manual promotion to real capital. 1a/1e need market-resolution data, which
    # the sweep now fetches on demand (see discovery_data.evaluate_sweep).
    enabled_theories: frozenset = frozenset(
        {"1a", "1b", "1c", "1d", "1e", "1f", "1g", "1h", "1i", "1j"})
    # paper watchlist size cap
    watchlist_cap: int = 25
    # auto-remove decayed wallets from paper (False = keep accumulating)
    auto_remove: bool = True
    # on-disk cache for market resolutions (1a/1e need how each market settled).
    # Resolved markets are immutable so they're cached permanently; None disables
    # the cache (every sweep re-fetches).
    res_cache_dir: str | None = None


@dataclass(frozen=True)
class Eval:
    """One wallet's evaluation from a sweep."""

    wallet: str
    roi: float = 0.0
    tstat: float = 0.0
    capture_cents: float = 0.0
    lead_cents: float = 0.0
    hit_rate: float = 0.0
    n: int = 0
    # entry-price discipline (F2) — share of buy $ at tail / in the copyable band
    tail_ratio: float = 0.0
    copyable_ratio: float = 1.0
    # PnL-curve shape (F1) — long-arc consistency, robust to the /activity cap
    curve_sharpe: float = 0.0
    curve_drawdown: float = 0.0
    net_pnl: float = 0.0
    # strategy theories that flagged this wallet + their reasons (why follow it)
    flagged_by: tuple = ()
    reason: str = ""


@dataclass
class DiscoveryState:
    """Persisted across sweeps (and restarts) so pings fire once."""

    on_watchlist: dict[str, dict] = field(default_factory=dict)  # wallet -> last metrics
    last_run: float = 0.0
    initialized: bool = False  # first completed sweep done (suppresses ping storm)

    @classmethod
    def from_json(cls, d: dict | None) -> "DiscoveryState":
        d = d or {}
        return cls(
            on_watchlist=dict(d.get("on_watchlist") or {}),
            last_run=float(d.get("last_run") or 0.0),
            initialized=bool(d.get("initialized") or False),
        )

    def to_json(self) -> dict:
        return {
            "on_watchlist": self.on_watchlist,
            "last_run": self.last_run,
            "initialized": self.initialized,
        }


@dataclass
class CycleResult:
    new_state: DiscoveryState
    watchlist: list[Eval]          # ordered (capture desc), capped — write to file
    newly_qualified: list[Eval]    # entered the watchlist this sweep — ping these
    removed: list[str]             # wallets dropped from paper this sweep
    first_init: bool               # this sweep is the initial seed (send one summary)


def _meta(e: Eval) -> dict:
    return {
        "roi": round(e.roi, 4), "tstat": round(e.tstat, 3),
        "capture_cents": round(e.capture_cents, 3),
        "lead_cents": round(e.lead_cents, 3),
        "hit_rate": round(e.hit_rate, 3), "n": e.n,
        "tail_ratio": round(e.tail_ratio, 3),
        "flagged_by": list(e.flagged_by), "reason": e.reason,
    }


def run_discovery_cycle(
    evaluated: dict[str, Eval], prev: DiscoveryState, cfg: DiscoveryConfig
) -> CycleResult:
    """Decide the new paper watchlist from this sweep's evaluations.

    ``evaluated`` must cover the freshly-scored skill pool *and* every wallet
    currently on the watchlist (the runner force-evaluates the latter so decay
    can be measured). Returns the capped, ordered watchlist plus the
    notify/remove deltas.
    """
    prev_on = set(prev.on_watchlist)

    qualified: dict[str, Eval] = {}
    for w, e in evaluated.items():
        if e.tail_ratio > cfg.max_tail_ratio:
            continue  # tail-dominated buy flow — un-copyable, skip regardless of theory
        flagged = bool(e.flagged_by)
        # legacy lead-lag gate (== theory 1c) OR any independent theory fired
        legacy = e.tstat >= cfg.min_tstat and e.capture_cents >= cfg.min_capture_cents
        entered = legacy or flagged
        # retain a prior wallet while it's still flagged, or (legacy path) while
        # its t-stat holds the floor and capture hasn't decayed out — the t-stat
        # floor applies even in keep mode, so a collapsed wallet is dropped.
        retained_legacy = (w in prev_on and e.tstat >= cfg.min_tstat
                           and _retain_on_decay(cfg, e))
        retained = (w in prev_on and flagged) or retained_legacy
        if entered or retained:
            qualified[w] = e

    # Rank by how many independent theories agree (flag count), then capture, and
    # keep the top-N. Capture is the lead-lag signal only theories 1c/1h produce,
    # so a capture-only sort would bury every wallet that a non-capture theory
    # (1a/1b/1d/1e/1g/1i/1j) flagged at capture 0 and starve it out of the cap.
    # Flag-count-first keeps each theory represented; capture breaks ties.
    ranked = sorted(qualified.values(),
                    key=lambda e: (len(e.flagged_by), e.capture_cents), reverse=True)
    watchlist = ranked[: cfg.watchlist_cap]
    on_now = {e.wallet for e in watchlist}

    newly_qualified = [e for e in watchlist if e.wallet not in prev_on]
    removed = sorted(prev_on - on_now)

    new_state = DiscoveryState(
        on_watchlist={e.wallet: _meta(e) for e in watchlist},
        last_run=prev.last_run,  # runner stamps the real time
        initialized=True,
    )
    return CycleResult(
        new_state=new_state,
        watchlist=watchlist,
        newly_qualified=newly_qualified,
        removed=removed,
        first_init=not prev.initialized,
    )


def _retain_on_decay(cfg: DiscoveryConfig, e: Eval) -> bool:
    """Should a wallet *already* on the list be kept this sweep?

    With auto_remove off it always stays (keeps accumulating paper PnL). With
    auto_remove on it stays only while capture holds above the lower drop band
    (hysteresis) — so a wallet sitting between drop and entry bands doesn't flap
    on and off every sweep."""
    if not cfg.auto_remove:
        return True
    return e.capture_cents >= cfg.drop_capture_cents


def watchlist_to_targets(watchlist: list[Eval], cfg: DiscoveryConfig) -> dict:
    """Serialize to the copy_watchlist.json shape the paper harness reads."""
    return {
        "category": cfg.category,
        "method": cfg.method,
        "source": "discovery",
        "targets": [
            {"rank": i + 1, "wallet": e.wallet, **_meta(e)}
            for i, e in enumerate(watchlist)
        ],
    }
