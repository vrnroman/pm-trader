"""x_cookies: the X List source over the owner's session cookies, driven by a
fake twscrape API (an async generator of fake tweets). No network; the clock
and the sleep are injected.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.newsbot.items import NO_TIMESTAMP_FLAG, DedupStore, SourceError
from src.newsbot.sources import roster
from src.newsbot.sources import x_cookies as xc

T0 = 1_761_300_000.0  # 2026-10-24 ~10:40 UTC, pinned
AUTH = "0123456789abcdef0123456789abcdef01234567"
CT0 = "feedfacefeedfacefeedfacefeedfacefeedface0123"
FULL_ENV = {"X_AUTH_TOKEN": AUTH, "X_CT0": CT0, "X_LIST_ID": "1234567890123"}


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

def _user(name):
    return SimpleNamespace(username=name)


def _tweet(tid, text, *, user="DeItaone", minutes_ago=5.0, date=..., links=(), retweeted=None, quoted=None, url=...):
    if date is ...:
        date = datetime.fromtimestamp(T0, tz=timezone.utc) - timedelta(minutes=minutes_ago)
    if url is ...:
        url = f"https://x.com/{user}/status/{tid}"
    return SimpleNamespace(id=tid, id_str=str(tid), rawContent=text, user=_user(user), date=date, url=url,
                           links=list(links), retweetedTweet=retweeted, quotedTweet=quoted, media=[])


def _link(short, full):
    return SimpleNamespace(tcourl=short, url=full, text=full)


class NoAccountError(Exception):
    """Same name as twscrape's; the module matches by name so a test never needs the library."""


class FakePool:
    def __init__(self, account=None):
        self.account = account
        self.gets = 0

    async def get(self, username):
        self.gets += 1
        return self.account


def _account(*, active=True, error_msg=None, locks=None):
    return SimpleNamespace(username=xc.ACCOUNT_NAME, active=active, error_msg=error_msg, locks=locks or {})


class FakeApi:
    """`script` is a list of pages; each page is a list of tweets or an
    exception to raise. The last page repeats once the script runs out."""

    def __init__(self, script, pool=None):
        self.script = list(script)
        self.calls: list[tuple[int, int]] = []
        self.pool = pool

    async def list_timeline(self, list_id, limit=-1):
        self.calls.append((list_id, limit))
        page = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(page, BaseException):
            raise page
        for tw in page:
            yield tw


class FakeSleep:
    def __init__(self, stop=None, stop_after=None):
        self.calls: list[float] = []
        self.stop = stop
        self.stop_after = stop_after

    async def __call__(self, s):
        self.calls.append(float(s))
        if self.stop is not None and self.stop_after is not None and len(self.calls) >= self.stop_after:
            self.stop.set()
        await asyncio.sleep(0)


def _stores(tmp_path):
    return DedupStore(tmp_path / "dedup.json"), roster.Counters(tmp_path / "roster.json")


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def test_disabled_when_any_key_is_missing_or_blank():
    assert xc.enabled(FULL_ENV) is True
    for k in FULL_ENV:
        env = dict(FULL_ENV)
        env.pop(k)
        assert xc.enabled(env) is False, k
        env[k] = "   "
        assert xc.enabled(env) is False, k
    assert xc.enabled({**FULL_ENV, "X_LIST_ID": "not-a-number"}) is False
    assert xc.enabled({**FULL_ENV, "X_LIST_ID": "0"}) is False
    assert xc.enabled({}) is False


