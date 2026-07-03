"""Tests for auto promote/demote governance over the trustworthy promotion gate."""

from __future__ import annotations

import pytest

from src.copy_trading import gate_history, promotion_state as ps
from src.copy_trading.copy_paper import PaperPosition
from src.copy_trading.governance import (
    evaluate_governance, group_settled_by_wallet, run_governance_cycle)

WIN = "0x" + "a" * 40
LOSE = "0x" + "b" * 40

FLOORS = dict(
    promote_min_n=15, promote_min_roi=0.10, promote_min_tstat=0.0,
    promote_min_second_half_roi=-0.10, promote_min_conditions=8,
    promote_min_categories=3,
    demote_min_n=15, demote_max_roi=-0.05, demote_min_abs_loss=5.0,
    demote_max_wilson=0.50,
)


def pos(target, i, *, pnl, spent=10.0, entry=0.5, won=None, condition=None, category=None):
    return PaperPosition(
        copy_id=f"{target}-{i}", target=target,
        condition_id=condition if condition is not None else f"{target[:6]}-c{i}",
        token_id=f"T{i}", outcome_index=0,
        category=category if category is not None else f"cat{i % 4}",
        their_price=entry, entry_price=entry, shares=spent / entry, spent=spent,
        drag_bps=0, opened_ts=float(i), closed=True,
        won=(pnl > 0) if won is None else won, pnl=pnl, closed_ts=float(i))


def diversified_winner(target=WIN, n=15, pnl=1.2):
    return [pos(target, i, pnl=pnl) for i in range(n)]


def loser(target=LOSE, n=15):
    return [pos(target, i, pnl=-1.0) for i in range(n)]


def _ev(positions, **over):
    by_wallet = group_settled_by_wallet(positions)
    kw = dict(promoted=set(), blacklist=set(), offered=set(),
              now=1000.0, cooldown_s=86400.0, **FLOORS)
    kw.update(over)
    return evaluate_governance(by_wallet, **kw)


# --------------------------------------------------------------------------- #
# evaluate_governance (pure)
# --------------------------------------------------------------------------- #

def test_offer_when_clears_floor():
    offers, dem, held = _ev(diversified_winner())
    assert [o["wallet"] for o in offers] == [WIN]
    assert dem == [] and held == []


def test_demote_real_loser():
    offers, dem, held = _ev(loser())
    assert offers == [] and held == []
    assert dem[0]["wallet"] == LOSE
    assert dem[0]["until"] == 1000.0 + 86400.0


def test_held_when_clears_bar_but_fails_floor():
    # 15 winning bets (+12% ROI) but all on ONE market -> passes n+ROI, fails floor.
    ps_ = [pos(WIN, i, pnl=1.2, condition="cSAME", category="sports") for i in range(15)]
    offers, dem, held = _ev(ps_)
    assert offers == [] and dem == []
    assert held[0]["wallet"] == WIN
    assert any("concentrated" in r for r in held[0]["reasons"])


def test_no_action_below_base_bar():
    # good ROI but only 10 settled: neither an offer nor a "held" (never crossed bar).
    offers, dem, held = _ev(diversified_winner(n=10))
    assert offers == [] and dem == [] and held == []


def test_skip_promoted_blacklisted_offered():
    assert _ev(diversified_winner(), promoted={WIN.lower()})[0] == []
    assert _ev(diversified_winner(), offered={WIN.lower()})[0] == []
    assert _ev(loser(), blacklist={LOSE.lower()})[1] == []


def test_longshot_offered_not_blocked():
    # low win rate, +EV, diversified -> must be offered (the anti-longshot-bias case)
    target = "0x" + "c" * 40
    outcomes = ([True] * 7 + [False] * 11)
    inter = []
    w = [o for o in outcomes if o]; l = [o for o in outcomes if not o]
    while w or l:
        if l: inter.append(l.pop())
        if w: inter.append(w.pop())
        if l: inter.append(l.pop())
    ps_ = [pos(target, i, pnl=(23.3 if won else -10.0), entry=0.30, won=won,
               condition=f"c{i}", category=f"k{i % 5}") for i, won in enumerate(inter)]
    offers, dem, held = _ev(ps_)
    assert [o["wallet"] for o in offers] == [target]


