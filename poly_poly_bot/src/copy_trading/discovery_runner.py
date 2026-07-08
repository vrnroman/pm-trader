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
import html
import json
import logging
import os
import threading
import time
from typing import Callable, Optional

from types import SimpleNamespace

from src.copy_trading import governance
from src.copy_trading import promotion_state
from src.copy_trading.consensus import run_consensus_scan
from src.copy_trading.copy_replay import proven_positive
from src.copy_trading.discovery import (
    DiscoveryConfig,
    DiscoveryState,
    Eval,
    long_horizon_to_targets,
    run_discovery_cycle,
    watchlist_to_targets,
)
from src.copy_trading import gate_history
from src.copy_trading import gate_recheck_queue
from src.copy_trading import late_bet_queue
from src.copy_trading.discovery_data import evaluate_sweep, fetch_activity
from src.copy_trading.entry_profile import is_copyable_entry
from src.copy_trading.llm_review import (
    DEFAULT_MODEL, RATE_LIMITED, build_dossier, review_wallet)
from src.copy_trading.outcome_names import DEFAULT_RESOLVER
from src.copy_trading.theories import REGISTRY as THEORY_REGISTRY
from src.copy_trading.trader_scoring import classify_market

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


def _confidence_band(confidence: float) -> str:
    """Bucket a gate confidence for calibration slicing (high/medium/low)."""
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.6:
        return "medium"
    return "low"


def format_find(e: Eval, verdict=None) -> str:
    """Telegram body for a newly-qualified wallet (HTML parse mode; optional Claude verdict)."""
    lines = [
        "🔍 <b>New copyable wallet</b> — added to paper watchlist, measuring now",
        f"<code>{e.wallet}</code>",
    ]
    if e.flagged_by:
        lines.append(f"Flagged by <b>{', '.join(e.flagged_by)}</b>")
        if e.reason:
            lines.append(f"<i>{html.escape(e.reason)}</i>")
    lines.append(
        f"Edge: <b>{e.capture_cents:+.2f}¢</b>/trade · hit {e.hit_rate:.0%} · "
        f"ROI {e.roi:+.0%} · t-stat {e.tstat:.1f} (n={e.n}) · tail {e.tail_ratio:.0%}"
    )
    # Copy-replay = what copying this wallet (hold-to-resolution) actually earns —
    # the selection signal that matches the harness. exit ROI is the diagnostic.
    if e.copy_n:
        tag = " ⚠️FADE" if e.fade else (" ✅" if e.copy_roi > 0 else "")
        lines.append(
            f"Copy-replay: <b>{e.copy_roi:+.0%}</b>/$ hold-to-res "
            f"(hit {e.copy_hit:.0%}, n={e.copy_n}, t {e.copy_tstat:.1f}) · "
            f"exit {e.exit_roi:+.0%} (n={e.exit_n}){tag}"
        )
    if e.curve_sharpe or e.net_pnl:
        lines.append(f"Curve: sharpe {e.curve_sharpe:+.2f} · maxDD {e.curve_drawdown:.0%}")
    if verdict is not None:
        lines.append(
            f"🤖 Claude: <b>{verdict.verdict}</b> (insider {verdict.insider_likelihood}, "
            f"copyable {'yes' if verdict.copyable else 'no'}, conf {verdict.confidence:.0%})"
        )
        lines.append(f"<i>{html.escape(verdict.reasoning)}</i>")
    lines.append(f"👤 {_profile_url(e.wallet)}")
    return "\n".join(lines)


def _theory_brief(flagged_by) -> list[dict]:
    """``[{id, desc, needs_capture}]`` for the theories that qualified a wallet.

    Tells the gate WHY the wallet is here and which fields it should expect: a
    theory with ``needs_capture=False`` (1a/1b/1d/1e/1f/1g/1i/1j) never ran the
    lead-lag stage, so a missing ``copyability`` block is expected, not damning.
    """
    out: list[dict] = []
    for tid in flagged_by:
        th = THEORY_REGISTRY.get(tid)
        if th is not None:
            out.append({"id": tid, "desc": th.desc, "needs_capture": th.needs_capture})
        else:
            out.append({"id": tid})
    return out


