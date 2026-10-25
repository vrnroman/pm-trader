"""newsbot.sources: every family against a saved real response (fetched once
on 2026-10-25, trimmed to a few entries; see tests/fixtures/newsbot/). No
test opens a socket; the poller and the Jetstream stream run on fakes."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from src.newsbot.items import NO_TIMESTAMP_FLAG, DedupStore, SourceError
from src.newsbot.sources import BROWSER_UA, CONTACT_UA, bluesky, hn, poller, roster, rss, telegram_web, treeofalpha

FX = Path(__file__).parent / "fixtures" / "newsbot"
NOW = 1792922000.0  # 2026-10-25T09:53:20Z


def fx(name: str) -> bytes:
    return (FX / name).read_bytes()


def _spec(key="rss:test", domains=("geo",), headers=None):
    return rss.FeedSpec(key=key, url="https://example.invalid/feed", domains=domains, headers=headers or {})


# ===========================================================================
# RSS / Atom
# ===========================================================================

def test_rss2_nyt_items_carry_the_feeds_own_pubdate_and_guid():
    out = rss.parse(fx("nyt_home.rss.xml"), _spec("rss:nyt-home"), NOW)
    assert len(out) == 3
    first = out[0]
    assert first.id.startswith("rss:nyt-home:https://www.nytimes.com/2026/10/24/")
    assert first.published_ts == 1792890377.0, "Sun, 25 Oct 2026 01:06:17 +0000"
    assert first.seen_ts == NOW and first.domains == ("geo",)
    assert first.title.startswith("A New Level of Threat and Fear")
    assert first.text.startswith("With new intelligence"), "description, HTML stripped, not the title twice"
    assert first.url.startswith("https://www.nytimes.com/")
    assert NO_TIMESTAMP_FLAG not in first.text


def test_atom_verge_prefers_published_and_converts_minus_four_to_utc():
    out = rss.parse(fx("verge.atom.xml"), _spec("rss:verge", ("corp",)), NOW)
    assert len(out) == 3
    e = out[0]
    assert e.id == "rss:verge:https://www.theverge.com/?p=1018205"
    assert e.published_ts == 1792877352.0, "2026-10-24T17:29:12-04:00 is 21:29:12Z"
    assert e.url == "https://www.theverge.com/ai-artificial-intelligence/1018205/blue-planet-iii-authentic-organic-ai"
    assert e.title == "Blue Planet III is keeping the rough edges in the age of AI"


def test_sec_8k_atom_uses_updated_as_acceptance_time_and_keeps_the_item_lines():
    out = rss.parse(fx("sec_8k.atom.xml"), _spec("sec:8k", ("corp",)), NOW)
    assert len(out) == 10
    e = out[0]
    assert e.id == "sec:8k:urn:tag:sec.gov,2008:accession-number=0001493152-26-048288"
    assert e.title == "8-K - Greenwave Technology Solutions, Inc. (0001589149) (Filer)"
    assert e.published_ts == 1792791015.0, "2026-10-23T17:30:15-04:00 (EDT) -> 21:30:15Z"
    assert "Item 5.08: Shareholder Nominations" in e.text and "Item 8.01: Other Events" in e.text
    assert e.url.startswith("https://www.sec.gov/Archives/edgar/data/1589149/")
    # entries are newest-first as EDGAR serves them; timestamps are all tz-aware epoch floats
    assert all(isinstance(x.published_ts, float) for x in out)
    assert out[0].published_ts >= out[-1].published_ts


def test_trumpstruth_rss_pubdate_plus_zero_and_statuses_url():
    out = rss.parse(fx("trumpstruth.rss.xml"), _spec("rss:trumpstruth", ("politics",)), NOW)
    assert len(out) == 3
    e = out[0]
    assert e.id == "rss:trumpstruth:https://www.trumpstruth.org/statuses/42714"
    assert e.published_ts == 1792908125.0, "Sun, 25 Oct 2026 06:02:05 +0000"
    assert e.title.startswith("Rob Carson") and e.url == "https://www.trumpstruth.org/statuses/42714"
    assert out[1].published_ts == 1792903363.0 and out[1].title.startswith("Obama was")


def test_rdf_rss10_dw_items_in_a_namespace_with_dc_date():
    out = rss.parse(fx("dw.rdf.xml"), _spec("rss:dw"), NOW)
    assert len(out) == 2
    assert out[0].title == "Brazil votes in tight runoff between leftist Lula and right-wing Flavio Bolsonaro"
    assert out[0].published_ts == 1792920840.0, "<dc:date>2026-10-25T09:34:00Z"
    assert out[0].url.startswith("https://www.dw.com/en/brazil-votes")
    assert out[0].text.startswith("The high stakes election")


def test_fed_press_feed_with_a_utf8_bom_and_cdata_pubdate():
    out = rss.parse(fx("fed_press.rss.xml"), _spec("rss:fed-press", ("corp",)), NOW)
    assert len(out) == 2
    assert out[0].published_ts == 1792162800.0, "Fri, 16 Oct 2026 15:00:00 GMT"
    assert out[0].url == "https://www.federalreserve.gov/newsevents/pressreleases/enforcement20261016a.htm"


def test_rss_item_without_a_date_gets_seen_ts_and_a_flag_in_text():
    body = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
    <item><title>Undated thing</title><link>https://e.com/1</link><guid>g1</guid></item>
    </channel></rss>"""
    out = rss.parse(body, _spec(), NOW)
    assert len(out) == 1
    assert out[0].published_ts == NOW
    assert out[0].text.startswith(NO_TIMESTAMP_FLAG)
    assert out[0].id == "rss:test:g1"


