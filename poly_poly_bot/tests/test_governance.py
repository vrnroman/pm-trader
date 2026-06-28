"""Tests for auto promote/demote governance."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.copy_trading import promotion_state as ps
from src.copy_trading.copy_paper import PaperPosition
from src.copy_trading.governance import evaluate_governance, run_governance_cycle

BASE = dict(
    promote_min_n=15, promote_min_roi=0.10,
    demote_min_n=15, demote_max_roi=-0.05,
    now=1000.0, cooldown_s=86400.0,
)


def w(wallet, n, roi, net=0.0):
    return SimpleNamespace(wallet=wallet, n_closed=n, roi=roi, net_pnl=net)


def _ev(wallets, **over):
    kw = dict(promoted=set(), blacklist=set(), offered=set(), **BASE)
    kw.update(over)
    return evaluate_governance(wallets, **kw)


def test_promote_offer_when_matured_positive():
    offers, dem = _ev([w("0xA", 15, 0.12, 300)])
    assert [o["wallet"] for o in offers] == ["0xA"]
    assert dem == []


def test_demote_when_matured_negative():
    offers, dem = _ev([w("0xB", 20, -0.08, -200)])
    assert offers == []
    assert len(dem) == 1
    assert dem[0]["wallet"] == "0xB"
    assert dem[0]["until"] == BASE["now"] + BASE["cooldown_s"]


def test_hold_in_the_middle_band():
    offers, dem = _ev([w("0xC", 20, 0.03, 50)])
    assert offers == [] and dem == []


def test_hold_when_too_few_settled():
    # great ROI but only 10 resolved — not enough evidence either way.
    offers, dem = _ev([w("0xD", 10, 0.5, 400)])
    assert offers == [] and dem == []
    offers2, dem2 = _ev([w("0xD", 10, -0.5, -400)])
    assert offers2 == [] and dem2 == []


def test_skip_already_promoted_and_blacklisted():
    offers, dem = _ev(
        [w("0xA", 15, 0.2, 300), w("0xB", 20, -0.2, -300)],
        promoted={"0xa"}, blacklist={"0xb"})
    assert offers == [] and dem == []


def test_offered_suppresses_repeat():
    offers, _ = _ev([w("0xA", 15, 0.2, 300)], offered={"0xa"})
    assert offers == []


def test_skip_none_roi_and_non_address():
    offers, dem = _ev([w("0xA", 15, None, 0), w("(unknown)", 20, 0.5, 500)])
    assert offers == [] and dem == []


# ---- integration over a real ledger via aggregate_system_b ----

WIN = "0x" + "a" * 40
LOSE = "0x" + "b" * 40


def _pos(target, i, pnl):
    return PaperPosition(
        copy_id=f"{target}-{i}", target=target, condition_id="0xC",
        token_id=f"TOK{i}", outcome_index=0, category="research",
        their_price=0.5, entry_price=0.5, shares=20.0, spent=10.0, drag_bps=0,
        opened_ts=0.0, closed=True, won=(pnl > 0), pnl=pnl)


@pytest.fixture
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMOTED_WALLETS_STORE", str(tmp_path / "promoted.json"))
    monkeypatch.setenv("COPY_BLACKLIST_STORE", str(tmp_path / "blacklist.json"))
    monkeypatch.setenv("PROMOTION_OFFERS_STORE", str(tmp_path / "offers.json"))
    ps.clear_cache()
    yield
    ps.clear_cache()


def _run(positions, sent, now=1000.0, send_ok=True):
    return run_governance_cycle(
        positions, now=now,
        promote_min_n=15, promote_min_roi=0.10,
        demote_min_n=15, demote_max_roi=-0.05,
        cooldown_s=86400.0, default_tier="1b",
        send_offer=lambda o: (sent.append(o) or send_ok),
        send_demotion=lambda d: sent.append(("demote", d)),
    )


def test_cycle_offers_once_and_records(stores):
    positions = [_pos(WIN, i, 1.2) for i in range(15)]   # roi = +12%
    sent = []
    offers, dem = _run(positions, sent)
    assert len(offers) == 1 and dem == []
    assert ps.offer_status(WIN) == "offered"
    # a second pass must NOT re-offer (deduped by the offers store)
    offers2, _ = _run(positions, sent)
    assert offers2 == []


def test_cycle_does_not_record_when_send_fails(stores):
    positions = [_pos(WIN, i, 1.2) for i in range(15)]
    sent = []
    offers, _ = _run(positions, sent, send_ok=False)
    assert offers == []                       # not recorded -> retried next time
    assert ps.offer_status(WIN) is None


def test_cycle_demotes_and_blacklists(stores):
    positions = [_pos(LOSE, i, -1.0) for i in range(15)]   # roi = -10%
    sent = []
    offers, dem = _run(positions, sent)
    assert offers == [] and len(dem) == 1
    assert ps.is_blacklisted(LOSE, now=1000.0) is True
    assert ("demote", dem[0]) in sent