def _dossier_from_eval(e: Eval, paper_record: Optional[dict] = None) -> dict:
    """Map a sweep Eval into the llm_review dossier shape.

    The lead-lag ``copyability`` block is included ONLY when it was actually
    measured (``e.n > 0``). When ``e.n == 0`` the wallet qualified via a
    non-lead-lag theory and has no lead-lag sample — passing ``evaluation=None``
    omits the block so the gate judges it on its qualifying theory + copy-replay
    + skill + curve, rather than reading a row of zeros as a disqualifying
    artifact. A *measured* wallet with negative capture (``e.n > 0``) keeps its
    block and stays fully skippable — the settlement-lag scoopers still get cut.
    ``paper_record`` (paper-proven re-entries only) adds the REALIZED forward
    paper record so the gate can weigh what actually happened when we copied.
    """
    return build_dossier(
        e.wallet,
        metrics=SimpleNamespace(roi=e.roi, tstat=e.tstat),
        evaluation=e if e.n > 0 else None,  # omit lead-lag block when unmeasured
        copy_replay=e,  # copy_roi/copy_n/copy_hit/exit_roi (self-omits when copy_n==0)
        qualifying_theories=_theory_brief(e.flagged_by),
        why_flagged=e.reason or None,
        entry=SimpleNamespace(mean_entry=None, tail_ratio=e.tail_ratio,
                              copyable_ratio=e.copyable_ratio),
        curve=SimpleNamespace(net_pnl=e.net_pnl, max_drawdown_frac=e.curve_drawdown,
                              up_ratio=None, sharpe=e.curve_sharpe),
        paper_record=paper_record,
    )


