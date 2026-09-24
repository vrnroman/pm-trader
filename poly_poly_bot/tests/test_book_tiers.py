"""Book B at more than one slice floor (2026-09-24 requirements, part 3 §3.4),
the live floor decoupled from the paper floor, R4, R5, R6."""
from __future__ import annotations

import json

import pytest

from src.config import CONFIG
from src.copy_trading import book_tiers, live_budget


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(CONFIG, "copy_paper_b_ledger", str(tmp_path / "copy_paper_ledger_b.jsonl"))
    monkeypatch.setattr(CONFIG, "wallet_discovery_state", str(tmp_path / "discovery_state.json"))
    monkeypatch.setattr(CONFIG, "copy_paper_min_usd", 300.0)
    monkeypatch.setattr(CONFIG, "copy_paper_b_books", "b300:300,b150:150,b100:100")
    monkeypatch.setattr(CONFIG, "zset_gate_book", "b300")
    monkeypatch.setattr(CONFIG, "live_min_trader_bet_usd", 0.0)
    return tmp_path


def test_the_first_book_is_todays_files_and_the_others_get_their_own(box):
    bs = book_tiers.books()
    assert [(b.id, b.min_usd, b.primary) for b in bs] == [("b300", 300.0, True), ("b150", 150.0, False), ("b100", 100.0, False)]
    assert bs[0].scope == "b" and bs[0].tag == "COPY-PAPER-B" and book_tiers.ledger_path(bs[0]) == CONFIG.copy_paper_b_ledger
    assert bs[1].scope == "b150" and bs[1].tag == "COPY-PAPER-B150"
    assert book_tiers.ledger_path(bs[1]) == str(box / "copy_paper_ledger_b150.jsonl")
    assert book_tiers.gate_history_path(bs[0]).endswith("promotion-gate-history_b.jsonl")
    assert book_tiers.gate_history_path(bs[2]).endswith("promotion-gate-history_b100.jsonl")


def test_a_bad_spec_still_runs_the_primary_and_the_gate_book_is_a_knob(box, monkeypatch):
    assert [b.id for b in book_tiers.parse_spec("")] == ["b300"]
    assert [b.id for b in book_tiers.parse_spec("junk,b150:x,b150:150,b150:150,b-7:5")] == ["b150"]
    assert book_tiers.gate_ledger_path() == CONFIG.copy_paper_b_ledger
    monkeypatch.setattr(CONFIG, "zset_gate_book", "b150")
    assert book_tiers.gate_book().id == "b150" and book_tiers.gate_ledger_path().endswith("copy_paper_ledger_b150.jsonl")
    monkeypatch.setattr(CONFIG, "zset_gate_book", "nope")
    assert book_tiers.gate_book().id == "b300", "an unknown gate book falls back to the primary"


def test_real_money_keeps_its_own_floor_whatever_the_paper_books_do(box, monkeypatch):
    assert book_tiers.live_min_trader_bet() == 300.0
    monkeypatch.setattr(CONFIG, "copy_paper_min_usd", 150.0)
    assert book_tiers.live_min_trader_bet() == 150.0, "by default the paper floor"
    monkeypatch.setattr(CONFIG, "live_min_trader_bet_usd", 300.0)
    assert book_tiers.live_min_trader_bet() == 300.0
    monkeypatch.setattr(CONFIG, "live_budget_usd", 80.0)
    monkeypatch.setattr(live_budget, "_balance_cache", None)
    assert live_budget.caps(live=False).min_trader_bet_usd == 300.0
    dy = open("../.github/workflows/deploy.yml", encoding="utf-8").read()
    assert "ensure_env COPY_PAPER_B_BOOKS b300:300,b150:150,b100:100" in dy and "ensure_env LIVE_MIN_TRADER_BET_USD 300" in dy


def test_the_lines_read_each_ledger_and_mark_the_gate_book(box):
    for name, rows in (("copy_paper_ledger_b.jsonl", 12), ("copy_paper_ledger_b150.jsonl", 0)):
        with open(box / name, "w", encoding="utf-8") as f:
            for i in range(rows):
                f.write(json.dumps({"copy_id": f"{name}-{i}", "target": "0xw", "condition_id": "c", "token_id": "t", "outcome_index": 0,
                                    "category": "sports", "their_price": 0.5, "entry_price": 0.5, "shares": 40.0, "spent": 20.0,
                                    "drag_bps": 100, "opened_ts": 1.0 + i, "closed": True, "won": i % 2 == 0,
                                    "pnl": 4.0 if i % 2 == 0 else -20.0, "ideal_pnl": 4.0 if i % 2 == 0 else -20.0, "closed_ts": 5.0 + i}) + "\n")
    ls = book_tiers.lines(100.0)
    assert ls[0].startswith("b300 (floor $300): 12 settled, 0 open, realized -40.0%") and ls[0].endswith("feeds the Z gate")
    assert ls[1] == "b150 (floor $150): 0 settled, 0 open; too few to read"
    assert ls[2].startswith("b100 (floor $100): 0 settled")


def test_main_runs_one_thread_per_book_and_only_the_primary_talks(box):
    src = open("main.py", encoding="utf-8").read()
    b = src[src.index("def _copy_paper_b_loop(book=None):"):src.index("def _ab_race_reporter_loop")]
    assert "_kw.update(min_usd=book.min_usd, ledger_path=book_tiers.ledger_path(book, CONFIG)" in b
    assert 'state_scope=_scope,' in b and 'scope="b"' not in b
    assert "if book.primary else (lambda o: False)" in b and "observer=_get_shadow_observer() if book.primary else None" in b
    assert "if summary.resolved and book.primary:" in b and "if book.primary:\n        try:\n            cross_route.seed_extras" in b
    assert "for _book in _bt.books(CONFIG):" in src and "target=_copy_paper_b_loop, args=(_book,)" in src
    # R5: discovery scores on the book's own slice
    assert "min_usd=float(CONFIG.copy_paper_min_usd)," in src[src.index("cfg = DiscoveryConfig("):]
    # R6: the digest names the near misses with their failing checks
    dg = open("scripts/ops_digest.py", encoding="utf-8").read()
    assert "near the Z door" in dg and "zc.distinct_fails" in dg and "book_tiers.lines(now)" in dg


def test_the_gate_reads_the_gate_book_and_the_wallets_own_last_trade(box, monkeypatch):
    from src.copy_trading import wallet_form, zset_candidates
    monkeypatch.setattr(wallet_form.CONFIG, "data_dir", str(box))
    src = open("src/copy_trading/zset_candidates.py", encoding="utf-8").read()
    assert "PaperCopyLedger(book_tiers.gate_ledger_path(CONFIG))" in src
    wallet_form._write({"ts": 1.0, "wallets": {"0xw": {"ok": True, "reason": "r", "last_trade_ts": 5_000_000.0}}})
    now = 5_000_000.0 + 3 * 86400

    class P:
        def __init__(self, ts):
            self.target, self.opened_ts, self.closed_ts, self.closed = "0xW", ts, ts + 100, True
            self.their_price, self.entry_price, self.spent, self.pnl, self.ideal_pnl, self.won = 0.5, 0.5, 20.0, 4.0, 4.0, True
            self.shares, self.category, self.condition_id, self.token_id = 40.0, "sports", "c", "t"
    rows = [P(now - 40 * 86400 + i) for i in range(20)]   # our last copy 40 days ago; the wallet itself traded 3 days ago
    c = zset_candidates.evaluate("0xW", rows, [], era=None, now=now, book_corr=None)
    idle = [ch for ch in c.checks if str(ch[0]).startswith("active within")][0]
    assert idle[1] is True, idle
