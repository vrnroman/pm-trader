"""Tests for the forward paper-copy harness (Strategy 1b execution measurement)."""

from __future__ import annotations

import os
import tempfile

from src.copy_trading.copy_paper import (
    CopyPaperEngine,
    PaperCopyLedger,
    PaperPosition,
    format_resolution_telegram,
    report,
    simulate_copy_fill,
)


# --------------------------------------------------------------------------- #
# simulate_copy_fill
# --------------------------------------------------------------------------- #

def test_fill_at_book_with_drag():
    # target bought at 0.50; current best ask is 0.52 -> we pay up, drag +400bps
    # (needs a slippage cap >= 400bps to allow the chase)
    fill = simulate_copy_fill(0.50, [(0.52, 1000)], copy_usd=52, max_slippage_bps=500)
    assert fill.shares > 0
    assert abs(fill.avg_price - 0.52) < 1e-9
    assert fill.drag_bps == 400


def test_fill_respects_slippage_cap():
    # best ask 0.61 is beyond 0.50*(1+200bps)=0.51 -> unfilled
    fill = simulate_copy_fill(0.50, [(0.61, 1000)], copy_usd=50, max_slippage_bps=200)
    assert fill.shares == 0
    assert fill.spent == 0


def test_fill_walks_levels_within_budget():
    # 0.50 has 20 shares ($10), then 0.505 deeper; copy $20 -> spans two levels
    fill = simulate_copy_fill(0.50, [(0.50, 20), (0.505, 1000)], copy_usd=20,
                              max_slippage_bps=300)
    assert abs(fill.spent - 20) < 1e-6
    assert 0.50 <= fill.avg_price <= 0.505


def test_fill_empty_book_unfilled():
    fill = simulate_copy_fill(0.50, [], copy_usd=50)
    assert fill.shares == 0


def test_fill_depth_limited():
    # only $5 of asks available within slippage, want $50
    fill = simulate_copy_fill(0.50, [(0.50, 10)], copy_usd=50, max_slippage_bps=10)
    assert abs(fill.spent - 5.0) < 1e-6  # 10 shares * 0.50


def test_fill_skips_stale_dust_ask_below_floor():
    # Regression for the "drag $-30950" blow-up: a dust ask at 0.001 sitting
    # under a 0.62 market is stale data. It must be skipped, not swept — else a
    # $50 budget buys ~50k shares and the drag metric explodes.
    fill = simulate_copy_fill(
        0.62, [(0.001, 1_000_000), (0.63, 1000)], copy_usd=50, max_slippage_bps=200,
    )
    assert fill.avg_price >= 0.62 * 0.5         # filled on the credible level, not the dust
    assert fill.shares < 200                    # ~80 shares, not ~50k
    assert abs(fill.drag_bps) < 500             # bounded, not -9984bps


def test_fill_unfilled_when_only_sub_floor_liquidity():
    # If the *only* liquidity is non-credible deep-discount dust, treat as unfilled.
    fill = simulate_copy_fill(0.62, [(0.001, 1_000_000)], copy_usd=50)
    assert fill.shares == 0 and fill.spent == 0


def test_fill_allows_genuine_favourable_move_within_floor():
    # A real pullback to 0.40 from a 0.62 entry (within the 50% floor) still fills.
    fill = simulate_copy_fill(0.62, [(0.40, 10000)], copy_usd=50, max_slippage_bps=200)
    assert fill.shares > 0
    assert abs(fill.avg_price - 0.40) < 1e-9


# --------------------------------------------------------------------------- #
# PaperPosition.realize
# --------------------------------------------------------------------------- #

def _pos(**kw):
    base = dict(
        copy_id="tx1-TOK", target="0xT", condition_id="0xC", token_id="TOK",
        outcome_index=0, category="sports", their_price=0.50, entry_price=0.52,
        shares=100.0, spent=52.0, drag_bps=400, opened_ts=1000.0,
    )
    base.update(kw)
    return PaperPosition(**base)


def test_realize_win_counts_drag():
    p = _pos()
    p.realize(won=True, now=2000.0)
    assert p.closed and p.won
    assert abs(p.pnl - (100 - 52)) < 1e-9          # our PnL with drag
    assert abs(p.ideal_pnl - (100 - 50)) < 1e-9    # drag-free PnL
    # execution drag cost = ideal - actual = 2.0
    assert abs(p.ideal_pnl - p.pnl - 2.0) < 1e-9


def test_realize_loss():
    p = _pos()
    p.realize(won=False, now=2000.0)
    assert p.pnl == -52.0
    assert p.ideal_pnl == -50.0


# --------------------------------------------------------------------------- #
# Ledger persistence & dedup
# --------------------------------------------------------------------------- #

def test_ledger_roundtrip_and_dedup():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "ledger.jsonl")
        led = PaperCopyLedger(path)
        led.add(_pos(copy_id="a"))
        assert led.has("a")
        # reload from disk
        led2 = PaperCopyLedger(path)
        assert led2.has("a")
        assert len(led2.open_positions()) == 1


