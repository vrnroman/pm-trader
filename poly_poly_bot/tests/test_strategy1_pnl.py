"""Strategy 1 (copy trading) P&L: aggregation + the /pnl report wiring.

Before this module existed the /pnl report's Strategy-1 block was a constant:
realized summed a ``pnl`` field that ``TradeRecord`` never had (always 0),
unrealized and open-bet count were hardcoded to 0, and the realized P&L the
redeemer computed was thrown away. These tests pin the real behaviour so that
regression can't come back silently.
"""

from __future__ import annotations

import json

import pytest

from src.copy_trading import pnl as s1pnl
from src.copy_trading.pnl import OpenPositionPnl


# --------------------------------------------------------------------------- #
# Pure aggregation
# --------------------------------------------------------------------------- #

def test_summarize_realized_counts_wins_losses_and_sums():
    rows = [
        {"pnl": 10.0, "won": True},
        {"pnl": -4.0, "won": False},
        {"pnl": 2.5, "won": True},
    ]
    total, wins, losses = s1pnl.summarize_realized(rows)
    assert total == 8.5
    assert wins == 2
    assert losses == 1


def test_summarize_realized_infers_win_loss_from_sign_when_won_absent():
    rows = [{"pnl": 3.0}, {"pnl": -1.0}, {"pnl": 0.0}]
    total, wins, losses = s1pnl.summarize_realized(rows)
    assert total == 2.0
    assert wins == 1
    assert losses == 1  # break-even is neither


def test_value_open_positions_marks_to_market():
    positions = {
        "tokA": {"shares": 100.0, "avg_price": 0.40, "market": "Will A win?"},
    }
    prices = {"tokA": 0.60}
    out = s1pnl.value_open_positions(positions, lambda t: prices.get(t), fee=0.0)
    assert len(out) == 1
    p = out[0]
    assert p.cost == pytest.approx(40.0)
    assert p.value == pytest.approx(60.0)
    assert p.unrealized_pnl == pytest.approx(20.0)
    assert p.unrealized_pct == pytest.approx(0.5)


def test_value_open_positions_applies_exit_fee_when_requested():
    positions = {"t": {"shares": 100.0, "avg_price": 0.50}}
    out = s1pnl.value_open_positions(positions, lambda t: 0.50, fee=0.02)
    # Selling 100 shares at 0.50 with 2% fee returns 49.0 vs 50.0 cost.
    assert out[0].unrealized_pnl == pytest.approx(-1.0)


def test_value_open_positions_unpriced_position_has_none_pnl():
    positions = {"t": {"shares": 10.0, "avg_price": 0.30}}
    out = s1pnl.value_open_positions(positions, lambda t: None)
    assert out[0].unrealized_pnl is None
    assert out[0].cur_price is None
    assert out[0].cost == pytest.approx(3.0)


def test_value_open_positions_skips_zero_share_positions():
    positions = {"t": {"shares": 0.0, "avg_price": 0.30}}
    out = s1pnl.value_open_positions(positions, lambda t: 0.5)
    assert out == []


def test_summarize_combines_realized_and_open():
    realized = [{"pnl": 5.0, "won": True}, {"pnl": -2.0, "won": False}]
    open_pos = [
        OpenPositionPnl("a", "A", 100, 0.40, 0.60, cost=40.0, value=60.0,
                        unrealized_pnl=20.0, unrealized_pct=0.5),
        OpenPositionPnl("b", "B", 50, 0.50, None, cost=25.0, value=0.0,
                        unrealized_pnl=None, unrealized_pct=None),
    ]
    s = s1pnl.summarize(realized, open_pos)
    assert s.realized_pnl == 3.0
    assert s.realized_wins == 1 and s.realized_losses == 1
    assert s.unrealized_pnl == 20.0       # unpriced position excluded
    assert s.open_positions == 2
    assert s.priced == 1 and s.unpriced == 1
    assert s.cost_basis == pytest.approx(65.0)  # both positions' cost
    assert s.market_value == pytest.approx(60.0)
    assert s.net_pnl == 23.0
    assert s.hit_rate == pytest.approx(0.5)
    # ROI is computed against full cost basis of open positions.
    assert s.unrealized_roi == pytest.approx(20.0 / 65.0)


def test_summarize_empty_is_all_zero():
    s = s1pnl.summarize([], [])
    assert s.realized_pnl == 0.0
    assert s.unrealized_pnl == 0.0
    assert s.open_positions == 0
    assert s.net_pnl == 0.0
    assert s.hit_rate is None
    assert s.unrealized_roi is None


# --------------------------------------------------------------------------- #
# Realized ledger round-trip
# --------------------------------------------------------------------------- #

@pytest.fixture
def tmp_data_dir(monkeypatch, tmp_path):
    from src.config import CONFIG
    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    return tmp_path