def test_config_defaults_floor_list_url_and_domain_override():
    cfg = xc.config_from_env(FULL_ENV)
    assert cfg.list_id == 1234567890123 and cfg.poll_s == 75 and cfg.domains == ("politics", "geo", "crypto", "corp")
    assert cfg.cookies == f"auth_token={AUTH}; ct0={CT0}"
    assert xc.config_from_env({**FULL_ENV, "X_POLL_S": "10"}).poll_s == 30       # the floor
    assert xc.config_from_env({**FULL_ENV, "X_POLL_S": "junk"}).poll_s == 75     # the default
    assert xc.config_from_env({**FULL_ENV, "X_LIST_ID": "https://x.com/i/lists/987654321?x=1"}).list_id == 987654321
    assert xc.config_from_env({**FULL_ENV, "X_DOMAINS": "crypto, Corp,bogus"}).domains == ("crypto", "corp")
    assert xc.config_from_env({**FULL_ENV, "X_DOMAINS": "bogus"}).domains == xc.DEFAULT_DOMAINS
    assert xc.config_from_env({**FULL_ENV, "X_ACCOUNTS_DB": "/tmp/x.db"}).db_path == "/tmp/x.db"


def test_scrub_removes_both_cookies_from_any_message():
    cfg = xc.config_from_env(FULL_ENV)
    assert xc.scrub(f"cookie {AUTH} and {CT0} leaked", cfg) == "cookie *** and *** leaked"
    assert xc.scrub("clean", None) == "clean"


# --------------------------------------------------------------------------
# Tweet -> Item
# --------------------------------------------------------------------------

def test_tweet_maps_to_item_with_id_source_timestamps_url_title_and_expanded_links():
    tw = _tweet(111, "*FED HOLDS RATES\nmore: https://t.co/abc", minutes_ago=2.0,
                links=[_link("https://t.co/abc", "https://www.federalreserve.gov/newsevents/pressreleases/monetary20261024a.htm")])
    item = xc.tweet_to_item(tw, T0, ("politics", "corp"))
    assert item.id == "x:111"
    assert item.source == "x:deitaone"            # lower-cased handle
    assert item.domains == ("politics", "corp")
    assert item.published_ts == pytest.approx(T0 - 120.0)
    assert item.seen_ts == T0
    assert item.url == "https://x.com/DeItaone/status/111"
    assert item.title == "*FED HOLDS RATES more: https://www.federalreserve.gov/newsevents/pressreleases/monetary20261024a.htm"
    assert "https://t.co/abc" not in item.text and "monetary20261024a.htm" in item.text


def test_quote_tweet_keeps_its_own_text_and_appends_the_quoted_text():
    quoted = _tweet(100, "BREAKING: ceasefire signed https://t.co/q", user="Reuters",
                    links=[_link("https://t.co/q", "https://reuters.com/x")])
    tw = _tweet(112, "Markets will love this", user="unusual_whales", quoted=quoted)
    item = xc.tweet_to_item(tw, T0)
    assert item.text == "Markets will love this\n\nQT @Reuters: BREAKING: ceasefire signed https://reuters.com/x"
    assert item.source == "x:unusual_whales" and item.id == "x:112"


def test_pure_retweet_is_skipped_but_a_quote_is_not():
    original = _tweet(100, "original", user="Reuters")
    assert xc.tweet_to_item(_tweet(113, "RT @Reuters: original", retweeted=original), T0) is None
    assert xc.tweet_to_item(_tweet(114, "take", quoted=original), T0) is not None


def test_missing_text_id_or_date_are_handled():
    assert xc.tweet_to_item(_tweet(115, ""), T0) is None                         # media-only
    assert xc.tweet_to_item(SimpleNamespace(id=None, id_str=None, rawContent="x"), T0) is None
    item = xc.tweet_to_item(_tweet(116, "no clock", date=None), T0)
    assert item.published_ts == T0 and item.text.startswith(NO_TIMESTAMP_FLAG)
    naive = xc.tweet_to_item(_tweet(117, "naive", date=datetime(2026, 10, 24, 10, 0, 0)), T0)
    assert naive.published_ts == datetime(2026, 10, 24, 10, 0, 0, tzinfo=timezone.utc).timestamp()
    no_user = xc.tweet_to_item(SimpleNamespace(id=118, rawContent="who", user=None, date=None, url=None), T0)
    assert no_user.source == "x:unknown" and no_user.url == "https://x.com/i/status/118"


