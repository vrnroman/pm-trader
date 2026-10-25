"""The news bot's paper book and lead ledger (run s-pw9rom, 2026-10-25)."""

import pytest

from src.newsbot import leads, paper


# ---- paper.walk: the ladder is sorted here, never trusted ----

def test_walk_sorts_the_ladder_and_walks_levels():
    # asks given DESCENDING (the CLOB's order): the best ask is the last row
    asks = [(0.60, 100), (0.55, 4), (0.52, 6)]
    f = paper.walk(asks, 5.0, "ask")
    assert f.top == 0.52 and f.levels == 2
    # 6 shares at 0.52 = 3.12, then 1.88 at 0.55
    assert f.filled_usd == pytest.approx(5.0)
    assert f.avg_price == pytest.approx(5.0 / (6 + 1.88 / 0.55), rel=1e-6)
    bids = [(0.40, 50), (0.48, 3), (0.45, 10)]  # ascending = the CLOB's bid order
    g = paper.walk(bids, 5.0, "bid")
    assert g.top == 0.48 and g.levels == 2


def test_walk_reports_thin_books_and_empty_ladders():
    thin = paper.walk([(0.50, 2)], 5.0, "ask")  # only $1 on the book
    assert thin.filled_usd == pytest.approx(1.0) and thin.avg_price == 0.5
    assert paper.walk([], 5.0, "ask").avg_price is None
    assert paper.walk([(0.0, 10), (0.3, 0)], 5.0, "ask").avg_price is None


# ---- the book ----

