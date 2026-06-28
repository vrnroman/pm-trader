"""Tests for the consensus-of-sharps signal (pure detection + dedup + format)."""
from __future__ import annotations

from src.copy_trading.consensus import (
    ConsensusMember,
    ConsensusSignal,
    detect_consensus,
    format_consensus_signal,
    new_signals,
)
from src.copy_trading.outcome_names import OutcomeNameResolver


def _buy(wallet, cid="C", oi=1, usd=1000.0, price=0.5, ts=1000.0, title="Mkt", slug="s"):
    return {"wallet": wallet, "condition_id": cid, "outcome_index": oi, "usd": usd,
            "price": price, "ts": ts, "title": title, "slug": slug, "category": "sports"}


def test_fires_when_k_independent_wallets_agree():
    buys = [_buy("0xA"), _buy("0xB"), _buy("0xC")]
    sigs = detect_consensus(buys, k=3, window_s=86400, min_usd=500, now=1000.0)
    assert len(sigs) == 1
    assert sigs[0].n == 3
    assert sigs[0].outcome_index == 1


def test_no_fire_below_k():
    buys = [_buy("0xA"), _buy("0xB")]
    assert detect_consensus(buys, k=3, window_s=86400, min_usd=500, now=1000.0) == []


def test_same_wallet_twice_counts_once_keeps_largest():
    buys = [_buy("0xA", usd=600), _buy("0xA", usd=1500), _buy("0xB"), _buy("0xC")]
    sigs = detect_consensus(buys, k=3, window_s=86400, min_usd=500, now=1000.0)
    assert sigs[0].n == 3
    a = next(m for m in sigs[0].members if m.wallet == "0xa")
    assert a.usd == 1500


def test_different_outcomes_dont_merge():
    buys = [_buy("0xA", oi=0), _buy("0xB", oi=1), _buy("0xC", oi=1)]
    sigs = detect_consensus(buys, k=2, window_s=86400, min_usd=500, now=1000.0)
    # only outcome 1 has 2 wallets
    assert len(sigs) == 1 and sigs[0].outcome_index == 1 and sigs[0].n == 2


def test_window_and_min_usd_filters():
    buys = [_buy("0xA", ts=100), _buy("0xB", ts=1000), _buy("0xC", usd=100)]
    # cutoff = 1000-500 = 500: 0xA(ts100) too old, 0xC under min_usd -> only 0xB
    sigs = detect_consensus(buys, k=1, window_s=500, min_usd=500, now=1000.0)
    assert sigs[0].n == 1 and sigs[0].members[0].wallet == "0xb"


def test_funder_dedup_collapses_sybils():
    # 0xA and 0xB share funder F (sybils) -> one voice; 0xC independent -> total 2
    buys = [_buy("0xA", usd=900), _buy("0xB", usd=1500), _buy("0xC")]
    funder = {"0xa": "0xfff", "0xb": "0xfff", "0xc": ""}
    sigs = detect_consensus(buys, k=3, window_s=86400, min_usd=500, now=1000.0,
                            funder_of=funder)
    assert sigs == []  # only 2 independent voices, below k=3
    sigs2 = detect_consensus(buys, k=2, window_s=86400, min_usd=500, now=1000.0,
                             funder_of=funder)
    assert sigs2[0].n == 2
    # the kept sybil is the larger bet (0xB $1500)
    wallets = {m.wallet for m in sigs2[0].members}
    assert wallets == {"0xb", "0xc"}


def test_empty_funder_treated_independent():
    buys = [_buy("0xA"), _buy("0xB"), _buy("0xC")]
    funder = {"0xa": "", "0xb": "", "0xc": ""}  # all unknown/CEX -> independent
    sigs = detect_consensus(buys, k=3, window_s=86400, min_usd=500, now=1000.0,
                            funder_of=funder)
    assert sigs[0].n == 3


def test_signal_aggregates():
    buys = [_buy("0xA", usd=1000, price=0.40, ts=1000),
            _buy("0xB", usd=1000, price=0.60, ts=1000 + 3600)]
    s = detect_consensus(buys, k=2, window_s=86400, min_usd=500, now=1000 + 3600)[0]
    assert s.total_usd == 2000
    assert abs(s.avg_price - 0.50) < 1e-9       # usd-weighted
    assert s.time_spread_s == 3600


