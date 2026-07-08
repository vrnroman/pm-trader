"""Evidence-throughput levers (starvation RCA 2026-07): starved-wallet slate
priority + paper-only category-cap relief, and the over_real_cap audit stamp."""

from __future__ import annotations

import json
import os
import tempfile

from src.copy_trading.copy_paper import CopyPaperEngine, PaperCopyLedger, PaperPosition


def _trade(copy_id, token, target="0xT", their_price=0.50, their_usd=1000,
           category="sports"):
    return dict(copy_id=copy_id, target=target, condition_id=f"c-{copy_id}",
                token_id=token, outcome_index=0, category=category,
                their_price=their_price, their_usd=their_usd)


def _engine(led, feed, **kw):
    return CopyPaperEngine(
        led, detector=lambda: feed,
        book_fetcher=lambda t: [(0.50, 10000)],
        resolver=lambda c: None, max_copy_usd=50, **kw)


def _seed(led, target, n, closed=True, day_ts=1.0):
    """n existing ledger positions for `target` (evidence), opened off-day."""
    for i in range(n):
        led.add(PaperPosition(
            copy_id=f"seed-{target}-{i}", target=target, condition_id=f"sc{i}",
            token_id=f"st-{target}-{i}", outcome_index=0, category="other",
            their_price=0.5, entry_price=0.5, shares=10, spent=5.0, drag_bps=0,
            opened_ts=day_ts, closed=closed, won=True, pnl=1.0,
            closed_ts=day_ts + 1))


NOW = 10 * 86400.0  # far from the seeds' UTC day so day-caps start at zero


def test_starved_priority_gives_cold_wallet_the_last_slot():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        _seed(led, "0xhot", 10)
        # feed order: hot wallet first; category cap leaves ONE slot today
        feed = [_trade("h1", "T1", target="0xhot"),
                _trade("c1", "T2", target="0xcold")]
        eng = _engine(led, feed, max_copies_per_category_day=1,
                      starved_priority=True)
        s = eng.run_cycle(now=NOW)
        assert s.opened == 1
        opened = [p for p in led.positions.values()
                  if p.copy_id in ("h1", "c1")]
        assert [p.target for p in opened] == ["0xcold"]   # cold wallet won the slot


def test_priority_off_keeps_feed_order():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        _seed(led, "0xhot", 10)
        feed = [_trade("h1", "T1", target="0xhot"),
                _trade("c1", "T2", target="0xcold")]
        eng = _engine(led, feed, max_copies_per_category_day=1)
        s = eng.run_cycle(now=NOW)
        assert s.opened == 1
        opened = [p for p in led.positions.values()
                  if p.copy_id in ("h1", "c1")]
        assert [p.target for p in opened] == ["0xhot"]    # legacy: first come


def test_relief_admits_starved_wallet_over_category_cap():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        feed = [_trade(f"t{i}", f"T{i}", target=f"0xw{i}") for i in range(4)]
        eng = _engine(led, feed, max_copies_per_category_day=2,
                      relief_evidence_n=15, relief_max_per_category_day=3)
        s = eng.run_cycle(now=NOW)
        # 2 under the real cap + 1 more under relief; the 4th hits the relief cap
        assert s.opened == 3
        assert s.skipped_slate_cap == 1
        flags = sorted((p.copy_id, p.over_real_cap) for p in led.positions.values())
        assert flags == [("t0", False), ("t1", False), ("t2", True)]


def test_relief_denied_to_wallet_with_enough_evidence():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        _seed(led, "0xhot", 20)   # over the evidence floor -> no relief
        feed = [_trade("a", "T1", target="0xother"),
                _trade("b", "T2", target="0xother2"),
                _trade("h", "T3", target="0xhot")]
        eng = _engine(led, feed, max_copies_per_category_day=2,
                      relief_evidence_n=15, relief_max_per_category_day=5)
        s = eng.run_cycle(now=NOW)
        assert s.opened == 2                      # hot wallet stopped at the real cap
        assert s.skipped_slate_cap == 1
        assert all(not p.over_real_cap for p in led.positions.values())


def test_relief_never_bypasses_the_wallet_cap():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        feed = [_trade(f"t{i}", f"T{i}", target="0xcold") for i in range(3)]
        eng = _engine(led, feed, max_copies_per_wallet_day=1,
                      max_copies_per_category_day=1,
                      relief_evidence_n=15, relief_max_per_category_day=10)
        s = eng.run_cycle(now=NOW)
        assert s.opened == 1                      # wallet cap binds despite relief
        assert s.skipped_slate_cap == 2


def test_defaults_leave_engine_unchanged():
    with tempfile.TemporaryDirectory() as d:
        led = PaperCopyLedger(os.path.join(d, "l.jsonl"))
        feed = [_trade(f"t{i}", f"T{i}", target=f"0xw{i}") for i in range(4)]
        eng = _engine(led, feed, max_copies_per_category_day=2)
        s = eng.run_cycle(now=NOW)
        assert s.opened == 2 and s.skipped_slate_cap == 2
        assert all(not p.over_real_cap for p in led.positions.values())


def test_persist_omits_over_real_cap_unless_set():
    # Rollback safety: rows must stay byte-compatible with the legacy strict
    # loader unless cap relief actually fired.
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "l.jsonl")
        led = PaperCopyLedger(path)
        _seed(led, "0xa", 2)
        a, b = sorted(led.positions.values(), key=lambda p: p.copy_id)
        a.over_real_cap = True
        led.save()
        rows = {json.loads(ln)["copy_id"]: json.loads(ln)
                for ln in open(path) if ln.strip()}
        assert rows[a.copy_id]["over_real_cap"] is True
        assert "over_real_cap" not in rows[b.copy_id]


def test_over_real_cap_roundtrips_and_loader_tolerates_unknown_keys():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "l.jsonl")
        led = PaperCopyLedger(path)
        _seed(led, "0xa", 1)
        pos = next(iter(led.positions.values()))
        pos.over_real_cap = True
        led.save()
        # a future-schema row with an unknown key must still load (rollback safety)
        row = json.loads(open(path).readline())
        row["copy_id"] = "future-row"
        row["some_future_field"] = 123
        with open(path, "a") as f:
            f.write(json.dumps(row) + "\n")
        led2 = PaperCopyLedger(path)
        assert led2.positions[pos.copy_id].over_real_cap is True
        assert "future-row" in led2.positions
