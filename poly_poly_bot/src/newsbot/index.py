"""The market universe the news bot can map a headline onto (DESIGN.md, `index.py`).

Gamma's active, not-closed markets above a volume floor live in one SQLite file
with an FTS5 index over (question, description, event_title, tags, outcomes).
``candidates(text, k)`` ranks them by bm25 for a headline, boosts hits in the
question/event title, and penalises sports books and markets about to end —
the two shapes of market that a news item cannot be early on. Short crypto
up/down markets (5-minute and 15-minute windows) are never stored: they are
coin-flips on a price feed, not on news.

Refresh is incremental and tolerant (2026-10-25): every page is upserted as it
arrives, a failed page keeps the rows already on disk, and only a pass that
read the whole universe deletes the markets Gamma no longer lists (closed ones
vanish from ``active=true&closed=false``). Nothing here reads the network
except ``gamma_fetch_all``, which is the injectable ``fetch`` of ``refresh``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable, Iterator

logger = logging.getLogger("poly_poly_bot")

GAMMA_URL = "https://gamma-api.polymarket.com/markets"
# Gamma silently caps a page at 100 rows whatever ``limit`` says (observed
# 2026-10-25 with limit=500 -> 100 rows); the pager steps by what came back, so
# the cap costs nothing but extra requests. The cap of pages bounds a runaway.
GAMMA_PAGE_LIMIT = 500
GAMMA_MAX_PAGES = 120
DEFAULT_VOLUME_MIN_USD = 5000.0
ENDING_SOON_S = 2 * 3600

# Tag label/slug (lower-cased) -> domain. Static on purpose: the owner reads this
# table, the two-week report is cut by it, and a drifting classifier would make
# the per-domain numbers incomparable across days.
TAG_DOMAINS: dict[str, str] = {
    # politics
    "politics": "politics", "trump": "politics", "us election": "politics",
    "us-election": "politics", "congress": "politics", "elections": "politics",
    "us politics": "politics", "midterms": "politics", "senate": "politics",
    "house": "politics", "supreme court": "politics", "white house": "politics",
    "global elections": "politics", "world elections": "politics",
    "primaries": "politics", "key senate races": "politics", "governor": "politics",
    "epstein": "politics", "main election": "politics", "israel election": "politics",
    # geo
    "geopolitics": "geo", "israel": "geo", "iran": "geo", "ukraine": "geo",
    "russia": "geo", "china": "geo", "middle east": "geo", "war": "geo",
    "military": "geo", "military strikes": "geo", "military actions": "geo",
    "gaza": "geo", "nato": "geo", "foreign policy": "geo", "israel x iran": "geo",
    "putin": "geo", "zelensky": "geo", "zelenskyy": "geo", "yemen": "geo",
    "peace deal": "geo", "taiwan": "geo", "north korea": "geo", "venezuela": "geo",
    # crypto
    "crypto": "crypto", "bitcoin": "crypto", "ethereum": "crypto", "solana": "crypto",
    "sec crypto": "crypto", "crypto prices": "crypto", "stablecoins": "crypto",
    "defi": "crypto", "memecoins": "crypto", "xrp": "crypto", "dogecoin": "crypto",
    # corp (business / tech / macro)
    "business": "corp", "tech": "corp", "ai": "corp", "companies": "corp",
    "earnings": "corp", "ipo": "corp", "stocks": "corp", "fed": "corp",
    "economy": "corp", "fed rates": "corp", "fomc": "corp", "economic policy": "corp",
    "macro indicators": "corp", "finance": "corp", "openai": "corp", "big tech": "corp",
    "corporate financials": "corp", "us cpi": "corp", "inflation": "corp",
    "tariffs": "corp", "global rates": "corp", "kevin warsh": "corp", "nvidia": "corp",
    "tesla": "corp", "apple": "corp", "microsoft": "corp", "google": "corp",
    "anthropic": "corp", "spacex": "corp",
    # ent
    "culture": "ent", "pop culture": "ent", "movies": "ent", "music": "ent",
    "awards": "ent", "tv": "ent", "celebrities": "ent", "tweet markets": "ent",
    "entertainment": "ent", "oscars": "ent", "grammys": "ent", "box office": "ent",
    "elon musk": "ent",
}

# Any of these labels, or a label containing one of the fragments, marks a sports
# book (plus Gamma's own ``sportsMarketType``). Esports count: a match result is
# a match result, and no RSS feed is early on it.
SPORTS_TAGS = {
    "sports", "games", "soccer", "nfl", "nba", "mlb", "nhl", "epl", "la liga",
    "premier league", "basketball", "football", "tennis", "ufc", "mma", "f1",
    "formula 1", "golf", "cricket", "boxing", "hockey", "baseball", "esports",
    "league of legends", "counter strike 2", "cs2", "valorant", "dota 2", "nfl (all)",
    "ncaa", "college football", "ballon d'or", "wnba", "mls", "champions league",
    "serie a", "bundesliga", "ligue 1", "rugby", "olympics", "liga endesa",
}
SPORTS_FRAGMENTS = ("nfl", "nba", "mlb", "nhl", "ncaa", "esports", "league", "liga",
                    "premier", "worlds", "swiss stage", "swiss round", "counter strike",
                    "world cup", "grand slam", "playoffs")

# 5-minute and 15-minute crypto up/down books: ``btc-updown-5m-<ts>`` slugs,
# question "Bitcoin Up or Down - October 24, 9:45AM-10:00AM ET".
_UPDOWN_SLUG = re.compile(r"(^|-)updown-(5m|15m)(-|$)")
_UPDOWN_MINUTES = re.compile(r"\b(5|15)[- ]?(m|min|mins|minute|minutes)\b", re.I)
_UPDOWN_WINDOW = re.compile(
    r"(\d{1,2}):(\d{2})\s*(AM|PM)?\s*[-–]\s*(\d{1,2}):(\d{2})\s*(AM|PM)", re.I)

_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "by", "and", "or", "is", "are",
    "was", "were", "will", "be", "at", "as", "with", "from", "that", "this", "it",
    "its", "after", "before", "says", "said", "has", "have", "had", "over", "into",
    "than", "not", "no", "up", "down", "amid", "about", "his", "her", "their", "he",
    "she", "they", "we", "you", "i", "but", "if", "so", "do", "does", "did", "more",
    "new", "just", "now", "us", "vs", "breaking", "report", "reports", "live",
}
_TOKEN = re.compile(r"[a-z0-9]+")


class PageError(Exception):
    """One Gamma page failed; ``refresh`` keeps the rows it already has."""


GAMMA_OFFSET_CAP = 2000


def gamma_fetch_all(*, page_limit: int = GAMMA_PAGE_LIMIT, timeout_s: float = 20,
                    session=None, max_pages: int = GAMMA_MAX_PAGES) -> Iterator[list[dict]]:
    """Yield pages of active, open markets, highest 24h volume first.

    ``include_tag=true`` is required: without it Gamma returns ``events[].tags``
    empty and the market has no ``tags`` key at all (checked 2026-10-25), and
    the domain map would see nothing. A failed page raises ``PageError``.
    """
    import requests  # local: the index is importable without the network stack

    sess = session or requests.Session()
    offset = 0
    for _ in range(max_pages):
        params = {
            "active": "true", "closed": "false", "limit": page_limit, "offset": offset,
            "order": "volume24hr", "ascending": "false", "include_tag": "true",
        }
        try:
            resp = sess.get(GAMMA_URL, params=params, timeout=timeout_s)
            if getattr(resp, "status_code", None) == 422 and offset >= GAMMA_OFFSET_CAP:
                # Gamma refuses offsets past ~2000 with a 422 (seen live
                # 2026-10-25 at offset=2100). Sorted by 24h volume, the first
                # 2000 are the whole universe we price; the pass is complete.
                return
            resp.raise_for_status()
            page = resp.json()
        except Exception as e:  # noqa: BLE001 - any failure is "this page failed"
            raise PageError(f"gamma offset={offset}: {e!r}") from e
        if not isinstance(page, list) or not page:
            return
        yield page
        offset += len(page)


@dataclass(frozen=True)
class Candidate:
    market_id: str
    condition_id: str
    question: str
    event_title: str
    tags: tuple[str, ...]
    domains: tuple[str, ...]
    outcomes: list[str]
    token_ids: list[str]      # aligned with ``outcomes``
    best_bid: float | None
    best_ask: float | None
    end_ts: float | None
    is_sports: bool
    slug: str = ""
    prices: list[float] = field(default_factory=list)   # Gamma outcomePrices, aligned
    last_price: float | None = None
    neg_risk: bool = False
    score: float = 0.0          # ranking score of the query that produced it (higher = better)


# ---------------------------------------------------------------------------
# pure helpers (unit-tested on their own)

def _lower_labels(tags: Iterable[dict | str]) -> list[str]:
    out: list[str] = []
    for t in tags or ():
        if isinstance(t, dict):
            for key in ("label", "slug"):
                v = t.get(key)
                if v:
                    out.append(str(v).strip().lower())
        elif t:
            out.append(str(t).strip().lower())
    return out


def market_tags(m: dict) -> list[str]:
    """Display labels, deduplicated, from the market's own ``tags`` (present with
    ``include_tag=true``) with the event's tags as the fallback."""
    seen: dict[str, None] = {}
    for src in (m.get("tags") or [], *[(ev.get("tags") or []) for ev in (m.get("events") or []) if isinstance(ev, dict)]):
        for t in src:
            label = (t.get("label") if isinstance(t, dict) else t) or ""
            label = str(label).strip()
            if label:
                seen.setdefault(label, None)
    return list(seen)