def test_new_signals_dedup_cooldown_and_growth():
    buys3 = [_buy("0xA"), _buy("0xB"), _buy("0xC")]
    s3 = detect_consensus(buys3, k=2, window_s=86400, min_usd=500, now=1000.0)
    fired: dict = {}
    assert len(new_signals(s3, fired, now=1000.0, cooldown_s=3600)) == 1   # first fire
    assert new_signals(s3, fired, now=1100.0, cooldown_s=3600) == []        # within cooldown
    # consensus grows to 4 members -> fresh ping even within cooldown
    s4 = detect_consensus(buys3 + [_buy("0xD")], k=2, window_s=86400, min_usd=500, now=1200.0)
    assert len(new_signals(s4, fired, now=1200.0, cooldown_s=3600)) == 1
    # after cooldown elapses, re-fires
    assert len(new_signals(s4, fired, now=1200.0 + 3601, cooldown_s=3600)) == 1


def test_format_says_what_is_bought():
    buys = [_buy("0xAAAAAAAAAA", oi=1, usd=1000, price=0.35),
            _buy("0xBBBBBBBBBB", oi=1, usd=550, price=0.30),
            _buy("0xCCCCCCCCCC", oi=1, usd=900, price=0.33)]
    sig = detect_consensus(buys, k=3, window_s=86400, min_usd=500, now=1000.0)[0]
    resolver = OutcomeNameResolver(fetcher=lambda cid: ["Yes", "No"])
    msg = format_consensus_signal(sig, resolver)
    assert "BUY “No”" in msg            # the actual outcome, not "Outcome #1"
    assert "<b>3 sharps" in msg
    assert "$2,450" in msg               # total
    assert "@ 35¢" in msg                # a member entry in cents


def test_format_honest_when_outcome_unresolved():
    buys = [_buy("0xA", oi=2), _buy("0xB", oi=2)]
    sig = detect_consensus(buys, k=2, window_s=86400, min_usd=500, now=1000.0)[0]
    resolver = OutcomeNameResolver(fetcher=lambda cid: ["Yes", "No"])  # no index 2
    msg = format_consensus_signal(sig, resolver)
    assert "Outcome #2" in msg           # honest fallback, never a fabricated side


def test_format_flags_unverified_independence():
    buys = [_buy("0xA", oi=1), _buy("0xB", oi=1), _buy("0xC", oi=1)]
    sig = detect_consensus(buys, k=3, window_s=86400, min_usd=500, now=1000.0)[0]
    resolver = OutcomeNameResolver(fetcher=lambda cid: ["Yes", "No"])
    # verified -> no warning
    assert "independence not confirmed" not in format_consensus_signal(sig, resolver, True)
    # unverified -> honest warning, not a silent fake-independent signal
    assert "independence not confirmed" in format_consensus_signal(sig, resolver, False)


def test_signal_independence_verified_per_signal():
    from src.copy_trading.consensus import signal_independence_verified
    buys = [_buy("0xA", oi=1), _buy("0xB", oi=1), _buy("0xC", oi=1)]
    sig = detect_consensus(buys, k=3, window_s=86400, min_usd=500, now=1000.0)[0]
    # all members looked up with real funders -> verified
    assert signal_independence_verified(sig, {"0xa": "0xf1", "0xb": "0xf2", "0xc": "0xf3"})
    # a CEX/no-traceable-funder member ("" but PRESENT = looked up) is treated as
    # independent, so a legitimately-independent CEX-funded consensus is verified
    # (not falsely flagged) as long as the lookups worked (some real funder exists)
    assert signal_independence_verified(sig, {"0xa": "0xf1", "0xb": "", "0xc": "0xf3"})
    # a member whose lookup FAILED is ABSENT from the map -> NOT verified
    assert not signal_independence_verified(sig, {"0xa": "0xf1", "0xc": "0xf3"})
    # no funder data worked at all (blank key -> all "") -> can't confirm (no fail-open)
    assert not signal_independence_verified(sig, {"0xa": "", "0xb": "", "0xc": ""})
    # lookup failed entirely (None) -> unverified
    assert not signal_independence_verified(sig, None)
    assert not signal_independence_verified(sig, {})
