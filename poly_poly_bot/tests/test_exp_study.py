"""Historical studies (s-ye5990): a what-if over the box's own rows as a
who-stays / who-enters / who-leaves table, frozen once, caveat printed."""
from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

from src.config import CONFIG
from src.copy_trading import exp_cards, wallet_form

_SPEC = importlib.util.spec_from_file_location("exp_study", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "exp_study.py")
es = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(es)

NOW = 1_790_300_000.0
DAY = 86400.0


@pytest.fixture
def desk(tmp_path, monkeypatch):
    data = tmp_path / "data"; data.mkdir()
    monkeypatch.setattr(CONFIG, "data_dir", str(data))
    monkeypatch.setattr(CONFIG, "copy_paper_min_usd", 300.0)
    monkeypatch.setattr(wallet_form, "FORM_MIN_N", 3)
    monkeypatch.setattr(wallet_form, "FORM_DAYS", 14.0)
    return data


def acts_for(usd: float, n: int, won_every: int = 2, start: float = NOW - 10 * DAY):
    """n BUYs of ``usd`` at 0.5, each redeemed (won) or not; conditions c0..cn."""
    out = []
    for i in range(n):
        ts = start + i * 3600
        cid = f"c{usd:.0f}-{i}"
        out.append({"type": "TRADE", "side": "BUY", "timestamp": ts, "conditionId": cid, "outcomeIndex": 0,
                    "price": 0.5, "usdcSize": usd, "size": usd / 0.5})
        if i % won_every == 0:
            out.append({"type": "REDEEM", "timestamp": ts + 7200, "conditionId": cid, "usdcSize": usd * 2})
    return out


def test_the_min_usd_study_says_who_stays_enters_leaves_and_freezes_once(desk):
    # w1 bets 400 (in at both floors); w2 bets 200 (in only at 150); w3 bets 50 (out at both)
    rows = {"0xw1": acts_for(400, 6, won_every=1), "0xw2": acts_for(200, 6, won_every=1), "0xw3": acts_for(50, 6)}
    reads = []

    def fetch(w):
        reads.append(w)
        return rows[w], [], wallet_form.Coverage(rows=len(rows[w]), pages=1, oldest_ts=NOW - 12 * DAY, capped=(w == "0xw2"))
    res = {a["conditionId"]: 0 for r in rows.values() for a in r if a["type"] == "TRADE"}
    b_rows = [{"target": w, "closed": True} for w in rows for _ in range(12)]
    rec = es.run("min_usd", {"from": 300, "to": 150}, now=NOW, question="300 to 150?", fetch=fetch,
                 resolve=lambda cid: res.get(cid), b_rows=b_rows, zset_wallets={"0xw1"})
    by = {r["wallet"]: r for r in rec["rows"]}
    assert by["0xw1"]["move"] == "stay" and by["0xw2"]["move"] == "enter" and by["0xw3"]["move"] == "out"
    assert by["0xw2"]["n_from"] == 0 and by["0xw2"]["n_to"] == 6 and by["0xw2"]["roi_to"] == pytest.approx(1.0)
    assert by["0xw2"]["capped"] is True
    t = rec["totals"]
    assert (t["wallets_in_from"], t["wallets_in_to"], t["copies_from"], t["copies_to"]) == (1, 2, 6, 12)
    assert rec["totals_line"].startswith("wallets in 1 -> 2 (stay 1, enter 1, leave 0); copies 6 -> 12")
    assert "3 of 3 wallets studied" in rec["caveat"] and "1 capped, marked *" in rec["caveat"]
    md = es.markdown(rec)
    assert "| enter | 0xw2* |" in md and "## caveat" in md and "—" not in md
    rec2, path, written = es.run_and_freeze("min_usd", {"from": 300, "to": 150}, now=NOW, question="300 to 150?", fetch=fetch,
                                            resolve=lambda cid: res.get(cid), b_rows=b_rows, zset_wallets={"0xw1"})
    assert written and rec2["id"] == rec["id"] and path.endswith(f"{rec['id']}.md")
    _, _, again = es.run_and_freeze("min_usd", {"from": 300, "to": 150}, now=NOW, fetch=fetch,
                                    resolve=lambda cid: res.get(cid), b_rows=b_rows, zset_wallets={"0xw1"})
    assert not again, "frozen once"
    assert exp_cards.studies()[0]["totals_line"] == rec["totals_line"]


