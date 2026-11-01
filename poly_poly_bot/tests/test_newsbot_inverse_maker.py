"""Run s-wj4gnb (2026-11-01): fresh marks, the inverse / tight / maker books,
and the pre-registered go-live bar.

The first week's marks walked the ladder cached at entry for every token the
watch set had evicted, so the "2h exit" was the spread. These tests drive the
production seams (``Runner.process_item``, ``Runner.mark_all``,
``PaperBook.mark``, ``MakerDesk.check``, ``pnl.pnl_text``) and assert both
directions of every rule.
"""

import json
import threading

import pytest

from src.newsbot import judge as judge_mod
from src.newsbot import maker as maker_mod
from src.newsbot import paper, pnl, verdict
from src.newsbot import runner as runner_mod
from src.newsbot.tape import clob_ws
from tests.test_newsbot_runner import FakeIndex, _cand, _fake_claude, _item


# ---- the paper book: a mark reads a current book or says unknown ----

def _book(tmp_path, monkeypatch, *, ts):
    monkeypatch.setenv("NEWS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NEWS_STAKE_USD", "5")
    st = {"ask": [(0.42, 50)], "bid": [(0.40, 50)], "now": 1000.0, "ts": ts}
    b = paper.PaperBook("llm", ask_ladder=lambda t: st["ask"], bid_ladder=lambda t: st["bid"],
                        fee_bps=lambda t: 0, now=lambda: st["now"], book_ts=lambda t: st["ts"])
    return b, st


def _fire(b, **kw):
    args = dict(item_id="i1", source="s", domains=("geo",), market_id="m1", condition_id="c1",
                token_id="t1", outcome="Yes", question="Will X?", published_ts=900.0, seen_ts=950.0,
                decided_ts=990.0, freshness="fresh", confidence=0.8, why="", event="Event A")
    args.update(kw)
    return b.fire(**args)


def test_entry_records_both_sides_and_the_mid(tmp_path, monkeypatch):
    b, st = _book(tmp_path, monkeypatch, ts=1000.0)
    row = _fire(b)
    assert row.ask_top == 0.42 and row.bid_top == 0.40 and row.mid_entry == pytest.approx(0.41)
    assert row.fresh_marks is True and row.event == "Event A"


def test_a_mark_on_an_old_book_is_unknown_and_a_current_one_is_a_price(tmp_path, monkeypatch):
    b, st = _book(tmp_path, monkeypatch, ts=1000.0)
    row = _fire(b)
    # 5m due; the only book is the one read at entry, 300 s old > 120 s
    st["now"] = 1300.0
    st["bid"] = [(0.55, 50)]
    assert b.mark() == 1
    m = row.marks["5m"]
    assert m["pnl"] is None and m["exit_price"] is None and m["age_s"] == pytest.approx(300.0)
    # 30m due with a book read 10 s ago: a price, its mid and its age recorded
    st["now"], st["ts"] = 2800.0, 2790.0
    st["ask"] = [(0.57, 50)]
    assert b.mark() == 1
    m = row.marks["30m"]
    assert m["exit_price"] == 0.55 and m["pnl"] is not None and m["mid"] == pytest.approx(0.56)
    assert m["age_s"] == pytest.approx(10.0)


def test_the_mark_budget_defers_rows_and_never_writes_unknown(tmp_path, monkeypatch):
    b, st = _book(tmp_path, monkeypatch, ts=1000.0)
    r1 = _fire(b, item_id="i1", token_id="t1", condition_id="c1")
    r2 = _fire(b, item_id="i2", token_id="t2", condition_id="c2")
    st["now"], st["ts"] = 1301.0, 1300.0
    budget = {"left": 1}
    assert b.mark(budget=budget) == 1 and budget["left"] == 0
    assert ("5m" in r1.marks) != ("5m" in r2.marks), "one row marked, the other still due"
    assert b.mark(budget={"left": 5}) == 1
    assert "5m" in r1.marks and "5m" in r2.marks


# ---- the runner: the stale-ladder bug, reproduced at the production seam ----

