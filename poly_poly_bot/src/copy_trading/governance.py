"""Auto promote / demote governance over the System-B paper-copy ledger.

Each copy cycle, look at every watched wallet's *settled* paper-copy record and:

  * **Promote-offer** a wallet only once it clears the trustworthy promotion gate
    (``promotion_gate.evaluate_floor``): enough settled copies, ROI above the
    floor, a per-bet RETURN t-stat that says the edge is not just variance, a
    non-decaying recent half, and bets spread across independent markets. A wallet
    that clears the old bare bar (n + ROI) but fails the new rigor is *held*, not
    offered, and the reason is logged. One Telegram offer with a tap-to-accept
    button is sent (deduped via the offers store); accepting adds it to System A.
    On top of the statistical floor an *advisory* Claude review annotates the
    offer — it never blocks one (the floor is the block; the gate's own
    calibration is still unvalidated), so a broken CLI can't silently suppress a
    good candidate.
  * **Demote** a wallet proven to lose — enough resolved copies AND a negative ROI
    past the floor AND a real absolute dollar loss (not micro-capital noise) AND a
    win rate that doesn't hold up. It's blacklisted for a cooldown so it's dropped
    from the watchlist and can't immediately re-qualify on the next sweep.

The decision (`evaluate_governance`) is pure and unit-tested over per-wallet
settled positions; the cycle wrapper does the state I/O, the advisory LLM call,
history logging, and fires injected senders. Promotion never moves real money on
its own — System A still runs under PREVIEW_MODE until the owner turns it off, and
`/golive` re-checks the wallet live before that flip.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from src.copy_trading import gate_history, promotion_gate, promotion_state
from src.copy_trading.copy_paper import is_dust_fill

logger = logging.getLogger("poly_poly_bot")


def _theories_from_positions(positions) -> list:
    """Union of the discovery theories that flagged this wallet, from the settled
    positions' stamped ``flagged_by`` (stable across watchlist re-flags)."""
    out: list = []
    for p in positions:
        for t in (getattr(p, "flagged_by", None) or ()):
            if t not in out:
                out.append(t)
    return out


def group_settled_by_wallet(paper_positions) -> dict[str, list]:
    """wallet(lower) -> its settled, non-dust copy positions. The unit the
    promotion gate scores."""
    by_wallet: dict[str, list] = {}
    for p in paper_positions:
        if not getattr(p, "closed", False):
            continue
        if is_dust_fill(p):
            continue
        key = (getattr(p, "target", "") or "").lower()
        if not key:
            continue
        by_wallet.setdefault(key, []).append(p)
    return by_wallet


