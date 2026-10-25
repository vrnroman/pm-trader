"""The Item every source emits, the dedup store, and the two shared helpers
every source needs (timestamp parsing, HTML stripping).

The Item schema is DESIGN.md's, field for field. ``published_ts`` is the
SOURCE's own clock; a source that gives none gets ``seen_ts`` and the text
is flagged so the lead-time ledger can exclude it rather than count a fake
zero lag (2026-10-25: the thesis is "does the source lead the price", so a
timestamp we invented would answer the question for us).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

NO_TIMESTAMP_FLAG = "[no source timestamp]"


class SourceError(Exception):
    """A source answered, but not with the thing we poll it for (a Telegram
    channel without a public preview, an HTML error page where a feed should
    be). Counted as an error on the roster, never a crash of the poller."""


@dataclass(frozen=True, slots=True)
class Item:
    id: str              # f"{source}:{native_id}"; the dedup key
    source: str          # roster key: "tg:financialjuice", "bsky:reuters.com", "rss:nyt-home", "sec:8k", "toa", "hn"
    domains: tuple       # from the roster: ("geo",), ("corp",), ("crypto",), ("politics",), ("ent",), ("sport",)
    published_ts: float  # the SOURCE's own timestamp (UTC epoch), never ours
    seen_ts: float       # when we received it
    title: str
    text: str
    url: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domains"] = list(self.domains)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        return cls(
            id=str(d["id"]), source=str(d["source"]), domains=tuple(d.get("domains") or ()),
            published_ts=float(d["published_ts"]), seen_ts=float(d["seen_ts"]),
            title=str(d.get("title") or ""), text=str(d.get("text") or ""), url=str(d.get("url") or ""),
        )


def make_id(source: str, native_id: str) -> str:
    return f"{source}:{native_id}"


# --------------------------------------------------------------------------
# Dedup store
# --------------------------------------------------------------------------

class DedupStore:
    """Seen item ids on disk: a JSON list, newest last, capped with FIFO
    eviction so a two-week run cannot grow it without bound (50k ids is
    ~3 MB and about four days of every source at full tilt; anything older
    than that is also outside every poll window, so re-seeing it is not a
    real risk)."""

    CAP = 50_000

    def __init__(self, path: str | Path, cap: int = CAP):
        self.path = Path(path)
        self.cap = int(cap)
        self._order: deque[str] = deque()
        self._set: set[str] = set()
        self._dirty = False
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A torn file is worse than an empty one only if we crash on it;
            # starting empty means at most one duplicate per source this boot.
            return
        ids = raw.get("ids", []) if isinstance(raw, dict) else raw
        for i in ids[-self.cap:]:
            if isinstance(i, str) and i not in self._set:
                self._order.append(i)
                self._set.add(i)

    def __len__(self) -> int:
        return len(self._order)

    def __contains__(self, item_id: str) -> bool:
        return item_id in self._set

    def seen(self, item_id: str) -> bool:
        return item_id in self._set

    def add(self, item_id: str) -> bool:
        """Record an id. Returns True when it was new."""
        if item_id in self._set:
            return False
        self._order.append(item_id)
        self._set.add(item_id)
        while len(self._order) > self.cap:
            self._set.discard(self._order.popleft())
        self._dirty = True
        return True

    def save(self, force: bool = False) -> bool:
        """Write the file atomically (tmp + os.replace). Returns True when a
        write happened."""
        if not (self._dirty or force):
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"cap": self.cap, "ids": list(self._order)})
        fd, tmp = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self._dirty = False
        return True


# --------------------------------------------------------------------------
# Timestamps
# --------------------------------------------------------------------------

_ISO_Z = re.compile(r"Z$", re.I)


def parse_iso8601(s: str | None) -> float | None:
    """ISO 8601 with an offset or Z -> UTC epoch seconds. A naive string is
    read as UTC (Atom requires an offset; the sources that omit one, HN and
    Bluesky, mean UTC)."""
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(_ISO_Z.sub("+00:00", s))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def parse_rfc822(s: str | None) -> float | None:
    """RSS pubDate (RFC 822/2822, incl. the 'EST'/'GMT' zone names) -> UTC
    epoch seconds; naive means UTC."""
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def parse_timestamp(s: str | None) -> float | None:
    """Either spelling; feeds mix them (Atom in an RSS <dc:date>, RSS pubDate
    written as ISO by some CMSes). ISO first: fromisoformat rejects an RFC 822
    string outright, while parsedate can misread an ISO one."""
    ts = parse_iso8601(s)
    return ts if ts is not None else parse_rfc822(s)


# --------------------------------------------------------------------------
# HTML -> text
# --------------------------------------------------------------------------

_BLOCK_TAGS = {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}
_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n\s*\n+")


class _Stripper(HTMLParser):
    """Text out of a fragment, block tags as newlines, anchor hrefs kept
    (an item's link is often the only thing that tells two squawks apart)."""

    def __init__(self, keep_links: bool):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.keep_links = keep_links
        self._href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "a" and self.keep_links:
            self._href = dict(attrs).get("href")
            self._anchor_text = []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "a" and self.keep_links and self._href is not None:
            text = "".join(self._anchor_text).strip()
            href = self._href.strip()
            if text and href and not href.startswith(("#", "javascript:")):
                shown = text.rstrip("…").rstrip(".")
                bare = href.split("://", 1)[-1]
                # Telegram shows long URLs scheme-less and truncated with an
                # ellipsis; the href is the real one, so it replaces the stub.
                is_stub = any(a.startswith(shown) for a in (href, bare)) or any(shown.startswith(a) for a in (href, bare))
                self.parts.append(href if is_stub else f"{text} ({href})")
            else:
                self.parts.append(text)
            self._href = None
            self._anchor_text = []

    def handle_data(self, data):
        if self._href is not None and self.keep_links:
            self._anchor_text.append(data)
        else:
            self.parts.append(data)


def strip_html(fragment: str | None, keep_links: bool = False) -> str:
    if not fragment:
        return ""
    p = _Stripper(keep_links)
    try:
        p.feed(fragment)
        p.close()
    except Exception:  # html.parser is lenient; this is for the truly broken
        return _WS.sub(" ", unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()
    text = "".join(p.parts)
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _NL.sub("\n", text).strip()


def first_line(text: str, limit: int = 200) -> str:
    """A title for sources that have none (Telegram, Bluesky)."""
    line = next((ln.strip() for ln in text.split("\n") if ln.strip()), "")
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"