def test_rss_not_xml_is_a_source_error_not_a_crash():
    with pytest.raises(SourceError, match="not XML"):
        rss.parse(b"<!doctype html><html><body>Access denied</body></html>", _spec(), NOW)
    with pytest.raises(SourceError, match="unknown feed root"):
        rss.parse(b"<?xml version='1.0'?><opml/>", _spec(), NOW)


def test_rss_prepare_sends_conditional_headers_from_state_and_spec_headers_win():
    state = {"etag": 'W/"abc"', "last_modified": "Sun, 25 Oct 2026 09:10:21 GMT"}
    url, h = rss.prepare(_spec(headers={"User-Agent": CONTACT_UA}), state)
    assert url == "https://example.invalid/feed"
    assert h["If-None-Match"] == 'W/"abc"' and h["If-Modified-Since"] == "Sun, 25 Oct 2026 09:10:21 GMT"
    assert h["User-Agent"] == CONTACT_UA, "SEC's contact UA replaces the browser default"
    _, h2 = rss.prepare(_spec(), {})
    assert h2["User-Agent"] == BROWSER_UA and "If-None-Match" not in h2


def test_rss_handle_304_is_empty_and_validators_are_stored_only_after_a_parse():
    state: dict = {}
    assert rss.handle(304, httpx.Headers({}), b"", _spec(), state, NOW) == []
    hdrs = httpx.Headers({"ETag": '"e1"', "Last-Modified": "Sun, 25 Oct 2026 09:10:21 GMT"})
    out = rss.handle(200, hdrs, fx("nyt_home.rss.xml"), _spec(), state, NOW)
    assert len(out) == 3 and state == {"etag": '"e1"', "last_modified": "Sun, 25 Oct 2026 09:10:21 GMT"}
    with pytest.raises(SourceError):
        rss.handle(200, httpx.Headers({"ETag": '"poison"'}), b"<html>error</html>", _spec(), state, NOW)
    assert state["etag"] == '"e1"', "an unparseable 200 must not pin us to 304s of garbage"
    with pytest.raises(SourceError, match="HTTP 500"):
        rss.handle(500, httpx.Headers({}), b"", _spec(), state, NOW)


