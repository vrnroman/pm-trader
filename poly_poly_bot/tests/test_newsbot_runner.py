"""The news bot's supervisor, end to end on fakes (run s-pw9rom, 2026-10-25).

Drives the production entry points (``Runner.process_item``, ``scan_jumps``,
``mark_all``, ``news_text``) with a fake index, a scripted ``claude -p``
runner and ladders set on the real QuoteBook. No network, no wall clock
where a ``now`` is supplied.
"""

import json
import threading

import pytest

from src.newsbot import index as index_mod
from src.newsbot import judge as judge_mod
from src.newsbot import runner as runner_mod
from src.newsbot.items import Item
from src.newsbot.tape import clob_ws, livedata


class FakeIndex:
    def __init__(self, cands):
        self.cands = cands
        self.refreshed = 0

    def refresh(self, *a, **k):
        self.refreshed += 1

    def stats(self):
        return {"n_markets": len(self.cands)}

    def candidates(self, text, k=8, domains=None, *, now=None):
        words = set(text.lower().split())
        return [c for c in self.cands if words & set(c.question.lower().split())][:k]

    def by_condition(self, cid):
        return next((c for c in self.cands if c.condition_id == cid), None)

    def by_token(self, tok):
        return next((c for c in self.cands if tok in c.token_ids), None)

    def all_token_ids(self, domains=None):
        return [t for c in self.cands for t in c.token_ids]


def _cand(mid, cid, q, toks, dom=("corp",), sports=False):
    return index_mod.Candidate(market_id=mid, condition_id=cid, question=q, event_title=q, tags=(),
                               domains=dom, outcomes=["Yes", "No"], token_ids=list(toks),
                               best_bid=0.40, best_ask=0.42, end_ts=None, is_sports=sports)


def _envelope(obj):
    return {"result": json.dumps(obj), "duration_api_ms": 1200, "total_cost_usd": 0.01}


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NEWS_STAKE_USD", "5")
    monkeypatch.setenv("NEWS_DOMAINS", "corp,geo")
    monkeypatch.setenv("NEWS_LLM_DAILY_BUDGET", "10")
    # no network anywhere: the roster is loaded but nothing polls in these tests;
    # fee reads and REST books are stubbed
    monkeypatch.setattr(runner_mod.Runner, "_rest_book", lambda self, tok: None)
    import src.copy_trading.fee_rate as fr
    monkeypatch.setattr(fr, "fee_bps", lambda tok, now=None: 500)
    sent = []
    import src.telegram_bot as tb
    monkeypatch.setattr(tb, "send_message", lambda text, kind=None, **k: sent.append((kind, text)) or True)
    r = runner_mod.Runner(threading.Event())
    cands = [_cand("m1", "c1", "Will Anthropic announce an IPO in 2026?", ["ta", "tb"]),
             _cand("m2", "c2", "Will the Fed cut rates in December?", ["tc", "td"]),
             _cand("m9", "c9", "Lakers vs Celtics", ["te", "tf"], dom=("sport",), sports=True)]
    r.index = FakeIndex(cands)
    # a quiet, quoted book for the Anthropic market: fresh
    lad = clob_ws.parse_ladder({"bids": [{"price": "0.40", "size": "100"}], "asks": [{"price": "0.42", "size": "100"}]}, ts_ms=1_000_000)
    for tok in ("ta", "tb", "tc", "td", "te", "tf"):
        r.book.set_ladder(tok, lad)
    r.book.record("ta", 1_000_000, 0.40, 0.42)
    r.book.record("ta", 1_600_000, 0.40, 0.42)
    return r, sent


def _item(i="bsky:reuters.com:1", title="Anthropic to announce IPO, Dario says", src="bsky:reuters.com"):
    return Item(id=i, source=src, domains=("corp",), published_ts=1500.0, seen_ts=1510.0,
                title=title, text="", url="https://x")


def _fake_claude(material=True, market="m1", idx=0, prob=0.7):
    obj = {"material": material, "market_id": market, "outcome_index": idx, "direction": "yes",
           "implied_prob": prob, "confidence": 0.8, "why": "new information", "already_priced": False}
    def run_claude(prompt, **kw):
        return {"result": json.dumps(obj), "duration_api_ms": 1200, "total_cost_usd": 0.01}
    return run_claude


