"""Auto promote / demote governance over the System-B paper-copy ledger.

Each copy cycle, look at every watched wallet's *settled* paper-copy record and:

  * **Promote-offer** a wallet that has matured to a real edge — at least
    ``promote_min_n`` resolved copies AND copy ROI at/above ``promote_min_roi``
    (default n>=15, ROI>=+10%). One Telegram offer with a tap-to-accept button is
    sent (deduped via the offers store); accepting adds it to System A.
  * **Demote** a wallet proven to lose — at least ``demote_min_n`` resolved copies
    AND copy ROI at/below ``demote_max_roi`` (default n>=15, ROI<=-5%). It's
    blacklisted for a cooldown so it's dropped from the watchlist and can't
    immediately re-qualify on the next discovery sweep.

The decision (`evaluate_governance`) is pure and unit-tested; the cycle wrapper
does the state I/O and fires injected senders, so there's no Telegram dependency
here. Promotion never moves real money on its own — System A still runs under
PREVIEW_MODE until the owner turns it off.
"""

from __future__ import annotations

from typing import Callable, Optional

from src.copy_trading import promotion_state
from src.copy_trading.pnl_unified import aggregate_system_b


def evaluate_governance(
    wallets,
    *,
    promoted: set,
    blacklist: set,
    offered: set,
    promote_min_n: int,
    promote_min_roi: float,
    demote_min_n: int,
    demote_max_roi: float,
    now: float,
    cooldown_s: float,
) -> tuple[list[dict], list[dict]]:
    """Decide promote-offers and demotions from per-wallet System-B P&L.

    ``wallets`` is any iterable of objects exposing ``.wallet`` (lowercased),
    ``.n_closed``, ``.roi`` (None when no settled capital) and ``.net_pnl`` — i.e.
    ``WalletPnl`` rows from ``aggregate_system_b``. ``promoted`` / ``blacklist`` /
    ``offered`` are lowercased wallet sets used to suppress repeats. Returns
    ``(offers, demotions)``; each item is a dict with wallet + stats (demotions
    also carry ``until``). Pure — no I/O, no side effects.
    """
    offers: list[dict] = []
    demotions: list[dict] = []
    for w in wallets:
        key = (w.wallet or "").lower()
        if not key.startswith("0x"):
            continue                      # skip unknown / untagged buckets
        if key in promoted or key in blacklist:
            continue                      # already graduated or already demoted
        roi = w.roi
        if roi is None:                   # no settled capital yet — can't judge
            continue
        n = w.n_closed
        if n >= promote_min_n and roi >= promote_min_roi:
            if key not in offered:
                offers.append({
                    "wallet": w.wallet, "n_closed": n,
                    "roi": roi, "net_pnl": w.net_pnl,
                })
        elif n >= demote_min_n and roi <= demote_max_roi:
            demotions.append({
                "wallet": w.wallet, "n_closed": n,
                "roi": roi, "net_pnl": w.net_pnl,
                "until": now + cooldown_s,
            })
    return offers, demotions


def run_governance_cycle(
    paper_positions,
    *,
    now: float,
    promote_min_n: int,
    promote_min_roi: float,
    demote_min_n: int,
    demote_max_roi: float,
    cooldown_s: float,
    default_tier: str,
    send_offer: Callable[[dict], bool],
    send_demotion: Optional[Callable[[dict], None]] = None,
) -> tuple[list[dict], list[dict]]:
    """Aggregate the System-B ledger, evaluate, then persist + notify.

    ``send_offer(offer)`` must return truthy when the Telegram offer was actually
    delivered — only then is it recorded, so a transient send failure is retried
    next cycle instead of being silently swallowed. ``send_demotion`` is a
    best-effort notice. Returns ``(offers_sent, demotions_applied)``.
    """
    b_wallets = aggregate_system_b(list(paper_positions))
    promoted = promotion_state.promoted_set()
    blacklist = promotion_state.active_blacklist(now)
    offered = set(promotion_state.offers_map().keys())

    offers, demotions = evaluate_governance(
        b_wallets,
        promoted=promoted, blacklist=blacklist, offered=offered,
        promote_min_n=promote_min_n, promote_min_roi=promote_min_roi,
        demote_min_n=demote_min_n, demote_max_roi=demote_max_roi,
        now=now, cooldown_s=cooldown_s,
    )

    sent: list[dict] = []
    for o in offers:
        o = {**o, "tier": default_tier}
        if send_offer(o):
            promotion_state.record_offer(
                o["wallet"], status="offered",
                n_closed=o["n_closed"], roi=o["roi"], now=now)
            sent.append(o)

    applied: list[dict] = []
    for d in demotions:
        promotion_state.add_blacklist(
            d["wallet"], until=d["until"], reason="auto-demote",
            n_closed=d["n_closed"], roi=d["roi"], now=now)
        if send_demotion is not None:
            try:
                send_demotion(d)
            except Exception:  # pragma: no cover - a notice must not break the loop
                pass
        applied.append(d)

    return sent, applied
