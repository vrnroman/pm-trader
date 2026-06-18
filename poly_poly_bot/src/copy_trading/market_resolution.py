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
            # closed=true is REQUIRED: Gamma's /markets defaults to OPEN markets
            # only, so without it a resolved market returns nothing — which
            # silently starved every resolution lookup (theories 1a/1e + the
            # copy-replay gate) and preview realization. A still-open market just
            # isn't returned, which callers already treat as "unresolved".
            r = session.get(GAMMA_API + "/markets",
                            params={"condition_ids": condition_id, "closed": "true"},
                            timeout=20)
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


def fetch_market(condition_id: str, session: requests.Session | None = None) -> dict | None:
    """Return the raw Gamma market dict for a condition id (or None on failure).

    Unlike ``fetch_resolution`` this is uncached and exposes the full market —
    notably ``clobTokenIds`` and ``outcomePrices`` — which the preview realizer
    needs to map a held token to its outcome index and resolution. Resolved
    positions are dropped from inventory after first use, so re-fetching only
    ever hits still-open markets."""
    if not condition_id:
        return None
    return _get(session or requests.Session(), condition_id)


def _read_cache(condition_id: str, cache_dir: str | None) -> MarketResolution | None:
    if not cache_dir:
        return None
    path = os.path.join(cache_dir, f"res_{condition_id}.json")
    if os.path.exists(path):
        try:
            d = json.load(open(path))
            return MarketResolution(winning_index=d.get("winning_index"),
                                    end_ts=float(d.get("end_ts") or 0.0))
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _write_cache(condition_id: str, res: MarketResolution, cache_dir: str | None) -> None:
    if not cache_dir or res.winning_index is None:  # only cache immutable resolved markets
        return
    path = os.path.join(cache_dir, f"res_{condition_id}.json")
    try:
        tmp = path + ".tmp"
        json.dump({"winning_index": res.winning_index, "end_ts": res.end_ts}, open(tmp, "w"))
        os.replace(tmp, path)
    except OSError:
        pass


def _get_batch(session: requests.Session, cids: list[str]) -> list[dict]:
    """One Gamma call for up to ~50 markets (repeated condition_ids params)."""
    # closed=true is REQUIRED — see _get: without it Gamma returns only open
    # markets, so a batch of resolved condition_ids comes back empty.
    params = ([("condition_ids", c) for c in cids]
              + [("limit", str(len(cids))), ("closed", "true")])
    for _ in range(3):
        try:
            r = session.get(GAMMA_API + "/markets", params=params, timeout=30)
            if r.status_code == 200:
                j = r.json()
                return j if isinstance(j, list) else ([j] if isinstance(j, dict) else [])
            if 400 <= r.status_code < 500 and r.status_code != 429:
                return []
        except requests.RequestException:
            pass
        time.sleep(0.25)
    return []


def fetch_resolutions(
    condition_ids,
    cache_dir: str | None = None,
    workers: int = 8,
    batch_size: int = 50,
) -> dict[str, MarketResolution]:
    """Resolutions for many markets. Disk-cached resolved markets are read
    first; the rest are fetched in **batched** Gamma calls (one request per
    ``batch_size`` markets) across a thread pool — turning tens of thousands of
    per-market calls into hundreds. Markets that fail to fetch are skipped."""
    out: dict[str, MarketResolution] = {}
    misses: list[str] = []
    for c in dict.fromkeys(condition_ids):  # dedupe, keep order
        cached = _read_cache(c, cache_dir)
        if cached is not None:
            out[c] = cached
        else:
            misses.append(c)
    if not misses:
        return out

    batches = [misses[i:i + batch_size] for i in range(0, len(misses), batch_size)]

    def run(batch):
        markets = _get_batch(requests.Session(), batch)
        res: dict[str, MarketResolution] = {}
        for m in markets:
            cid = m.get("conditionId")
            if cid:
                res[cid] = parse_resolution(m)
        return res

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(run, b) for b in batches]):
            try:
                for cid, r in f.result().items():
                    out[cid] = r
                    _write_cache(cid, r, cache_dir)
            except Exception:
                pass
    return out
