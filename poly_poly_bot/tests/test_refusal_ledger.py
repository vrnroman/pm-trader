"""Every refusal gets a price (run s-k7m2qa)."""
from __future__ import annotations

import json

import pytest

from src.config import CONFIG
from src.copy_trading import refusal_ledger as rl

T = 1790800000.0
W = "0x5213eb85fcd465c8927a8382f95dd2dc22306a35"


class Pos:
    def __init__(self, target, token, opened, their_price, won=None, refunded=False):
        self.target, self.token_id, self.opened_ts, self.their_price = target, token, opened, their_price
        self.closed = won is not None
        self.won = won
        self.refunded = refunded


def _skip(ts, reason, token="TOK", trader=W, price=0.5):
    return {"timestamp": ts, "status": "SKIPPED", "side": "BUY", "trader_address": trader,
            "token_id": token, "reason": reason, "price": price, "market": "m"}


def test_the_reason_text_classifies():
    assert rl.classify("market quality: Price drift too high: 750bps > 300bps") == "drift"
    assert rl.classify("market quality: Spread too wide: 600bps > 500bps") == "spread"
    assert rl.classify("wallet out of form: scalper: 100% of exits within 10 min") == "form"
    assert rl.classify("new-wallet cap (first 7 days in set Z): 1 of 1 copies") == "new-wallet cap"
    assert rl.classify("Trader bet $31.73 < min_trader_bet $300.00 for tier 1b") == "floor"
    assert rl.classify("max copies reached (2/2)") == "copies cap"
    assert rl.classify("Price 0.8900 + 2.5% fee = 0.9123 > tier 1b max 0.9") == "price cap"
    assert rl.classify("something new") == "other"


def test_timestamps_parse_from_iso_and_numbers():
    assert rl._ts("2026-10-01T05:17:01Z") == pytest.approx(1790831821.0)
    assert rl._ts("2026-10-01T05:17:01+00:00") == pytest.approx(1790831821.0)
    assert rl._ts("2026-10-01T05:17:01") == pytest.approx(1790831821.0)
    assert rl._ts(1790831821) == 1790831821.0
    assert rl._ts("garbage") == 0.0 and rl._ts(None) == 0.0


def test_load_keeps_skipped_buys_since_and_nothing_else(tmp_path):
    p = tmp_path / "th.jsonl"
    rows = [_skip("2026-10-01T05:00:00Z", "market quality: Price drift too high"),
            {**_skip("2026-10-01T05:00:00Z", "x"), "side": "SELL"},
            {**_skip("2026-10-01T05:00:00Z", "x"), "status": "FILLED"},
            _skip("2026-09-01T05:00:00Z", "old")]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    out = rl.load_refusals(str(p), since_ts=rl._ts("2026-09-30T00:00:00Z"))
    assert len(out) == 1 and out[0]["cls"] == "drift" and out[0]["trader"] == W


def test_the_join_prices_a_refusal_at_their_price_and_at_ours():
    ref = [{"ts": T, "trader": W, "token": "TOK", "reason": "market quality: Price drift", "cls": "drift",
            "price": 0.5, "title": "m"}]
    b = [Pos(W, "TOK", T + 60, 0.50, won=True)]
    q = [{"target": W, "token_id": "TOK", "their_ts": T, "our_price": 0.55}]
    j = rl.join(ref, b, q)
    assert j[0]["settled"] and j[0]["won"] and j[0]["their_price"] == 0.5 and j[0]["our_price"] == 0.55
    rows = rl.table(j, stake_usd=6.4)
    assert rows[0]["cls"] == "drift" and rows[0]["n"] == 1 and rows[0]["won"] == 1
    assert rows[0]["net_their"] == pytest.approx(6.4, abs=0.01)          # 1/0.5 - 1 = +100%
    assert rows[0]["net_our"] == pytest.approx(6.4 * (1 / 0.55 - 1), abs=0.01)


