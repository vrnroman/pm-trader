"""The exchange's fee on a token, read, never assumed.

A taker pays ``shares x rate x p x (1 - p)`` (docs.polymarket.com/trading/
fees), ``rate`` set per market. The rate is Gamma's ``feeSchedule.rate`` on
the market; the CLOB's ``/fee-rate`` answers its 1000-bps ceiling for every
market and is not what is charged (2026-10-05). ``fee_bps`` is that rate in
bps, cached on disk a day, None when it cannot be read: a fee we could not
read is never booked as zero by a caller that can say "unread".
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable, Optional

from src.config import CONFIG
from src.logger import logger

GAMMA_API_URL = "https://gamma-api.polymarket.com"
CACHE_FILE = "fee-rates-v2.json"
CACHE_TTL_S = 24 * 3600.0

_lock = threading.Lock()
_mem: dict = {}            # token_id -> (bps, ts)
_loaded = False
# Tests can hand the read in.
reader: Optional[Callable[[str], Optional[int]]] = None


def _path() -> str:
    return os.path.join(CONFIG.data_dir, CACHE_FILE)


def rate_bps_from_market(row: dict) -> Optional[int]:
    """The taker rate in bps from one Gamma market row; None when the row
    does not say. Fees switched off on the market read as 0."""
    if not isinstance(row, dict):
        return None
    if row.get("feesEnabled") is False:
        return 0
    sched = row.get("feeSchedule")
    if not isinstance(sched, dict) or sched.get("rate") is None:
        return None
    try:
        rate = float(sched["rate"])
    except (TypeError, ValueError):
        return None
    if rate < 0 or rate >= 1:
        return None
    return int(round(rate * 10000))


def _rows(payload) -> list[dict]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [r for r in payload["data"] if isinstance(r, dict)]
    return []


def _row_tokens(row: dict) -> list[str]:
    raw = row.get("clobTokenIds") or row.get("clob_token_ids") or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = []
    return [str(t) for t in raw or []]


def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, dict) and "bps" in v:
                    _mem[str(k)] = (int(v["bps"]), float(v.get("ts") or 0.0))
    except (OSError, ValueError, TypeError):
        pass


def _save() -> None:
    try:
        os.makedirs(CONFIG.data_dir, exist_ok=True)
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({k: {"bps": b, "ts": t} for k, (b, t) in _mem.items()}, f)
        os.replace(tmp, _path())
    except OSError as exc:
        logger.warn(f"[fee] cache write failed: {exc}")


def _read_from_exchange(token_id: str) -> Optional[int]:
    """One Gamma lookup (open markets, then closed); None on any failure."""
    if reader is not None:
        try:
            return reader(token_id)
        except Exception as exc:  # noqa: BLE001
            logger.warn(f"[fee] injected reader failed for {str(token_id)[:12]}: {exc}")
            return None
    try:
        import httpx
        with httpx.Client(timeout=5.0) as client:
            for params in ({"clob_token_ids": token_id}, {"clob_token_ids": token_id, "closed": "true"}):
                resp = client.get(f"{GAMMA_API_URL}/markets", params=params)
                resp.raise_for_status()
                for row in _rows(resp.json()):
                    if str(token_id) in _row_tokens(row):
                        return rate_bps_from_market(row)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warn(f"[fee] rate unread for {str(token_id)[:12]}: {exc}")
        return None


def fee_bps(token_id: str, now: Optional[float] = None) -> Optional[int]:
    """The market's taker fee rate on ``token_id`` in bps, or None when it
    cannot be read. Cached a day per token, on disk."""
    tok = str(token_id or "")
    if not tok:
        return None
    now = time.time() if now is None else now
    with _lock:
        _load()
        hit = _mem.get(tok)
        if hit is not None and now - hit[1] < CACHE_TTL_S:
            return hit[0]
    v = _read_from_exchange(tok)
    if v is None:
        return hit[0] if hit is not None else None
    with _lock:
        _mem[tok] = (int(v), now)
        _save()
    return int(v)


def reset_for_tests() -> None:
    global _loaded
    with _lock:
        _mem.clear()
        _loaded = False
