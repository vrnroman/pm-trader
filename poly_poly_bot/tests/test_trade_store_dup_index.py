"""get_duplicate_count reads the history incrementally (2026-10-06: the full
parse per trade was 47% of the event loop and the executor fell behind)."""

import json
import os

from src.copy_trading import trade_store


def _row(**kw):
    return json.dumps(kw) + "\n"


def _old_full_scan(path, market_key, side):
    n = 0
    for line in open(path):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("side") == side and (rec.get("market") == market_key
                                        or rec.get("condition_id") == market_key):
            n += 1
    return n


def _setup(tmp_path, monkeypatch):
    path = tmp_path / "trade-history.jsonl"
    monkeypatch.setattr(trade_store, "_HISTORY_FILE", str(path))
    monkeypatch.setattr(trade_store, "_dup_index",
                        {"path": None, "ino": None, "head": b"", "offset": 0, "counts": {}})
    return path


def test_counts_by_market_or_condition_id_once_per_row(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    path.write_text(_row(side="BUY", market="Will X?", condition_id="0xc1")
                    + _row(side="BUY", market="Will X?", condition_id="0xc1")
                    + _row(side="SELL", market="Will X?", condition_id="0xc1")
                    + _row(side="BUY", market="0xc1", condition_id="0xc1")
                    + "not json\n")
    for key in ("Will X?", "0xc1", "nope"):
        for side in ("BUY", "SELL"):
            assert trade_store.get_duplicate_count(key, side) == _old_full_scan(path, key, side)
    assert trade_store.get_duplicate_count("0xc1", "BUY") == 3
    assert trade_store.get_duplicate_count("", "BUY") == 0


def test_appends_are_picked_up_without_rereading(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    path.write_text(_row(side="BUY", market="M"))
    assert trade_store.get_duplicate_count("M", "BUY") == 1
    with open(path, "a") as f:
        f.write(_row(side="BUY", market="M"))
    assert trade_store.get_duplicate_count("M", "BUY") == 2
    assert trade_store._dup_index["offset"] == os.path.getsize(path)


def test_half_written_row_waits_for_its_newline(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    full = _row(side="BUY", market="M")
    path.write_text(full + full[:10])
    assert trade_store.get_duplicate_count("M", "BUY") == 1
    with open(path, "a") as f:
        f.write(full[10:])
    assert trade_store.get_duplicate_count("M", "BUY") == 2


def test_truncation_rebuilds_even_when_the_file_regrows(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    path.write_text(_row(side="BUY", market="OLD") * 3)
    assert trade_store.get_duplicate_count("OLD", "BUY") == 3
    # reset_pnl truncates in place; new rows land before the next lookup.
    with open(path, "w") as f:
        f.write(_row(side="BUY", market="NEW-MARKET-LONGER") * 4)
    assert trade_store.get_duplicate_count("OLD", "BUY") == 0
    assert trade_store.get_duplicate_count("NEW-MARKET-LONGER", "BUY") == 4


def test_missing_file_is_zero(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert trade_store.get_duplicate_count("M", "BUY") == 0


def test_append_trade_history_rows_are_counted(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    assert trade_store.get_duplicate_count("Mkt", "BUY") == 0
    with open(path, "a") as f:
        f.write(_row(side="BUY", market="Mkt", condition_id="0xabc"))
    assert trade_store.get_duplicate_count("0xabc", "BUY") == 1
