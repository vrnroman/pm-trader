"""Tests for the selective System-B reset (keep net-positive wallets)."""

from __future__ import annotations

import os

from src.copy_trading.copy_paper import PaperCopyLedger, PaperPosition
from src.copy_trading.reset_pnl import selective_reset_system_b

WIN = "0xwin"
LOSE = "0xlose"
OPENW = "0xopen"


def _pos(target, i, pnl, closed=True, entry=0.5):
    return PaperPosition(
        copy_id=f"{target}-{i}", target=target, condition_id="0xC",
        token_id=f"TOK{i}", outcome_index=0, category="research",
        their_price=0.5, entry_price=entry, shares=20.0, spent=10.0, drag_bps=0,
        opened_ts=0.0, closed=closed, won=(pnl > 0), pnl=pnl)


def _seed(path):
    L = PaperCopyLedger(path)
    L.add(_pos(WIN, "a", 5.0))           # winner net +10
    L.add(_pos(WIN, "b", 5.0))
    L.add(_pos(LOSE, "c", -5.0))         # loser net -5
    L.add(_pos(OPENW, "d", 0.0, closed=False))  # only open -> net 0
    return L


def test_keeps_only_positive_wallets(tmp_path):
    led = str(tmp_path / "l.jsonl")
    _seed(led)
    res = selective_reset_system_b(led, confirm=True, archive=True)
    assert res.applied is True
    assert res.kept_wallets == [WIN]
    assert res.kept_rows == 2 and res.dropped_rows == 2

    after = PaperCopyLedger(led)
    assert {p.target for p in after.positions.values()} == {WIN}
    assert len(after.positions) == 2


def test_dust_rows_dropped_even_for_kept_wallet(tmp_path):
    led = str(tmp_path / "l.jsonl")
    L = _seed(led)
    # a dust fill for the winner (entry far below their_price) — excluded from the
    # net calc AND dropped from the rewritten ledger.
    L.add(_pos(WIN, "dust", 999.0, entry=0.001))
    res = selective_reset_system_b(led, confirm=True, archive=False)
    assert res.kept_wallets == [WIN]
    assert res.kept_rows == 2                     # the two clean winner rows only


def test_dry_run_changes_nothing(tmp_path):
    led = str(tmp_path / "l.jsonl")
    _seed(led)
    before = os.path.getmtime(led)
    res = selective_reset_system_b(led, confirm=False)
    assert res.applied is False
    assert res.kept_wallets == [WIN]             # still reports the plan
    assert os.path.getmtime(led) == before        # file untouched


def test_archive_created(tmp_path):
    led = str(tmp_path / "l.jsonl")
    _seed(led)
    res = selective_reset_system_b(led, confirm=True, archive=True)
    assert res.archived and os.path.exists(res.archived)


def test_missing_ledger_is_noop(tmp_path):
    res = selective_reset_system_b(str(tmp_path / "nope.jsonl"), confirm=True)
    assert res.applied is False and res.kept_rows == 0