def test_title_is_at_most_200_chars_and_one_line():
    item = xc.tweet_to_item(_tweet(119, "y" * 350 + "\nsecond line"), T0)
    assert len(item.title) <= 200 and item.title.endswith("…") and "\n" not in item.title
    assert len(item.text) == 350 + 1 + len("second line")


# --------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------

async def test_fetch_returns_new_items_oldest_first_dedups_and_counts(tmp_path):
    dedup, counters = _stores(tmp_path)
    dedup.add("x:2")  # seen on a previous boot
    original = _tweet(50, "orig", user="Reuters")
    api = FakeApi([[_tweet(3, "newest", minutes_ago=1.0), _tweet(2, "seen", minutes_ago=2.0),
                    _tweet(4, "RT @Reuters: orig", retweeted=original, minutes_ago=0.5),
                    _tweet(1, "oldest", minutes_ago=9.0)]])
    state: dict = {}
    cfg = xc.config_from_env(FULL_ENV)
    new = await xc.fetch(state, dedup, counters, api=api, now=T0, cfg=cfg)
    assert [i.id for i in new] == ["x:1", "x:3"]
    assert api.calls == [(1234567890123, xc.PAGE_LIMIT)]   # one request, the List's page
    assert dedup.seen("x:3") and not dedup.seen("x:4")       # the retweet never enters the store
    row = counters.snapshot()["x"]
    assert row["items"] == 2 and row["errors"] == 0 and row["last_ok_ts"] == T0
    assert row["last_item_ts"] == pytest.approx(T0 - 60.0)
    assert state["last_read"] == 4 and state["empty_streak"] == 0
    # The same page again: nothing new, the ok still lands.
    assert await xc.fetch(state, dedup, counters, api=api, now=T0 + 50, cfg=cfg) == []
    assert counters.snapshot()["x"]["items"] == 2 and counters.snapshot()["x"]["last_ok_ts"] == T0 + 50


async def test_fetch_without_api_and_without_keys_is_a_source_error(tmp_path):
    dedup, counters = _stores(tmp_path)
    with pytest.raises(SourceError, match="disabled"):
        await xc.fetch({}, dedup, counters, now=T0, cfg=xc.config_from_env({}))


async def test_auth_error_becomes_a_source_error_with_the_accounts_reason_and_no_cookie(tmp_path):
    dedup, counters = _stores(tmp_path)
    pool = FakePool(_account(active=False, error_msg=f"(32) Could not authenticate you token={AUTH}"))
    api = FakeApi([NoAccountError("No account available for queue ListLatestTweetsTimeline")], pool=pool)
    cfg = xc.config_from_env(FULL_ENV)
    with pytest.raises(SourceError) as ei:
        await xc.fetch({}, dedup, counters, api=api, now=T0, cfg=cfg)
    msg = str(ei.value)
    assert msg.startswith("auth:") and "refresh X_AUTH_TOKEN" in msg
    assert AUTH not in msg and CT0 not in msg and "***" in msg
    row = counters.snapshot()["x"]
    assert row["errors"] == 1 and row["last_error"]["msg"] == msg and AUTH not in row["last_error"]["msg"]
    assert pool.gets == 1


async def test_the_real_twscrape_no_account_error_is_recognised(tmp_path):
    twscrape = pytest.importorskip("twscrape")
    dedup, counters = _stores(tmp_path)
    api = FakeApi([twscrape.NoAccountError("No account available")])  # no pool: generic reason
    with pytest.raises(SourceError, match="no usable account"):
        await xc.fetch({}, dedup, counters, api=api, now=T0, cfg=xc.config_from_env(FULL_ENV))