@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NEWS_STAKE_USD", "5")
    monkeypatch.setenv("NEWS_DOMAINS", "corp,geo")
    monkeypatch.setenv("NEWS_LLM_DAILY_BUDGET", "10")
    rest = {"lad": {}}
    monkeypatch.setattr(runner_mod.Runner, "_rest_book", lambda self, tok: rest["lad"].get(tok))
    import src.newsbot.fees as fr
    monkeypatch.setattr(fr, "fee_bps", lambda tok, now=None: 0)
    import src.telegram_bot as tb
    monkeypatch.setattr(tb, "send_message", lambda text, kind=None, **k: True)
    r = runner_mod.Runner(threading.Event())
    r.index = FakeIndex([_cand("m1", "c1", "Will Anthropic announce an IPO in 2026?", ["ta", "tb"])])
    # the entry book, YES 0.40/0.42 and NO 0.58/0.60, as the socket left it
    r.book.set_ladder("ta", clob_ws.parse_ladder({"bids": [{"price": "0.40", "size": "100"}],
                                                  "asks": [{"price": "0.42", "size": "100"}]}, ts_ms=1_650_000))
    r.book.set_ladder("tb", clob_ws.parse_ladder({"bids": [{"price": "0.58", "size": "100"}],
                                                  "asks": [{"price": "0.60", "size": "100"}]}, ts_ms=1_650_000))
    r.book.record("ta", 1_000_000, 0.40, 0.42)
    r.book.record("ta", 1_600_000, 0.40, 0.42)
    monkeypatch.setattr(judge_mod, "run_claude", _fake_claude())
    return r, rest


def _rest_ladder(bid, ask, ts_s):
    return clob_ws.parse_ladder({"bids": [{"price": str(bid), "size": "100"}],
                                 "asks": [{"price": str(ask), "size": "100"}]}, ts_ms=int(ts_s * 1000))


def test_an_llm_fire_books_the_inverse_side_at_its_own_ask(rig):
    r, rest = rig
    out = r.process_item(_item(), now=1700.0)
    assert out and out["fired"]
    inv = list(r.books["llm-inverse"].ledger.rows.values())
    assert len(inv) == 1 and inv[0].token_id == "tb" and inv[0].entry_price == 0.60 and inv[0].outcome == "No"
    llm = next(iter(r.books["llm"].ledger.rows.values()))
    assert llm.token_id == "ta" and llm.entry_price == 0.42


def test_marks_read_a_fresh_book_not_the_entry_snapshot(rig, monkeypatch):
    r, rest = rig
    r.process_item(_item(), now=1700.0)
    row = next(iter(r.books["llm"].ledger.rows.values()))
    # two hours on, the market moved to 0.50/0.52 and the REST book says so
    now = row.quote_ts + 7201
    rest["lad"]["ta"] = _rest_ladder(0.50, 0.52, now - 600)   # body stamp: last change 10 min ago
    r._rest_memo.clear()                      # two hours on: the entry's failed read is long forgotten
    monkeypatch.setattr(runner_mod.time, "time", lambda: now)
    r.mark_all(now=now)
    m = row.marks["2h"]
    assert m["exit_price"] == 0.50, "the bid of the book read now, not the 0.40 cached at entry"
    assert m["mid"] == pytest.approx(0.51) and m["age_s"] < 1.0, "a REST read is current as of the read, whatever its body stamp says"


def test_a_failed_rest_read_is_not_retried_inside_five_seconds(rig, monkeypatch):
    r, rest = rig
    calls = []
    monkeypatch.setattr(runner_mod.Runner, "_rest_book", lambda self, tok: calls.append(tok))
    r._ladder("ta")
    r._ladder("ta")
    assert calls == ["ta"], "REST down must not cost a GET per read in the 30 s loop"


def test_a_late_mark_is_not_that_horizons_exit(rig, monkeypatch):
    r, rest = rig
    r.process_item(_item(), now=1700.0)
    row = next(iter(r.books["llm"].ledger.rows.values()))
    now = row.quote_ts + 7200 + 3600          # the box was down for an hour past 2h
    rest["lad"]["ta"] = _rest_ladder(0.50, 0.52, now)
    r._rest_memo.clear()
    monkeypatch.setattr(runner_mod.time, "time", lambda: now)
    r.mark_all(now=now)
    assert row.marks["2h"]["pnl"] is None and row.marks["2h"]["late_s"] == pytest.approx(3600.0)


