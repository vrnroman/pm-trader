"""Owner, 2026-10-11: every live bet $5 flat, up to ~10 open on the ~$50 there,
and every copy refused for money kept on paper (the missed book)."""

import inspect
import json

import pytest

from src.config import CONFIG
from src.copy_trading import live_budget, missed_paper, tiered_risk_manager, trade_executor
from src.copy_trading.copy_paper import REFUNDED, PaperCopyLedger
from src.models import DetectedTrade


def _cfg_1b():
    from src.copy_trading.strategy_config import TierConfig
    return TierConfig(tier="1b", enabled=True, wallets=[], copy_percentage=5.0,
                      max_bet=25.0, min_bet=5.0, max_total_exposure=200.0,
                      max_price=0.90, min_price=0.10, min_trader_bet=100.0,
                      hold_to_settlement=False, alert_only=False)


@pytest.fixture
def fixed(monkeypatch):
    monkeypatch.setattr(CONFIG, "min_order_size_usd", 5.0)
    monkeypatch.setattr(CONFIG, "max_copies_per_market_side", 2)
    monkeypatch.setattr(CONFIG, "live_budget_usd", 80.0)
    monkeypatch.setattr(live_budget, "_balance_cache", None)
    monkeypatch.setattr(live_budget, "_open_cost_cache", None)
    monkeypatch.setattr(live_budget, "PER_COPY_FRAC", 0.08)
    monkeypatch.setattr(live_budget, "PER_COPY_ABS", 5.0)
    monkeypatch.setattr(live_budget, "EXPOSURE_ABS", 50.0)


def _equity(monkeypatch, cash, open_cost=0.0):
    monkeypatch.setattr(live_budget, "_read_balance", lambda now=None: cash)
    monkeypatch.setattr(live_budget, "_read_open_cost", lambda now=None: open_cost)


def test_a_38_dollar_wallet_trades_five_dollar_copies(fixed, monkeypatch):
    """The 2026-10-11 state: $37.56 equity, 8% = $3.00, every copy refused."""
    _equity(monkeypatch, 31.16, 6.40)
    c = live_budget.caps(live=True)
    assert c.per_copy_usd == 5.0 and c.tradeable
    assert c.exposure_usd == 37.56, "open at once never exceeds what is there"
    cfg, why = live_budget.govern_tier(_cfg_1b(), live=True)
    assert why is None and cfg.max_bet == 5.0


def test_open_at_once_is_fifty_when_the_wallet_holds_more(fixed, monkeypatch):
    _equity(monkeypatch, 70.0, 10.0)
    c = live_budget.caps(live=True)
    assert (c.per_copy_usd, c.exposure_usd) == (5.0, 50.0)


def test_every_copy_is_exactly_five_dollars(fixed, monkeypatch):
    _equity(monkeypatch, 45.0, 0.0)
    cfg, _ = live_budget.govern_tier(_cfg_1b(), live=True)
    monkeypatch.setattr(tiered_risk_manager, "can_spend", lambda amt: (True, ""))
    for their_usd in (300.0, 1000.0, 50000.0):  # 5% of each is $15 to $2,500
        t = DetectedTrade(id="x", trader_address="0xa", timestamp="2099-01-01T00:00:00Z",
                          market="m", token_id="t", side="BUY", size=their_usd, price=0.5)
        d = tiered_risk_manager._evaluate_tiered_trade_with_state(
            t, "1b", tiered_risk_manager.TierExposure(), cfg)
        assert d.should_copy and d.copy_size == 5.0


def test_the_tenth_copy_fits_and_the_eleventh_is_exposure_full(fixed, monkeypatch):
    _equity(monkeypatch, 10.0, 45.0)  # $55 equity, $50 cap
    cfg, _ = live_budget.govern_tier(_cfg_1b(), live=True)
    monkeypatch.setattr(tiered_risk_manager, "can_spend", lambda amt: (True, ""))
    t = DetectedTrade(id="x", trader_address="0xa", timestamp="2099-01-01T00:00:00Z",
                      market="m", token_id="t", side="BUY", size=300.0, price=0.5)
    ok = tiered_risk_manager._evaluate_tiered_trade_with_state(
        t, "1b", tiered_risk_manager.TierExposure(open_total=45.0), cfg)
    full = tiered_risk_manager._evaluate_tiered_trade_with_state(
        t, "1b", tiered_risk_manager.TierExposure(open_total=50.0), cfg)
    assert ok.should_copy and ok.copy_size == 5.0
    assert not full.should_copy and missed_paper.is_money_reason(full.reason)


def test_the_fractions_still_rule_when_the_dollars_are_unset(fixed, monkeypatch):
    monkeypatch.setattr(live_budget, "PER_COPY_ABS", None)
    monkeypatch.setattr(live_budget, "EXPOSURE_ABS", None)
    _equity(monkeypatch, 31.16, 6.40)
    c = live_budget.caps(live=True)
    assert c.per_copy_usd == 3.0 and not c.tradeable


def test_deploy_sets_five_dollars_and_fifty_open():
    src = open("../.github/workflows/deploy.yml", encoding="utf-8").read()
    assert "ensure_env LIVE_PER_COPY_USD 5" in src
    assert "ensure_env LIVE_EXPOSURE_USD 50" in src


# ---- the missed book ----

@pytest.fixture
def book(tmp_path, monkeypatch):
    p = tmp_path / "missed.jsonl"
    monkeypatch.setenv("MISSED_PAPER_LEDGER", str(p))
    monkeypatch.setenv("LIVE_PER_COPY_USD", "5")
    return p


