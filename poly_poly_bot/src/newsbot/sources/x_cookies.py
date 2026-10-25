"""X (Twitter) through the owner's own logged-in session: ONE private List
timeline, polled every X_POLL_S seconds with twscrape.

There is no free X API. The owner approved using HIS OWN account's two
session cookies (`auth_token`, `ct0`) with an unofficial GraphQL client,
having been told this is against X's terms and that a flagged account is
his risk. So the request volume stays where a human reading one List would
be: one request every 45-60 s against one List timeline (the List is where
he puts the flash accounts), never a per-account timeline, never a tight
retry. A rate limit or a rejected session raises `SourceError` so the loop
backs off (double, cap 30 min) and logs once per episode.

Config (env):
    X_AUTH_TOKEN   the `auth_token` cookie of a logged-in x.com session
    X_CT0          the `ct0` cookie of the same session
    X_LIST_ID      the List's numeric id (x.com/i/lists/<id>; the URL is accepted too)
    X_POLL_S       optional, default 50, floor 30
    X_DOMAINS      optional comma list applied to every item
                   (default politics,geo,crypto,corp)
    X_ACCOUNTS_DB  optional path of twscrape's accounts db
                   (default <data_dir>/news/x-accounts.db)

The cookies ARE the login (as sensitive as the password). They go into
twscrape's accounts db on disk and nowhere else; no log line, counter row or
exception message ever carries them (`scrub` is applied to every message
that could have come from the library). twscrape's own PostHog telemetry is
switched off before the library is imported.

Items: `id = x:<tweet id>`, `source = x:<username>` (lower-case), the
List's domains, `published_ts` = the tweet's own date (UTC), title = the
first 200 chars, text = the full text with t.co links expanded, `url` = the
tweet's URL. Pure retweets are skipped (the original lands through the List
when its author is on it; otherwise it is someone else's news). Quote
tweets stay, with the quoted text appended. The roster counter row is `x`
(one row per polled thing: the List), not one per account.
"""
from __future__ import annotations

import asyncio
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.logger import logger
from src.newsbot.items import NO_TIMESTAMP_FLAG, Item, SourceError, make_id

ENV_AUTH_TOKEN = "X_AUTH_TOKEN"
ENV_CT0 = "X_CT0"
ENV_LIST_ID = "X_LIST_ID"
ENV_POLL_S = "X_POLL_S"
ENV_DOMAINS = "X_DOMAINS"
ENV_DB = "X_ACCOUNTS_DB"

KEY = "x"                      # the roster counter row and the id prefix
ACCOUNT_NAME = "cookie-session"  # twscrape needs a username for its db row; the cookies are the login
QUEUE = "ListLatestTweetsTimeline"  # twscrape's lock key for the list endpoint
DEFAULT_POLL_S = 75
MIN_POLL_S = 30
MAX_BACKOFF_S = 1800
PAGE_LIMIT = 20                # X's page size: one GraphQL request per poll once the List holds 20 posts
DEFAULT_DOMAINS = ("politics", "geo", "crypto", "corp")
TITLE_CHARS = 200
TEXT_CHARS = 2000

_LIST_URL = re.compile(r"/lists/(\d+)")
_WS = re.compile(r"\s+")


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    auth_token: str
    ct0: str
    list_id: int
    poll_s: int = DEFAULT_POLL_S
    domains: tuple = DEFAULT_DOMAINS
    db_path: str = ""          # "" -> default_db_path() at make_api time

    @property
    def ok(self) -> bool:
        return bool(self.auth_token and self.ct0 and self.list_id > 0)

    @property
    def cookies(self) -> str:
        """The cookie header twscrape stores; never log it."""
        return f"auth_token={self.auth_token}; ct0={self.ct0}"


def parse_list_id(raw: str | None) -> int:
    """'1234567890' or 'https://x.com/i/lists/1234567890' -> 1234567890; anything else -> 0."""
    s = (raw or "").strip()
    if not s:
        return 0
    m = _LIST_URL.search(s)
    if m:
        s = m.group(1)
    return int(s) if s.isdigit() and int(s) > 0 else 0


def parse_poll_s(raw: str | None) -> int:
    s = (raw or "").strip()
    try:
        v = int(s) if s else DEFAULT_POLL_S
    except ValueError:
        v = DEFAULT_POLL_S
    return max(v, MIN_POLL_S)


def parse_domains(raw: str | None) -> tuple:
    """A comma list filtered to the roster's known domains; empty/invalid -> the default."""
    from src.newsbot.sources.roster import DOMAINS
    got = tuple(dict.fromkeys(d.strip().lower() for d in (raw or "").split(",") if d.strip().lower() in DOMAINS))
    return got or DEFAULT_DOMAINS