def test_rss_fetch_uses_the_client_and_returns_items():
    def app(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == CONTACT_UA
        return httpx.Response(200, content=fx("sec_8k.atom.xml"), headers={"ETag": '"s1"'})
    client = httpx.Client(transport=httpx.MockTransport(app))
    state: dict = {}
    out = rss.fetch(_spec("sec:8k", ("corp",), headers={"User-Agent": CONTACT_UA}), state, client=client)
    assert len(out) == 10 and state["etag"] == '"s1"'


# ===========================================================================
# Telegram
# ===========================================================================

def test_telegram_page_yields_ids_text_timestamps_and_post_urls():
    spec = telegram_web.spec_for("financialjuice", ("geo", "corp"), poll_s=30)
    assert spec.key == "tg:financialjuice" and spec.url == "https://t.me/s/financialjuice"
    out = telegram_web.parse(fx("tg_financialjuice.html").decode(), spec, NOW)
    assert [it.id for it in out] == ["tg:financialjuice:142489", "tg:financialjuice:142490", "tg:financialjuice:142491"]
    a, b, c = out
    assert a.published_ts == 1792845809.0, "<time datetime='2026-10-24T12:43:29+00:00'>"
    assert b.published_ts == 1792845889.0 and c.published_ts == 1792849480.0
    assert a.text == "Zelenskiy: starlink restrictions completely removed|FJ", "the channel's self-link is branding, dropped"
    assert b.text.startswith("Iran President Pezeshkian blames US") and "'I still think" in b.text, "entities decoded"
    assert c.title.startswith("US updates travel advisories") and c.title == c.text[:len(c.title)]
    assert a.url == "https://t.me/FinancialJuice/142489"
    assert a.domains == ("geo", "corp") and a.seen_ts == NOW and a.source == "tg:financialjuice"


def test_telegram_keeps_external_link_urls_in_text():
    html = (
        '<section class="tgme_channel_history js-message_history">'
        '<div class="tgme_widget_message_wrap js-widget_message_wrap"><div class="tgme_widget_message" data-post="Chan/7">'
        '<div class="tgme_widget_message_text js-message_text" dir="auto">Breaking: deal signed<br/>'
        '<a href="https://x.com/acc/status/99" target="_blank">x.com/acc/status/9…</a> &amp; <a href="https://e.com/p">source</a></div>'
        '<div class="tgme_widget_message_footer"><time datetime="2026-10-25T09:00:00+00:00" class="time">09:00</time></div>'
        '</div></div></section>'
    )
    out = telegram_web.parse(html, telegram_web.spec_for("chan"), NOW)
    assert len(out) == 1
    assert out[0].text == "Breaking: deal signed\nhttps://x.com/acc/status/99 & source (https://e.com/p)"
    assert out[0].title == "Breaking: deal signed"
    assert out[0].published_ts == 1792918800.0


def test_telegram_no_preview_contact_page_is_a_source_error():
    with pytest.raises(SourceError, match=r"@reuters has no public preview \(Send Message\)"):
        telegram_web.parse(fx("tg_reuters_nopreview.html").decode(), telegram_web.spec_for("reuters"), NOW)
    with pytest.raises(SourceError, match="no public preview"):
        telegram_web.handle(302, httpx.Headers({"location": "https://t.me/reuters"}), b"", telegram_web.spec_for("reuters"), {}, NOW)


def test_telegram_empty_history_page_is_zero_items_not_an_error():
    html = '<html><body><section class="tgme_channel_history js-message_history"></section></body></html>'
    assert telegram_web.parse(html, telegram_web.spec_for("newchan"), NOW) == []


def test_telegram_prepare_uses_a_browser_user_agent():
    url, h = telegram_web.prepare(telegram_web.spec_for("WatcherGuru"), {})
    assert url == "https://t.me/s/WatcherGuru" and h["User-Agent"].startswith("Mozilla/5.0")


def test_telegram_photo_only_post_is_skipped_and_missing_time_is_flagged():
    html = (
        '<section class="tgme_channel_history">'
        '<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="C/1">'
        '<a class="tgme_widget_message_photo_wrap" href="x"></a><time datetime="2026-10-25T09:00:00+00:00"></time></div></div>'
        '<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="C/2">'
        '<div class="tgme_widget_message_text">words only</div></div></div>'
        '</section>'
    )
    out = telegram_web.parse(html, telegram_web.spec_for("c"), NOW)
    assert [it.id for it in out] == ["tg:c:2"]
    assert out[0].published_ts == NOW and out[0].text.startswith(NO_TIMESTAMP_FLAG)


# ===========================================================================
# Bluesky
# ===========================================================================

def test_jetstream_frame_maps_to_item_with_handle_url_and_created_at():
    frames = json.loads(fx("jetstream_frames.json"))
    f = frames[0]
    handle_by_did = {f["did"]: "example.com"}
    it = bluesky.frame_to_item(f, handle_by_did, NOW, {"example.com": ("corp",)})
    assert it is not None
    assert it.id == f"bsky:example.com:{f['commit']['rkey']}" and it.source == "bsky:example.com"
    assert it.url == f"https://bsky.app/profile/example.com/post/{f['commit']['rkey']}"
    assert it.published_ts == pytest.approx(1792922452.349), "record.createdAt 2026-10-25T10:00:52.349Z"
    assert it.seen_ts == NOW and it.domains == ("corp",)
    assert it.text.startswith(f["commit"]["record"]["text"])
    assert "https://www.excavate.top/card/7943" in it.text, "the facet's full link is appended"


def test_jetstream_frames_that_are_not_our_new_posts_are_none():
    frames = json.loads(fx("jetstream_frames.json"))
    f = frames[0]
    assert bluesky.frame_to_item(f, {"did:plc:someone-else": "x.com"}, NOW) is None, "DID not ours"
    assert bluesky.frame_to_item({**f, "kind": "identity"}, {f["did"]: "h"}, NOW) is None
    deleted = {**f, "commit": {**f["commit"], "operation": "delete"}}
    assert bluesky.frame_to_item(deleted, {f["did"]: "h"}, NOW) is None
    liked = {**f, "commit": {**f["commit"], "collection": "app.bsky.feed.like"}}
    assert bluesky.frame_to_item(liked, {f["did"]: "h"}, NOW) is None
    reply = {**f, "commit": {**f["commit"], "record": {**f["commit"]["record"], "reply": {"root": {}}}}}
    assert bluesky.frame_to_item(reply, {f["did"]: "h"}, NOW) is None


def test_author_feed_parses_posts_with_created_at_and_rkey_urls():
    out = bluesky.author_feed_to_items(json.loads(fx("bsky_authorfeed.json")), "kyivpost.com", NOW, ("geo",))
    assert [it.id for it in out] == ["bsky:kyivpost.com:3myovtdsjr22h", "bsky:kyivpost.com:3myotmgt3bs2h", "bsky:kyivpost.com:3myot6egqx22h"]
    a = out[0]
    assert a.published_ts == pytest.approx(1792920988.172), "2026-10-25T09:36:28.172Z"
    assert a.url == "https://bsky.app/profile/kyivpost.com/post/3myovtdsjr22h"
    assert a.title.startswith("Ukrainian drones struck Siberia")
    assert a.text.count("kyivpost.com/post/88099") == 1, "the facet link already shows in the text; not appended twice"
    assert a.domains == ("geo",)


def test_resolve_dids_and_fetch_author_feed_over_a_mock_transport():
    def app(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("resolveHandle"):
            if request.url.params["handle"] == "reuters.com":
                return httpx.Response(200, content=fx("bsky_resolve.json"))
            return httpx.Response(400, json={"error": "InvalidRequest"})
        assert request.url.params["actor"] == "kyivpost.com" and request.url.params["filter"] == "posts_no_replies"
        return httpx.Response(200, content=fx("bsky_authorfeed.json"))
    client = httpx.Client(transport=httpx.MockTransport(app))
    assert bluesky.resolve_dids(["reuters.com", "nope.invalid"], client=client) == {"reuters.com": "did:plc:jbvnehrrdqoulco4rf5gxg5r"}
    out = bluesky.fetch_author_feed("kyivpost.com", client=client, domains=("geo",), seen_ts=NOW)
    assert len(out) == 3 and out[0].source == "bsky:kyivpost.com"


def test_jetstream_url_lists_every_did_and_the_cursor():
    u = bluesky.jetstream_url(["did:plc:a", "did:plc:b"], cursor=1792922453484385)
    assert u.startswith("wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post")
    assert u.count("wantedDids=") == 2 and u.endswith("&cursor=1792922453484385")
    assert "cursor" not in bluesky.jetstream_url(["did:plc:a"])


class _FakeWS:
    def __init__(self, frames, then: Exception | None):
        self.frames, self.then = list(frames), then

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.frames:
            return json.dumps(self.frames.pop(0))
        if self.then:
            raise self.then
        raise StopAsyncIteration


async def test_stream_reconnects_with_cursor_and_backs_off_then_resets():
    frames = json.loads(fx("jetstream_frames.json"))
    # The two captured frames are from two different accounts; both are "ours" here.
    dids = {"h.com": frames[0]["did"], "g.com": frames[1]["did"]}
    urls: list[str] = []
    sleeps: list[float] = []
    stop = asyncio.Event()
    scripts = [
        _FakeWS([frames[0]], ConnectionError("dropped")),      # one frame, then a drop
        _FakeWS([], ConnectionError("refused")),               # fails straight away -> backoff doubles
        _FakeWS([frames[1]], None),                             # a clean close after one frame
    ]

    def connect(url):
        urls.append(url)
        if not scripts:
            stop.set()
            return _FakeWS([], None)
        return scripts.pop(0)

    async def sleep(s):
        sleeps.append(s)

    cursors: list[int] = []
    q: asyncio.Queue = asyncio.Queue()
    dedup = DedupStore(Path("/nonexistent/never-saved.json"))
    await bluesky.stream(q, dids, cursors.append, domains_by_handle={"h.com": ("geo",)},
                         connect=connect, sleep=sleep, clock=lambda: NOW, stop=stop, dedup=dedup)
    assert len(urls) == 4 and "cursor" not in urls[0] and urls[0].count("wantedDids=") == 2
    t1 = frames[0]["time_us"]
    assert urls[1].endswith(f"&cursor={t1 - bluesky.CURSOR_REWIND_US}"), "reconnect resumes a little before the last frame"
    assert urls[2].endswith(f"&cursor={t1 - bluesky.CURSOR_REWIND_US}"), "no frame on the failed attempt: same cursor"
    assert cursors == [frames[0]["time_us"], frames[1]["time_us"]]
    assert sleeps[:2] == [1.0, 2.0], "exponential backoff across the two failures"
    assert sleeps[2] == 0, "a clean close reconnects at once"
    got = [q.get_nowait() for _ in range(q.qsize())]
    assert [g.source for g in got] == ["bsky:h.com", "bsky:g.com"]
    assert got[0].domains == ("geo",) and got[1].domains == (), "domains come from the roster, per handle"


# ===========================================================================
# Tree of Alpha / HN
# ===========================================================================

def test_treeofalpha_maps_id_title_epoch_ms_url_and_source_tag():
    out = treeofalpha.parse(fx("toa.json"), seen_ts=NOW)
    assert len(out) == 5
    a = out[0]
    assert a.id == "toa:2114287006754984371" and a.source == "toa"
    assert a.published_ts == pytest.approx(1792920278.959), "time 1792920278959 ms"
    assert a.title.startswith("Wu Blockchain (@WuBlockchain):")
    assert a.url == "https://x.com/WuBlockchain/status/2114287006754984371#"
    assert a.text.endswith("[Twitter]") and a.domains == ("crypto", "corp")
    assert treeofalpha.SPEC.poll_s >= treeofalpha.MIN_POLL_S == 20, "30 req/min cap"
    with pytest.raises(SourceError):
        treeofalpha.parse(b"{}", seen_ts=NOW)


def test_treeofalpha_prepare_and_handle_use_the_etag():
    state: dict = {}
    url, h = treeofalpha.prepare(treeofalpha.SPEC, state)
    assert url == "https://news.treeofalpha.com/api/news?limit=50" and "If-None-Match" not in h
    out = treeofalpha.handle(200, httpx.Headers({"ETag": 'W/"1552-x"'}), fx("toa.json"), treeofalpha.SPEC, state, NOW)
    assert len(out) == 5 and state["etag"] == 'W/"1552-x"'
    assert treeofalpha.prepare(treeofalpha.SPEC, state)[1]["If-None-Match"] == 'W/"1552-x"'
    assert treeofalpha.handle(304, httpx.Headers({}), b"", treeofalpha.SPEC, state, NOW) == []


def test_hn_algolia_stories_map_created_at_i_title_url_object_id():
    out = hn.parse(fx("hn.json"), seen_ts=NOW)
    assert len(out) == 5
    a = out[0]
    assert a.id == "hn:50229861" and a.source == "hn"
    assert a.published_ts == 1792922209.0, "created_at_i"
    assert a.title == "France asked ISPs to prepare temporary DNS blocks for major social platforms"
    assert a.url.startswith("https://www.blast-info.fr/")
    assert a.domains == ("corp",)
    url, h = hn.prepare(hn.SPEC, {})
    assert "search_by_date" in url and "tags=story" in url and h["User-Agent"] == CONTACT_UA


def test_hn_story_without_a_url_links_to_the_hn_item():
    body = json.dumps({"hits": [{"objectID": "1", "title": "Ask HN: x?", "created_at_i": 1792922000, "story_text": "<p>why</p>"}]}).encode()
    out = hn.parse(body, seen_ts=NOW)
    assert out[0].url == "https://news.ycombinator.com/item?id=1" and out[0].text == "Ask HN: x?\nwhy"
    with pytest.raises(SourceError):
        hn.parse(b'{"nope": 1}', seen_ts=NOW)


# ===========================================================================
# Roster
# ===========================================================================

def test_roster_v1_is_well_formed():
    keys = [s.key for s in roster.V1]
    assert len(keys) == len(set(keys)), "no duplicate keys"
    for s in roster.V1:
        assert s.kind in roster.KINDS and s.domains and set(s.domains) <= set(roster.DOMAINS)
        if s.kind == "rss":
            assert s.url.startswith("https://") and s.poll_s >= 60
        if s.kind == "tg":
            assert s.channel and s.key == f"tg:{s.channel.lower()}" and s.poll_s >= 30
        if s.kind == "bsky":
            assert s.handle and s.key == f"bsky:{s.handle.lower()}" and s.poll_s == 0
    sec = next(s for s in roster.V1 if s.key == "sec:8k")
    assert sec.headers["User-Agent"] == "poly-news-bot vrnroman@gmail.com" and "output=atom" in sec.url
    assert next(s for s in roster.V1 if s.key == "rss:trumpstruth").url == "https://trumpstruth.org/feed"
    assert next(s for s in roster.V1 if s.key == "toa").poll_s >= 20
    for ch in ("insiderpaper", "clashreport", "visegrad_24", "financialjuice", "walterbloomberg", "wublockchainenglish", "watcherguru"):
        assert f"tg:{ch}" in keys
    for h in ("reuters.com", "apnews.com", "polymarket.com", "unusualwhales.bsky.social"):
        assert f"bsky:{h}" in keys


def test_roster_load_applies_default_domains_disable_list_and_poll_override():
    base = roster.load({})
    assert all(set(s.domains) & set(roster.DEFAULT_DOMAINS) for s in base)
    assert not any(s.key in ("rss:variety", "tg:fabrizioromano") for s in base), "ent/sport off by default (ruling 2026-10-25)"
    everything = roster.load({"NEWS_DOMAINS": ",".join(roster.DOMAINS)})
    assert len(everything) == len(roster.V1) > len(base)
    off = roster.load({"NEWS_SOURCES_DISABLE": "tg:financialjuice, toa,hn"})
    off_keys = {s.key for s in off}
    assert not {"tg:financialjuice", "toa", "hn"} & off_keys and "sec:8k" in off_keys
    fast = roster.load({"NEWS_POLL_TG_FINANCIALJUICE_S": "5", "NEWS_POLL_RSS_NYT_HOME_S": "15", "NEWS_POLL_TOA_S": "abc"})
    by = {s.key: s for s in fast}
    assert by["tg:financialjuice"].poll_s == 15, "floored: a Telegram page is ~140 KB"
    assert by["rss:nyt-home"].poll_s == 15 and by["toa"].poll_s == 20, "a bad override is ignored"
    kinds = roster.by_kind(base)
    assert set(kinds) == set(roster.KINDS) and kinds["toa"][0].key == "toa"


def test_roster_rejects_unknown_kind_or_domain_and_duplicate_keys():
    with pytest.raises(ValueError):
        roster.Source(key="x", kind="smoke", domains=("geo",))
    with pytest.raises(ValueError):
        roster.Source(key="x", kind="rss", domains=("weather",))
    dup = (roster.V1[0], roster.V1[0])
    with pytest.raises(ValueError, match="duplicate"):
        roster.load({}, sources=dup)


def test_counters_persist_and_reload(tmp_path):
    p = tmp_path / "news" / "roster.json"
    c = roster.Counters(p, save_every_s=30)
    c.ok("tg:x", 3, NOW, last_item_ts=NOW - 40)
    c.ok("tg:x", 0, NOW + 30, last_item_ts=NOW - 100)
    c.error("rss:y", NOW + 1, "HTTP 429")
    assert c.save(NOW) is True
    assert c.save(NOW + 5) is False, "throttled"
    c.ok("tg:x", 1, NOW + 60)
    assert c.save(NOW + 10) is False and c.save(NOW + 10, force=True) is True
    again = roster.Counters(p)
    snap = again.snapshot()
    assert snap["tg:x"]["items"] == 4 and snap["tg:x"]["last_ok_ts"] == NOW + 60
    assert snap["tg:x"]["last_item_ts"] == NOW - 40, "the newest published_ts, not the latest call's"
    assert snap["rss:y"]["errors"] == 1 and snap["rss:y"]["last_error"]["msg"] == "HTTP 429"
    assert not list(p.parent.glob("*.tmp"))


# ===========================================================================
# Poller
# ===========================================================================

class _Resp:
    def __init__(self, status, body=b"", headers=None):
        self.status_code, self.content, self.headers = status, body, httpx.Headers(headers or {})


class _FakeClient:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    async def get(self, url, headers=None):
        self.calls.append((url, dict(headers or {})))
        step = self.script.pop(0) if self.script else _Resp(200, fx("toa.json"))
        if isinstance(step, Exception):
            raise step
        return step


def _run(src, script, n_sleeps, dedup, counters, clock_ts=NOW):
    sleeps: list[float] = []
    stop = asyncio.Event()
    q: asyncio.Queue = asyncio.Queue()
    client = _FakeClient(script)

    async def sleep(s):
        sleeps.append(s)
        if len(sleeps) >= n_sleeps:
            stop.set()

    asyncio.run(poller.run_pollers([src], q, dedup, counters, client=client, sleep=sleep, clock=lambda: clock_ts, stop=stop))
    return sleeps, q, client


def test_poller_backs_off_on_429_doubling_up_to_the_cap_and_recovers(tmp_path):
    src = next(s for s in roster.V1 if s.key == "toa")
    dedup = DedupStore(tmp_path / "seen.json")
    counters = roster.Counters(tmp_path / "roster.json")
    script = [_Resp(429), _Resp(429), _Resp(403), _Resp(200, fx("toa.json"), {"ETag": '"t"'}), _Resp(304)]
    sleeps, q, client = _run(src, script, n_sleeps=5, dedup=dedup, counters=counters)
    assert sleeps == [40, 80, 160, 20, 20], "20 s base: doubles per 429/403, back to base on the next 200"
    assert q.qsize() == 5 and counters.snapshot()["toa"]["errors"] == 3 and counters.snapshot()["toa"]["items"] == 5
    assert client.calls[4][1]["If-None-Match"] == '"t"', "the ETag the 200 carried rides the next request"
    assert dedup.seen("toa:2114287006754984371")


def test_poller_backoff_is_capped_at_thirty_minutes(tmp_path):
    src = roster.Source(key="rss:t", kind="rss", domains=("geo",), poll_s=600, url="https://e.invalid/f")
    sleeps, _, _ = _run(src, [_Resp(429)] * 4, n_sleeps=4, dedup=DedupStore(tmp_path / "s.json"),
                        counters=roster.Counters(tmp_path / "r.json"))
    assert sleeps == [1200, 1800, 1800, 1800]


def test_poller_dedups_across_polls_and_a_source_error_backs_off(tmp_path):
    src = roster.Source(key="tg:c", kind="tg", channel="c", domains=("geo",), poll_s=30)
    dedup = DedupStore(tmp_path / "seen.json")
    counters = roster.Counters(tmp_path / "roster.json")
    page = fx("tg_financialjuice.html")
    script = [_Resp(200, page), _Resp(200, page), _Resp(200, fx("tg_reuters_nopreview.html")), httpx.ConnectTimeout("slow")]
    sleeps, q, client = _run(src, script, n_sleeps=4, dedup=dedup, counters=counters)
    assert q.qsize() == 3, "the second identical page adds nothing"
    assert sleeps == [30, 30, 60, 60], "no-preview page doubles; a transport timeout keeps the interval"
    snap = counters.snapshot()["tg:c"]
    assert snap["items"] == 3 and snap["errors"] == 2 and "no public preview" in snap["last_error"]["msg"] or "ConnectTimeout" in snap["last_error"]["msg"]
    assert client.calls[0][1]["User-Agent"].startswith("Mozilla/5.0")
    assert json.loads((tmp_path / "seen.json").read_text())["ids"][:1] == ["tg:c:142489"], "dedup saved to disk"
    assert (tmp_path / "roster.json").exists()


def test_poller_logs_a_backoff_once_per_episode(tmp_path, monkeypatch):
    lines: list[str] = []
    monkeypatch.setattr(poller.logger, "warn", lambda m: lines.append(m))
    monkeypatch.setattr(poller.logger, "info", lambda m: lines.append(m))
    src = next(s for s in roster.V1 if s.key == "hn")
    _run(src, [_Resp(429)] * 3 + [_Resp(200, fx("hn.json"))], n_sleeps=4,
         dedup=DedupStore(tmp_path / "s.json"), counters=roster.Counters(tmp_path / "r.json"))
    backoffs = [ln for ln in lines if "backing off" in ln]
    assert len(backoffs) == 1 and "source=hn status=429" in backoffs[0]
    assert any("recovered" in ln for ln in lines)
    assert all(ln.startswith("[news-src]") for ln in lines)


def test_poller_skips_bluesky_sources_and_idles_on_an_empty_roster(tmp_path):
    only_socket = [s for s in roster.V1 if s.kind == "bsky"][:2]
    q: asyncio.Queue = asyncio.Queue()
    asyncio.run(poller.run_pollers(only_socket, q, DedupStore(tmp_path / "s.json"), roster.Counters(tmp_path / "r.json"),
                                   client=_FakeClient([]), stop=asyncio.Event()))
    assert q.qsize() == 0
