"""Tests for shared utility functions."""

import math
from datetime import datetime, timezone

import pytest

from src.utils import (
    ceil_cents,
    error_message,
    quantize_buy_shares,
    quantize_sell_shares,
    round_cents,
    short_address,
    today_utc,
)


class TestShortAddress:
    def test_normal_address(self):
        addr = "0x1234567890abcdef1234567890abcdef12345678"
        assert short_address(addr) == "0x1234...5678"

    def test_short_string(self):
        # Should still work even if address is short (no crash)
        result = short_address("0xABCD")
        assert "..." in result


class TestRoundCents:
    def test_rounds_down(self):
        assert round_cents(1.234) == 1.23

    def test_rounds_up(self):
        assert round_cents(1.235) == 1.24

    def test_exact(self):
        assert round_cents(1.50) == 1.50

    def test_zero(self):
        assert round_cents(0.0) == 0.0

    def test_negative(self):
        assert round_cents(-1.236) == -1.24


class TestCeilCents:
    def test_rounds_up(self):
        assert ceil_cents(1.231) == 1.24

    def test_exact_stays(self):
        assert ceil_cents(1.23) == 1.23

    def test_zero(self):
        assert ceil_cents(0.0) == 0.0

    def test_small_fraction(self):
        assert ceil_cents(0.001) == 0.01


class TestTodayUtc:
    def test_returns_date_string(self):
        result = today_utc()
        # Format YYYY-MM-DD
        assert len(result) == 10
        assert result[4] == "-"
        assert result[7] == "-"

    def test_matches_utc_date(self):
        expected = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert today_utc() == expected


class TestErrorMessage:
    def test_exception(self):
        exc = ValueError("something went wrong")
        assert error_message(exc) == "something went wrong"

    def test_runtime_error(self):
        exc = RuntimeError("timeout")
        assert error_message(exc) == "timeout"

    def test_non_exception_object(self):
        assert error_message(42) == "42"

    def test_string(self):
        assert error_message("raw error") == "raw error"

    def test_none(self):
        assert error_message(None) == "None"


def _is_cents_clean(usd_amount: float) -> bool:
    """True iff usd_amount has <=2 decimal places (Polymarket maker rule)."""
    return abs(usd_amount * 100 - round(usd_amount * 100)) < 1e-6


def _has_four_decimal_shares(shares: float) -> bool:
    """True iff shares has <=4 decimal places (Polymarket taker rule)."""
    return abs(shares * 10000 - round(shares * 10000)) < 1e-6


