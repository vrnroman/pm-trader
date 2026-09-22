"""Error fingerprints (s-qbzbrw): the deterministic step before the model."""
from __future__ import annotations

import pytest

from src.config import CONFIG
from src.copy_trading import ops_fingerprint as fp

NOW = 1_789_500_000.0


@pytest.fixture
def fp_env(tmp_path, monkeypatch):
    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(fp.CONFIG, "data_dir", str(tmp_path))
    return tmp_path


def test_two_occurrences_of_one_fault_share_a_fingerprint():
    a = "2026-09-19 23:41:55 WARNING [form] could not read 0x00110b8e: activity read incomplete (throttled)"
    b = "2026-09-20 03:12:01 WARNING [form] could not read 0xf49614e6: activity read incomplete (throttled)"
    assert fp.fingerprint(a) == fp.fingerprint(b)
    assert fp.normalize(a) == "WARNING [form] could not read <hex>: activity read incomplete (throttled)"
    c = "2026-09-22 12:00:00 ERROR [exec] Order placement returned None for 'Will Udinese Calcio win on 2026-09-07?'"
    d = "2026-09-23 12:00:00 ERROR [exec] Order placement returned None for 'Will Stade Rennais FC 1901 win on 2026-0'"
    assert fp.fingerprint(c) == fp.fingerprint(d)
    e = "2026-09-22 12:00:00 ERROR Onchain poll error: {'code': -32002, 'message': 'request timed out'}"
    assert fp.fingerprint(e) != fp.fingerprint(c), "different faults, different rows"


def test_tracebacks_collapse_on_their_frames():
    a = '  File "/app/src/copy_trading/x.py", line 12, in run'
    b = '  File "/app/src/copy_trading/x.py", line 99, in run'
    assert fp.fingerprint(a) == fp.fingerprint(b)


def test_ingest_wakes_on_new_and_on_a_rate_crossing(fp_env, monkeypatch):
    monkeypatch.setattr(fp, "RATE_HITS", 3)
    line = "2026-09-22 12:00:00 ERROR [x] boom 0xabcdef012345 at 12"
    d, wake = fp.ingest([line], now=NOW)
    key = fp.fingerprint(line)
    assert wake == [key] and d[key]["count"] == 1
    d, wake = fp.ingest([line], now=NOW + 10)
    assert wake == [] and d[key]["count"] == 2, "a known fault is counted, not a wake"
    d, wake = fp.ingest([line], now=NOW + 20)
    assert wake == [key] and d[key]["count"] == 3, "the rate crossing wakes once"
    d, wake = fp.ingest([line], now=NOW + 30)
    assert wake == [], "and not again while above the rate"
    # the window slides: far later, the same fault is below the rate again
    d, wake = fp.ingest([line] * 3, now=NOW + fp.RATE_WINDOW_S + 100)
    assert wake == [key]


def test_proof_is_two_counters_and_silence_is_not_proof(fp_env):
    line = "2026-09-22 12:00:00 ERROR [x] boom"
    fp.ingest([line], now=NOW)
    key = fp.fingerprint(line)
    assert fp.proof(key, now=NOW)[0] == "open"
    assert fp.mark_action(key, "fix", now=NOW + 60, detail="pushed abc123") is True
    assert fp.proof(key, now=NOW + 3600)[0] == "unproven"
    assert "silence is not proof" in fp.proof(key, now=NOW + 3600)[1]
    fp.bump_path_runs(key, 5, now=NOW + 7200)
    state, why = fp.proof(key, now=NOW + 7200)
    assert state == "unproven" and "5 run(s)" in why and "24 h needed" in why
    state, why = fp.proof(key, now=NOW + 60 + fp.PROOF_WINDOW_S)
    assert state == "done" and "0 hits over 5 run(s)" in why
    fp.ingest([line], now=NOW + 60 + fp.PROOF_WINDOW_S + 5)
    assert fp.proof(key, now=NOW + 60 + fp.PROOF_WINDOW_S + 6)[0] == "recurred"
    assert fp.proof("nope", now=NOW)[0] == "unknown"
    assert fp.mark_action("nope", "fix", now=NOW) is False


def test_rows_render_state_and_the_normalised_line(fp_env):
    fp.ingest(["2026-09-22 12:00:00 ERROR [x] boom 7"], now=NOW)
    (row,) = fp.rows(now=NOW + 60)
    assert "x1" in row and "[open:" in row and "ERROR [x] boom N" in row
    assert "—" not in row and "–" not in row


def test_unreadable_table_is_empty_not_a_crash(fp_env):
    (fp_env / fp.TABLE_FILE).write_text("{not json")
    assert fp.read() == {}
    d, wake = fp.ingest(["2026-09-22 12:00:00 ERROR [x] boom"], now=NOW)
    assert len(d) == 1 and len(wake) == 1