def test_a_refusal_without_a_twin_is_counted_not_dropped():
    ref = [{"ts": T, "trader": W, "token": "TOK", "reason": "r", "cls": "drift", "price": 0.5, "title": "m"},
           {"ts": T, "trader": W, "token": "ZZZ", "reason": "r", "cls": "floor", "price": 0.5, "title": "m"}]
    b = [Pos(W, "TOK", T + 5 * 3600, 0.5, won=True),        # too far: another trade
         Pos(W, "ZZZ", T + 10, 0.5)]                        # open, not settled
    rows = rl.table(rl.join(ref, b, []), stake_usd=6.4)
    by = {r["cls"]: r for r in rows}
    assert by["drift"]["n"] == 1 and by["drift"]["settled"] == 0
    assert by["floor"]["n"] == 1 and by["floor"]["settled"] == 0
    text = rl.render(rows, days=7, stake_usd=6.4, n_refusals=2)
    assert "0 settled twins yet" in text and "2 refusals, 0 with a settled paper twin" in text


def test_a_refunded_twin_is_not_a_settlement():
    ref = [{"ts": T, "trader": W, "token": "TOK", "reason": "r", "cls": "drift", "price": 0.5, "title": "m"}]
    rows = rl.table(rl.join(ref, [Pos(W, "TOK", T, 0.5, won=False, refunded=True)], []), stake_usd=6.4)
    assert rows[0]["settled"] == 0


def test_the_nearest_twin_and_quote_win():
    ref = [{"ts": T, "trader": W, "token": "TOK", "reason": "r", "cls": "drift", "price": 0.5, "title": "m"}]
    b = [Pos(W, "TOK", T + 3000, 0.4, won=False), Pos(W, "TOK", T + 30, 0.5, won=True)]
    q = [{"target": W, "token_id": "TOK", "their_ts": T + 500, "our_price": 0.9},
         {"target": W, "token_id": "TOK", "their_ts": T + 2, "our_price": 0.52}]
    j = rl.join(ref, b, q)
    assert j[0]["won"] is True and j[0]["our_price"] == 0.52


def test_the_digest_line_names_the_three_biggest_at_our_quote():
    rows = [{"cls": "drift", "n": 40, "settled": 20, "won": 12, "quoted": 20, "net_their": 10.0, "net_our": -12.0, "settled_quoted": 20},
            {"cls": "floor", "n": 300, "settled": 100, "won": 60, "quoted": 90, "net_their": 30.0, "net_our": 25.0, "settled_quoted": 90},
            {"cls": "form", "n": 30, "settled": 10, "won": 5, "quoted": 10, "net_their": 1.0, "net_our": 2.0, "settled_quoted": 10},
            {"cls": "other", "n": 5, "settled": 1, "won": 1, "quoted": 1, "net_their": 3.0, "net_our": 3.0, "settled_quoted": 1},
            {"cls": "spread", "n": 9, "settled": 0, "won": 0, "quoted": 0, "net_their": 0.0, "net_our": 0.0, "settled_quoted": 0}]
    line = rl.line(rows, days=7)
    assert line.startswith("🧾 refusals 7d: floor 300 (+25 at our quote), drift 40 (-12 at our quote), other 5")
    assert rl.line([rows[-1]], days=7) == ""


def test_the_baseline_is_written_once(tmp_path):
    p = str(tmp_path / rl.BASELINE_FILE)
    assert rl.write_baseline_once([{"cls": "x"}], days=7, now=T, path=p) is True
    assert rl.write_baseline_once([{"cls": "y"}], days=7, now=T + 1, path=p) is False
    assert json.loads(open(p).read())["rows"] == [{"cls": "x"}]


def test_report_reads_the_three_files_and_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(rl.CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(CONFIG, "copy_paper_b_ledger", str(tmp_path / "b.jsonl"))
    (tmp_path / "trade-history.jsonl").write_text(json.dumps(_skip("2026-10-01T05:00:00Z", "market quality: Price drift too high")) + "\n")
    from src.copy_trading import shadow_quote
    monkeypatch.setattr(shadow_quote, "load_rows", lambda since_ts=0.0: [])
    rep = rl.report(days=7, now=rl._ts("2026-10-01T12:00:00Z"), stake_usd=6.4)
    assert rep["n"] == 1 and rep["rows"][0]["cls"] == "drift" and rep["baseline_written"] is True
    assert "Refusals, last 7d" in rep["text"]
    # a torn ledger path is a measured "not measured", never a raise
    monkeypatch.setattr(rl, "load_refusals", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("torn")))
    rep2 = rl.report(days=7, now=T)
    assert rep2["rows"] == [] and "not measured" in rep2["text"]
