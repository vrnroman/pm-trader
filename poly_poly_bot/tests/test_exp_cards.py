"""Experiment cards (s-ye5990): bars in numbers on day 0, a verdict by code
on day N, one live at a time, frozen studies, a disk cap."""
from __future__ import annotations

import json

import pytest

from src.config import CONFIG
from src.copy_trading import exp_cards

NOW = 1_790_300_000.0     # 2026-09-25 03:33 UTC, a fixed instant


@pytest.fixture
def desk(tmp_path, monkeypatch):
    data = tmp_path / "data"; data.mkdir()
    monkeypatch.setattr(CONFIG, "data_dir", str(data))
    monkeypatch.setattr(CONFIG, "copy_paper_b_ledger", str(data / "book_b.jsonl"))
    return data


def card(**kw) -> dict:
    base = {"id": "min150", "title": "slice floor 150", "hypothesis": "37 declined winners at 150..300 last week",
            "knobs": {"min_usd": 150}, "win_bar": {"roi_pp": 2.0, "min_n": 30}, "kill_bar": {"roi_pp": -3.0, "min_n": 20},
            "max_days": 14}
    base.update(kw)
    return base


def cmp_of(*, t_roi: float, c_roi: float, n: int, n_c: int = 40, valid: bool = True) -> dict:
    return {"a": {"ideal_roi_net": c_roi, "n_settled": n_c}, "b": {"ideal_roi_net": t_roi, "n_settled": n},
            "validity": {"valid": valid, "reasons": [] if valid else ["book B had a 50h zero-open window"]}}


# ---- validation ----

def test_a_card_needs_bars_in_numbers_and_a_change(desk):
    ok, why, c = exp_cards.validate(card())
    assert ok and c["status"] == "queued" and c["knobs"] == {"min_usd": 150.0} and c["max_days"] == 14
    assert not exp_cards.validate(card(win_bar={"roi_pp": 1.0, "min_n": 30}))[0], "win bar under the floor"
    assert not exp_cards.validate(card(win_bar={"roi_pp": 2.0, "min_n": 5}))[0], "too few copies"
    assert not exp_cards.validate(card(kill_bar={"roi_pp": 1.0}))[0], "kill bar above zero"
    assert not exp_cards.validate(card(max_days=60))[0]
    assert not exp_cards.validate(card(knobs={}))[0], "no change"
    assert not exp_cards.validate(card(knobs={"ledger_path": "x"}))[0]
    assert not exp_cards.validate(card(id="Bad Id"))[0]
    assert "—" not in exp_cards.validate(card(title="a — b"))[2]["title"]


def test_a_code_change_must_sit_behind_its_flag(desk):
    diff = "--- a/poly_poly_bot/src/copy_trading/patterns.py\n+++ b/poly_poly_bot/src/copy_trading/patterns.py\n@@ -1 +1 @@\n-a\n+b\n"
    assert not exp_cards.validate(card(knobs={}, diff=diff))[0], "no flag"
    assert not exp_cards.validate(card(knobs={}, diff=diff, flag="wide_band"))[0], "flag not read"
    ok, why, c = exp_cards.validate(card(knobs={}, diff=diff.replace("+b", '+if exp_flag.on("wide_band"): b'), flag="wide_band"))
    assert ok and c["flag"] == "wide_band"


# ---- one live at a time ----

def test_one_live_experiment_the_rest_queue(desk):
    ok, why, a = exp_cards.create(card(), NOW)
    assert ok and a["status"] == "queued"
    assert not exp_cards.create(card(), NOW)[0], "written once"
    ok, msg = exp_cards.launch("min150", NOW)
    assert ok and exp_cards.live_card()["id"] == "min150" and "14 days" in msg
    ok, _, b = exp_cards.create(card(id="min150-first", knobs={"min_usd": 150, "first_entry_only": True}, parent_id="min150"), NOW + 1)
    assert ok
    ok, why = exp_cards.launch("min150-first", NOW + 2)
    assert not ok and "one experiment at a time" in why
    assert exp_cards.next_queued()["id"] == "min150-first"
    events = [(r["id"], r["event"]) for r in exp_cards.backlog_rows()]
    assert events == [("min150", "queued"), ("min150", "live"), ("min150-first", "queued")]


# ---- the verdict, by code ----

