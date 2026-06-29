"""Late-bet lead queue — resolution-gated wallet discovery (Strategy 1c → 1b bridge).

A large geopolitical BUY placed close to resolution, in the copyable price band
(``price < near_cert_buy_price``), is a *candidate* informed wallet — but a
single bet is luck-or-skill ambiguous. So instead of trusting the bet, we PARK
the wallet in a pending queue keyed to that market's resolution, then wait:

  * the market resolves in the wallet's favour  → the wallet becomes an *eval
    seed*: force-included in the next discovery sweep so it gets the full
    statistical funnel (closed-position ROI / t-stat / lead-lag) AND the Claude
    copyability gate before it can ever reach the paper watchlist.
  * the market resolves against the wallet       → dropped (the bet was wrong).
  * the market never cleanly resolves within the max-wait window → dropped.

This is the bridge between the event-driven pattern detector (which sees the
bet) and the wallet-quality discovery funnel (which decides whether the wallet
is worth copying). It deliberately holds NO opinion on copyability itself — it
only narrows leads to "placed a big late bet AND was right" and hands the
survivors to the existing eval machinery.

State lives in one JSON file (``data/late_bet_queue.json``)::

    {"pending": {"<wallet>:<cid>:<token_id>": {entry}}, "eval_seeds": ["0x..."]}

Reads are mtime-cached; writes are atomic (tmp + replace) and lock-serialized,
matching ``promotion_state``. ``fetch_market`` / ``classify`` are injectable so
the test suite never hits the network.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable, Optional

from src.config import CONFIG
from src.copy_trading.strategy_config import TIER_1C
from src.logger import logger

_LOCK = threading.RLock()
# path -> (mtime, parsed_dict). Invalidated when the file's mtime changes.
_CACHE: dict[str, tuple[float, dict]] = {}


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

def queue_path() -> str:
    override = os.environ.get("LATE_BET_QUEUE_STORE", "").strip()
    return override or os.path.join(CONFIG.data_dir, "late_bet_queue.json")


# --------------------------------------------------------------------------- #
# Low-level cached read / atomic write
# --------------------------------------------------------------------------- #

def _read(path: str) -> dict:
    """Parse the queue JSON, served from an mtime-keyed cache.

    Always returns a dict with ``pending`` (dict) and ``eval_seeds`` (list)
    keys so callers never have to guard for missing/corrupt state.
    """
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {"pending": {}, "eval_seeds": []}
    cached = _CACHE.get(path)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (json.JSONDecodeError, OSError):
        data = {}
    pending = data.get("pending")
    seeds = data.get("eval_seeds")
    data = {
        "pending": pending if isinstance(pending, dict) else {},
        "eval_seeds": seeds if isinstance(seeds, list) else [],
    }
    _CACHE[path] = (mtime, data)
    return data


def _write(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
    try:
        _CACHE[path] = (os.path.getmtime(path), data)
    except OSError:
        _CACHE.pop(path, None)


def clear_cache() -> None:
    """Drop the mtime cache (tests; or after an external file edit)."""
    with _LOCK:
        _CACHE.clear()


# --------------------------------------------------------------------------- #
# Pending leads
# --------------------------------------------------------------------------- #

def _pending_key(wallet: str, condition_id: str, token_id: str) -> str:
    return f"{wallet.lower()}:{condition_id}:{token_id}"


def enqueue_lead(
    *,
    wallet: str,
    condition_id: str,
    token_id: str,
    market: str,
    outcome: str,
    price: float,
    size: float,
    end_ts: float,
    now: Optional[float] = None,
) -> bool:
    """Park a late-bet lead until its market resolves. Returns True if newly
    added, False if this (wallet, market, outcome) is already pending.

    ``token_id`` is required — it's how ``process_resolutions`` later decides
    whether the bet won (via ``preview_resolver.classify_position``). A lead
    with no token id can't be resolution-checked, so it's rejected.
    """
    if not wallet or not condition_id or not token_id:
        return False
    now = time.time() if now is None else now
    key = _pending_key(wallet, condition_id, token_id)
    with _LOCK:
        path = queue_path()
        data = _read(path)
        if key in data["pending"]:
            return False
        data["pending"][key] = {
            "wallet": wallet,
            "condition_id": condition_id,
            "token_id": token_id,
            "market": market,
            "outcome": outcome,
            "price": float(price),
            "size": float(size),
            "end_ts": float(end_ts),
            "enqueued_ts": float(now),
        }
        _write(path, data)
    hrs = max(0.0, (end_ts - now) / 3600.0)
    logger.info(
        f"[late-bet] queued lead {wallet[:10]} on {(market or condition_id)[:48]} "
        f"@ {price:.3f} (${size:.0f}), resolves in {hrs:.1f}h"
    )
    return True


def pending() -> list[dict]:
    """All currently-parked leads (awaiting resolution)."""
    return list(_read(queue_path())["pending"].values())


# --------------------------------------------------------------------------- #
# Eval seeds (resolution-validated winners → next discovery sweep)
# --------------------------------------------------------------------------- #

def eval_seeds() -> list[str]:
    """Wallets that won their late bet and are queued to be force-scored by the
    next discovery sweep. Peek only — call ``clear_eval_seeds`` once consumed."""
    return list(_read(queue_path())["eval_seeds"])


def clear_eval_seeds() -> None:
    """Drop all eval seeds (after a discovery sweep has consumed them)."""
    with _LOCK:
        path = queue_path()
        data = _read(path)
        if data["eval_seeds"]:
            data["eval_seeds"] = []
            _write(path, data)


def _default_fetch_market(condition_id: str) -> Optional[dict]:
    # Imported lazily so the queue module stays import-light (and tests that
    # inject a fake fetcher never pull in requests / the network layer).
    from src.copy_trading.market_resolution import fetch_market
    return fetch_market(condition_id)


def _default_classify(market: Optional[dict], token_id: str) -> Optional[bool]:
    from src.copy_trading.preview_resolver import classify_position
    return classify_position(market, token_id)


def process_resolutions(
    now: Optional[float] = None,
    *,
    fetch_market: Callable[[str], Optional[dict]] = _default_fetch_market,
    classify: Callable[[Optional[dict], str], Optional[bool]] = _default_classify,
    max_wait_s: Optional[float] = None,
) -> dict:
    """Resolve every *matured* pending lead and route it.

    For each lead whose market end time has passed:
      * won  → wallet added to ``eval_seeds`` (deduped), lead removed.
      * lost → lead removed.
      * still unresolved (Gamma resolution lag) → kept, unless it has waited
        longer than ``max_wait_s`` past its end time, in which case it's
        expired and removed so a never-resolving market can't squat the queue.

    Leads whose market hasn't reached its end time yet are left untouched.
    Returns a counts dict ``{"won","lost","expired","kept","seeded"}``.
    """
    now = time.time() if now is None else now
    if max_wait_s is None:
        max_wait_s = TIER_1C.late_lead_max_resolution_wait_days * 86400.0
    counts = {"won": 0, "lost": 0, "expired": 0, "kept": 0, "seeded": 0}
    with _LOCK:
        path = queue_path()
        data = _read(path)
        if not data["pending"]:
            return counts
        # copy the seed list so the dedup check sees in-progress additions too
        seeds = list(data["eval_seeds"])
        seen = {w.lower() for w in seeds}
        survivors: dict[str, dict] = {}
        changed = False
        for key, entry in data["pending"].items():
            end_ts = float(entry.get("end_ts") or 0.0)
            if end_ts <= 0 or now < end_ts:
                survivors[key] = entry          # not matured yet
                counts["kept"] += 1
                continue
            wallet = entry.get("wallet", "")
            token_id = entry.get("token_id", "")
            won: Optional[bool] = None
            try:
                market = fetch_market(entry.get("condition_id", ""))
                won = classify(market, token_id)
            except Exception:  # pragma: no cover - network/parse defensive
                logger.warning(f"[late-bet] resolution lookup failed for {key}")
                won = None
            market_label = (entry.get("market") or "")[:48]
            if won is True:
                changed = True
                counts["won"] += 1
                if wallet.lower() not in seen:
                    seeds.append(wallet)
                    seen.add(wallet.lower())
                    counts["seeded"] += 1
                logger.info(f"[late-bet] WON → eval seed: {wallet[:10]} on {market_label}")
            elif won is False:
                changed = True
                counts["lost"] += 1
                logger.info(f"[late-bet] lost, dropped: {wallet[:10]} on {market_label}")
            else:
                # closed-but-unresolved or fetch failure — keep until it either
                # resolves or ages out of the wait window.
                if now - end_ts > max_wait_s:
                    changed = True
                    counts["expired"] += 1
                    logger.info(
                        f"[late-bet] expired (no resolution in "
                        f"{max_wait_s / 86400.0:.0f}d): {wallet[:10]}"
                    )
                else:
                    survivors[key] = entry
                    counts["kept"] += 1
        if changed:
            data["pending"] = survivors
            data["eval_seeds"] = seeds
            _write(path, data)
    return counts