def paper_proven_wallets(
    ledger_path: str, *, min_n: int, min_roi: float,
) -> dict[str, dict]:
    """Wallets whose REALIZED paper-copy record is positive: >= ``min_n`` settled
    non-dust copies at ROI > ``min_roi``. Feeds the discovery sweep's
    paper-evidence retention override (2026-07 starvation RCA: retention was
    blind to paper results, so the best earners decayed off mid-accrual and the
    promotion funnel starved). Recomputed from the ledger file every call —
    status is never sticky, so it lapses the moment the record stops clearing
    the bar. Reads the JSONL defensively and fails safe to {} (no override this
    sweep) on a missing/corrupt/wrong-shape ledger — but logs the failure so a
    persistent parse error can't disable the path invisibly. Uses the same
    settled/dust semantics as the promotion gate (``group_settled_by_wallet`` +
    ``compute_stats``) so "proven" means the same thing on both sides.
    """
    import json
    from types import SimpleNamespace

    try:
        rows: list = []
        with open(ledger_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue  # one torn/garbage line must not void the ledger
                if isinstance(d, dict):
                    rows.append(SimpleNamespace(**d))
        out: dict[str, dict] = {}
        for wallet, positions in group_settled_by_wallet(rows).items():
            stats = promotion_gate.compute_stats(wallet, positions)
            if (stats.n_closed >= min_n and stats.roi is not None
                    and stats.roi > min_roi):
                out[wallet] = {
                    "n_closed": stats.n_closed,
                    "roi": round(stats.roi, 4),
                    "net_pnl": round(stats.net_pnl, 2),
                    "wins": stats.wins,
                }
        return out
    except FileNotFoundError:
        return {}  # no paper history yet — nothing to prove
    except Exception as e:
        logger.debug("[DISCOVERY] paper-proven ledger read failed (%s) — "
                     "no paper-evidence override this sweep", e)
        return {}


def _probation_eligible(
    stats, replay: dict | None, *,
    min_settled: int, min_replay_n: int, min_replay_roi: float, min_replay_tstat: float,
) -> bool:
    """A wallet that fails the full promote floor but has STRONG own-history
    copy-and-hold replay (already computed by discovery) AND a small forward-paper
    sample that agrees. This ONLY lowers the offer bar — the real-money /golive
    gate is untouched (still 30 settled + full floor), so probation never weakens
    what real capital must clear. Requiring a strong copy-replay edge is itself the
    anti-scooper guard: the replay measures the copyable-band hold-to-resolution
    action, exactly what a scooper's near-$1 book fails."""
    if not replay:
        return False
    own_strong = (int(replay.get("copy_n", 0)) >= min_replay_n
                  and float(replay.get("copy_roi", 0.0)) >= min_replay_roi
                  and float(replay.get("copy_tstat", 0.0)) >= min_replay_tstat)
    fwd_agrees = (stats.n_closed >= min_settled and stats.roi is not None
                  and stats.roi >= 0.0
                  and (stats.second_half_roi is None or stats.second_half_roi >= 0.0))
    return own_strong and fwd_agrees


def evaluate_governance(
    positions_by_wallet: dict[str, list],
    *,
    promoted: set,
    blacklist: set,
    offered: set,
    promote_min_n: int,
    promote_min_roi: float,
    promote_min_tstat: float,
    promote_min_second_half_roi: float,
    promote_min_conditions: int,
    promote_min_categories: int,
    demote_min_n: int,
    demote_max_roi: float,
    demote_min_abs_loss: float,
    demote_max_wilson: float,
    now: float,
    cooldown_s: float,
    replay_by_wallet: dict | None = None,
    probation_enabled: bool = False,
    probation_min_settled: int = 5,
    probation_min_replay_n: int = 20,
    probation_min_replay_roi: float = 0.05,
    probation_min_replay_tstat: float = 2.0,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Decide promote-offers, demotions, and holds from per-wallet settled P&L.

    ``positions_by_wallet`` maps a lowercased ``0x`` wallet to its settled
    ``PaperPosition`` list (see ``group_settled_by_wallet``). ``promoted`` /
    ``blacklist`` / ``offered`` are lowercased wallet sets that suppress repeats.
    Returns ``(offers, demotions, held)``:

      * ``offers``  — wallets that cleared the full statistical floor (each dict
        carries ``stats``/``theories``/``warnings`` for the annotation).
      * ``demotions`` — wallets bad enough to blacklist (carry ``until``).
      * ``held``    — wallets that met the old n+ROI bar but the new rigor holds,
        each with the human-readable ``reasons`` (for observability, not action).

    Pure — no I/O, no side effects."""
    offers: list[dict] = []
    demotions: list[dict] = []
    held: list[dict] = []

    for key, positions in positions_by_wallet.items():
        if not key.startswith("0x"):
            continue
        if key in promoted or key in blacklist:
            continue
        wallet = next((getattr(p, "target", None) for p in positions
                       if getattr(p, "target", None)), key)
        stats = promotion_gate.compute_stats(wallet, positions)

        demote, dreason = promotion_gate.should_demote(
            stats, min_n=demote_min_n, max_roi=demote_max_roi,
            min_abs_loss=demote_min_abs_loss, max_wilson=demote_max_wilson)
        if demote:
            demotions.append({
                "wallet": wallet, "n_closed": stats.n_closed, "roi": stats.roi,
                "net_pnl": stats.net_pnl, "until": now + cooldown_s, "reason": dreason,
            })
            continue

        if key in offered:
            continue  # already offered / accepted / held — don't re-evaluate the offer

        floor = promotion_gate.evaluate_floor(
            stats, min_n=promote_min_n, min_roi=promote_min_roi,
            min_tstat=promote_min_tstat,
            min_second_half_roi=promote_min_second_half_roi,
            min_conditions=promote_min_conditions,
            min_categories=promote_min_categories)
        theories = _theories_from_positions(positions)
        replay = (replay_by_wallet or {}).get(key)
        if floor.passed:
            offers.append({
                "wallet": wallet, "n_closed": stats.n_closed, "roi": stats.roi,
                "net_pnl": stats.net_pnl, "stats": stats, "theories": theories,
                "warnings": floor.warnings,
            })
        elif probation_enabled and _probation_eligible(
                stats, replay, min_settled=probation_min_settled,
                min_replay_n=probation_min_replay_n,
                min_replay_roi=probation_min_replay_roi,
                min_replay_tstat=probation_min_replay_tstat):
            # Fast-track: strong own-history replay + a small agreeing forward
            # sample -> an EARLY offer tagged "probation" (tap-to-accept only, never
            # auto-accepted; real money still needs manual /golive + /live CONFIRM).
            offers.append({
                "wallet": wallet, "n_closed": stats.n_closed, "roi": stats.roi,
                "net_pnl": stats.net_pnl, "stats": stats, "theories": theories,
                "warnings": floor.reasons,   # surface WHY the full floor was skipped
                "tier": "probation", "probation": True,
                "replay": {"copy_n": int((replay or {}).get("copy_n", 0)),
                           "copy_roi": float((replay or {}).get("copy_roi", 0.0)),
                           "copy_tstat": float((replay or {}).get("copy_tstat", 0.0))},
            })
        elif stats.n_closed >= promote_min_n and stats.roi is not None \
                and stats.roi >= promote_min_roi:
            # Cleared the old bare bar but the new rigor holds it — surface why.
            held.append({
                "wallet": wallet, "n_closed": stats.n_closed, "roi": stats.roi,
                "net_pnl": stats.net_pnl, "reasons": floor.reasons,
                "stats": stats, "theories": theories,
            })

    return offers, demotions, held


def find_retirements(
    positions_by_wallet: dict[str, list],
    *,
    now: float,
    min_n: int,
    dead_band_low: float,
    dead_band_high: float,
    max_window_s: float,
    promoted: set,
    blacklist: set,
    offered: set,
    retired: set,
) -> list[dict]:
    """Wallets to NEUTRALLY retire (time-box the dead-band). A wallet that has
    enough settled copies, sits in the inconclusive band (``dead_band_low <
    roi < dead_band_high`` — neither promotable nor demotable), and has been
    observed longer than ``max_window_s`` (by its oldest copy) is stuck: it is
    removed so it stops squatting a watchlist slot, but it is NOT a proven loser,
    so this is distinct from a demotion and it stays re-discoverable. Pure."""
    out: list[dict] = []
    for key, positions in positions_by_wallet.items():
        if not key.startswith("0x"):
            continue
        if key in promoted or key in blacklist or key in offered or key in retired:
            continue
        wallet = next((getattr(p, "target", None) for p in positions
                       if getattr(p, "target", None)), key)
        stats = promotion_gate.compute_stats(wallet, positions)
        if stats.n_closed < min_n or stats.roi is None:
            continue
        if not (dead_band_low < stats.roi < dead_band_high):
            continue
        oldest = min((float(getattr(p, "opened_ts", 0.0) or 0.0) for p in positions),
                     default=now)
        age_s = now - oldest
        if age_s < max_window_s:
            continue
        out.append({
            "wallet": wallet, "n_closed": stats.n_closed, "roi": stats.roi,
            "net_pnl": stats.net_pnl, "age_days": round(age_s / 86400.0, 1),
        })
    return out


def _log_history(history_path: Optional[str], row: dict) -> None:
    gate_history.append(history_path, row)


def run_governance_cycle(
    paper_positions,
    *,
    now: float,
    promote_min_n: int,
    promote_min_roi: float,
    promote_min_tstat: float,
    promote_min_second_half_roi: float,
    promote_min_conditions: int,
    promote_min_categories: int,
    demote_min_n: int,
    demote_max_roi: float,
    demote_min_abs_loss: float,
    demote_max_wilson: float,
    cooldown_s: float,
    default_tier: str,
    send_offer: Callable[[dict], bool],
    send_demotion: Optional[Callable[[dict], None]] = None,
    review_fn: Optional[Callable[[dict], object]] = None,
    llm_model: Optional[str] = None,
    history_path: Optional[str] = None,
    replay_by_wallet: dict | None = None,
    probation_enabled: bool = False,
    probation_min_settled: int = 5,
    probation_min_replay_n: int = 20,
    probation_min_replay_roi: float = 0.05,
    probation_min_replay_tstat: float = 2.0,
    time_box_enabled: bool = False,
    time_box_window_s: float = 45 * 86400.0,
    retire_cooldown_s: float = 45 * 86400.0,
    send_retirement: Optional[Callable[[dict], None]] = None,
) -> tuple[list[dict], list[dict]]:
    """Group the settled ledger, evaluate the gate, then persist + notify.

    ``send_offer(offer)`` must return truthy when the Telegram offer was actually
    delivered — only then is it recorded, so a transient send failure is retried
    next cycle. ``review_fn`` (default off) is the ADVISORY Claude promotion
    review; its verdict rides along on the offer dict as ``llm`` and never blocks
    the offer. Every fired offer / demote / first-time hold is appended to
    ``history_path`` (promotion-gate-history) for ``/gate``. Returns
    ``(offers_sent, demotions_applied)``."""
    positions_by_wallet = group_settled_by_wallet(paper_positions)
    promoted = promotion_state.promoted_set()
    blacklist = promotion_state.active_blacklist(now)
    offers_map = promotion_state.offers_map()
    # An active offer (offered/accepted/dismissed) suppresses re-offering; a prior
    # "held" record suppresses re-logging the hold but still lets a later pass fire.
    offered_active = {w for w, r in offers_map.items()
                      if r.get("status") in ("offered", "accepted", "dismissed")}
    held_seen = {w for w, r in offers_map.items() if r.get("status") == "held"}

    offers, demotions, held = evaluate_governance(
        positions_by_wallet,
        promoted=promoted, blacklist=blacklist, offered=offered_active,
        promote_min_n=promote_min_n, promote_min_roi=promote_min_roi,
        promote_min_tstat=promote_min_tstat,
        promote_min_second_half_roi=promote_min_second_half_roi,
        promote_min_conditions=promote_min_conditions,
        promote_min_categories=promote_min_categories,
        demote_min_n=demote_min_n, demote_max_roi=demote_max_roi,
        demote_min_abs_loss=demote_min_abs_loss, demote_max_wilson=demote_max_wilson,
        now=now, cooldown_s=cooldown_s,
        replay_by_wallet=replay_by_wallet, probation_enabled=probation_enabled,
        probation_min_settled=probation_min_settled,
        probation_min_replay_n=probation_min_replay_n,
        probation_min_replay_roi=probation_min_replay_roi,
        probation_min_replay_tstat=probation_min_replay_tstat,
    )

    sent: list[dict] = []
    for o in offers:
        stats = o.get("stats")
        # A probation offer carries its own tier so it never sizes as a fully-vetted
        # promotion; a normal offer falls back to the default tier.
        o_tier = o.get("tier") or default_tier
        verdict = None
        if review_fn is not None:
            try:
                from src.copy_trading.llm_review import build_promotion_dossier
                dossier = build_promotion_dossier(
                    o["wallet"], stats=stats, theories=o.get("theories"),
                    floor_warnings=o.get("warnings"), tier=o_tier)
                verdict = review_fn(dossier) if llm_model is None else review_fn(dossier, model=llm_model)
            except Exception:  # advisory only — a broken review never blocks the offer
                logger.warning("[PROMOTE-GATE] LLM review errored for %s (offering anyway)",
                               o["wallet"], exc_info=True)
                verdict = None
        o = {**o, "tier": o_tier, "llm": verdict,
             "llm_attempted": review_fn is not None}
        if send_offer(o):
            promotion_state.record_offer(
                o["wallet"], status="offered",
                n_closed=o["n_closed"], roi=o["roi"], now=now)
            _log_history(history_path, {
                "ts": now, "event": "offer", "wallet": o["wallet"],
                "n_closed": o["n_closed"], "roi": round(float(o["roi"] or 0.0), 4),
                "net_pnl": o["net_pnl"], "tier": o_tier, "probation": o.get("probation", False),
                "roi_tstat": getattr(stats, "roi_tstat", None),
                "second_half_roi": getattr(stats, "second_half_roi", None),
                "distinct_conditions": getattr(stats, "distinct_conditions", None),
                "distinct_categories": getattr(stats, "distinct_categories", None),
                "theories": o.get("theories", []),
                "warnings": o.get("warnings", []),
                "llm_verdict": getattr(verdict, "verdict", None),
                "llm_confidence": getattr(verdict, "confidence", None),
                "llm_reasoning": getattr(verdict, "reasoning", None),
            })
            sent.append(o)

    applied: list[dict] = []
    for d in demotions:
        promotion_state.add_blacklist(
            d["wallet"], until=d["until"], reason="auto-demote",
            n_closed=d["n_closed"], roi=d["roi"] or 0.0, now=now)
        _log_history(history_path, {
            "ts": now, "event": "demote", "wallet": d["wallet"],
            "n_closed": d["n_closed"], "roi": round(float(d["roi"] or 0.0), 4),
            "net_pnl": d["net_pnl"], "reason": d.get("reason", ""),
        })
        if send_demotion is not None:
            try:
                send_demotion(d)
            except Exception:  # pragma: no cover - a notice must not break the loop
                pass
        applied.append(d)

    # Record first-time holds once (transition-safe: a held wallet that later
    # passes the floor is not in offered_active, so it will still fire an offer).
    for h in held:
        key = (h["wallet"] or "").lower()
        if key in held_seen:
            continue
        promotion_state.record_offer(
            h["wallet"], status="held", n_closed=h["n_closed"], roi=h["roi"] or 0.0, now=now)
        _log_history(history_path, {
            "ts": now, "event": "held", "wallet": h["wallet"],
            "n_closed": h["n_closed"], "roi": round(float(h["roi"] or 0.0), 4),
            "net_pnl": h["net_pnl"], "reasons": h.get("reasons", []),
            "theories": h.get("theories", []),
        })
        logger.info("[PROMOTE-GATE] holding %s (n=%d roi=%+.0f%%): %s",
                    h["wallet"], h["n_closed"], (h["roi"] or 0.0) * 100,
                    "; ".join(h.get("reasons", [])))

    # Time-box the dead-band: neutrally retire wallets stuck inconclusive past the
    # observation window so they stop squatting a slot (re-discoverable, NOT
    # blacklisted). Off by default; the dead-band is (demote line, promote line).
    if time_box_enabled:
        retired_now = promotion_state.active_retired(now)
        for r in find_retirements(
                positions_by_wallet, now=now, min_n=demote_min_n,
                dead_band_low=demote_max_roi, dead_band_high=promote_min_roi,
                max_window_s=time_box_window_s, promoted=promoted,
                blacklist=blacklist, offered=offered_active, retired=retired_now):
            promotion_state.add_retired(
                r["wallet"], until=now + retire_cooldown_s, reason="time-box: dead-band",
                n_closed=r["n_closed"], roi=r["roi"] or 0.0, now=now)
            _log_history(history_path, {
                "ts": now, "event": "retire", "wallet": r["wallet"],
                "n_closed": r["n_closed"], "roi": round(float(r["roi"] or 0.0), 4),
                "net_pnl": r["net_pnl"], "age_days": r["age_days"],
                "reason": "time-box: inconclusive past window",
            })
            if send_retirement is not None:
                try:
                    send_retirement(r)
                except Exception:  # pragma: no cover — a notice must not break the loop
                    pass
            logger.info("[PROMOTE-GATE] retiring %s (n=%d roi=%+.0f%% age=%.0fd): "
                        "dead-band past window, re-discoverable",
                        r["wallet"], r["n_closed"], (r["roi"] or 0.0) * 100, r["age_days"])

    return sent, applied
