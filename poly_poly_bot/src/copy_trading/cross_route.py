"""Cross-strategy wallet routing — A's exits feed B's watchlist (2026-07 race).

The A-vs-B counterfactual proved per-wallet evidence FLIPS between fill regimes
(0x161a: -21% realized under A's lagged fills, +9.1% under B's instant-copy
replay). So when a wallet leaves strategy A's ecosystem — a governance demote, a
discovery cull, a retention drop — it must not silently vanish from strategy B,
whose thesis those wallets may prove. Any A-exit is offered to B through one
B-fit check:

  * its own-history copy replay clears the replay bar (the replay IS the
    B-mechanism simulation: copy-and-hold at the target's own price), OR
  * B's own realized ledger is already positive on it (n >= 5, roi > 0).

A wallet that fails both stays out (proven-negative beats proven-positive —
replay-negative culls are B-negative by construction). B's own blacklist always
binds. Routed wallets land in B's extras watchlist file, provenance-stamped, so
the funnel digest and the week-end verdict can attribute every B-only wallet.
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

from src.copy_trading import governance, promotion_state
from src.copy_trading.copy_replay import proven_positive
from src.logger import logger

B_SCOPE = "b"


def _load_targets(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        targets = data.get("targets")
        return targets if isinstance(targets, list) else []
    except (OSError, json.JSONDecodeError, AttributeError):
        return []


def _write_targets(path: str, targets: list[dict]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"source": "strategy-b-extras", "targets": targets}, f, indent=2)
    os.replace(tmp, path)


def seed_extras(path: str, wallets: str, now: Optional[float] = None) -> bool:
    """Create B's extras file with the seed wallets — ONLY if it doesn't exist
    yet, so a restart never resets cross-routed history. Returns True if seeded."""
    if os.path.exists(path):
        return False
    seeds = [w.strip() for w in (wallets or "").split(",") if w.strip()]
    ts = now if now is not None else time.time()
    _write_targets(path, [
        {"wallet": w, "source": "seed", "added_ts": ts,
         "reason": "initial strategy-B seed (A-demoted, B-fit per counterfactual)"}
        for w in seeds
    ])
    if seeds:
        logger.info(f"[COPY-PAPER-B] seeded extras watchlist with "
                    f"{len(seeds)} wallet(s): {', '.join(seeds)}")
    return bool(seeds)


def route_to_b(
    wallet: str,
    *,
    extras_path: str,
    b_ledger_path: str,
    reason: str,
    replay_n: int = 0,
    replay_roi: float = 0.0,
    min_replay_n: int = 12,
    min_replay_roi: float = 0.02,
    watchlist_entry: Optional[dict] = None,
    now: Optional[float] = None,
) -> tuple[bool, str]:
    """Offer an A-exiting wallet to strategy B. Returns (routed, why).

    Idempotent: an already-routed wallet is a no-op. ``watchlist_entry`` (the
    wallet's last discovery-watchlist row, if available) donates
    approved_categories / median_usd so B's category gate and conviction sizing
    keep working for a wallet the shared watchlist no longer carries.
    """
    w = (wallet or "").strip()
    if not w:
        return False, "empty wallet"
    now = now if now is not None else time.time()

    if promotion_state.is_blacklisted(w, now=now, scope=B_SCOPE):
        return False, "B-blacklisted (B's own proven-negative binds)"

    targets = _load_targets(extras_path)
    if any((t.get("wallet") or "").lower() == w.lower() for t in targets):
        return False, "already routed"

    replay_fit = proven_positive(int(replay_n), float(replay_roi),
                                 min_n=min_replay_n, min_roi=min_replay_roi)
    b_record_fit = False
    b_rec = None
    if not replay_fit:
        proven = governance.paper_proven_wallets(
            b_ledger_path, min_n=5, min_roi=0.0)
        b_rec = proven.get(w.lower())
        b_record_fit = b_rec is not None

    if not (replay_fit or b_record_fit):
        return False, (f"not B-fit (replay {replay_roi:+.3f} @ n={replay_n} "
                       f"< {min_replay_roi:+.3f} @ n>={min_replay_n}; no positive B record)")

    entry = {
        "wallet": w,
        "source": "cross-route",
        "reason": reason,
        "added_ts": now,
        "replay_n": int(replay_n),
        "replay_roi": round(float(replay_roi), 4),
    }
    if b_rec:
        entry["b_record"] = b_rec
    if watchlist_entry:
        for k in ("approved_categories", "median_usd", "flagged_by"):
            if watchlist_entry.get(k) is not None:
                entry[k] = watchlist_entry[k]
    targets.append(entry)
    _write_targets(extras_path, targets)
    why = ("replay-fit" if replay_fit else "B-record-fit")
    logger.info(f"[COPY-PAPER-B] cross-routed {w} to strategy B ({why}; {reason})")
    return True, why
