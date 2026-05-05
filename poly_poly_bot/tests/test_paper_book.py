"""Tests for the tennis-arb paper-trading book.

Covers the full position lifecycle (OPEN → HOLD → FLIP → RESOLVED),
PnL accounting, persistence across instantiations, the per-event
breakdown, and the void/null resolution edge case.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

import pytest

from src.tennis.paper_book import TennisPaperBook


def _signal(
    *,
    condition_id: str = "0xMATCH1",
    token_id: str = "TOKA",
    price: float = 0.50,
    size: float = 10.0,
    player_a: str = "Hugo Dellien",
    player_b: str = "Jesper de Jong",
    target_player: str = "Hugo Dellien",
    outcome_label: str = "Hugo Dellien",
    sharp_prob: float = 0.65,
    divergence: float = 0.15,
    event_title: str = "Internazionali BNL d'Italia",
    market_id: str = "M1",
    side: str = "A",
) -> dict[str, Any]:
    """Build the dict shape that TennisArbStrategy.scan() emits."""
    return {
        "strategy": "tennis_arb",
        "condition_id": condition_id,
        "token_id": token_id,
        "market_id": market_id,
        "polymarket_price": price,
        "bet_size": size,
        "player_a": player_a,
        "player_b": player_b,
        "target_player": target_player,
        "outcome_label": outcome_label,
        "sharp_prob": sharp_prob,
        "divergence": divergence,
        "event_title": event_title,
        "event_slug": "rome-2026",
        "polymarket_url": "https://polymarket.com/event/rome-2026",
        "tournament": "Atp Rome",
        "match_time": "2026-05-06T14:00:00+00:00",
        "side": side,
    }


@pytest.fixture
def book(tmp_path):
    return TennisPaperBook(data_dir=str(tmp_path))


# ── Lifecycle: OPEN / HOLD / FLIP / RESOLVE ───────────────────────────


def test_open_creates_position_with_correct_shares(book):
    sig = _signal(price=0.40, size=10.0)
    res = book.process_signal(sig)
    assert res["action"] == "OPEN"
    assert res["realized_pnl_usd"] is None
    open_positions = book.open_positions()
    assert len(open_positions) == 1
    pos = open_positions[0]
    # shares = size / price = 10 / 0.40 = 25
    assert pos["shares"] == 25.0
    assert pos["entry_price"] == 0.4
    assert pos["status"] == "OPEN"


def test_same_side_signal_holds(book):
    book.process_signal(_signal(token_id="TOKA", price=0.40, size=10.0))
    res = book.process_signal(_signal(token_id="TOKA", price=0.45, size=10.0))
    # Same token = same direction → HOLD. We don't stack into the position
    # (would muddle PnL accounting).
    assert res["action"] == "HOLD"
    assert len(book.open_positions()) == 1
    # Original entry preserved
    assert book.open_positions()[0]["entry_price"] == 0.4


def test_flip_closes_old_and_opens_new(book):
    # Hold YES on player A at 0.40; new signal flips to player B at 0.65.
    # The implied current PM price for our (now-disfavored) side is
    # 1 - 0.65 = 0.35, so we sell YES_A at 0.35 — a loss vs entry 0.40.
    book.process_signal(_signal(token_id="TOKA", price=0.40, size=10.0))
    res = book.process_signal(_signal(
        token_id="TOKB", price=0.65, size=8.0,
        target_player="Jesper de Jong", outcome_label="Jesper de Jong",
    ))
    assert res["action"] == "FLIP"
    # shares_a = 10 / 0.40 = 25; realized = 25 * (0.35 - 0.40) = -1.25
    assert res["realized_pnl_usd"] == pytest.approx(-1.25, rel=1e-4)
    open_positions = book.open_positions()
    assert len(open_positions) == 1  # the new B position
    new = open_positions[0]
    assert new["token_id"] == "TOKB"
    assert new["entry_price"] == 0.65
    assert new["shares"] == pytest.approx(8.0 / 0.65, rel=1e-4)
    closed = book.closed_positions()
    assert len(closed) == 1
    assert closed[0]["exit_reason"] == "FLIP"


def test_flip_with_winning_close_realizes_profit(book):
    # Enter A at 0.30, then flip into B at 0.85 → close-out price for A is
    # 1 - 0.85 = 0.15 (we lose), so this still loses. The profitable flip
    # case is when the OLD price has *fallen* against us — er, this test
    # is to verify the math in the *winning* close direction. Easier: enter
    # A at 0.70 and the flip implies our side is now at 1 - 0.20 = 0.80
    # → profit.
    book.process_signal(_signal(token_id="TOKA", price=0.70, size=14.0))
    res = book.process_signal(_signal(token_id="TOKB", price=0.20, size=10.0))
    assert res["action"] == "FLIP"
    # shares = 14 / 0.70 = 20; close at 1 - 0.20 = 0.80; realized = 20*(0.80-0.70)=2.00
    assert res["realized_pnl_usd"] == pytest.approx(2.0, rel=1e-4)


def test_resolution_winning_token_closes_at_one(book):
    book.process_signal(_signal(token_id="TOKA", price=0.40, size=10.0))
    closed = book.resolve("0xMATCH1", winning_token_id="TOKA")
    assert len(closed) == 1
    # shares = 25; PnL = 25 * (1.0 - 0.4) = 15.0
    assert closed[0]["realized_pnl_usd"] == pytest.approx(15.0, rel=1e-4)
    assert closed[0]["exit_reason"] == "RESOLVED"
    assert book.open_position_count() == 0


def test_resolution_losing_token_closes_at_zero(book):
    book.process_signal(_signal(token_id="TOKA", price=0.40, size=10.0))
    closed = book.resolve("0xMATCH1", winning_token_id="TOKB")
    assert len(closed) == 1
    # PnL = 25 * (0.0 - 0.4) = -10.0
    assert closed[0]["realized_pnl_usd"] == pytest.approx(-10.0, rel=1e-4)


def test_resolution_void_closes_at_entry_price(book):
    # Walkover / void: book closes at entry_price → zero realized PnL.
    book.process_signal(_signal(token_id="TOKA", price=0.40, size=10.0))
    closed = book.resolve("0xMATCH1", winning_token_id=None)
    assert len(closed) == 1
    assert closed[0]["realized_pnl_usd"] == pytest.approx(0.0, abs=1e-4)
    assert closed[0]["exit_price"] == pytest.approx(0.4, abs=1e-4)


def test_resolution_only_touches_matching_condition_id(book):
    book.process_signal(_signal(condition_id="0xA", token_id="TA", price=0.5, size=10))
    book.process_signal(_signal(condition_id="0xB", token_id="TB", price=0.5, size=10))
    closed = book.resolve("0xA", winning_token_id="TA")
    assert len(closed) == 1
    assert book.open_position_count() == 1  # the 0xB position is still open


# ── PnL aggregation ──────────────────────────────────────────────────


def test_realized_pnl_sums_all_closed(book):
    # Open A on match 1, resolve as winner: +6 PnL (15 shares * (1.0-0.6)=6)
    book.process_signal(_signal(condition_id="0xA", token_id="TA", price=0.60, size=9))
    book.resolve("0xA", winning_token_id="TA")
    # Open A on match 2, resolve as loser: -10 PnL (20 shares * (0-0.5))
    book.process_signal(_signal(condition_id="0xB", token_id="TB", price=0.50, size=10))
    book.resolve("0xB", winning_token_id="OTHER")
    # Total realized = 6 + -10 = -4
    assert book.realized_pnl() == pytest.approx(-4.0, abs=1e-4)


def test_unrealized_pnl_marks_to_current_price(book):
    book.process_signal(_signal(condition_id="0xA", token_id="TA", price=0.50, size=10))
    # 20 shares at entry 0.50; current 0.65 → unrealized = 20 * (0.65-0.50) = 3.0
    u = book.unrealized_pnl({"TA": 0.65})
    assert u == pytest.approx(3.0, abs=1e-4)


def test_unrealized_pnl_skips_positions_without_quote(book):
    book.process_signal(_signal(condition_id="0xA", token_id="TA", price=0.5, size=10))
    book.process_signal(_signal(condition_id="0xB", token_id="TB", price=0.5, size=10))
    # Only TA in the price map; TB contributes 0
    u = book.unrealized_pnl({"TA": 0.6})
    assert u == pytest.approx(20.0 * (0.6 - 0.5), abs=1e-4)


# ── Per-event breakdown ──────────────────────────────────────────────


def test_breakdown_groups_by_event(book):
    book.process_signal(_signal(
        condition_id="0xA", token_id="TA", event_title="Match 1", price=0.4, size=10,
    ))
    book.process_signal(_signal(
        condition_id="0xB", token_id="TB", event_title="Match 2", price=0.6, size=12,
    ))
    book.resolve("0xA", winning_token_id="TA")  # +15 realized for Match 1
    breakdown = book.breakdown_by_event(current_prices={"TB": 0.7})
    by_event = {g["event_title"]: g for g in breakdown}
    assert by_event["Match 1"]["realized_pnl_usd"] == pytest.approx(15.0, abs=1e-4)
    # Match 2 unrealized: 20 shares (12/0.6) * (0.7-0.6) = 2.0
    assert by_event["Match 2"]["unrealized_pnl_usd"] == pytest.approx(2.0, abs=1e-4)
    # Sorting is by total descending — Match 1 (15.0) before Match 2 (2.0)
    assert breakdown[0]["event_title"] == "Match 1"


# ── Persistence ───────────────────────────────────────────────────────


def test_state_persists_across_instances(tmp_path):
    book = TennisPaperBook(data_dir=str(tmp_path))
    book.process_signal(_signal(token_id="TA", price=0.40, size=10))
    book.resolve("0xMATCH1", winning_token_id="TA")
    realized_before = book.realized_pnl()
    # Build a fresh book from disk and verify the closed position survived
    book2 = TennisPaperBook(data_dir=str(tmp_path))
    assert book2.realized_pnl() == pytest.approx(realized_before, abs=1e-4)
    assert book2.open_position_count() == 0
    assert len(book2.closed_positions()) == 1


def test_corrupt_state_file_resets_and_does_not_crash(tmp_path):
    p = tmp_path / "tennis_paper_book.json"
    p.write_text("not json {")
    # Should log + start fresh
    book = TennisPaperBook(data_dir=str(tmp_path))
    assert book.realized_pnl() == 0.0
    assert book.open_position_count() == 0
    # And still functional
    book.process_signal(_signal(price=0.5, size=10.0))
    assert book.open_position_count() == 1


# ── Take-profit ──────────────────────────────────────────────────────


def test_take_profit_closes_at_exit_price(book):
    book.process_signal(_signal(token_id="TOKA", price=0.20, size=10.0))
    closed = book.take_profit("TOKA", exit_price=0.60)
    assert closed is not None
    # shares = 10 / 0.20 = 50; realized = 50 * (0.60 - 0.20) = 20.0
    assert closed["realized_pnl_usd"] == pytest.approx(20.0, abs=1e-4)
    assert closed["exit_reason"] == "TAKE_PROFIT"
    assert book.open_position_count() == 0


def test_take_profit_unknown_token_returns_none(book):
    book.process_signal(_signal(token_id="TOKA", price=0.20, size=10.0))
    assert book.take_profit("OTHER", exit_price=0.60) is None
    assert book.open_position_count() == 1


def test_take_profit_persists_to_disk(tmp_path):
    book = TennisPaperBook(data_dir=str(tmp_path))
    book.process_signal(_signal(token_id="TOKA", price=0.20, size=10.0))
    book.take_profit("TOKA", exit_price=0.60)
    book2 = TennisPaperBook(data_dir=str(tmp_path))
    assert book2.open_position_count() == 0
    assert book2.realized_pnl() == pytest.approx(20.0, abs=1e-4)


# ── Defensive guards ─────────────────────────────────────────────────


def test_zero_price_signal_is_skipped_not_crashed(book):
    res = book.process_signal(_signal(price=0.0, size=10.0))
    assert res["action"] == "HOLD"
    assert book.open_position_count() == 0