def test_with_no_fresh_book_a_mark_is_unknown_not_the_entry_bid(rig, monkeypatch):
    r, rest = rig
    r.process_item(_item(), now=1700.0)
    row = next(iter(r.books["llm"].ledger.rows.values()))
    now = row.quote_ts + 7201
    monkeypatch.setattr(runner_mod.time, "time", lambda: now)
    r.mark_all(now=now)                       # REST read fails: only the entry ladder exists
    assert row.marks["2h"]["pnl"] is None and row.marks["2h"]["exit_price"] is None


@pytest.mark.parametrize("frac,booked", [(0.05, 1), (0.04, 0)])
def test_tight_book_takes_only_tight_spreads(rig, frac, booked):
    """0.40/0.42 is 2c, 4.8% of the 0.42 ask: tight under a 5% bar, not under 4%."""
    r, rest = rig
    r.tight_cents, r.tight_frac = 2.0, frac
    r.process_item(_item(), now=1700.0)
    assert len(r.books["llm"].ledger.rows) == 1
    assert len(r.books["llm-tight"].ledger.rows) == booked


def test_a_wide_spread_in_cents_is_never_tight(rig):
    r, rest = rig
    r.tight_cents, r.tight_frac = 1.0, 0.5
    r.process_item(_item(), now=1700.0)
    assert len(r.books["llm"].ledger.rows) == 1 and len(r.books["llm-tight"].ledger.rows) == 0


def test_an_llm_fire_rests_a_maker_order_at_the_bid(rig):
    r, rest = rig
    r.process_item(_item(), now=1700.0)
    orders = list(r.maker.orders.values())
    assert len(orders) == 1 and orders[0].limit == 0.40 and orders[0].mid_post == pytest.approx(0.41)
    assert orders[0].event and orders[0].state == "resting"


# ---- the maker desk: the tape must come to us ----

