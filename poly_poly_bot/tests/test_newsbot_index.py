"""newsbot.index: the Gamma universe in SQLite + FTS5, searched by headline.

The fixture is one Gamma ``/markets?include_tag=true`` page captured 2026-10-25
(28 real rows) plus 10 synthetic rows (``_synthetic`` key) for the shapes the
real page happened not to contain: an Anthropic IPO book, a Gaza ceasefire, a
Bitcoin ETF, 5m/15m up-down books, a sub-floor row, a sportsMarketType row with
no sports tag, a 3-outcome row. Nothing here touches the network or the clock.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.newsbot import index
from src.newsbot.index import MarketIndex, PageError

FIXTURE = Path(__file__).parent / "fixtures" / "newsbot" / "gamma_markets.json"
NOW = datetime(2026, 10, 25, 14, 0, tzinfo=timezone.utc).timestamp()


@pytest.fixture(scope="module")
def page() -> list[dict]:
    return json.loads(FIXTURE.read_text())


@pytest.fixture
def idx(tmp_path, page):
    ix = MarketIndex(tmp_path / "news" / "index.sqlite", volume_min=5000)
    ix.refresh(lambda: [page], now=NOW)
    yield ix
    ix.close()


def _ids(cands):
    return [c.market_id for c in cands]


# -- static rules ------------------------------------------------------------

@pytest.mark.parametrize("question,slug,expect", [
    ("Bitcoin Up or Down - October 25, 3:40PM-3:45PM ET", "btc-updown-5m-1793043600", True),
    ("Ethereum Up or Down - October 25, 3:30PM-3:45PM ET", "eth-updown-15m-1793043000", True),
    ("Bitcoin Up or Down - October 24, 9:45AM-10:00AM ET", "weird-slug", True),      # window spans noon-ish, 15 min
    ("Bitcoin Up or Down - October 24, 11:55PM-12:00AM ET", "x", True),              # crosses midnight
    ("Bitcoin Up or Down on October 25?", "bitcoin-up-or-down-on-october-25", False),  # the daily book stays
    ("Bitcoin Up or Down - October 24, 9:00AM-10:00AM ET", "x", False),              # hourly stays
    ("Will Bitcoin reach $90,000 in October?", "will-bitcoin-reach-90000", False),
    ("Solana 5 minute up or down", "sol-5m", True),
])
def test_short_updown_rule(question, slug, expect):
    assert index.is_short_updown(question, slug) is expect


def test_domain_map_and_sports():
    assert index.derive_domains(["Politics", "Trump"], False) == ("politics",)
    assert index.derive_domains(["Geopolitics", "Israel", "Politics"], False) == ("geo", "politics")
    assert index.derive_domains(["Crypto", "Bitcoin"], False) == ("crypto",)
    assert index.derive_domains(["Tech", "AI", "IPO"], False) == ("corp",)
    assert index.derive_domains(["Culture", "Movies"], False) == ("ent",)
    assert index.derive_domains(["Israel Election"], False) == ("politics",)
    assert index.derive_domains([], True) == ("sport",)
    assert index.is_sports_market({"sportsMarketType": "moneyline"}, [])
    assert index.is_sports_market({}, ["NFL (All)"])
    assert index.is_sports_market({}, ["LoL Worlds 2026"])
    assert not index.is_sports_market({}, ["Politics", "Fed"])


def test_query_tokens_drop_stopwords_and_dupes():
    assert index.query_tokens("The Fed cuts rates, the Fed!") == ["fed", "cuts", "rates"]
    assert index.query_tokens("   ") == []


# -- refresh -------------------------------------------------------------------

def test_refresh_upserts_and_applies_static_exclusions(idx, page):
    summary = idx.refresh(lambda: [page], now=NOW)
    assert summary["complete"] is True
    assert summary["rows"] == len(page) == 38
    assert summary["skipped_updown"] == 2          # 5m BTC + 15m ETH
    assert summary["skipped_volume"] == 1          # Claude 6 at $1200 < $5000
    assert summary["upserted"] == 35
    assert summary["deleted"] == 0                 # second pass over the same page: nothing vanished
    assert idx.by_market("9000006") is None and idx.by_market("9000007") is None
    assert idx.by_market("9000008") is None
    assert idx.by_market("6084603") is not None    # daily "Bitcoin Up or Down on October 25?" is kept

    st = idx.stats()
    assert st["n_markets"] == 35
    assert st["last_refresh_ts"] == NOW and st["last_full_refresh_ts"] == NOW
    assert st["by_domain"]["sport"] == st["n_sports"] == 7
    for d in ("politics", "geo", "crypto", "corp", "ent", "sport"):
        assert st["by_domain"][d] > 0


def test_refresh_reads_domains_from_market_tags(idx):
    fed = idx.by_market("2589811")
    assert fed is not None
    assert "corp" in fed.domains and "Fed" in fed.tags
    assert fed.event_title == "Fed Decision in October?"
    assert fed.outcomes == ["Yes", "No"] and len(fed.token_ids) == 2
    assert fed.best_bid is not None and fed.best_ask is not None and fed.best_bid <= fed.best_ask
    assert fed.end_ts == datetime(2026, 10, 29, 3, 59, tzinfo=timezone.utc).timestamp()
    assert fed.neg_risk is True                     # the Fed decision event is a neg-risk group
    assert idx.by_market("9000001").neg_risk is False

    clasico = idx.by_market("5598481")
    assert clasico.is_sports and "sport" in clasico.domains

    chiefs = idx.by_market("9000009")             # sportsMarketType with a non-sports-looking tag
    assert chiefs.is_sports and chiefs.domains == ("sport",)

    gaza = idx.by_market("9000003")
    assert gaza.domains == ("geo",)


def test_by_token_aligned_with_outcomes(idx):
    oscar = idx.by_market("9000010")
    assert oscar.outcomes == ["Sinners", "Hamnet", "One Battle After Another"]
    assert len(oscar.token_ids) == 3
    assert idx.by_token(oscar.token_ids[2]).market_id == "9000010"
    assert idx.outcome_index(oscar.token_ids[2]) == 2
    assert idx.by_token("not-a-token") is None
    assert idx.by_market("nope") is None


def test_all_token_ids_filters_by_domain(idx):
    every = idx.all_token_ids()
    crypto = idx.all_token_ids(["crypto"])
    assert len(every) == 35 * 2 + 1                 # 34 binary rows + the 3-outcome Oscar row
    assert len(set(every)) == len(every)
    assert set(crypto) < set(every)
    assert all("crypto" in idx.by_token(t).domains for t in crypto)
    assert idx.all_token_ids(["sport"]) and all(idx.by_token(t).is_sports for t in idx.all_token_ids(["sport"]))


def test_refresh_incremental_deletes_closed_and_vanished(idx, page):
    page2 = [m for m in page if m["id"] not in ("9000001", "616902")]   # delisted
    closed = dict(next(m for m in page if m["id"] == "9000003"), closed=True)
    page2 = [closed if m["id"] == "9000003" else m for m in page2]
    summary = idx.refresh(lambda: [page2], now=NOW + 600)
    assert summary["complete"] and summary["deleted"] == 2 and summary["skipped_closed"] == 1
    assert idx.by_market("9000001") is None and idx.by_market("616902") is None
    assert idx.by_market("9000003") is None
    assert idx.by_token("990000010001") is None   # tokens go with the market
    assert idx.stats()["n_markets"] == 32
    assert idx.candidates("Anthropic IPO", k=3, now=NOW) and "9000001" not in _ids(idx.candidates("Anthropic IPO", k=3, now=NOW))


def test_refresh_failed_page_keeps_old_rows(idx, page, caplog):
    def flaky():
        yield page[:5]
        raise PageError("gamma offset=100: 502")

    with caplog.at_level(logging.WARNING):
        summary = idx.refresh(flaky, now=NOW + 1200)
    assert summary["complete"] is False and summary["pages"] == 1 and summary["deleted"] == 0
    assert "old rows kept" in caplog.text
    assert idx.stats()["n_markets"] == 35
    assert idx.stats()["last_refresh_ts"] == NOW + 1200       # partial pass still refreshed quotes
    assert idx.stats()["last_full_refresh_ts"] == NOW          # but was not a full pass

    def broken():
        raise RuntimeError("boom")
        yield  # noqa: unreachable, makes it a generator

    summary = idx.refresh(broken, now=NOW + 1800)
    assert summary["complete"] is False and summary["error"] and idx.stats()["n_markets"] == 35
    assert idx.stats()["last_refresh_ts"] == NOW + 1200       # nothing was read this time


def test_refresh_empty_universe_is_not_a_full_pass(idx):
    summary = idx.refresh(lambda: [], now=NOW + 60)
    assert summary["complete"] is False and summary["deleted"] == 0
    assert idx.stats()["n_markets"] == 35


def test_refresh_updates_quotes_in_place(idx, page):
    fed = dict(next(m for m in page if m["id"] == "2589811"), bestBid=0.5, bestAsk=0.52)
    idx.refresh(lambda: [[fed]], now=NOW + 60)      # a one-row "page": a complete pass deletes the rest
    c = idx.by_market("2589811")
    assert (c.best_bid, c.best_ask) == (0.5, 0.52)
    assert idx.stats()["n_markets"] == 1


def test_volume_floor_from_env(tmp_path, page, monkeypatch):
    monkeypatch.setenv("NEWS_INDEX_VOLUME_MIN", "1000000")
    ix = MarketIndex(tmp_path / "hi.sqlite")
    assert ix.volume_min == 1_000_000
    s = ix.refresh(lambda: [page], now=NOW)
    assert s["skipped_volume"] > 1 and ix.stats()["n_markets"] == s["upserted"] < 35
    ix.close()


# -- candidates ----------------------------------------------------------------

@pytest.mark.parametrize("headline,first,domain", [
    ("Anthropic announces IPO", "9000001", "corp"),
    ("ceasefire in Gaza", "9000003", "geo"),
    ("Bitcoin ETF approved", "9000005", "crypto"),
])
def test_candidates_rank_the_obvious_market_first(idx, headline, first, domain):
    cands = idx.candidates(headline, k=8, now=NOW)
    assert cands and cands[0].market_id == first
    assert domain in cands[0].domains
    assert cands[0].score > cands[-1].score > 0
    assert len(cands) <= 8
    assert isinstance(cands[0].outcomes, list) and len(cands[0].token_ids) == len(cands[0].outcomes)


def test_candidates_fed_cuts_rates(idx):
    cands = idx.candidates("Fed cuts rates", k=8, now=NOW)
    fed_ids = {"2589811", "2589812", "2589813", "616902"}
    assert set(_ids(cands)[:4]) == fed_ids
    assert "2589811" in _ids(cands)[:4]             # the "decrease by 25 bps" leg is offered
    assert not any(c.is_sports for c in cands)


def test_candidates_penalise_sports_and_filter_by_domain(idx):
    cands = idx.candidates("Real Madrid beat Barcelona", k=8, now=NOW)
    assert cands and all(c.is_sports for c in cands)
    assert all("sport" in c.domains for c in cands)
    assert idx.candidates("Real Madrid beat Barcelona", k=8, domains=["politics"], now=NOW) == []
    # the same text indexed as a non-sports row would score 1/0.35 higher: the penalty is applied
    raw = max(c.score for c in cands)
    assert raw < 5


def test_candidates_penalise_markets_ending_within_two_hours(idx):
    far = idx.candidates("US Iran ceasefire", k=8, now=NOW)
    by_id = {c.market_id: c for c in far}
    assert by_id["4641065"].score == by_id["5686982"].score   # same text, same end-of-month-ish horizon
    near_end = datetime(2026, 10, 29, 2, 30, tzinfo=timezone.utc).timestamp()   # 5686982 ends 03:59Z
    near = {c.market_id: c for c in idx.candidates("US Iran ceasefire", k=8, now=near_end)}
    assert near["5686982"].score == pytest.approx(by_id["5686982"].score * index.ENDING_SOON_PENALTY, abs=1e-3)
    assert near["4641065"].score == by_id["4641065"].score
    assert _ids(idx.candidates("US Iran ceasefire", k=8, now=near_end)).index("4641065") \
        < _ids(idx.candidates("US Iran ceasefire", k=8, now=near_end)).index("5686982")


def test_candidates_k_and_empty(idx):
    assert idx.candidates("Anthropic IPO", k=2, now=NOW) and len(idx.candidates("Anthropic IPO", k=2, now=NOW)) == 2
    assert idx.candidates("", now=NOW) == []
    assert idx.candidates("the of and", now=NOW) == []
    assert idx.candidates("zzqxv blorp", now=NOW) == []


def test_like_fallback_when_fts5_missing(tmp_path, page, caplog):
    with caplog.at_level(logging.WARNING):
        ix = MarketIndex(tmp_path / "like.sqlite", use_fts=False, volume_min=5000)
    assert "LIKE search fallback" in caplog.text
    ix.refresh(lambda: [page], now=NOW)
    assert ix.stats()["fts5"] is False and ix.stats()["n_markets"] == 35
    assert ix.candidates("Anthropic announces IPO", k=3, now=NOW)[0].market_id == "9000001"
    assert ix.candidates("ceasefire in Gaza", k=3, now=NOW)[0].market_id == "9000003"
    assert set(_ids(ix.candidates("Fed cuts rates", k=4, now=NOW))) == {"2589811", "2589812", "2589813", "616902"}
    ix.close()


def test_reopen_keeps_rows_and_search(tmp_path, page):
    path = tmp_path / "persist.sqlite"
    ix = MarketIndex(path, volume_min=5000)
    ix.refresh(lambda: [page], now=NOW)
    ix.close()
    ix2 = MarketIndex(path, volume_min=5000)
    assert ix2.stats()["n_markets"] == 35 and ix2.stats()["last_refresh_ts"] == NOW
    assert ix2.candidates("Bitcoin ETF approved", k=1, now=NOW)[0].market_id == "9000005"
    ix2.close()


def test_gamma_fetch_all_pages_by_returned_length_and_raises_page_error():
    class Resp:
        def __init__(self, body, status=200):
            self._body, self.status = body, status

        def raise_for_status(self):
            if self.status != 200:
                raise RuntimeError(f"http {self.status}")

        def json(self):
            return self._body

    class Sess:
        def __init__(self, script):
            self.script, self.calls = list(script), []

        def get(self, url, params=None, timeout=None):
            self.calls.append(params)
            return self.script.pop(0)

    sess = Sess([Resp([{"id": "1"}] * 100), Resp([{"id": "2"}] * 7), Resp([])])
    pages = list(index.gamma_fetch_all(session=sess))
    assert [len(p) for p in pages] == [100, 7]
    assert [c["offset"] for c in sess.calls] == [0, 100, 107]   # step = rows returned, not the limit
    assert sess.calls[0]["include_tag"] == "true" and sess.calls[0]["limit"] == 500

    sess = Sess([Resp([{"id": "1"}]), Resp(None, status=502)])
    gen = index.gamma_fetch_all(session=sess)
    assert len(next(gen)) == 1
    with pytest.raises(PageError):
        next(gen)


def test_gammas_offset_cap_ends_the_pass_as_complete():
    """A 422 at offset >= 2000 is Gamma's cap, not a failed page (2026-10-25)."""
    from src.newsbot import index as idx

    class Resp:
        def __init__(self, status, rows):
            self.status_code = status
            self._rows = rows

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"{self.status_code}")

        def json(self):
            return self._rows

    class Sess:
        def get(self, url, params=None, timeout=None):
            off = params["offset"]
            if off >= 2000:
                return Resp(422, None)
            return Resp(200, [{"id": str(off + i)} for i in range(100)])

    pages = list(idx.gamma_fetch_all(session=Sess(), page_limit=100))
    assert len(pages) == 20 and pages[-1][-1]["id"] == "1999"

    class Sess422Early:
        def get(self, url, params=None, timeout=None):
            return Resp(422, None)

    import pytest as _pt
    with _pt.raises(idx.PageError):
        list(idx.gamma_fetch_all(session=Sess422Early(), page_limit=100))
