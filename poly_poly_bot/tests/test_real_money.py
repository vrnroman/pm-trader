"""Real-money accounting: the /real surface and the module behind it.

What these tests exist to protect: **paper must never be counted as real
money, one real order must never be counted twice, and a win Polymarket paid
out is a win even when the bot's own ledger never heard of it.** Everything
else here is arithmetic around those invariants.
"""

from __future__ import annotations

import pytest

from src.copy_trading import real_money as rm


def _row(**kw) -> dict:
    base = {
        "timestamp": "2026-09-10T12:00:00+00:00",
        "trader_address": "0xaaaa000000000000000000000000000000000001",
        "market": "Will X happen?",
        "side": "BUY",
        "copy_size": 8.0,
        "price": 0.5,
        "status": "PLACED",
        "token_id": "tok-1",
    }
    base.update(kw)
    return base


# ------------------------------------------------------------------
# Classification — the paper/real boundary
# ------------------------------------------------------------------

@pytest.mark.parametrize("status,kind", [
    ("PLACED", "real"), ("FILLED", "real"), ("PARTIAL", "real"),
    ("UNFILLED", "real"), ("ABANDONED", "real"),
    ("PREVIEW", "paper"),
    ("DISARMED", "not-placed"), ("SKIPPED", "not-placed"), ("ALERT_ONLY", "not-placed"),
    ("", "unknown"), ("WAT", "unknown"),
])
def test_classify_row(status, kind):
    assert rm.classify_row(_row(status=status)) == kind


def test_preview_and_disarmed_rows_never_become_orders():
    rows = [_row(status="PREVIEW"), _row(status="DISARMED"),
            _row(status="SKIPPED"), _row(status="ALERT_ONLY")]
    assert rm.collapse_orders(rows) == []
    st = rm.summarize_orders(rm.collapse_orders(rows))
    assert st.posted_usd == 0.0 and st.filled_usd == 0.0


# ------------------------------------------------------------------
# Collapsing — one order, however many rows it wrote
# ------------------------------------------------------------------

def test_placed_then_filled_is_one_order_counted_once():
    rows = [
        _row(status="PLACED", order_id="ord-1"),
        _row(status="FILLED", order_id="ord-1", fill_price=0.5, fill_shares=16.0),
    ]
    orders = rm.collapse_orders(rows)
    assert len(orders) == 1
    o = orders[0]
    assert o.status == "FILLED"
    assert o.posted_usd == 8.0
    assert o.filled_usd == pytest.approx(8.0)
    st = rm.summarize_orders(orders)
    assert st.n_orders == 1 and st.n_filled == 1
    assert st.filled_usd == pytest.approx(8.0)


def test_a_late_fill_supersedes_an_earlier_unfilled():
    """The cancel that failed because the order had just matched."""
    rows = [
        _row(status="PLACED", order_id="ord-1"),
        _row(status="UNFILLED", order_id="ord-1", fill_shares=0.0),
        _row(status="FILLED", order_id="ord-1", fill_price=0.5, fill_shares=16.0),
    ]
    o = rm.collapse_orders(rows)[0]
    assert o.status == "FILLED"
    assert o.filled_usd == pytest.approx(8.0)


def test_unfilled_order_returns_its_money():
    rows = [
        _row(status="PLACED", order_id="ord-1"),
        _row(status="UNFILLED", order_id="ord-1", fill_shares=0.0),
    ]
    orders = rm.collapse_orders(rows)
    st = rm.summarize_orders(orders)
    assert orders[0].filled_usd == 0.0
    assert st.n_unfilled == 1
    assert st.returned_usd == pytest.approx(8.0)
    assert st.filled_usd == 0.0


def test_partially_filled_then_cancelled_counts_only_what_filled():
    rows = [
        _row(status="PLACED", order_id="ord-1", copy_size=10.0, price=0.5),
        _row(status="UNFILLED", order_id="ord-1", fill_shares=8.0),
    ]
    o = rm.collapse_orders(rows)[0]
    # 8 shares accounted at the copied price, the rest came back.
    assert o.filled_usd == pytest.approx(4.0)
    assert o.unfilled_usd == pytest.approx(6.0)


def test_a_posted_order_with_no_verdict_is_pending_not_filled():
    orders = rm.collapse_orders([_row(status="PLACED", order_id="ord-9")])
    st = rm.summarize_orders(orders)
    assert orders[0].pending and not orders[0].settled
    assert st.n_pending == 1 and st.pending_usd == pytest.approx(8.0)
    assert st.n_filled == 0


def test_sell_fills_are_proceeds_not_deployment():
    rows = [
        _row(status="FILLED", order_id="b", fill_price=0.5, fill_shares=16.0),
        _row(status="FILLED", order_id="s", side="SELL", fill_price=0.6,
             fill_shares=16.0),
    ]
    st = rm.summarize_orders(rm.collapse_orders(rows))
    assert st.filled_usd == pytest.approx(8.0)      # only the buy left the wallet
    assert st.sell_proceeds_usd == pytest.approx(9.6)
    assert st.n_buy == 1 and st.n_sell == 1