async def test_empty_read_with_a_locked_account_is_rate_limited_and_a_healthy_one_is_empty(tmp_path):
    dedup, counters = _stores(tmp_path)
    cfg = xc.config_from_env(FULL_ENV)
    until = datetime(2026, 10, 24, 11, 0, tzinfo=timezone.utc)
    locked = FakeApi([[]], pool=FakePool(_account(locks={xc.QUEUE: until})))
    with pytest.raises(SourceError, match="rate-limited until 2026-10-24T11:00:00"):
        await xc.fetch({}, dedup, counters, api=locked, now=T0, cfg=cfg)
    healthy = FakeApi([[]], pool=FakePool(_account()))
    state: dict = {}
    for _ in range(3):
        assert await xc.fetch(state, dedup, counters, api=healthy, now=T0, cfg=cfg) == []
    assert state["empty_streak"] == 3
    assert counters.snapshot()["x"]["errors"] == 1


async def test_gql_outdated_and_transport_errors_are_sorted(tmp_path):
    dedup, counters = _stores(tmp_path)
    cfg = xc.config_from_env(FULL_ENV)

    class GqlFeaturesOutdatedError(Exception):
        pass

    with pytest.raises(SourceError, match="upgrade twscrape"):
        await xc.fetch({}, dedup, counters, api=FakeApi([GqlFeaturesOutdatedError("336")]), now=T0, cfg=cfg)
    with pytest.raises(ConnectionError):  # transport: propagates as itself, but is counted
        await xc.fetch({}, dedup, counters, api=FakeApi([ConnectionError(f"reset {CT0}")]), now=T0, cfg=cfg)
    row = counters.snapshot()["x"]
    assert row["errors"] == 2 and CT0 not in row["last_error"]["msg"]


# --------------------------------------------------------------------------
# run loop
# --------------------------------------------------------------------------

async def test_run_backs_off_on_source_errors_doubling_to_the_cap_and_recovers(tmp_path):
    dedup, counters = _stores(tmp_path)
    auth = NoAccountError("none")
    page2 = [_tweet(1, "first", minutes_ago=1.0), _tweet(2, "second", minutes_ago=0.1)]
    # The pool says "inactive" throughout, so an EMPTY page would also read as
    # an auth failure; the recovery pages are non-empty on purpose.
    api = FakeApi([[_tweet(1, "first", minutes_ago=1.0)], auth, auth, auth, auth, page2, page2],
                  pool=FakePool(_account(active=False, error_msg="(32) Could not authenticate you")))
    stop = asyncio.Event()
    sleep = FakeSleep(stop=stop, stop_after=7)
    q: asyncio.Queue = asyncio.Queue()
    cfg = xc.config_from_env(FULL_ENV)
    import random as _r
    await asyncio.wait_for(xc.run(q, dedup, counters, stop=stop, api=api, sleep=sleep, clock=lambda: T0, cfg=cfg,
                                  max_backoff_s=300, rng=_r.Random(0)), 2)
    # the error backoff doubles from base independently of the jittered success
    # cadence (calls 0, 5, 6 are successes -> human-shaped, only >= MIN_POLL_S)
    assert [sleep.calls[i] for i in (1, 2, 3, 4)] == [150.0, 300.0, 300.0, 300.0]  # base 75 -> 150, cap 300
    assert all(c >= xc.MIN_POLL_S for c in (sleep.calls[0], sleep.calls[5], sleep.calls[6]))
    assert len(api.calls) == 7
    assert [q.get_nowait().id for _ in range(q.qsize())] == ["x:1", "x:2"]
    row = counters.snapshot()["x"]
    assert row["items"] == 2 and row["errors"] == 4
    assert dedup.seen("x:1") and dedup.seen("x:2")


