"""/wallets and set Z's door.

The leaderboard ranks by all-time net PnL; real money follows set Z, whose
gate reads the clean era at their price. The old row verdict (PROMOTE-READY
on 15 settled and positive PnL) printed READY next to wallets the gate
refuses, which is the question the owner keeps asking: "good wallets, why
not in Z?". Each row now carries the gate's own standing, from the one
evaluation the cards and the auto-admit scan run.
"""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import pytest

from src.config import CONFIG
from src.copy_trading import live_guard, live_mode, zset
from src.copy_trading import zset_candidates as zc

W1 = "0x" + "1" * 40
W2 = "0x" + "2" * 40
W3 = "0x" + "3" * 40


class _P:
    def __init__(self, spent=50.0, ideal=5.0, opened=1000.0, closed=True):
        self.spent, self.ideal_pnl = spent, ideal
        self.opened_ts, self.closed = opened, closed


def _row(cid, target, *, won=True, price=0.5, spent=20.0, opened=5000.0):
    pnl = (spent / price - spent) if won else -spent
    return {"copy_id": cid, "target": target, "condition_id": "c" + cid,
            "token_id": "t" + cid, "outcome_index": 0, "category": "sports",
            "their_price": price, "entry_price": price, "shares": spent / price,
            "spent": spent, "drag_bps": 100, "opened_ts": opened, "title": "m",
            "slug": "", "event_key": "", "flagged_by": [], "strategy": "B",
            "horizon_days": 0.0, "mark_price": 0.0, "marked_ts": 0.0,
            "unrealized_pnl": 0.0, "closed": True, "won": won, "pnl": pnl,
            "ideal_pnl": pnl, "closed_ts": opened + 3600, "exited_early": False,
            "cost_usd": 0.02, "ideal_cost_usd": 0.5}


