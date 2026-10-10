"""The ledger books wins (run s-k7m2qa, 2026-10-01).

Until this shipped the watcher booked settlements only from rows whose token
was still in the wallet (``why == "resolved"``): a loser sitting there at $0.
A winner is paid by Polymarket in the resolution block, leaves the wallet,
and was released as ``why == "gone"`` and dropped. The ops ledger read 12
settled / 0 won while Polymarket's own rows read 32W/17L. Probation evicted
the best wallet as "0 of 2 won"; the SRE escalated a 12-loss streak twice.

These tests drive ``settle_released``, the one seam ``main.py`` calls, with
rows shaped like the real tier ledger and activity shaped like the real
Data API (``REDEEM`` rows carry no asset, only the condition; our own BUY
names the condition).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config import CONFIG
from src.copy_trading import ops_watch as ow

TOK = "113034430878768724272370722009970212521380904707731855345754801157534908440839"
CID = "0x97861c699e92693271937124caf301c6235803e388d6c168689e903871e27473"
W = "0x5213eb85fcd465c8927a8382f95dd2dc22306a35"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(ow.CONFIG, "data_dir", str(tmp_path))
    return tmp_path


def _ledger(tmp_path, kind=None):
    p = tmp_path / ow.LEDGER_FILE
    rows = [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []
    return [r for r in rows if kind is None or r.get("kind") == kind]


def _gone(ts=1790831823.0, cost=6.4, tok=TOK):
    return {"token_id": tok, "cost": cost, "ts": ts, "trader": W, "tier": "1b",
            "title": "China Open: Roman Safiullin vs Flavio Cobolli", "why": "gone"}


def _resolved(ts=1790831823.0, cost=6.4, tok="555"):
    return {"token_id": tok, "cost": cost, "ts": ts, "trader": W, "tier": "1b",
            "title": "Hangzhou Open: Daniil Medvedev vs Andrey Rublev", "why": "resolved"}


def _buy(ts=1790831823, tok=TOK, cid=CID, usdc=6.56475, oi=0):
    return {"timestamp": ts, "conditionId": cid, "type": "TRADE", "size": 13.33, "usdcSize": usdc,
            "price": 0.48, "asset": tok, "side": "BUY", "outcomeIndex": oi, "title": "China Open"}


def _redeem(ts=1790842451, cid=CID, usdc=13.33, oi=0):
    # The real row: no asset, no side, the condition, the outcome index and the cash.
    row = {"timestamp": ts, "conditionId": cid, "type": "REDEEM", "size": 13.33,
           "usdcSize": usdc, "price": 0, "asset": "", "side": "", "title": "China Open"}
    if oi is not None:
        row["outcomeIndex"] = oi
    return row


def _sell(ts=1790842451, tok=TOK, cid=CID, usdc=9.1):
    return {"timestamp": ts, "conditionId": cid, "type": "TRADE", "size": 13.33,
            "usdcSize": usdc, "price": 0.68, "asset": tok, "side": "SELL", "title": "China Open"}


# --------------------------------------------------------------------------- #
# payout_from_activity: the match
# --------------------------------------------------------------------------- #

def test_a_redeem_is_matched_through_our_own_buy():
    rows = [_buy(), _redeem()]
    assert ow.payout_from_activity(TOK, 1790831823.0, rows) == 13.33


def test_a_sell_counts_as_the_payout():
    assert ow.payout_from_activity(TOK, 1790831823.0, [_buy(), _sell()]) == 9.1


def test_a_redeem_for_another_condition_is_not_ours():
    rows = [_buy(), _redeem(cid="0xother")]
    assert ow.payout_from_activity(TOK, 1790831823.0, rows) is None


def test_a_redeem_before_the_placement_is_not_this_rows_payout():
    old = _redeem(ts=1790831823 - 2 * 86400)
    assert ow.payout_from_activity(TOK, 1790831823.0, [_buy(), old]) is None


def test_a_token_we_never_bought_on_the_api_cannot_be_attributed():
    assert ow.payout_from_activity("999", 1790831823.0, [_buy(), _redeem()]) is None


def test_both_sides_of_one_condition_do_not_share_a_payout():
    """Two followed wallets on opposite sides of one match: one REDEEM row
    for the winner. The loser's token must not read as paid (verifier,
    s-k7m2qa, finding 1)."""
    rows = [_buy(tok=TOK, oi=0), _buy(tok="999", oi=1), _redeem(oi=0, usdc=13.33)]
    assert ow.payout_from_activity(TOK, 1790831823.0, rows) == 13.33
    assert ow.payout_from_activity("999", 1790831823.0, rows) is None


def test_a_redeem_without_an_outcome_index_is_held_when_two_of_our_tokens_share_the_condition():
    rows = [_buy(tok=TOK, oi=0), _buy(tok="999", oi=1), _redeem(oi=None, usdc=13.33)]
    assert ow.payout_from_activity(TOK, 1790831823.0, rows) is None
    assert ow.payout_from_activity("999", 1790831823.0, rows) is None
    # and attributed when the token is the only one we hold on the condition
    assert ow.payout_from_activity(TOK, 1790831823.0, [_buy(tok=TOK, oi=0), _redeem(oi=None)]) == 13.33


def test_a_zero_redeem_is_a_found_loss_not_a_hold():
    """A neg-risk loser Polymarket clears for $0 is a payout row that says 0."""
    assert ow.payout_from_activity(TOK, 1790831823.0, [_buy(), _redeem(usdc=0.0)]) == 0.0


# --------------------------------------------------------------------------- #
# settle_released: the seam main.py calls
# --------------------------------------------------------------------------- #

def test_a_gone_winner_is_booked_as_a_win(env):
    out = ow.settle_released([_gone()], [], fetch_activity=lambda since: [_buy(), _redeem()],
                             equity=88.0, stated=80.0, floor=30.0, send=None, now=1790842500.0)
    assert out == {"booked": 1, "pending": 0, "activity_ok": True}
    st = _ledger(env, "settled")
    assert len(st) == 1 and st[0]["won"] is True
    assert st[0]["pnl"] == pytest.approx(13.33 - 6.4, abs=0.01)
    assert st[0]["wallet"] == W
    # The loss streak reads the win.
    assert ow._read_json(ow._p(ow.STATE_FILE)).get("loss_streak") == 0


def test_a_gone_row_without_a_payout_yet_is_held_not_booked(env):
    out = ow.settle_released([_gone()], [], fetch_activity=lambda since: [_buy()],
                             equity=88.0, stated=80.0, floor=30.0, send=None, now=1790842500.0)
    assert out["booked"] == 0 and out["pending"] == 1
    assert _ledger(env, "settled") == []
    held = _ledger(env, "settle_pending")
    assert len(held) == 1 and "left the wallet" in held[0]["detail"]
    assert ow.pending_rows()[0]["token_id"] == TOK


def test_a_held_row_is_booked_on_a_later_pass_once(env):
    ow.settle_released([_gone()], [], fetch_activity=lambda since: [_buy()],
                       equity=88.0, stated=80.0, floor=30.0, send=None, now=1790842500.0)
    # Next pass: nothing newly released, the payout row has landed.
    out = ow.settle_released([], [], fetch_activity=lambda since: [_buy(), _redeem()],
                             equity=88.0, stated=80.0, floor=30.0, send=None, now=1790842800.0)
    assert out["booked"] == 1 and out["pending"] == 0
    assert ow.pending_rows() == []
    # And a third pass with the same activity books nothing twice.
    ow.settle_released([_gone()], [], fetch_activity=lambda since: [_buy(), _redeem()],
                       equity=88.0, stated=80.0, floor=30.0, send=None, now=1790843100.0)
    assert len(_ledger(env, "settled")) == 1


def test_an_unreadable_activity_holds_every_gone_row_and_still_books_the_chain(env):
    redeemable = [{"tokenId": "555", "size": 11.0, "curPrice": 0.0, "title": "Medvedev"}]
    out = ow.settle_released([_gone(), _resolved()], redeemable, fetch_activity=lambda since: None,
                             equity=88.0, stated=80.0, floor=30.0, send=None, now=1790842500.0)
    assert out["activity_ok"] is False
    assert out["booked"] == 1 and out["pending"] == 1
    st = _ledger(env, "settled")
    assert st[0]["token_id"] == "555" and st[0]["won"] is False
    assert "unreadable" in _ledger(env, "settle_pending")[0]["after"]


def test_a_resolved_row_the_chain_list_does_not_carry_is_held_not_booked_at_zero(env):
    """The latent $0 trap (verifier, finding 5): unknown is not zero on the
    chain path either."""
    out = ow.settle_released([_resolved(tok="555")], [], fetch_activity=lambda since: [],
                             equity=88.0, stated=80.0, floor=30.0, send=None, now=1790842500.0)
    assert out["booked"] == 0 and out["pending"] == 1
    assert _ledger(env, "settled") == []


def test_booked_counts_rows_written_not_rows_offered(env):
    act = [_buy(), _redeem()]
    a = ow.settle_released([_gone()], [], fetch_activity=lambda since: act,
                           equity=88.0, stated=80.0, floor=30.0, send=None, now=1790842500.0)
    b = ow.settle_released([_gone()], [], fetch_activity=lambda since: act,
                           equity=88.0, stated=80.0, floor=30.0, send=None, now=1790842800.0)
    assert a["booked"] == 1 and b["booked"] == 0


def test_a_corrupt_pending_file_is_said_and_a_bad_said_map_does_not_raise(env):
    (env / ow.PENDING_FILE).write_text("{not json")
    assert ow.pending_rows() == []
    (env / ow.PENDING_FILE).write_text(json.dumps({"rows": [_gone()], "said": 5}))
    out = ow.settle_released([], [], fetch_activity=lambda since: [_buy()],
                             equity=88.0, stated=80.0, floor=30.0, send=None, now=1790842500.0)
    assert out["pending"] == 1


def test_a_raising_activity_reader_is_a_hold_not_a_crash(env):
    def boom(since):
        raise RuntimeError("data api 502")
    out = ow.settle_released([_gone()], [], fetch_activity=boom,
                             equity=88.0, stated=80.0, floor=30.0, send=None, now=1790842500.0)
    assert out == {"booked": 0, "pending": 1, "activity_ok": False}


def test_the_activity_is_not_read_when_nothing_left_the_wallet(env):
    calls = []
    redeemable = [{"tokenId": "555", "size": 11.0, "curPrice": 0.0, "title": "Medvedev"}]
    ow.settle_released([_resolved()], redeemable, fetch_activity=lambda since: calls.append(since) or [],
                       equity=88.0, stated=80.0, floor=30.0, send=None, now=1790842500.0)
    assert calls == []


def test_the_activity_window_starts_before_the_oldest_held_row(env):
    seen = []
    ow.settle_released([_gone(ts=1790000000.0), _gone(ts=1790500000.0, tok="777")], [],
                       fetch_activity=lambda since: seen.append(since) or [],
                       equity=88.0, stated=80.0, floor=30.0, send=None, now=1790842500.0)
    assert seen and seen[0] <= 1790000000.0 - ow.PAYOUT_MATCH_SLACK_S + 1


def test_a_held_row_is_said_once_a_day_not_every_pass(env):
    for i in range(5):
        ow.settle_released([_gone()] if i == 0 else [], [], fetch_activity=lambda since: [_buy()],
                           equity=88.0, stated=80.0, floor=30.0, send=None, now=1790842500.0 + i * 300)
    assert len(_ledger(env, "settle_pending")) == 1
    ow.settle_released([], [], fetch_activity=lambda since: [_buy()],
                       equity=88.0, stated=80.0, floor=30.0, send=None,
                       now=1790842500.0 + ow.PENDING_SAID_EVERY_S + 1)
    assert len(_ledger(env, "settle_pending")) == 2


def test_two_placements_on_one_token_share_one_payout(env):
    rows = [_gone(cost=6.4), _gone(cost=6.4)]
    ow.settle_released(rows, [], fetch_activity=lambda since: [_buy(), _redeem(usdc=26.66)],
                       equity=88.0, stated=80.0, floor=30.0, send=None, now=1790842500.0)
    st = _ledger(env, "settled")
    assert len(st) == 1 and st[0]["pnl"] == pytest.approx(26.66 - 12.8, abs=0.01)


def test_probation_sees_the_win(env):
    ow.probation_start(W, now=1790831000.0)
    ow.settle_released([_gone()], [], fetch_activity=lambda since: [_buy(), _redeem()],
                       equity=88.0, stated=80.0, floor=30.0, send=None, now=1790842500.0)
    trial = ow.probation_trial(W, 1790831000.0)
    assert trial["n"] == 1 and trial["won"] == 1


def test_main_calls_the_seam_not_the_old_booker():
    """The production call site: the guard books through settle_released,
    with the proxy wallet's activity as the reader, and the old inline
    aggregate is gone."""
    import os
    src = open(os.path.join(os.path.dirname(__file__), "..", "main.py"), encoding="utf-8").read()
    assert "ops_watch.settle_released(" in src
    assert "real_money.fetch_activity(" in src
    assert "ops_watch.aggregate_released(" not in src
    assert "ops_watch.record_settlements(" not in src
    i = src.index("rows_out=released_rows"); j = src.index("ops_watch.settle_released(")
    assert i < j, "the reconcile must release rows before the watcher books them"


def test_the_exposure_reconcile_releases_resolved_neg_risk_positions():
    """A resolved neg-risk loser is never claimed, so it stays in the wallet
    and is never "gone"; the redeemer's neg-risk-free subset never named it
    resolved either. Seven of them held the tier "full" for two days
    (2026-10-10). The reconcile reads the full resolved set."""
    src = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    i = src.index("_resolved_ids = set()")
    j = src.index("_trm.reconcile_tiered_exposure(", i)
    block = src[i:j]
    assert "for _p in (resolved or []):" in block and "redeemable" not in block.split("for _p")[1]