def config_from_env(env=None) -> Config:
    env = os.environ if env is None else env
    return Config(
        auth_token=(env.get(ENV_AUTH_TOKEN) or "").strip(),
        ct0=(env.get(ENV_CT0) or "").strip(),
        list_id=parse_list_id(env.get(ENV_LIST_ID)),
        poll_s=parse_poll_s(env.get(ENV_POLL_S)),
        domains=parse_domains(env.get(ENV_DOMAINS)),
        db_path=(env.get(ENV_DB) or "").strip(),
    )


def enabled(env=None) -> bool:
    """Both cookies and a numeric list id present."""
    return config_from_env(env).ok


def default_db_path() -> Path:
    from src.config import CONFIG
    return Path(CONFIG.data_dir) / "news" / "x-accounts.db"


def scrub(msg: str, cfg: Config | None) -> str:
    """Strip the two cookies out of any text that might be logged."""
    s = str(msg)
    if cfg is not None:
        for secret in (cfg.auth_token, cfg.ct0):
            if secret and len(secret) >= 8:
                s = s.replace(secret, "***")
    return s


# --------------------------------------------------------------------------
# Tweet -> Item
# --------------------------------------------------------------------------

def source_key(username: str | None) -> str:
    u = str(username or "").strip().lstrip("@").lower()
    return f"{KEY}:{u or 'unknown'}"


def tweet_text(tweet) -> str:
    """rawContent with every t.co link replaced by its expanded URL."""
    text = str(getattr(tweet, "rawContent", None) or "").strip()
    for link in getattr(tweet, "links", None) or ():
        short = getattr(link, "tcourl", None)
        full = getattr(link, "url", None)
        if isinstance(short, str) and isinstance(full, str) and short and full and short in text:
            text = text.replace(short, full)
    return text


def make_title(text: str, limit: int = TITLE_CHARS) -> str:
    one = _WS.sub(" ", text).strip()
    return one if len(one) <= limit else one[: limit - 1].rstrip() + "…"


def _published(tweet) -> float | None:
    date = getattr(tweet, "date", None)
    if date is None:
        return None
    try:
        if isinstance(date, datetime):
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            return float(date.timestamp())
        return float(date)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def tweet_to_item(tweet, seen_ts: float, domains: tuple = DEFAULT_DOMAINS) -> Item | None:
    """One twscrape Tweet -> Item; None for a pure retweet, a tweet without
    an id, or one with no text at all (media-only: nothing to judge)."""
    tid = getattr(tweet, "id", None)
    if tid is None:
        tid = getattr(tweet, "id_str", None)
    if tid is None:
        return None
    if getattr(tweet, "retweetedTweet", None) is not None:
        return None
    user = getattr(tweet, "user", None)
    username = str(getattr(user, "username", None) or "").strip().lstrip("@")
    text = tweet_text(tweet)
    quoted = getattr(tweet, "quotedTweet", None)
    if quoted is not None:
        qtext = tweet_text(quoted)
        if qtext:
            quser = str(getattr(getattr(quoted, "user", None), "username", None) or "").strip().lstrip("@")
            prefix = f"QT @{quser}: " if quser else "QT: "
            text = f"{text}\n\n{prefix}{qtext}".strip()
    if not text:
        return None
    published = _published(tweet)
    if published is None:
        text = f"{NO_TIMESTAMP_FLAG} {text}"
        published = float(seen_ts)
    url = str(getattr(tweet, "url", None) or "") or f"https://x.com/{username or 'i'}/status/{tid}"
    return Item(
        id=make_id(KEY, str(tid)), source=source_key(username), domains=tuple(domains) or DEFAULT_DOMAINS,
        published_ts=published, seen_ts=float(seen_ts),
        title=make_title(text), text=text[:TEXT_CHARS], url=url,
    )


# --------------------------------------------------------------------------
# twscrape glue (every import of the library lives here, so the tests and a
# box without it never touch it)
# --------------------------------------------------------------------------

async def make_api(cfg: Config):
    """An `twscrape.API` over our own accounts db with the owner's cookies as
    its one account. `raise_when_no_account=True` is essential: without it a
    rate-limited or deactivated account makes the library sleep forever in a
    5 s loop instead of telling us."""
    # twscrape posts usage events to PostHog unless told not to; the owner's
    # scraping of his own feed is nobody else's business.
    os.environ.setdefault("TWS_TELEMETRY", "0")
    try:
        from twscrape import API
        from twscrape.logger import set_log_level
    except ImportError as e:
        raise SourceError("twscrape not installed (pip install twscrape)") from e
    set_log_level("WARNING")  # its loguru goes to stderr; INFO is per-request chatter
    db = Path(cfg.db_path) if cfg.db_path else default_db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    api = API(str(db), raise_when_no_account=True)
    # Upsert: a new deploy with fresh cookies re-activates the row twscrape
    # may have marked inactive when the old session died.
    await api.pool.add_account_cookies(ACCOUNT_NAME, cfg.cookies)
    return api