@pytest.fixture
def books(tmp_path, monkeypatch):
    """Book B with one thin wallet, an empty book A, an era floor, isolated stores."""
    b = tmp_path / "b.jsonl"
    with open(b, "w") as f:
        f.writelines(json.dumps(_row(f"b{i}", W1, won=(i != 5), opened=5000.0 + i)) + "\n"
                     for i in range(6))
    (tmp_path / "a.jsonl").write_text("")
    (tmp_path / "ab_race_state.json").write_text(json.dumps({"era_floor_ts": 1.0}))
    for mod in (zset.promotion_state, live_guard, live_mode):
        monkeypatch.setattr(mod.CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(CONFIG, "copy_paper_b_ledger", str(b))
    monkeypatch.setattr(CONFIG, "copy_paper_ledger", str(tmp_path / "a.jsonl"))
    zset.promotion_state.clear_cache()
    yield tmp_path
    zset.promotion_state.clear_cache()


def _cand(ok, checks):
    return zc.Candidate(wallet=W1, ok=ok, gate_ready=ok, checks=checks, gate_checks=checks)


# --------------------------------------------------------------------------- #
# standing(): one phrase, membership before judgement
# --------------------------------------------------------------------------- #

def test_membership_and_eviction_come_before_the_gate_verdict():
    passing = _cand(True, [("x", True, "")])
    assert "in set Z" in zc.standing(W1, passing, in_z={W1}, evicted=set(), auto_admit=True)
    s = zc.standing(W1, passing, in_z=set(), evicted={W1}, auto_admit=True)
    assert "evicted" in s and "/zset readmit" in s
    s = zc.standing(W1, passing, in_z=set(), evicted={"*"}, auto_admit=True)
    assert "unreadable" in s and "closed" in s
    assert "no settled copies" in zc.standing(W1, None, in_z=set(), evicted=set(), auto_admit=True)


def test_a_passer_says_who_admits_it():
    passing = _cand(True, [("x", True, "")])
    assert "auto-admit" in zc.standing(W1, passing, in_z=set(), evicted=set(), auto_admit=True)
    s = zc.standing(W1, passing, in_z=set(), evicted=set(), auto_admit=False)
    assert "ZSET_AUTO_ADMIT is off" in s and "/zset candidates" in s


def test_a_refusal_names_the_failing_checks_with_their_detail():
    checks = [("≥30 settled copies", False, "12"),
              ("paper ROI ≥ +0% now", True, "+8%"),
              ("active within 14d", False, "21d ago"),
              ("promotion floor still holds", False, "conditions 5 < 8"),
              ("the other book does not contradict it", True, "")]
    s = zc.standing(W1, _cand(False, checks), in_z=set(), evicted=set(), auto_admit=True)
    assert s.startswith("gate ✗ 3/5: ")
    assert "≥30 settled copies (12)" in s and "active within 14d (21d ago)" in s
    assert "+1 more" in s
    assert "promotion floor" not in s, "only the first two fails are spelled out"
    assert "paper ROI" not in s, "a passing check is not a reason"


# --------------------------------------------------------------------------- #
# standing_map(): the real gate, per shown wallet, keyed lowercased
# --------------------------------------------------------------------------- #

def test_standing_map_runs_the_real_gate_and_skips_non_addresses(books):
    era, b, a = zc.load_books()
    zset.admit(W2, ready=True, checks=[], settled=[_P(ideal=6.0, opened=5.0)] * 30,
               era_floor=1.0, rails_supplied=True)
    st = zc.standing_map([W1.upper(), W2, W3, "(legacy)", "(unknown)", W1],
                         b, a, era=era, now=time.time(), book_corr=(0.1, 20))
    assert set(st) == {W1, W2, W3}, "keys are lowercased addresses, pseudo-wallets skipped"
    assert st[W1].startswith("gate ✗") and "settled copies" in st[W1]
    assert "in set Z" in st[W2]
    assert "no settled copies" in st[W3]


# --------------------------------------------------------------------------- #
# /wallets: the standing rides each row; the old READY verdict is gone
# --------------------------------------------------------------------------- #

def _unified():
    from src.copy_trading import pnl_unified as u
    from src.copy_trading.copy_paper import PaperPosition

    def pp(target, pnl, copy_id):
        return PaperPosition(
            copy_id=copy_id, target=target, condition_id="c", token_id="t",
            outcome_index=0, category="x", their_price=0.5, entry_price=0.5,
            shares=100, spent=50.0, drag_bps=0, opened_ts=0.0,
            flagged_by=("1b",), closed=True, won=(pnl > 0), pnl=pnl,
        )
    # 20 settled, +$400 all-time: the old verdict called this PROMOTE-READY.
    positions = [pp(W1, 20.0, f"c{i}") for i in range(20)] + [pp(W2, -15.0, "d1")]
    b = u.aggregate_system_b(positions)
    return u.build_unified([], b), [], b, 0, {"near": positions, "b": []}


def test_wallets_rows_carry_the_gate_standing_not_the_old_ready_verdict(monkeypatch):
    from src import telegram_bot as tb
    from src.copy_trading import ops_watch

    monkeypatch.setattr(tb, "_compute_unified", _unified)
    monkeypatch.setattr(zc, "load_books", lambda: (1.0, [], []))
    monkeypatch.setattr(zc, "candidates", lambda b, a, era, now, wallets=None: ([object()], [object(), object()], None))
    monkeypatch.setattr(ops_watch, "auto_admit_enabled", lambda: True)
    monkeypatch.setattr(zset, "wallets", lambda: [W2])
    seen: dict = {}

    def fake_map(wallets, b, a, *, era, now, book_corr=None, auto_admit=True):
        seen["wallets"] = list(wallets)
        seen["auto"] = auto_admit
        return {W1: "gate ✗ 2/11: ≥30 settled copies IN THE CLEAN ERA (0 clean of 20 all-time); active within 14d (never)",
                W2: "🅩 in set Z"}
    monkeypatch.setattr(zc, "standing_map", fake_map)

    sent: list = []
    with patch.object(tb, "send_message", lambda x, **k: sent.append(x)):
        tb._handle_command("/wallets")
    out = sent[-1]
    assert "PROMOTE-READY" not in out and "HOLD" not in out
    assert "Set Z</b>: 1 wallet(s) · 1 pass the gate today · 2 near misses · auto-admit on" in out
    assert "IN THE CLEAN ERA (0 clean of 20 all-time)" in out
    assert "in set Z" in out
    assert seen["auto"] is True
    assert W1 in seen["wallets"] and W2 in seen["wallets"], "every shown wallet is judged"


def test_wallets_still_renders_when_the_books_cannot_be_read(monkeypatch):
    from src import telegram_bot as tb

    monkeypatch.setattr(tb, "_compute_unified", _unified)

    def boom():
        raise OSError("disk")
    monkeypatch.setattr(zc, "load_books", boom)
    sent: list = []
    with patch.object(tb, "send_message", lambda x, **k: sent.append(x)):
        tb._handle_command("/wallets")
    out = sent[-1]
    assert "standing unavailable" in out
    assert "Top wallets: all strategies" in out and W1[:6] in out
    assert "PROMOTE-READY" not in out
