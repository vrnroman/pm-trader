"""The owner's picks (2026-10-10): in Z by his decision, never benched,
held to resolution (their sells are not mirrored)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.config import CONFIG
from src.copy_trading import owner_picks, strategy_config, wallet_form, zset

A = "0x1985327e5782c62362dbbdf714c423d40d8f51ab"
B = "0x09b045baad1fbe115c70785635a261411774a3b6"


@pytest.fixture
def picks(monkeypatch, tmp_path):
    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(CONFIG, "live_hold_wallets", f"{A.upper().replace('0X', '0x')}, {B},not-an-address")
    monkeypatch.setattr(zset, "evicted_set", lambda: set())
    return tmp_path


def test_the_list_parses_and_ignores_junk(picks):
    assert owner_picks.hold_wallets() == {A, B}
    assert owner_picks.is_pick(A.upper().replace("0X", "0x")) and not owner_picks.is_pick("0xabc")


def test_a_pick_is_in_z_with_a_tier_and_never_benched(picks):
    assert A in zset.wallet_set() and B in zset.wallet_set()
    assert strategy_config.get_wallet_tier(A) == "1b"
    benched, why = wallet_form.is_benched(A)
    assert benched is False and "held to resolution" in why


def test_an_eviction_still_removes_a_pick(picks, monkeypatch):
    monkeypatch.setattr(zset, "evicted_set", lambda: {A})
    assert A not in zset.wallet_set() and B in zset.wallet_set()
    assert strategy_config.get_wallet_tier(A) is None


def test_no_list_changes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(CONFIG, "live_hold_wallets", "")
    assert owner_picks.hold_wallets() == set()


def test_the_executor_ignores_a_picks_sells_and_skips_its_flip_gate():
    src = (Path(__file__).resolve().parents[1] / "src" / "copy_trading" / "trade_executor.py").read_text()
    i = src.index("if owner_picks.is_pick(trade.trader_address):")
    j = src.index("# --- SELL check: verify we have a position ---")
    assert i < j and "mark_trade_as_seen(trade.id)" in src[i:j] and "continue" in src[i:j]
    assert 'if trade.side == "BUY" and not _op.is_pick(trade.trader_address):' in src