def test_a_fresh_material_item_fires_llm_headline_any_and_random(rig, monkeypatch):
    r, sent = rig
    monkeypatch.setattr(judge_mod, "run_claude", _fake_claude())
    out = r.process_item(_item(), now=1700.0)
    assert out and out["fired"] and out["state"] == "fresh"
    assert len(r.books["llm"].ledger.rows) == 1
    assert len(r.books["headline-any"].ledger.rows) == 1
    assert len(r.books["random"].ledger.rows) == 1
    row = next(iter(r.books["llm"].ledger.rows.values()))
    assert row.entry_price == 0.42 and row.token_id == "ta" and row.freshness == "fresh"
    assert row.fee_usd == pytest.approx(5 * 0.05 * 0.58, abs=1e-3)
    # the phone got one fire message, with no confidence number in it
    kinds = [k for k, _ in sent]
    assert kinds.count("news") == 1
    text = sent[0][1]
    assert "Paper BUY" in text and "0.8" not in text.split("tape:")[0].split("@")[1][:30]
    # the lead ledger has the item with its four clocks
    it = r.leads.items[_item().id]
    assert it.fired and it.published_ts == 1500.0 and it.seen_ts == 1510.0 and it.quote_ts == 1700.0


def test_the_same_item_twice_never_double_books(rig, monkeypatch):
    r, sent = rig
    monkeypatch.setattr(judge_mod, "run_claude", _fake_claude())
    r.process_item(_item(), now=1700.0)
    r.process_item(_item(), now=1800.0)
    assert len(r.books["llm"].ledger.rows) == 1 and len(r.books["headline-any"].ledger.rows) == 1
    assert sum(1 for k, _ in sent if k == "news") == 1


def test_a_moving_tape_blocks_the_llm_book_but_not_headline_any(rig, monkeypatch):
    r, sent = rig
    # the Anthropic market ran 8c in the last minutes
    r.book.record("ta", 1_650_000, 0.48, 0.50)
    r.book.record("ta", 1_690_000, 0.49, 0.51)
    monkeypatch.setattr(judge_mod, "run_claude", _fake_claude())
    out = r.process_item(_item(i="x2"), now=1700.0)
    assert out and not out["fired"] and out["state"] in ("moving", "late")
    assert len(r.books["llm"].ledger.rows) == 0 and len(r.books["headline-any"].ledger.rows) == 1
    assert len(r.books["random"].ledger.rows) == 0
    assert not [k for k, _ in sent if k == "news"]


def test_not_material_and_wrong_domain_fire_nothing(rig, monkeypatch):
    r, sent = rig
    monkeypatch.setattr(judge_mod, "run_claude", _fake_claude(material=False, market=None, idx=None))
    assert r.process_item(_item(i="x3"), now=1700.0) is None
    ent = Item(id="x4", source="rss:variety", domains=("ent",), published_ts=1.0, seen_ts=2.0,
               title="Anthropic IPO", text="", url="")
    assert r.process_item(ent, now=1700.0) is None
    assert not r.books["llm"].ledger.rows and not r.books["headline-any"].ledger.rows


def test_budget_exhausted_means_no_fire_and_no_crash(rig, monkeypatch):
    r, sent = rig
    for _ in range(10):
        r.budget.take()
    called = []
    monkeypatch.setattr(judge_mod, "run_claude", lambda *a, **k: called.append(1))
    assert r.process_item(_item(i="x5"), now=1700.0) is None
    assert not called, "no LLM call past the daily cap"


