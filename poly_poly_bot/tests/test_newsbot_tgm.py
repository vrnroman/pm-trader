"""telegram_mtproto: the client-API Telegram source, driven by fake client /
event objects. No network, no Telethon network call; the clock is injected.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.newsbot.items import NO_TIMESTAMP_FLAG, DedupStore
from src.newsbot.sources import roster
from src.newsbot.sources import telegram_mtproto as tgm

T0 = 1_761_300_000.0  # 2026-10-24 ~10:40 UTC, pinned
FULL_ENV = {"TELEGRAM_API_ID": "12345", "TELEGRAM_API_HASH": "a" * 32, "TELEGRAM_USER_SESSION": "1BQANOTREAL"}


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

def _msg(mid, text, *, channel_id=1001, minutes_ago=5.0, entities=None, date=...):
    if date is ...:
        date = datetime.fromtimestamp(T0, tz=timezone.utc) - timedelta(minutes=minutes_ago)
    return SimpleNamespace(id=mid, message=text, text=text, date=date, entities=entities,
                           peer_id=SimpleNamespace(channel_id=channel_id))


def _event(message):
    return SimpleNamespace(message=message, chat_id=-(1_000_000_000_000 + message.peer_id.channel_id))


class FakeFloodWaitError(Exception):
    def __init__(self, seconds):
        super().__init__(f"A wait of {seconds} seconds is required")
        self.seconds = seconds


class FakeClient:
    """Enough of TelegramClient for `stream`: connect / is_user_authorized /
    get_entity / add_event_handler / iter_messages / run_until_disconnected /
    disconnect. `history` is channel (lower) -> list of messages newest first.
    `drop` is awaited by run_until_disconnected; `connect_errors` is a list of
    exceptions raised by successive connect() calls (None = fine)."""

    def __init__(self, history=None, *, entity_ids=None, connect_errors=(), run_error=ConnectionError("link down")):
        self.history = {k.lower(): v for k, v in (history or {}).items()}
        self.entity_ids = {k.lower(): v for k, v in (entity_ids or {}).items()}
        self.connect_errors = list(connect_errors)
        self.run_error = run_error
        self.handler = None
        self.drop = asyncio.Event()
        self.connects = 0
        self.disconnects = 0
        self.resolved: list[str] = []
        self.iter_calls: list[tuple] = []

    async def connect(self):
        self.connects += 1
        if self.connect_errors:
            err = self.connect_errors.pop(0)
            if err is not None:
                raise err

    async def is_user_authorized(self):
        return True

    async def get_entity(self, name):
        self.resolved.append(name)
        if name.lower() not in self.entity_ids:
            raise ValueError(f"No user has {name!r} as username")
        return SimpleNamespace(id=self.entity_ids[name.lower()], username=name)

    def add_event_handler(self, callback, builder=None):
        self.handler = callback

    async def iter_messages(self, entity, limit=20):
        name = getattr(entity, "username", entity)
        self.iter_calls.append((name, limit))
        for m in self.history.get(name.lower(), [])[:limit]:
            yield m

    async def run_until_disconnected(self):
        await self.drop.wait()
        self.drop.clear()
        if self.run_error is not None:
            raise self.run_error

    async def disconnect(self):
        self.disconnects += 1


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


async def _until(pred, n=200):
    for _ in range(n):
        if pred():
            return True
        await asyncio.sleep(0)
    return pred()


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def test_disabled_when_any_credential_is_missing():
    assert tgm.enabled(FULL_ENV) is True
    for k in FULL_ENV:
        env = dict(FULL_ENV)
        env.pop(k)
        assert tgm.enabled(env) is False, k
        env[k] = "   "
        assert tgm.enabled(env) is False, k
    assert tgm.enabled({**FULL_ENV, "TELEGRAM_API_ID": "not-a-number"}) is False
    assert tgm.enabled({}) is False


def test_channel_list_defaults_to_the_rosters_tg_channels():
    cfg = tgm.config_from_env(FULL_ENV)
    expected = [s.channel for s in roster.V1 if s.kind == "tg"]
    assert len(expected) == 13 and "europeelects" in expected
    assert list(cfg.channels) == expected
    assert cfg.api_id == 12345 and cfg.session == "1BQANOTREAL"


def test_channel_list_parses_usernames_links_and_at_names_and_dedups():
    raw = " @Visegrad_24, https://t.me/s/WatcherGuru ,t.me/newchan/1234 telegram.me/Another_One?x=1\nhttps://t.me/+inviteHash, 123, bad-name"
    got = tgm.parse_channels(raw, defaults=["insiderpaper"])
    assert got == ["insiderpaper", "Visegrad_24", "WatcherGuru", "newchan", "Another_One"]
    # Env extras come after the roster and never duplicate it.
    cfg = tgm.config_from_env({**FULL_ENV, "NEWS_TGM_CHANNELS": "@financialjuice, https://t.me/extra_chan"})
    assert cfg.channels.count("financialjuice") == 1
    assert cfg.channels[-1] == "extra_chan" and len(cfg.channels) == len(tgm.roster_channels()) + 1
    assert tgm.normalize_channel("") is None and tgm.normalize_channel("https://t.me/joinchat/abc") is None


def test_roster_domains_by_channel_are_lower_cased():
    d = tgm.roster_domains()
    assert d["watcherguru"] == ("crypto", "corp")
    assert d["financialjuice"] == ("geo", "corp", "politics")


# --------------------------------------------------------------------------
# Message -> Item
# --------------------------------------------------------------------------

def test_message_maps_to_item_with_id_source_timestamps_url_title_text():
    text = "BREAKING: Ceasefire talks resume in Cairo\nMore: https://example.com/a?x=1"
    m = _msg(777, text, minutes_ago=2.0, entities=[SimpleNamespace(url="https://hidden.example/b")])
    item = tgm.message_to_item(m, "ClashReport", T0, ("geo",))
    assert item.id == "tgm:clashreport:777"
    assert item.source == "tgm:clashreport"
    assert item.domains == ("geo",)
    assert item.published_ts == pytest.approx(T0 - 120.0)
    assert item.seen_ts == T0
    assert item.url == "https://t.me/ClashReport/777"
    assert item.title == "BREAKING: Ceasefire talks resume in Cairo"
    assert "https://example.com/a?x=1" in item.text
    assert item.text.endswith("https://hidden.example/b")  # the text-link entity's URL is kept


def test_media_only_message_is_skipped_and_missing_date_is_flagged():
    assert tgm.message_to_item(_msg(1, ""), "x", T0) is None
    assert tgm.message_to_item(_msg(2, None), "x", T0) is None
    assert tgm.message_to_item(SimpleNamespace(id=None, message="hi", date=None), "x", T0) is None
    item = tgm.message_to_item(_msg(3, "no clock", date=None), "x", T0)
    assert item.published_ts == T0 and item.text.startswith(NO_TIMESTAMP_FLAG)
    naive = tgm.message_to_item(_msg(4, "naive", date=datetime(2026, 10, 24, 10, 0, 0)), "x", T0)
    assert naive.published_ts == datetime(2026, 10, 24, 10, 0, 0, tzinfo=timezone.utc).timestamp()


def test_title_is_the_first_line_capped_at_200_chars():
    long = "x" * 350 + "\nsecond line"
    item = tgm.message_to_item(_msg(5, long), "chan", T0)
    assert len(item.title) <= 200 and item.title.endswith("…")


def test_unknown_channel_defaults_to_geo_domain():
    item = tgm.message_to_item(_msg(6, "hello"), "chan", T0, ())
    assert item.domains == ("geo",)


def test_flood_wait_is_recognised_by_shape_only():
    assert tgm.flood_wait_seconds(FakeFloodWaitError(7)) == 7.0
    assert tgm.flood_wait_seconds(ConnectionError("x")) is None
    assert tgm.flood_wait_seconds(SimpleNamespace(seconds=3)) is None  # not an exception of the flood family
    from telethon.errors import FloodWaitError
    assert tgm.flood_wait_seconds(FloodWaitError(request=None, capture=42)) == 42.0


def test_peer_channel_id_from_message_peer_or_minus_100_chat_id():
    assert tgm._peer_channel_id(_event(_msg(1, "t", channel_id=1001))) == 1001
    assert tgm._peer_channel_id(SimpleNamespace(message=SimpleNamespace(peer_id=None), chat_id=-1001234567890)) == 1234567890
    assert tgm._peer_channel_id(SimpleNamespace(message=None, chat_id=None)) is None


# --------------------------------------------------------------------------
# Backfill
# --------------------------------------------------------------------------

async def test_fetch_recent_returns_oldest_first_and_skips_media_only():
    client = FakeClient({"Chan": [_msg(3, "newest"), _msg(2, ""), _msg(1, "oldest", minutes_ago=9.0)]})
    items = await tgm.fetch_recent(client, "Chan", limit=20, domains=("corp",), seen_ts=T0)
    assert [i.id for i in items] == ["tgm:chan:1", "tgm:chan:3"]
    assert items[0].domains == ("corp",) and client.iter_calls == [("Chan", 20)]


# --------------------------------------------------------------------------
# The stream
# --------------------------------------------------------------------------

async def _run_stream(client, tmp_path, *, channels, sleep=None, stop=None, **kw):
    stop = stop or asyncio.Event()
    q: asyncio.Queue = asyncio.Queue()
    dedup = DedupStore(tmp_path / "dedup.json")
    counters = roster.Counters(tmp_path / "roster.json")
    sleep = sleep or FakeSleep()
    task = asyncio.create_task(tgm.stream(q, dedup, counters, stop=stop, client_factory=lambda: client,
                                          channels=channels, clock=lambda: T0, sleep=sleep, **kw))
    return task, q, dedup, counters, stop


async def test_stream_backfills_then_pushes_live_messages_deduped_with_counters(tmp_path):
    client = FakeClient({"insiderpaper": [_msg(11, "backfill two"), _msg(10, "backfill one", minutes_ago=8.0)]},
                        entity_ids={"insiderpaper": 1001, "clashreport": 1002})
    task, q, dedup, counters, stop = await _run_stream(client, tmp_path, channels=["@InsiderPaper", "https://t.me/s/ClashReport"],
                                                       domains_by_channel={"insiderpaper": ("geo", "corp")})
    assert await _until(lambda: client.handler is not None and q.qsize() == 2)
    assert client.resolved == ["InsiderPaper", "ClashReport"]
    a, b = q.get_nowait(), q.get_nowait()
    assert (a.id, b.id) == ("tgm:insiderpaper:10", "tgm:insiderpaper:11")  # oldest first
    assert a.domains == ("geo", "corp")

    # A live post on a followed channel: one item, roster counted, dedup holds.
    live = _msg(12, "LIVE: markets halt\nhttps://x.example/1", channel_id=1002, minutes_ago=0.2)
    await client.handler(_event(live))
    await client.handler(_event(live))  # the same update twice (Telethon replays on reconnect)
    assert q.qsize() == 1
    item = q.get_nowait()
    assert item.source == "tgm:clashreport" and item.url == "https://t.me/ClashReport/12"
    assert item.domains == ("geo",)  # not on the roster map given -> default
    assert item.seen_ts == T0 and item.published_ts == pytest.approx(T0 - 12.0)
    assert dedup.seen("tgm:clashreport:12")

    # An update from a chat we did not ask for, and a media-only post, are ignored.
    await client.handler(_event(_msg(99, "noise", channel_id=4242)))
    await client.handler(_event(_msg(13, "", channel_id=1002)))
    assert q.qsize() == 0

    snap = counters.snapshot()
    assert snap["tgm:insiderpaper"]["items"] == 2 and snap["tgm:insiderpaper"]["last_ok_ts"] == T0
    assert snap["tgm:insiderpaper"]["last_item_ts"] == pytest.approx(T0 - 300.0)
    assert snap["tgm:clashreport"]["items"] == 1 and snap["tgm:clashreport"]["last_item_ts"] == pytest.approx(T0 - 12.0)
    assert snap["tgm:clashreport"]["errors"] == 0

    stop.set()
    await asyncio.wait_for(task, 2)
    assert client.disconnects == 1


async def test_backfill_is_deduped_against_the_store_and_a_second_connect(tmp_path):
    dedup = DedupStore(tmp_path / "dedup.json")
    dedup.add("tgm:chan:2")  # seen on a previous boot
    client = FakeClient({"chan": [_msg(3, "c"), _msg(2, "b"), _msg(1, "a")]}, entity_ids={"chan": 7})
    q: asyncio.Queue = asyncio.Queue()
    counters = roster.Counters(tmp_path / "roster.json")
    stop = asyncio.Event()
    sleep = FakeSleep()
    task = asyncio.create_task(tgm.stream(q, dedup, counters, stop=stop, client_factory=lambda: client,
                                          channels=["chan"], clock=lambda: T0, sleep=sleep))
    assert await _until(lambda: q.qsize() == 2)
    assert sorted(i.id for i in (q.get_nowait(), q.get_nowait())) == ["tgm:chan:1", "tgm:chan:3"]
    # Drop the link: the reconnect backfills again and pushes nothing new.
    client.drop.set()
    assert await _until(lambda: client.connects == 2 and len(client.iter_calls) == 2)
    await asyncio.sleep(0)
    assert q.qsize() == 0
    assert counters.snapshot()["tgm:chan"]["items"] == 2
    assert counters.snapshot()["tgm"]["errors"] == 1
    stop.set()
    await asyncio.wait_for(task, 2)


async def test_disconnects_back_off_exponentially_to_the_cap(tmp_path):
    client = FakeClient(entity_ids={"chan": 7})
    stop = asyncio.Event()
    sleep = FakeSleep(stop=stop, stop_after=5)
    task, q, dedup, counters, stop = await _run_stream(client, tmp_path, channels=["chan"], sleep=sleep, stop=stop,
                                                       max_backoff_s=8.0)
    for _ in range(5):
        assert await _until(lambda: client.handler is not None)
        client.handler = None
        client.drop.set()
        await asyncio.sleep(0)
    await asyncio.wait_for(task, 2)
    assert sleep.calls == [1.0, 2.0, 4.0, 8.0, 8.0]
    assert counters.snapshot()["tgm"]["errors"] == 5
    assert client.disconnects == 5


async def test_flood_wait_sleeps_the_seconds_asked_and_does_not_grow_the_backoff(tmp_path):
    client = FakeClient(entity_ids={"chan": 7}, connect_errors=[FakeFloodWaitError(7), None, None])
    stop = asyncio.Event()
    sleep = FakeSleep(stop=stop, stop_after=2)
    task, q, dedup, counters, stop = await _run_stream(client, tmp_path, channels=["chan"], sleep=sleep, stop=stop)
    assert await _until(lambda: client.handler is not None)
    client.drop.set()  # one ordinary drop after the flood wait
    await asyncio.wait_for(task, 2)
    assert sleep.calls == [8.0, 1.0]  # 7 s asked + 1 s margin; then the ladder starts at 1 s
    assert counters.snapshot().get("tgm", {}).get("errors", 0) == 1  # the flood wait is not an error


async def test_unresolved_channel_is_counted_and_the_rest_still_stream(tmp_path):
    client = FakeClient(entity_ids={"good": 7})
    task, q, dedup, counters, stop = await _run_stream(client, tmp_path, channels=["ghost_chan", "good"])
    assert await _until(lambda: client.handler is not None)
    await client.handler(_event(_msg(1, "hello", channel_id=7)))
    assert q.get_nowait().source == "tgm:good"
    snap = counters.snapshot()
    assert snap["tgm:ghost_chan"]["errors"] == 1 and "resolve" in snap["tgm:ghost_chan"]["last_error"]["msg"]
    stop.set()
    await asyncio.wait_for(task, 2)


async def test_stream_without_credentials_or_channels_returns_at_once(tmp_path):
    q: asyncio.Queue = asyncio.Queue()
    stop = asyncio.Event()
    await asyncio.wait_for(tgm.stream(q, None, roster.Counters(tmp_path / "r.json"), stop=stop, env={}), 2)
    client = FakeClient()
    await asyncio.wait_for(tgm.stream(q, None, roster.Counters(tmp_path / "r.json"), stop=stop,
                                      client_factory=lambda: client, channels=["https://t.me/+invite"]), 2)
    assert client.connects == 0 and q.qsize() == 0


def test_default_client_factory_builds_a_string_session_client_without_connecting():
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    # Telethon decodes the string on construction, so a well-formed (empty) one.
    cfg = tgm.config_from_env({**FULL_ENV, "TELEGRAM_USER_SESSION": StringSession().save()})
    client = tgm.default_client_factory(cfg)()
    assert isinstance(client, TelegramClient) and isinstance(client.session, StringSession)
    assert client.api_id == 12345 and not client.is_connected()
