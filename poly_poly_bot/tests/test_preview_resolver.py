"""Paper-mode realization for the tiered executor (System A)."""

from __future__ import annotations

import pytest

from src.copy_trading.preview_resolver import (
    classify_position,
    realize_preview_positions,
    run_preview_realization,
)


def _market(closed=True, prices='["1","0"]', tokens='["YES","NO"]'):
    return {"closed": closed, "outcomePrices": prices, "clobTokenIds": tokens}


# --------------------------------------------------------------------------- #
# classify_position (pure)
# --------------------------------------------------------------------------- #

def test_classify_won_when_held_token_is_winning_outcome():
    assert classify_position(_market(), "YES") is True


def test_classify_lost_when_held_token_is_losing_outcome():
    assert classify_position(_market(), "NO") is False


def test_classify_none_when_market_open():
    assert classify_position(_market(closed=False), "YES") is None


def test_classify_none_when_not_cleanly_resolved():
    # closed but prices haven't settled to ~1/0 yet
    assert classify_position(_market(prices='["0.5","0.5"]'), "YES") is None


def test_classify_none_when_token_not_in_market():
    assert classify_position(_market(), "OTHER") is None


def test_classify_accepts_list_shaped_fields():
    m = {"closed": True, "outcomePrices": ["0", "1"], "clobTokenIds": ["YES", "NO"]}
    assert classify_position(m, "NO") is True
    assert classify_position(m, "YES") is False


def test_classify_none_on_missing_market():
    assert classify_position(None, "YES") is None


# --------------------------------------------------------------------------- #
# realize_preview_positions (pure)
# --------------------------------------------------------------------------- #

def test_realize_books_resolved_and_skips_open():
    positions = {
        "YES": {"shares": 100.0, "avg_price": 0.40, "market": "Win?",
                "market_key": "0xwin", "tier": "1a", "trader_address": "0xAAA"},
        "OPEN": {"shares": 50.0, "avg_price": 0.30, "market": "Open?",
                 "market_key": "0xopen", "tier": "1b", "trader_address": "0xBBB"},
    }

    def fetch(cid):
        if cid == "0xwin":
            return _market(prices='["1","0"]', tokens='["YES","X"]')
        return _market(closed=False)   # 0xopen still open

    rows, drop = realize_preview_positions(positions, fetch, now_iso="2026-06-17T00:00:00Z")
    assert drop == ["YES"]
    assert len(rows) == 1
    r = rows[0]
    assert r["won"] is True
    assert r["pnl"] == pytest.approx(100.0 - 40.0)   # winner redeems shares @ $1
    assert r["tier"] == "1a" and r["trader_address"] == "0xAAA"
    assert r["exit"] == "resolution"


def test_realize_books_loss():
    positions = {
        "NO": {"shares": 100.0, "avg_price": 0.40, "market": "M",
               "market_key": "0xc", "tier": "1a", "trader_address": "0xA"},
    }
    rows, drop = realize_preview_positions(
        positions, lambda c: _market(prices='["1","0"]', tokens='["YES","NO"]'),
    )
    assert drop == ["NO"]
    assert rows[0]["won"] is False
    assert rows[0]["pnl"] == pytest.approx(-40.0)     # loser redeems $0


def test_realize_skips_positions_without_condition_id():
    positions = {"T": {"shares": 10.0, "avg_price": 0.5, "market_key": ""}}
    rows, drop = realize_preview_positions(positions, lambda c: _market())
    assert rows == [] and drop == []


# --------------------------------------------------------------------------- #
# run_preview_realization (integration: appends + drops)
# --------------------------------------------------------------------------- #

def test_book_preview_exit_records_early_exit(monkeypatch, tmp_path):
    from src.config import CONFIG
    from src.copy_trading import inventory
    from src.copy_trading import pnl as s1pnl
    from src.copy_trading.trade_executor import _book_preview_exit
    from src.models import DetectedTrade

    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    saved = inventory.get_positions()
    try:
        inventory._positions = {
            "TOK": {"shares": 100.0, "avg_price": 0.40, "market": "M",
                    "market_key": "0xc", "tier": "1b", "trader_address": "0xWALLET"},
        }
        trade = DetectedTrade(
            id="i", trader_address="0xWALLET", timestamp="2026-06-17T00:00:00Z",
            market="M", condition_id="0xc", token_id="TOK", side="SELL",
            size=10.0, price=0.55, outcome="Yes",
        )
        _book_preview_exit(trade, sell_shares=100.0)
        rows = s1pnl.load_realized()
        assert len(rows) == 1
        r = rows[0]
        assert r["exit"] == "sell"
        assert r["pnl"] == pytest.approx(100.0 * (0.55 - 0.40))
        assert r["tier"] == "1b" and r["trader_address"] == "0xWALLET"
        assert r["won"] is True
    finally:
        inventory._positions = saved


def test_run_preview_realization_appends_and_drops(monkeypatch, tmp_path):
    from src.config import CONFIG
    from src.copy_trading import inventory
    from src.copy_trading import pnl as s1pnl

    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    # _INVENTORY_FILE is bound at import time, so redirect it too or record_sell
    # would persist to the real repo data dir.
    monkeypatch.setattr(inventory, "_INVENTORY_FILE", str(tmp_path / "preview-inventory.json"))
    saved = inventory.get_positions()
    try:
        inventory._positions = {
            "YES": {"shares": 100.0, "avg_price": 0.40, "market": "Win?",
                    "market_key": "0xwin", "tier": "1a", "trader_address": "0xAAA"},
        }
        n = run_preview_realization(
            market_fetcher=lambda c: _market(prices='["1","0"]', tokens='["YES","NO"]')
        )
        assert n == 1
        assert "YES" not in inventory.get_positions()       # dropped
        rows = s1pnl.load_realized()
        assert len(rows) == 1 and rows[0]["won"] is True and rows[0]["tier"] == "1a"
    finally:
        inventory._positions = saved
