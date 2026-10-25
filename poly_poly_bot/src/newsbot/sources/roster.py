"""The v1 source list as data, and the per-source counters.

Every entry is what the 2026-10-25 probe verified live (URL, format, poll
interval); nothing here was guessed. Entries carry domain tags so the
runner can keep to NEWS_DOMAINS; entertainment and sport are tagged and
present (the data is cheap to keep) but off under the default domains per
the manager ruling of 2026-10-25 (DESIGN.md).
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from src.newsbot.sources import CONTACT_UA

KINDS = ("rss", "tg", "bsky", "toa", "hn")
DOMAINS = ("politics", "crypto", "geo", "corp", "ent", "sport")
DEFAULT_DOMAINS = ("politics", "crypto", "geo", "corp")


@dataclass(frozen=True)
class Source:
    key: str
    kind: str                 # one of KINDS
    domains: tuple
    poll_s: int = 60
    url: str = ""             # rss / toa / hn
    handle: str = ""          # bsky
    channel: str = ""         # tg
    headers: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"{self.key}: unknown kind {self.kind!r}")
        bad = [d for d in self.domains if d not in DOMAINS]
        if bad:
            raise ValueError(f"{self.key}: unknown domains {bad}")


def _rss(key, url, *domains, poll_s=60, headers=None):
    return Source(key=f"rss:{key}", kind="rss", url=url, domains=tuple(domains), poll_s=poll_s, headers=dict(headers or {}))


def _tg(channel, *domains, poll_s=60):
    return Source(key=f"tg:{channel.lower()}", kind="tg", channel=channel, domains=tuple(domains), poll_s=poll_s)


def _bsky(handle, *domains):
    return Source(key=f"bsky:{handle.lower()}", kind="bsky", handle=handle, domains=tuple(domains), poll_s=0)


SEC_HEADERS = {"User-Agent": CONTACT_UA}

V1: tuple[Source, ...] = (
    # --- Telegram squawk channels (t.me/s, 30-60 s) ---
    _tg("insiderpaper", "geo", "corp", poll_s=30),
    _tg("clashreport", "geo", poll_s=30),
    _tg("visegrad_24", "geo", "politics"),
    _tg("geopolitics_prime", "geo"),
    _tg("warmonitors", "geo"),
    _tg("disclosetv", "geo", "politics"),
    _tg("Megatron_ron", "geo"),
    _tg("financialjuice", "geo", "corp", "politics", poll_s=30),
    _tg("walterbloomberg", "corp", "politics", poll_s=30),
    _tg("wublockchainenglish", "crypto"),
    _tg("WatcherGuru", "crypto", "corp"),
    _tg("fabrizioromano", "sport"),
    # --- RSS/Atom: fast general ---
    _rss("nyt-home", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "geo", "politics", "corp"),
    _rss("nyt-world", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "geo"),
    _rss("nypost", "https://nypost.com/feed/", "politics", "geo"),
    _rss("france24", "https://www.france24.com/en/rss", "geo"),
    _rss("dw", "https://rss.dw.com/rdf/rss-en-all", "geo"),
    _rss("aljazeera", "https://www.aljazeera.com/xml/rss/all.xml", "geo"),
    _rss("bbc-world", "https://feeds.bbci.co.uk/news/world/rss.xml", "geo"),
    _rss("guardian-world", "https://www.theguardian.com/world/rss", "geo"),
    _rss("guardian-us", "https://www.theguardian.com/us-news/rss", "politics"),
    _rss("cbs", "https://www.cbsnews.com/latest/rss/main", "politics", "geo"),
    _rss("fox-latest", "https://moxie.foxnews.com/google-publisher/latest.xml", "politics"),
    _rss("independent", "https://www.independent.co.uk/rss", "geo", "politics"),
    # /feed/ is a 404; /feed/rss/ is the live one (checked 2026-10-25).
    _rss("kyivindependent", "https://kyivindependent.com/feed/rss/", "geo"),
    # --- RSS: corporate / markets ---
    _rss("bloomberg-markets", "https://feeds.bloomberg.com/markets/news.rss", "corp"),
    _rss("bloomberg-tech", "https://feeds.bloomberg.com/technology/news.rss", "corp"),
    _rss("bloomberg-politics", "https://feeds.bloomberg.com/politics/news.rss", "politics"),
    _rss("cnbc-top", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "corp", "politics"),
    _rss("cnbc-business", "https://www.cnbc.com/id/10001147/device/rss/rss.html", "corp"),
    _rss("cnbc-tech", "https://www.cnbc.com/id/19854910/device/rss/rss.html", "corp"),
    _rss("wsj-world", "https://feeds.content.dowjones.io/public/rss/RSSWorldNews", "geo", "politics", poll_s=120),
    _rss("wsj-markets", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain", "corp", poll_s=120),
    _rss("prnewswire", "https://www.prnewswire.com/rss/news-releases-list.rss", "corp"),
    _rss("openai", "https://openai.com/news/rss.xml", "corp", poll_s=120),
    _rss("apple", "https://www.apple.com/newsroom/rss-feed.rss", "corp", poll_s=300),
    _rss("google-blog", "https://blog.google/rss/", "corp", poll_s=300),
    _rss("techcrunch", "https://techcrunch.com/feed/", "corp", poll_s=120),
    _rss("verge", "https://www.theverge.com/rss/index.xml", "corp", poll_s=120),
    # --- RSS: entertainment (tagged; off under default NEWS_DOMAINS) ---
    _rss("variety", "https://variety.com/feed/", "ent"),
    _rss("deadline", "https://deadline.com/feed/", "ent", poll_s=120),
    _rss("thr", "https://www.hollywoodreporter.com/feed/", "ent", poll_s=120),
    _rss("billboard", "https://www.billboard.com/feed/", "ent", poll_s=120),
    # --- RSS: crypto ---
    _rss("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "crypto", poll_s=120),
    _rss("theblock", "https://www.theblock.co/rss.xml", "crypto", poll_s=120),
    _rss("cointelegraph", "https://cointelegraph.com/rss", "crypto", poll_s=120),
    _rss("decrypt", "https://decrypt.co/feed", "crypto", poll_s=120),
    # --- Government (Atom/RSS) ---
    Source(key="sec:8k", kind="rss", domains=("corp",), poll_s=60, headers=dict(SEC_HEADERS),
           url="https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&count=40&output=atom"),
    Source(key="sec:press", kind="rss", domains=("corp", "crypto"), poll_s=300, headers=dict(SEC_HEADERS),
           url="https://www.sec.gov/news/pressreleases.rss"),
    _rss("whitehouse-actions", "https://www.whitehouse.gov/presidential-actions/feed/", "politics", "geo", poll_s=300),
    _rss("whitehouse-briefings", "https://www.whitehouse.gov/briefings-statements/feed/", "politics", poll_s=300),
    _rss("fed-press", "https://www.federalreserve.gov/feeds/press_all.xml", "corp", "politics"),
    _rss("doj", "https://www.justice.gov/news/rss?type=press_release", "politics", "crypto", poll_s=300),
    # Truth Social: the API is Cloudflare-blocked from the VM; this RSS mirror
    # matched the API's timestamps in the probe. The post is the event.
    _rss("trumpstruth", "https://trumpstruth.org/feed", "politics", "geo", "corp", poll_s=60),
    # --- Bluesky (Jetstream; poll_s=0 means socket) ---
    _bsky("reuters.com", "geo", "politics", "corp"),
    _bsky("apnews.com", "geo", "politics"),
    _bsky("theguardian.com", "geo", "politics"),
    _bsky("washingtonpost.com", "politics", "geo"),
    _bsky("nytimes.com", "politics", "geo"),
    _bsky("wsj.com", "corp", "politics"),
    _bsky("cnbc.com", "corp"),
    _bsky("bloomberg.com", "corp", "politics"),
    _bsky("cnn.com", "politics", "geo"),
    _bsky("cbsnews.com", "politics"),
    _bsky("nbcnews.com", "politics"),
    _bsky("nypost.com", "politics"),
    _bsky("politico.com", "politics"),
    _bsky("axios.com", "politics", "corp"),
    _bsky("thehill.com", "politics"),
    _bsky("semafor.com", "politics", "corp"),
    _bsky("kyivindependent.com", "geo"),
    _bsky("kyivpost.com", "geo"),
    _bsky("noelreports.com", "geo"),
    _bsky("aljazeera.com", "geo"),
    _bsky("france24.com", "geo"),
    _bsky("timesofisrael.com", "geo"),
    _bsky("thetimes.com", "geo", "politics"),
    _bsky("deadline.com", "ent"),
    _bsky("billboard.com", "ent"),
    _bsky("popcrave.com", "ent"),
    _bsky("watcher.guru", "crypto", "corp"),
    _bsky("decrypt.co", "crypto"),
    _bsky("techcrunch.com", "corp"),
    _bsky("theverge.com", "corp"),
    _bsky("federalreserve.gov", "corp", "politics"),
    _bsky("polymarket.com", "politics", "crypto"),
    _bsky("unusualwhales.bsky.social", "corp", "politics"),
    # --- JSON APIs ---
    Source(key="toa", kind="toa", domains=("crypto", "corp"), poll_s=20,
           url="https://news.treeofalpha.com/api/news?limit=50"),
    Source(key="hn", kind="hn", domains=("corp",), poll_s=60,
           url="https://hn.algolia.com/api/v1/search_by_date?tags=story&hitsPerPage=50"),
)


def _env_key(key: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in key).upper()


def load(env=None, sources: tuple[Source, ...] = V1) -> list[Source]:
    """The roster after env: NEWS_SOURCES_DISABLE (comma list of keys),
    NEWS_DOMAINS (comma list; a source stays if any of its domains is in it),
    NEWS_POLL_<KEY>_S (per-source interval; the key with non-alphanumerics
    as underscores, upper-cased, e.g. NEWS_POLL_TG_FINANCIALJUICE_S=15)."""
    env = os.environ if env is None else env
    disabled = {k.strip() for k in (env.get("NEWS_SOURCES_DISABLE") or "").split(",") if k.strip()}
    raw_domains = (env.get("NEWS_DOMAINS") or "").strip()
    wanted = {d.strip() for d in raw_domains.split(",") if d.strip()} if raw_domains else set(DEFAULT_DOMAINS)
    out: list[Source] = []
    seen: set[str] = set()
    for s in sources:
        if s.key in seen:
            raise ValueError(f"duplicate roster key {s.key}")
        seen.add(s.key)
        if s.key in disabled or not (set(s.domains) & wanted):
            continue
        override = env.get(f"NEWS_POLL_{_env_key(s.key)}_S")
        if override and s.kind != "bsky":
            try:
                s = replace(s, poll_s=max(int(override), _floor(s)))
            except ValueError:
                pass
        out.append(s)
    return out


def _floor(s: Source) -> int:
    # Tree of Alpha caps at 30 req/min; Telegram pages are ~140 KB each.
    return {"toa": 20, "tg": 15}.get(s.kind, 10)


def by_kind(sources) -> dict[str, list[Source]]:
    out: dict[str, list[Source]] = {k: [] for k in KINDS}
    for s in sources:
        out[s.kind].append(s)
    return out


# --------------------------------------------------------------------------
# Counters
# --------------------------------------------------------------------------

def default_counters_path() -> Path:
    from src.config import CONFIG
    return Path(CONFIG.data_dir) / "news" / "roster.json"


class Counters:
    """Per-source tallies the brief and /news print: items, errors,
    last_ok_ts, last_item_ts (the newest published_ts seen), last_error.
    Persisted as JSON so a restart does not zero the roster's history."""

    FIELDS = ("items", "errors", "last_ok_ts", "last_item_ts", "last_error")

    def __init__(self, path: str | Path | None = None, save_every_s: float = 30.0):
        self.path = Path(path) if path is not None else default_counters_path()
        self.save_every_s = float(save_every_s)
        self._rows: dict[str, dict] = {}
        self._dirty = False
        self._last_save = 0.0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        rows = raw.get("sources") if isinstance(raw, dict) else None
        if isinstance(rows, dict):
            for k, v in rows.items():
                if isinstance(v, dict):
                    self._rows[k] = {"items": int(v.get("items") or 0), "errors": int(v.get("errors") or 0),
                                     "last_ok_ts": v.get("last_ok_ts"), "last_item_ts": v.get("last_item_ts"),
                                     "last_error": v.get("last_error")}

    def row(self, key: str) -> dict:
        return self._rows.setdefault(key, {"items": 0, "errors": 0, "last_ok_ts": None, "last_item_ts": None, "last_error": None})

    def ok(self, key: str, n_items: int, now: float, last_item_ts: float | None = None) -> None:
        r = self.row(key)
        r["items"] += int(n_items)
        r["last_ok_ts"] = float(now)
        if last_item_ts is not None and (r["last_item_ts"] is None or last_item_ts > r["last_item_ts"]):
            r["last_item_ts"] = float(last_item_ts)
        self._dirty = True

    def error(self, key: str, now: float, msg: str = "") -> None:
        r = self.row(key)
        r["errors"] += 1
        r["last_error"] = {"ts": float(now), "msg": str(msg)[:300]}
        self._dirty = True

    def snapshot(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in self._rows.items()}

    def save(self, now: float | None = None, force: bool = False) -> bool:
        """Atomic write, throttled to one per save_every_s unless forced."""
        now = time.time() if now is None else now
        if not self._dirty and not force:
            return False
        if not force and now - self._last_save < self.save_every_s:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"saved_ts": now, "sources": self._rows}, indent=0, sort_keys=True)
        fd, tmp = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self._dirty = False
        self._last_save = now
        return True
