"""RSS 2.0 and Atom feeds, with stdlib XML and conditional GET.

Covers the newsroom feeds, SEC's EDGAR "current filings" Atom (entries carry
only <updated>; title "8-K - COMPANY (CIK) (Filer)"; the summary lists the
8-K items) and trumpstruth.org's RSS mirror of Truth Social (RFC 822
pubDate with +0000; the Truth Social API itself is Cloudflare-blocked from
the VM, 2026-10-25 probe).
"""
from __future__ import annotations

import hashlib
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import httpx

from src.newsbot.items import (
    NO_TIMESTAMP_FLAG, Item, SourceError, make_id, parse_timestamp, strip_html,
)
from src.newsbot.sources import BROWSER_UA

TEXT_LIMIT = 2000  # the judge reads a headline and a paragraph, not the article


@dataclass(frozen=True)
class FeedSpec:
    key: str                 # roster key, e.g. "rss:nyt-home", "sec:8k"
    url: str
    domains: tuple = ()
    headers: dict = field(default_factory=dict)
    poll_s: int = 60


def prepare(spec, state: dict) -> tuple[str, dict]:
    headers = {"User-Agent": BROWSER_UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"}
    headers.update(spec.headers or {})
    if state.get("etag"):
        headers["If-None-Match"] = state["etag"]
    if state.get("last_modified"):
        headers["If-Modified-Since"] = state["last_modified"]
    return spec.url, headers


def handle(status: int, headers, body: bytes, spec, state: dict, seen_ts: float) -> list[Item]:
    if status == 304:
        return []
    if status != 200:
        raise SourceError(f"HTTP {status}")
    etag = headers.get("etag") if headers is not None else None
    last_mod = headers.get("last-modified") if headers is not None else None
    items = parse(body, spec, seen_ts)
    # Only remember validators from a response we could parse: a 200 with an
    # HTML error page and a fresh ETag would otherwise pin us to 304s forever.
    if etag:
        state["etag"] = etag
    if last_mod:
        state["last_modified"] = last_mod
    return items


def fetch(spec, state: dict, client: httpx.Client | None = None) -> list[Item]:
    url, headers = prepare(spec, state)
    own = client is None
    client = client or httpx.Client(timeout=15.0, follow_redirects=True)
    try:
        r = client.get(url, headers=headers)
        return handle(r.status_code, r.headers, r.content, spec, state, time.time())
    finally:
        if own:
            client.close()


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def parse(body: bytes, spec, seen_ts: float) -> list[Item]:
    """Bytes in (the declared encoding is honoured: SEC serves ISO-8859-1),
    Items out, in the feed's own order. Handles RSS 2.0, RSS 1.0/RDF (DW
    puts its items in the purl.org/rss/1.0 namespace) and Atom; children
    are matched by local name because the same feed element shows up with
    and without a namespace across publishers."""
    if body[:3] == b"\xef\xbb\xbf":
        body = body[3:]  # the Fed's press feed opens with a UTF-8 BOM
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        head = body[:80].decode("utf-8", "replace").strip().replace("\n", " ")
        raise SourceError(f"not XML ({e}); starts {head!r}") from e
    local = _local(root.tag)
    if local == "feed":
        return [it for it in (_atom_entry(e, spec, seen_ts) for e in root.iter() if _local(e.tag) == "entry") if it]
    if local in ("rss", "RDF") or any(_local(c.tag) == "channel" for c in root):
        entries = [e for e in root.iter() if _local(e.tag) == "item"]
        return [it for it in (_rss_item(e, spec, seen_ts) for e in entries) if it]
    raise SourceError(f"unknown feed root <{root.tag}>")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _children(el, name: str):
    return [c for c in el if _local(c.tag) == name]


def _text(el, *names: str) -> str:
    """First non-empty text among the named direct children (by local
    name). Atom <content type="xhtml"> nests markup instead of escaping it,
    so a child with no text but with children is serialised."""
    for name in names:
        for node in _children(el, name):
            if node.text and node.text.strip():
                return node.text.strip()
            inner = "".join(ET.tostring(c, encoding="unicode") for c in node)
            if inner.strip():
                return inner
    return ""


def _finish(spec, native_id: str, title: str, text: str, url: str, published: float | None, seen_ts: float) -> Item:
    if published is None:
        # The source gave no clock. seen_ts fills the field so the schema
        # holds, and the flag keeps the lead ledger from counting it.
        published = seen_ts
        text = f"{NO_TIMESTAMP_FLAG} {text}".strip()
    return Item(
        id=make_id(spec.key, native_id), source=spec.key, domains=tuple(spec.domains),
        published_ts=float(published), seen_ts=float(seen_ts),
        title=title[:500], text=text[:TEXT_LIMIT], url=url,
    )


def _fallback_id(*parts: str) -> str:
    return "sha1:" + hashlib.sha1("\x1f".join(parts).encode("utf-8", "replace")).hexdigest()[:20]


def _rss_item(el, spec, seen_ts: float) -> Item | None:
    title = strip_html(_text(el, "title"))
    link = _text(el, "link")
    if not link:
        # RDF items name themselves by rdf:about; some RSS 2.0 feeds only carry an atom:link.
        link = next((v for k, v in el.attrib.items() if _local(k) == "about"), "")
        if not link:
            alt = [ln for ln in _children(el, "link") if ln.get("rel", "alternate") == "alternate" and ln.get("href")]
            link = alt[0].get("href") if alt else ""
    guid = _text(el, "guid") or link or _fallback_id(title, _text(el, "pubDate"))
    published = parse_timestamp(_text(el, "pubDate", "date", "pubdate", "published", "updated"))
    body = strip_html(_text(el, "description", "encoded", "summary"))
    if not title and not body:
        return None
    text = body if body and body != title else title
    return _finish(spec, guid, title or body.split("\n", 1)[0], text, link, published, seen_ts)


def _atom_entry(el, spec, seen_ts: float) -> Item | None:
    title = strip_html(_text(el, "title"))
    links = _children(el, "link")
    link = next((ln.get("href") for ln in links if ln.get("rel", "alternate") == "alternate" and ln.get("href")), "")
    if not link and links:
        link = links[0].get("href", "")
    native = _text(el, "id") or link or _fallback_id(title, _text(el, "updated"))
    # <published> is the entry's own birth; SEC has only <updated>, which for
    # a filing index is the acceptance time, the clock we want.
    published = parse_timestamp(_text(el, "published", "updated"))
    body = strip_html(_text(el, "summary", "content"))
    if not title and not body:
        return None
    text = body if body and body != title else title
    return _finish(spec, native, title or body.split("\n", 1)[0], text, link, published, seen_ts)
