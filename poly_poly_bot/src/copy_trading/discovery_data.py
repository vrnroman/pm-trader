"""Runtime data layer for continuous wallet discovery.

Network IO tuned for an always-on loop (rather than a one-shot backtest):
  * TTL-cached wallet activity on disk, so each sweep sees fresh trades without
    re-pulling everything every time;
  * bounded concurrency so discovery never starves the trading threads;
  * shutdown-aware so a stop request doesn't wait out a full sweep.

Pure analysis is reused from ``trader_scoring`` and ``lead_lag``; this module
only fetches and assembles ``Eval`` rows for ``discovery.run_discovery_cycle``.
"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from src.copy_trading.discovery import DiscoveryConfig, Eval
from src.copy_trading.lead_lag import WalletLeadLag, analyze_buy
from src.copy_trading.trader_scoring import compute_wallet_metrics, select_targets

DATA_API = os.environ.get("DATA_API_URL", "https://data-api.polymarket.com")
CLOB = "https://clob.polymarket.com"
HISTORY_RETENTION_DAYS = 31  # CLOB price-history rolling window


def _stopping(ev: threading.Event | None) -> bool:
    return ev is not None and ev.is_set()


def _sleep_unless_stopped(ev: threading.Event | None, secs: float) -> None:
    """Pace the sweep without sleeping through a shutdown request.

    Used to space out the many requests of a wide (200k-wallet) scan so we stay
    under the data-API 429 ceiling. Returns immediately if the stop event fires,
    so a deploy/shutdown doesn't have to wait out a pacing pause."""
    if secs <= 0:
        return
    if ev is not None:
        ev.wait(secs)
    else:
        time.sleep(secs)


def _get(session, base, path, **params):
    for _ in range(4):
        try:
            r = session.get(base + path, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(1.0)
        except requests.RequestException:
            pass
        time.sleep(0.25)
    return None


# ─── universe ────────────────────────────────────────────────────────────────
def build_universe(
    target: int,
    min_amounts=(3000, 1200, 500, 250, 100),
    max_offset: int | None = None,
    page_pause_s: float | None = None,
) -> list[str]:
    """Active taker wallets from the recent trade feed.

    For a *wide* insider sweep, pass a large ``target`` (e.g. 200k): we page each
    stake tier — high tiers first, so the strongest wallets seed the set — until
    the tier runs dry, the per-tier offset budget (``max_offset``) is exhausted,
    or we've collected ``target`` unique wallets, then take whatever we found.
    Lower tiers (down to $100) widen the net to catch insiders placing modest
    bets, not just whales. A short ``page_pause_s`` between pages keeps these
    long deep-paging runs under the data-API 429 ceiling.
    """
    if max_offset is None:
        max_offset = int(os.environ.get("WALLET_DISCOVERY_UNIVERSE_MAX_OFFSET", "100000"))
    if page_pause_s is None:
        page_pause_s = float(os.environ.get("WALLET_DISCOVERY_PAGE_PAUSE_S", "0.3"))
    s = requests.Session()
    seen: set[str] = set()
    for amt in min_amounts:
        off = 0
        while off < max_offset and len(seen) < target:
            tr = _get(s, DATA_API, "/trades", limit=500, offset=off,
                      filterType="CASH", filterAmount=amt, takerOnly="true")
            if not tr:
                break
            for t in tr:
                w = t.get("proxyWallet")
                if w:
                    seen.add(w)
            off += 500
            if len(tr) < 500:
                break  # tier exhausted — no point paging an empty offset
            if page_pause_s > 0:
                time.sleep(page_pause_s)
    return list(seen)[:target]


# ─── activity (TTL-cached) ───────────────────────────────────────────────────
def fetch_activity(wallet: str, cache_dir: str | None, ttl_s: float, cap: int = 4000) -> list[dict]:
    """Wallet activity, served from disk cache if younger than ``ttl_s``."""
    path = os.path.join(cache_dir, f"{wallet}.json") if cache_dir else None
    if path and os.path.exists(path):
        try:
            if (time.time() - os.path.getmtime(path)) < ttl_s:
                return json.load(open(path))
        except (json.JSONDecodeError, OSError):
            pass
    s = requests.Session()
    acts: list[dict] = []
    off = 0
    while off < cap:
        a = _get(s, DATA_API, "/activity", user=wallet, limit=500, offset=off)
        if not a:
            break
        acts += a
        off += 500
        if len(a) < 500:
            break
    if path:
        try:
            tmp = path + ".tmp"
            json.dump(acts, open(tmp, "w"))
            os.replace(tmp, path)
        except OSError:
            pass
    return acts


def fetch_all_activity(wallets, cache_dir, ttl_s, workers=8, stop=None) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_activity, w, cache_dir, ttl_s): w for w in wallets}
        for f in as_completed(futs):
            if _stopping(stop):
                break
            try:
                out[futs[f]] = f.result() or []
            except Exception:
                out[futs[f]] = []
    return out


