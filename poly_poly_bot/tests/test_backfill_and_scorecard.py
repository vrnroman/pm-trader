"""The backfill of already-paid wins and our side of the book (run s-k7m2qa,
phase 2)."""
from __future__ import annotations

import json

import pytest

from src.config import CONFIG
from src.copy_trading import ops_watch as ow, real_money as rm

W = "0x5213eb85fcd465c8927a8382f95dd2dc22306a35"
TOK = "113034430878768724272370722009970212521380904707731855345754801157534908440839"
CID = "0x97861c69"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(ow.CONFIG, "data_dir", str(tmp_path))
    return tmp_path


def _ledger(tmp_path, kind=None):
    p = tmp_path / ow.LEDGER_FILE
    rows = [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []
    return [r for r in rows if kind is None or r.get("kind") == kind]


def _deals():
    buy = rm.Deal(ts=1790831823, kind="BUY", title="China Open", shares=13.33, price=0.48, usd=-6.56,
                  condition_id=CID, asset=TOK, wallet=W)
    pay = rm.Deal(ts=1790842451, kind="PAYOUT", title="China Open", shares=13.33, usd=13.33, condition_id=CID)
    lbuy = rm.Deal(ts=1790600000, kind="BUY", title="Lost one", shares=12.0, price=0.53, usd=-6.4,
                   condition_id="0xlost", asset="555", wallet=W)
    return [buy, pay, lbuy]


def _markets():
    won = rm.MarketResult(condition_id=CID, title="China Open", wallet=W, first_buy_ts=1790831823,
                          paid_usd=6.56, paid_out_usd=13.33, sold_usd=0.0, held_usd=0.0)
    lost = rm.MarketResult(condition_id="0xlost", title="Lost one", wallet=W, first_buy_ts=1790600000,
                           paid_usd=6.4, paid_out_usd=0.0, sold_usd=0.0, held_usd=0.0)
    assert won.state == "won" and lost.state == "lost"
    return [won, lost]


def test_backfill_rows_are_the_unbooked_wins_dated_at_the_payout():
    rows = ow.backfill_rows(_deals(), _markets(), already=set())
    assert len(rows) == 1
    r = rows[0]
    assert r["token_id"] == TOK and r["wallet"] == W and r["ts"] == 1790842451
    assert r["cost"] == 6.56 and r["payout"] == 13.33


def test_a_win_with_no_followed_wallet_behind_it_is_not_a_copy():
    """The canary and the owner's own bets on the same wallet are wins, not
    copies: left out and said (verifier, s-k7m2qa round 3)."""
    hand = rm.MarketResult(condition_id="0xhand", title="United Russia", wallet="", first_buy_ts=1790600000,
                           paid_usd=50.0, paid_out_usd=0.0, sold_usd=53.33)
    deal = rm.Deal(ts=1790600000, kind="BUY", title="United Russia", shares=66.0, price=0.75, usd=-50.0,
                   condition_id="0xhand", asset="888", wallet="")
    skipped = []
    rows = ow.backfill_rows([deal], [hand], already=set(), skipped_out=skipped)
    assert rows == [] and len(skipped) == 1 and skipped[0]["pnl"] == pytest.approx(3.33, abs=0.01)


def test_a_win_the_ledger_already_booked_is_not_backfilled():
    assert ow.backfill_rows(_deals(), _markets(), already={TOK}) == []


def test_apply_backfill_writes_marked_rows_once_and_dedups_future_bookings(env):
    rows = ow.backfill_rows(_deals(), _markets(), already=set())
    assert ow.apply_backfill(rows, now=1790860000.0) == 1
    assert ow.apply_backfill(rows, now=1790860100.0) == 0
    st = _ledger(env, "settled")
    assert len(st) == 1 and st[0]["backfill"] is True and st[0]["won"] is True
    assert st[0]["pnl"] == pytest.approx(6.77, abs=0.01)
    assert st[0]["ts"] == 1790842451            # dated at the payout, not at the backfill
    assert st[0]["day"] == "2026-10-01"
    state = ow._read_json(ow._p(ow.STATE_FILE))
    assert TOK in state["settled_tokens"]
    assert "loss_streak" not in state and "day_pnl" not in state     # running state untouched
    # the live booker now refuses the same win
    out = ow.settle_released([{"token_id": TOK, "cost": 6.4, "ts": 1790831823.0, "trader": W, "tier": "1b",
                               "title": "China Open", "why": "gone"}], [],
                             fetch_activity=lambda since: [], equity=88.0, stated=80.0, floor=30.0,
                             send=None, now=1790860200.0)
    assert out["booked"] == 0 and len(_ledger(env, "settled")) == 1


def test_probation_and_the_wallet_ledger_read_the_backfilled_win(env):
    ow.probation_start(W, now=1790800000.0)
    ow.apply_backfill(ow.backfill_rows(_deals(), _markets(), already=set()), now=1790860000.0)
    trial = ow.probation_trial(W, 1790800000.0)
    assert trial["n"] == 1 and trial["won"] == 1
    led = ow.wallet_ledger(now=1790860000.0, days=30)
    assert led[0]["wallet"] == W and led[0]["won"] == 1


def test_the_member_scorecard_line_reads_our_rows_and_the_refused_twins(env):
    ow.apply_backfill(ow.backfill_rows(_deals(), _markets(), already=set()), now=1790860000.0)
    refused = {W: {"wallet": W, "n": 12, "settled": 5, "won": 3, "net_their": 4.2}}
    line = ow.wallet_scorecard_line(W, now=1790860000.0, days=30, refused=refused)
    assert "1 settled, 1W/0L, +6.77 before fee" in line and "too few to read" in line
    assert "refused 12, 5 settled twins 3W: +4 at book B's price" in line
    assert ow.wallet_scorecard_line("0xnobody", now=1790860000.0, refused=refused) == "ours 30d: no settled copies"


def test_the_z_wide_digest_line_sums_the_members_only(env, monkeypatch):
    from src.copy_trading import refusal_ledger, zset
    ow.apply_backfill(ow.backfill_rows(_deals(), _markets(), already=set()), now=1790860000.0)
    ow.receipt("settled", before="open $6.40", after="paid $0.00", detail="lost", now=1790850000.0,
               extra={"token_id": "777", "wallet": "0xoutsider", "pnl": -6.4, "won": False, "cost": 6.4})
    monkeypatch.setattr(zset, "wallets", lambda: [W])
    monkeypatch.setattr(refusal_ledger, "report", lambda **kw: {"per_wallet": {W: {"n": 3, "settled": 2, "won": 1, "net_their": -1.0},
                                                                            "0xoutsider": {"n": 9, "settled": 9, "won": 9, "net_their": 90.0}}})
    line = ow.z_scorecard_line(now=1790860000.0, days=30)
    assert "1 settled, 1W/0L, +6.77 before fee" in line
    assert "refused 3 of theirs, 2 settled twins would have netted -1 at book B's price" in line
    assert "90" not in line


def test_the_z_line_is_empty_when_nothing_settled(env, monkeypatch):
    from src.copy_trading import zset
    monkeypatch.setattr(zset, "wallets", lambda: [W])
    assert ow.z_scorecard_line(now=1790860000.0) == ""


def test_refusal_ledger_per_wallet_aggregates_at_their_price():
    from src.copy_trading import refusal_ledger as rl
    joined = [{"trader": W, "settled": True, "won": True, "their_price": 0.5},
              {"trader": W, "settled": True, "won": False, "their_price": 0.5},
              {"trader": W, "settled": False},
              {"trader": "0xo", "settled": True, "won": True, "their_price": 0.25}]
    pw = rl.per_wallet(joined, stake_usd=6.4)
    assert pw[W]["n"] == 3 and pw[W]["settled"] == 2 and pw[W]["won"] == 1
    assert pw[W]["net_their"] == pytest.approx(0.0, abs=0.01)
    assert pw["0xo"]["net_their"] == pytest.approx(6.4 * 3, abs=0.01)


def test_the_daily_line_carries_the_z_scorecard_and_the_refusal_line():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "src" / "copy_trading" / "ops_watch.py").read_text()
    assert "zs = z_scorecard_line(now)" in src and "(tail, lag, exp, ref, zs)" in src
    tb = (pathlib.Path(__file__).resolve().parents[1] / "src" / "telegram_bot.py").read_text()
    assert "ops_watch.wallet_scorecard_line(w, days=30.0, refused=_refused)" in tb


def test_the_backfill_script_is_a_dry_run_unless_told_to_apply():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "scripts" / "backfill_settled_wins.py").read_text()
    assert 'apply = "--apply" in argv' in src and "ops_watch.apply_backfill(rows)" in src
    assert src.index("dry run; pass --apply to write") < src.index("ops_watch.apply_backfill(rows)")
