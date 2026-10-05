"""The skip rails questioned (run s-k7m2qa, the owner's third ask).

The fee-aware ceiling, the never-held exit skip, the one-row-per-episode
market-quality refusal, the fill line's break-even, the paper books' live
fee. The executor loop itself is not drivable in a test; its two seams are
asserted on the production call site text and the helpers are driven.
"""
from __future__ import annotations

import pathlib

import pytest

from src.config import CONFIG
from src.copy_trading import fee_rate, trade_store
from src.copy_trading import tiered_risk_manager as trm
from src.copy_trading.strategy_config import TierConfig
from src.models import DetectedTrade, TradeRecord

SRC = pathlib.Path(__file__).resolve().parents[1]


def _trade(price=0.89, side="BUY", size=400.0, token="TOK1"):
    # The age rail reads the wall clock, so the trade is stamped "now": the
    # test moves with the clock instead of pinning a day that will age out.
    from datetime import datetime, timezone
    return DetectedTrade(
        id=f"tx-{token}", trader_address="0x5213eb85fcd465c8927a8382f95dd2dc22306a35",
        market="Adana: Teodora Kostovic vs Dalma Galfi", side=side, size=size, price=price,
        timestamp=datetime.now(timezone.utc).isoformat(), condition_id="0xcid", token_id=token, outcome="Yes")


def _cfg(max_price=0.90):
    return TierConfig(tier="1b", enabled=True, copy_percentage=10.0, max_bet=50.0, min_bet=5.0,
                      max_total_exposure=500.0, max_price=max_price, min_price=0.0, min_trader_bet=0.0)


# --------------------------------------------------------------------------- #
# The fee-aware price ceiling
# --------------------------------------------------------------------------- #

def test_a_buy_under_the_cap_before_the_fee_and_over_it_after_is_refused(monkeypatch):
    # 0.899 on a 0.05 market: 0.05 x 0.101 = 0.50% fee, 0.9035 a dollar.
    monkeypatch.setattr(fee_rate, "fee_bps", lambda tok: 500)
    d = trm._evaluate_tiered_trade_with_state(_trade(price=0.899), "1b", trm.TierExposure(), _cfg(0.90))
    assert d.should_copy is False
    assert "0.50% fee" in d.reason and "0.9035" in d.reason and "> tier 1b max 0.9" in d.reason


def test_the_curved_fee_lets_a_buy_well_under_the_cap_through(monkeypatch):
    # 0.89 on the same market costs 0.8949: the flat-10% reading refused it.
    monkeypatch.setattr(fee_rate, "fee_bps", lambda tok: 500)
    d = trm._evaluate_tiered_trade_with_state(_trade(price=0.89), "1b", trm.TierExposure(), _cfg(0.90))
    assert "tier 1b max" not in (d.reason or "")


def test_the_same_buy_on_a_no_fee_market_passes_the_ceiling(monkeypatch):
    monkeypatch.setattr(fee_rate, "fee_bps", lambda tok: 0)
    d = trm._evaluate_tiered_trade_with_state(_trade(price=0.89), "1b", trm.TierExposure(), _cfg(0.90))
    assert "tier 1b max" not in (d.reason or "")


def test_an_unread_fee_does_not_refuse(monkeypatch):
    """A fee we could not read is not a fee of zero and not a fee of infinity:
    the plain ceiling stands and nothing else."""
    monkeypatch.setattr(fee_rate, "fee_bps", lambda tok: None)
    d = trm._evaluate_tiered_trade_with_state(_trade(price=0.89), "1b", trm.TierExposure(), _cfg(0.90))
    assert "fee" not in (d.reason or "")


def test_a_raising_fee_read_does_not_refuse_the_trade(monkeypatch):
    def boom(tok):
        raise RuntimeError("502")
    monkeypatch.setattr(fee_rate, "fee_bps", boom)
    d = trm._evaluate_tiered_trade_with_state(_trade(price=0.89), "1b", trm.TierExposure(), _cfg(0.90))
    assert "fee" not in (d.reason or "")


def test_a_sell_is_never_fee_capped(monkeypatch):
    monkeypatch.setattr(fee_rate, "fee_bps", lambda tok: pytest.fail("a SELL asked for the fee"))
    d = trm._evaluate_tiered_trade_with_state(_trade(price=0.89, side="SELL"), "1b", trm.TierExposure(), _cfg(0.90))
    assert "fee" not in (d.reason or "")


def test_the_plain_ceiling_still_fires_first(monkeypatch):
    monkeypatch.setattr(fee_rate, "fee_bps", lambda tok: pytest.fail("over the cap already; no fee read"))
    d = trm._evaluate_tiered_trade_with_state(_trade(price=0.95), "1b", trm.TierExposure(), _cfg(0.90))
    assert d.should_copy is False and "Price 0.9500 > tier 1b max 0.9" in d.reason


# --------------------------------------------------------------------------- #
# Tokens we ever bought: the never-held exit skip
# --------------------------------------------------------------------------- #

@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(trade_store, "_HISTORY_FILE", str(tmp_path / "trade-history.jsonl"))
    monkeypatch.setattr(trade_store, "_bought_tokens", None)
    yield tmp_path
    monkeypatch.setattr(trade_store, "_bought_tokens", None)