class DiscoveryRunner:
    def __init__(
        self,
        *,
        config: DiscoveryConfig,
        watchlist_path: str,
        state_path: str,
        long_horizon_watchlist_path: Optional[str] = None,
        cache_dir: Optional[str] = None,
        activity_ttl_s: float = 86400.0,
        cycle_interval_s: int = 21600,
        notify: Optional[Callable[[str], None]] = None,
        llm_review_enabled: bool = False,
        llm_review_top_n: int = 5,
        llm_model: str = DEFAULT_MODEL,
        holdout_frac: float = 0.0,
        holdout_max_per_sweep: int = 2,
        # Paper-evidence retention override (2026-07 starvation RCA): when a
        # ledger path is given, wallets whose REALIZED paper record clears the
        # floors are force-included in the sweep and qualify while swept —
        # retention was blind to paper results, so the best earners decayed off
        # mid-accrual. None disables the override entirely (legacy behaviour).
        paper_ledger_path: Optional[str] = None,
        paper_proven_min_n: int = 5,
        paper_proven_min_roi: float = 0.0,
        consensus_fired_path: Optional[str] = None,
        # injectable for tests
        evaluate: Callable[..., dict[str, Eval]] = evaluate_sweep,
        llm_review: Callable[..., object] = review_wallet,
        now: Callable[[], float] = time.time,
        rand: Callable[[], float] = None,
        consensus_fetch_buys: Optional[Callable[[str], list]] = None,
        consensus_funder_map: Optional[Callable[[list], dict]] = None,
        consensus_resolver=None,
    ):
        self.cfg = config
        self.watchlist_path = watchlist_path
        self.state_path = state_path
        self.long_horizon_watchlist_path = long_horizon_watchlist_path
        self.cache_dir = cache_dir
        self.activity_ttl_s = activity_ttl_s
        self.cycle_interval_s = cycle_interval_s
        self._notify = notify
        self.llm_review_enabled = llm_review_enabled
        self.llm_review_top_n = llm_review_top_n
        self.llm_model = llm_model
        self.holdout_frac = holdout_frac
        self.holdout_max_per_sweep = holdout_max_per_sweep
        self.paper_ledger_path = paper_ledger_path
        self.paper_proven_min_n = paper_proven_min_n
        self.paper_proven_min_roi = paper_proven_min_roi
        self._evaluate = evaluate
        self._llm_review = llm_review
        self._now = now
        if rand is None:
            import random
            rand = random.random
        self._rand = rand
        self.consensus_fired_path = consensus_fired_path or (
            (state_path + ".consensus.json") if state_path else None)
        # Append-only gate-decision log (sibling of the discovery state file), so
        # the accept/reject mix is queryable via /gate instead of log-trawled.
        self.gate_history_path = (
            os.path.join(os.path.dirname(state_path), "gate-history.jsonl")
            if state_path else None)
        # Restart-surviving queue of wallets whose gate check was deferred because
        # claude -p was spend/rate-limited (drained each sweep once the limit clears).
        self.gate_recheck_queue_path = (
            os.path.join(os.path.dirname(state_path), "gate-recheck-queue.json")
            if state_path else None)
        self._consensus_fetch_buys_fn = consensus_fetch_buys or self._live_consensus_buys
        self._consensus_funder_map_fn = consensus_funder_map or self._live_funder_map
        self._consensus_resolver = consensus_resolver or DEFAULT_RESOLVER

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

    def _late_bet_seeds(self) -> list[str]:
        """Resolve matured late-bet leads and return the validated-winner
        wallets to force-include in this sweep. Best-effort: any failure yields
        no seeds rather than aborting the sweep."""
        try:
            counts = late_bet_queue.process_resolutions(self._now())
            seeds = late_bet_queue.eval_seeds()
            if counts.get("won") or counts.get("lost") or counts.get("expired"):
                logger.info(
                    "[DISCOVERY] late-bet leads: won=%d lost=%d expired=%d → %d seed(s)",
                    counts.get("won", 0), counts.get("lost", 0),
                    counts.get("expired", 0), len(seeds),
                )
            return seeds
        except Exception:  # pragma: no cover - never break the sweep
            logger.warning("[DISCOVERY] late-bet seed processing failed", exc_info=True)
            return []

    def _paper_proven(self) -> dict[str, dict]:
        """Wallets with a positive REALIZED paper record (wallet(lower) -> stats),
        recomputed from the ledger every sweep — never sticky. Excludes wallets
        whose most recent gate decision was a real (non-holdout) skip made WITH
        this exact paper record: a rejected wallet accrues no new copies, so its
        frozen record would otherwise re-qualify it and burn a gate slot every
        sweep. New settled evidence (n_closed changed) re-opens the question."""
        if not self.paper_ledger_path:
            return {}
        proven = governance.paper_proven_wallets(
            self.paper_ledger_path, min_n=self.paper_proven_min_n,
            min_roi=self.paper_proven_min_roi)
        if not proven:
            return {}
        last_row: dict[str, dict] = {}
        for row in gate_history.load(self.gate_history_path):
            w = (row.get("wallet") or "").lower()
            if w:
                last_row[w] = row
        out: dict[str, dict] = {}
        for w, rec in proven.items():
            row = last_row.get(w)
            if (row is not None and row.get("verdict") == "skip"
                    and not row.get("admitted") and row.get("paper_proven")
                    and row.get("paper_n") == rec["n_closed"]):
                continue  # the gate already judged exactly this record — hold
            out[w] = rec
        return out

    # ── one sweep ──
    def run_once(self, stop: Optional[threading.Event] = None) -> "CycleResultLike":
        prev = self._load_state()
        # Late-bet leads: resolve any matured parked bets, then force-include the
        # resolution-validated winners in this sweep so they get the full eval
        # funnel (score + Claude gate) before they can reach the paper watchlist.
        seeds = self._late_bet_seeds()
        # Paper-evidence override (A): force-include wallets with a positive
        # realized paper record so a decayed-off earner is re-swept and can
        # re-enter — the sweep, not this cache, decides (blacklist and the
        # replay proven-negative gate still bind inside the cycle).
        proven = self._paper_proven()
        evaluated = self._evaluate(
            self.cfg, must_include=set(prev.on_watchlist) | set(seeds) | set(proven),
            cache_dir=self.cache_dir, activity_ttl_s=self.activity_ttl_s, stop=stop,
        )
        if not evaluated:
            logger.info("[DISCOVERY] sweep produced no evaluations (stopped or empty)")
            return None
        # Sweep ran — consume the seeds so each winner is force-scored once.
        if seeds:
            try:
                late_bet_queue.clear_eval_seeds()
            except Exception:  # pragma: no cover - never break the sweep
                logger.warning("[DISCOVERY] failed to clear late-bet seeds", exc_info=True)
        # Exclude auto-demoted wallets (proven-negative copy ROI in their cooldown)
        # so a bad wallet can't re-qualify and squat a watchlist slot. Also exclude
        # time-box-retired wallets (inconclusive dead-band, neutrally removed and
        # re-discoverable once the retire window lapses) for the same slot reason.
        _now = self._now()
        blacklisted = promotion_state.active_blacklist(_now) | promotion_state.active_retired(_now)
        result = run_discovery_cycle(evaluated, prev, self.cfg,
                                     blacklisted=blacklisted,
                                     paper_proven=set(proven))

        # Claude gate — the FINAL admission check, after the statistical funnel.
        # Runs only on *newly* qualified wallets (retained ones were already
        # vetted), and a "skip" verdict drops the wallet from the watchlist and
        # the persisted state before either is written below. Fail-open: any LLM
        # failure admits the wallet. Skipped on the first-init seed.
        # Snapshot who was parked BEFORE this sweep's gate ran, so the drain below
        # only re-checks wallets deferred on an EARLIER sweep — not the ones this
        # sweep's gate is about to park (re-checking those immediately would just
        # burn a second rate-limited call for no gain; the limit didn't change
        # mid-sweep).
        parked_before = {e.get("wallet") for e in
                         gate_recheck_queue.pending(self.gate_recheck_queue_path)}

        verdicts, holdouts, gate_calls = (({}, set(), 0) if result.first_init
                                          else self._llm_gate(result, proven))

        # Re-run any gate checks that were deferred because claude -p was
        # rate/spend-limited on an earlier sweep. Must run AFTER the gate and
        # BEFORE the watchlist/state writes below, so a now-"skip" removes the
        # provisional wallet from what gets persisted this sweep. Drain only
        # wallets parked on an earlier sweep AND not re-gated this sweep (a
        # decay-then-requalify wallet the gate just handled), and share the gate's
        # per-sweep LLM budget so a recovery sweep never exceeds llm_review_top_n.
        gated_now = {e.wallet for e in result.newly_qualified}
        try:
            self._drain_gate_queue(
                result, only_wallets=(parked_before - gated_now),
                budget=self.llm_review_top_n - gate_calls)
        except Exception:  # a broken re-check must never break the sweep
            logger.warning("[DISCOVERY] gate re-check drain failed; continuing", exc_info=True)

        # auto-paper: rewrite the watchlist the harness consumes (post-gate)
        _atomic_write_json(self.watchlist_path,
                           watchlist_to_targets(result.watchlist, self.cfg))

        # Strategy 4: write the long-horizon wallets to their own file (a separate
        # track — never fed to the paper copier). Snapshot the current sweep so
        # the list reflects who's long-horizon right now.
        if self.cfg.s4_enabled and self.long_horizon_watchlist_path:
            _atomic_write_json(self.long_horizon_watchlist_path,
                               long_horizon_to_targets(result.long_horizon, self.cfg))
            if result.long_horizon:
                logger.info("[DISCOVERY] long-horizon (Strategy 4): %d wallets tracked",
                            len(result.long_horizon))

        # persist (stamp real time)
        result.new_state.last_run = self._now()
        self._save_state(result.new_state)

        # notify
        if result.first_init:
            top = ", ".join(f"{e.wallet[:8]}…({e.capture_cents:+.1f}¢)"
                            for e in result.watchlist[:5])
            self._send(
                f"🔍 <b>Discovery initialized</b> — {len(result.watchlist)} wallets on "
                f"the paper watchlist.\nTop: {top or '—'}"
            )
        else:
            seed_set = {w.lower() for w in seeds}
            for e in result.newly_qualified:
                msg = format_find(e, verdicts.get(e.wallet))
                if e.wallet in holdouts:
                    # A holdout is a wallet Claude said SKIP, admitted anyway to
                    # measure the counterfactual — say so, so the "Claude: skip"
                    # line below doesn't read as the gate contradicting itself.
                    msg = ("🧪 <b>Gate holdout</b> — Claude said skip; admitted to "
                           "paper anyway to measure whether the skip was right\n" + msg)
                if e.wallet.lower() in seed_set:
                    msg = ("🎯 <b>Late-bet lead validated</b> — won its "
                           "near-resolution bet, then cleared eval\n" + msg)
                if e.wallet.lower() in proven:
                    rec = proven[e.wallet.lower()]
                    msg = ("📈 <b>Paper-proven re-acquired</b> — realized paper "
                           f"record {rec['n_closed']} settled, ROI "
                           f"{rec['roi'] * 100:+.1f}% (${rec['net_pnl']:+.2f})\n" + msg)
                self._send(msg)

        logger.info(
            "[DISCOVERY] swept=%d qualified=%d new=%d removed=%d watchlist=%d",
            len(evaluated), len(result.watchlist), len(result.newly_qualified),
            len(result.removed), len(result.watchlist),
        )
        if result.paper_proven:
            logger.info("[DISCOVERY] paper-proven (realized-ledger override): %s",
                        ", ".join(result.paper_proven))
        if result.removed:
            logger.info("[DISCOVERY] decayed off paper: %s", ", ".join(result.removed))
        # Gate autopsy — every cull attributable (the RCA curve gates used to be
        # silent, which made "did the 1.5 ceiling over-cull?" unanswerable). One
        # line per REMOVED wallet (was on paper, dropped this sweep — the ones
        # that matter), plus an aggregate reason histogram over the whole sweep.
        for w in result.removed:
            logger.info("[DISCOVERY] cull: %s — %s", w,
                        result.culled.get(w, "unattributed"))
        if result.culled:
            gate_counts: dict[str, int] = {}
            for reason in result.culled.values():
                key = reason.split(" (", 1)[0].split(" —", 1)[0]
                gate_counts[key] = gate_counts.get(key, 0) + 1
            logger.info("[DISCOVERY] cull histogram: %s",
                        ", ".join(f"{k}={n}" for k, n in
                                  sorted(gate_counts.items(), key=lambda kv: -kv[1])))

        # consensus-of-sharps signal (signal-only) over the copy-validated wallets
        try:
            self._run_consensus(result.watchlist)
        except Exception:  # a signal scan must never break the discovery loop
            logger.warning("[DISCOVERY] consensus scan failed", exc_info=True)
        return result

    # ── consensus-of-sharps signal ──
    def _copy_validated_wallets(self, watchlist: list[Eval]) -> list[str]:
        """Watchlist wallets proven +EV under our copy action (the 'sharps')."""
        return [e.wallet for e in watchlist if proven_positive(
            e.copy_n, e.copy_roi,
            min_n=self.cfg.min_copy_replay_n, min_roi=self.cfg.min_copy_replay_roi)]

    def _load_consensus_fired(self) -> dict:
        if not self.consensus_fired_path:
            return {}
        try:
            return json.load(open(self.consensus_fired_path))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_consensus_fired(self, fired: dict) -> None:
        if self.consensus_fired_path:
            _atomic_write_json(self.consensus_fired_path, fired)

    def _live_consensus_buys(self, wallet: str) -> list:
        """Recent copyable BUYs (full fields) for one wallet, from cached activity."""
        since = self._now() - self.cfg.consensus_window_s
        out = []
        for a in fetch_activity(wallet, self.cache_dir, self.activity_ttl_s) or []:
            if a.get("type") != "TRADE" or a.get("side") != "BUY":
                continue
            ts = float(a.get("timestamp") or 0)
            if ts < since:
                continue
            price = float(a.get("price") or 0)
            if not is_copyable_entry(price):  # same band as the rest of the pipeline
                continue
            usd = float(a.get("usdcSize") or 0) or float(a.get("size") or 0) * price
            title = a.get("title", "") or ""
            out.append({
                "wallet": wallet, "condition_id": a.get("conditionId"),
                "outcome_index": a.get("outcomeIndex"), "usd": usd, "price": price,
                "ts": ts, "title": title,
                "slug": a.get("eventSlug") or a.get("slug") or "",
                "category": classify_market(title),
            })
        return out

    def _live_funder_map(self, wallets: list):
        """wallet(lower) -> non-CEX funder address ("" = unknown/CEX). Returns
        ``None`` on a total lookup failure so the caller can mark the consensus
        signal's independence as UNVERIFIED rather than silently passing a sybil
        cluster as independent (the anti-sybil collapse needs real funder data —
        and it's off entirely when ETHERSCAN_API_KEY is unset)."""
        import asyncio

        from src.copy_trading.wallet_funder import get_funder, is_cex_funder

        async def _gather():
            return await asyncio.gather(
                *[get_funder(w) for w in wallets], return_exceptions=True)
        try:
            infos = asyncio.run(_gather())
        except Exception:
            logger.warning("[DISCOVERY] consensus funder map failed; "
                           "independence will be marked UNVERIFIED", exc_info=True)
            return None
        out: dict = {}
        for w, info in zip(wallets, infos):
            if isinstance(info, Exception):
                continue                       # lookup FAILED -> absent (unverified)
            f = getattr(info, "funder", "") or ""
            # present-as-key = looked up; "" = CEX/no-traceable-funder (independent),
            # a real address = its funder (used to collapse same-funder sybils).
            out[w.lower()] = f if (f and not is_cex_funder(f)) else ""
        return out

    def _run_consensus(self, watchlist: list[Eval]) -> None:
        if not self.cfg.consensus_enabled:
            return
        sharps = self._copy_validated_wallets(watchlist)
        # Members are the copy-VALIDATED wallets, which need copy-replay data
        # (copy_n) — produced only when the sweep fetched resolutions (under
        # copy_replay_gate OR a resolution-needing theory OR Strategy 4). So when
        # there are too few sharps, name the likely cause (gate off → no copy data)
        # instead of going dark — but DON'T hard-skip on the gate alone: copy_n can
        # still be populated via those other paths, and consensus should run then.
        if len(sharps) < self.cfg.consensus_min_wallets:
            hint = "" if self.cfg.copy_replay_gate else \
                " — copy_replay_gate is off, so no copy-validation data (turn it on)"
            logger.info("[DISCOVERY] consensus: %d copy-validated sharps (< k=%d) — skip%s",
                        len(sharps), self.cfg.consensus_min_wallets, hint)
            return
        fired = self._load_consensus_fired()
        funder_of = self._consensus_funder_map_fn(sharps)
        run_consensus_scan(
            sharps,
            fetch_buys=self._consensus_fetch_buys_fn,
            resolver=self._consensus_resolver,
            send=self._send,
            fired=fired,
            now=self._now(),
            k=self.cfg.consensus_min_wallets,
            window_s=self.cfg.consensus_window_s,
            min_usd=self.cfg.consensus_min_usd,
            cooldown_s=self.cfg.consensus_cooldown_s,
            funder_of=funder_of,
            log=lambda m: logger.info("[DISCOVERY] %s", m),
        )
        self._save_consensus_fired(fired)

    def _llm_gate(self, result, proven: Optional[dict] = None) -> tuple[dict, set]:
        """Claude admission gate over this sweep's NEW qualifiers (mutates result).

        For each newly-qualified wallet (already ordered by strength), ask Claude
        for a verdict; a ``skip`` drops the wallet from ``result.watchlist``,
        ``result.newly_qualified`` and ``result.new_state.on_watchlist`` so it
        never reaches the watchlist file or the persisted state. Fail-open: a
        ``None`` verdict (LLM disabled, unavailable, or errored) admits the
        wallet. Bounded by ``llm_review_top_n`` per sweep — any new wallets past
        the cap are admitted ungated (with a warning) so a flood can't stall the
        loop. ``proven`` (wallet(lower) -> realized paper stats) annotates a
        paper-proven re-entry's dossier with the REALIZED copy record, so the
        gate judges the actual outcome of copying the wallet rather than
        re-rejecting on the same own-history stats it saw last time; a skip on
        one of these is logged as a distinct paper-proven-rejected event so the
        evidence conflict is visible instead of eaten. Returns
        ``(verdicts, holdout_wallets)``: wallet -> LLMVerdict for the
        reviewed wallets (annotates the Telegram pings), and the set of wallets
        holdout-admitted despite a skip. Never raises into the sweep loop.
        """
        if not self.llm_review_enabled or not result.newly_qualified:
            return {}, set(), 0
        proven = proven or {}
        verdicts: dict = {}
        rejected: set = set()
        holdout_wallets: set = set()
        holdouts = 0
        calls = 0                 # claude -p calls made (shared budget with the drain)
        for i, e in enumerate(result.newly_qualified):
            paper_rec = proven.get(e.wallet.lower())
            if i >= self.llm_review_top_n:
                logger.warning("[DISCOVERY] LLM gate cap (%d) reached — admitting %s ungated",
                               self.llm_review_top_n, e.wallet)
                self._record_gate(e, "admit-cap", admitted=True, paper_record=paper_rec)
                continue
            dossier = _dossier_from_eval(e, paper_record=paper_rec)
            try:
                v = self._llm_review(dossier, model=self.llm_model)
            except Exception:  # pragma: no cover - belt-and-suspenders
                v = None
            calls += 1
            if v is RATE_LIMITED:
                # Spend/rate-limited: don't lose the wallet. Admit it provisionally
                # (paper-only, reversible) AND park the check so it's redone once the
                # limit clears — instead of fail-open-and-forget (permanently ungated).
                self._enqueue_recheck(e, dossier)
                self._record_gate(e, "skip-deferred", admitted=True, requeued=True,
                                  paper_record=paper_rec)
                logger.info("[DISCOVERY] LLM gate rate-limited for %s — admitted "
                            "provisionally, check queued for re-run", e.wallet)
                continue
            if v is None:  # fail-open: a broken gate must not freeze discovery
                logger.warning("[DISCOVERY] LLM gate unavailable for %s — admitting (fail-open)",
                               e.wallet)
                self._record_gate(e, "admit-fail-open", admitted=True, paper_record=paper_rec)
                continue
            verdicts[e.wallet] = v
            if v.verdict == "skip":
                # Gate self-calibration holdout: occasionally admit a would-be-skip
                # (keeping its skip verdict/reasoning) so its paper outcome can later
                # be compared against the admitted wallets — the counterfactual the
                # gate's +EV can't be measured without. Capped per sweep, since it
                # is by construction admitting wallets the gate thinks are bad.
                if (self.holdout_frac > 0.0 and holdouts < self.holdout_max_per_sweep
                        and self._rand() < self.holdout_frac):
                    holdouts += 1
                    holdout_wallets.add(e.wallet)
                    self._record_gate(e, v.verdict, admitted=True, holdout=True,
                                      confidence=v.confidence, reasoning=v.reasoning,
                                      paper_record=paper_rec)
                    logger.info("[DISCOVERY] LLM gate HOLDOUT-admitted %s (would skip, "
                                "conf %.0f%%): measuring counterfactual",
                                e.wallet, v.confidence * 100)
                    continue
                self._record_gate(e, v.verdict, admitted=False,
                                  confidence=v.confidence, reasoning=v.reasoning,
                                  paper_record=paper_rec)
                rejected.add(e.wallet)
                if paper_rec:
                    # Evidence conflict: realized paper says copy, the gate says
                    # skip. Distinct marker so the autopsy/digest can surface it.
                    logger.info(
                        "[DISCOVERY] LLM gate REJECTED paper-proven %s (paper "
                        "n=%d roi %+.1f%%, conf %.0f%%): %s", e.wallet,
                        paper_rec["n_closed"], paper_rec["roi"] * 100,
                        v.confidence * 100, v.reasoning)
                else:
                    logger.info("[DISCOVERY] LLM gate REJECTED %s (conf %.0f%%): %s",
                                e.wallet, v.confidence * 100, v.reasoning)
            else:
                self._record_gate(e, v.verdict, admitted=True,
                                  confidence=v.confidence, reasoning=v.reasoning,
                                  paper_record=paper_rec)
        if rejected:
            self._drop_from_result(result, rejected)
            logger.info("[DISCOVERY] LLM gate dropped %d/%d new wallet(s) before watchlist add",
                        len(rejected), len(result.newly_qualified) + len(rejected))
        return verdicts, holdout_wallets, calls

    def _record_gate(self, e, verdict: str, *, admitted: bool, holdout: bool = False,
                     requeued: bool = False, confidence: float = 0.0,
                     reasoning: str = "", paper_record: Optional[dict] = None) -> None:
        """Append one gate decision to the history log (queryable via /gate).

        Records WHY the wallet qualified (its theories) and whether lead-lag was
        even measured, so the accept/reject mix is attributable per theory. A
        ``holdout`` row is a would-be-skip admitted anyway to measure the
        counterfactual; a ``requeued`` row is a provisional admit whose check was
        deferred (rate-limited) and parked for re-run; the ``confidence_band`` lets
        a later calibration slice outcomes by how sure the gate was. A
        ``paper_proven`` row was gated WITH its realized paper record in the
        dossier; ``paper_n`` pins which record was judged, so the wallet is only
        re-gated once NEW settled evidence exists (see ``_paper_proven``)."""
        row = {
            "ts": self._now(),
            "wallet": e.wallet,
            "verdict": verdict,
            "admitted": admitted,
            "holdout": holdout,
            "requeued": requeued,
            "confidence": round(confidence, 3),
            "confidence_band": _confidence_band(confidence),
            "theories": list(e.flagged_by),
            "had_leadlag": e.n > 0,
            "copy_n": e.copy_n,
            "reasoning": reasoning,
        }
        if paper_record:
            row["paper_proven"] = True
            row["paper_n"] = paper_record.get("n_closed")
            row["paper_roi"] = paper_record.get("roi")
        gate_history.append(self.gate_history_path, row)

    def _enqueue_recheck(self, e, dossier: dict) -> None:
        """Park a rate-limited wallet's gate check for a later sweep to re-run."""
        gate_recheck_queue.enqueue(
            self.gate_recheck_queue_path, e.wallet, dossier,
            theories=list(e.flagged_by), had_leadlag=e.n > 0, copy_n=e.copy_n,
            now=self._now())

    def _drain_gate_queue(self, result, only_wallets=None, budget=None) -> None:
        """Re-run deferred (rate-limited) gate checks against the current sweep.

        For each parked wallet that is still on the watchlist, re-run the check on
        its stored dossier. Only a REAL verdict resolves the wallet: a ``skip``
        removes the provisionally-admitted wallet from the watchlist + state now
        (and pings); ``follow``/``watch`` confirms it. Anything that is NOT a real
        verdict — still rate-limited, a timeout, or any transient re-check failure —
        keeps the wallet parked for the next sweep, so a deferred wallet is never
        dequeued-and-forgotten while still lacking a real decision (that would be
        the fail-open-and-forget this whole feature removes). A wallet that decayed
        off the watchlist is dequeued. ``only_wallets`` (when given) restricts the
        drain to wallets parked on an EARLIER sweep and not re-gated this sweep.
        ``budget`` caps the claude -p re-checks this sweep — SHARED with the gate's
        own per-sweep budget so a recovery sweep never exceeds ``llm_review_top_n``
        total LLM calls; leftovers wait for the next sweep. Never raises."""
        if not self.llm_review_enabled or not self.gate_recheck_queue_path:
            return
        if budget is None:
            budget = self.llm_review_top_n
        if budget <= 0:
            return
        entries = gate_recheck_queue.pending(self.gate_recheck_queue_path)
        if not entries:
            return
        on_wl = {e.wallet for e in result.watchlist}
        resolved: set = set()      # dequeue (re-checked or gone)
        rejected: set = set()      # remove from watchlist (deferred check said skip)
        checked = 0
        for entry in entries:
            wallet = entry.get("wallet")
            if not wallet:
                continue
            if only_wallets is not None and wallet not in only_wallets:
                continue                      # parked/gated THIS sweep — wait
            if wallet not in on_wl:
                resolved.add(wallet)          # decayed off — nothing to re-check
                continue
            if checked >= budget:
                break                          # shared cap; leave the rest parked
            checked += 1
            try:
                v = self._llm_review(entry.get("dossier") or {}, model=self.llm_model)
            except Exception:  # pragma: no cover - defensive
                v = None
            verdict = getattr(v, "verdict", None)
            if verdict is None:
                # Still rate-limited OR a transient re-check failure (timeout/None):
                # keep it parked and try again next sweep. NEVER dequeue a wallet
                # that still has no real decision.
                continue
            resolved.add(wallet)               # a real verdict — resolve it
            self._record_recheck(entry, verdict)
            if verdict == "skip":
                rejected.add(wallet)
                logger.info("[DISCOVERY] deferred gate re-check REJECTED %s: %s",
                            wallet, getattr(v, "reasoning", ""))
                self._send(
                    "🚫 <b>Deferred gate re-check</b> — Claude now says <b>skip</b>; "
                    f"removed the provisionally-admitted wallet\n"
                    f"<code>{html.escape(wallet)}</code>\n"
                    f"<i>{html.escape(getattr(v, 'reasoning', '') or '')}</i>")
        if rejected:
            self._drop_from_result(result, rejected)
            logger.info("[DISCOVERY] deferred re-check removed %d provisional wallet(s)",
                        len(rejected))
        if resolved:
            gate_recheck_queue.remove(self.gate_recheck_queue_path, resolved)

    def _record_recheck(self, entry: dict, verdict) -> None:
        """Log a deferred-check resolution to gate-history (from the stored entry,
        since the sweep's Eval for this retained wallet may differ)."""
        admitted = verdict != "skip"
        gate_history.append(self.gate_history_path, {
            "ts": self._now(),
            "wallet": entry.get("wallet"),
            "verdict": (verdict or "admit-recheck-unavailable"),
            "admitted": admitted,
            "holdout": False,
            "requeued": False,
            "recheck": True,
            "theories": list(entry.get("theories") or []),
            "had_leadlag": bool(entry.get("had_leadlag")),
            "copy_n": entry.get("copy_n", 0),
            "reasoning": "deferred gate check re-run after rate limit",
        })

    @staticmethod
    def _drop_from_result(result, rejected: set) -> None:
        """Remove gate-rejected wallets from the watchlist, the new-qualifier
        list, and the persisted state so they're neither written nor remembered
        (a rejected wallet is re-evaluated as 'new' on the next sweep)."""
        result.watchlist = [e for e in result.watchlist if e.wallet not in rejected]
        result.newly_qualified = [e for e in result.newly_qualified if e.wallet not in rejected]
        for w in rejected:
            result.new_state.on_watchlist.pop(w, None)

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