# ─── lead-lag copyability ────────────────────────────────────────────────────
def fetch_recent_buys(wallet: str, since_ts: float, min_usd: float) -> list[dict]:
    s = requests.Session()
    out, offset = [], 0
    while offset < 1500:
        acts = _get(s, DATA_API, "/activity", user=wallet, limit=500, offset=offset)
        if not acts:
            break
        stop = False
        for a in acts:
            ts = float(a.get("timestamp") or 0)
            if ts < since_ts:
                stop = True
                continue
            if a.get("type") != "TRADE" or a.get("side") != "BUY":
                continue
            price = float(a.get("price") or 0)
            if not (0.05 <= price <= 0.95):
                continue
            usd = float(a.get("usdcSize") or 0) or float(a.get("size") or 0) * price
            if usd < min_usd:
                continue
            token = a.get("asset") or ""
            if token:
                out.append({"token": token, "ts": ts, "price": price, "usd": usd})
        if stop or len(acts) < 500:
            break
        offset += 500
    return out


def fetch_price_series(token: str, cache: dict) -> list[tuple[float, float]]:
    if token in cache:
        return cache[token]
    s = requests.Session()
    j = _get(s, CLOB, "/prices-history", market=token, interval="max", fidelity=10)
    series = []
    for pt in (j or {}).get("history", []) or []:
        t, p = pt.get("t"), pt.get("p")
        if t is not None and p is not None:
            series.append((float(t), float(p)))
    series.sort()
    cache[token] = series
    return series


def lead_lag_wallet(buys, delay_s, horizon_s, price_cache) -> WalletLeadLag:
    w = WalletLeadLag()
    tokens = {b["token"] for b in buys}
    series_by_token: dict[str, list] = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(fetch_price_series, t, price_cache): t for t in tokens}
        for f in as_completed(futs):
            series_by_token[futs[f]] = f.result()
    for b in buys:
        series = series_by_token.get(b["token"])
        if not series:
            continue
        r = analyze_buy(series, b["ts"], delay_s=delay_s, horizon_s=horizon_s)
        if r is not None:
            w.add(r, side_sign=1)
    return w


# ─── full sweep: universe -> skill -> copyability -> Eval rows ────────────────
def _merge_topk(pool: list, chunk_scored: dict, cfg: DiscoveryConfig) -> list:
    """Fold a chunk's scored wallets into the running top-K skill pool.

    ``pool`` is the prior winners (RankedMetrics). We re-run the same
    filter+rank over the union of the pool and the chunk, capped at
    ``skill_pool``. Because each input already holds at least the global top-K
    it can contribute, the top-K of the union is exact — so this streams 200k
    wallets through fixed memory without changing which wallets are selected."""
    combined = {rm.address: rm.metrics for rm in pool}
    combined.update(chunk_scored)
    return select_targets(
        combined, method=cfg.method, min_capital=cfg.min_capital,
        min_closed=cfg.min_closed, top_k=cfg.skill_pool,
    )


