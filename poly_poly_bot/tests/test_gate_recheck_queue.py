"""Tests for the deferred-gate-check file queue (survives restart)."""

from __future__ import annotations

from src.copy_trading import gate_recheck_queue as q


def test_enqueue_and_pending(tmp_path):
    p = str(tmp_path / "queue.json")
    q.clear_cache()
    assert q.enqueue(p, "0xA", {"wallet": "0xA"}, theories=["1b"], copy_n=3, now=1.0) is True
    entries = q.pending(p)
    assert len(entries) == 1
    assert entries[0]["wallet"] == "0xA"
    assert entries[0]["dossier"] == {"wallet": "0xA"}
    assert entries[0]["theories"] == ["1b"]


def test_enqueue_is_idempotent_per_wallet(tmp_path):
    p = str(tmp_path / "queue.json")
    q.clear_cache()
    q.enqueue(p, "0xA", {"v": 1}, now=1.0)
    q.enqueue(p, "0xA", {"v": 2}, now=2.0)      # same wallet -> refresh, not duplicate
    entries = q.pending(p)
    assert len(entries) == 1 and entries[0]["dossier"] == {"v": 2}


def test_remove(tmp_path):
    p = str(tmp_path / "queue.json")
    q.clear_cache()
    q.enqueue(p, "0xA", {}, now=1.0)
    q.enqueue(p, "0xB", {}, now=1.0)
    q.remove(p, ["0xA"])
    assert [e["wallet"] for e in q.pending(p)] == ["0xB"]


def test_survives_restart(tmp_path):
    # a fresh module cache (simulating a process restart) still reads the file.
    p = str(tmp_path / "queue.json")
    q.clear_cache()
    q.enqueue(p, "0xA", {"wallet": "0xA"}, now=1.0)
    q.clear_cache()                              # drop in-memory cache = "restart"
    assert [e["wallet"] for e in q.pending(p)] == ["0xA"]


def test_missing_and_corrupt_are_safe(tmp_path):
    assert q.pending(None) == []
    assert q.pending(str(tmp_path / "nope.json")) == []
    assert q.enqueue(None, "0xA", {}) is False
    bad = tmp_path / "bad.json"
    bad.write_text("not json{")
    q.clear_cache()
    assert q.pending(str(bad)) == []             # corrupt -> empty, no raise
    q.remove(str(bad), ["0xA"])                  # must not raise