class TestQuantizeBuyShares:
    """The Tiafoe failure: shares=ceil(bet/price) → 4-decimal maker_amount.

    quantize_buy_shares must always produce (shares, price*shares) that
    satisfy Polymarket's CLOB precision rules and stay within budget.
    """

    def test_tiafoe_regression_returns_integer_shares(self):
        """price=0.63, bet=$9, tick=0.01 → 14 shares ($8.82), not 14.29."""
        shares = quantize_buy_shares(9.0, 0.63, 0.01)
        assert shares == pytest.approx(14.0, abs=1e-9)
        assert 0.63 * shares == pytest.approx(8.82, abs=1e-9)

    def test_even_price_allows_fractional_shares(self):
        """price=0.50, tick=0.01: gcd(50,10000)=50 → step=200 → shares step 0.02."""
        shares = quantize_buy_shares(9.05, 0.50, 0.01)
        # 9.05/0.50 = 18.1; nearest 0.02 multiple <= 18.1 is 18.10 (m=181000,
        # which is multiple of 200). maker = 9.05.
        assert shares == pytest.approx(18.10, abs=1e-9)
        assert _is_cents_clean(0.50 * shares)

    def test_tick_0_001_with_coprime_price_needs_10x_shares(self):
        """price=0.999, tick=0.001: gcd(999, 1e5)=1 → step=1e5 → 10-share lots."""
        shares = quantize_buy_shares(20.0, 0.999, 0.001)
        assert shares == pytest.approx(20.0, abs=1e-9)
        assert 0.999 * shares == pytest.approx(19.98, abs=1e-9)

    def test_returns_zero_when_budget_below_smallest_step(self):
        """$5 at 0.999 (10-share lots = $9.99 min) cannot fit — must return 0."""
        assert quantize_buy_shares(5.0, 0.999, 0.001) == 0.0

    def test_rejects_invalid_price(self):
        assert quantize_buy_shares(10.0, 0.0, 0.01) == 0.0
        assert quantize_buy_shares(10.0, -0.5, 0.01) == 0.0
        # price >= 1 is invalid for the YES side (CLOB uses price < 1)
        assert quantize_buy_shares(10.0, 1.0, 0.01) == 0.0

    def test_rejects_invalid_budget(self):
        assert quantize_buy_shares(0.0, 0.5, 0.01) == 0.0
        assert quantize_buy_shares(-5.0, 0.5, 0.01) == 0.0

    def test_rejects_invalid_tick(self):
        assert quantize_buy_shares(10.0, 0.5, 0.0) == 0.0
        assert quantize_buy_shares(10.0, 0.5, -0.01) == 0.0

    def test_never_overspends_budget(self):
        """price * shares must never exceed the requested budget."""
        for price in [0.01, 0.05, 0.11, 0.23, 0.37, 0.50, 0.63, 0.77, 0.91, 0.99]:
            for bet in [5.0, 7.5, 10.0, 9.01, 100.0]:
                shares = quantize_buy_shares(bet, price, 0.01)
                if shares > 0:
                    assert price * shares <= bet + 1e-9, (
                        f"overspent: bet={bet} price={price} shares={shares}"
                    )

    @pytest.mark.parametrize("tick", [0.1, 0.01, 0.001, 0.0001])
    @pytest.mark.parametrize("bet", [5.0, 10.0, 20.0, 50.0, 9.0])
    def test_invariant_cents_clean_maker_across_ticks(self, tick, bet):
        """Across all valid prices on each tick, output always satisfies
        the Polymarket precision rules: shares <=4dp and price*shares <=2dp."""
        # Sample prices across the tick grid (skip 0 and the boundary at 1).
        n_ticks = int(round(1 / tick))
        # Test every tick at coarse grids, every 10th at fine grids.
        step = 1 if n_ticks <= 100 else max(1, n_ticks // 100)
        for k in range(1, n_ticks, step):
            price = round(k * tick, 4)
            shares = quantize_buy_shares(bet, price, tick)
            if shares == 0.0:
                continue
            assert _has_four_decimal_shares(shares), (
                f"shares not 4dp: tick={tick} price={price} bet={bet} shares={shares}"
            )
            assert _is_cents_clean(price * shares), (
                f"maker not cents: tick={tick} price={price} bet={bet} "
                f"shares={shares} maker={price * shares}"
            )


class TestQuantizeSellShares:
    """SELL legs face the symmetric rule: price*shares is the taker (USDC)
    proceeds and must round to cents.
    """

    def test_basic_sell_returns_integer_when_step_is_integer(self):
        """price=0.49, tick=0.01: gcd(49,10000)=1 → integer shares only."""
        shares = quantize_sell_shares(10.0, 0.49, 0.01)
        assert shares == pytest.approx(10.0, abs=1e-9)
        assert _is_cents_clean(0.49 * shares)

    def test_floors_to_largest_valid_position(self):
        """Holding 10.29 shares at price 0.63 (integer step) → sell 10, keep 0.29."""
        shares = quantize_sell_shares(10.29, 0.63, 0.01)
        assert shares == pytest.approx(10.0, abs=1e-9)
        assert _is_cents_clean(0.63 * shares)

    def test_returns_zero_when_position_below_step(self):
        """0.5 shares at 0.63 (integer step) → no valid sell."""
        assert quantize_sell_shares(0.5, 0.63, 0.01) == 0.0

    def test_never_exceeds_available_shares(self):
        for price in [0.05, 0.23, 0.50, 0.63, 0.99]:
            for held in [0.5, 1.0, 5.0, 10.29, 100.0]:
                shares = quantize_sell_shares(held, price, 0.01)
                if shares > 0:
                    assert shares <= held + 1e-9

    @pytest.mark.parametrize("tick", [0.1, 0.01, 0.001])
    def test_invariant_cents_clean_proceeds_across_ticks(self, tick):
        n_ticks = int(round(1 / tick))
        step = 1 if n_ticks <= 100 else max(1, n_ticks // 50)
        for k in range(1, n_ticks, step):
            price = round(k * tick, 4)
            for held in [10.0, 100.0, 14.29, 50.5]:
                shares = quantize_sell_shares(held, price, tick)
                if shares == 0.0:
                    continue
                assert _has_four_decimal_shares(shares)
                assert _is_cents_clean(price * shares), (
                    f"proceeds not cents: tick={tick} price={price} "
                    f"held={held} shares={shares} proceeds={price * shares}"
                )