async def test_run_keeps_the_base_interval_on_transport_errors(tmp_path):
    dedup, counters = _stores(tmp_path)
    api = FakeApi([ConnectionError("reset"), ConnectionError("reset"), []])
    stop = asyncio.Event()
    sleep = FakeSleep(stop=stop, stop_after=3)
    q: asyncio.Queue = asyncio.Queue()
    import random as _r
    await asyncio.wait_for(xc.run(q, dedup, counters, stop=stop, api=api, sleep=sleep, clock=lambda: T0,
                                  cfg=xc.config_from_env({**FULL_ENV, "X_POLL_S": "45"}), rng=_r.Random(0)), 2)
    # transport errors hold the base backoff (45); the clean read that follows
    # gets a jittered human interval
    assert sleep.calls[0] == 45.0 and sleep.calls[1] == 45.0 and sleep.calls[2] >= xc.MIN_POLL_S
    assert counters.snapshot()["x"]["errors"] == 2


async def test_run_is_a_no_op_without_keys_and_stops_cleanly_mid_backoff(tmp_path):
    dedup, counters = _stores(tmp_path)
    q: asyncio.Queue = asyncio.Queue()
    sleep = FakeSleep()
    await asyncio.wait_for(xc.run(q, dedup, counters, stop=asyncio.Event(), sleep=sleep, env={}), 2)
    assert sleep.calls == [] and counters.snapshot() == {}

    # A long real backoff must end the moment stop is set.
    api = FakeApi([NoAccountError("none")])
    stop = asyncio.Event()
    task = asyncio.create_task(xc.run(q, dedup, counters, stop=stop, api=api, clock=lambda: T0,
                                      cfg=xc.config_from_env(FULL_ENV)))
    for _ in range(50):
        if api.calls:
            break
        await asyncio.sleep(0)
    assert api.calls == [(1234567890123, xc.PAGE_LIMIT)]
    stop.set()
    await asyncio.wait_for(task, 2)   # not after 50 s
    assert len(api.calls) == 1


# --------------------------------------------------------------------------
# twscrape glue (local sqlite only; no network)
# --------------------------------------------------------------------------

async def test_make_api_stores_the_cookies_as_one_active_account_and_mutes_telemetry(tmp_path, monkeypatch):
    pytest.importorskip("twscrape")
    monkeypatch.delenv("TWS_TELEMETRY", raising=False)
    cfg = xc.config_from_env({**FULL_ENV, "X_ACCOUNTS_DB": str(tmp_path / "news" / "x-accounts.db")})
    api = await xc.make_api(cfg)
    assert (tmp_path / "news" / "x-accounts.db").exists()
    acc = await api.pool.get(xc.ACCOUNT_NAME)
    assert acc.active is True and acc.cookies == {"auth_token": AUTH, "ct0": CT0}
    assert api.pool._raise_when_no_account is True   # else a rate limit hangs the loop forever
    assert __import__("os").environ.get("TWS_TELEMETRY") == "0"
    assert await xc.account_trouble(api) is None
    # A second boot with the same path upserts rather than duplicating or failing.
    api2 = await xc.make_api(cfg)
    assert (await api2.pool.get(xc.ACCOUNT_NAME)).cookies["ct0"] == CT0


def test_next_interval_is_jittered_not_fixed_and_respects_the_floor():
    import random as _r
    from src.newsbot.sources.x_cookies import next_interval, MIN_POLL_S
    rng = _r.Random(1)
    day = 10 * 3600.0   # 10:00 local at offset 0 = active
    vals = [next_interval(75.0, day, rng, quiet_offset_h=0.0) for _ in range(400)]
    assert len(set(round(v) for v in vals)) > 100, "a fixed cadence is a bot tell"
    assert min(vals) >= MIN_POLL_S
    import statistics as st
    assert 40 < st.median(vals) < 200, st.median(vals)


def test_next_interval_slows_overnight():
    import random as _r
    import statistics as st
    from src.newsbot.sources.x_cookies import next_interval
    rng = _r.Random(2)
    awake = st.median([next_interval(75.0, 10 * 3600.0, rng, quiet_offset_h=0.0) for _ in range(300)])
    asleep = st.median([next_interval(75.0, 4 * 3600.0, rng, quiet_offset_h=0.0) for _ in range(300)])
    assert asleep > awake * 2, (awake, asleep)