def is_sports_market(m: dict, tags: list[str] | None = None) -> bool:
    if m.get("sportsMarketType"):
        return True
    for lab in _lower_labels(tags if tags is not None else market_tags(m)):
        if lab in SPORTS_TAGS or any(frag in lab for frag in SPORTS_FRAGMENTS):
            return True
    return False


def derive_domains(tags: Iterable[str], is_sports: bool) -> tuple[str, ...]:
    found: dict[str, None] = {}
    for lab in _lower_labels(tags):
        dom = TAG_DOMAINS.get(lab)
        if dom is None and "election" in lab:
            dom = "politics"
        if dom is None and ("ceasefire" in lab or lab.endswith(" war") or lab == "war"):
            dom = "geo"
        if dom:
            found.setdefault(dom, None)
    if is_sports:
        found.setdefault("sport", None)
    return tuple(found)


def is_short_updown(question: str | None, slug: str | None) -> bool:
    """The static exclusion: a crypto up/down book over a 5 or 15 minute window."""
    if slug and _UPDOWN_SLUG.search(slug.lower()):
        return True
    q = (question or "").strip()
    if "up or down" not in q.lower():
        return False
    if _UPDOWN_MINUTES.search(q):
        return True
    m = _UPDOWN_WINDOW.search(q)
    if not m:
        return False
    h1, m1, ap1, h2, m2, ap2 = m.groups()
    ap1 = (ap1 or ap2).upper()
    ap2 = ap2.upper()

    def _mins(h: str, mm: str, ap: str) -> int:
        hh = int(h) % 12 + (12 if ap == "PM" else 0)
        return hh * 60 + int(mm)

    span = (_mins(h2, m2, ap2) - _mins(h1, m1, ap1)) % (24 * 60)
    return 0 < span <= 15