# --------------------------------------------------------------------------- #
# run_governance_cycle (I/O: offers store, blacklist, history, advisory LLM)
# --------------------------------------------------------------------------- #

@pytest.fixture
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMOTED_WALLETS_STORE", str(tmp_path / "promoted.json"))
    monkeypatch.setenv("COPY_BLACKLIST_STORE", str(tmp_path / "blacklist.json"))
    monkeypatch.setenv("PROMOTION_OFFERS_STORE", str(tmp_path / "offers.json"))
    ps.clear_cache()
    yield
    ps.clear_cache()


def _run(positions, sent, *, tmp_path, now=1000.0, send_ok=True, review_fn=None):
    return run_governance_cycle(
        positions, now=now, cooldown_s=86400.0, default_tier="1b",
        send_offer=lambda o: (sent.append(o) or send_ok),
        send_demotion=lambda d: sent.append(("demote", d)),
        review_fn=review_fn,
        history_path=str(tmp_path / "promotion-gate-history.jsonl"),
        **FLOORS)


def test_cycle_offers_once_and_records(stores, tmp_path):
    sent = []
    offers, dem = _run(diversified_winner(), sent, tmp_path=tmp_path)
    assert len(offers) == 1 and dem == []
    assert ps.offer_status(WIN) == "offered"
    rows = gate_history.load(str(tmp_path / "promotion-gate-history.jsonl"))
    assert rows[-1]["event"] == "offer" and rows[-1]["wallet"] == WIN
    # a second pass must NOT re-offer
    offers2, _ = _run(diversified_winner(), sent, tmp_path=tmp_path)
    assert offers2 == []


def test_cycle_llm_review_annotates_but_never_blocks(stores, tmp_path):
    from src.copy_trading.llm_review import PromotionVerdict
    seen = {}

    def review(dossier, **kw):
        seen["dossier"] = dossier
        return PromotionVerdict("reject", 0.9, "looks like variance", ("thin",))

    sent = []
    offers, _ = _run(diversified_winner(), sent, tmp_path=tmp_path, review_fn=review)
    assert len(offers) == 1                       # rejected by LLM but STILL offered
    assert offers[0]["llm"].verdict == "reject"
    assert "paper_copy_record" in seen["dossier"]
    rows = gate_history.load(str(tmp_path / "promotion-gate-history.jsonl"))
    assert rows[-1]["llm_verdict"] == "reject"


def test_cycle_llm_unavailable_still_offers(stores, tmp_path):
    sent = []
    offers, _ = _run(diversified_winner(), sent, tmp_path=tmp_path,
                     review_fn=lambda d, **k: None)   # review returns nothing
    assert len(offers) == 1 and offers[0]["llm"] is None
    assert offers[0]["llm_attempted"] is True


def test_cycle_does_not_record_when_send_fails(stores, tmp_path):
    sent = []
    offers, _ = _run(diversified_winner(), sent, tmp_path=tmp_path, send_ok=False)
    assert offers == []                            # not recorded -> retried next time
    assert ps.offer_status(WIN) is None


def test_cycle_demotes_and_blacklists(stores, tmp_path):
    sent = []
    offers, dem = _run(loser(), sent, tmp_path=tmp_path)
    assert offers == [] and len(dem) == 1
    assert ps.is_blacklisted(LOSE, now=1000.0) is True
    assert ("demote", dem[0]) in sent
    rows = gate_history.load(str(tmp_path / "promotion-gate-history.jsonl"))
    assert rows[-1]["event"] == "demote"


def test_cycle_records_held_once(stores, tmp_path):
    concentrated = [pos(WIN, i, pnl=1.2, condition="cSAME", category="sports")
                    for i in range(15)]
    sent = []
    _run(concentrated, sent, tmp_path=tmp_path)
    assert ps.offer_status(WIN) == "held"
    rows = gate_history.load(str(tmp_path / "promotion-gate-history.jsonl"))
    held_rows = [r for r in rows if r.get("event") == "held"]
    assert len(held_rows) == 1
    # a second cycle must NOT re-log the same hold
    _run(concentrated, sent, tmp_path=tmp_path)
    rows2 = gate_history.load(str(tmp_path / "promotion-gate-history.jsonl"))
    assert len([r for r in rows2 if r.get("event") == "held"]) == 1
