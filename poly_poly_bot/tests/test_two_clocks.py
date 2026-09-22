"""Two clocks on every followed fill (s-qbzbrw, 2026-09-22).

The chain runs as a shadow next to the data api: both stamp the same trade
id, the report joins them, and the bot flips the chain to primary only on
its own evidence, once, and says so once.
"""
from __future__ import annotations

import json

import pytest

from src.config import CONFIG
from src.copy_trading import two_clocks as tc
from src.copy_trading.trade_ids import canonical_trade_id, normalize_tx_hash

NOW = 1_789_400_000.0


@pytest.fixture
def clocks_env(tmp_path, monkeypatch):
    from src.copy_trading import ops_watch
    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(tc.CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(ops_watch.CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(tc, "_FORCE", "")
    monkeypatch.setattr(tc, "_noted", None)
    return tmp_path


def _fill(i, api_lag=18.0, chain_lag=4.0, chain=True, api=True):
    tid = f"0x{i:064x}-tok{i}-BUY"
    their = NOW + i * 60
    if chain:
        tc.note("onchain", tid, their_ts=their, seen_at=their + chain_lag, target="0xZ", token_id=f"tok{i}")
    if api:
        tc.note("data-api", tid, their_ts=their, seen_at=their + api_lag, target="0xZ", token_id=f"tok{i}")
    return tid


def test_one_id_from_either_spelling_of_the_hash():
    """web3 8 / hexbytes 2 hand back hex() without 0x; the api has it."""
    class H:
        def hex(self):
            return "abc123"
    assert normalize_tx_hash(H()) == "0xabc123"
    assert normalize_tx_hash("0xABC123") == "0xabc123"
    assert normalize_tx_hash(b"\xab\xc1\x23") == "0xabc123"
    assert normalize_tx_hash("") == "" and normalize_tx_hash(None) == ""
    assert canonical_trade_id(H(), "77", "buy") == canonical_trade_id("0xABC123", 77, "BUY") == "0xabc123-77-BUY"


def test_the_report_joins_by_id_and_counts_what_did_not_match(clocks_env):
    for i in range(6):
        _fill(i)
    _fill(10, chain=False)              # the chain missed one
    _fill(11, api=False)                # the api missed one
    tid = _fill(12)
    tc.note("onchain", tid, their_ts=NOW, seen_at=NOW + 5)   # the same id again from one source: not written
    r = tc.report(0.0, now=NOW + 3600)
    assert (r["matched"], r["api_only"], r["chain_only"], r["dupes"]) == (7, 1, 1, 0)
    assert sum(1 for x in tc.load_rows() if x["id"] == tid and x["source"] == "onchain") == 1, "note is idempotent"
    assert r["api_lag_p50"] == 18.0 and r["chain_lag_p50"] == 4.0 and r["gain_p50"] == 14.0
    assert r["missed_frac"] == pytest.approx(1 / 8)
    assert "matched" in tc.line(0.0, now=NOW + 3600) and "shadow" in tc.line(0.0, now=NOW + 3600)


def test_no_rows_is_said_plainly(clocks_env):
    assert tc.line() == "two clocks: no fills stamped yet"
    ok, why, _ = tc.cutover_ready(now=NOW)
    assert ok is False and "0 matched" in why


def test_cutover_needs_enough_matched_no_dupes_and_a_real_gain(clocks_env, monkeypatch):
    monkeypatch.setattr(tc, "SHADOW_MIN_MATCHED", 5)
    for i in range(4):
        _fill(i)
    assert tc.cutover_ready(now=NOW)[0] is False, "4 of 5 matched"
    _fill(4)
    ok, why, ev = tc.cutover_ready(now=NOW)
    assert ok is True and "chain earlier by 14.0s" in why and ev["dupes"] == 0
    # a replayed row (a restart re-reading its last chunk) is counted, never a reason
    import json as _json
    with open(clocks_env / tc.ROWS_FILE, "a", encoding="utf-8") as f:
        f.write(_json.dumps({"v": tc.ROW_VERSION, "ts": NOW, "source": "onchain", "id": f"0x{0:064x}-tok0-BUY",
                             "their_ts": NOW, "seen_at": NOW + 9, "lag_s": 9.0}) + "\n")
    r = tc.report(0.0, now=NOW)
    assert r["dupes"] == 1 and tc.cutover_ready(now=NOW)[0] is True
    assert "replayed rows 1" in tc.line(0.0, now=NOW)


def test_cutover_refuses_when_the_chain_misses_too_much_or_is_not_earlier(clocks_env, monkeypatch):
    monkeypatch.setattr(tc, "SHADOW_MIN_MATCHED", 5)
    for i in range(5):
        _fill(i)
    _fill(20, chain=False)
    ok, why, _ = tc.cutover_ready(now=NOW)
    assert ok is False and "missed" in why
    # a chain that is not earlier is no win
    for i in range(30, 36):
        _fill(i, api_lag=3.0, chain_lag=9.0, chain=True, api=True)
    # rebuild cleanly: only slow-chain fills (the idempotency set follows the file)
    (clocks_env / tc.ROWS_FILE).unlink()
    monkeypatch.setattr(tc, "_noted", None)
    for i in range(30, 36):
        _fill(i, api_lag=3.0, chain_lag=9.0)
    ok, why, _ = tc.cutover_ready(now=NOW)
    assert ok is False and "not earlier" in why


def test_the_flip_happens_once_and_is_pinned_by_env(clocks_env, monkeypatch):
    monkeypatch.setattr(tc, "SHADOW_MIN_MATCHED", 5)
    for i in range(5):
        _fill(i)
    sent: list = []
    assert tc.is_primary() is False
    row = tc.maybe_cutover(send=sent.append, now=NOW)
    assert row is not None and row["kind"] == "onchain_primary" and tc.is_primary() is True
    assert len(sent) == 1 and "primary" in sent[0] and "—" not in sent[0]
    assert tc.maybe_cutover(send=sent.append, now=NOW + 1) is None and len(sent) == 1, "once"
    assert json.load(open(clocks_env / tc.PRIMARY_FILE))["primary"] is True
    monkeypatch.setattr(tc, "_FORCE", "true")
    assert tc.is_primary() is False, "ONCHAIN_SHADOW=true pins the shadow whatever the file says"
    monkeypatch.setattr(tc, "_FORCE", "false")
    assert tc.is_primary() is True


def test_an_unreadable_flag_file_means_shadow(clocks_env):
    (clocks_env / tc.PRIMARY_FILE).write_text("{not json")
    assert tc.is_primary() is False


def test_a_pinned_shadow_never_flips_nor_announces(clocks_env, monkeypatch):
    """ONCHAIN_SHADOW=true is the rollback control deploy.yml advertises: with
    it set, a ready fixture must not write the flag, post a receipt or send,
    however many guard passes run."""
    monkeypatch.setattr(tc, "SHADOW_MIN_MATCHED", 5)
    for i in range(5):
        _fill(i)
    monkeypatch.setattr(tc, "_FORCE", "true")
    sent: list = []
    for _ in range(3):
        assert tc.maybe_cutover(send=sent.append, now=NOW) is None
    assert sent == [] and not (clocks_env / tc.PRIMARY_FILE).exists()
    from src.copy_trading import ops_watch
    assert [r["kind"] for r in ops_watch.ledger_rows()] == []


def test_rows_from_an_older_meaning_count_for_nothing(clocks_env):
    """The first day's chain rows carried the wall clock as the fill time;
    they stay on disk and are ignored by every report and by the cutover."""
    import json as _json
    with open(clocks_env / tc.ROWS_FILE, "a", encoding="utf-8") as f:
        f.write(_json.dumps({"ts": NOW, "source": "onchain", "id": "x", "their_ts": NOW, "seen_at": NOW + 1, "lag_s": 1.0}) + "\n")
        f.write(_json.dumps({"v": 1, "ts": NOW, "source": "data-api", "id": "x", "their_ts": NOW, "seen_at": NOW + 2, "lag_s": 2.0}) + "\n")
    assert tc.load_rows() == [] and tc.line() == "two clocks: no fills stamped yet"
    _fill(1)
    assert len(tc.load_rows()) == 2 and all(r["v"] == tc.ROW_VERSION for r in tc.load_rows())
