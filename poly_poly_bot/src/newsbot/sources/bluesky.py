"""Bluesky: the wire services and newsrooms that left X (Reuters, AP, WaPo,
Bloomberg, Kyiv Post...). Two paths:

- `stream`: Jetstream, Bluesky's own JSON firehose, filtered server-side to
  our DIDs and `app.bsky.feed.post`. A post arrives < 1 s after it is made
  (2026-10-25 probe: time_us lag <= 0.03 s). Reconnects with `cursor=<time_us>`
  and exponential backoff; the dedup store absorbs the replay.
- `fetch_author_feed`: the public AppView's getAuthorFeed, for boot (the last
  20 posts before the socket is up) and for tests. `max-age=30`, so polling
  it faster than 30 s is pointless.

Handles are resolved to DIDs once at boot (`resolve_dids`); the DID is what
Jetstream filters on and what a frame carries, the handle is what we print.
"""
from __future__ import annotations

import asyncio
import json
import time
from urllib.parse import urlencode

import httpx

from src.logger import logger
from src.newsbot.items import NO_TIMESTAMP_FLAG, Item, SourceError, first_line, make_id, parse_iso8601

PUBLIC_API = "https://public.api.bsky.app/xrpc"
JETSTREAM_URL = "wss://jetstream2.us-east.bsky.network/subscribe"
POST_COLLECTION = "app.bsky.feed.post"
# On reconnect the cursor is rewound this much so a frame in flight when the
# socket dropped is replayed rather than lost; dedup drops the repeats.
CURSOR_REWIND_US = 5_000_000
MAX_BACKOFF_S = 60


def source_key(handle: str) -> str:
    return f"bsky:{handle.lower()}"


def post_url(handle: str, rkey: str) -> str:
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


# --------------------------------------------------------------------------
# Resolution and polling (HTTP)
# --------------------------------------------------------------------------

def resolve_dids(handles, client: httpx.Client | None = None) -> dict[str, str]:
    """handle -> did via com.atproto.identity.resolveHandle. A handle that
    does not resolve is logged and left out (the roster will show it with
    zero items rather than the boot failing on one renamed account)."""
    own = client is None
    client = client or httpx.Client(timeout=15.0)
    out: dict[str, str] = {}
    try:
        for h in handles:
            try:
                r = client.get(f"{PUBLIC_API}/com.atproto.identity.resolveHandle", params={"handle": h})
                did = r.json().get("did") if r.status_code == 200 else None
            except (httpx.HTTPError, ValueError) as e:
                did = None
                logger.warn(f"[news-src] bsky resolve failed handle={h} err={e}")
            if did:
                out[h] = did
            else:
                logger.warn(f"[news-src] bsky handle did not resolve handle={h}")
    finally:
        if own:
            client.close()
    return out


def fetch_author_feed(handle: str, client: httpx.Client | None = None, limit: int = 20,
                      domains: tuple = (), seen_ts: float | None = None) -> list[Item]:
    own = client is None
    client = client or httpx.Client(timeout=15.0)
    try:
        r = client.get(f"{PUBLIC_API}/app.bsky.feed.getAuthorFeed",
                       params={"actor": handle, "limit": limit, "filter": "posts_no_replies"})
        if r.status_code != 200:
            raise SourceError(f"HTTP {r.status_code}")
        return author_feed_to_items(r.json(), handle, time.time() if seen_ts is None else seen_ts, domains)
    finally:
        if own:
            client.close()


def author_feed_to_items(payload: dict, handle: str, seen_ts: float, domains: tuple = ()) -> list[Item]:
    feed = payload.get("feed") if isinstance(payload, dict) else None
    if not isinstance(feed, list):
        raise SourceError("no 'feed' list in getAuthorFeed")
    out: list[Item] = []
    for entry in feed:
        post = (entry or {}).get("post") or {}
        if entry.get("reason"):
            continue  # a repost of someone else's post; not this account speaking
        author = (post.get("author") or {}).get("handle") or handle
        uri = post.get("uri") or ""
        rkey = uri.rsplit("/", 1)[-1] if "/" in uri else ""
        item = record_to_item(post.get("record") or {}, author, rkey, seen_ts, domains)
        if item:
            out.append(item)
    return out


# --------------------------------------------------------------------------
# Frame -> Item
# --------------------------------------------------------------------------

def record_to_item(record: dict, handle: str, rkey: str, seen_ts: float, domains: tuple = ()) -> Item | None:
    if not rkey or record.get("$type", POST_COLLECTION) != POST_COLLECTION:
        return None
    if record.get("reply"):
        return None  # replies are conversation, not news
    text = str(record.get("text") or "").strip()
    links = _facet_links(record)
    for uri in links:
        bare = uri.split("://", 1)[-1].rstrip("/")
        if bare not in text:
            text = f"{text}\n{uri}".strip()
    if not text:
        return None  # image-only post with no caption
    published = parse_iso8601(record.get("createdAt"))
    if published is None:
        text = f"{NO_TIMESTAMP_FLAG} {text}"
        published = seen_ts
    key = source_key(handle)
    return Item(
        id=make_id(key, rkey), source=key, domains=tuple(domains),
        published_ts=published, seen_ts=float(seen_ts),
        title=first_line(text), text=text[:2000], url=post_url(handle, rkey),
    )


