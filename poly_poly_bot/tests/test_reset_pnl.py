"""P&L/risk/spend reset: archive + clear file behavior and in-memory hooks."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from src.copy_trading.reset_pnl import _target_paths, reset_pnl

_NOW = datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc)
_STAMP = "20260617T120000Z"


def _seed(d: str) -> None:
    """Create a representative set of P&L + state + keep-me files."""
    os.makedirs(d, exist_ok=True)
    for name in ("copy_paper_ledger.jsonl", "realized-pnl.jsonl", "trade-history.jsonl",
                 "inventory.json", "preview-inventory.json", "tiered-risk-state.json",
                 "risk-state.json", "daily-spend.json", "trader-counts.json",
                 "seen-trades.json", "copy_watchlist.json"):
        with open(os.path.join(d, name), "w") as f:
            f.write("{}\n")


def test_reset_archives_and_clears_pnl_files(tmp_path):
    d = str(tmp_path)
    _seed(d)
    res = reset_pnl(d, confirm=True, now=_NOW, reset_memory=False)

    # P&L + state files cleared ...
    assert not os.path.exists(os.path.join(d, "realized-pnl.jsonl"))
    assert not os.path.exists(os.path.join(d, "copy_paper_ledger.jsonl"))
    assert not os.path.exists(os.path.join(d, "risk-state.json"))
    assert not os.path.exists(os.path.join(d, "daily-spend.json"))
    # ... and each archived with a timestamp suffix.
    assert os.path.exists(os.path.join(d, "archive", f"realized-pnl.jsonl.{_STAMP}"))
    assert os.path.exists(os.path.join(d, "archive", f"copy_paper_ledger.jsonl.{_STAMP}"))
    assert len(res.cleared) == 9 and len(res.archived) == 9


def test_reset_leaves_dedup_and_watchlist_untouched(tmp_path):
    d = str(tmp_path)
    _seed(d)
    reset_pnl(d, confirm=True, now=_NOW, reset_memory=False)
    assert os.path.exists(os.path.join(d, "seen-trades.json"))
    assert os.path.exists(os.path.join(d, "copy_watchlist.json"))


def test_reset_no_confirm_is_noop(tmp_path):
    d = str(tmp_path)
    _seed(d)
    res = reset_pnl(d, confirm=False, now=_NOW, reset_memory=False)
    assert res.cleared == [] and res.archived == []
    assert os.path.exists(os.path.join(d, "realized-pnl.jsonl"))


def test_reset_no_archive_clears_without_backup(tmp_path):
    d = str(tmp_path)
    _seed(d)
    res = reset_pnl(d, confirm=True, archive=False, now=_NOW, reset_memory=False)
    assert not os.path.exists(os.path.join(d, "realized-pnl.jsonl"))
    assert res.archived == []
    assert not os.path.exists(os.path.join(d, "archive"))


def test_reset_missing_files_are_skipped(tmp_path):
    d = str(tmp_path)  # empty dir, nothing seeded
    res = reset_pnl(d, confirm=True, now=_NOW, reset_memory=False)
    assert res.cleared == [] and res.archived == []
    assert len(res.skipped) == len(_target_paths(d, None))


def test_reset_custom_copy_paper_ledger_path(tmp_path):
    d = str(tmp_path)
    ledger = str(tmp_path / "elsewhere" / "ledger.jsonl")
    os.makedirs(os.path.dirname(ledger), exist_ok=True)
    with open(ledger, "w") as f:
        f.write("{}\n")
    res = reset_pnl(d, confirm=True, now=_NOW, copy_paper_ledger=ledger, reset_memory=False)
    assert not os.path.exists(ledger)
    assert any(p.endswith(f"ledger.jsonl.{_STAMP}") for p in res.archived)


# --------------------------------------------------------------------------- #
# In-memory reset hooks
# --------------------------------------------------------------------------- #

def test_inventory_reset_state_clears_positions():
    from src.copy_trading import inventory
    saved = inventory.get_positions()
    try:
        inventory._positions = {"t": {"shares": 5, "avg_price": 0.5}}
        inventory.reset_state()
        assert inventory.get_positions() == {}
    finally:
        inventory._positions = saved


def test_risk_modules_reset_state_zeroes_counters():
    from src.copy_trading import daily_spend_guard, risk_manager, tiered_risk_manager

    risk_manager._state.daily_volume_usd = 123.0
    risk_manager.reset_state()
    assert risk_manager._state.daily_volume_usd == 0.0

    tiered_risk_manager._tier_exposures["1a"].open_total = 99.0
    tiered_risk_manager.reset_state()
    assert tiered_risk_manager._tier_exposures["1a"].open_total == 0.0

    daily_spend_guard._state.spent_usd = 50.0
    daily_spend_guard.reset_state()
    assert daily_spend_guard._state.spent_usd == 0.0


def test_reset_pnl_reset_memory_invokes_hooks(tmp_path):
    from src.copy_trading import inventory
    saved = inventory.get_positions()
    try:
        inventory._positions = {"t": {"shares": 1, "avg_price": 0.4}}
        reset_pnl(str(tmp_path), confirm=True, now=_NOW, reset_memory=True)
        assert inventory.get_positions() == {}
    finally:
        inventory._positions = saved