def _trade(i="t1", token="tok", price=0.4, side="BUY", who="0xAbC"):
    return DetectedTrade(id=i, trader_address=who, timestamp="2026-10-11T00:00:00Z",
                         market="Will X win?", condition_id="0xcond", token_id=token,
                         side=side, size=300.0, price=price)


@pytest.mark.parametrize("reason,money", [
    ("bankroll governor: per copy $3.00 (8% of $38) is under the $5 order minimum", True),
    ("Tier 1b exposure full: remaining=$2.00 < min_bet=$5.00", True),
    ("cash on chain $3.10 is under the $5.00 copy", True),
    ("disarmed: the arm is off", True),
    ("Daily spend cap reached: $54.00 >= $54.00", True),
    ("Trader bet $50.00 < min_trader_bet $100.00 for tier 1b (the global floor)", False),
    ("Price 0.9500 > tier 1b max 0.9", False),
    ("Trade too old: 3.0h > 2h", False),
])
def test_only_money_refusals_count_as_missed(reason, money):
    assert missed_paper.is_money_reason(reason) is money


def test_a_refused_buy_is_booked_at_five_dollars_their_price(book):
    assert missed_paper.record(_trade(), "Tier 1b exposure full", now=100.0)
    p = PaperCopyLedger(str(book)).positions["t1-tok"]
    assert (p.spent, p.entry_price, p.their_price, p.shares) == (5.0, 0.4, 0.4, 12.5)
    assert p.target == "0xabc" and p.opened_ts == 100.0 and not p.closed
    assert "exposure full" in p.slug
    assert not missed_paper.record(_trade(), "again"), "one row per trade"


def test_sells_and_bad_prices_are_not_booked(book):
    assert not missed_paper.record(_trade(side="SELL"), "exposure full")
    assert not missed_paper.record(_trade(price=0.0), "exposure full")
    assert not missed_paper.record(_trade(price=1.0), "exposure full")
    assert not book.exists()


def test_no_more_copies_of_one_side_than_live_would_take(book):
    for i in range(4):
        missed_paper.record(_trade(i=f"t{i}"), "exposure full", max_per_token=2)
    assert len(PaperCopyLedger(str(book)).positions) == 2


def test_a_broken_ledger_never_raises_into_the_executor(book):
    book.write_text("not json\n")
    assert missed_paper.record(_trade(), "exposure full") is False


def _market(winner_idx=None, refund=False, closed=True):
    prices = ["0.5", "0.5"] if refund else ["1", "0"] if winner_idx == 0 else ["0", "1"]
    return {"closed": closed, "outcomePrices": json.dumps(prices),
            "clobTokenIds": json.dumps(["tokA", "tokB"])}


def test_settle_books_wins_losses_and_refunds(book):
    missed_paper.record(_trade(i="w", token="tokA", price=0.4), "exposure full", now=1.0)
    missed_paper.record(_trade(i="l", token="tokB", price=0.6), "exposure full", now=2.0)
    assert missed_paper.settle(now=10.0, fetch=lambda cid: _market(winner_idx=0)) == 2
    led = PaperCopyLedger(str(book))
    w, l = led.positions["w-tokA"], led.positions["l-tokB"]
    assert w.won is True and w.pnl == pytest.approx(12.5 - 5.0)
    assert l.won is False and l.pnl == pytest.approx(-5.0)
    s = missed_paper.summary()
    assert (s["settled"], s["won"]) == (2, 1) and s["pnl"] == pytest.approx(2.5)
    assert any("ROI" in x for x in missed_paper.summary_lines())


def test_settle_refund_and_open_markets(book):
    missed_paper.record(_trade(i="r", token="tokA", price=0.4), "exposure full")
    assert missed_paper.settle(fetch=lambda cid: None) == 0, "unresolved stays open"
    assert missed_paper.settle(fetch=lambda cid: _market(refund=True)) == 1
    p = PaperCopyLedger(str(book)).positions["r-tokA"]
    assert p.refunded and p.pnl == pytest.approx(12.5 * 0.5 - 5.0)
    assert REFUNDED == -1


def test_the_executor_books_every_money_refusal():
    src = inspect.getsource(trade_executor.place_trade_orders)
    assert "missed_paper.is_money_reason(decision.reason)" in src
    assert "missed_paper.record(trade, _why_c)" in src
    assert 'missed_paper.record(trade, "disarmed: the arm is off")' in src
    import main
    assert "missed_paper.settle()" in inspect.getsource(main._live_guard_loop)


def test_by_day_and_the_winning_streak(book):
    day = 86400.0
    missed_paper.record(_trade(i="a", token="tokA", price=0.4), "exposure full", now=1.0 * day)
    missed_paper.record(_trade(i="b", token="tokA", price=0.4), "exposure full", now=2.0 * day)
    missed_paper.record(_trade(i="c", token="tokB", price=0.6), "exposure full", now=3.0 * day)
    led = PaperCopyLedger(str(book))
    led.positions["a-tokA"].realize(True, now=1.5 * day)   # day 1 +
    led.positions["b-tokA"].realize(True, now=2.5 * day)   # day 2 +
    led.positions["c-tokB"].realize(False, now=3.5 * day)  # day 3 -
    led.save()
    days = missed_paper.by_day()
    assert [d for d, _ in days] == ["1970-01-02", "1970-01-03", "1970-01-04"]
    assert days[0][1] == (1, 1, 7.5) and days[2][1] == (1, 0, -5.0)
    assert missed_paper.winning_streak(days) == 0, "a losing last day resets"
    assert missed_paper.winning_streak(days[:2]) == 2
    lines = missed_paper.summary_lines()
    assert any("winning days in a row: 0" in x for x in lines)
    assert any("1970-01-02: 1 settled, 1 won, $+7.50" in x for x in lines)
