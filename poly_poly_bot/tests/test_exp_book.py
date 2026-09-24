"""The experiment process (s-ye5990): control = book B, treatment = B plus
the card, one feed, the flag on around the treatment only, every write
under the card's directory."""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib

import pytest

from src.config import CONFIG
from src.copy_trading import exp_flag

_SPEC = importlib.util.spec_from_file_location("exp_book", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "exp_book.py")
eb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(eb)

NOW = 1_790_300_000.0


@pytest.fixture
def box(tmp_path, monkeypatch):
    real = tmp_path / "real"; real.mkdir()
    card_dir = tmp_path / "exp" / "min150"; card_dir.mkdir(parents=True)
    (real / "copy_watchlist.json").write_text(json.dumps({"wallets": [{"address": "0xW1"}]}))
    (real / "copy_watchlist_b_extra.json").write_text(json.dumps({"wallets": []}))
    (real / "copy_blacklist_b.json").write_text(json.dumps({"0xbad": {"until": 0}, "0xold": {"until": NOW - 1}}))
    monkeypatch.setattr(CONFIG, "copy_paper_min_usd", 300.0)
    monkeypatch.setattr(CONFIG, "copy_paper_feed_min_usd", 100.0)
    card = {"id": "min150", "status": "live", "knobs": {"min_usd": 150.0}, "flag": "", "started_ts": NOW}
    (card_dir / "card.json").write_text(json.dumps(card))
    return {"real": real, "card_dir": card_dir, "card": card}


class _Runner:
    """Stands in for CopyPaperRunner: records the flag state at each cycle."""
    made = []

    def __init__(self, **kw):
        self.kw = kw
        self.cycle_interval_s = 1
        self.seen = []
        _Runner.made.append(self)

    def wallets(self):
        return ["0xw1"]

    def run_once(self):
        self.seen.append(exp_flag.active())
        return type("S", (), {"opened": 0, "resolved": 0})()


def test_build_is_book_b_plus_the_card_with_paths_under_the_card(box, monkeypatch):
    from src.copy_trading import copy_paper_runner
    _Runner.made = []
    monkeypatch.setattr(copy_paper_runner, "CopyPaperRunner", _Runner)
    control, treatment = eb.build(box["card"], str(box["card_dir"]), real_data_dir=str(box["real"]),
                                  feed=object(), book_fetcher=lambda t: [], resolver=lambda c: None, now=lambda: NOW)
    ck, tk = control.kw, treatment.kw
    assert ck["min_usd"] == 300.0 and tk["min_usd"] == 150.0
    assert ck["strategy"] == tk["strategy"] == "B" and ck["fill_at_their_price_bps"] == tk["fill_at_their_price_bps"]
    assert ck["ledger_path"] == str(box["card_dir"] / "control.jsonl") and tk["ledger_path"] == str(box["card_dir"] / "treatment.jsonl")
    assert ck["era_state_path"].startswith(str(box["card_dir"])) and tk["era_state_path"] != ck["era_state_path"]
    assert ck["watchlist_path"] == str(box["real"] / "copy_watchlist.json")
    assert ck["gate_history_path"] == str(box["real"] / "gate-history.jsonl")
    assert ck["blacklist_provider"]() == {"0xbad"}, "B's blacklist, read from the real data dir, expiry honoured"
    others = {k: v for k, v in tk.items() if k not in ("min_usd", "ledger_path", "era_state_path")}
    assert others == {k: v for k, v in ck.items() if k not in ("min_usd", "ledger_path", "era_state_path")}


def test_the_flag_is_on_for_the_treatment_cycle_only(box):
    c, t = _Runner(), _Runner()
    eb.cycle({**box["card"], "flag": "wide_band"}, c, t)
    assert c.seen == [frozenset()] and t.seen == [frozenset({"wide_band"})]
    assert not exp_flag.on("wide_band"), "off after"

    class Boom(_Runner):
        def run_once(self):
            raise RuntimeError("x")
    with pytest.raises(RuntimeError):
        eb.cycle({**box["card"], "flag": "wide_band"}, c, Boom())
    assert not exp_flag.on("wide_band"), "off even when the treatment blows up"


def test_run_stops_when_the_card_is_no_longer_live_and_writes_only_under_the_card(box, monkeypatch, tmp_path):
    from src.copy_trading import copy_paper_runner
    _Runner.made = []
    monkeypatch.setattr(copy_paper_runner, "CopyPaperRunner", _Runner)
    slept = []
    clock = {"t": NOW}

    def sleep(s):
        slept.append(s); clock["t"] += s
        if len(slept) == 2:
            (box["card_dir"] / "card.json").write_text(json.dumps({**box["card"], "status": "kill"}))
    logs = []
    before = {str(p) for p in tmp_path.rglob("*")}
    n = eb.run(str(box["card_dir"] / "card.json"), real_data_dir=str(box["real"]), sleep=sleep, now=lambda: clock["t"],
               log=logs.append, feed=object(), book_fetcher=lambda t: [], resolver=lambda c: None)
    assert n == 2 and slept == [1, 1]
    hb = json.loads((box["card_dir"] / "heartbeat.json").read_text())
    assert hb["cycles"] == 2 and hb["note"] == "stopped: card is kill" and hb["pid"] == os.getpid()
    assert any("is kill: stopping" in l for l in logs)
    new = {str(p) for p in tmp_path.rglob("*")} - before
    assert new and all(str(box["card_dir"]) in p for p in new), f"wrote outside the card: {new}"
    assert eb.run(str(box["card_dir"] / "card.json"), real_data_dir=str(box["real"]), log=logs.append) == 0, "a concluded card does not run"


def test_main_refuses_a_key_in_the_environment(box, monkeypatch, capsys):
    monkeypatch.setenv("PRIVATE_KEY", "0xdeadbeef")
    assert eb.main(["--card", str(box["card_dir"] / "card.json"), "--max-rss-mb", "0"]) == 2
    out = capsys.readouterr().out
    assert "refusing to run with PRIVATE_KEY" in out and "deadbeef" not in out
