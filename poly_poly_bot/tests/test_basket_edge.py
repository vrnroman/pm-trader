"""Tests for depth-aware basket-arbitrage edge math (Strategy 3)."""

from __future__ import annotations

from src.basket_arb.edge import basket_buy_edge, top_of_book_sum


def test_no_edge_when_basket_costs_more_than_one():
    # two complementary outcomes, asks sum to 1.02 -> no arb
    legs = [[(0.52, 100)], [(0.50, 100)]]
    e = basket_buy_edge(legs)
    assert e.profit <= 0
    assert abs(top_of_book_sum(legs) - 1.02) < 1e-9


def test_simple_two_leg_arb():
    # buy 1 of each for 0.48+0.50 = 0.98, guaranteed payout 1.0 -> +0.02/basket
    legs = [[(0.48, 100)], [(0.50, 100)]]
    e = basket_buy_edge(legs)
    assert e.feasible
    assert abs(e.best_size - 100) < 1e-9          # min depth across legs
    assert abs(e.cost - 98.0) < 1e-9
    assert abs(e.profit - 2.0) < 1e-9             # 100 payout - 98 cost
    assert abs(e.roi - (2.0 / 98.0)) < 1e-6


def test_depth_limited_by_thinnest_leg():
    # leg A deep, leg B only 10 shares -> basket size capped at 10
    legs = [[(0.40, 1000)], [(0.50, 10)]]
    e = basket_buy_edge(legs)
    assert abs(e.best_size - 10) < 1e-9
    assert abs(e.cost - (0.40 * 10 + 0.50 * 10)) < 1e-9
    assert abs(e.profit - (10 - 9.0)) < 1e-9


def test_walks_book_optimum_at_breakpoint():
    # leg A: 5 @0.30 then 100 @0.55 ; leg B: 100 @0.40
    # at q=5: cost = 5*0.30 + 5*0.40 = 3.5, payout 5 -> profit 1.5
    # at q=100: cost = (5*0.30+95*0.55) + 100*0.40 = (1.5+52.25)+40=93.75,
    #           payout 100 -> profit 6.25  (deeper is better here)
    legs = [[(0.30, 5), (0.55, 100)], [(0.40, 100)]]
    e = basket_buy_edge(legs)
    assert abs(e.best_size - 100) < 1e-9
    assert abs(e.profit - 6.25) < 1e-6


def test_optimum_stops_before_unprofitable_depth():
    # leg A cheap-then-expensive; going deep destroys the edge
    # leg A: 10 @0.30 then 1000 @0.80 ; leg B: 1000 @0.45
    # q=10: cost=10*0.30 + 10*0.45 = 7.5 payout 10 -> +2.5
    # q=1000: cost=(3+ 990*0.80)+1000*0.45=(3+792)+450=1245 payout 1000 -> -245
    legs = [[(0.30, 10), (0.80, 1000)], [(0.45, 1000)]]
    e = basket_buy_edge(legs)
    assert abs(e.best_size - 10) < 1e-9
    assert abs(e.profit - 2.5) < 1e-6


def test_fee_reduces_payout_and_can_erase_thin_edge():
    legs = [[(0.49, 100)], [(0.50, 100)]]   # sum 0.99, gross +0.01/basket
    no_fee = basket_buy_edge(legs, fee_rate=0.0)
    assert no_fee.profit > 0
    # 2% fee on payout: payout 0.98/basket < 0.99 cost -> edge gone
    with_fee = basket_buy_edge(legs, fee_rate=0.02)
    assert with_fee.profit <= 0


def test_infeasible_when_a_leg_has_no_asks():
    legs = [[(0.40, 100)], []]
    e = basket_buy_edge(legs)
    assert not e.feasible
    assert e.profit == 0.0
    assert top_of_book_sum(legs) == float("inf")


def test_multi_outcome_negrisk_basket():
    # 4-way event, asks 0.20/0.25/0.25/0.24 = 0.94 -> +0.06/basket
    legs = [[(0.20, 50)], [(0.25, 50)], [(0.25, 50)], [(0.24, 50)]]
    e = basket_buy_edge(legs)
    assert e.n_legs == 4
    assert abs(e.best_size - 50) < 1e-9
    assert abs(e.cost - (0.94 * 50)) < 1e-6
    assert abs(e.profit - (50 - 47.0)) < 1e-6


def test_unsorted_asks_are_normalised():
    legs = [[(0.55, 100), (0.30, 5)], [(0.40, 100)]]  # leg A given worst-first
    e = basket_buy_edge(legs)
    # same as test_walks_book_optimum_at_breakpoint
    assert abs(e.profit - 6.25) < 1e-6