def test_window_excludes_older_days():
    rows = [
        _row(status="FILLED", order_id="old", timestamp="2026-08-01T00:00:00+00:00",
             fill_price=0.5, fill_shares=16.0),
        _row(status="FILLED", order_id="new", timestamp="2026-09-10T00:00:00+00:00",
             fill_price=0.5, fill_shares=16.0),
    ]
    orders = rm.collapse_orders(rows, since_day="2026-09-01")
    assert [o.order_id for o in orders] == ["new"]




# ------------------------------------------------------------------
# Polymarket's rows — the fixture is the shape of 2026-09-06..15
# ------------------------------------------------------------------

LIVE = rm.iso_epoch("2026-09-06T12:00:00+00:00")
H = 3600
W_A = "0x" + "a" * 40
W_B = "0x" + "b" * 40


def _trade(ts, side, cid, usdc, *, size=10.0, price=0.5, asset=None, title=None,
           outcome="Yes"):
    return {"timestamp": ts, "type": "TRADE", "side": side, "conditionId": cid,
            "asset": asset or f"tok-{cid}", "usdcSize": usdc, "size": size,
            "price": price, "title": title or f"Market {cid}", "outcome": outcome}


def _redeem(ts, cid, usdc, *, size=None):
    return {"timestamp": ts, "type": "REDEEM", "side": "", "conditionId": cid,
            "asset": "", "usdcSize": usdc, "size": usdc if size is None else size,
            "price": 0, "title": f"Market {cid}", "outcome": "Yes"}


def _pos(cid, size, avg, cur, *, resolved, initial=None, current=None):
    row = {"conditionId": cid, "size": size, "avgPrice": avg, "curPrice": cur,
           "redeemable": resolved, "title": f"Market {cid}", "outcome": "Yes",
           "endDate": "2026-09-15"}
    row["initialValue"] = size * avg if initial is None else initial
    row["currentValue"] = size * cur if current is None else current
    return row


def _order(ts_epoch, token, side="BUY", wallet=W_A, oid=None, source=""):
    from datetime import datetime, timezone
    iso = datetime.fromtimestamp(ts_epoch, timezone.utc).isoformat()
    return _row(status="FILLED", order_id=oid or f"o-{token}-{side}-{ts_epoch}",
                timestamp=iso, token_id=token, side=side, trader_address=wallet,
                source=source, fill_price=0.5, fill_shares=10.0)


def _scenario():
    """won-and-paid-out (w), lost (l), sold-then-resolved dust (s), still
    trading (o), plus a pre-live leftover (old) and a pre-live payout."""
    activity = [
        _redeem(LIVE - 5 * H, "old", 0.33),                           # before live
        _trade(LIVE + 1 * H, "BUY", "w", 6.58, size=14.88, price=0.43),
        _redeem(LIVE + 4 * H, "w", 14.88),                            # the missed win
        _trade(LIVE + 5 * H, "BUY", "l", 6.56, size=12.8, price=0.50),
        _trade(LIVE + 6 * H, "BUY", "s", 6.46, size=7.9, price=0.81),
        _trade(LIVE + 7 * H, "SELL", "s", 6.36, size=7.27, price=0.88),
        _trade(LIVE + 8 * H, "BUY", "o", 5.00, size=10.0, price=0.50),
        {"timestamp": LIVE + 9 * H, "type": "REWARD", "usdcSize": 1.0},
    ]
    positions = [
        _pos("l", 12.8, 0.5, 0.0, resolved=True),
        _pos("s", 0.63, 0.81, 1.0, resolved=True),
        _pos("o", 10.0, 0.5, 0.62, resolved=False),
        _pos("old", 970.0, 0.26, 0.0, resolved=True),
        _pos("zero", 0.0, 0.5, 0.5, resolved=False),                 # empty: dropped
    ]
    orders = rm.collapse_orders([
        _order(LIVE, "tok-first-test", wallet="", source="testorder"),
        _order(LIVE + 1 * H - 20, "tok-w"),
        _order(LIVE + 5 * H - 20, "tok-l"),
        _order(LIVE + 6 * H - 400, "tok-s", wallet=W_B),               # resting order
        _order(LIVE + 7 * H - 30, "tok-s", side="SELL", wallet=W_B),
        _order(LIVE + 8 * H - 20, "tok-o", wallet=W_B),
    ])
    return activity, positions, orders


