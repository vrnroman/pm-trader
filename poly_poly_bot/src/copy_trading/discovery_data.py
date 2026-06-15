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
from src.copy_trading.entry_profile import EntryProfile, entry_profile, is_copyable_entry
from src.copy_trading.lead_lag import WalletLeadLag, analyze_buy
from src.copy_trading.pnl_curve import CurveMetrics, curve_metrics, fetch_pnl_curve
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
                # Empirically the data-API sends `Retry-After: 0` (no real hint),
                # so fall back to a fixed 1s cool-off; honour a larger value if
                # the server ever starts sending one.
                try:
                    wait = float(r.headers.get("Retry-After") or 0)
                except ValueError:
                    wait = 0.0
                time.sleep(max(wait, 1.0))
                continue
            if 400 <= r.status_code < 500:
                return None  # client error (e.g. offset cap exceeded) won't fix on retry
            # else 5xx — fall through to the backoff sleep and retry
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
    window_s: float | None = None,
    expand_filters: bool | None = None,
) -> list[str]:
    """Wallets active in the recent trade feed (default: the last ``window_s``).

    NOTE: the data-API hard-caps ``/trades`` pagination at **offset 3000**
    (beyond it returns HTTP 400 "max historical activity offset of 3000
    exceeded"), so a single filter exposes only its ~3500 most-recent trades.
    We widen the net two ways:

    * **stake tiers** ($3000 → $100, high first so the strongest wallets seed
      the set and modest-bet insiders are still caught);
    * **filter expansion** (``expand_filters``): each tier is also queried per
      ``side`` (BUY/SELL) and ``takerOnly`` (true=takers, false=incl. makers).
      Each filter combination is its own newest-first feed, so the union covers
      more distinct wallets within the same recent window — at the cost of ~20×
      the requests. Off by default; turn on for a wider (but slower) sweep.

    ``window_s`` makes this an *active-in-the-last-N-seconds* universe: trades
    older than the cutoff are skipped, and because the feed is newest-first we
    stop paging a filter combo as soon as it crosses the cutoff (so a 24h sweep
    rarely needs the full offset budget). ``window_s=0`` disables the window and
    pages each combo to ``max_offset`` (the legacy top-stake behaviour).

    Stops a combo when it runs dry, the offset budget (``max_offset``, capped at
    the API's 3000) is hit, the window cutoff is crossed, or we've collected
    ``target`` unique wallets. A short ``page_pause_s`` between pages keeps us
    under the 429 ceiling.
    """
    if max_offset is None:
        max_offset = int(os.environ.get("WALLET_DISCOVERY_UNIVERSE_MAX_OFFSET", "3000"))
    if page_pause_s is None:
        page_pause_s = float(os.environ.get("WALLET_DISCOVERY_PAGE_PAUSE_S", "0.3"))
    if window_s is None:
        window_s = float(os.environ.get("WALLET_DISCOVERY_UNIVERSE_WINDOW_S", "86400"))
    if expand_filters is None:
        expand_filters = os.environ.get(
            "WALLET_DISCOVERY_EXPAND_FILTERS", "false").strip().lower() == "true"

    cutoff = (time.time() - window_s) if window_s and window_s > 0 else None
    sides = ("BUY", "SELL") if expand_filters else (None,)
    takers = ("true", "false") if expand_filters else ("true",)
    combos = [(amt, side, taker)
              for amt in min_amounts for side in sides for taker in takers]

    s = requests.Session()
    seen: set[str] = set()
    for amt, side, taker in combos:
        off = 0
        while off <= max_offset and len(seen) < target:  # offset 3000 itself is valid
            params = dict(limit=500, offset=off, filterType="CASH",
                          filterAmount=amt, takerOnly=taker)
            if side:
                params["side"] = side
            tr = _get(s, DATA_API, "/trades", **params)
            if not tr:
                break
            crossed = False
            for t in tr:
                if cutoff is not None and float(t.get("timestamp") or 0) < cutoff:
                    crossed = True  # newest-first: this and the rest are too old
                    continue
                w = t.get("proxyWallet")
                if w:
                    seen.add(w)
            if crossed:
                break  # remaining offsets are entirely outside the window
            off += 500
            if len(tr) < 500:
                break  # combo exhausted — no point paging an empty offset
            if page_pause_s > 0:
                time.sleep(page_pause_s)
    return list(seen)[:target]


