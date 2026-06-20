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

from src.copy_trading.copy_replay import proven_negative, proven_positive


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
    # copy-replay selection gate — score each candidate on OUR copy action
    # (copy its copyable BUYs, hold to resolution) and DROP wallets whose
    # measured copy-and-hold edge is proven-negative, regardless of which theory
    # flagged them. This fixes the core leak: the legacy metric rewarded a
    # wallet's own closed-position ROI, but the live harness only copies the
    # 0.05-0.95 middle of the book and holds it — so favorite-buyers / scalpers
    # whose edge is in near-locks + early exits looked great yet lost when
    # copied. The watchlist now ranks copy-validated wallets first. Reversible:
    # set copy_replay_gate=False to fall back to the legacy theory-agreement rank.
    copy_replay_gate: bool = True
    min_copy_replay_n: int = 12        # resolved replayed copies before we judge a wallet
    min_copy_replay_roi: float = 0.0   # mean copy-and-hold ROI/$ bar to qualify / not be dropped
    fade_roi: float = -0.10            # at/below this (with enough n) -> FADE label (diagnostic)
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
    # Strategy 4 — long-horizon bet tracking. When enabled, the sweep classifies
    # each wallet by how early it bets before resolution (see horizon_profile) and
    # routes long-horizon-dominated wallets to a SEPARATE watchlist rather than
    # the copy funnel — they have no closed markets to score, so the copy/PnL
    # gates can't judge them. Tracked, not skipped. Off by default (zero added
    # API cost): the open-market end-date fetch only runs when this is on.
    s4_enabled: bool = False
    s4_long_horizon_days: float = 180.0
    s4_min_long_ratio: float = 0.5
    s4_min_dated_buys: int = 5
    long_horizon_cap: int = 25
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
    # copy-replay (copy this wallet's copyable BUYs, hold to resolution) — the
    # selection signal that measures the SAME action the live harness takes.
    # exit_roi/exit_n are the two-horizon diagnostic (round-trip / exit-follow).
    copy_roi: float = 0.0
    copy_tstat: float = 0.0
    copy_n: int = 0
    copy_hit: float = 0.0
    exit_roi: float = 0.0
    exit_n: int = 0
    fade: bool = False
    # strategy theories that flagged this wallet + their reasons (why follow it)
    flagged_by: tuple = ()
    reason: str = ""
    # bet-horizon classification (Strategy 1 = near-term, Strategy 4 = long-horizon
    # conviction bets that won't resolve for months). "1" by default so wallets
    # without horizon data flow through the existing funnel unchanged.
    strategy: str = "1"
    long_horizon_ratio: float = 0.0   # share of dated buy $ placed long before resolution
    horizon_days: float = 0.0         # USD-weighted mean days-before-resolution


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
    # Strategy 4 — long-horizon wallets tracked separately from the copy funnel.
    # A per-sweep snapshot (ranked by horizon), written to its own watchlist file;
    # empty unless DiscoveryConfig.s4_enabled and the sweep classified any wallet
    # as long-horizon. Kept out of `watchlist` so they never feed the paper copier.
    long_horizon: list[Eval] = field(default_factory=list)


