"""Discovery excludes auto-demoted (blacklisted) wallets from re-qualifying."""

from __future__ import annotations

from src.copy_trading.discovery import (
    DiscoveryConfig,
    DiscoveryState,
    Eval,
    run_discovery_cycle,
)

CFG = DiscoveryConfig(min_capture_cents=1.5, min_tstat=10.0)


def _flagged(wallet):
    # flagged by a theory + clean entry profile -> qualifies on its own.
    return Eval(wallet=wallet, flagged_by=("1g",), tstat=2.0, tail_ratio=0.1)


def test_blacklisted_wallet_excluded():
    e = _flagged("0xBAD")
    r = run_discovery_cycle({"0xBAD": e}, DiscoveryState(), CFG,
                            blacklisted={"0xbad"})
    assert r.watchlist == []


def test_not_blacklisted_qualifies():
    e = _flagged("0xBAD")
    r = run_discovery_cycle({"0xBAD": e}, DiscoveryState(), CFG)
    assert [x.wallet for x in r.watchlist] == ["0xBAD"]


def test_blacklist_also_blocks_retained_wallet():
    # already on the watchlist last sweep, still flagged this sweep, but now
    # blacklisted -> it must be dropped, not retained.
    e = _flagged("0xBAD")
    prev = DiscoveryState(on_watchlist={"0xBAD": {}}, initialized=True)
    r = run_discovery_cycle({"0xBAD": e}, prev, CFG, blacklisted={"0xbad"})
    assert r.watchlist == []
    assert "0xBAD" in r.removed
