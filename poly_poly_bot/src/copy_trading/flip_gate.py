"""A buy the target has already left is not traded (2026-09-24, part 2 D1).

Owner's rule: the Spain trade was a buy and a full sell one second apart
by the target; with ~30 s copy latency the bot bought into a position the
target had already left, could not follow them out, and ate the loss. Such
a trade is detected and refused, never copied, in preview and live alike.

Two sources, local first: every detected trade the pollers enqueue is
noted here per wallet (``note_detected``), so by the time the executor
reaches the BUY, the target's SELL of the same token is usually already on
record. When nothing newer than the buy is on record for that wallet, one
data-api ``/activity`` read (cached COPY_FLIP_FETCH_TTL_S per wallet) is
the fallback. ``sold / bought >= COPY_FLIP_EXIT_FRAC`` refuses the buy.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Optional

from src.config import CONFIG


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


FETCH_TTL_S = _env_f("COPY_FLIP_FETCH_TTL_S", 30.0)
KEEP_PER_WALLET = 300
_lock = threading.Lock()
_rows: dict[str, deque] = {}
_fetched: dict[str, tuple[float, list]] = {}


def _ts(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def note_detected(trader: str, token_id: str, side: str, shares: float, ts) -> None:
    """One row per detected trade, from every source, kept in memory."""
    w = (trader or "").lower()
    if not w or not token_id:
        return
    row = {"token": str(token_id), "side": str(side or "").upper(), "shares": float(shares or 0.0), "ts": _ts(ts)}
    with _lock:
        _rows.setdefault(w, deque(maxlen=KEEP_PER_WALLET)).append(row)


def local_rows(trader: str) -> list[dict]:
    with _lock:
        return list(_rows.get((trader or "").lower(), ()))


def clear() -> None:
    with _lock:
        _rows.clear()
        _fetched.clear()


def _fetch_activity(trader: str) -> Optional[list]:
    """The data-api's newest 50 rows for the wallet, as flip rows."""
    try:
        import requests

        from src.copy_trading.discovery_data import DATA_API, _get
        rows = _get(requests.Session(), DATA_API, "/activity", user=trader, limit=50)
    except Exception:  # noqa: BLE001
        return None
    if rows is None:
        return None
    out = []
    for a in rows:
        if a.get("type") != "TRADE":
            continue
        try:
            out.append({"token": str(a.get("asset") or ""), "side": str(a.get("side") or "").upper(),
                        "shares": float(a.get("size") or 0.0), "ts": float(a.get("timestamp") or 0)})
        except (TypeError, ValueError):
            continue
    return out


def _remote_rows(trader: str, now: float, fetch: Optional[Callable[[str], Optional[list]]]) -> Optional[list]:
    w = trader.lower()
    with _lock:
        hit = _fetched.get(w)
    if hit and now - hit[0] < FETCH_TTL_S:
        return hit[1]
    rows = (fetch or _fetch_activity)(trader)
    if rows is None:
        return None
    with _lock:
        _fetched[w] = (now, rows)
    return rows


def target_already_exited(trader: str, token_id: str, buy_ts, buy_shares: float, *,
                          now: Optional[float] = None, fetch: Optional[Callable] = None) -> tuple[bool, str]:
    """Did the target SELL this token after the buy we are about to copy?
    ``(exited, reason)``; the reason names the share sold and the delay."""
    now = time.time() if now is None else now
    if buy_shares <= 0 or not token_id:
        return (False, "")
    frac_bar = float(getattr(CONFIG, "copy_flip_exit_frac", 0.5) or 0.5)
    t0 = _ts(buy_ts)
    rows = local_rows(trader)
    newer = [r for r in rows if r["ts"] >= t0 - 1.0]
    if not any(r["token"] == str(token_id) and r["side"] == "SELL" for r in newer):
        # nothing newer on record for this wallet: one read, cached
        if not any(r["ts"] > t0 for r in rows):
            remote = _remote_rows(trader, now, fetch)
            if remote:
                newer = [r for r in remote if r["ts"] >= t0 - 1.0]
    sells = [r for r in newer if r["token"] == str(token_id) and r["side"] == "SELL"]
    if not sells:
        return (False, "")
    sold = sum(r["shares"] for r in sells)
    frac = sold / buy_shares
    if frac >= frac_bar:
        delay = max(0.0, max(r["ts"] for r in sells) - t0)
        return (True, f"target already sold {min(frac, 9.99):.0%} of this buy {delay:.0f}s later")
    return (False, "")


# --------------------------------------------------------------------------- #
# Their position before a sell (part 2 B): what share of it did they sell?
# --------------------------------------------------------------------------- #

def _fetch_positions(trader: str) -> Optional[list]:
    """The data-api's open positions for the wallet: ``(token, shares)`` rows."""
    try:
        import requests

        from src.copy_trading.discovery_data import DATA_API, _get
        rows = _get(requests.Session(), DATA_API, "/positions", user=trader, sizeThreshold=1, limit=500)
    except Exception:  # noqa: BLE001
        return None
    if rows is None:
        return None
    out = []
    for p in rows:
        try:
            out.append({"token": str(p.get("asset") or ""), "shares": float(p.get("size") or 0.0)})
        except (TypeError, ValueError):
            continue
    return out


def exit_share(trader: str, token_id: str, sold_shares: float, sell_ts, *, now: Optional[float] = None,
               fetch_positions: Optional[Callable] = None) -> tuple[Optional[float], str]:
    """The share of THEIR position the target sold: ``sold / held before``.
    Held-before from the local record (buys minus earlier sells of the
    token), else the data-api's current position plus the sale. None when
    nothing says (then the caller treats the sell as a full exit, the old
    behaviour, and says so)."""
    now = time.time() if now is None else now
    t0 = _ts(sell_ts)
    rows = [r for r in local_rows(trader) if r["token"] == str(token_id) and r["ts"] < t0 + 0.5]
    bought = sum(r["shares"] for r in rows if r["side"] == "BUY")
    sold_before = sum(r["shares"] for r in rows if r["side"] == "SELL" and r["ts"] < t0)
    held_before = bought - sold_before
    if held_before >= sold_shares > 0 and bought > 0:
        return (min(1.0, sold_shares / held_before), f"from the record: sold {sold_shares:.2f} of {held_before:.2f}")
    pos = (fetch_positions or _fetch_positions)(trader)
    if pos is None:
        return (None, "their position unknown")
    left = sum(p["shares"] for p in pos if p["token"] == str(token_id))
    before = left + sold_shares
    if before <= 0 or sold_shares <= 0:
        return (None, "their position unknown")
    return (min(1.0, sold_shares / before), f"from their positions: sold {sold_shares:.2f} of {before:.2f}")
