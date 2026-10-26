"""/pnl: the experiment's money, every number with its n."""

import time

from src.newsbot import paper, pnl


def _row(led, rid, *, cond, decided, mark2h=None, res=None, void="", book="llm"):
    r = paper.PaperRow(row_id=rid, book=book, item_id=rid, source="tg:x", domains=("geo",), market_id="m",
                       condition_id=cond, token_id="t" + rid, outcome="Yes", question=f"Will {rid} happen?",
                       published_ts=decided - 60, seen_ts=decided - 30, decided_ts=decided, quote_ts=decided,
                       freshness="fresh", confidence=0.5, why="", ask_top=0.5, entry_price=0.5, stake=5.0,
                       filled_usd=5.0, fee_bps=0, fee_usd=0.0, shares=10.0,
                       marks={"2h": {"pnl": mark2h}} if mark2h is not None else {}, void=void)
    if res is not None:
        r.resolution_pnl, r.resolved, r.closed = res, res > 0, True
    led.add(r)


def test_pnl_report_money_with_n_controls_and_void(tmp_path):
    now = time.mktime((2026, 10, 27, 12, 0, 0, 0, 0, 0)) - time.timezone
    led = {b: paper.PaperLedger(b, path=str(tmp_path / f"{b}.jsonl")) for b in paper.BOOKS}
    _row(led["llm"], "a", cond="c1", decided=now - 20000, mark2h=1.5, res=5.0)
    _row(led["llm"], "b", cond="c2", decided=now - 3600, mark2h=-0.5)
    _row(led["llm"], "d", cond="c3", decided=now - 3000, mark2h=-4.0, void="duplicate")
    _row(led["random"], "r", cond="c9", decided=now - 3600, mark2h=-1.0, book="random")
    t = pnl.pnl_text(led, now=now)
    assert "2 bets" in t and "1 resolved" in t
    assert "+$1.00 (+10.0%, n=2)" in t, "2h: +1.5 - 0.5 on $10, void row left out"
    assert "held +$5.00 (1 won of 1)" in t
    assert "5m   collecting (n=0)" in t, "an empty horizon is never $0"
    assert "random       -$1.00" in t and "headline-any collecting (n=0)" in t
    assert "1 duplicate row(s) voided" in t
    assert "SGT" in t and "UTC" not in t


def test_open_bets_marked_at_the_bid_now(tmp_path):
    now = time.time()
    led = {b: paper.PaperLedger(b, path=str(tmp_path / f"{b}.jsonl")) for b in paper.BOOKS}
    _row(led["llm"], "a", cond="c1", decided=now - 600)
    t = pnl.pnl_text(led, now=now, bid_now=lambda tok: 0.6)
    assert "Open bets if sold at the bid now: +$1.00 (n=1)" in t
    short = pnl.pnl_text(led, now=now, short=True)
    assert "/pnl for the rest" in short and "Against the controls" not in short