def test_jump_with_a_headline_books_tape_first_and_a_dark_jump_is_counted(rig):
    r, sent = rig
    # recent item about the Fed, then a Fed market jump: explained, tape-first fires
    r.recent.append(_item(i="bsky:wsj.com:9", title="Fed cuts rates by 25bp, Powell says", src="bsky:wsj.com"))
    r.item_by_id["bsky:wsj.com:9"] = r.recent[-1]
    lad = clob_ws.parse_ladder({"bids": [{"price": "0.55", "size": "50"}], "asks": [{"price": "0.58", "size": "50"}]}, ts_ms=1_700_000)
    r.book.set_ladder("tc", lad)
    base = 1600.0
    for i, px in enumerate([0.40, 0.42, 0.47, 0.52, 0.56]):
        r.buckets.add(livedata.Trade(condition_id="c2", asset="tc", price=px, yes_price=px, size=100, ts=base + i * 30,
                                     side="BUY", outcome="Yes", title="Fed", slug="fed"))
    # an unexplained jump on the Anthropic market: dark
    for i, px in enumerate([0.40, 0.44, 0.50, 0.55]):
        r.buckets.add(livedata.Trade(condition_id="c1", asset="ta", price=px, yes_price=px, size=100, ts=base + i * 30,
                                     side="BUY", outcome="Yes", title="A", slug="a"))
    # a sports jump is excluded
    for i, px in enumerate([0.40, 0.60]):
        r.buckets.add(livedata.Trade(condition_id="c9", asset="te", price=px, yes_price=px, size=100, ts=base + i * 30,
                                     side="BUY", outcome="Yes", title="L", slug="l"))
    n = r.scan_jumps(now=base + 150)
    assert n == 2
    fed = next(j for j in r.leads.jumps.values() if j.condition_id == "c2")
    ant = next(j for j in r.leads.jumps.values() if j.condition_id == "c1")
    assert fed.dark is False and fed.first_source == "bsky:wsj.com" and fed.lead_s is not None
    assert ant.dark is True
    assert len(r.books["tape-first"].ledger.rows) == 1
    tf = next(iter(r.books["tape-first"].ledger.rows.values()))
    assert tf.token_id == "tc" and tf.entry_price == 0.58
    assert r.scan_jumps(now=base + 151) == 0, "a jump is reported once"


def test_marks_move_the_item_ledger_and_ping_a_missed_move(rig, monkeypatch):
    r, sent = rig
    # an item mapped but not fired (tape said moving), then the market keeps going our way
    r.book.record("ta", 1_650_000, 0.48, 0.50)
    r.book.record("ta", 1_690_000, 0.49, 0.51)
    monkeypatch.setattr(judge_mod, "run_claude", _fake_claude())
    r.process_item(_item(i="x6"), now=1700.0)
    it = r.leads.items["x6"]
    assert it.fired is False and it.mid_at_decision == pytest.approx(0.50)
    r.book.record("ta", 3_600_000, 0.60, 0.62)
    r.book.set_ladder("ta", clob_ws.parse_ladder({"bids": [{"price": "0.60", "size": "50"}], "asks": [{"price": "0.62", "size": "50"}]}, ts_ms=3_600_000))
    r.mark_all(now=1700.0 + 1801)
    assert r.leads.items["x6"].moved["5m"] == pytest.approx(11.0) and "30m" in r.leads.items["x6"].moved
    assert any("Moved without us" in t for k, t in sent)
    r.mark_all(now=1700.0 + 1802)
    assert sum(1 for k, t in sent if "Moved without us" in t) == 1, "pinged once"


def test_news_text_reads_from_disk_when_no_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runner_mod, "_RUNNER", None)
    text = runner_mod.news_text()
    assert "News bot" in text and "n=0" in text


def test_report_text_prints_n_everywhere(rig, monkeypatch):
    r, sent = rig
    monkeypatch.setattr(judge_mod, "run_claude", _fake_claude())
    r.process_item(_item(i="x7"), now=1700.0)
    text = r.report_text()
    assert "1 fired" in text and "llm:" in text and "random:" in text and "LLM calls today 1/10" in text
    assert "—" not in text


def test_owner_text_becomes_an_item_on_the_queue(rig):
    r, sent = rig
    r.owner_text("Dario says Anthropic will IPO", {"message_id": 5, "date": 1234})
    item = r.queue.get_nowait()
    assert item.source == "owner" and item.published_ts == 1234.0 and item.domains == ("corp", "geo")


def test_stale_items_are_counted_not_judged(rig, monkeypatch):
    r, sent = rig
    called = []
    monkeypatch.setattr(judge_mod, "run_claude", lambda *a, **k: called.append(1))
    old = Item(id="old1", source="rss:nyt-home", domains=("corp",), published_ts=1000.0, seen_ts=1700.0,
               title="Anthropic to announce IPO", text="", url="")
    assert r.process_item(old, now=1700.0 + 3600) is None
    assert not called and sum(r.day_stale.values()) == 1
    # the owner's forwards are never stale
    mine = Item(id="own1", source="owner", domains=("corp",), published_ts=1000.0, seen_ts=1700.0,
                title="Anthropic to announce IPO", text="", url="")
    monkeypatch.setattr(judge_mod, "run_claude", _fake_claude())
    assert r.process_item(mine, now=1700.0 + 3600) is not None
    assert "stale skipped" in r.report_text(now=1700.0 + 3600)
