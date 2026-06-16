"""Market resolution lookup (Gamma API), cached to disk.

Several theories need to know *how a market settled* — which outcome resolved
YES and when — to judge whether a trade was right (1e longshot calibration) and
how early it was placed (1a). The Gamma `/markets?condition_ids=…` endpoint
returns `closed`, `outcomePrices` (which become `["1","0"]`/`["0","1"]` on
resolution), and `endDate`. Resolved markets never change, so they're cached
permanently on disk; unresolved markets return ``None`` (winning_index unknown).

Used by the backtest (to label historical trades) and optionally by the live
sweep (to enrich the deep-eval wallets' contexts).
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from src.copy_trading.wallet_context import MarketResolution

GAMMA_API = os.environ.get("GAMMA_API_URL", "https://gamma-api.polymarket.com")
_RESOLVED_PRICE = 0.99  # a resolved YES outcome prices ~1.0


def _parse_iso(s: str | None) -> float:
    if not s:
        return 0.0
    try:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return 0.0


def parse_resolution(market: dict) -> MarketResolution:
    """Reduce a Gamma market dict to a MarketResolution.

    winning_index is set only when the market is closed AND one outcome prices
    at ~1.0 (a clean YES/NO resolution); otherwise it's None (unknown/open).
    """
    end_ts = _parse_iso(market.get("endDate") or market.get("endDateIso"))
    if not market.get("closed"):
        return MarketResolution(winning_index=None, end_ts=end_ts)
    raw = market.get("outcomePrices") or []
    try:
        prices = [float(x) for x in (json.loads(raw) if isinstance(raw, str) else raw)]
    except (ValueError, TypeError):
        prices = []
    if not prices:
        return MarketResolution(winning_index=None, end_ts=end_ts)
    top = max(range(len(prices)), key=lambda i: prices[i])
    winning = top if prices[top] >= _RESOLVED_PRICE else None
    return MarketResolution(winning_index=winning, end_ts=end_ts)


def _get(session: requests.Session, condition_id: str) -> dict | None:
    for _ in range(3):
        try:
            r = session.get(GAMMA_API + "/markets",
                            params={"condition_ids": condition_id}, timeout=20)
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, list):
                    return j[0] if j else None
                return j if isinstance(j, dict) else None
            if 400 <= r.status_code < 500 and r.status_code != 429:
                return None
        except requests.RequestException:
            pass
        time.sleep(0.25)
    return None


def fetch_resolution(
    condition_id: str,
    cache_dir: str | None = None,
    session: requests.Session | None = None,
) -> MarketResolution | None:
    """One market's resolution, served from disk cache if a *resolved* result
    was stored (resolved markets are immutable). Returns None on fetch failure."""
    path = os.path.join(cache_dir, f"res_{condition_id}.json") if cache_dir else None
    if path and os.path.exists(path):
        try:
            d = json.load(open(path))
            return MarketResolution(winning_index=d.get("winning_index"),
                                    end_ts=float(d.get("end_ts") or 0.0))
        except (json.JSONDecodeError, OSError):
            pass
    market = _get(session or requests.Session(), condition_id)
    if market is None:
        return None
    res = parse_resolution(market)
    # only cache once actually resolved (open markets will change)
    if path and res.winning_index is not None:
        try:
            tmp = path + ".tmp"
            json.dump({"winning_index": res.winning_index, "end_ts": res.end_ts}, open(tmp, "w"))
            os.replace(tmp, path)
        except OSError:
            pass
    return res


def fetch_resolutions(
    condition_ids,
    cache_dir: str | None = None,
    workers: int = 8,
) -> dict[str, MarketResolution]:
    """Resolutions for many markets, concurrently; skips any that fail to fetch."""
    out: dict[str, MarketResolution] = {}
    cids = list(dict.fromkeys(condition_ids))  # dedupe, keep order
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_resolution, c, cache_dir): c for c in cids}
        for f in as_completed(futs):
            r = None
            try:
                r = f.result()
            except Exception:
                r = None
            if r is not None:
                out[futs[f]] = r
    return out