def test_ledger_persists_closed_state():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "l.jsonl")
        led = PaperCopyLedger(path)
        p = _pos(copy_id="x")
        led.add(p)
        p.realize(won=True, now=1.0)
        led.save()
        led2 = PaperCopyLedger(path)
        assert led2.closed_positions()[0].won is True


# --------------------------------------------------------------------------- #
# Engine cycle with injected fakes
# --------------------------------------------------------------------------- #

def _trade(copy_id, token, oi=0, their_price=0.50, their_usd=1000):
    return dict(copy_id=copy_id, target="0xT", condition_id="0xC", token_id=token,
                outcome_index=oi, category="sports", their_price=their_price,
                their_usd=their_usd)


def test_engine_opens_dedups_and_resolves():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        feed = [[_trade("t1", "TOK", oi=0)], [_trade("t1", "TOK", oi=0)]]  # same trade twice
        books = {"TOK": [(0.51, 10000)]}
        resolved = {}  # condition -> winner

        eng = CopyPaperEngine(
            led, detector=lambda: feed[cycle[0]],
            book_fetcher=lambda t: books.get(t, []),
            resolver=lambda c: resolved.get(c),
            max_copy_usd=50,
        )
        cycle = [0]
        s1 = eng.run_cycle(now=100)
        assert s1.opened == 1 and len(led.open_positions()) == 1

        cycle[0] = 1
        s2 = eng.run_cycle(now=200)   # same copy_id -> deduped, no new open
        assert s2.opened == 0

        # now resolve in favour of outcome 0
        resolved["0xC"] = 0
        s3 = eng.run_cycle(now=300)
        assert s3.resolved == 1
        assert len(led.closed_positions()) == 1
        assert led.closed_positions()[0].won is True


def test_engine_skips_unfilled():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        eng = CopyPaperEngine(
            led, detector=lambda: [_trade("t1", "TOK", their_price=0.50)],
            book_fetcher=lambda t: [(0.99, 1000)],  # way beyond slippage
            resolver=lambda c: None, max_slippage_bps=200,
        )
        s = eng.run_cycle(now=1)
        assert s.opened == 0 and s.skipped_unfilled == 1


def test_report_aggregates_drag_and_roi():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        p1 = _pos(copy_id="w", shares=100, spent=52, their_price=0.50)
        p1.realize(won=True, now=1.0)
        p2 = _pos(copy_id="l", shares=100, spent=52, their_price=0.50)
        p2.realize(won=False, now=1.0)
        led.add(p1)
        led.add(p2)
        r = report(led)
        assert r["closed"] == 2
        assert abs(r["realized_pnl"] - ((100 - 52) + (-52))) < 1e-6  # -4
        assert abs(r["execution_drag_cost"] - 4.0) < 1e-6  # 2 per trade * 2
        assert r["hit_rate"] == 0.5


# --------------------------------------------------------------------------- #
# Resolution context + Telegram formatting
# --------------------------------------------------------------------------- #

def test_resolved_positions_carry_market_context():
    # detector context (title/slug) must survive onto the closed position so the
    # notification can name what resolved instead of only counting it.
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        tr = _trade("t1", "TOK", oi=0)
        tr["title"] = "Will BTC hit $100k in 2025?"
        tr["slug"] = "btc-100k-2025"
        eng = CopyPaperEngine(
            led, detector=lambda: [tr],
            book_fetcher=lambda t: [(0.51, 10000)],
            resolver=lambda c: 0,          # resolves to outcome 0 immediately
            max_copy_usd=50,
        )
        s = eng.run_cycle(now=100)
        assert s.opened == 1 and s.resolved == 1
        assert len(s.resolved_positions) == 1
        p = s.resolved_positions[0]
        assert p.title == "Will BTC hit $100k in 2025?"
        assert p.slug == "btc-100k-2025"
        assert p.won is True


def test_format_resolution_telegram_win_names_market_and_links():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        p = _pos(copy_id="w", title="Will BTC hit $100k in 2025?",
                 slug="btc-100k-2025", shares=100, spent=50,
                 their_price=0.50, entry_price=0.52, drag_bps=400)
        p.realize(won=True, now=1.0)
        led.add(p)
        msg = format_resolution_telegram([p], report(led))
        assert "Will BTC hit $100k in 2025?" in msg          # what resolved
        assert "polymarket.com/event/btc-100k-2025" in msg   # dig deeper
        assert "✅ WON" in msg
        assert "+400bps drag" in msg                         # per-position drag
        assert "<b>Ledger:</b>" in msg                       # cumulative footer


def test_format_resolution_telegram_loss_and_titleless_fallback():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        p = _pos(copy_id="l", title="", category="politics",
                 shares=100, spent=50, their_price=0.50)
        p.realize(won=False, now=1.0)
        led.add(p)
        msg = format_resolution_telegram([p], report(led))
        assert "❌ LOST" in msg
        assert "(politics market)" in msg     # falls back to category when untitled
        assert "1 market resolved" in msg     # singular