@pytest.fixture
def book(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NEWS_STAKE_USD", "5")
    state = {"ask": [(0.42, 50)], "bid": [(0.40, 50)], "fee": 500, "now": 1000.0}
    b = paper.PaperBook("llm", ask_ladder=lambda t: state["ask"], bid_ladder=lambda t: state["bid"],
                        fee_bps=lambda t: state["fee"], now=lambda: state["now"])
    return b, state


def _fire(b, **kw):
    args = dict(item_id="bsky:1", source="bsky:reuters.com", domains=("geo",), market_id="m1",
                condition_id="c1", token_id="t1", outcome="Yes", question="Will X happen?",
                published_ts=900.0, seen_ts=950.0, decided_ts=990.0, freshness="fresh",
                confidence=0.8, why="new")
    args.update(kw)
    return b.fire(**args)


def test_fire_books_the_honest_ask_with_the_fee(book):
    b, st = book
    row = _fire(b)
    assert row is not None and row.entry_price == 0.42 and row.filled_usd == 5.0
    # fee = stake x rate x (1-p) = 5 x 0.05 x 0.58
    assert row.fee_usd == pytest.approx(5 * 0.05 * 0.58, abs=1e-4)
    assert row.shares == pytest.approx(5 / 0.42, abs=1e-3)
    assert row.quote_ts == 1000.0 and row.freshness == "fresh"
    assert _fire(b) is None, "one row per (book, item, token): a restart cannot double-book"
    assert len(b.ledger.rows) == 1


def test_fire_never_books_a_price_the_market_did_not_show(book):
    b, st = book
    st["ask"] = []
    assert _fire(b) is None and not b.ledger.rows
    st["ask"] = None
    assert _fire(b, item_id="x2") is None


def test_marks_come_due_once_each_and_survive_a_restart(book, tmp_path):
    b, st = book
    _fire(b)
    st["now"] = 1000.0 + 301      # 5m due
    st["bid"] = [(0.50, 100)]
    assert b.mark() == 1
    r = next(iter(b.ledger.rows.values()))
    assert "5m" in r.marks and r.marks["5m"]["exit_price"] == 0.5
    # pnl: shares x 0.5 minus exit fee (shares x 0.5 x 0.05 x 0.5) minus cost minus entry fee
    sh = r.shares
    exp = sh * 0.5 - sh * 0.5 * 0.05 * 0.5 - 5.0 - r.fee_usd
    assert r.marks["5m"]["pnl"] == pytest.approx(exp, abs=1e-3)
    assert b.mark() == 0, "already marked: nothing to do"
    # restart: a fresh book on the same ledger file sees the mark and does not re-mark
    b2 = paper.PaperBook("llm", ask_ladder=lambda t: st["ask"], bid_ladder=lambda t: [(0.9, 10)],
                         fee_bps=lambda t: 500, now=lambda: st["now"])
    assert b2.mark() == 0
    st["now"] = 1000.0 + 1801     # 30m due
    assert b2.mark() == 1
    r2 = next(iter(b2.ledger.rows.values()))
    assert r2.marks["5m"]["exit_price"] == 0.5 and r2.marks["30m"]["exit_price"] == 0.9


def test_an_unreadable_bid_marks_unknown_not_zero(book):
    b, st = book
    _fire(b)
    st["now"] = 1400.0
    st["bid"] = []
    assert b.mark() == 1
    r = next(iter(b.ledger.rows.values()))
    assert r.marks["5m"]["pnl"] is None and r.marks["5m"]["exit_price"] is None
    s = paper.summary(b.ledger)
    assert s["horizons"]["5m"] == {"n": 0} or s["horizons"]["5m"]["n"] == 0


def test_settle_waits_for_the_last_horizon_then_closes(book):
    b, st = book
    _fire(b)
    st["now"] = 1000 + 86401
    assert b.mark() == 4
    assert b.settle(lambda cid: "t1") == 1
    r = next(iter(b.ledger.rows.values()))
    assert r.closed and r.resolved is True
    assert r.resolution_pnl == pytest.approx(r.shares - 5.0 - r.fee_usd, abs=1e-4)
    s = paper.summary(b.ledger)
    assert s["resolution"] == {"n": 1, "won": 1, "pnl": round(r.resolution_pnl, 2)}


def test_refund_and_loss_at_resolution(book):
    b, st = book
    _fire(b, item_id="a", token_id="ta")
    _fire(b, item_id="b", token_id="tb")
    st["now"] = 1000 + 86401
    b.mark()
    assert b.settle(lambda cid: "REFUND") == 2
    for r in b.ledger.rows.values():
        assert r.resolution_pnl == pytest.approx(r.shares * 0.5 - 5.0 - r.fee_usd, abs=1e-4)


def test_summary_carries_n_and_sd(book):
    b, st = book
    for i in range(3):
        _fire(b, item_id=f"i{i}", token_id=f"t{i}")
    st["now"] = 1400.0
    st["bid"] = [(0.45, 100)]
    b.mark()
    s = paper.summary(b.ledger)
    h = s["horizons"]["5m"]
    assert h["n"] == 3 and h["sd"] >= 0 and h["roi"] is not None


def test_pick_random_market():
    import random
    class C:
        def __init__(s):
            s.market_id = "m"
            s.condition_id = "c"
            s.token_ids = ["a", "b"]
            s.outcomes = ["Yes", "No"]
            s.question = "q"
    pick = paper.pick_random_market([C()], random.Random(1))
    assert pick[0] == "m" and pick[2] in ("a", "b")
    assert paper.pick_random_market([], random.Random(1)) is None


# ---- leads ----

class It:
    def __init__(self, id, source, ts, title, text=""):
        self.id, self.source, self.published_ts, self.title, self.text = id, source, ts, title, text


@pytest.fixture
def lled(tmp_path):
    return leads.LeadLedger(path=str(tmp_path / "leads.jsonl"))


def _jump(ts=10_000.0, q="Will the Fed cut rates in October?"):
    return leads.JumpRow(jump_id=f"c1:{int(ts // 60)}", ts=ts, condition_id="c1", market_id="m1",
                         question=q, domains=("corp",), delta_cents=12.0, from_price=0.4,
                         to_price=0.52, notional=900.0, n_trades=14)


def test_tokens_and_overlap_ignore_stopwords():
    assert "fed" in leads.tokens("Fed cuts rates") and "the" not in leads.tokens("the Fed")
    assert leads.overlap("Will the Fed cut rates?", "Fed cuts rates by 25bp") >= 2


def test_attribute_finds_the_first_mention_and_signs_the_lead(lled):
    j = _jump()
    assert lled.add_jump(j) and not lled.add_jump(j)
    items = [It("a", "rss:nyt", 9_700.0, "Fed cuts rates by a quarter point"),
             It("b", "bsky:reuters.com", 9_400.0, "Fed cuts rates, Powell says"),
             It("c", "tg:x", 9_500.0, "Weather in Paris")]
    lled.attribute(j, items, lookback_s=900)
    assert j.dark is False and j.first_item_id == "b", "earliest matching mention wins"
    assert j.lead_s == pytest.approx(600.0) and j.candidates_n == 2 and j.judged_by == "overlap"


def test_attribute_marks_dark_when_nothing_matches(lled):
    j = _jump()
    lled.add_jump(j)
    lled.attribute(j, [It("z", "rss:x", 9_900.0, "Football transfer news")], lookback_s=900)
    assert j.dark is True and j.first_item_id == "" and j.lead_s is None


def test_attribute_uses_the_pick_when_given_and_falls_back(lled):
    j = _jump()
    items = [It("a", "s", 9_800.0, "Fed cuts rates"), It("b", "s", 9_700.0, "Fed rates unchanged")]
    lled.attribute(j, items, lookback_s=900, pick=lambda jump, cands: cands[1])
    assert j.first_item_id == "b" and j.judged_by == "llm"
    j2 = _jump(ts=20_000.0)
    lled.attribute(j2, [It("c", "s", 19_800.0, "Fed cuts rates")], lookback_s=900,
                   pick=lambda jump, cands: (_ for _ in ()).throw(RuntimeError("boom")))
    assert j2.dark is True, "a failing picker is not a match"


def test_items_and_stats_with_persistence(lled, tmp_path):
    lled.add_item(leads.ItemRow(item_id="i1", source="s", domains=("geo",), market_id="m", token_id="t",
                                question="q", published_ts=1.0, seen_ts=5.0, decided_ts=11.0, quote_ts=12.0,
                                material=True, fired=True, freshness="fresh", mid_at_decision=0.4))
    lled.mark_item("i1", "24h", 7.0)
    lled.mark_item("i1", "24h", 99.0)  # second mark ignored
    j = _jump()
    j.domains = ("geo",)
    lled.add_jump(j)
    lled.attribute(j, [], lookback_s=900)
    again = leads.LeadLedger(path=str(tmp_path / "leads.jsonl"))
    assert again.items["i1"].moved == {"24h": 7.0} and again.jumps[j.jump_id].dark is True
    s = again.stats(move_cents=5.0)
    g = s["domains"]["geo"]
    assert g["jumps"] == 1 and g["dark"] == 1 and g["dark_frac"] == 1.0
    assert g["fired"] == 1 and g["fired_moved_our_way"] == 1 and g["latency_median_s"] == 6.0
    assert s["domains"]["all"]["items"] == 1


def test_owner_forward_explains_a_dark_jump_without_touching_the_dark_count(lled):
    j = _jump(ts=10_000.0)
    lled.add_jump(j)
    lled.attribute(j, [], lookback_s=900)
    assert j.dark is True
    late = It("owner:1", "owner", 10_000.0 + 2400, "Fed cuts rates, Powell says")
    assert lled.attribute_owner(late, ["c1"]) == 1
    assert j.dark is True and j.owner_explained and j.owner_late_s == pytest.approx(2400.0)
    assert lled.attribute_owner(late, ["c1"]) == 0, "once"
    # a forward a day and a half later explains nothing
    stale = It("owner:2", "owner", 10_000.0 + 2 * 86400, "Fed cuts rates")
    j2 = _jump(ts=10_000.0)
    j2.jump_id = "c1:other"
    lled.add_jump(j2)
    lled.attribute(j2, [], lookback_s=900)
    assert lled.attribute_owner(stale, ["c1"]) == 0
    s = lled.stats()
    a = s["domains"]["all"]
    assert a["dark"] == 2 and a["owner_explained"] == 1 and a["owner_late_median_s"] == pytest.approx(2400.0)


def test_watched_and_unknown_jumps_are_counted(lled):
    j1 = _jump(ts=10_000.0)
    j1.watched = True
    j2 = _jump(ts=20_000.0)
    j2.jump_id = "c1:b"
    j2.watched = False
    for j in (j1, j2):
        lled.add_jump(j)
        lled.attribute(j, [], lookback_s=900)
    a = lled.stats()["domains"]["all"]
    assert a["jumps"] == 2 and a["watched"] == 1 and a["unknown"] == 1


def test_summary_sd_is_the_standard_error_of_the_mean(book):
    b, st = book
    for i in range(4):
        _fire(b, item_id=f"s{i}", token_id=f"t{i}")
    st["now"] = 1400.0
    st["bid"] = [(0.462, 100)]   # four identical rows
    b.mark()
    h = paper.summary(b.ledger)["horizons"]["5m"]
    assert h["n"] == 4 and h["sd"] == 0.0, "identical ROIs have no spread"


def test_overlap_matches_demonyms_and_single_proper_nouns():
    assert leads.overlap("Melania Trump says secured ceasefire in Ukrainian city of Oleshky", "Russia x Ukraine ceasefire") >= 2
    assert leads.overlap("Zelenskiy: Starlink restrictions completely removed", "Will Starlink restore service in Ukraine?") >= 2
    assert leads.overlap("Brazilian voters head to the polls", "Will Lula win Brazil's election?") >= 2
    assert leads.overlap("Jets vs. Dolphins: preview, prediction, what to watch", "Will Macron remain president?") == 0
    assert leads.overlap("a game preview tonight", "Will the game be postponed?") <= 1, "a common word alone is not a match"
    # lowercase tweet, the market carries the casing
    assert leads.overlap("zelenskiy: starlink restrictions completely removed", "Will Starlink restore service in Ukraine?") >= 2
    # an ALL-CAPS wire headline brings no proper nouns of its own
    assert leads.overlap("*WHITE HOUSE: PRESIDENT TO ADDRESS NATION TONIGHT*", "Will the President of France resign?") <= 1
    # two common words shared are not a match either
    assert leads.overlap("Underdog promo code: play $10, get $50 on the game tonight", "Will the game go to overtime tonight?") <= 1
    assert leads.overlap("Fanatics promo for Chiefs vs Seahawks", "Chiefs vs. Seahawks: O/U 47.5") >= 2, "the market's teams are proper nouns"
