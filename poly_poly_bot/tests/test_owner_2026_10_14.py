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
    assert "ensure_env LIVE_MIN_ENTRY_PRICE 0" in src  # owner, 2026-10-15: off (was 0.35 for a day)


# ---- owner picks and the exit door (2026-10-16) ----

def test_evicting_an_owner_pick_is_reported_as_done(tmp_path, monkeypatch):
    from src.copy_trading import zset, promotion_state, owner_picks
    monkeypatch.setattr(promotion_state, "DATA_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(promotion_state, "promoted_path", lambda scope="": str(tmp_path / f"p{scope}.json"))
    monkeypatch.setattr(promotion_state, "retired_path", lambda scope="": str(tmp_path / f"r{scope}.json"))
    w = "0xd970693a3384dc762b191707a4927ac3814bbbba"
    monkeypatch.setattr(owner_picks, "hold_wallets", lambda: {w})
    assert w in zset.wallet_set(), "a pick is in Z without a promoted record"
    assert zset.evict(w, "test") is True
    assert w not in zset.wallet_set()
    assert zset.readmit(w, "test") is True
    assert w in zset.wallet_set()


def test_the_exit_door_never_evicts_an_owner_pick(monkeypatch):
    import inspect
    from src.copy_trading import zset_decay
    src = inspect.getsource(zset_decay.check)
    assert "_is_owner_pick(w)" in src
    assert src.index("_is_owner_pick(w)") < src.index("evicted = zset.evict(w, reason=reason)")
    monkeypatch.setattr(zset_decay, "_is_owner_pick", lambda w: w == "0xpick")
    assert zset_decay._is_owner_pick("0xpick") and not zset_decay._is_owner_pick("0xother")


# ---- /positions is paged (2026-10-17) ----

def test_positions_are_read_across_pages():
    import asyncio
    from src.copy_trading import inventory

    class Resp:
        def __init__(self, rows): self._rows = rows
        def raise_for_status(self): pass
        def json(self): return self._rows

    class Client:
        calls = []
        async def get(self, url, params=None):
            Client.calls.append(dict(params))
            off = params["offset"]; lim = params["limit"]
            rows = [{"asset": f"t{i}", "size": 1} for i in range(off, min(off + lim, 1203))]
            return Resp(rows)

    rows = asyncio.run(inventory.fetch_all_positions(Client(), "u", {"user": "0xp"}))
    assert len(rows) == 1203 and rows[-1]["asset"] == "t1202"
    assert [c["offset"] for c in Client.calls] == [0, 500, 1000]
    assert all(c["limit"] == 500 and c["user"] == "0xp" for c in Client.calls)


def test_a_failed_page_fails_the_whole_read():
    import asyncio
    from src.copy_trading import inventory

    class Resp:
        def __init__(self, rows, ok=True): self._rows, self._ok = rows, ok
        def raise_for_status(self):
            if not self._ok: raise RuntimeError("502")
        def json(self): return self._rows

    class Client:
        async def get(self, url, params=None):
            if params["offset"] == 0:
                return Resp([{"asset": f"t{i}"} for i in range(500)])
            return Resp([], ok=False)

    with pytest.raises(RuntimeError):
        asyncio.run(inventory.fetch_all_positions(Client(), "u", {"user": "0xp"}))


def test_the_redeemer_reads_positions_through_the_same_pager():
    import inspect
    from src.copy_trading import auto_redeemer
    assert "fetch_all_positions(client, url, params)" in inspect.getsource(auto_redeemer._fetch_redeemable_positions)


# ---- settlements: a parked row never doubles a fresh one (2026-10-17) ----

def _settle_env(tmp_path, monkeypatch):
    from src.copy_trading import ops_watch as ow
    monkeypatch.setattr(ow.CONFIG, "data_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(ow, "_p", lambda name: str(tmp_path / name))
    return ow


def test_a_parked_gone_row_is_superseded_by_the_fresh_release(tmp_path, monkeypatch):
    import json
    ow = _settle_env(tmp_path, monkeypatch)
    tok = "7" * 20
    (tmp_path / ow.PENDING_FILE).write_text(json.dumps({"rows": [
        {"token_id": tok, "cost": 5.0, "why": "gone", "ts": 1.0, "trader": "0xabc", "tier": "1b", "title": "t"}],
        "said": {}, "ts": 1.0}))
    fresh = [{"token_id": tok, "cost": 5.0, "why": "resolved", "ts": 2.0, "trader": "0xabc", "tier": "1b", "title": "t"}]
    sent = []
    out = ow.settle_released(fresh, redeemable=[{"tokenId": tok, "size": 10.0, "curPrice": 0.0, "currentValue": 0.0, "title": "t"}],
                             fetch_activity=lambda since: [], equity=100.0, stated=150.0, floor=None,
                             send=lambda *a, **k: sent.append(a), now=10.0)
    rows = [json.loads(l) for l in open(tmp_path / "ops-ledger.jsonl") if l.strip()]
    st = [r for r in rows if r.get("kind") == "settled"]
    assert len(st) == 1 and st[0]["cost"] == 5.0 and st[0]["pnl"] == -5.0, "once, at $5, not $10"
    assert out["pending"] == 0


def test_a_parked_gone_row_the_chain_lists_as_resolved_is_booked_as_a_loss(tmp_path, monkeypatch):
    import json
    ow = _settle_env(tmp_path, monkeypatch)
    tok = "8" * 20
    (tmp_path / ow.PENDING_FILE).write_text(json.dumps({"rows": [
        {"token_id": tok, "cost": 5.0, "why": "gone", "ts": 1.0, "trader": "0xabc", "tier": "1b", "title": "t"}],
        "said": {}, "ts": 1.0}))
    out = ow.settle_released([], redeemable=[{"tokenId": tok, "size": 10.0, "curPrice": 0.0, "currentValue": 0.0, "title": "t"}],
                             fetch_activity=lambda since: [], equity=100.0, stated=150.0, floor=None,
                             send=lambda *a, **k: None, now=10.0)
    rows = [json.loads(l) for l in open(tmp_path / "ops-ledger.jsonl") if l.strip()]
    st = [r for r in rows if r.get("kind") == "settled"]
    assert len(st) == 1 and st[0]["won"] is False and st[0]["pnl"] == -5.0
    assert out["pending"] == 0, "no longer parked"


# ---- price drift 7%, drift refusals on paper (2026-10-18) ----

def test_deploy_keeps_drift_tolerance_at_three_percent():
    src = open("../.github/workflows/deploy.yml", encoding="utf-8").read()
    assert "ensure_env MAX_PRICE_DRIFT_BPS 300" in src  # 7% for a day on 2026-10-18, mis-priced


def test_drift_check_uses_the_configured_tolerance(monkeypatch):
    from src.copy_trading import trade_executor as te
    monkeypatch.setattr(te.CONFIG, "max_price_drift_bps", 700)
    monkeypatch.setattr(te.CONFIG, "max_spread_bps", 10000)
    t = _trade("0xAAA"); t.price = 0.50
    assert te._check_market_quality(t, {"midpoint": 0.53, "spread_bps": 380}) is None, "6% passes at 7%"
    issue = te._check_market_quality(t, {"midpoint": 0.55, "spread_bps": 360})
    assert issue and "Price drift too high" in issue, "10% is still refused"


def test_market_quality_refusals_are_booked_on_paper():
    import inspect
    from src.copy_trading import trade_executor as te
    src = inspect.getsource(te.place_trade_orders)
    assert 'missed_paper.record(trade, f"market quality: {quality_issue}",' in src
    assert 'entry_price=(snapshot or {}).get("midpoint")' in src
    assert missed_paper.is_money_reason("market quality: Price drift too high: 597bps > 300bps")