def _facet_links(record: dict) -> list[str]:
    out: list[str] = []
    for facet in record.get("facets") or []:
        for feat in (facet or {}).get("features") or []:
            if feat.get("$type") == "app.bsky.richtext.facet#link" and feat.get("uri"):
                out.append(str(feat["uri"]))
    embed = record.get("embed") or {}
    ext = embed.get("external") if isinstance(embed, dict) else None
    if isinstance(ext, dict) and ext.get("uri"):
        out.append(str(ext["uri"]))
    seen: set[str] = set()
    return [u for u in out if not (u in seen or seen.add(u))]


def frame_to_item(frame: dict, handle_by_did: dict[str, str], seen_ts: float,
                  domains_by_handle: dict[str, tuple] | None = None) -> Item | None:
    """One Jetstream frame -> Item, or None for anything that is not a new
    post by one of our accounts (deletes, likes, other collections, DIDs we
    did not ask for but the server sent anyway)."""
    if frame.get("kind") != "commit":
        return None
    commit = frame.get("commit") or {}
    if commit.get("operation") != "create" or commit.get("collection") != POST_COLLECTION:
        return None
    handle = handle_by_did.get(frame.get("did", ""))
    if not handle:
        return None
    domains = (domains_by_handle or {}).get(handle, ())
    return record_to_item(commit.get("record") or {}, handle, str(commit.get("rkey") or ""), seen_ts, domains)


def jetstream_url(dids, cursor: int | None = None, base: str = JETSTREAM_URL) -> str:
    params = [("wantedCollections", POST_COLLECTION)] + [("wantedDids", d) for d in dids]
    if cursor:
        params.append(("cursor", str(int(cursor))))
    return f"{base}?{urlencode(params)}"


# --------------------------------------------------------------------------
# The socket
# --------------------------------------------------------------------------

async def stream(queue: asyncio.Queue, dids: dict[str, str], on_cursor=None, *,
                 domains_by_handle: dict[str, tuple] | None = None, cursor: int | None = None,
                 connect=None, sleep=asyncio.sleep, clock=time.time, stop: asyncio.Event | None = None,
                 max_backoff_s: float = MAX_BACKOFF_S, dedup=None, counters=None) -> None:
    """Run until `stop` is set (or cancelled). `dids` is handle -> did, as
    `resolve_dids` returns it. `on_cursor(time_us)` is called per frame so
    the caller can persist the cursor for the next boot."""
    if connect is None:
        import websockets
        connect = websockets.connect
    handle_by_did = {did: h for h, did in dids.items()}
    backoff = 1.0
    err_logged = False
    while not (stop is not None and stop.is_set()):
        url = jetstream_url(handle_by_did.keys(), cursor)
        try:
            async with connect(url) as ws:
                logger.info(f"[news-src] bsky jetstream connected dids={len(handle_by_did)} cursor={cursor or 0}")
                async for raw in ws:
                    if stop is not None and stop.is_set():
                        break
                    # A frame, not the handshake, proves the link: a server that
                    # accepts and drops at once must still see the backoff grow.
                    backoff = 1.0
                    err_logged = False
                    try:
                        frame = json.loads(raw)
                    except ValueError:
                        continue
                    tu = frame.get("time_us")
                    if isinstance(tu, int):
                        cursor = max(tu - CURSOR_REWIND_US, 0)
                        if on_cursor:
                            on_cursor(tu)
                    now = clock()
                    item = frame_to_item(frame, handle_by_did, now, domains_by_handle)
                    if item is None:
                        continue
                    if dedup is not None and not dedup.add(item.id):
                        continue
                    await queue.put(item)
                    if counters is not None:
                        counters.ok(item.source, 1, now, item.published_ts)
                    logger.info(f"[news-src] source={item.source} new=1 lag_s={now - item.published_ts:.1f} title={item.title[:80]!r}")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # ConnectionClosed, OSError, handshake errors: all mean "reconnect"
            if counters is not None:
                counters.error("bsky", clock(), str(e))
            if not err_logged:
                logger.warn(f"[news-src] bsky jetstream dropped err={type(e).__name__}: {e}; reconnecting in {backoff:.0f}s")
                err_logged = True
            if stop is not None and stop.is_set():
                break
            await sleep(backoff)
            backoff = min(backoff * 2, max_backoff_s)
            continue
        if stop is not None and stop.is_set():
            break
        # A clean close (server rotation) is not an error: reconnect at once with the cursor.
        await sleep(0)
