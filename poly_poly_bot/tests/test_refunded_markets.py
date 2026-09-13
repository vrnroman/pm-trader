"""Issue #33: a cancelled (50/50-refunded) market closes a paper or preview
position at $0.50 a share, mirroring the CTF payout, instead of stranding it
open forever (both readers treated a 50/50 as "unresolved")."""

from __future__ import annotations

from src.copy_trading import copy_paper_live as live
from src.copy_trading.copy_paper import REFUNDED, CopyPaperEngine, PaperCopyLedger, PaperPosition
from src.copy_trading.preview_resolver import classify_payout, classify_position, realize_preview_positions


def _open_pos(ledger, *, spent=10.0, shares=20.0, their=0.5):
    ledger.add(PaperPosition(
        copy_id="c1", target="0xT", condition_id="m1", token_id="tok1",
        outcome_index=0, category="other", their_price=their,
        entry_price=spent / shares, shares=shares, spent=spent,
        drag_bps=0, opened_ts=0.0,
    ))


def test_the_live_resolver_reads_a_fifty_fifty_as_refunded(monkeypatch):
    monkeypatch.setattr(live, "_get", lambda base, path, **kw: [
        {"closed": True, "outcomePrices": '["0.5", "0.5"]'}])
    assert live.resolve("0xC") == REFUNDED
    assert live.parse_winner({"closed": True, "outcomePrices": ["1", "0"]}) == 0
    assert live.parse_winner({"closed": True, "outcomePrices": ["0", "1"]}) == 1
    assert live.parse_winner({"closed": True, "outcomePrices": ["0.7", "0.3"]}) is None, "not clean"
    assert live.parse_winner({"closed": False, "outcomePrices": ["0.5", "0.5"]}) is None, "still open"


def test_the_engine_books_a_refund_at_half_a_share(tmp_path):
    ledger = PaperCopyLedger(str(tmp_path / "l.jsonl"))
    _open_pos(ledger, spent=12.0, shares=20.0, their=0.6)     # entry 0.60
    eng = CopyPaperEngine(ledger, detector=lambda: [], book_fetcher=lambda t: [],
                          resolver=lambda cid: REFUNDED)
    s = eng.run_cycle(now=100.0)
    assert s.resolved == 1 and s.refunded == 1 and s.resolved_positions
    (pos,) = ledger.closed_positions()
    assert pos.refunded is True and pos.won is False and pos.closed is True
    assert abs(pos.pnl - (20 * 0.5 - 12.0)) < 1e-9, "half the shares' notional back, not a total loss"
    assert abs(pos.ideal_pnl - (20 * 0.5 - 20 * 0.6)) < 1e-9
    # and the row round-trips through the ledger file
    again = PaperCopyLedger(str(tmp_path / "l.jsonl"))
    assert again.closed_positions()[0].refunded is True


def test_a_refunded_market_does_not_strand_the_position(tmp_path):
    """Before: the resolver answered None for a 50/50 and the position sat
    open across every cycle."""
    ledger = PaperCopyLedger(str(tmp_path / "l.jsonl"))
    _open_pos(ledger)
    eng = CopyPaperEngine(ledger, detector=lambda: [], book_fetcher=lambda t: [],
                          resolver=lambda cid: live.parse_winner(
                              {"closed": True, "outcomePrices": '["0.5", "0.5"]'}))
    eng.run_cycle(now=1.0)
    assert ledger.open_positions() == []


def _market(prices, tokens='["YES","NO"]', closed=True):
    return {"closed": closed, "outcomePrices": prices, "clobTokenIds": tokens}


def test_preview_payout_reads_win_loss_and_refund():
    assert classify_payout(_market('["1","0"]'), "YES") == 1.0
    assert classify_payout(_market('["1","0"]'), "NO") == 0.0
    assert classify_payout(_market('["0.5","0.5"]'), "YES") == 0.5
    assert classify_payout(_market('["0.5","0.5"]'), "NO") == 0.5
    assert classify_payout(_market('["0.7","0.3"]'), "YES") is None
    assert classify_payout(_market('["0.5","0.5"]', closed=False), "YES") is None
    # the boolean reader (the late-bet lead) still calls a refund "no verdict"
    assert classify_position(_market('["0.5","0.5"]'), "YES") is None
    assert classify_position(_market('["1","0"]'), "YES") is True


def test_preview_realization_books_a_refund_at_half():
    positions = {"YES": {"shares": 80.0, "avg_price": 0.6, "market": "m", "market_key": "0xc",
                         "tier": "1a", "trader_address": "0xW"}}
    rows, drop = realize_preview_positions(positions, lambda cid: _market('["0.5","0.5"]'),
                                           now_iso="2026-09-13T00:00:00+00:00")
    assert drop == ["YES"] and len(rows) == 1
    row = rows[0]
    assert row["returned"] == 40.0 and row["pnl"] == -8.0
    assert row["won"] is False and row["refunded"] is True
    assert row["tier"] == "1a" and row["exit"] == "resolution" and row["source"] == "preview"