def _rec(status, side="BUY", token="TOK1"):
    return TradeRecord(timestamp="2026-10-01T05:17:01Z", trader_address="0xabc", market="m", side=side,
                       trader_size=400.0, copy_size=6.4, price=0.5, status=status, token_id=token)


def test_a_token_is_known_once_any_buy_of_ours_was_recorded(store):
    assert trade_store.token_ever_bought("TOK1") is False
    trade_store.append_trade_history(_rec("FILLED"))
    assert trade_store.token_ever_bought("TOK1") is True
    trade_store.append_trade_history(_rec("SKIPPED", token="TOK2"))
    assert trade_store.token_ever_bought("TOK2") is False, "a refused buy never bought anything"
    trade_store.append_trade_history(_rec("FILLED", side="SELL", token="TOK3"))
    assert trade_store.token_ever_bought("TOK3") is False, "a sell is not a buy"


def test_the_set_is_rebuilt_from_the_history_after_a_restart(store, monkeypatch):
    trade_store.append_trade_history(_rec("PREVIEW", token="PAPER"))
    trade_store.append_trade_history(_rec("PLACED", token="LIVE"))
    monkeypatch.setattr(trade_store, "_bought_tokens", None)
    assert trade_store.token_ever_bought("PAPER") and trade_store.token_ever_bought("LIVE")
    assert not trade_store.token_ever_bought("NEVER")


def test_a_missing_history_reads_as_nothing_bought(store):
    assert trade_store.token_ever_bought("X") is False


# --------------------------------------------------------------------------- #
# The executor's seams (call-site text; the loop is not drivable here)
# --------------------------------------------------------------------------- #

def test_the_executor_refuses_a_never_held_exit_before_asking_the_api():
    src = (SRC / "src" / "copy_trading" / "trade_executor.py").read_text()
    i = src.index('if trade.side == "SELL" and not has_position(trade.token_id):')
    j = src.index("if not token_ever_bought(trade.token_id):")
    k = src.index("syncing inventory...")
    assert i < j < k, "the never-held check must come before the inventory sync"
    assert "SELL skipped: we never held" in src


def test_a_market_quality_refusal_writes_one_skip_row_on_its_first_retry():
    src = (SRC / "src" / "copy_trading" / "trade_executor.py").read_text()
    block = src[src.index("# --- Market quality check ---"):src.index("# --- The flip gate")]
    assert "if increment_retry(trade.id) == 1:" in block
    assert '_skip_row(record_trade_history, trade, qt, f"market quality: {quality_issue}")' in block
    assert "mark_trade_as_seen" not in block, "the refusal still retries; only the record changed"


def test_the_fill_line_carries_the_break_even():
    src = (SRC / "src" / "copy_trading" / "trade_executor.py").read_text()
    assert "fee_bps=_fee" in src and "side=trade.side" in src


@pytest.mark.asyncio
async def test_the_notifier_prints_what_a_win_nets_after_the_fee(monkeypatch):
    from src.copy_trading import telegram_notifier as tn
    sent = []

    async def fake_send(text):
        sent.append(text)
        return True
    monkeypatch.setattr(tn, "_send_message", fake_send)
    await tn.TelegramNotifier().trade_filled("China Open: Safiullin vs Cobolli", 13.33, 0.48,
                                             outcome="Roman Safiullin", fee_bps=500, side="BUY")
    assert "a win nets +6.77" in sent[0] and "fee $0.17 = 2.6%" in sent[0]
    sent.clear()
    await tn.TelegramNotifier().trade_filled("m", 10.0, 0.5, side="SELL")
    assert "a win nets" not in sent[0]


# --------------------------------------------------------------------------- #
# The paper books charge the live fee, forward
# --------------------------------------------------------------------------- #

def test_the_paper_engine_charges_the_live_fee_when_it_can_read_it():
    from src.copy_trading import copy_paper
    src = (SRC / "src" / "copy_trading" / "copy_paper.py").read_text()
    assert "fee_lookup" in src and "_live = self.fee_lookup(token)" in src
    import inspect
    assert "fee_lookup" in inspect.signature(copy_paper.CopyPaperEngine.__init__).parameters


def test_the_recipes_hand_the_fee_reader_to_every_book(monkeypatch):
    from src.copy_trading import book_recipes
    monkeypatch.setattr(CONFIG, "copy_paper_costs_enabled", True)
    assert book_recipes._fee_lookup(CONFIG) is fee_rate.fee_bps
    monkeypatch.setattr(CONFIG, "copy_paper_costs_enabled", False)
    assert book_recipes._fee_lookup(CONFIG) is None
    assert "fee_lookup=_fee_lookup(cfg)" in (SRC / "src" / "copy_trading" / "book_recipes.py").read_text()
    assert "fee_lookup=_book_recipes._fee_lookup(CONFIG)" in (SRC / "main.py").read_text()


def test_the_refusal_command_and_the_daily_line_are_wired():
    tb = (SRC / "src" / "telegram_bot.py").read_text()
    assert '{"command": "refusals"' in tb and 'text.startswith("/refusals")' in tb
    ow = (SRC / "src" / "copy_trading" / "ops_watch.py").read_text()
    assert "ref = refusal_line(now)" in ow and "(tail, lag, exp, ref, zs)" in ow
