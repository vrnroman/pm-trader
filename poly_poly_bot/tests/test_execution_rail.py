"""The execution rail, the observer's coverage, the per-wallet floor and the
clean stop (run s-wo3xsp, 2026-09-26: the owner's rulings on his doc).

The through-line: real money fills after our lag, paper book B at the
target's price. The gap is the one thing that has hurt real money, so the
Z door now judges it per copy at the observer's own quotes and says which
evidence answered. Everything here drives the real entry points (the
candidates gate, ``zset.admit``, the observer callback, the live floor
lookup) and checks the rendered result, never a helper's kwargs.
"""
from __future__ import annotations

import ast
import json
import time

import pytest

from src.config import CONFIG
from src.copy_trading import live_guard, live_mode, shadow_quote, zset
from src.copy_trading import zset_candidates as zc

W1 = "0x" + "a" * 40
W2 = "0x" + "b" * 40
Z1 = "0x" + "c" * 40


class _P:
    """A settled book-B position: copy_id carries the quote match."""

    def __init__(self, cid, target, *, price=0.5, spent=20.0, won=True, opened=5000.0):
        self.copy_id, self.target = cid, target
        self.their_price, self.entry_price, self.spent = price, price, spent
        self.shares = spent / price
        self.pnl = (spent / price - spent) if won else -spent
        self.ideal_pnl, self.won = self.pnl, won
        self.opened_ts, self.closed_ts, self.closed = opened, opened + 3600, True
        self.exited_early, self.cost_usd, self.category = False, 0.02, "sports"
        self.condition_id, self.token_id, self.outcome_index = "c" + cid, "t" + cid, 0


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    for mod in (zset.promotion_state, live_guard, live_mode, shadow_quote):
        monkeypatch.setattr(mod.CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    zset.promotion_state.clear_cache()
    zc.clear_quotes_cache()
    shadow_quote.set_priority_provider(None)
    yield tmp_path
    zset.promotion_state.clear_cache()
    zc.clear_quotes_cache()
    shadow_quote.set_priority_provider(None)


# --------------------------------------------------------------------------- #
# execution_check: the slice when it covers the wallet, book A while thin
# --------------------------------------------------------------------------- #

def test_the_slice_refuses_a_wallet_that_loses_at_real_quotes():
    ok, detail, rail = zset.execution_check(-0.138, 31, 0.40, 20)
    assert ok is False and rail == zset.RAIL_SLICE
    assert "-14% at real quotes over 31 matched" in detail, detail
    assert "book" not in detail, "book A's opinion is not consulted once the slice covers the wallet"


def test_a_thin_slice_falls_back_to_book_a_and_says_so():
    ok, detail, rail = zset.execution_check(0.30, 9, -0.20, 15)
    assert ok is False and rail == zset.RAIL_BOOK_A, "book A contradicts, the slice is too thin to overrule it"
    assert detail.startswith("slice thin (9 matched, needs 15)"), detail
    ok2, detail2, rail2 = zset.execution_check(None, 0, None, 0)
    assert ok2 is True and rail2 == zset.RAIL_BOOK_A and "not enough to contradict" in detail2
    assert zset.execution_label(rail) == zset.BOOK_A_LABEL
    assert zset.execution_label(zset.RAIL_SLICE) == zset.SLICE_LABEL


def test_the_slice_passes_a_wallet_that_makes_money_at_real_quotes_over_a_contradicting_a():
    ok, _detail, rail = zset.execution_check(0.05, 40, -0.30, 25)
    assert ok is True and rail == zset.RAIL_SLICE


# --------------------------------------------------------------------------- #
# The gate: evaluate() and admit() read the slice from the observer's log
# --------------------------------------------------------------------------- #

def _rows(target, n, *, won_every=True):
    return [_P(f"{target[:6]}{i}", target, won=(won_every or i % 2 == 0), opened=5000.0 + i)
            for i in range(n)]


def _quotes_losing(positions, *, our_price):
    """A quote for every copy at a price that turns each win into a loss."""
    return {p.copy_id: our_price for p in positions}


def test_evaluate_refuses_on_the_slice_and_the_card_names_the_rail(monkeypatch):
    monkeypatch.setattr(CONFIG, "copy_golive_min_settled", 15)
    b = _rows(W1, 20)
    # Their price 0.5, ours 0.99: every winning copy pays 1/0.99 - 1 per dollar,
    # a rounding error, and the losing ones are the same loss -> negative slice.
    quotes = {p.copy_id: 0.99 for p in b[:10]} | {p.copy_id: 0.5 for p in b[10:]}
    for p in b[10:]:
        p.won = False
        p.pnl = p.ideal_pnl = -p.spent
    c = zc.evaluate(W1, b, [], era=1.0, now=time.time(), book_corr=None, quotes=quotes)
    assert c is not None and c.real_n == 20 and c.exec_rail == zset.RAIL_SLICE
    assert c.real_roi is not None and c.real_roi < 0
    labels = {lab: ok for lab, ok, _ in c.checks}
    assert labels[zset.SLICE_LABEL] is False and zset.BOOK_A_LABEL not in labels
    assert c.ok is False
    # The card and the standing say which rail answered.
    card = zc.render_card(c, rq=zc.real_quote_slice(W1, b, quotes, 1.0), pen=None,
                          ex=zc.exits_share(c.settled, 1.0), slices=("", ""),
                          now=time.time(), in_z=False, esc=lambda x: x)
    assert "execution rail: the real-quote slice" in card
    failed = [lab for lab, ok, _ in c.checks if not ok]
    assert zset.SLICE_LABEL in failed and zset.BOOK_A_LABEL not in failed, failed


def test_evaluate_with_a_thin_slice_judges_by_book_a_and_the_card_says_thin(monkeypatch):
    monkeypatch.setattr(CONFIG, "copy_golive_min_settled", 15)
    b = _rows(W1, 20)
    quotes = {p.copy_id: 0.99 for p in b[:5]}          # 5 matched: thin
    c = zc.evaluate(W1, b, [], era=1.0, now=time.time(), book_corr=None, quotes=quotes)
    assert c.real_n == 5 and c.exec_rail == zset.RAIL_BOOK_A
    labels = {lab: (ok, det) for lab, ok, det in c.checks}
    assert zset.BOOK_A_LABEL in labels and labels[zset.BOOK_A_LABEL][0] is True
    assert labels[zset.BOOK_A_LABEL][1].startswith("slice thin (5 matched, needs 15)")
    card = zc.render_card(c, rq=zc.real_quote_slice(W1, b, quotes, 1.0), pen=None,
                          ex=zc.exits_share(c.settled, 1.0), slices=("", ""),
                          now=time.time(), in_z=False, esc=lambda x: x)
    assert "execution rail: book A (slice thin, 5 of 15 matched)" in card


def test_admit_refuses_on_the_slice_even_when_book_a_agrees():
    b = _rows(W1, 20)
    ok, checks = zset.admit(W1, ready=True, checks=[], settled=b, era_floor=1.0,
                            other_book_roi=0.40, other_book_n=30,
                            real_roi=-0.05, real_n=25, rails_supplied=True)
    assert ok is False
    failed = {lab: det for lab, good, det in checks if not good}
    assert zset.SLICE_LABEL in failed and "-5% at real quotes over 25 matched" in failed[zset.SLICE_LABEL]
    assert W1 not in zset.wallet_set()


def test_admit_without_a_slice_is_judged_by_book_a_not_waved_through():
    b = _rows(W1, 20)
    ok, checks = zset.admit(W1, ready=True, checks=[], settled=b, era_floor=1.0,
                            other_book_roi=-0.30, other_book_n=30, rails_supplied=True)
    assert ok is False, "no slice supplied means thin, and book A contradicts"
    failed = [lab for lab, good, _ in checks if not good]
    assert zset.BOOK_A_LABEL in failed


def test_the_scan_and_the_seed_hand_the_slice_to_admit(tmp_path, monkeypatch):
    """The production call sites, not a helper: zset_candidates.admit passes
    the evaluated slice into zset.admit, so a wallet losing at real quotes
    is refused at the tap and at the scan."""
    monkeypatch.setattr(CONFIG, "copy_golive_min_settled", 15)
    monkeypatch.setattr(CONFIG, "copy_golive_min_roi", 0.0)
    b = _rows(W1, 20)
    for p in b[10:]:
        p.won = False
        p.pnl = p.ideal_pnl = -p.spent
    # Write the observer's log so load_quotes() reads the real file.
    for p in b:
        shadow_quote.record({"copy_id": p.copy_id, "target": W1, "token_id": p.token_id,
                             "their_price": 0.5, "our_price": 0.99 if p.won else 0.5,
                             "detected_at": p.opened_ts, "quote_lag_s": 1.0,
                             "penalty_bps": 100, "notify_latency_s": 5})
    zc.clear_quotes_cache()
    ok, checks, cand = zc.admit(W1, era=1.0, b_positions=b, a_positions=[], now=time.time())
    assert cand is not None and cand.exec_rail == zset.RAIL_SLICE and cand.real_n == 20
    assert ok is False
    assert any(lab == zset.SLICE_LABEL and not good for lab, good, _ in checks)
    src = open("scripts/seed_zset.py", encoding="utf-8").read()
    assert "real_roi=rq.get(\"real_roi\")" in src and "real_n=int(rq.get(\"n_matched\")" in src


def test_an_unreadable_quote_log_is_a_thin_slice_never_a_pass(monkeypatch, caplog):
    def boom():
        raise OSError("disk")
    monkeypatch.setattr(shadow_quote, "load_rows", boom)
    zc.clear_quotes_cache()
    assert zc.load_quotes() == {}
    assert any("real-quote log unreadable" in r.getMessage() for r in caplog.records)


def test_load_quotes_is_read_once_a_minute(monkeypatch):
    calls = {"n": 0}

    def rows():
        calls["n"] += 1
        return [{"copy_id": "q", "our_price": 0.6, "quote_lag_s": 1.0, "detected_at": 1.0}]
    monkeypatch.setattr(shadow_quote, "load_rows", rows)
    zc.clear_quotes_cache()
    zc.load_quotes(now=100.0)
    zc.load_quotes(now=130.0)
    assert calls["n"] == 1
    zc.load_quotes(now=100.0 + zc.QUOTES_TTL_S + 1)
    assert calls["n"] == 2


# --------------------------------------------------------------------------- #
# The observer: env cap, set Z first, lower books on a budget, coverage rows
# --------------------------------------------------------------------------- #

def _observer(monkeypatch, cap):
    monkeypatch.setattr(shadow_quote, "MAX_SAMPLES_PER_SWEEP", cap)
    queued = []
    monkeypatch.setattr(shadow_quote, "quote_once", lambda c, t, p: None)
    monkeypatch.setattr(shadow_quote, "record_unquotable", lambda t, reason="": queued.append(t["copy_id"]))
    observer, stop = shadow_quote.make_observer(lambda: object())
    return observer, stop, queued


def test_set_z_and_the_near_misses_are_quoted_first_when_a_sweep_exceeds_the_cap(monkeypatch):
    shadow_quote.set_priority_provider(lambda: {Z1})
    observer, stop, queued = _observer(monkeypatch, cap=2)
    try:
        observer([{"copy_id": "r1", "target": W1}, {"copy_id": "r2", "target": W2},
                  {"copy_id": "z1", "target": Z1.upper()}])
        deadline = time.time() + 3
        while len(queued) < 2 and time.time() < deadline:
            time.sleep(0.05)
    finally:
        stop()
    assert queued[0] == "z1", f"the set-Z trade is at the head of the queue: {queued}"
    assert len(queued) == 2 and "r2" not in queued
    rows = shadow_quote.coverage_rows()
    assert rows and rows[-1]["detected"] == 3 and rows[-1]["queued"] == 2
    assert rows[-1]["dropped"] == 1 and rows[-1]["priority"] == 1 and rows[-1]["cap"] == 2


def test_a_lower_book_rides_the_same_observer_on_its_own_budget_and_a_zero_budget_is_off(monkeypatch):
    observer, stop, queued = _observer(monkeypatch, cap=40)
    try:
        b150 = shadow_quote.budgeted(observer, 1, "b150")
        b150([{"copy_id": "s1", "target": W1}, {"copy_id": "s2", "target": W1}])
        # The primary sees the same first trade: quoted once, not twice.
        observer([{"copy_id": "s1", "target": W1}, {"copy_id": "p1", "target": W2}])
        deadline = time.time() + 3
        while len(queued) < 2 and time.time() < deadline:
            time.sleep(0.05)
    finally:
        stop()
    assert sorted(queued) == ["p1", "s1"], queued
    books = {r["book"]: r for r in shadow_quote.coverage_rows()}
    assert books["b150"]["cap"] == 1 and books["b150"]["dropped"] == 1
    assert books["primary"]["already"] == 1, "the trade the lower book already queued is counted, not re-quoted"
    assert shadow_quote.budgeted(observer, 0, "b100") is None
    assert shadow_quote.budgeted(None, 10, "b100") is None
    line = shadow_quote.coverage_line()
    assert "b150: 1 quoted of 2 new, 1 dropped at the cap" in line and "primary: 1 quoted of 1 new" in line


def test_a_trade_a_lower_book_dropped_at_its_budget_is_still_quoted_by_the_primary(monkeypatch):
    """The verifier's reproduction (s-wo3xsp): b150 sweeps first with a budget
    of 1 over two trades; the primary, with room for forty, must quote the
    second, not read it as already seen."""
    observer, stop, queued = _observer(monkeypatch, cap=40)
    try:
        b150 = shadow_quote.budgeted(observer, 1, "b150")
        b150([{"copy_id": "x1", "target": W1}, {"copy_id": "x2", "target": W1}])
        observer([{"copy_id": "x1", "target": W1}, {"copy_id": "x2", "target": W1}])
        deadline = time.time() + 3
        while len(queued) < 2 and time.time() < deadline:
            time.sleep(0.05)
    finally:
        stop()
    assert sorted(queued) == ["x1", "x2"], queued
    books = {r["book"]: r for r in shadow_quote.coverage_rows()}
    assert books["b150"]["dropped"] == 1 and books["primary"]["queued"] == 1 and books["primary"]["already"] == 1


def test_the_receipt_scripts_run_as_plain_files_too(tmp_path):
    import subprocess
    import sys as _sys
    for name in ("rail_swap_receipt", "floor_truth_receipt"):
        r = subprocess.run([_sys.executable, "-c",
                            f"import runpy, sys; sys.argv=['x','--help']; runpy.run_path('scripts/{name}.py', run_name='__main__')"],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0 and "--out" in r.stdout, (name, r.stdout[-300:], r.stderr[-300:])


def test_the_cap_and_the_lower_budget_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("SHADOW_MAX_SAMPLES_PER_SWEEP", "75")
    monkeypatch.setenv("SHADOW_LOWER_BOOK_BUDGET", "0")
    assert shadow_quote._env_int("SHADOW_MAX_SAMPLES_PER_SWEEP", 40) == 75
    assert shadow_quote._env_int("SHADOW_LOWER_BOOK_BUDGET", 10) == 10, "0 is not a cap; the default stands for the cap helper"
    monkeypatch.setenv("SHADOW_MAX_SAMPLES_PER_SWEEP", "banana")
    assert shadow_quote._env_int("SHADOW_MAX_SAMPLES_PER_SWEEP", 40) == 40


def test_main_wires_the_priority_and_the_lower_books():
    src = open("main.py", encoding="utf-8").read()
    assert "shadow_quote.set_priority_provider(zset_candidates.priority_wallets)" in src
    assert "def _lower_book_observer(book_id: str):" in src
    assert "shadow_quote.budgeted(_get_shadow_observer(), shadow_quote.LOWER_BOOK_BUDGET, book_id)" in src


def test_priority_wallets_is_z_plus_the_last_scan(monkeypatch):
    monkeypatch.setattr(zset, "wallet_set", lambda: {Z1})
    zc._near_door.clear()
    zc._near_door.update({W1})
    assert zc.priority_wallets() == {Z1, W1}


# --------------------------------------------------------------------------- #
# The per-wallet floor: the row, the choice, the record, the switch
# --------------------------------------------------------------------------- #

def _acts(wallet, bets):
    """Activity rows: (usd, price, won, ts) -> a BUY on its own market."""
    out = []
    for i, (usd, price, won, ts) in enumerate(bets):
        out.append({"type": "TRADE", "side": "BUY", "conditionId": f"m{i}", "price": price,
                    "usdcSize": usd, "size": usd / price, "timestamp": ts, "outcomeIndex": 0,
                    "asset": f"tok{i}", "title": f"Will {i} happen?", "_won": won})
    return out


def _res_dir(tmp_path, acts):
    from src.copy_trading import market_resolution
    d = tmp_path / "rescache"
    d.mkdir()
    for ev in acts:
        market_resolution._write_cache(ev["conditionId"], market_resolution.MarketResolution(
            winning_index=0 if ev["_won"] else 1, end_ts=ev["timestamp"] + 3600), str(d))
    return str(d)


def test_the_row_picks_the_floor_with_the_best_trimmed_roi_that_clears_the_bars(tmp_path):
    from src.copy_trading import wallet_floor
    # 20 bets at $160 (winning 16 of 20 at 0.5) and 20 bets at $320 (winning 10 of 20).
    bets = [(160.0, 0.5, i % 5 != 0, 10_000.0 + i) for i in range(20)]
    bets += [(320.0, 0.5, i % 2 == 0, 20_000.0 + i) for i in range(20)]
    acts = _acts(W1, bets)
    row = wallet_floor.row_for(W1, acts, era=1.0, now=30_000.0, res_cache_dir=_res_dir(tmp_path, acts),
                               min_n=15, min_roi=0.10)
    at = row["at"]
    assert at["300"]["n"] == 20 and at["150"]["n"] == 40 and at["100"]["n"] == 40 and at["200"]["n"] == 20
    assert at["300"]["ok"] is False, "half the $320 bets lost: ROI 0 is under the +10% floor"
    assert at["150"]["ok"] is True and at["100"]["ok"] is True
    assert row["chosen"] == 150.0, "the same trimmed ROI at 150 and 100; the higher floor wins the tie"
    assert row["label"].startswith("backward replay")
    line = wallet_floor.line(row)
    assert line.startswith("copies at $150: 300 no") and "150 YES" in line and "backward replay" in line


def test_no_floor_clearing_the_bars_keeps_the_global_and_the_line_says_so(tmp_path):
    from src.copy_trading import wallet_floor
    acts = _acts(W1, [(400.0, 0.5, False, 10_000.0 + i) for i in range(20)])
    row = wallet_floor.row_for(W1, acts, era=1.0, now=30_000.0, res_cache_dir=_res_dir(tmp_path, acts),
                               min_n=15, min_roi=0.10)
    assert row["chosen"] is None
    assert wallet_floor.line(row).startswith("no floor clears the bars, global floor stays")
    assert wallet_floor.line(None) == "floor row: not measured yet"


def test_the_live_floor_is_the_global_until_the_owner_flips_the_switch(monkeypatch):
    from src.copy_trading import wallet_floor
    zset.admit(W1, ready=True, checks=[], settled=_rows(W1, 20), era_floor=1.0,
               real_roi=0.2, real_n=20, rails_supplied=True)
    assert zset.promotion_state.update_promoted(W1, {wallet_floor.FLOOR_KEY: 150.0, wallet_floor.ROW_KEY: {"chosen": 150.0}}, scope=zset.SCOPE)
    monkeypatch.setattr(CONFIG, "live_per_wallet_min_usd", "false")
    assert wallet_floor.live_floor(W1, 300.0) == 300.0, "off: the global floor, whatever the record says"
    monkeypatch.setattr(CONFIG, "live_per_wallet_min_usd", "true")
    assert wallet_floor.live_floor(W1, 300.0) == 150.0
    assert wallet_floor.live_floor(W2, 300.0) == 300.0, "a wallet with no chosen floor keeps the global"
    assert wallet_floor.live_floor_why(W1, 300.0)[1] == "this wallet's own floor (all Z wallets)"
    # The annotation never admits: a wallet outside Z gets no record.
    assert zset.promotion_state.update_promoted(W2, {wallet_floor.FLOOR_KEY: 100.0}, scope=zset.SCOPE) is False
    assert W2 not in zset.wallet_set()
    # The gate's own keys are not touched by an annotation.
    rec = zset.promotion_state.promoted_map(zset.SCOPE)[W1]
    assert rec["source"] == "gate" and rec["tier"] == "1b"


def test_the_switch_takes_a_wallet_list_as_a_canary_and_fails_closed_on_a_typo(monkeypatch, caplog):
    from src.copy_trading import wallet_floor
    zset.admit(W1, ready=True, checks=[], settled=_rows(W1, 20), era_floor=1.0,
               real_roi=0.2, real_n=20, rails_supplied=True)
    zset.admit(W2, ready=True, checks=[], settled=_rows(W2, 20), era_floor=1.0,
               real_roi=0.2, real_n=20, rails_supplied=True)
    for w in (W1, W2):
        zset.promotion_state.update_promoted(w, {wallet_floor.FLOOR_KEY: 150.0, wallet_floor.ROW_KEY: {"chosen": 150.0}}, scope=zset.SCOPE)
    # The list: only the listed wallet moves; the other keeps the global.
    monkeypatch.setattr(CONFIG, "live_per_wallet_min_usd", f" {W1.upper()} ,")
    assert wallet_floor.mode()[0] == wallet_floor.MODE_LIST
    assert wallet_floor.live_floor_why(W1, 300.0) == (150.0, "this wallet's own floor (listed wallet)")
    assert wallet_floor.live_floor_why(W2, 300.0) == (300.0, "the global floor (not listed)")
    assert wallet_floor.enabled() is True
    # A typo is none, said once, never true by accident.
    wallet_floor._mode_said.clear()
    for bad in ("ture", f"{W1},0xnotawallet", "1,2"):
        monkeypatch.setattr(CONFIG, "live_per_wallet_min_usd", bad)
        assert wallet_floor.mode()[0] == wallet_floor.MODE_NONE, bad
        assert wallet_floor.live_floor(W1, 300.0) == 300.0
    said = [r for r in caplog.records if "LIVE_PER_WALLET_MIN_USD=" in r.getMessage()]
    assert len(said) == 3 and all("read as false" in r.getMessage() for r in said)
    monkeypatch.setattr(CONFIG, "live_per_wallet_min_usd", "ture")
    wallet_floor.mode()
    assert len([r for r in caplog.records if "LIVE_PER_WALLET_MIN_USD=" in r.getMessage()]) == 3, "said once per value"
    for off in ("", "false", "0", "off", None):
        monkeypatch.setattr(CONFIG, "live_per_wallet_min_usd", off)
        assert wallet_floor.mode()[0] == wallet_floor.MODE_NONE and wallet_floor.enabled() is False


def test_the_live_path_asks_the_floor_module_at_both_checks():
    """The seam: a per-wallet floor that only one of the two min-bet checks
    knew about would be refused by the other one first."""
    ex = open("src/copy_trading/trade_executor.py", encoding="utf-8").read()
    tr = open("src/copy_trading/tiered_risk_manager.py", encoding="utf-8").read()
    assert "wallet_floor.live_floor_why(trade.trader_address, gov.min_trader_bet_usd)" in ex
    assert "wallet_floor.live_floor_why(trade.trader_address, cfg.min_trader_bet)" in tr
    assert "trade.size < _floor" in ex and "trade.size < floor" in tr, "both checks compare against the wallet's floor"


def test_the_tiered_check_uses_the_wallets_floor_when_on(monkeypatch):
    from src.copy_trading import wallet_floor
    monkeypatch.setattr(CONFIG, "live_per_wallet_min_usd", "true")
    monkeypatch.setattr(wallet_floor, "stored_floor", lambda w: 150.0 if w.lower() == W1 else None)
    src = open("src/copy_trading/tiered_risk_manager.py", encoding="utf-8").read()
    assert "for tier {tier} ({why})" in src, "the skip line says which floor applied and why"
    assert wallet_floor.live_floor(W1, 300.0) == 150.0 and wallet_floor.live_floor(W2, 300.0) == 300.0
    assert wallet_floor.live_floor_why(W2, 300.0)[1].startswith("the global floor (no chosen floor")


def test_the_floor_truth_receipt_reads_the_row_against_the_forward_book(tmp_path, monkeypatch):
    from scripts import floor_truth_receipt as ft
    from src.copy_trading import book_tiers, wallet_floor
    zset.admit(W1, ready=True, checks=[], settled=_rows(W1, 20), era_floor=1.0,
               real_roi=0.2, real_n=20, rails_supplied=True)
    zset.promotion_state.update_promoted(W1, {wallet_floor.FLOOR_KEY: 150.0, wallet_floor.ROW_KEY: {
        "chosen": 150.0, "at": {"150": {"n": 22, "roi": 0.16, "trimmed": 0.09, "ok": True}}}}, scope=zset.SCOPE)
    b150 = _rows(W1, 20)
    for p in b150[10:]:
        p.won = False
        p.pnl = p.ideal_pnl = -p.spent
    quotes = {p.copy_id: 0.99 if p.won else 0.5 for p in b150}
    monkeypatch.setattr(CONFIG, "copy_paper_b_books", "b300:300,b150:150")
    monkeypatch.setattr(ft, "PaperCopyLedger", lambda path: type("L", (), {"positions": {p.copy_id: p for p in (b150 if "b150" in path else [])}})())
    monkeypatch.setattr(ft.virtual_ledger, "quote_map", lambda rows: quotes)
    monkeypatch.setattr(ft.shadow_quote, "load_rows", lambda: [])
    monkeypatch.setattr(ft.era_state, "era_floor_ts", lambda p: 1.0)
    text, summary = ft.receipt(now=time.time())
    assert summary["z"] == 1 and summary["disagree"] == 1, (summary, text)
    assert "backward at $150: +16% (trimmed +9%, n=22)" in text and "forward b150 at real quotes" in text and "DISAGREE" in text
    assert "A retained baseline, not a verdict" in text


def test_refresh_stores_the_row_on_the_record_once_a_day_and_reports_a_move(tmp_path, monkeypatch):
    from src.copy_trading import discovery_data, wallet_floor
    zset.admit(W1, ready=True, checks=[], settled=_rows(W1, 20), era_floor=1.0,
               real_roi=0.2, real_n=20, rails_supplied=True)
    bets = [(160.0, 0.5, True, 10_000.0 + i) for i in range(20)]
    acts = _acts(W1, bets)
    monkeypatch.setattr(CONFIG, "wallet_discovery_res_cache", _res_dir(tmp_path, acts))
    monkeypatch.setattr(discovery_data, "fetch_activity", lambda w, d, t: acts)
    r = wallet_floor.refresh(W1, now=30_000.0, era=1.0)
    assert r is not None
    row, before, after = r
    assert before is None and after == 150.0
    assert wallet_floor.stored(W1)["chosen"] == 150.0 and wallet_floor.stored_floor(W1) == 150.0
    assert wallet_floor.refresh(W1, now=30_000.0 + 3600, era=1.0) is None, "fresh: not recomputed"
    assert wallet_floor.refresh(W1, now=30_000.0 + wallet_floor.REFRESH_S + 1, era=1.0) is not None
    # A failed read is never a row.
    def failing(w, d, t):
        discovery_data._activity_fetch_failures.append(w)
        return []
    monkeypatch.setattr(discovery_data, "fetch_activity", failing)
    assert wallet_floor.refresh(W1, now=30_000.0 + 2 * wallet_floor.REFRESH_S, era=1.0) is None
    assert wallet_floor.stored_floor(W1) == 150.0, "the last good row stays"


def test_the_scan_writes_the_floor_row_and_says_when_it_moves(tmp_path, monkeypatch):
    from src.copy_trading import ops_admit, ops_watch, wallet_floor
    monkeypatch.setattr(ops_watch.CONFIG, "data_dir", str(tmp_path))
    zset.admit(W1, ready=True, checks=[], settled=_rows(W1, 20), era_floor=1.0,
               real_roi=0.2, real_n=20, rails_supplied=True)
    calls = {"n": 0}

    def fake_refresh(w, *, now=None, era=None, force=False):
        calls["n"] += 1
        return ({"chosen": 150.0, "at": {}, "label": wallet_floor.ROW_LABEL}, 300.0, 150.0)
    monkeypatch.setattr(wallet_floor, "refresh", fake_refresh)
    sent = []
    moved = ops_admit.refresh_floors({W1}, skip=set(), era=1.0, now=1000.0, send=lambda t, k: sent.append(t))
    assert moved == [W1] and calls["n"] == 1
    assert sent and "Floor moved" in sent[0] and "(switch off): real money keeps the global floor" in sent[0]
    rows = [r for r in ops_watch.ledger_rows(kinds={"floor_row"})]
    assert rows and rows[-1]["wallet"] == W1 and rows[-1]["floor_after"] == 150.0 and rows[-1]["push"] == "WALLET"


# --------------------------------------------------------------------------- #
# The rail watch: a Z wallet on the fallback for a week is an [ops] line
# --------------------------------------------------------------------------- #

def test_a_z_wallet_on_book_a_for_seven_days_is_said_once_on_an_ops_line(tmp_path, monkeypatch, caplog):
    from src.copy_trading import ops_admit, ops_grammar, ops_watch
    monkeypatch.setattr(ops_watch.CONFIG, "data_dir", str(tmp_path))

    class C:
        def __init__(self, w, rail, n):
            self.wallet, self.exec_rail, self.real_n = w, rail, n
    day = 86400.0
    ops_admit.rail_watch([C(Z1, zset.RAIL_BOOK_A, 4)], in_z={Z1}, now=1000.0)
    ops_admit.rail_watch([C(Z1, zset.RAIL_BOOK_A, 6)], in_z={Z1}, now=1000.0 + 6 * day)
    assert not [r for r in caplog.records if "judged by book A" in r.getMessage()], "six days: not yet"
    d = ops_admit.rail_watch([C(Z1, zset.RAIL_BOOK_A, 7)], in_z={Z1}, now=1000.0 + 7 * day + 1)
    said = [r for r in caplog.records if "judged by book A for 7 days" in r.getMessage()]
    assert len(said) == 1 and "7 of 15 matched" in said[0].getMessage()
    assert ops_grammar.is_important(said[0].getMessage()), "an [ops] line reaches the important file and the sidecar"
    assert d[Z1]["said"] is True
    ops_admit.rail_watch([C(Z1, zset.RAIL_BOOK_A, 7)], in_z={Z1}, now=1000.0 + 8 * day)
    assert len([r for r in caplog.records if "judged by book A" in r.getMessage()]) == 1, "said once"
    # Back on the slice: the clock resets and a later fallback starts fresh.
    d = ops_admit.rail_watch([C(Z1, zset.RAIL_SLICE, 20)], in_z={Z1}, now=1000.0 + 9 * day)
    assert d[Z1]["rail"] == zset.RAIL_SLICE and d[Z1]["said"] is False


# --------------------------------------------------------------------------- #
# The clean stop: a deadline in the bot, a handler in the sidecar
# --------------------------------------------------------------------------- #

def test_the_bot_ends_itself_before_docker_force_kills_it():
    src = open("main.py", encoding="utf-8").read()
    tree = ast.parse(src)
    handler = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_signal_handler")
    body = ast.unparse(handler)
    assert "threading.Timer(SHUTDOWN_DEADLINE_S, _hard_exit)" in body and "t.daemon = True" in body
    assert 'SHUTDOWN_DEADLINE_S = float(os.environ.get("SHUTDOWN_DEADLINE_S", "8") or 8)' in src
    hard = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_hard_exit")
    assert "os._exit(0)" in ast.unparse(hard) and "threads still running" in ast.unparse(hard)
    assert "MainThread" in ast.unparse(hard), "the main thread is not 'still running'; it is the one being ended"


def test_the_sidecar_traps_sigterm_because_pid_1_ignores_the_default():
    src = open("scripts/ai_sre.py", encoding="utf-8").read()
    tree = ast.parse(src)
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    body = ast.unparse(main)
    assert "_signal.signal(_signal.SIGTERM, _on_term)" in body
    term = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_on_term")
    assert "raise SystemExit(0)" in ast.unparse(term)


def test_the_rail_swap_receipt_reads_the_live_gate(tmp_path, monkeypatch):
    from scripts import rail_swap_receipt as rs
    monkeypatch.setattr(CONFIG, "copy_golive_min_settled", 15)
    b = _rows(W1, 20) + _rows(W2, 20)
    for p in b[10:20]:
        p.won = False
        p.pnl = p.ideal_pnl = -p.spent
    quotes = {p.copy_id: (0.99 if p.target == W1 else 0.5) for p in b}
    monkeypatch.setattr(zc, "load_books", lambda: (1.0, b, []))
    monkeypatch.setattr(zc, "load_quotes", lambda now=None: quotes)
    text, summary = rs.receipt(now=time.time())
    assert summary["wallets"] == 2 and summary["thin"] == 0
    assert summary["a_only"] == 1 and W1[:10] in text.split("Refused only by the slice")[1]
    assert "A retained baseline, not an improvement claim" in text
