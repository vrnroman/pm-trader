"""Tree of Alpha's news JSON: the only free relay of the X flash accounts
(WuBlockchain, DeItaone, FirstSquawk, exchange notices), 5-60 s after the
tweet. `x-ratelimit-limit: 30` per minute (2026-10-25 probe), so the poll
interval floor is 20 s and the poller backs off on 429.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import httpx

from src.newsbot.items import NO_TIMESTAMP_FLAG, Item, SourceError, make_id
from src.newsbot.sources import BROWSER_UA

URL = "https://news.treeofalpha.com/api/news?limit=50"
MIN_POLL_S = 20


@dataclass(frozen=True)
class ToaSpec:
    key: str = "toa"
    url: str = URL
    domains: tuple = ("crypto", "corp")
    headers: dict = field(default_factory=dict)
    poll_s: int = MIN_POLL_S


SPEC = ToaSpec()


def prepare(spec, state: dict) -> tuple[str, dict]:
    headers = {"User-Agent": BROWSER_UA, "Accept": "application/json"}
    headers.update(spec.headers or {})
    if state.get("etag"):
        headers["If-None-Match"] = state["etag"]
    return spec.url, headers


def handle(status: int, headers, body: bytes, spec, state: dict, seen_ts: float) -> list[Item]:
    if status == 304:
        return []
    if status != 200:
        raise SourceError(f"HTTP {status}")
    items = parse(body, spec, seen_ts)
    etag = headers.get("etag") if headers is not None else None
    if etag:
        state["etag"] = etag
    return items


def fetch(state: dict, client: httpx.Client | None = None, spec=SPEC) -> list[Item]:
    url, headers = prepare(spec, state)
    own = client is None
    client = client or httpx.Client(timeout=15.0, follow_redirects=True)
    try:
        r = client.get(url, headers=headers)
        return handle(r.status_code, r.headers, r.content, spec, state, time.time())
    finally:
        if own:
            client.close()


def parse(body: bytes, spec=SPEC, seen_ts: float | None = None) -> list[Item]:
    seen_ts = time.time() if seen_ts is None else seen_ts
    try:
        rows = json.loads(body)
    except ValueError as e:
        raise SourceError(f"not JSON ({e})") from e
    if not isinstance(rows, list):
        raise SourceError(f"unexpected JSON shape {type(rows).__name__}")
    out: list[Item] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("_id"):
            continue
        title = str(row.get("title") or "").strip()
        # `en` is Tree's English rendering of a non-English post; the title
        # keeps the "Account (@handle): " prefix the judge uses for who-said-it.
        body_text = str(row.get("en") or "").strip() or title
        if not title and not body_text:
            continue
        ms = row.get("time")
        try:
            published = float(ms) / 1000.0 if ms is not None else None
        except (TypeError, ValueError):
            published = None
        if published is None:
            body_text = f"{NO_TIMESTAMP_FLAG} {body_text}"
            published = seen_ts
        src_tag = str(row.get("source") or "").strip()
        text = body_text if not src_tag or body_text.startswith(src_tag) else f"{body_text}\n[{src_tag}]"
        out.append(Item(
            id=make_id(spec.key, str(row["_id"])), source=spec.key, domains=tuple(spec.domains),
            published_ts=published, seen_ts=float(seen_ts),
            title=(title or body_text)[:500], text=text[:2000], url=str(row.get("url") or ""),
        ))
    return out
