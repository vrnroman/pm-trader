"""Public Telegram channels through the web preview, https://t.me/s/<channel>.

Unofficial but stable for years and served live (`cache-control: no-store`,
2026-10-25 probe). Each post is a `div.tgme_widget_message_wrap` with
`data-post="Chan/123"`, a `div.tgme_widget_message_text` and a
`<time datetime="ISO8601+00:00">` in the footer. A channel that has turned
the preview off, or a username that is a user/bot/absent, redirects to the
`t.me/<name>` page ("Contact @x" / "View @x" with a Send Message button and
no messages): that is a SourceError, never a crash (the roster counts it and
the brief says the channel is dark).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser

import httpx

from src.newsbot.items import NO_TIMESTAMP_FLAG, Item, SourceError, first_line, make_id, parse_iso8601, strip_html
from src.newsbot.sources import BROWSER_UA


@dataclass(frozen=True)
class ChannelSpec:
    key: str                 # "tg:<channel lowercased>"
    channel: str
    domains: tuple = ()
    headers: dict = field(default_factory=dict)
    poll_s: int = 30

    @property
    def url(self) -> str:
        return f"https://t.me/s/{self.channel}"


def spec_for(channel: str, domains: tuple = (), poll_s: int = 30) -> ChannelSpec:
    return ChannelSpec(key=f"tg:{channel.lower()}", channel=channel, domains=tuple(domains), poll_s=poll_s)


def prepare(spec, state: dict) -> tuple[str, dict]:
    headers = {"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"}
    headers.update(spec.headers or {})
    return f"https://t.me/s/{spec.channel}", headers


def handle(status: int, headers, body: bytes, spec, state: dict, seen_ts: float) -> list[Item]:
    if status in (301, 302, 303, 307, 308):
        # The client should follow; if it did not, the preview is off.
        raise SourceError(f"redirected (HTTP {status}): channel @{spec.channel} has no public preview")
    if status != 200:
        raise SourceError(f"HTTP {status}")
    html = body.decode("utf-8", "replace")
    return parse(html, spec, seen_ts)


def fetch(channel, state: dict, client: httpx.Client | None = None, domains: tuple = ()) -> list[Item]:
    spec = channel if hasattr(channel, "channel") else spec_for(channel, domains)
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

@dataclass
class _Post:
    post: str = ""           # "Chan/123"
    text_html: list = field(default_factory=list)
    datetime: str = ""


class _PageParser(HTMLParser):
    """Collects every message wrap's id, raw text HTML and footer time, plus
    the page-level markers that tell a dead preview from an empty channel."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.posts: list[_Post] = []
        self.page_action: str | None = None      # "Send Message", "View in Telegram", ...
        self.has_history = False                   # section.tgme_channel_history present
        self._cur: _Post | None = None
        self._depth = 0           # tag depth inside the current wrap
        self._text_depth = 0      # tag depth inside the message_text div (0 = outside)
        self._in_action = False

    @staticmethod
    def _classes(attrs) -> set:
        return set((dict(attrs).get("class") or "").split())

    def handle_starttag(self, tag, attrs):
        cls = self._classes(attrs)
        a = dict(attrs)
        if tag == "section" and "tgme_channel_history" in cls:
            self.has_history = True
        if tag == "div" and "tgme_widget_message_wrap" in cls:
            self._cur = _Post()
            self.posts.append(self._cur)
            self._depth = 1
            return
        if self._cur is None:
            if tag == "a" and ("tgme_action_button_new" in cls or "tgme_action_button" in cls):
                self._in_action = True
            return
        if tag not in _VOID:
            self._depth += 1
        if tag == "div" and "tgme_widget_message" in cls and a.get("data-post"):
            self._cur.post = a["data-post"]
        if tag == "time" and a.get("datetime") and not self._cur.datetime:
            self._cur.datetime = a["datetime"]
        if self._text_depth:
            if tag not in _VOID:
                self._text_depth += 1
            self._cur.text_html.append(self.get_starttag_text() or "")
        elif tag == "div" and "tgme_widget_message_text" in cls:
            self._text_depth = 1

    def handle_startendtag(self, tag, attrs):
        if self._cur is not None and self._text_depth:
            self._cur.text_html.append(self.get_starttag_text() or "")
        elif tag == "time":
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self._in_action and tag == "a":
            self._in_action = False
        if self._cur is None or tag in _VOID:
            return
        if self._text_depth:
            self._text_depth -= 1
            if self._text_depth:
                self._cur.text_html.append(f"</{tag}>")
        self._depth -= 1
        if self._depth <= 0:
            self._cur = None
            self._text_depth = 0

    def _data(self, s: str):
        if self._in_action:
            self.page_action = ((self.page_action or "") + s).strip()
        if self._cur is not None and self._text_depth:
            self._cur.text_html.append(s)

    def handle_data(self, data):
        self._data(data)

    def handle_entityref(self, name):
        self._data(f"&{name};")

    def handle_charref(self, name):
        self._data(f"&#{name};")


_VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr", "area", "base", "col", "embed", "track"}
_SELF_LINK = re.compile(r"\s*\(https://t\.me/[A-Za-z0-9_]+\)$")  # a trailing bare channel link, any case


def parse(html: str, spec, seen_ts: float) -> list[Item]:
    p = _PageParser()
    p.feed(html)
    p.close()
    if not p.posts:
        if p.page_action or "tgme_channel_history" not in html:
            what = p.page_action or "no channel history on the page"
            raise SourceError(f"@{spec.channel} has no public preview ({what})")
        return []  # a real channel page with zero messages (new or wiped)
    items: list[Item] = []
    for post in p.posts:
        if not post.post or "/" not in post.post:
            continue
        chan, _, msg_id = post.post.partition("/")
        text = strip_html("".join(post.text_html), keep_links=True)
        # Squawk channels sign every post with a link to themselves
        # ("...|FJ (https://t.me/FinancialJuice)"); that is branding, not news.
        text = _SELF_LINK.sub("", text.replace(f" (https://t.me/{chan})", "")).strip()
        if not text:
            continue  # a photo/video/sticker with no caption: nothing to judge
        published = parse_iso8601(post.datetime)
        url = f"https://t.me/{chan}/{msg_id}"
        if published is None:
            # Every live page carries the time; a missing one means the
            # markup changed. Flag rather than guess (see items.NO_TIMESTAMP_FLAG).
            text = f"{NO_TIMESTAMP_FLAG} {text}"
            published = seen_ts
        items.append(Item(
            id=make_id(spec.key, msg_id), source=spec.key, domains=tuple(spec.domains),
            published_ts=float(published), seen_ts=float(seen_ts),
            title=first_line(text), text=text[:2000], url=url,
        ))
    return items
