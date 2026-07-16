"""Restart-surviving queue of wallets whose LLM gate check was DEFERRED because
``claude -p`` was spend/rate-limited.

When the shortlist gate can't reach Claude because the subscription is limited,
the wallet is admitted to the paper watchlist *provisionally* (so we never lose
it) AND parked here with the dossier that was already built for it. Each
discovery sweep drains the queue: once the subscription is back, the check runs
on the stored dossier and the verdict is applied (a ``skip`` removes the
provisionally-admitted wallet; a ``follow``/``watch`` confirms it). Until then the
entry survives process restarts because it lives in a single JSON file.

State is one JSON file (path injected by the caller, like ``gate_history``)::

    {"pending": {"<wallet-lower>": {wallet, dossier, theories, had_leadlag,
                                    copy_n, ts}}}

Reads are mtime-cached; writes are atomic (tmp + replace) and lock-serialized,
matching ``late_bet_queue`` / ``promotion_state``. Pure and defensive: nothing
here raises into the sweep loop.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Optional

_LOCK = threading.RLock()
# path -> (mtime, parsed_dict). Invalidated when the file's mtime changes.
_CACHE: dict[str, tuple[float, dict]] = {}


def _read(path: str) -> dict:
    """Parse the queue JSON (mtime-cached). Always returns ``{"pending": {...}}``."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {"pending": {}}
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
    data = {"pending": pending if isinstance(pending, dict) else {}}
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


def enqueue(path: Optional[str], wallet: str, dossier: dict, *,
            theories=None, had_leadlag: bool = False, copy_n: int = 0,
            now: Optional[float] = None) -> bool:
    """Park a wallet whose gate check was deferred. Idempotent per wallet (a
    second enqueue refreshes the entry). Returns True on success, False on a
    missing path / bad wallet. Never raises."""
    if not path or not wallet:
        return False
    now = time.time() if now is None else now
    try:
        with _LOCK:
            data = _read(path)
            data["pending"][wallet.lower()] = {
                "wallet": wallet,
                "dossier": dossier,
                "theories": list(theories or []),
                "had_leadlag": bool(had_leadlag),
                "copy_n": int(copy_n or 0),
                "ts": float(now),
            }
            _write(path, data)
        return True
    except OSError:
        return False


def pending(path: Optional[str]) -> list[dict]:
    """All parked entries (each carries ``wallet`` + the stored ``dossier``)."""
    if not path:
        return []
    return list(_read(path)["pending"].values())


def bump_attempts(path: Optional[str], wallet: str) -> int:
    """Increment and return the entry's failed-re-check attempt count.

    Lets the drain loop bound how many sweeps a still-failing re-check may
    burn before it resolves as a visible unvetted admit (a parked wallet used
    to retry forever). Returns 0 for a missing path/entry. Never raises."""
    if not path or not wallet:
        return 0
    try:
        with _LOCK:
            data = _read(path)
            entry = data["pending"].get(wallet.lower())
            if entry is None:
                return 0
            entry["attempts"] = int(entry.get("attempts", 0) or 0) + 1
            _write(path, data)
            return entry["attempts"]
    except OSError:
        return 0


def remove(path: Optional[str], wallets) -> None:
    """Drop entries for the given wallets (after they've been re-checked)."""
    if not path:
        return
    keys = {(w or "").lower() for w in wallets}
    if not keys:
        return
    try:
        with _LOCK:
            data = _read(path)
            changed = False
            for k in keys:
                if k in data["pending"]:
                    del data["pending"][k]
                    changed = True
            if changed:
                _write(path, data)
    except OSError:
        pass