def test_parse_deals_signs_cash_and_counts_what_it_does_not_understand():
    activity, _, _ = _scenario()
    deals, other = rm.parse_deals(activity, since_ts=LIVE)
    assert [d.kind for d in deals][:2] == ["BUY", "SELL"]        # newest first
    by_kind = {(d.kind, d.condition_id): d.usd for d in deals}
    assert by_kind[("BUY", "w")] == pytest.approx(-6.58)
    assert by_kind[("SELL", "s")] == pytest.approx(6.36)
    assert by_kind[("PAYOUT", "w")] == pytest.approx(14.88)
    assert ("PAYOUT", "old") not in by_kind                      # before live
    assert other == 1                                            # the reward row


def test_parse_deals_skips_rows_without_a_timestamp():
    deals, other = rm.parse_deals([{"type": "TRADE", "side": "BUY"}, "junk", None])
    assert deals == [] and other == 0


def test_parse_positions_marks_state_and_drops_empty_holdings():
    _, positions, _ = _scenario()
    ps = {p.condition_id: p for p in rm.parse_positions(positions)}
    assert "zero" not in ps
    assert ps["o"].state == "open"
    assert ps["o"].pnl == pytest.approx(1.2)
    assert ps["o"].pnl_pct == pytest.approx(0.24)
    assert ps["s"].state == "collect" and ps["s"].value_usd == pytest.approx(0.63)
    assert ps["l"].state == "spent"


def test_parse_positions_falls_back_to_size_times_price():
    [p] = rm.parse_positions([{"conditionId": "c", "size": 10.0, "avgPrice": 0.4,
                               "curPrice": 0.7}])
    assert p.cost_usd == pytest.approx(4.0) and p.value_usd == pytest.approx(7.0)
    assert p.state == "open"


def test_a_winner_paid_out_on_chain_is_a_win():
    """The 2026-09-16 bug: a winner that paid out has no position row and no
    redeemer ledger row, so every such market was invisible and /real read
    0W/8L. Polymarket's payout row is the win."""
    activity, positions, orders = _scenario()
    book = rm.build_book(activity, positions, orders)
    w = book.result_for["w"]
    assert w.state == "won"
    assert w.pnl == pytest.approx(14.88 - 6.58)


def test_book_results_from_polymarket_rows():
    activity, positions, orders = _scenario()
    book = rm.build_book(activity, positions, orders)
    r = book.result_for
    assert r["l"].state == "lost" and r["l"].pnl == pytest.approx(-6.56)
    # Sold most of it, the rest resolved a winner and waits to be collected.
    assert r["s"].state == "won"
    assert r["s"].pnl == pytest.approx(6.36 + 0.63 - 6.46)
    assert r["o"].state == "open" and r["o"].held_usd == pytest.approx(6.2)
    assert "old" not in r                         # a pre-live market is no result
    assert (book.wins, book.losses, book.n_open) == (2, 1, 1)
    assert book.paid_usd == pytest.approx(6.58 + 6.56 + 6.46 + 5.00)
    assert book.sold_usd == pytest.approx(6.36)
    assert book.paid_out_usd == pytest.approx(14.88)
    assert book.held_usd == pytest.approx(0.63 + 6.2)
    assert book.net_usd == pytest.approx(
        6.36 + 14.88 + 0.63 + 6.2 - (6.58 + 6.56 + 6.46 + 5.00))
    assert book.n_other_rows == 1


def test_book_balance_views():
    activity, positions, orders = _scenario()
    book = rm.build_book(activity, positions, orders)
    assert [p.condition_id for p in book.open_positions] == ["o"]
    assert [p.condition_id for p in book.to_collect] == ["s"]
    assert book.value_usd == pytest.approx(0.63 + 6.2)
    # The live loser is a result; only the pre-live leftover is set aside.
    assert [p.condition_id for p in book.spent_before_live] == ["old"]


def test_live_start_is_the_first_real_order():
    _, _, orders = _scenario()
    assert rm.live_start_ts(orders) == LIVE
    assert rm.live_start_ts([]) is None
    book = rm.build_book([], [], [])
    assert book.live_ts is None and book.markets == []


def test_deals_carry_the_followed_wallet_they_copied():
    activity, positions, orders = _scenario()
    book = rm.build_book(activity, positions, orders)
    wallets = {(d.kind, d.condition_id): d.wallet for d in book.deals}
    assert wallets[("BUY", "w")] == W_A
    assert wallets[("BUY", "s")] == W_B          # matched across a resting order's delay
    assert wallets[("SELL", "s")] == W_B
    assert wallets[("PAYOUT", "w")] == ""        # no order behind a payout...
    assert book.result_for["w"].wallet == W_A    # ...its market carries the wallet


