"""Real-money accounting: the /real surface and the module behind it.

The one thing these tests exist to protect: **paper must never be counted as
real money, and one real order must never be counted twice.** Everything else
here is arithmetic around those two invariants.
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
# Realized rows — what settled, and what may not be claimed as real
# ------------------------------------------------------------------

def test_redeemer_rows_are_real_preview_rows_are_not():
    rows = [
        {"source": "redeemer", "token_id": "tok-x", "pnl": 3.0, "cost_basis": 5.0,
         "returned": 8.0, "won": True},
        {"source": "preview", "token_id": "tok-1", "pnl": -5.0, "cost_basis": 5.0,
         "returned": 0.0, "won": False},
    ]
    real, other = rm.split_realized(rows, {"tok-1"})
    assert [r["source"] for r in real] == ["redeemer"]
    assert [r["source"] for r in other] == ["preview"]


def test_a_preview_row_on_a_real_token_is_still_paper():
    """The fill model books paper exits on tokens real money also touched;
    counting them would credit the real book with a simulated result."""
    rows = [{"source": "preview", "token_id": "tok-1", "pnl": 9.0}]
    real, other = rm.split_realized(rows, {"tok-1"})
    assert real == [] and len(other) == 1


def test_unsourced_row_is_real_only_when_a_real_order_bought_that_token():
    rows = [
        {"token_id": "tok-1", "pnl": 1.0, "cost_basis": 4.0},   # real order's token
        {"token_id": "tok-legacy", "pnl": -575.0},              # pre-schema debris
    ]
    real, other = rm.split_realized(rows, {"tok-1"})
    assert len(real) == 1 and real[0]["token_id"] == "tok-1"
    assert len(other) == 1


def test_summarize_realized_counts_record_and_roi():
    st = rm.summarize_realized([
        {"pnl": 3.0, "cost_basis": 5.0, "returned": 8.0, "won": True},
        {"pnl": -5.0, "cost_basis": 5.0, "returned": 0.0, "won": False},
    ])
    assert st.n_rows == 2 and st.wins == 1 and st.losses == 1
    assert st.pnl == pytest.approx(-2.0)
    assert st.returned_usd == pytest.approx(8.0)
    assert st.roi == pytest.approx(-0.2)


def test_realized_roi_is_none_without_settled_cost():
    assert rm.summarize_realized([]).roi is None


# ------------------------------------------------------------------
# Breakdowns
# ------------------------------------------------------------------

def test_by_day_groups_orders_and_realized():
    orders = rm.collapse_orders([
        _row(status="FILLED", order_id="a", timestamp="2026-09-10T01:00:00+00:00",
             fill_price=0.5, fill_shares=16.0),
        _row(status="FILLED", order_id="b", timestamp="2026-09-11T01:00:00+00:00",
             fill_price=0.5, fill_shares=16.0),
    ])
    days = rm.by_day(orders, [{"timestamp": "2026-09-11T05:00:00+00:00", "pnl": 2.0}])
    assert [d.date for d in days] == ["2026-09-11", "2026-09-10"]   # newest first
    assert days[0].realized_pnl == pytest.approx(2.0)
    assert days[1].filled_usd == pytest.approx(8.0)


def test_by_wallet_ranks_by_money_and_attributes_settled_pnl():
    w1 = "0x" + "1" * 40
    w2 = "0x" + "2" * 40
    orders = rm.collapse_orders([
        _row(status="FILLED", order_id="a", trader_address=w1, token_id="t1",
             fill_price=0.5, fill_shares=40.0),
        _row(status="FILLED", order_id="b", trader_address=w2, token_id="t2",
             fill_price=0.5, fill_shares=10.0),
    ])
    lines = rm.by_wallet(orders, [
        {"trader_address": w1, "token_id": "t1", "pnl": 4.0, "won": True},
        {"token_id": "t2", "pnl": -5.0, "won": False},   # unattributed -> by token
    ])
    assert lines[0].wallet == w1 and lines[0].filled_usd == pytest.approx(20.0)
    assert lines[0].realized_pnl == pytest.approx(4.0) and lines[0].wins == 1
    assert lines[1].wallet == w2 and lines[1].realized_pnl == pytest.approx(-5.0)


def test_test_orders_get_their_own_bucket():
    orders = rm.collapse_orders([
        _row(status="FILLED", order_id="t", trader_address="", source="testorder",
             fill_price=0.98, fill_shares=5.0),
    ])
    lines = rm.by_wallet(orders, [])
    assert lines[0].wallet == rm.TEST_ORDER_WALLET


def test_not_spent_counts_the_disarmed_skips():
    ns = rm.summarize_not_spent([
        _row(status="DISARMED", copy_size=8.0),
        _row(status="DISARMED", copy_size=4.0),
        _row(status="PREVIEW", copy_size=25.0),
        _row(status="FILLED", order_id="x"),
    ])
    assert ns.n_disarmed == 2 and ns.disarmed_usd == pytest.approx(12.0)
    assert ns.n_preview == 1 and ns.preview_usd == pytest.approx(25.0)


# ------------------------------------------------------------------
# Chain positions
# ------------------------------------------------------------------

def test_chain_positions_fold_cost_value_and_collectable():
    st = rm.summarize_chain_positions([
        {"size": 20.0, "avgPrice": 0.5, "initialValue": 10.0, "currentValue": 12.0},
        {"size": 10.0, "avgPrice": 0.4, "curPrice": 1.0, "redeemable": True},
        {"size": 0.0, "avgPrice": 0.9},          # dust/closed: ignored
        "not a row",
    ])
    assert st.n_positions == 2
    assert st.cost_usd == pytest.approx(14.0)     # 10 + 10*0.4
    assert st.value_usd == pytest.approx(22.0)    # 12 + 10*1.0
    assert st.unrealized == pytest.approx(8.0)
    assert st.n_redeemable == 1 and st.redeemable_usd == pytest.approx(10.0)


def test_chain_read_failure_is_none_not_zero(monkeypatch):
    """A failed read must not render as a confident $0 — the exact mistake
    that left the bankroll floor unable to fire."""
    import requests

    def boom(*a, **kw):
        raise requests.RequestException("no network")

    monkeypatch.setattr(requests, "get", boom)
    assert rm.fetch_chain_positions("0xabc") is None
    assert rm.fetch_chain_positions("") is None


# ------------------------------------------------------------------
# The whole report
# ------------------------------------------------------------------

def test_build_report_end_to_end():
    history = [
        _row(status="PREVIEW", copy_size=25.0),                     # paper
        _row(status="DISARMED", copy_size=8.0),                     # refused
        _row(status="PLACED", order_id="ord-1", token_id="t1"),
        _row(status="FILLED", order_id="ord-1", token_id="t1",
             fill_price=0.5, fill_shares=16.0),
        _row(status="PLACED", order_id="ord-2", token_id="t2", copy_size=6.0),
        _row(status="UNFILLED", order_id="ord-2", token_id="t2", copy_size=6.0,
             fill_shares=0.0),
    ]
    realized = [
        {"source": "redeemer", "token_id": "t1", "pnl": 2.0, "cost_basis": 8.0,
         "returned": 10.0, "won": True, "timestamp": "2026-09-12T00:00:00+00:00"},
        {"source": "preview", "token_id": "t9", "pnl": 99.0, "cost_basis": 50.0},
    ]
    chain = [{"size": 12.0, "avgPrice": 0.5, "currentValue": 7.0}]

    rep = rm.build_report(history, realized, chain_rows=chain)
    assert rep.has_real_activity
    assert rep.stats.n_orders == 2
    assert rep.stats.filled_usd == pytest.approx(8.0)
    assert rep.stats.returned_usd == pytest.approx(6.0)
    assert rep.realized.pnl == pytest.approx(2.0)        # the paper +99 is excluded
    assert rep.n_unattributed_realized == 1
    assert rep.not_spent.n_disarmed == 1 and rep.not_spent.n_preview == 1
    assert rep.chain is not None and rep.chain.cost_usd == pytest.approx(6.0)
    assert rep.at_work_usd == pytest.approx(6.0)         # the chain's word


def test_build_report_without_a_chain_read_falls_back_to_the_ledger():
    history = [_row(status="FILLED", order_id="a", token_id="t1",
                    fill_price=0.5, fill_shares=16.0)]
    rep = rm.build_report(history, [], chain_rows=None)
    assert rep.chain is None
    assert rep.at_work_usd == pytest.approx(8.0)   # filled, nothing settled yet


def test_empty_everything_is_a_quiet_report():
    rep = rm.build_report([], [])
    assert not rep.has_real_activity
    assert rep.stats.n_orders == 0 and rep.realized.pnl == 0.0
