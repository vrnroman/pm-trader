"""Owner, 2026-10-14: 0x5213 out, at most 3 open copies per wallet, no equity floor."""

import pytest

from src.config import CONFIG
from src.copy_trading import live_budget, live_guard, missed_paper, tiered_risk_manager as trm
from src.models import DetectedTrade


def _cfg_1b():
    from src.copy_trading.strategy_config import TierConfig
    return TierConfig(tier="1b", enabled=True, wallets=[], copy_percentage=5.0,
                      max_bet=5.0, min_bet=5.0, max_total_exposure=50.0,
                      max_price=0.90, min_price=0.10, min_trader_bet=100.0,
                      hold_to_settlement=False, alert_only=False)


def _trade(who="0xAAA", tok="t9"):
    return DetectedTrade(id="x", trader_address=who, timestamp="2099-01-01T00:00:00Z",
                         market="m", token_id=tok, side="BUY", size=300.0, price=0.5)


def _exposure(*traders):
    return trm.TierExposure(placements=[
        {"token_id": f"t{i}", "cost": 5.0, "ts": 1.0, "trader": t.lower(), "title": ""}
        for i, t in enumerate(traders)])


@pytest.fixture
def three(monkeypatch):
    monkeypatch.setenv("LIVE_MAX_OPEN_PER_WALLET", "3")
    monkeypatch.setattr(trm, "can_spend", lambda amt: (True, ""))


def test_the_fourth_open_copy_of_one_wallet_is_refused(three):
    exp = _exposure("0xAAA", "0xaaa", "0xAAA", "0xBBB")
    d = trm._evaluate_tiered_trade_with_state(_trade("0xaaa"), "1b", exp, _cfg_1b())
    assert not d.should_copy and "wallet slots full: 3 of 3" in d.reason
    assert missed_paper.is_money_reason(d.reason), "booked on paper so the cap can be judged"


def test_another_wallet_still_gets_a_slot(three):
    exp = _exposure("0xAAA", "0xAAA", "0xAAA")
    d = trm._evaluate_tiered_trade_with_state(_trade("0xBBB"), "1b", exp, _cfg_1b())
    assert d.should_copy and d.copy_size == 5.0


def test_two_open_leaves_room_for_a_third(three):
    exp = _exposure("0xAAA", "0xAAA")
    d = trm._evaluate_tiered_trade_with_state(_trade("0xAAA"), "1b", exp, _cfg_1b())
    assert d.should_copy


def test_sells_are_never_blocked_by_the_wallet_cap(three):
    exp = _exposure("0xAAA", "0xAAA", "0xAAA")
    t = _trade("0xAAA"); t.side = "SELL"
    d = trm._evaluate_tiered_trade_with_state(t, "1b", exp, _cfg_1b())
    assert "wallet slots full" not in (d.reason or "")


def test_zero_switches_the_cap_off(monkeypatch):
    monkeypatch.setenv("LIVE_MAX_OPEN_PER_WALLET", "0")
    monkeypatch.setattr(trm, "can_spend", lambda amt: (True, ""))
    exp = _exposure(*["0xAAA"] * 6)
    d = trm._evaluate_tiered_trade_with_state(_trade("0xAAA"), "1b", exp, _cfg_1b())
    assert d.should_copy


def test_the_wallet_cap_defaults_to_three(monkeypatch):
    monkeypatch.delenv("LIVE_MAX_OPEN_PER_WALLET", raising=False)
    assert trm.max_open_per_wallet() == 3
    monkeypatch.setenv("LIVE_MAX_OPEN_PER_WALLET", "junk")
    assert trm.max_open_per_wallet() == 3


# ---- no floor ----

def test_floor_off_means_no_floor_and_the_guard_never_trips_on_equity(monkeypatch):
    monkeypatch.setattr(CONFIG, "live_budget_usd", 80.0)
    monkeypatch.setattr(live_budget, "FLOOR_OFF", True)
    monkeypatch.setattr(live_budget, "FLOOR_ABS", 10.0)
    assert live_budget.floor_usd() is None
    fired, why = live_guard.should_self_disarm(equity_usd=3.0, floor_usd=live_budget.floor_usd())
    assert fired is False, "no floor: $3 of equity does not disarm"
    fired, why = live_guard.should_self_disarm(equity_usd=3.0, floor_usd=10.0)
    assert fired is True and "under the floor" in why


def test_floor_off_is_explicit_not_a_zero(monkeypatch):
    monkeypatch.setattr(CONFIG, "live_budget_usd", 80.0)
    monkeypatch.setattr(live_budget, "FLOOR_OFF", False)
    monkeypatch.setattr(live_budget, "FLOOR_ABS", None)
    assert live_budget.floor_usd() == 56.0, "unset or 0 keeps the fraction floor; only 'off' removes it"


def test_deploy_turns_the_floor_off_caps_wallets_and_drops_0x5213():
    src = open("../.github/workflows/deploy.yml", encoding="utf-8").read()
    assert "ensure_env LIVE_FLOOR_USD off" in src
    assert "ensure_env LIVE_MAX_OPEN_PER_WALLET 3" in src
    hold = [l for l in src.splitlines() if "ensure_env LIVE_HOLD_WALLETS" in l][0]
    assert "0x5213eb85" not in hold and "0x9f15613e" in hold


# ---- no entry under 0.35 ----

def _priced(price, side="BUY"):
    t = _trade("0xCCC"); t.price = price; t.side = side
    return t


def test_a_buy_under_35_cents_is_refused(monkeypatch):
    monkeypatch.setenv("LIVE_MIN_ENTRY_PRICE", "0.35")
    monkeypatch.setattr(trm, "can_spend", lambda amt: (True, ""))
    d = trm._evaluate_tiered_trade_with_state(_priced(0.30), "1b", _exposure(), _cfg_1b())
    assert not d.should_copy and "entry under 0.35" in d.reason
    assert missed_paper.is_money_reason(d.reason), "kept on paper so the rule can be judged"
    d = trm._evaluate_tiered_trade_with_state(_priced(0.35), "1b", _exposure(), _cfg_1b())
    assert d.should_copy, "0.35 itself is allowed"


def test_a_sell_under_35_cents_is_still_an_exit(monkeypatch):
    monkeypatch.setenv("LIVE_MIN_ENTRY_PRICE", "0.35")
    d = trm._evaluate_tiered_trade_with_state(_priced(0.30, "SELL"), "1b", _exposure(), _cfg_1b())
    assert "entry under" not in (d.reason or "")


def test_entry_floor_defaults_to_35_and_zero_disables(monkeypatch):
    monkeypatch.delenv("LIVE_MIN_ENTRY_PRICE", raising=False)
    assert trm.min_entry_price() == 0.35
    monkeypatch.setenv("LIVE_MIN_ENTRY_PRICE", "0")
    monkeypatch.setattr(trm, "can_spend", lambda amt: (True, ""))
    d = trm._evaluate_tiered_trade_with_state(_priced(0.12), "1b", _exposure(), _cfg_1b())
    assert "entry under" not in (d.reason or "")
    src = open("../.github/workflows/deploy.yml", encoding="utf-8").read()
    assert "ensure_env LIVE_MIN_ENTRY_PRICE 0.35" in src