def prune_cache(cache_dir: str | None, ttl_s: float, max_files: int | None = None) -> int:
    """Bound the on-disk /activity cache; return how many files were removed.

    The universe churns every sweep, so wallets that drop out leave their
    ``{wallet}.json`` behind. Without pruning these orphans accumulate forever
    (~1 MB each at the 4000-record cap → tens of GB), eventually filling a small
    VM's disk. We delete anything older than ``ttl_s`` (it would be re-fetched on
    use anyway), then, if the directory is still over ``max_files``, drop the
    oldest by mtime as a hard backstop. RAM is unaffected — this is purely a disk
    guard.
    """
    if not cache_dir or not os.path.isdir(cache_dir):
        return 0
    now = time.time()
    removed = 0
    fresh: list[tuple[float, str]] = []
    for name in os.listdir(cache_dir):
        if not name.endswith(".json"):
            continue
        path = os.path.join(cache_dir, name)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if ttl_s and (now - mtime) >= ttl_s:
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
        else:
            fresh.append((mtime, path))
    if max_files and len(fresh) > max_files:
        fresh.sort()  # oldest first
        for _, path in fresh[: len(fresh) - max_files]:
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    return removed


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
            if not is_copyable_entry(price):  # skip tail entries (no copyable edge)
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


def wallet_entry_profile(wallet: str, cache_dir: str | None, ttl_s: float) -> EntryProfile:
    """Entry-price discipline from a wallet's (cached) activity; never raises."""
    try:
        return entry_profile(fetch_activity(wallet, cache_dir, ttl_s))
    except Exception:
        return EntryProfile()


def wallet_curve_metrics(wallet: str) -> CurveMetrics:
    """PnL-curve shape from the user-pnl endpoint; never raises."""
    try:
        return curve_metrics(fetch_pnl_curve(wallet))
    except Exception:
        return CurveMetrics()


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

    # Keep the on-disk activity cache bounded before we add this sweep's files.
    if cache_dir:
        prune_cache(cache_dir, activity_ttl_s,
                    max_files=int(os.environ.get("WALLET_DISCOVERY_CACHE_MAX_FILES", "15000")))

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
    # 8 workers (fetch_all_activity default) sustained ~148 /activity req/s with
    # zero 429s in testing; 16 workers started drawing 429s. So 8 workers is the
    # real governor and a 0.5s pause between 100-wallet batches leaves margin.
    batch_pause_s = float(os.environ.get("WALLET_DISCOVERY_BATCH_PAUSE_S", "0.5"))
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
        m = metric_by_wallet.get(w)
        tstat = m.tstat if m else 0.0
        roi = m.roi if m else 0.0
        # Entry discipline + PnL-curve shape: cheap on the small deep-eval set,
        # and the curve makes heavy traders (capped at ~3.5k /activity records)
        # scoreable on their long arc. Both degrade to neutral defaults on error.
        ep = wallet_entry_profile(w, cache_dir, activity_ttl_s)
        cm = wallet_curve_metrics(w)
        sig = dict(tail_ratio=ep.tail_ratio, copyable_ratio=ep.copyable_ratio,
                   curve_sharpe=cm.sharpe, curve_drawdown=cm.max_drawdown_frac,
                   net_pnl=cm.net_pnl)
        buys = fetch_recent_buys(w, since, cfg.min_usd)
        if len(buys) < cfg.min_ll_trades:
            # not enough recent data to judge copyability — record skill + signals
            evaluated[w] = Eval(wallet=w, roi=roi, tstat=tstat, **sig)
            continue
        agg = lead_lag_wallet(buys[:60], delay_s, horizon_s, price_cache)
        evaluated[w] = Eval(
            wallet=w, roi=roi, tstat=tstat,
            capture_cents=agg.avg_capture * 100,
            lead_cents=agg.avg_lead * 100,
            hit_rate=agg.capture_hit_rate, n=agg.n,
            **sig,
        )
    return evaluated
