"""Runtime stores for paper-copy governance — promoted wallets + blacklist.

Three small JSON files in the data dir, read on hot paths (detection routing,
discovery gating) and written from the Telegram thread (a one-tap promote) and
the copy-paper thread (an auto-demote). Kept dependency-light (stdlib + CONFIG
for the data dir) so ``strategy_config`` / ``trade_monitor`` can import it
without pulling in the heavier P&L / engine modules.

  * **promoted_wallets.json** — wallets the owner promoted to System A via the
    Telegram offer. Merged into ``get_all_tiered_wallets`` / ``get_wallet_tier``
    and the monitored-address set so a promotion takes effect on the next
    detection poll WITHOUT a restart — i.e. it behaves exactly like adding the
    wallet to ``STRATEGY_1B_WALLETS``, except dynamic. Still PREVIEW-gated: no
    real money moves until ``PREVIEW_MODE`` is turned off.
  * **copy_blacklist.json** — wallets auto-demoted (proven-negative copy ROI on
    enough resolved paper copies). Excluded from the watchlist + re-qualification
    for a cooldown window so a bad wallet can't squat a slot or keep coming back.
  * **promotion_offers.json** — which wallets have already been offered for
    promotion (and whether accepted/dismissed), so the offer fires once.

Reads are cached by file mtime so the per-trade routing path costs a ``stat``,
not a parse. Writes are atomic (tmp + replace) and serialized by a lock, so the
Telegram thread and the copy-paper thread can't clobber each other's updates.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Optional

from src.config import CONFIG

# Valid System-A tiers a wallet can be promoted into.
VALID_TIERS = ("1a", "1b")

_LOCK = threading.RLock()
# path -> (mtime, parsed_dict). Invalidated when the file's mtime changes.
_CACHE: dict[str, tuple[float, dict]] = {}


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

def _data_path(env_key: str, filename: str) -> str:
    override = os.environ.get(env_key, "").strip()
    return override or os.path.join(CONFIG.data_dir, filename)


def promoted_path() -> str:
    return _data_path("PROMOTED_WALLETS_STORE", "promoted_wallets.json")


def blacklist_path() -> str:
    return _data_path("COPY_BLACKLIST_STORE", "copy_blacklist.json")


def offers_path() -> str:
    return _data_path("PROMOTION_OFFERS_STORE", "promotion_offers.json")


# --------------------------------------------------------------------------- #
# Low-level cached read / atomic write
# --------------------------------------------------------------------------- #

def _read(path: str) -> dict:
    """Parse a JSON dict, served from an mtime-keyed cache. {} on missing/corrupt."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
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
# Promoted wallets
# --------------------------------------------------------------------------- #

def promoted_map() -> dict:
    """Lowercased-wallet -> record ({wallet, tier, ts, source})."""
    return _read(promoted_path())


def promoted_wallets() -> list[str]:
    """Original-case addresses of all promoted wallets (for detection/fetch)."""
    return [rec.get("wallet") or w for w, rec in promoted_map().items()]


def promoted_set() -> set[str]:
    """Lowercased set of promoted wallets (membership tests)."""
    return set(promoted_map().keys())


def promoted_tier_of(wallet: str) -> Optional[str]:
    """The tier a wallet was promoted into, or None if not promoted."""
    rec = promoted_map().get((wallet or "").lower())
    return rec.get("tier") if rec else None


def add_promoted(wallet: str, tier: str = "1b", source: str = "telegram",
                 now: Optional[float] = None) -> dict:
    """Promote a wallet into a System-A tier at runtime. Idempotent (re-promoting
    updates the tier/timestamp). Returns the stored record. Tier is validated."""
    wallet = (wallet or "").strip()
    if not wallet:
        raise ValueError("empty wallet")
    tier = (tier or "1b").lower()
    if tier not in VALID_TIERS:
        raise ValueError(f"invalid tier {tier!r} (expected one of {VALID_TIERS})")
    rec = {
        "wallet": wallet,
        "tier": tier,
        "ts": now if now is not None else time.time(),
        "source": source,
    }
    with _LOCK:
        data = dict(_read(promoted_path()))
        data[wallet.lower()] = rec
        _write(promoted_path(), data)
    return rec


def remove_promoted(wallet: str) -> bool:
    """Drop a wallet from the promoted store. Returns True if it was present."""
    key = (wallet or "").lower()
    with _LOCK:
        data = dict(_read(promoted_path()))
        if key not in data:
            return False
        del data[key]
        _write(promoted_path(), data)
    return True


# --------------------------------------------------------------------------- #
# Blacklist (auto-demoted wallets)
# --------------------------------------------------------------------------- #

def blacklist_map() -> dict:
    """Lowercased-wallet -> record ({wallet, until, reason, ts, n_closed, roi})."""
    return _read(blacklist_path())


def is_blacklisted(wallet: str, now: Optional[float] = None) -> bool:
    """True if the wallet is under an active (non-expired) demotion cooldown."""
    rec = blacklist_map().get((wallet or "").lower())
    if not rec:
        return False
    now = now if now is not None else time.time()
    until = float(rec.get("until") or 0.0)
    return until <= 0.0 or now < until   # until<=0 means permanent


def active_blacklist(now: Optional[float] = None) -> set[str]:
    """Lowercased set of wallets currently within their demotion cooldown."""
    now = now if now is not None else time.time()
    out: set[str] = set()
    for w, rec in blacklist_map().items():
        until = float(rec.get("until") or 0.0)
        if until <= 0.0 or now < until:
            out.add(w)
    return out


def add_blacklist(wallet: str, *, until: float, reason: str = "",
                  n_closed: int = 0, roi: float = 0.0,
                  now: Optional[float] = None) -> dict:
    """Blacklist a wallet until ``until`` (unix secs; <=0 = permanent)."""
    wallet = (wallet or "").strip()
    if not wallet:
        raise ValueError("empty wallet")
    rec = {
        "wallet": wallet,
        "until": float(until),
        "reason": reason,
        "ts": now if now is not None else time.time(),
        "n_closed": int(n_closed),
        "roi": round(float(roi), 4),
    }
    with _LOCK:
        data = dict(_read(blacklist_path()))
        data[wallet.lower()] = rec
        _write(blacklist_path(), data)
    return rec


# --------------------------------------------------------------------------- #
# Promotion offers (dedupe so a wallet is offered once)
# --------------------------------------------------------------------------- #

def offers_map() -> dict:
    """Lowercased-wallet -> offer record ({wallet, status, ts, n_closed, roi})."""
    return _read(offers_path())


def record_offer(wallet: str, *, status: str, n_closed: int = 0, roi: float = 0.0,
                 now: Optional[float] = None) -> dict:
    """Persist an offer's state ('offered' | 'accepted' | 'dismissed')."""
    wallet = (wallet or "").strip()
    rec = {
        "wallet": wallet,
        "status": status,
        "ts": now if now is not None else time.time(),
        "n_closed": int(n_closed),
        "roi": round(float(roi), 4),
    }
    with _LOCK:
        data = dict(_read(offers_path()))
        data[wallet.lower()] = rec
        _write(offers_path(), data)
    return rec


def offer_status(wallet: str) -> Optional[str]:
    rec = offers_map().get((wallet or "").lower())
    return rec.get("status") if rec else None