def test_the_bars_decide_in_the_cards_order(desk):
    c = exp_cards.validate(card())[2]; c["started_ts"] = NOW
    v = exp_cards.verdict
    assert v(c, cmp_of(t_roi=0.05, c_roi=0.01, n=10), NOW + 86400)["status"] == "live"
    assert v(c, cmp_of(t_roi=0.05, c_roi=0.01, n=30), NOW + 86400)["status"] == "win"
    assert v(c, cmp_of(t_roi=-0.02, c_roi=0.01, n=20), NOW + 86400)["status"] == "kill"
    # kill is checked before win: a bar that is both is a kill
    both = exp_cards.verdict({**c, "kill_bar": {"roi_pp": 5.0 * -1, "min_n": 10}}, cmp_of(t_roi=-0.06, c_roi=0.0, n=30), NOW)
    assert both["status"] == "kill"
    # the harness voids first, whatever the treatment says
    h = v(c, cmp_of(t_roi=0.10, c_roi=0.01, n=40), NOW + 86400, harness_pp=2.0, harness_n=25)
    assert h["status"] == "void" and "harness" in h["why"]
    assert v(c, cmp_of(t_roi=0.10, c_roi=0.01, n=40), NOW + 86400, harness_pp=2.0, harness_n=5)["status"] == "win", "too few to judge the harness"
    # a stalled book voids after day 2, not on day 1
    assert v(c, cmp_of(t_roi=0.0, c_roi=0.0, n=5, valid=False), NOW + 86400)["status"] == "live"
    assert v(c, cmp_of(t_roi=0.0, c_roi=0.0, n=5, valid=False), NOW + 3 * 86400)["status"] == "void"
    assert all("—" not in x["why"] for x in (h,))


def test_the_clock_extends_once_when_starved_then_voids_or_kills(desk):
    c = exp_cards.validate(card())[2]; c["started_ts"] = NOW
    late = NOW + 14 * 86400
    e = exp_cards.verdict(c, cmp_of(t_roi=0.03, c_roi=0.01, n=12), late)
    assert e["status"] == "extend"
    exp_cards.create(card(), NOW); exp_cards.launch("min150", NOW)
    live = exp_cards.load("min150")
    exp_cards.apply_verdict(live, e, late)
    live = exp_cards.load("min150")
    assert live["extended"] and live["max_days"] == 21 and live["status"] == "live"
    assert exp_cards.verdict(live, cmp_of(t_roi=0.03, c_roi=0.01, n=12), late)["status"] == "live", "the extension bought a week"
    assert exp_cards.verdict(live, cmp_of(t_roi=0.03, c_roi=0.01, n=12), late + 7 * 86400)["status"] == "void", "starved twice"
    k = exp_cards.verdict(live, cmp_of(t_roi=0.02, c_roi=0.01, n=35), late + 7 * 86400)
    assert k["status"] == "kill" and "did not clear the win bar" in k["why"]
    exp_cards.apply_verdict(live, k, late + 7 * 86400)
    done = exp_cards.load("min150")
    assert done["status"] == "kill" and done["concluded_ts"] == late + 7 * 86400
    exp_cards.apply_verdict(done, {"status": "win", "why": "late"}, late + 8 * 86400)
    assert exp_cards.load("min150")["status"] == "kill", "a concluded card is never touched again"
    assert [r["event"] for r in exp_cards.backlog_rows()][-2:] == ["extended", "kill"]