def _meta(e: Eval) -> dict:
    return {
        "roi": round(e.roi, 4), "tstat": round(e.tstat, 3),
        "capture_cents": round(e.capture_cents, 3),
        "lead_cents": round(e.lead_cents, 3),
        "hit_rate": round(e.hit_rate, 3), "n": e.n,
        "tail_ratio": round(e.tail_ratio, 3),
        # copy-replay selection signal (+ two-horizon exit diagnostic + fade tag)
        "copy_roi": round(e.copy_roi, 4), "copy_tstat": round(e.copy_tstat, 3),
        "copy_n": e.copy_n, "copy_hit": round(e.copy_hit, 3),
        "exit_roi": round(e.exit_roi, 4), "exit_n": e.exit_n, "fade": e.fade,
        "flagged_by": list(e.flagged_by), "reason": e.reason,
        # bet-horizon classification (Strategy 1 near-term vs 4 long-horizon)
        "strategy": e.strategy,
        "long_horizon_ratio": round(e.long_horizon_ratio, 3),
        "horizon_days": round(e.horizon_days, 1),
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

    # Strategy 4: peel long-horizon wallets off BEFORE the copy funnel. They bet
    # on far-future events with no closed markets to score, so the copy/PnL gates
    # below can't judge them — we track them on their own clock instead of
    # dropping them or polluting the copy watchlist. Disabled (s4_enabled=False)
    # leaves every wallet in the near-term path, so behaviour is unchanged.
    long_horizon_evals: list[Eval] = []
    if cfg.s4_enabled:
        near_term = {}
        for w, e in evaluated.items():
            if e.strategy == "4":
                long_horizon_evals.append(e)
            else:
                near_term[w] = e
        evaluated = near_term
        long_horizon_evals.sort(
            key=lambda e: (e.long_horizon_ratio, e.horizon_days), reverse=True)
        long_horizon_evals = long_horizon_evals[: cfg.long_horizon_cap]

    qualified: dict[str, Eval] = {}
    for w, e in evaluated.items():
        if e.tail_ratio > cfg.max_tail_ratio:
            continue  # tail-dominated buy flow — un-copyable, skip regardless of theory
        # copy-replay gate: drop wallets PROVEN to lose under our actual copy
        # action — enough resolved replayed copies AND a mean copy-and-hold
        # ROI/$ below the bar — no matter which theory flagged them. Wallets with
        # too little replay data are NOT dropped (insufficient evidence); they
        # just rank below copy-validated ones in the cap.
        if cfg.copy_replay_gate and proven_negative(
                e.copy_n, e.copy_roi,
                min_n=cfg.min_copy_replay_n, min_roi=cfg.min_copy_replay_roi):
            continue
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

    # Rank copy-VALIDATED wallets first (proven positive copy-and-hold edge),
    # ordered by their measured copy ROI — selection now leads with the same
    # action the live harness takes. Ties and unproven wallets fall back to the
    # legacy order: theory-agreement (flag count), then capture. Flag-count
    # before capture keeps each non-capture theory (1a/1b/1d/1e/1g/1i/1j)
    # represented rather than buried by the lead-lag-only signal. When no wallet
    # has replay data this reduces exactly to the legacy (flag-count, capture)
    # ranking, so behaviour is unchanged until copy-replay data accrues.
    ranked = sorted(qualified.values(), key=lambda e: _rank_key(cfg, e), reverse=True)
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
        long_horizon=long_horizon_evals,
    )


def _copy_validated(cfg: DiscoveryConfig, e: Eval) -> bool:
    """A wallet with enough resolved replayed copies AND a positive measured
    copy-and-hold edge — i.e. it earns under the action we actually take."""
    return cfg.copy_replay_gate and proven_positive(
        e.copy_n, e.copy_roi,
        min_n=cfg.min_copy_replay_n, min_roi=cfg.min_copy_replay_roi)


def _rank_key(cfg: DiscoveryConfig, e: Eval):
    """Watchlist priority: copy-validated wallets first (by measured copy ROI),
    then the legacy theory-agreement / capture order. Reduces exactly to
    (flag-count, capture) when no replay data exists, so it is backward-safe."""
    proven = _copy_validated(cfg, e)
    return (1 if proven else 0,
            e.copy_roi if proven else 0.0,
            len(e.flagged_by),
            e.capture_cents)


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


def long_horizon_to_targets(long_horizon: list[Eval], cfg: DiscoveryConfig) -> dict:
    """Serialize the Strategy-4 long-horizon snapshot to its own watchlist file.

    Same row shape as ``watchlist_to_targets`` (so tooling can read either), but
    a distinct ``source`` so it's never confused with the copy watchlist the
    paper harness consumes — these wallets are tracked, not copied.
    """
    return {
        "category": cfg.category,
        "source": "discovery_long_horizon",
        "long_horizon_days": cfg.s4_long_horizon_days,
        "targets": [
            {"rank": i + 1, "wallet": e.wallet, **_meta(e)}
            for i, e in enumerate(long_horizon)
        ],
    }
