"""Tests for the /golive pre-flip gate and its pure checker."""

from __future__ import annotations

import pytest

from src.copy_trading import promotion_gate as pg
from src.copy_trading import promotion_state as ps
from src.copy_trading.copy_paper import PaperPosition

FLOOR_KW = dict(min_n=15, min_roi=0.10, min_tstat=0.0,
                min_second_half_roi=-0.10, min_conditions=8, min_categories=3)


def pos(target, i, *, pnl, spent=10.0, entry=0.5):
    return PaperPosition(
        copy_id=f"{target}-{i}", target=target, condition_id=f"c{i}",
        token_id=f"T{i}", outcome_index=0, category=f"cat{i % 4}",
        their_price=entry, entry_price=entry, shares=spent / entry, spent=spent,
        drag_bps=0, opened_ts=float(i), closed=True, won=(pnl > 0), pnl=pnl,
        closed_ts=float(i))


def _ready_positions(n=30):
    return [pos("0xA", i, pnl=1.2) for i in range(n)]


def test_golive_ready_when_all_pass():
    s = pg.compute_stats("0xA", _ready_positions(30))
    ready, checks = pg.golive_check(
        s, last_trade_ts=1_000_000.0, now=1_000_000.0 + 86400,
        min_settled=30, max_idle_days=14.0, min_roi=0.0, floor_kwargs=FLOOR_KW)
    assert ready is True
    assert all(ok for _, ok, _ in checks)


def test_golive_holds_on_thin_sample():
    s = pg.compute_stats("0xA", _ready_positions(20))     # < 30 golive bar
    ready, checks = pg.golive_check(
        s, last_trade_ts=1_000_000.0, now=1_000_000.0,
        min_settled=30, max_idle_days=14.0, min_roi=0.0, floor_kwargs=FLOOR_KW)
    assert ready is False
    assert any(("settled" in label and not ok) for label, ok, _ in checks)


def test_golive_holds_on_stale_wallet():
    s = pg.compute_stats("0xA", _ready_positions(30))
    ready, checks = pg.golive_check(
        s, last_trade_ts=0.0, now=100 * 86400,             # 100 days idle
        min_settled=30, max_idle_days=14.0, min_roi=0.0, floor_kwargs=FLOOR_KW)
    assert ready is False
    assert any(("active" in label and not ok) for label, ok, _ in checks)


def test_golive_holds_when_roi_went_negative():
    s = pg.compute_stats("0xA", [pos("0xA", i, pnl=-0.5) for i in range(30)])
    ready, checks = pg.golive_check(
        s, last_trade_ts=1.0, now=1.0,
        min_settled=30, max_idle_days=14.0, min_roi=0.0, floor_kwargs=FLOOR_KW)
    assert ready is False


# --- the Telegram handler ---

@pytest.fixture
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMOTED_WALLETS_STORE", str(tmp_path / "p.json"))
    ps.clear_cache()
    yield
    ps.clear_cache()


def test_golive_handler_reports(stores, tmp_path, monkeypatch):
    import json
    import time

    from src import telegram_bot
    wallet = "0x" + "a" * 40
    now = time.time()
    # a ready ledger for the wallet, with RECENT timestamps (active within 14d)
    ledger = tmp_path / "ledger.jsonl"
    with open(ledger, "w") as f:
        for i in range(30):
            p = pos(wallet, i, pnl=1.2)
            p.opened_ts = now - 3600 * i        # most recent bet ~now
            p.closed_ts = now - 3600 * i
            f.write(json.dumps(p.__dict__) + "\n")
    monkeypatch.setattr(telegram_bot.CONFIG, "copy_paper_ledger", str(ledger), raising=False)
    ps.add_promoted(wallet, tier="1b")

    sent = []
    monkeypatch.setattr(telegram_bot, "_send_chunked", lambda t, **k: sent.append(t))
    telegram_bot._handle_golive(f"/golive {wallet}")
    assert sent and "READY for live" in sent[0]


def test_golive_handler_usage_without_arg(monkeypatch):
    from src import telegram_bot
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda *a, **k: sent.append(a))
    telegram_bot._handle_golive("/golive")
    assert sent and "Usage" in sent[0][0]
