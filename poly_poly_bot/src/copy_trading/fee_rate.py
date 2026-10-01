"""The exchange's fee on a token, read, never assumed (run s-k7m2qa).

``copy_cost.py`` opens with "on Polymarket the trading fee is ~0". That was
true when it was written and is not any more: our own 65 real BUY fills show
a median 2.1% (max 4%) taker charge on sports markets (a $6.40 order paid
$6.56) and zero on weather markets. The paper books charged 0 bps, so a
sports wallet's paper ROI read about two points better than real money
would have kept; the price ceiling (0.90) was set with no fee behind it, so
at 0.90 on a 2.5%-fee market the break-even win rate is 92%, not 90%.

The CLOB publishes the rate per token (``GET /fee-rate?token_id=``, public,
no credentials). This leaf reads it through the same client the executor
uses, caches it on disk for a day (a market's fee does not change inside
one), and answers None when it cannot read, so every caller falls back to
what it did before: a fee we could not read is never a fee of zero on the
phone, it is "fee unread".

Three callers: the tier price ceiling (fee-aware: the price the exchange
really charges is price times one plus the fee), the paper books' modeled
cost (the live rate per copy from the day this shipped, forward only; old
rows keep what they were stamped with), and the deal line on the phone
(what a win nets after the fee, and the break-even win rate).
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable, Optional

from src.config import CONFIG
from src.logger import logger

CACHE_FILE = "fee-rates.json"
CACHE_TTL_S = 24 * 3600.0

_lock = threading.Lock()
_mem: dict = {}            # token_id -> (bps, ts)
_loaded = False
_client = None
# Tests and callers that already hold a client can hand the read in.
reader: Optional[Callable[[str], Optional[int]]] = None


def _path() -> str:
    return os.path.join(CONFIG.data_dir, CACHE_FILE)


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
    """One public GET; None on any failure."""
    global _client
    if reader is not None:
        try:
            return reader(token_id)
        except Exception as exc:  # noqa: BLE001
            logger.warn(f"[fee] injected reader failed for {str(token_id)[:12]}: {exc}")
            return None
    try:
        if _client is None:
            from py_clob_client_v2.client import ClobClient
            _client = ClobClient(CONFIG.clob_api_url, chain_id=CONFIG.chain_id)
        v = _client.get_fee_rate_bps(token_id)
        return int(v) if v is not None else None
    except Exception as exc:  # noqa: BLE001
        logger.warn(f"[fee] rate unread for {str(token_id)[:12]}: {exc}")
        return None


def fee_bps(token_id: str, now: Optional[float] = None) -> Optional[int]:
    """The taker fee on ``token_id`` in bps, or None when it cannot be read.
    Cached a day per token, on disk, so a restart does not re-ask."""
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
        # A stale cached value beats nothing: the fee did not change because
        # the read failed.
        return hit[0] if hit is not None else None
    with _lock:
        _mem[tok] = (int(v), now)
        _save()
    return int(v)


def effective_price(price: float, bps: Optional[int]) -> float:
    """What a dollar of the token really costs: the price plus the fee."""
    if bps is None or bps <= 0:
        return float(price)
    return float(price) * (1.0 + bps / 10000.0)


def break_even(price: float, bps: Optional[int], stake_usd: float) -> dict:
    """What a win nets on ``stake_usd`` at ``price`` after the fee, and the
    win rate that breaks even. ``bps`` None reads as unread (0 charged, said)."""
    p = float(price)
    f = (bps or 0) / 10000.0
    if p <= 0:
        return {"paid": stake_usd, "payout": 0.0, "net": -stake_usd, "be_win": 1.0, "fee_bps": bps}
    shares = stake_usd / p
    paid = stake_usd * (1.0 + f)
    return {"paid": round(paid, 2), "payout": round(shares, 2), "net": round(shares - paid, 2),
            "be_win": min(1.0, p * (1.0 + f)), "fee_bps": bps}


def break_even_line(price: float, bps: Optional[int], stake_usd: float) -> str:
    b = break_even(price, bps, stake_usd)
    fee = "fee unread" if bps is None else ("no fee" if bps <= 0 else f"fee {bps / 100:.1f}%")
    return (f"a win nets {b['net']:+.2f} on ${b['paid']:.2f} paid ({fee}); "
            f"break-even {b['be_win'] * 100:.0f}% win rate")


def reset_for_tests() -> None:
    global _loaded, _client
    with _lock:
        _mem.clear()
        _loaded = False
        _client = None
