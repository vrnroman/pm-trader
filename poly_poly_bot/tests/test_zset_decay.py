"""Set Z's exit door (run s-k7m2qa, 2026-10-01): a member is re-read against
the gate daily and leaves on its own after DECAY_DAYS consecutive days below
it. The gate itself is faked here (it has its own tests); these tests are
about the clock, the counter, what counts, the phone, and the eviction.
"""
from __future__ import annotations

import json
import time

import pytest

from src.config import CONFIG
from src.copy_trading import ops_watch as ow, promotion_state, zset, zset_candidates as zc, zset_decay as zd

DAY = 86400.0
T0 = 1790856000.0   # 2026-10-01 11:20 UTC
W1 = "0xaaaa000000000000000000000000000000000001"
W2 = "0xbbbb000000000000000000000000000000000002"


@pytest.fixture
def env(tmp_path, monkeypatch):
    for mod in (CONFIG, ow.CONFIG, zd.CONFIG, zset.promotion_state.CONFIG):
        monkeypatch.setattr(mod, "data_dir", str(tmp_path))
    promotion_state.clear_cache()
    monkeypatch.setattr(zd, "DECAY_DAYS", 7)
    yield tmp_path
    promotion_state.clear_cache()


def _ledger(tmp_path, kind=None):
    p = tmp_path / ow.LEDGER_FILE
    rows = [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []
    return [r for r in rows if kind is None or r.get("kind") == kind]


class Cand:
    def __init__(self, checks):
        self.checks = checks
        self.ok = all(ok for _l, ok, _d in checks)


PASS = [("≥15 settled copies", True, "40"), ("paper ROI ≥ +0% now", True, "+12%"),
        ("promotion floor still holds", True, "ok"), ("active within 14d", True, "1d ago"),
        ("still positive with its best 3 copies deleted", True, "+8%"),
        ("does not lose at the prices we would really pay", True, "+4% over 30")]
FAIL_FLOOR = [c if c[0] != "promotion floor still holds" else (c[0], False, "copy ROI +4% < floor +10%") for c in PASS]
FAIL_SAMPLE = [c if not c[0].startswith("≥15") else (c[0], False, "9") for c in PASS]
FAIL_IDLE = [c if not c[0].startswith("active within") else (c[0], False, "18d ago") for c in PASS]


def _fake_gate(verdicts: dict):
    """verdicts: wallet -> checks, or wallet -> callable(now) -> checks."""
    def evaluate(w, b, a, *, era, now, book_corr):
        v = verdicts.get(w.lower())
        if v is None:
            return None
        return Cand(v(now) if callable(v) else v)
    return evaluate


def _admit(w):
    ok, _ = zset.admit(w, ready=True, checks=[("gate", True, "")],
                       settled=[type("P", (), {"spent": 50.0, "ideal_pnl": 6.0, "opened_ts": 1000.0, "closed": True})() for _ in range(30)],
                       rails_supplied=True)
    assert ok


@pytest.fixture
def gate(monkeypatch):
    def set_(verdicts):
        monkeypatch.setattr(zc, "evaluate", _fake_gate(verdicts))
        monkeypatch.setattr(zd, "seed_from_history", lambda members, **kw: {})
    return set_


def _run(members, now, send=None, **kw):
    return zd.check(members, b_positions=[], a_positions=[], era=None, now=now, send=send, **kw)


# --------------------------------------------------------------------------- #
# What counts
# --------------------------------------------------------------------------- #

def test_only_the_quality_checks_count():
    assert zd.decay_fails(FAIL_FLOOR) == [("promotion floor still holds", "copy ROI +4% < floor +10%")]
    assert zd.decay_fails(FAIL_SAMPLE) == []
    assert zd.decay_fails(FAIL_IDLE) == []
    assert zd.decay_fails(PASS) == []


def test_a_sample_or_idle_failure_does_not_start_the_clock(env, gate):
    gate({W1: FAIL_SAMPLE, W2: FAIL_IDLE})
    out = _run([W1, W2], T0)
    assert out["green"] == [W1, W2] and zd.state() == {}


# --------------------------------------------------------------------------- #
# The clock
# --------------------------------------------------------------------------- #

def test_the_first_red_day_is_said_once_and_the_days_between_are_ledger_rows(env, gate):
    gate({W1: FAIL_FLOOR})
    sent = []
    for d in range(3):
        out = _run([W1], T0 + d * DAY, send=lambda t, kb=None: sent.append(t))
        assert out["red"] == [W1]
    assert zd.state()[W1]["days"] == 3
    assert len([m for m in sent if "Below the door" in m]) == 1
    days = _ledger(env, "decay_day")
    assert [r["days"] for r in days] == [1, 2, 3]
    assert [r["push"] for r in days] == ["WALLET", None, None]
    assert "below the door 3 of 7" in zd.line_for(W1)


def test_a_second_read_on_the_same_day_changes_nothing(env, gate):
    gate({W1: FAIL_FLOOR})
    _run([W1], T0)
    _run([W1], T0 + 3600)
    _run([W1], T0 + 7200)
    assert zd.state()[W1]["days"] == 1
    assert len(_ledger(env, "decay_day")) == 1


def test_a_passing_day_resets_the_clock_and_says_so(env, gate):
    verdicts = {W1: FAIL_FLOOR}
    gate(verdicts)
    for d in range(4):
        _run([W1], T0 + d * DAY)
    verdicts[W1] = PASS
    sent = []
    out = _run([W1], T0 + 4 * DAY, send=lambda t, kb=None: sent.append(t))
    assert out["green"] == [W1] and zd.state() == {} and zd.line_for(W1) == ""
    rec = _ledger(env, "decay_recovered")
    assert len(rec) == 1 and rec[0]["days"] == 4
    assert any("Back above the door" in m for m in sent)


def test_a_flicker_never_evicts(env, gate):
    """Three days down, one up, three down: the observed flicker pattern."""
    _admit(W1)
    seq = [FAIL_FLOOR] * 3 + [PASS] + [FAIL_FLOOR] * 3
    for d, v in enumerate(seq):
        gate({W1: v})
        _run([W1], T0 + d * DAY)
    assert [w.lower() for w in zset.wallets()] == [W1]
    assert zd.state()[W1]["days"] == 3


# --------------------------------------------------------------------------- #
# The eviction
# --------------------------------------------------------------------------- #

def test_seven_days_below_the_door_evicts_through_zset(env, gate):
    _admit(W1)
    gate({W1: FAIL_FLOOR})
    sent = []
    for d in range(7):
        out = _run([W1], T0 + d * DAY, send=lambda t, kb=None: sent.append(t))
    assert out["evicted"] == [W1]
    assert zset.wallets() == []
    assert W1 in zset.evicted_set()
    reason = promotion_state.retired_map(zset.SCOPE)[W1]["reason"]
    assert "7 consecutive days" in reason and "promotion floor" in reason
    ev = _ledger(env, "decay_evict")
    assert len(ev) == 1 and ev[0]["after"] == "evicted (sticky)" and ev[0]["push"] == "WALLET"
    assert any("Left set Z on its own" in m and "7 days running" in m for m in sent)
    assert zd.state() == {}


def test_the_window_is_the_env_knob(env, gate, monkeypatch):
    monkeypatch.setattr(zd, "DECAY_DAYS", 14)
    _admit(W1)
    gate({W1: FAIL_FLOOR})
    for d in range(13):
        _run([W1], T0 + d * DAY)
    assert [w.lower() for w in zset.wallets()] == [W1]
    out = _run([W1], T0 + 13 * DAY)
    assert out["evicted"] == [W1]


def test_an_eviction_that_does_not_stick_is_said_and_the_wallet_stays_counted(env, gate, monkeypatch):
    _admit(W1)
    gate({W1: FAIL_FLOOR})
    monkeypatch.setattr(zset, "evict", lambda w, reason="": False)
    sent = []
    for d in range(7):
        out = _run([W1], T0 + d * DAY, send=lambda t, kb=None: sent.append(t))
    assert out["evicted"] == [] and out["red"] == [W1]
    assert any("EVICTION FAILED" in m for m in sent)
    assert _ledger(env, "decay_evict")[0]["after"].startswith("EVICTION FAILED")
    assert zd.state()[W1]["days"] == 7


# --------------------------------------------------------------------------- #
# The unhappy paths
# --------------------------------------------------------------------------- #

def test_an_unreadable_member_is_skipped_and_the_rest_are_read(env, gate, monkeypatch):
    def evaluate(w, b, a, *, era, now, book_corr):
        if w == W1:
            raise RuntimeError("book torn")
        return Cand(FAIL_FLOOR)
    monkeypatch.setattr(zc, "evaluate", evaluate)
    monkeypatch.setattr(zd, "seed_from_history", lambda members, **kw: {})
    out = _run([W1, W2], T0)
    assert out["skipped"] == [W1] and out["red"] == [W2]


def test_a_member_with_no_rows_in_the_book_is_not_judged(env, gate):
    gate({})
    out = _run([W1], T0)
    assert out["skipped"] == [W1] and zd.state() == {}


def test_a_corrupt_state_file_reopens_the_door_from_the_history(env, monkeypatch):
    (env / zd.STATE_FILE).write_text("{not json")
    monkeypatch.setattr(zc, "evaluate", lambda w, b, a, *, era, now, book_corr: Cand(FAIL_FLOOR))
    sent = []
    out = _run([W1], T0, send=lambda t, kb=None: sent.append(t))
    assert out["red"] == [W1]
    assert zd.state()[W1]["days"] >= 1
    assert any("exit door is open" in m for m in sent), "a torn file is a re-open, not a silent zero"


FAIL_SCALPER = [c if not c[0].startswith("still positive") else c for c in PASS] + \
    [("not a scalper at our latency", False, "scalper: 100% of exits within 10 min")]


def test_the_seed_never_backdates_a_live_only_check(env, monkeypatch):
    """The scalper rail reads today's form table on every replay day, so a
    seed that counted it handed a scalper a 14-day streak on day one. It
    counts from today instead (verifier, s-k7m2qa round 3)."""
    monkeypatch.setattr(zc, "evaluate", lambda w, b, a, *, era, now, book_corr: Cand(FAIL_SCALPER))
    sent = []
    out = _run([W1], T0, send=lambda t, kb=None: sent.append(t))
    assert out["red"] == [W1] and zd.state()[W1]["days"] == 1
    assert zd.decay_fails(FAIL_SCALPER, replayable_only=True) == []
    assert zd.decay_fails(FAIL_SCALPER) == [("not a scalper at our latency", "scalper: 100% of exits within 10 min")]


def test_the_opening_roster_shows_who_left_not_passes(env, monkeypatch):
    _admit(W1)
    monkeypatch.setattr(zc, "evaluate", lambda w, b, a, *, era, now, book_corr: Cand(FAIL_FLOOR))
    sent = []
    out = _run([W1], T0, send=lambda t, kb=None: sent.append(t))
    assert out["evicted"] == [W1]
    roster = [m for m in sent if "exit door is open" in m][0]
    assert "LEFT:" in roster and "passes the door" not in roster


def test_an_evicted_member_on_a_stale_list_is_not_counted_again(env, gate):
    _admit(W1)
    gate({W1: FAIL_FLOOR})
    for d in range(7):
        _run([W1], T0 + d * DAY)
    assert zset.wallets() == []
    sent = []
    out = _run([W1], T0 + 7 * DAY, send=lambda t, kb=None: sent.append(t))
    assert out == {"red": [], "green": [], "evicted": [], "skipped": []}
    assert sent == [] and zd.state() == {}


# --------------------------------------------------------------------------- #
# The first run: the history is on the clock
# --------------------------------------------------------------------------- #

class Pos:
    def __init__(self, target, opened, closed_ts=None, won=True):
        self.target, self.opened_ts = target, opened
        self.closed = closed_ts is not None
        self.closed_ts = closed_ts or 0.0
        self.won, self.pnl, self.spent, self.ideal_pnl = (won if self.closed else None), (1.0 if self.closed else 0.0), 10.0, 1.0


def test_the_book_as_of_reopens_rows_closed_later():
    rows = [Pos("w", 100.0, closed_ts=900.0), Pos("w", 800.0, closed_ts=900.0),
            Pos("w", 100.0, closed_ts=500.0), Pos("w", 100.0)]
    past = zd._book_as_of(rows, 600.0)
    assert len(past) == 3                      # the row opened at 800 is not there yet
    assert past[0].closed is False and past[0].won is None   # closed at 900 > 600: open again
    assert past[1].closed is True and past[1].won is True    # closed at 500: already settled
    assert rows[0].closed is True              # the live objects are untouched


def test_the_first_run_seeds_the_counter_from_the_history(env, monkeypatch):
    """A member failing for 5 days before deploy starts at 5, and today's
    read makes it 6: no fresh window on deploy."""
    def evaluate(w, b, a, *, era, now, book_corr):
        return Cand(FAIL_FLOOR if now > T0 - 5.5 * DAY else PASS)
    monkeypatch.setattr(zc, "evaluate", evaluate)
    sent = []
    out = _run([W1], T0, send=lambda t, kb=None: sent.append(t))
    assert out["red"] == [W1]
    assert zd.state()[W1]["days"] == 6
    roster = [m for m in sent if "exit door is open" in m]
    assert len(roster) == 1 and "below the door 6 of 7" in roster[0]
    assert _ledger(env, "decay_roster")[0]["days"] == {W1: 6}


def test_the_first_run_says_the_roster_once_and_names_idle_members(env, monkeypatch):
    def evaluate(w, b, a, *, era, now, book_corr):
        return Cand(FAIL_IDLE if w == W2 else PASS)
    monkeypatch.setattr(zc, "evaluate", evaluate)
    sent = []
    _run([W1, W2], T0, send=lambda t, kb=None: sent.append(t))
    _run([W1, W2], T0 + DAY, send=lambda t, kb=None: sent.append(t))
    roster = [m for m in sent if "exit door is open" in m]
    assert len(roster) == 1
    assert "passes the door (idle 18d ago)" in roster[0]


def test_a_seeded_member_already_past_the_window_leaves_on_the_first_read(env, monkeypatch):
    _admit(W1)
    monkeypatch.setattr(zc, "evaluate", lambda w, b, a, *, era, now, book_corr: Cand(FAIL_FLOOR))
    out = _run([W1], T0)
    assert out["evicted"] == [W1] and zset.wallets() == []


# --------------------------------------------------------------------------- #
# The wiring
# --------------------------------------------------------------------------- #

def test_the_exit_door_runs_in_the_guard_regardless_of_the_admit_switch(env, monkeypatch):
    """ops_admit.exit_door reads the books once with the scan and does not
    consult the auto-admit flag: the way out never depends on the way in."""
    from src.copy_trading import ops_admit
    monkeypatch.setattr(ow, "auto_admit_enabled", lambda: False)
    _admit(W1)
    monkeypatch.setattr(zc, "evaluate", lambda w, b, a, *, era, now, book_corr: Cand(FAIL_FLOOR))
    monkeypatch.setattr(zd, "seed_from_history", lambda members, **kw: {})
    assert ops_admit.scan(now=T0, books=(None, [], [])) == []
    out = ops_admit.exit_door(now=T0, books=(None, [], []))
    assert out["red"] == [W1]


def test_main_runs_the_exit_door_after_the_scan_with_the_same_books():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "main.py").read_text()
    i = src.index("ops_admit.scan(send=_send_wallet_kb, limit=admit_scan_limit, books=_books)")
    j = src.index("ops_admit.exit_door(send=_send_wallet_kb, now=_now, books=_books)")
    assert i < j


def test_zset_shows_the_counter_next_to_the_member(env, gate, monkeypatch):
    from src import telegram_bot as tb
    _admit(W1)
    gate({W1: FAIL_FLOOR})
    _run([W1], T0); _run([W1], T0 + DAY)
    sent = []
    monkeypatch.setattr(tb, "_send_chunked", lambda text: sent.append(text))
    monkeypatch.setattr(tb, "send_message", lambda *a, **k: sent.append(a[0]) or True)
    tb._handle_zset("/zset")
    text = "\n".join(sent)
    assert "below the door 2 of 7 days" in text and "promotion floor" in text
    assert "7 days below it" in text
