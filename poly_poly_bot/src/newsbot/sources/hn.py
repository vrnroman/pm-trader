"""Hacker News newest stories via Algolia's search_by_date (open, no key).
The 1-10 min path for big tech/corporate news that has no RSS of its own
(Anthropic, Tesla, NVIDIA newsrooms are 404/403, 2026-10-25 probe).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import httpx

from src.newsbot.items import NO_TIMESTAMP_FLAG, Item, SourceError, make_id, parse_iso8601, strip_html
from src.newsbot.sources import CONTACT_UA

URL = "https://hn.algolia.com/api/v1/search_by_date?tags=story&hitsPerPage=50"


@dataclass(frozen=True)
class HnSpec:
    key: str = "hn"
    url: str = URL
    domains: tuple = ("corp",)
    headers: dict = field(default_factory=dict)
    poll_s: int = 60


SPEC = HnSpec()


def prepare(spec, state: dict) -> tuple[str, dict]:
    headers = {"User-Agent": CONTACT_UA, "Accept": "application/json"}
    headers.update(spec.headers or {})
    return spec.url, headers


def handle(status: int, headers, body: bytes, spec, state: dict, seen_ts: float) -> list[Item]:
    if status != 200:
        raise SourceError(f"HTTP {status}")
    return parse(body, spec, seen_ts)


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
        payload = json.loads(body)
    except ValueError as e:
        raise SourceError(f"not JSON ({e})") from e
    hits = payload.get("hits") if isinstance(payload, dict) else None
    if not isinstance(hits, list):
        raise SourceError("no 'hits' list in the Algolia response")
    out: list[Item] = []
    for h in hits:
        if not isinstance(h, dict) or not h.get("objectID"):
            continue
        title = str(h.get("title") or "").strip()
        if not title:
            continue
        oid = str(h["objectID"])
        published = None
        if h.get("created_at_i") is not None:
            try:
                published = float(h["created_at_i"])
            except (TypeError, ValueError):
                published = None
        if published is None:
            published = parse_iso8601(h.get("created_at"))
        text = title
        story_text = h.get("story_text")   # Ask/Tell HN posts carry their body here
        if story_text:
            text = f"{title}\n{strip_html(str(story_text))}"
        if published is None:
            text = f"{NO_TIMESTAMP_FLAG} {text}"
            published = seen_ts
        url = str(h.get("url") or f"https://news.ycombinator.com/item?id={oid}")
        out.append(Item(
            id=make_id(spec.key, oid), source=spec.key, domains=tuple(spec.domains),
            published_ts=published, seen_ts=float(seen_ts), title=title[:500], text=text[:2000], url=url,
        ))
    return out