async def account_trouble(api) -> str | None:
    """Why the account cannot serve right now, from twscrape's own row:
    'auth: ...' when it marked the session inactive (expired / banned),
    'rate-limited until ...' when the list endpoint is locked. None when
    the row looks healthy or the api exposes no pool (a fake)."""
    pool = getattr(api, "pool", None)
    get = getattr(pool, "get", None)
    if get is None:
        return None
    try:
        acc = await get(ACCOUNT_NAME)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - a db hiccup is not a verdict on the account
        return None
    if acc is None:
        return "auth: account row missing from the accounts db"
    if not getattr(acc, "active", True):
        why = getattr(acc, "error_msg", None) or "session expired or banned"
        return f"auth: {why}; refresh X_AUTH_TOKEN / X_CT0"
    lock = (getattr(acc, "locks", None) or {}).get(QUEUE)
    if lock is not None:
        try:
            until = lock.isoformat() if isinstance(lock, datetime) else str(lock)
        except Exception:  # noqa: BLE001
            until = "?"
        return f"rate-limited until {until}"
    return None


def _is_no_account(e: BaseException) -> bool:
    return type(e).__name__ == "NoAccountError"


def _is_gql_outdated(e: BaseException) -> bool:
    return type(e).__name__ == "GqlFeaturesOutdatedError"


# --------------------------------------------------------------------------
# One poll
# --------------------------------------------------------------------------

async def fetch(state: dict, dedup, counters, *, api=None, now: float | None = None, cfg: Config | None = None,
                env=None) -> list[Item]:
    """One request against the List; the new Items (oldest first), already
    recorded in `dedup` and counted on the `x` row. Raises SourceError (and
    counts the error) when the session is rejected, the endpoint is
    rate-limited, or the library says its query ids are stale; the caller
    backs off. Transport errors propagate as themselves."""
    cfg = cfg or config_from_env(env)
    now = time.time() if now is None else float(now)
    if api is None:
        if not cfg.ok:
            raise SourceError(f"disabled: {ENV_AUTH_TOKEN} / {ENV_CT0} / {ENV_LIST_ID} not all set")
        api = state.get("api")
        if api is None:
            api = state["api"] = await make_api(cfg)
    read = 0
    items: list[Item] = []
    try:
        async for tw in api.list_timeline(cfg.list_id, limit=PAGE_LIMIT):
            read += 1
            item = tweet_to_item(tw, now, cfg.domains)
            if item is not None:
                items.append(item)
        if read == 0:
            trouble = await account_trouble(api)
            if trouble:
                raise SourceError(trouble)
    except asyncio.CancelledError:
        raise
    except SourceError as e:
        msg = scrub(str(e), cfg)
        counters.error(KEY, now, msg)
        raise SourceError(msg) from None
    except Exception as e:  # noqa: BLE001 - sort the library's failures into "back off" vs "transport"
        if _is_no_account(e):
            trouble = await account_trouble(api)
            msg = scrub(trouble or "no usable account (rate-limited or session rejected)", cfg)
            counters.error(KEY, now, msg)
            raise SourceError(msg) from None
        if _is_gql_outdated(e):
            msg = "twscrape GraphQL query ids outdated; upgrade twscrape"
            counters.error(KEY, now, msg)
            raise SourceError(msg) from None
        counters.error(KEY, now, scrub(f"{type(e).__name__}: {e}", cfg))
        raise
    state["empty_streak"] = 0 if read else int(state.get("empty_streak", 0)) + 1
    state["last_read"] = read
    state["last_ok_ts"] = now
    items.sort(key=lambda it: it.published_ts)
    new = [it for it in items if dedup.add(it.id)]
    newest = max((it.published_ts for it in new), default=None)
    counters.ok(KEY, len(new), now, newest)
    return new


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------

