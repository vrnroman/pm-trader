"""The exchange's fee on a token, read, never assumed (run s-k7m2qa).

``copy_cost.py`` opens with "on Polymarket the trading fee is ~0". That was
true when it was written and is not any more: a taker pays
``shares x rate x p x (1 - p)`` in USDC (docs.polymarket.com/trading/fees),
with ``rate`` set per market (politics 0.04, sports 0.03-0.05, some 0).

Where the rate comes from (2026-10-05): the first version read the CLOB's
``/fee-rate`` and charged it as a flat share of the stake. That endpoint
answers ``{"base_fee": 1000}`` for EVERY market, zero-fee ones included: it is
the ceiling the order may carry, not what is charged. The phone read
"fee 10.0%" on every fill. The real rate is Gamma's ``feeSchedule.rate`` on
the market (``/markets?clob_token_ids=``), and it is curved by the price: as
a share of the dollars a BUY spends it is ``rate x (1 - p)``, so a 0.80 buy
on a 0.03 market pays 0.6%, not 10%. The 10-01 Safiullin fill checks it:
13.33 shares at 0.48 on a 0.05 market is 13.33 x 0.05 x 0.48 x 0.52 = $0.17,
and $6.56 was paid on a $6.40 order.

``fee_bps`` is that market rate in bps (300 for 0.03), cached on disk for a
day (a market's fee does not change inside one), None when it cannot be read,
so every caller falls back to what it did before: a fee we could not read is
never a fee of zero on the phone, it is "fee unread". ``fee_share`` turns it
into the share of a BUY's dollars at a price; every caller goes through it.

Three callers: the tier price ceiling (fee-aware: what a dollar of the token
really costs), the paper books' modeled cost (forward only; old rows keep what
they were stamped with), and the deal line on the phone (what a win nets after
the fee, and the break-even win rate).
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable, Optional

from src.config import CONFIG
from src.logger import logger

# v2: the v1 file holds the CLOB's 1000-bps ceiling for every token; never
# read it back as a rate.
CACHE_FILE = "fee-rates-v2.json"
CACHE_TTL_S = 24 * 3600.0

_lock = threading.Lock()
_mem: dict = {}            # token_id -> (bps, ts)
_loaded = False
# Tests and callers that already hold a client can hand the read in.
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
        from src.copy_trading.market_cache import GAMMA_API_URL, _query_variants, _rows, _row_tokens
        with httpx.Client(timeout=5.0) as client:
            for params in _query_variants(token_id):
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
    """The market's taker fee rate on ``token_id`` in bps (``fee_share``
    turns it into dollars), or None when it cannot be read.
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


def fee_share(price: float, bps: Optional[int]) -> float:
    """The fee as a share of the dollars a BUY at ``price`` spends:
    ``shares x rate x p x (1 - p)`` over ``shares x p`` is ``rate x (1 - p)``."""
    if bps is None or bps <= 0:
        return 0.0
    p = min(max(float(price), 0.0), 1.0)
    return bps / 10000.0 * (1.0 - p)


def effective_price(price: float, bps: Optional[int]) -> float:
    """What a dollar of the token really costs: the price plus the fee."""
    return float(price) * (1.0 + fee_share(price, bps))


def break_even(price: float, bps: Optional[int], stake_usd: float) -> dict:
    """What a win nets on ``stake_usd`` at ``price`` after the fee, and the
    win rate that breaks even. ``bps`` None reads as unread (0 charged, said)."""
    p = float(price)
    if p <= 0:
        return {"paid": stake_usd, "payout": 0.0, "net": -stake_usd, "be_win": 1.0,
                "fee_usd": 0.0, "fee_share": 0.0, "fee_bps": bps}
    f = fee_share(p, bps)
    shares = stake_usd / p
    fee_usd = stake_usd * f
    paid = stake_usd + fee_usd
    return {"paid": round(paid, 2), "payout": round(shares, 2), "net": round(shares - paid, 2),
            "be_win": min(1.0, p * (1.0 + f)), "fee_usd": round(fee_usd, 2), "fee_share": f,
            "fee_bps": bps}


def break_even_line(price: float, bps: Optional[int], stake_usd: float) -> str:
    b = break_even(price, bps, stake_usd)
    if bps is None:
        fee = "fee unread"
    elif bps <= 0:
        fee = "no fee"
    else:
        fee = f"fee ${b['fee_usd']:.2f} = {b['fee_share'] * 100:.1f}%"
    return (f"a win nets {b['net']:+.2f} on ${b['paid']:.2f} paid ({fee}); "
            f"break-even {b['be_win'] * 100:.0f}% win rate")


def reset_for_tests() -> None:
    global _loaded
    with _lock:
        _mem.clear()
        _loaded = False