def test_an_unread_wallet_is_a_row_not_a_crash_and_the_population_is_capped(desk):
    def fetch(w):
        raise RuntimeError("HTTP 500")
    b_rows = [{"target": f"0xw{i}", "closed": True} for i in range(5) for _ in range(12)]
    rec = es.run("form", {"days": 7, "min_bet": 300}, now=NOW, fetch=fetch, resolve=lambda c: None, b_rows=b_rows,
                 zset_wallets=set(), max_wallets=2)
    assert len(rec["rows"]) == 2 and all(r["move"] == "unread" for r in rec["rows"])
    assert "2 of 5 wallets studied" in rec["caveat"] and rec["totals"]["unread"] == 2


def test_the_wallet_cap_study_reads_book_b_only(desk, monkeypatch):
    monkeypatch.setattr(CONFIG, "copy_paper_b_max_per_wallet_day", 25)
    b_rows = []
    for i in range(30):    # one wallet, 30 copies on one day, the later ones lose
        b_rows.append({"target": "0xw1", "closed": True, "opened_ts": NOW + i * 60, "spent": 10.0,
                       "ideal_pnl": 5.0 if i < 5 else -10.0})
    rec = es.run("wallet_cap", {"from": 25, "to": 3}, now=NOW, b_rows=b_rows, zset_wallets=set())
    r = rec["rows"][0]
    assert r["n_from"] == 25 and r["n_to"] == 3 and r["roi_to"] == pytest.approx(0.5) and r["roi_from"] < 0
    assert r["move"] == "out", "3 copies is under the classifier's floor, and the script says so"
    assert "positive at their price on at least" in rec["caveat"]


def test_the_menu_is_closed(desk):
    with pytest.raises(ValueError):
        es.run("stake_size", {}, now=NOW, b_rows=[], zset_wallets=set())
    with pytest.raises(ValueError):
        es.run("wallet_cap", {}, now=NOW, b_rows=[], zset_wallets=set())
    assert any(l.strip().startswith("min_usd:") for l in es.menu_lines())


def test_a_study_that_varies_nothing_is_refused(desk, monkeypatch):
    monkeypatch.setattr(CONFIG, "copy_paper_first_entry_only", True)
    monkeypatch.setattr(CONFIG, "copy_paper_b_max_per_wallet_day", 25)
    with pytest.raises(ValueError, match="varies nothing"):
        es.run("first_entry", {"to": True}, now=NOW, fetch=lambda w: ([], [], None), resolve=lambda c: None, b_rows=[], zset_wallets=set())
    with pytest.raises(ValueError, match="varies nothing"):
        es.run("min_usd", {"from": 300, "to": 300}, now=NOW, fetch=lambda w: ([], [], None), resolve=lambda c: None, b_rows=[], zset_wallets=set())
    monkeypatch.setattr(CONFIG, "live_max_per_wallet_day", 3)
    with pytest.raises(ValueError, match="varies nothing"):
        es.run("wallet_cap", {"to": 3}, now=NOW, b_rows=[], zset_wallets=set())


def test_the_wallet_cap_study_starts_from_the_live_cap(desk, monkeypatch):
    """2026-09-25: the analyst asked "3 vs 5"; the study ran book B's 25 vs 5
    and could not answer. The baseline is the cap real money runs at, and
    nothing past book B's own cap can be read from its rows."""
    monkeypatch.setattr(CONFIG, "copy_paper_b_max_per_wallet_day", 25)
    monkeypatch.setattr(CONFIG, "live_max_per_wallet_day", 3)
    b_rows = [{"target": "0xw1", "closed": True, "opened_ts": NOW + i * 60, "spent": 10.0,
               "ideal_pnl": 5.0 if i < 3 else -10.0} for i in range(30)]
    rec = es.run("wallet_cap", {"to": 5}, now=NOW, b_rows=b_rows, zset_wallets=set())
    assert rec["settings"] == {"from": {"cap": 3}, "to": {"cap": 5}}
    r = rec["rows"][0]
    assert r["n_from"] == 3 and r["n_to"] == 5 and r["roi_from"] == pytest.approx(0.5) and r["roi_to"] < 0
    with pytest.raises(ValueError, match="book B caps at 25"):
        es.run("wallet_cap", {"to": 30}, now=NOW, b_rows=b_rows, zset_wallets=set())
