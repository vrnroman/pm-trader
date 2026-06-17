"""Exit-following in the paper-copy engine: when the target SELLs, we sell too.

Traders don't always hold to resolution; the copier must mirror early exits and
book PnL at the achievable bid rather than gambling on settlement.
"""

from __future__ import annotations

from src.copy_trading.copy_paper import CopyPaperEngine, PaperCopyLedger, PaperPosition


def _ledger(tmp_path):
    return PaperCopyLedger(str(tmp_path / "ledger.jsonl"))


def _open_pos(ledger, *, target="0xT", token="tok1", spent=10.0, shares=20.0, their=0.5):
    ledger.add(PaperPosition(
        copy_id="c1", target=target, condition_id="m1", token_id=token,
        outcome_index=0, category="other", their_price=their,
        entry_price=spent / shares, shares=shares, spent=spent,
        drag_bps=0, opened_ts=0.0,
    ))


def test_exit_following_closes_at_bid_not_resolution(tmp_path):
    ledger = _ledger(tmp_path)
    _open_pos(ledger, spent=10.0, shares=20.0)  # 20 shares cost $10 (entry 0.50)

    eng = CopyPaperEngine(
        ledger,
        detector=lambda: [],
        book_fetcher=lambda t: [],
        resolver=lambda cid: None,                       # never resolves
        exit_detector=lambda: [{"target": "0xT", "token_id": "tok1", "their_price": 0.70}],
        bid_fetcher=lambda t: [(0.68, 100)],             # we exit at the 0.68 bid
    )
    s = eng.run_cycle(now=100.0)

    assert s.exited == 1 and s.resolved == 0
    pos = ledger.closed_positions()[0]
    assert pos.exited_early is True and pos.closed is True
    # 20 shares * 0.68 = 13.6 proceeds - 10 spent = +3.6
    assert abs(pos.pnl - 3.6) < 1e-9 and pos.won is True


def test_exit_detector_ignores_untracked_tokens(tmp_path):
    ledger = _ledger(tmp_path)
    _open_pos(ledger, token="tok1")
    eng = CopyPaperEngine(
        ledger, detector=lambda: [], book_fetcher=lambda t: [], resolver=lambda cid: None,
        exit_detector=lambda: [{"target": "0xT", "token_id": "OTHER", "their_price": 0.9}],
        bid_fetcher=lambda t: [(0.9, 10)],
    )
    s = eng.run_cycle(now=1.0)
    assert s.exited == 0 and ledger.open_positions()                # still open


def test_no_exit_detector_keeps_resolution_path(tmp_path):
    ledger = _ledger(tmp_path)
    _open_pos(ledger, spent=10.0, shares=20.0)
    eng = CopyPaperEngine(ledger, detector=lambda: [], book_fetcher=lambda t: [],
                          resolver=lambda cid: 0)        # resolves YES (outcome 0)
    s = eng.run_cycle(now=5.0)
    assert s.exited == 0 and s.resolved == 1
    pos = ledger.closed_positions()[0]
    assert pos.exited_early is False and pos.won is True   # 20 shares payout - 10 = +10
    assert abs(pos.pnl - 10.0) < 1e-9
