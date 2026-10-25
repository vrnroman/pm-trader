"""One asyncio task per HTTP source, each at its own interval.

A 429 or 403 doubles that source's interval (up to 30 min) and is logged
once per episode, not per poll: the 2026-07 copy bot taught us that 261
identical rate-limit warnings a day hide the one that matters. A source
that answers 200 again drops back to its base interval and says so once.
Transport errors (timeouts, DNS, resets) keep the base interval: they are
ours or the network's, not a signal from the source.
"""
from __future__ import annotations

import asyncio
import time

import httpx

from src.logger import logger
from src.newsbot.items import SourceError
from src.newsbot.sources import hn, rss, telegram_web, treeofalpha

FAMILIES = {"rss": rss, "tg": telegram_web, "toa": treeofalpha, "hn": hn}
HTTP_TIMEOUT_S = 15.0
MAX_BACKOFF_S = 1800
BACKOFF_STATUSES = (429, 403)


def new_client() -> httpx.AsyncClient:
    # follow_redirects: trumpstruth.org 301s to www., and a Telegram channel
    # without a preview 302s to its contact page (which parse() then names).
    return httpx.AsyncClient(timeout=HTTP_TIMEOUT_S, follow_redirects=True, http2=False)


async def run_pollers(roster, queue: asyncio.Queue, dedup, counters, *, client: httpx.AsyncClient | None = None,
                      sleep=asyncio.sleep, clock=time.time, stop: asyncio.Event | None = None,
                      states: dict | None = None) -> None:
    """Poll every HTTP source on the roster until `stop` is set. Websocket
    sources (kind "bsky") are skipped here; `bluesky.stream` owns them."""
    http_sources = [s for s in roster if s.kind in FAMILIES]
    if not http_sources:
        logger.warn("[news-src] no HTTP sources on the roster; pollers idle")
        return
    own = client is None
    client = client or new_client()
    states = {} if states is None else states
    logger.info(f"[news-src] pollers starting n={len(http_sources)} "
                f"req_per_min={sum(60.0 / max(s.poll_s, 1) for s in http_sources):.0f}")
    tasks = [asyncio.ensure_future(poll_source(s, queue, dedup, counters, client, states.setdefault(s.key, {}),
                                               sleep=sleep, clock=clock, stop=stop)) for s in http_sources]
    try:
        await asyncio.gather(*tasks)
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        if own:
            await client.aclose()
        dedup.save()
        counters.save(force=True)


async def poll_source(src, queue: asyncio.Queue, dedup, counters, client, state: dict, *,
                      sleep=asyncio.sleep, clock=time.time, stop: asyncio.Event | None = None) -> None:
    fam = FAMILIES[src.kind]
    base = max(int(src.poll_s), 1)
    interval = base
    backoff_logged = False
    err_logged = False
    while not (stop is not None and stop.is_set()):
        now = clock()
        url, headers = fam.prepare(src, state)
        try:
            r = await client.get(url, headers=headers)
            status = r.status_code
            if status in BACKOFF_STATUSES:
                interval = min(interval * 2, MAX_BACKOFF_S)
                counters.error(src.key, now, f"HTTP {status}")
                if not backoff_logged:
                    logger.warn(f"[news-src] source={src.key} status={status} backing off interval={interval}s (max {MAX_BACKOFF_S}s)")
                    backoff_logged = True
            else:
                items = fam.handle(status, r.headers, r.content, src, state, now)
                new = [it for it in items if dedup.add(it.id)]
                for it in new:
                    await queue.put(it)
                newest = max((it.published_ts for it in new), default=None)
                counters.ok(src.key, len(new), now, newest)
                if backoff_logged or err_logged or interval != base:
                    logger.info(f"[news-src] source={src.key} recovered status={status} interval={base}s")
                interval = base
                backoff_logged = err_logged = False
                if new:
                    lag = now - max(it.published_ts for it in new)
                    logger.info(f"[news-src] source={src.key} status={status} seen={len(items)} new={len(new)} "
                                f"newest_lag_s={lag:.0f} title={new[0].title[:80]!r}")
                else:
                    logger.debug(f"[news-src] source={src.key} status={status} seen={len(items)} new=0")
        except asyncio.CancelledError:
            raise
        except SourceError as e:
            # The source answered with the wrong thing (no-preview page, HTML
            # where XML should be). Repeating faster will not change it.
            interval = min(interval * 2, MAX_BACKOFF_S)
            counters.error(src.key, now, str(e))
            if not err_logged:
                logger.warn(f"[news-src] source={src.key} source-error={e} interval={interval}s")
                err_logged = True
        except (httpx.HTTPError, OSError, asyncio.TimeoutError) as e:
            counters.error(src.key, now, f"{type(e).__name__}: {e}")
            if not err_logged:
                logger.warn(f"[news-src] source={src.key} transport-error={type(e).__name__}: {e}")
                err_logged = True
        except Exception as e:  # a parser bug must not kill the task for the next two weeks
            counters.error(src.key, now, f"{type(e).__name__}: {e}")
            logger.error(f"[news-src] source={src.key} unexpected {type(e).__name__}: {e}")
        try:
            dedup.save()
            counters.save(now)
        except OSError as e:
            logger.warn(f"[news-src] state save failed: {e}")
        if stop is not None and stop.is_set():
            break
        await sleep(interval)