@pytest.fixture
def desk(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NEWS_STAKE_USD", "5")
    monkeypatch.setenv("NEWS_MAKER_TTL_MIN", "30")
    st = {"bid": [(0.40, 50)], "ask": [(0.42, 50)], "now": 1000.0}
    b = paper.PaperBook("llm-maker", ask_ladder=lambda t: st["ask"], bid_ladder=lambda t: st["bid"],
                        fee_bps=lambda t: 500, now=lambda: st["now"])
    d = maker_mod.MakerDesk(b)
    common = dict(item_id="i1", source="s", domains=("geo",), market_id="m1", condition_id="c1",
                  token_id="t1", outcome="Yes", question="Will X?", published_ts=900.0, seen_ts=950.0,
                  decided_ts=990.0, freshness="fresh", confidence=0.8, why="")
    return d, b, st, common


def _check(d, now, *, hist=(), trade=None, quote=None, mid=None):
    return d.check(now, history=lambda t: list(hist), last_trade=lambda t: trade,
                   ladder=lambda t: quote, mid_now=lambda t: mid)


def test_touching_our_price_is_not_a_fill_trading_through_it_is(desk):
    d, b, st, common = desk
    o = d.post(common, bid=0.40, ask=0.42, now=1000.0, event="E")
    # the ask came down to 0.41 and a trade printed AT 0.40: we sit behind the queue
    _check(d, 1100.0, hist=[(1_050_000, 0.40, 0.41, 0.405)], trade=(1_060_000, 0.40), quote=(0.40, 0.41))
    assert o.state == "resting" and not b.ledger.rows
    # a trade below our limit: filled at our limit, maker fee zero, horizons from the fill
    _check(d, 1200.0, trade=(1_150_000, 0.39), quote=(0.39, 0.41))
    assert o.state == "filled" and o.fill_how == "trade<limit"
    row = next(iter(b.ledger.rows.values()))
    assert row.entry_price == 0.40 and row.fee_usd == 0.0 and row.quote_ts == 1150.0
    assert row.fee_bps == 500, "the exit still pays the taker fee"


def test_ask_down_to_our_limit_in_the_history_fills(desk):
    d, b, st, common = desk
    o = d.post(common, bid=0.40, ask=0.42, now=1000.0)
    _check(d, 1100.0, hist=[(900_000, 0.40, 0.40, 0.40), (1_080_000, 0.39, 0.40, 0.395)])
    assert o.state == "filled" and o.filled_ts == 1080.0, "the pre-post quote never counts"


def test_unfilled_orders_expire_once_and_keep_their_mid_marks(desk):
    d, b, st, common = desk
    o = d.post(common, bid=0.40, ask=0.42, now=1000.0)
    _check(d, 1000.0 + 1801, quote=(0.45, 0.47))
    assert o.state == "expired" and not b.ledger.rows
    _check(d, 1000.0 + 1900, trade=(1_000_000 + 1_850_000, 0.30), quote=(0.29, 0.31))
    assert o.state == "expired", "a trade after the ttl never fills an expired order"
    _check(d, 1000.0 + 7201, mid=0.50)
    _check(d, 1000.0 + 7300, mid=0.10)
    assert o.mid_marks["2h"] == 0.50, "written once"
    s = d.summary()
    assert s["filled"] == 0 and s["done"] == 1 and s["move_unfilled"][1] == 1
    assert s["move_unfilled"][0] == pytest.approx((0.50 - 0.41) / 0.40)
    again = maker_mod.MakerDesk(b)
    assert again.orders[o.order_id].state == "expired", "the ledger survives a restart"
    assert again.post(common, bid=0.40, ask=0.42, now=5000.0) is None, "one order per item and token"


def test_no_bid_or_out_of_band_posts_nothing(desk):
    d, b, st, common = desk
    assert d.post(common, bid=None, ask=0.42, now=1000.0) is None
    assert d.post({**common, "item_id": "i2"}, bid=0.97, ask=0.98, now=1000.0) is None
    assert d.skipped["no-bid"] == 1 and d.skipped["band"] == 1


# ---- the go-live bar ----

def _vrow(i, event, pnl_2h, *, fresh=True):
    return paper.PaperRow(row_id=f"r{i}", book="llm", item_id=f"i{i}", source="s", domains=("geo",),
                          market_id=f"m{i}", condition_id=f"c{i}", token_id=f"t{i}", outcome="Yes",
                          question="q", published_ts=0, seen_ts=0, decided_ts=0, quote_ts=0, freshness="fresh",
                          confidence=0, why="", ask_top=0.52, entry_price=0.52, stake=5.0, filled_usd=5.0,
                          fee_bps=0, fee_usd=0.0, shares=5 / 0.52,
                          marks={"2h": {"pnl": pnl_2h, "mid": 0.51 + pnl_2h / 50}},
                          bid_top=0.50, mid_entry=0.51, fresh_marks=fresh, event=event)


def test_six_markets_of_one_event_are_one_observation():
    rows = [_vrow(i, "Serbia turnout", -4.8) for i in range(6)] + [_vrow(9, "Other", 0.5)]
    st = verdict.book_stat(rows)
    assert st["events"] == 2 and st["rows"] == 7
    assert st["mean"] == pytest.approx((-0.96 + 0.10) / 2)


def test_bar_go_no_go_not_yet_both_ways():
    win = [_vrow(i, f"E{i}", 0.5 + (i % 3) * 0.1) for i in range(25)]
    assert verdict.verdict(win)["state"] == "GO"
    lose = [_vrow(i, f"E{i}", -0.25 + (i % 3) * 0.1) for i in range(25)]
    assert verdict.verdict(lose)["state"] == "NO-GO"
    noisy = [_vrow(i, f"E{i}", (1 if i % 2 else -1) * 1.0 + 0.05) for i in range(25)]
    assert verdict.verdict(noisy)["state"] == "NO-GO", "positive but inside 2 SE is not a GO"
    few = win[:24]
    v = verdict.verdict(few)
    assert v["state"] == "NOT-YET" and v["events"] == 24
    assert "NOT-YET (24 of 25 events)" in verdict.verdict_line("llm", few)
    stale = [_vrow(i, f"E{i}", 1.0, fresh=False) for i in range(30)]
    assert verdict.verdict(stale)["events"] == 0, "rows with replayed marks never count"


def test_split_separates_the_spread_from_the_signal():
    rows = [_vrow(i, f"E{i}", 0.0) for i in range(4)]
    sp = verdict.split(rows)
    assert sp["spread"]["mean"] == pytest.approx(0.02 / 0.52)
    assert sp["signal"]["mean"] == pytest.approx(0.0, abs=1e-9)


def test_pnl_shows_the_bar_and_names_the_stale_week(tmp_path):
    led = {b: paper.PaperLedger(b, path=str(tmp_path / f"{b}.jsonl")) for b in paper.BOOKS}
    for i in range(3):
        led["llm"].add(_vrow(i, f"E{i}", -0.2))
    old = _vrow(7, "E7", -0.25, fresh=False)
    led["llm"].add(old)
    t = pnl.pnl_text(led, now=10_000.0, maker_line="llm-maker orders: 0 posted, none finished yet (collecting)")
    assert "Go-live bar" in t and "NOT-YET (3 of 25 events)" in t
    assert "llm-inverse: NOT-YET (0 of 25 events, collecting)" in t
    assert "spread paid 3.8% of the price (3 events)" in t
    assert "Before 2026-11-01: 1 llm bets" in t and "3 bets" in t
    assert "llm-maker orders: 0 posted" in t


def _drow(i, dom, event, mid2h):
    r = _vrow(i, event, 0.0)
    r.domains = (dom,)
    r.marks["2h"]["mid"] = mid2h
    return r


def test_break_even_map_names_a_real_edge_and_calls_small_groups_too_few():
    # geo: 25 events whose mid rose 10c on a 0.52 entry (+19%), spread 3.8%: clears
    rows = [_drow(i, "geo", f"G{i}", 0.61 + (i % 3) * 0.001) for i in range(25)]
    # corp: 3 events with the same big move: still too few to say anything
    rows += [_drow(100 + i, "corp", f"C{i}", 0.61) for i in range(3)]
    # politics: 25 events with no move: does not clear the spread
    rows += [_drow(200 + i, "politics", f"P{i}", 0.51 + (0.001 if i % 2 else -0.001)) for i in range(25)]
    lines = {ln.split(":")[0]: ln for ln in verdict.domain_lines(rows)}
    assert "clears the spread" in lines["geo"] and "25 events" in lines["geo"]
    assert "too few" in lines["corp"] and "3 events" in lines["corp"]
    assert "does not clear" in lines["politics"]


def test_a_failed_rest_read_never_books_an_entry_from_an_old_book(rig, monkeypatch):
    """Verifier round 1 (s-wj4gnb): REST down + a two-day-old cached ladder
    booked a BUY at the old ask. Driven through Runner._ladder, not lists."""
    r, rest = rig
    old = clob_ws.parse_ladder({"bids": [{"price": "0.18", "size": "100"}],
                                "asks": [{"price": "0.20", "size": "100"}]}, ts_ms=1_000)
    r.book.set_ladder("ta", old)
    r.book.set_ladder("tb", old)
    from src.newsbot.items import Item

    def fresh_item(i, t):   # published a minute before: inside the 30 min item age
        return Item(id=i, source="bsky:reuters.com", domains=("corp",), published_ts=t - 60, seen_ts=t - 50,
                    title="Anthropic to announce IPO, Dario says", text="", url="https://x")
    out = r.process_item(fresh_item("bsky:reuters.com:1", 200_000.0), now=200_000.0)
    assert out is not None, "the item reached the judge; the books refused the old ladder"
    assert not r.books["llm"].ledger.rows and not r.books["headline-any"].ledger.rows
    assert not r.maker.orders and not r.books["llm-inverse"].ledger.rows
    # the same item with a current REST book books at that book's ask
    rest["lad"]["ta"] = _rest_ladder(0.58, 0.60, 204_000.0)
    r._rest_memo.clear()
    r.judged_recent.clear()
    r.process_item(fresh_item("bsky:reuters.com:2", 204_000.0), now=204_000.0)   # next hour: the hourly LLM cap is 1 here
    rows = list(r.books["headline-any"].ledger.rows.values())
    assert rows and rows[0].entry_price == 0.60
