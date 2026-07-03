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
        if floor.passed:
            offers.append({
                "wallet": wallet, "n_closed": stats.n_closed, "roi": stats.roi,
                "net_pnl": stats.net_pnl, "stats": stats, "theories": theories,
                "warnings": floor.warnings,
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
    )

    sent: list[dict] = []
    for o in offers:
        stats = o.get("stats")
        verdict = None
        if review_fn is not None:
            try:
                from src.copy_trading.llm_review import build_promotion_dossier
                dossier = build_promotion_dossier(
                    o["wallet"], stats=stats, theories=o.get("theories"),
                    floor_warnings=o.get("warnings"), tier=default_tier)
                verdict = review_fn(dossier) if llm_model is None else review_fn(dossier, model=llm_model)
            except Exception:  # advisory only — a broken review never blocks the offer
                logger.warning("[PROMOTE-GATE] LLM review errored for %s (offering anyway)",
                               o["wallet"], exc_info=True)
                verdict = None
        o = {**o, "tier": default_tier, "llm": verdict,
             "llm_attempted": review_fn is not None}
        if send_offer(o):
            promotion_state.record_offer(
                o["wallet"], status="offered",
                n_closed=o["n_closed"], roi=o["roi"], now=now)
            _log_history(history_path, {
                "ts": now, "event": "offer", "wallet": o["wallet"],
                "n_closed": o["n_closed"], "roi": round(float(o["roi"] or 0.0), 4),
                "net_pnl": o["net_pnl"], "tier": default_tier,
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

    return sent, applied