def evaluate_sweep(
    cfg: DiscoveryConfig,
    *,
    must_include: set[str] | None = None,
    cache_dir: str | None = None,
    activity_ttl_s: float = 86400.0,
    stop: threading.Event | None = None,
) -> dict[str, Eval]:
    """Run the funnel and return wallet -> Eval.

    ``must_include`` wallets (e.g. those already on the watchlist) are always
    lead-lag evaluated so decay can be measured even if they fall out of the
    fresh skill pool.
    """
    must_include = must_include or set()

    universe = build_universe(cfg.universe)
    for w in must_include:
        if w not in universe:
            universe.append(w)
    if _stopping(stop):
        return {}

    # Fetch + score the universe in CHUNKS so we never hold every wallet's raw
    # /activity in memory at once. The unchunked version held all wallets at once
    # and peaked ~2.5GB (OOM on a 2GB VM). Activity is disk-cached, so chunking
    # changes only *when* data is resident, not the network volume; and
    # `activity` is not needed past scoring (lead-lag below re-fetches via
    # fetch_recent_buys).
    #
    # We also keep only a STREAMING top-K skill pool rather than every wallet's
    # metrics: at 200k wallets the compact metrics dict (a per-market PnL list
    # each) would itself dwarf RAM. After each chunk we fold its survivors into a
    # running pool capped at ``skill_pool`` (top-K of a union == top-K of each
    # part's top-K), then drop the chunk entirely. Peak is bounded to ~one chunk
    # + the pool regardless of universe size, so the scan scales to 200k+.
    lookback = time.time() - cfg.lookback_days * 86400
    chunk_size = max(1, int(os.environ.get("WALLET_DISCOVERY_CHUNK", "100")))
    batch_pause_s = float(os.environ.get("WALLET_DISCOVERY_BATCH_PAUSE_S", "1.0"))
    pool: list = []                              # running top-K RankedMetrics
    must_metrics: dict = {}                      # retained metrics for watchlist wallets
    for i in range(0, len(universe), chunk_size):
        if _stopping(stop):
            return {}
        chunk = universe[i:i + chunk_size]
        activity = fetch_all_activity(chunk, cache_dir, activity_ttl_s, stop=stop)
        chunk_scored: dict = {}
        for w, a in activity.items():
            m = compute_wallet_metrics(a, start_ts=lookback, category=cfg.category)
            chunk_scored[w] = m
            if w in must_include:
                must_metrics[w] = m
        del activity  # release this chunk's raw activity before the next fetch
        pool = _merge_topk(pool, chunk_scored, cfg)
        del chunk_scored
        # Pause between batches so a wide sweep paces its /activity calls under
        # the data-API 429 ceiling (skip after the last chunk).
        if i + chunk_size < len(universe):
            _sleep_unless_stopped(stop, batch_pause_s)
    if _stopping(stop):
        return {}
    skilled = pool
    # metrics lookup for roi/tstat by wallet
    metric_by_wallet = {rm.address: rm.metrics for rm in skilled}

    # deep-evaluate the skill pool plus any wallets we must re-check
    to_eval = [rm.address for rm in skilled]
    for w in must_include:
        if w not in metric_by_wallet:
            to_eval.append(w)
            if w in must_metrics:
                metric_by_wallet[w] = must_metrics[w]

    since = time.time() - min(cfg.ll_lookback_days, HISTORY_RETENTION_DAYS - 1) * 86400
    delay_s, horizon_s = cfg.delay_min * 60, cfg.horizon_min * 60
    price_cache: dict[str, list] = {}

    evaluated: dict[str, Eval] = {}
    for w in to_eval:
        if _stopping(stop):
            break
        buys = fetch_recent_buys(w, since, cfg.min_usd)
        m = metric_by_wallet.get(w)
        tstat = m.tstat if m else 0.0
        roi = m.roi if m else 0.0
        if len(buys) < cfg.min_ll_trades:
            # not enough recent data to judge copyability — record skill only
            evaluated[w] = Eval(wallet=w, roi=roi, tstat=tstat)
            continue
        agg = lead_lag_wallet(buys[:60], delay_s, horizon_s, price_cache)
        evaluated[w] = Eval(
            wallet=w, roi=roi, tstat=tstat,
            capture_cents=agg.avg_capture * 100,
            lead_cents=agg.avg_lead * 100,
            hit_rate=agg.capture_hit_rate, n=agg.n,
        )
    return evaluated