def _parse_json_list(v) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    try:
        out = json.loads(v)
    except (TypeError, ValueError):
        return []
    return out if isinstance(out, list) else []


def _parse_end_ts(v) -> float | None:
    if not v:
        return None
    try:
        s = str(v).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _float(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def query_tokens(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for tok in _TOKEN.findall((text or "").lower()):
        if len(tok) < 2 or tok in _STOPWORDS:
            continue
        seen.setdefault(tok, None)
    return list(seen)


def fts5_available() -> bool:
    try:
        con = sqlite3.connect(":memory:")
        try:
            con.execute("CREATE VIRTUAL TABLE t USING fts5(a)")
        finally:
            con.close()
        return True
    except sqlite3.OperationalError:
        return False


# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL UNIQUE,
    condition_id TEXT,
    question TEXT NOT NULL DEFAULT '',
    slug TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    event_title TEXT NOT NULL DEFAULT '',
    event_slug TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    outcomes TEXT NOT NULL DEFAULT '[]',
    token_ids TEXT NOT NULL DEFAULT '[]',
    prices TEXT NOT NULL DEFAULT '[]',
    best_bid REAL, best_ask REAL, last_price REAL, volume24h REAL, volume REAL,
    end_ts REAL, neg_risk INTEGER NOT NULL DEFAULT 0, is_sports INTEGER NOT NULL DEFAULT 0,
    domains TEXT NOT NULL DEFAULT '',
    seen_pass INTEGER NOT NULL DEFAULT 0,
    updated_ts REAL
);
CREATE INDEX IF NOT EXISTS markets_condition ON markets(condition_id);
CREATE TABLE IF NOT EXISTS tokens (
    token_id TEXT PRIMARY KEY,
    market_id TEXT NOT NULL,
    outcome_index INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS tokens_market ON tokens(market_id);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS markets_fts USING fts5(
    question, description, event_title, tags, outcomes,
    content='markets', content_rowid='id', tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS markets_ai AFTER INSERT ON markets BEGIN
    INSERT INTO markets_fts(rowid, question, description, event_title, tags, outcomes)
    VALUES (new.id, new.question, new.description, new.event_title, new.tags, new.outcomes);
END;
CREATE TRIGGER IF NOT EXISTS markets_ad AFTER DELETE ON markets BEGIN
    INSERT INTO markets_fts(markets_fts, rowid, question, description, event_title, tags, outcomes)
    VALUES ('delete', old.id, old.question, old.description, old.event_title, old.tags, old.outcomes);
END;
CREATE TRIGGER IF NOT EXISTS markets_au AFTER UPDATE ON markets BEGIN
    INSERT INTO markets_fts(markets_fts, rowid, question, description, event_title, tags, outcomes)
    VALUES ('delete', old.id, old.question, old.description, old.event_title, old.tags, old.outcomes);
    INSERT INTO markets_fts(rowid, question, description, event_title, tags, outcomes)
    VALUES (new.id, new.question, new.description, new.event_title, new.tags, new.outcomes);
END;
"""

_COLUMNS = ("market_id", "condition_id", "question", "slug", "description", "event_title",
            "event_slug", "tags", "outcomes", "token_ids", "prices", "best_bid", "best_ask",
            "last_price", "volume24h", "volume", "end_ts", "neg_risk", "is_sports", "domains")
_SELECT = "SELECT " + ", ".join(_COLUMNS) + " FROM markets"

# bm25 column weights: a headline naming the question or the event title is the
# match that matters; description text is long and generic, so it counts least.
_BM25_WEIGHTS = (5.0, 0.5, 4.0, 2.0, 1.0)
_LIKE_WEIGHTS = {"question": 5.0, "description": 0.5, "event_title": 4.0, "tags": 2.0, "outcomes": 1.0}
SPORTS_PENALTY = 0.35
ENDING_SOON_PENALTY = 0.5


class MarketIndex:
    def __init__(self, path: str | os.PathLike, *, volume_min: float | None = None,
                 use_fts: bool | None = None):
        self.path = str(path)
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.volume_min = float(
            os.environ.get("NEWS_INDEX_VOLUME_MIN", DEFAULT_VOLUME_MIN_USD) if volume_min is None else volume_min)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self.fts = fts5_available() if use_fts is None else bool(use_fts)
        if self.fts:
            try:
                self._db.executescript(_FTS_SCHEMA)
                # A store written by a build without FTS5 has rows the triggers
                # never saw; rebuild from content once so search sees them.
                n_fts = self._db.execute("SELECT count(*) FROM markets_fts").fetchone()[0]
                n_rows = self._db.execute("SELECT count(*) FROM markets").fetchone()[0]
                if n_fts != n_rows:
                    self._db.execute("INSERT INTO markets_fts(markets_fts) VALUES('rebuild')")
                self._db.commit()
            except sqlite3.OperationalError as e:
                logger.warning("[news-index] FTS5 unavailable (%s) — LIKE search fallback", e)
                self.fts = False
        else:
            logger.warning("[news-index] sqlite lacks FTS5 — LIKE search fallback")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- refresh -------------------------------------------------------------

    def refresh(self, fetch: Callable[[], Iterable[list[dict]]] = gamma_fetch_all, *,
                now: float | None = None) -> dict:
        """Pull the universe through ``fetch`` (an iterable of pages) and upsert it.

        Returns the pass summary. ``complete`` is true only when every page was
        read and the pass saw at least one row; only then are unseen rows (closed,
        delisted, or fallen under the floor) deleted.
        """
        now = time.time() if now is None else float(now)
        with self._lock:
            pass_no = int(self._meta_get("pass_no", "0") or 0) + 1
            self._meta_set("pass_no", str(pass_no))
        summary = {"pass": pass_no, "pages": 0, "rows": 0, "upserted": 0, "deleted": 0,
                   "skipped_volume": 0, "skipped_updown": 0, "skipped_closed": 0,
                   "complete": False, "error": None}
        try:
            for page in fetch():
                summary["pages"] += 1
                with self._lock, self._db:
                    for m in page or ():
                        summary["rows"] += 1
                        kind = self._upsert_market(m, pass_no, now)
                        summary[kind] += 1
            summary["complete"] = summary["rows"] > 0
        except PageError as e:
            summary["error"] = str(e)
            logger.warning("[news-index] refresh partial after %d page(s): %s — old rows kept",
                           summary["pages"], e)
        except Exception as e:  # noqa: BLE001 - a refresh must never take the bot down
            summary["error"] = repr(e)
            logger.warning("[news-index] refresh aborted after %d page(s): %r — old rows kept",
                           summary["pages"], e)
        with self._lock, self._db:
            if summary["complete"]:
                gone = [r[0] for r in self._db.execute(
                    "SELECT market_id FROM markets WHERE seen_pass <> ?", (pass_no,))]
                for mid in gone:
                    self._delete_market(mid)
                summary["deleted"] = len(gone)
                self._meta_set("last_full_refresh_ts", repr(now))
            if summary["pages"]:
                self._meta_set("last_refresh_ts", repr(now))
        logger.info("[news-index] refresh pass=%d pages=%d rows=%d upserted=%d deleted=%d "
                    "skipped(volume=%d updown=%d closed=%d) complete=%s",
                    pass_no, summary["pages"], summary["rows"], summary["upserted"],
                    summary["deleted"], summary["skipped_volume"], summary["skipped_updown"],
                    summary["skipped_closed"], summary["complete"])
        return summary

    def _upsert_market(self, m: dict, pass_no: int, now: float) -> str:
        market_id = str(m.get("id") or "")
        if not market_id:
            return "skipped_closed"
        if m.get("closed") or m.get("active") is False or m.get("archived"):
            self._delete_market(market_id)
            return "skipped_closed"
        question = str(m.get("question") or "")
        slug = str(m.get("slug") or "")
        if is_short_updown(question, slug):
            self._delete_market(market_id)
            return "skipped_updown"
        volume = _float(m.get("volumeNum"))
        if volume is None:
            volume = _float(m.get("volume"))
        if (volume or 0.0) < self.volume_min:
            self._delete_market(market_id)
            return "skipped_volume"
        tags = market_tags(m)
        sports = is_sports_market(m, tags)
        domains = derive_domains(tags, sports)
        ev = next((e for e in (m.get("events") or []) if isinstance(e, dict)), {})
        outcomes = [str(o) for o in _parse_json_list(m.get("outcomes"))]
        token_ids = [str(t) for t in _parse_json_list(m.get("clobTokenIds"))]
        prices = [p for p in (_float(x) for x in _parse_json_list(m.get("outcomePrices"))) if p is not None]
        row = {
            "market_id": market_id,
            "condition_id": str(m.get("conditionId") or ""),
            "question": question,
            "slug": slug,
            "description": str(m.get("description") or ""),
            "event_title": str(ev.get("title") or ""),
            "event_slug": str(ev.get("slug") or ""),
            "tags": ", ".join(tags),
            "outcomes": json.dumps(outcomes),
            "token_ids": json.dumps(token_ids),
            "prices": json.dumps(prices),
            "best_bid": _float(m.get("bestBid")),
            "best_ask": _float(m.get("bestAsk")),
            "last_price": _float(m.get("lastTradePrice")),
            "volume24h": _float(m.get("volume24hr")),
            "volume": volume,
            "end_ts": _parse_end_ts(m.get("endDate")),
            "neg_risk": 1 if m.get("negRisk") else 0,
            "is_sports": 1 if sports else 0,
            "domains": ",".join(domains),
            "seen_pass": pass_no,
            "updated_ts": now,
        }
        cols = list(row)
        sets = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "market_id")
        self._db.execute(
            f"INSERT INTO markets ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)}) "
            f"ON CONFLICT(market_id) DO UPDATE SET {sets}", row)
        self._db.execute("DELETE FROM tokens WHERE market_id = ?", (market_id,))
        self._db.executemany(
            "INSERT OR REPLACE INTO tokens (token_id, market_id, outcome_index) VALUES (?, ?, ?)",
            [(tid, market_id, i) for i, tid in enumerate(token_ids) if tid])
        return "upserted"

    def _delete_market(self, market_id: str) -> None:
        self._db.execute("DELETE FROM tokens WHERE market_id = ?", (market_id,))
        self._db.execute("DELETE FROM markets WHERE market_id = ?", (market_id,))

    def _meta_get(self, key: str, default: str | None = None) -> str | None:
        r = self._db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return default if r is None else r[0]

    def _meta_set(self, key: str, value: str) -> None:
        self._db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    # -- lookups -------------------------------------------------------------

    @staticmethod
    def _row_to_candidate(r: sqlite3.Row, score: float = 0.0) -> Candidate:
        return Candidate(
            market_id=r["market_id"], condition_id=r["condition_id"] or "",
            question=r["question"], event_title=r["event_title"],
            tags=tuple(t for t in (r["tags"] or "").split(", ") if t),
            domains=tuple(d for d in (r["domains"] or "").split(",") if d),
            outcomes=list(json.loads(r["outcomes"] or "[]")),
            token_ids=list(json.loads(r["token_ids"] or "[]")),
            best_bid=r["best_bid"], best_ask=r["best_ask"], end_ts=r["end_ts"],
            is_sports=bool(r["is_sports"]), slug=r["slug"] or "",
            prices=list(json.loads(r["prices"] or "[]")), last_price=r["last_price"],
            neg_risk=bool(r["neg_risk"]), score=score,
        )

    def by_market(self, market_id: str) -> Candidate | None:
        with self._lock:
            r = self._db.execute(_SELECT + " WHERE market_id = ?", (str(market_id),)).fetchone()
        return None if r is None else self._row_to_candidate(r)

    def by_token(self, token_id: str) -> Candidate | None:
        with self._lock:
            r = self._db.execute(
                _SELECT + " WHERE market_id = (SELECT market_id FROM tokens WHERE token_id = ?)",
                (str(token_id),)).fetchone()
        return None if r is None else self._row_to_candidate(r)

    def by_condition(self, condition_id: str) -> Candidate | None:
        """The market behind a conditionId (the tape's key, 2026-10-25)."""
        with self._lock:
            r = self._db.execute(_SELECT + " WHERE condition_id = ?", (str(condition_id),)).fetchone()
        return None if r is None else self._row_to_candidate(r)

    def outcome_index(self, token_id: str) -> int | None:
        with self._lock:
            r = self._db.execute("SELECT outcome_index FROM tokens WHERE token_id = ?",
                                 (str(token_id),)).fetchone()
        return None if r is None else int(r[0])

    def all_token_ids(self, domains: Iterable[str] | None = None) -> list[str]:
        wanted = set(domains) if domains else None
        out: list[str] = []
        with self._lock:
            for r in self._db.execute("SELECT token_ids, domains FROM markets ORDER BY volume24h DESC"):
                if wanted is not None and not (wanted & set((r["domains"] or "").split(","))):
                    continue
                out.extend(json.loads(r["token_ids"] or "[]"))
        return out

    def stats(self) -> dict:
        with self._lock:
            n = self._db.execute("SELECT count(*) FROM markets").fetchone()[0]
            by_domain: dict[str, int] = {}
            n_sports = 0
            for r in self._db.execute("SELECT domains, is_sports FROM markets"):
                n_sports += int(r["is_sports"] or 0)
                for d in (r["domains"] or "").split(","):
                    if d:
                        by_domain[d] = by_domain.get(d, 0) + 1
            last = self._meta_get("last_refresh_ts")
            last_full = self._meta_get("last_full_refresh_ts")
        return {
            "n_markets": int(n), "by_domain": by_domain, "n_sports": n_sports,
            "last_refresh_ts": float(last) if last else None,
            "last_full_refresh_ts": float(last_full) if last_full else None,
            "fts5": self.fts, "volume_min": self.volume_min,
        }

    # -- search --------------------------------------------------------------

    def candidates(self, text: str, k: int = 8, domains: Iterable[str] | None = None,
                   *, now: float | None = None) -> list[Candidate]:
        """Top-k markets for a headline. Higher ``score`` is better; sports books and
        markets ending within two hours (or already past their end date) are
        penalised rather than dropped, so a thin universe still returns something."""
        tokens = query_tokens(text)
        if not tokens:
            return []
        now = time.time() if now is None else float(now)
        wanted = set(domains) if domains else None
        pool = max(k * 6, 40)
        with self._lock:
            rows = self._fts_rows(tokens, pool) if self.fts else self._like_rows(tokens, pool)
        ranked: list[Candidate] = []
        for r, raw in rows:
            if raw <= 0:
                continue
            doms = set((r["domains"] or "").split(","))
            if wanted is not None and not (wanted & doms):
                continue
            score = raw
            if r["is_sports"]:
                score *= SPORTS_PENALTY
            end_ts = r["end_ts"]
            if end_ts is not None and end_ts - now < ENDING_SOON_S:
                score *= ENDING_SOON_PENALTY
            ranked.append(self._row_to_candidate(r, round(score, 4)))
        ranked.sort(key=lambda c: (-c.score, c.market_id))
        return ranked[:k]

    def _fts_rows(self, tokens: list[str], pool: int) -> list[tuple[sqlite3.Row, float]]:
        query = " OR ".join('"' + t.replace('"', '""') + '"' for t in tokens)
        # columns qualified: the FTS table shares names (question, tags, ...) with markets
        sql = ("SELECT " + ", ".join(f"markets.{c}" for c in _COLUMNS)
               + ", -bm25(markets_fts, ?, ?, ?, ?, ?) AS raw "
               "FROM markets_fts JOIN markets ON markets.id = markets_fts.rowid "
               "WHERE markets_fts MATCH ? ORDER BY raw DESC LIMIT ?")
        try:
            cur = self._db.execute(sql, (*_BM25_WEIGHTS, query, pool))
        except sqlite3.OperationalError as e:
            logger.warning("[news-index] fts query failed (%s) — falling back to LIKE", e)
            return self._like_rows(tokens, pool)
        return [(r, float(r["raw"])) for r in cur.fetchall()]

    def _like_rows(self, tokens: list[str], pool: int) -> list[tuple[sqlite3.Row, float]]:
        """No FTS5: a weighted count of token hits per column, scanning only rows
        where some token appears somewhere."""
        hay = "lower(question || ' ' || description || ' ' || event_title || ' ' || tags || ' ' || outcomes)"
        where = " OR ".join(f"{hay} LIKE ?" for _ in tokens)
        params = [f"%{t}%" for t in tokens]
        out: list[tuple[sqlite3.Row, float]] = []
        for r in self._db.execute(_SELECT + f" WHERE {where}", params):
            score = 0.0
            for col, w in _LIKE_WEIGHTS.items():
                text = (r[col] or "").lower()
                score += w * sum(1 for t in tokens if t in text)
            if score > 0:
                out.append((r, score))
        out.sort(key=lambda x: -x[1])
        return out[:pool]