async def _pause(stop: asyncio.Event, seconds: float, sleep) -> None:
    """Sleep `seconds` or until `stop`, whichever comes first (a 30-minute
    backoff must not outlive a shutdown)."""
    sleeper = asyncio.ensure_future(sleep(seconds))
    stopper = asyncio.ensure_future(stop.wait())
    try:
        await asyncio.wait({sleeper, stopper}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for fut in (sleeper, stopper):
            if not fut.done():
                fut.cancel()


# A fixed poll interval is the easiest bot tell X has: a request landing every
# N seconds to the millisecond, around the clock. The owner asked for a human
# shape (2026-10-25). next_interval draws a heavy-tailed jitter around the base
# (most reads 0.5-2x, a one-in-seven "distracted" long gap), and slows down in
# the owner's local small hours, so the series looks like a person glancing at a
# list, not a cron. The base stays the knob (X_POLL_S); the median active gap is
# about the base, the account never reads faster than MIN_POLL_S.
def _local_hour(now: float, offset_h: float) -> int:
    return int(((now / 3600.0) + offset_h) % 24)


def _is_quiet(now: float, offset_h: float) -> bool:
    return 2 <= _local_hour(now, offset_h) < 9     # asleep: 02:00-09:00 local


def next_interval(base: float, now: float, rng: random.Random, *,
                  quiet_offset_h: float = 8.0, min_s: float = MIN_POLL_S) -> float:
    """A human-looking gap before the next read, in seconds."""
    iv = base * rng.lognormvariate(0.0, 0.45)      # median 1x, mostly 0.5-2x, heavy tail
    if rng.random() < 0.15:                        # a glance that did not happen
        iv *= rng.uniform(3.0, 7.0)
    if _is_quiet(now, quiet_offset_h):             # fewer reads while the owner sleeps
        iv *= rng.uniform(2.5, 5.0)
    return max(float(min_s), iv)


async def run(queue: asyncio.Queue, dedup, counters, *, stop: asyncio.Event, api=None, sleep=asyncio.sleep,
              clock=time.time, env=None, cfg: Config | None = None, max_backoff_s: float = MAX_BACKOFF_S,
              rng: random.Random | None = None, quiet_offset_h: float = 8.0) -> None:
    """Poll the List every `poll_s` until `stop` is set, putting new Items on
    `queue`. A SourceError doubles the interval (cap `max_backoff_s`) and is
    logged once per episode; a transport error keeps the base interval; a
    clean poll restores it and says so once."""
    cfg = cfg or config_from_env(env)
    if api is None:
        if not cfg.ok:
            logger.warn(f"[news-x] disabled: {ENV_AUTH_TOKEN} / {ENV_CT0} / {ENV_LIST_ID} not all set")
            return
        try:
            api = await make_api(cfg)
        except SourceError as e:
            counters.error(KEY, clock(), scrub(str(e), cfg))
            logger.error(f"[news-x] not starting: {scrub(str(e), cfg)}")
            return
    base = max(int(cfg.poll_s), MIN_POLL_S) if cfg.poll_s else DEFAULT_POLL_S
    rng = rng or random.Random()
    # Two clocks: the success cadence is human-shaped (next_interval); the error
    # backoff doubles from base, independent of it, so a run of failures is a
    # clean exponential retry, not a jittered one.
    backoff = float(base)
    interval = next_interval(base, clock(), rng, quiet_offset_h=quiet_offset_h)
    err_logged = False
    state: dict = {}
    logger.info(f"[news-x] polling list={cfg.list_id} base={base}s (jittered, human-shaped, slower overnight) "
                f"domains={','.join(cfg.domains)}")
    while not stop.is_set():
        now = clock()
        try:
            new = await fetch(state, dedup, counters, api=api, now=now, cfg=cfg)
            for it in new:
                await queue.put(it)
            if err_logged:
                logger.info("[news-x] recovered")
            err_logged = False
            backoff = float(base)
            interval = next_interval(base, now, rng, quiet_offset_h=quiet_offset_h)
            if new:
                lag = now - max(it.published_ts for it in new)
                logger.info(f"[news-x] read={state.get('last_read')} new={len(new)} newest_lag_s={lag:.0f} "
                            f"source={new[-1].source} title={new[-1].title[:80]!r}")
            else:
                logger.debug(f"[news-x] read={state.get('last_read')} new=0")
                if state.get("empty_streak") == 3:
                    logger.warn("[news-x] three empty reads in a row: is the List empty, private to another "
                                "account, or is X returning a blocked page?")
        except asyncio.CancelledError:
            raise
        except SourceError as e:
            backoff = min(backoff * 2, max_backoff_s)
            interval = backoff
            if not err_logged:
                logger.warn(f"[news-x] source-error={scrub(str(e), cfg)} backing off interval={interval:.0f}s "
                            f"(max {max_backoff_s:.0f}s)")
                err_logged = True
        except Exception as e:  # noqa: BLE001 - a transport blip or a parser bug must not end the two weeks
            interval = backoff
            if not err_logged:
                logger.warn(f"[news-x] error={type(e).__name__}: {scrub(str(e), cfg)} interval={interval:.0f}s")
                err_logged = True
        try:
            dedup.save()
            counters.save(now)
        except OSError as e:
            logger.warn(f"[news-x] state save failed: {e}")
        if stop.is_set():
            break
        await _pause(stop, interval, sleep)
    logger.info("[news-x] stopped")