def test_attribution_needs_the_same_token_side_and_a_close_time():
    deals, _ = rm.parse_deals([_trade(LIVE + 10 * H, "BUY", "x", 5.0)])
    rm.attribute_wallets(deals, rm.collapse_orders([
        _order(LIVE + 10 * H, "tok-x", side="SELL"),          # wrong side
        _order(LIVE + 10 * H, "tok-y"),                       # wrong token
        _order(LIVE + 10 * H - 2 * H, "tok-x"),               # too far
    ]))
    assert deals[0].wallet == ""


def test_test_orders_are_their_own_wallet():
    deals, _ = rm.parse_deals([_trade(LIVE + 60, "BUY", "t", 4.99,
                                      asset="tok-first-test")])
    rm.attribute_wallets(deals, rm.collapse_orders([
        _order(LIVE, "tok-first-test", wallet="", source="testorder")]))
    assert deals[0].wallet == rm.TEST_ORDER_WALLET


def test_a_bought_market_polymarket_has_not_caught_up_with_is_open_not_lost():
    orders = rm.collapse_orders([_order(LIVE, "tok-n")])
    book = rm.build_book([_trade(LIVE + 30, "BUY", "n", 5.0)], [], orders)
    m = book.result_for["n"]
    assert m.state == "open" and m.unseen
    assert m.pnl == pytest.approx(0.0)           # counted at cost
    assert book.n_unseen == 1 and book.losses == 0


def test_window_keeps_markets_first_bought_inside_it():
    activity, positions, orders = _scenario()
    since = LIVE + 5 * H - 60        # after w was bought, before its payout's peers
    book = rm.build_book(activity, positions, orders, since_ts=since)
    assert sorted(m.condition_id for m in book.markets) == ["l", "o", "s"]
    # w's payout sits outside this window's markets: never a free win.
    assert book.paid_out_usd == 0.0
    assert all(d.ts >= since for d in book.deals)
    # The pre-live split does not move with the window.
    assert [p.condition_id for p in book.spent_before_live] == ["old"]


def test_unreadable_holdings_stay_unknown():
    activity, _, orders = _scenario()
    book = rm.build_book(activity, None, orders)
    assert book.positions is None
    assert book.open_positions == [] and book.value_usd == 0.0


def test_by_wallet_counts_settled_results_only():
    activity, positions, orders = _scenario()
    rows = {w.wallet: w for w in rm.by_wallet(rm.build_book(activity, positions,
                                                            orders).markets)}
    a, b = rows[W_A], rows[W_B]
    assert (a.n_markets, a.wins, a.losses, a.n_open) == (2, 1, 1, 0)
    assert a.pnl == pytest.approx(14.88 - 6.58 - 6.56)
    assert (b.n_markets, b.wins, b.losses, b.n_open) == (2, 1, 0, 1)
    assert b.pnl == pytest.approx(6.36 + 0.63 - 6.46)   # the open market is not in it


# ------------------------------------------------------------------
# The network edge
# ------------------------------------------------------------------

class _Resp:
    def __init__(self, data, ok=True):
        self._data, self.ok = data, ok

    def json(self):
        return self._data


def test_chain_read_failure_is_none_not_zero(monkeypatch):
    """A failed read must not render as a confident $0 — the exact mistake
    that left the bankroll floor unable to fire."""
    import requests

    def boom(*a, **kw):
        raise requests.RequestException("no network")

    monkeypatch.setattr(requests, "get", boom)
    assert rm.fetch_chain_positions("0xabc") is None
    assert rm.fetch_activity("0xabc") is None
    assert rm.fetch_chain_positions("") is None
    assert rm.fetch_activity("") is None


def test_fetch_reads_every_page_and_asks_for_dust(monkeypatch):
    import requests

    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, dict(params)))
        full = [{"i": n} for n in range(rm._PAGE)]
        return _Resp(full if params["offset"] == 0 else [{"i": "last"}])

    monkeypatch.setattr(requests, "get", fake_get)
    rows = rm.fetch_chain_positions("0xabc")
    assert len(rows) == rm._PAGE + 1
    assert [c[1]["offset"] for c in calls] == [0, rm._PAGE]
    assert calls[0][0].endswith("/positions")
    assert calls[0][1]["sizeThreshold"] == 0       # a sub-share winner still shows

    calls.clear()
    rm.fetch_activity("0xabc", since_ts=LIVE)
    assert calls[0][0].endswith("/activity") and calls[0][1]["start"] == LIVE


def test_a_failed_later_page_fails_the_whole_read(monkeypatch):
    import requests

    def fake_get(url, params=None, timeout=None):
        if params["offset"] == 0:
            return _Resp([{"i": n} for n in range(rm._PAGE)])
        return _Resp(None, ok=False)

    monkeypatch.setattr(requests, "get", fake_get)
    assert rm.fetch_activity("0xabc") is None


def test_a_read_longer_than_the_page_cap_is_refused(monkeypatch):
    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **kw: _Resp(
        [{"i": n} for n in range(rm._PAGE)]))
    assert rm.fetch_activity("0xabc") is None