def test_append_and_load_realized_round_trip(tmp_data_dir):
    s1pnl.append_realized({"title": "X", "pnl": 1.5, "won": True})
    s1pnl.append_realized({"title": "Y", "pnl": -0.5, "won": False})
    rows = s1pnl.load_realized()
    assert [r["title"] for r in rows] == ["X", "Y"]
    total, wins, losses = s1pnl.summarize_realized(rows)
    assert total == 1.0 and wins == 1 and losses == 1


def test_load_realized_missing_file_returns_empty(tmp_data_dir):
    assert s1pnl.load_realized() == []


def test_load_realized_skips_corrupt_lines(tmp_data_dir):
    path = s1pnl.realized_pnl_path()
    with open(path, "w") as f:
        f.write(json.dumps({"pnl": 2.0}) + "\n")
        f.write("not json\n")
        f.write(json.dumps({"pnl": 3.0}) + "\n")
    rows = s1pnl.load_realized()
    assert len(rows) == 2


# --------------------------------------------------------------------------- #
# /pnl report wiring — the regression that motivated all of this
# --------------------------------------------------------------------------- #

@pytest.fixture
def s1_pnl_env(monkeypatch, tmp_path):
    """Isolate /pnl: only Strategy 1 enabled, tmp data dir, controlled prices."""
    from src import telegram_bot
    from src.config import CONFIG
    from src.copy_trading import inventory

    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(CONFIG, "strategy1_enabled", True)
    monkeypatch.setattr(CONFIG, "preview_mode", False)
    # Keep System B (paper-copy harness) out of these System-A tests: point its
    # ledger + watchlist at non-existent tmp paths so the unified /pnl shows
    # only the inventory/realized-ledger data the test sets up.
    monkeypatch.setattr(CONFIG, "copy_paper_ledger", str(tmp_path / "paper.jsonl"))
    monkeypatch.setattr(CONFIG, "copy_paper_watchlist", str(tmp_path / "wl.json"))

    buf: list[str] = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda text, **_kw: buf.append(text))

    # Controlled inventory + price feed.
    monkeypatch.setattr(inventory, "_positions", {})
    prices: dict[str, float] = {}
    monkeypatch.setattr(telegram_bot, "_fetch_midpoint", lambda t: prices.get(t))

    return telegram_bot, inventory, prices, buf


def test_pnl_reports_real_unrealized_and_open_count(s1_pnl_env):
    """Regression: open copy positions must show non-zero unrealized + count,
    not the old hardcoded 'Unrealized $0.00 / Open bets 0'."""
    telegram_bot, inventory, prices, buf = s1_pnl_env
    inventory._positions = {
        "tokA": {"shares": 100.0, "avg_price": 0.40, "market": "Will A win?"},
    }
    prices["tokA"] = 0.60

    telegram_bot._handle_command("/pnl")
    out = buf[-1]

    assert "Unrealized:  <b>$+20.00</b>" in out
    assert "Open bets:   <b>1</b>" in out
    assert "Open bets:   <b>0</b>" not in out  # the one open position is reflected everywhere


def test_pnl_reports_realized_from_ledger_with_record(s1_pnl_env):
    telegram_bot, inventory, prices, buf = s1_pnl_env
    s1pnl.append_realized({"title": "Won market", "pnl": 12.0, "won": True})
    s1pnl.append_realized({"title": "Lost market", "pnl": -3.0, "won": False})

    telegram_bot._handle_command("/pnl")
    out = buf[-1]

    assert "Realized:    <b>$+9.00</b>" in out
    assert "1W/1L" in out  # win/loss record surfaced


def test_pnl_net_combines_realized_and_unrealized(s1_pnl_env):
    telegram_bot, inventory, prices, buf = s1_pnl_env
    s1pnl.append_realized({"title": "W", "pnl": 10.0, "won": True})
    inventory._positions = {"t": {"shares": 100.0, "avg_price": 0.50, "market": "M"}}
    prices["t"] = 0.45  # -5 unrealized

    telegram_bot._handle_command("/pnl")
    out = buf[-1]

    assert "Realized:    <b>$+10.00</b>" in out
    assert "Unrealized:  <b>$-5.00</b>" in out
    assert "Net:         <b>$+5.00</b>" in out


def test_pnl_flags_unpriced_positions(s1_pnl_env):
    telegram_bot, inventory, prices, buf = s1_pnl_env
    inventory._positions = {"t": {"shares": 10.0, "avg_price": 0.30, "market": "M"}}
    # no price for "t" -> unpriced

    telegram_bot._handle_command("/pnl")
    out = buf[-1]

    assert "unpriced" in out
    assert "Open bets:   <b>1</b>" in out


def test_pnl_empty_strategy1_is_all_zero(s1_pnl_env):
    telegram_bot, inventory, prices, buf = s1_pnl_env
    telegram_bot._handle_command("/pnl")
    out = buf[-1]

    assert "Realized:    <b>$+0.00</b>" in out
    assert "Unrealized:  <b>$+0.00</b>" in out
    assert "Open bets:   <b>0</b>" in out