def _ledger(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for i, (target, roi, opened, closed) in enumerate(rows):
            spent = 20.0
            f.write(json.dumps({"copy_id": f"{path.name}-{i}", "target": target, "condition_id": f"c{i}", "token_id": f"t{i}",
                                "outcome_index": 0, "category": "sports", "their_price": 0.5, "entry_price": 0.5,
                                "shares": 40.0, "spent": spent, "drag_bps": 100, "opened_ts": opened, "closed": True,
                                "won": roi > 0, "pnl": roi * spent, "ideal_pnl": roi * spent, "closed_ts": closed}) + "\n")


def test_the_daily_check_reads_the_ledgers_once_a_day_and_writes_the_journal(desk):
    exp_cards.create(card(win_bar={"roi_pp": 2.0, "min_n": 10}, kill_bar={"roi_pp": -3.0, "min_n": 10}), NOW)
    exp_cards.launch("min150", NOW)
    d = desk / "exp" / "min150"
    day = NOW + 5 * 86400
    rows = [("0xw1" if i % 2 else "0xw2", 0.3 if i % 3 else -1.0, NOW + 8 * 3600 * i, NOW + 8 * 3600 * i + 7200) for i in range(12)]
    _ledger(d / "control.jsonl", rows)
    _ledger(d / "treatment.jsonl", [(t, r + 0.2, o, c) for t, r, o, c in rows])
    _ledger(desk / "book_b.jsonl", rows)    # the harness: control == book B
    row = exp_cards.check(exp_cards.load("min150"), day)
    assert row["status"] == "win" and row["n"] == 12 and row["delta_pp"] == pytest.approx(20.0, abs=0.01)
    assert row["harness_pp"] == 0.0
    again = exp_cards.check(exp_cards.load("min150"), day + 3600)
    assert again["ts"] == row["ts"] and len(exp_cards.journal_rows("min150")) == 1, "once a day"
    assert exp_cards.load("min150")["status"] == "win"
    line = exp_cards.line(day + 3600)
    assert line.startswith("\U0001f9ea exp min150 WIN:") and "—" not in line
    t = exp_cards.table(exp_cards.load("min150"))
    assert t[0] == "exp min150: slice floor 150" and any("WIN" in l and "+20.0 pp" in l for l in t)


def test_the_line_is_empty_when_nothing_runs_and_shows_the_live_card(desk):
    assert exp_cards.line(NOW) == ""
    exp_cards.create(card(), NOW); exp_cards.launch("min150", NOW)
    assert exp_cards.line(NOW + 3600) == "\U0001f9ea exp min150 day 0/14: no check yet"
    exp_cards.journal("min150", {"status": "live", "why": "w", "delta_pp": 1.2, "n": 9, "n_control": 11, "days": 4.0,
                                 "treatment": {"ideal_roi_net": 0.031, "n_settled": 9}, "control": {"ideal_roi_net": 0.012, "n_settled": 11}}, NOW + 4 * 86400)
    exp_cards.create(card(id="next-one"), NOW + 1)
    line = exp_cards.line(NOW + 4 * 86400)
    assert line == "\U0001f9ea exp min150 day 4/14: treatment +3.1% vs control +1.2% at their price (n 9/30), win at +2, kill at -3; queued 1"
    assert exp_cards.rows(NOW + 4 * 86400)[0].startswith("next-one")


def test_studies_freeze_once_and_the_cap_refuses_new_cards(desk, monkeypatch):
    p, w = exp_cards.freeze_study("2026-09-25-min_usd-abc", "# t\n", {"id": "2026-09-25-min_usd-abc", "totals_line": "x"})
    assert w and p.endswith("studies/2026-09-25-min_usd-abc.md")
    p2, w2 = exp_cards.freeze_study("2026-09-25-min_usd-abc", "# changed\n", {"id": "x"})
    assert not w2 and open(p2).read() == "# t\n", "never rewritten"
    assert exp_cards.studies()[0]["totals_line"] == "x"
    monkeypatch.setattr(exp_cards, "EXP_MAX_MB", 0.0)
    ok, why, _ = exp_cards.create(card(), NOW)
    assert not ok and "over" in why


def test_prune_drops_old_ledgers_and_keeps_the_record(desk):
    exp_cards.create(card(), NOW); exp_cards.launch("min150", NOW)
    d = desk / "exp" / "min150"
    (d / "control.jsonl").write_text("{}\n"); (d / "treatment.jsonl").write_text("{}\n")
    exp_cards.apply_verdict(exp_cards.load("min150"), {"status": "kill", "why": "k"}, NOW + 86400)
    assert exp_cards.prune(NOW + 2 * 86400) == [], "too soon"
    gone = exp_cards.prune(NOW + 40 * 86400)
    assert len(gone) == 2 and not (d / "control.jsonl").exists() and (d / "card.json").exists() and (d / "verdict.json").exists()


# ---- phase 2 (s-ye5990): no replay kind, one-tap presets, the unanswered ledger, the chain ----

def test_a_replay_card_is_refused_as_a_study(desk):
    ok, why, _ = exp_cards.validate(card(kind="replay"))
    assert not ok and why == "replay over history is a study: use kind study"


def test_a_tap_writes_a_request_the_sidecar_picks_up_and_renames(desk):
    kb = exp_cards.study_keyboard()["inline_keyboard"][0]
    assert [b["callback_data"] for b in kb] == ["study:min150", "study:form7", "study:cap3"]
    assert all(b["text"].startswith("study: ") and "—" not in b["text"] for b in kb)
    ok, msg = exp_cards.request_study("min150", NOW)
    assert ok and msg == "queued: floor 300 -> 150; the table lands here when it is done"
    assert exp_cards.request_study("stake", NOW) == (False, "no study preset 'stake'")
    reqs = exp_cards.pending_requests()
    assert len(reqs) == 1 and reqs[0][1]["kind"] == "min_usd" and reqs[0][1]["params"] == {"from": 300, "to": 150} and reqs[0][1]["by"] == "owner"
    exp_cards.finish_request(reqs[0][0], ok=True)
    assert exp_cards.pending_requests() == [] and (desk / "exp" / "studies" / f"request-{int(NOW)}-min150.done").exists()


def test_the_unanswered_ledger_is_plain_and_capped(desk, monkeypatch):
    monkeypatch.setattr(exp_cards, "UNANSWERED_KEEP", 3)
    for i in range(5):
        exp_cards.unanswered_add({"study": "s1", "wanted": f"q{i}", "why_not": "no feed archive"}, NOW + i)
    rows = exp_cards.unanswered_rows()
    assert [r["wanted"] for r in rows] == ["q2", "q3", "q4"] and rows[0]["day"] == "2026-09-25"
    assert set(rows[0]) == {"ts", "day", "study", "wanted", "why_not"}, "no score, no count"


def test_the_chain_is_one_computed_phrase(desk):
    exp_cards.create(card(), NOW)
    exp_cards.create(card(id="min150-first", parent_id="min150", study_ref="2026-09-25-min_usd-ab12"), NOW + 1)
    assert exp_cards.chain(exp_cards.load("min150")) == ""
    assert exp_cards.chain(exp_cards.load("min150-first")) == "min150-first <- min150, study 2026-09-25-min_usd-ab12"
    assert any("(min150-first <- min150, study 2026-09-25-min_usd-ab12)" in l for l in exp_cards.rows(NOW + 2))
    assert exp_cards.backlog_rows()[-1]["study_ref"] == "2026-09-25-min_usd-ab12"
