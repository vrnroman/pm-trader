"""The paper-copy runner drops blacklisted (auto-demoted) wallets immediately."""

from __future__ import annotations

import json
import os

from src.copy_trading import promotion_state as ps
from src.copy_trading.copy_paper_runner import CopyPaperRunner


def test_wallets_excludes_blacklisted(tmp_path, monkeypatch):
    monkeypatch.setenv("COPY_BLACKLIST_STORE", str(tmp_path / "bl.json"))
    ps.clear_cache()
    ps.add_blacklist("0xBBB", until=0, now=1000.0)   # permanent cooldown

    wl = str(tmp_path / "wl.json")
    json.dump({"targets": [{"wallet": "0xAAA"}, {"wallet": "0xBBB"}]}, open(wl, "w"))
    r = CopyPaperRunner(
        ledger_path=str(tmp_path / "l.jsonl"),
        watchlist_path=wl,
        detector_factory=lambda *a, **k: (lambda: []),
        book_fetcher=lambda t: [],
        resolver=lambda c: None,
    )
    try:
        assert r.wallets() == ["0xAAA"]
    finally:
        ps.clear_cache()


def test_no_blacklist_keeps_all(tmp_path, monkeypatch):
    monkeypatch.setenv("COPY_BLACKLIST_STORE", str(tmp_path / "bl.json"))
    ps.clear_cache()
    wl = str(tmp_path / "wl.json")
    json.dump({"targets": [{"wallet": "0xAAA"}, {"wallet": "0xBBB"}]}, open(wl, "w"))
    r = CopyPaperRunner(
        ledger_path=str(tmp_path / "l.jsonl"),
        watchlist_path=wl,
        detector_factory=lambda *a, **k: (lambda: []),
        book_fetcher=lambda t: [],
        resolver=lambda c: None,
    )
    try:
        assert r.wallets() == ["0xAAA", "0xBBB"]
    finally:
        ps.clear_cache()
