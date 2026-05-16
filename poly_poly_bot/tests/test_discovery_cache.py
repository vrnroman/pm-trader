"""Tests for PMDiscoveryCache: refresh, linking, retry-on-no-link, active_set."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.odds.models import MatchOdds
from src.tennis.discovery_cache import PMDiscoveryCache, _match_key, _NO_LINK


def _odds(player_a: str, player_b: str, match_time: datetime | None = None) -> MatchOdds:
    return MatchOdds(
        source="smarkets",
        tournament="Test Open",
        tour="ATP",
        player_a=player_a,
        player_b=player_b,
        odds_a=2.0,
        odds_b=2.0,
        implied_prob_a=0.5,
        implied_prob_b=0.5,
        match_time=match_time,
    )


def _pm(
    cid: str,
    player: str,
    question: str,
    other_player: str = "",
    event_title: str = "",
    pm_match_time: str = "",
    liquidity: float = 10000.0,
) -> dict:
    """Minimal PM market dict matching fetch_pm_tennis_markets_raw output shape."""
    title = event_title or f"{player} vs {other_player}"
    return {
        "event_title": title,
        "event_slug": "test-event",
        "event_end_date": "",
        "pm_match_time": pm_match_time,
        "question": question,
        "player": player,
        "group_item_title": player,
        "yes_price": 0.50,
        "yes_ask": 0.50,
        "yes_bid": 0.50,
        "volume": 50000.0,
        "liquidity": liquidity,
        "market_id": f"mkt_{cid}",
        "condition_id": cid,
        "token_id_yes": f"tok_yes_{cid}",
        "token_id_no": f"tok_no_{cid}",
    }


def _provider(odds: list[MatchOdds]) -> MagicMock:
    p = MagicMock()
    p.fetch_tennis_odds.return_value = odds
    return p


def test_refresh_links_pm_to_sharp_by_player_match():
    mt = datetime(2026, 5, 16, 14, 0, tzinfo=timezone.utc)
    pm_markets = [_pm(
        "c1", "Sinner",
        "Test Open: Jannik Sinner vs Carlos Alcaraz",
        other_player="Alcaraz",
        pm_match_time=mt.isoformat(),
    )]
    sharp = [_odds("Jannik Sinner", "Carlos Alcaraz", mt)]
    cache = PMDiscoveryCache(
        smarkets_provider=_provider(sharp),
        tours=["ATP"],
        fetch_pm_fn=lambda: pm_markets,
    )

    stats = cache.refresh()

    assert stats["cache_size"] == 1
    assert stats["linked"] == 1
    assert stats["no_link"] == 0
    entry = cache.get_entry("c1")
    assert entry["linked_match_key"] == _match_key(sharp[0])


def test_refresh_marks_no_link_when_no_sharp_match():
    pm_markets = [_pm(
        "c1", "Obscure",
        "Test Open: Obscure Player vs Other Obscure",
        other_player="OtherObscure",
    )]
    cache = PMDiscoveryCache(
        smarkets_provider=_provider([]),  # empty sharp list
        tours=["ATP"],
        fetch_pm_fn=lambda: pm_markets,
    )

    stats = cache.refresh()

    assert stats["cache_size"] == 1
    assert stats["linked"] == 0
    assert stats["no_link"] == 1
    assert cache.get_entry("c1")["linked_match_key"] == _NO_LINK


def test_refresh_retries_no_link_entries_next_cycle():
    """User #4: don't give up on no_link — Smarkets sometimes lists fixtures
    late, so re-attempt every refresh."""
    mt = datetime(2026, 5, 16, 14, 0, tzinfo=timezone.utc)
    pm_markets = [_pm(
        "c1", "Sinner",
        "Test Open: Jannik Sinner vs Carlos Alcaraz",
        other_player="Alcaraz",
        pm_match_time=mt.isoformat(),
    )]
    # First cycle: no sharp coverage.
    # Second cycle: sharp shows up.
    sharp_cycles = iter([[], [_odds("Jannik Sinner", "Carlos Alcaraz", mt)]])
    provider = MagicMock()
    provider.fetch_tennis_odds.side_effect = lambda **kw: next(sharp_cycles)

    cache = PMDiscoveryCache(
        smarkets_provider=provider,
        tours=["ATP"],
        fetch_pm_fn=lambda: pm_markets,
    )

    s1 = cache.refresh()
    assert s1["no_link"] == 1
    assert cache.get_entry("c1")["linked_match_key"] == _NO_LINK

    s2 = cache.refresh()
    assert s2["linked"] == 1
    assert s2["retried_nolink"] == 1
    assert s2["relinked_this_cycle"] == 1
    assert isinstance(cache.get_entry("c1")["linked_match_key"], tuple)


def test_refresh_drops_stale_link_when_sharp_disappears():
    """If a previously linked Smarkets fixture vanishes (event removed),
    the link must be cleared so we don't trade off a dangling pointer."""
    mt = datetime(2026, 5, 16, 14, 0, tzinfo=timezone.utc)
    pm_markets = [_pm(
        "c1", "Sinner",
        "Test Open: Jannik Sinner vs Carlos Alcaraz",
        other_player="Alcaraz",
        pm_match_time=mt.isoformat(),
    )]
    sharp_cycles = iter([[_odds("Jannik Sinner", "Carlos Alcaraz", mt)], []])
    provider = MagicMock()
    provider.fetch_tennis_odds.side_effect = lambda **kw: next(sharp_cycles)

    cache = PMDiscoveryCache(
        smarkets_provider=provider,
        tours=["ATP"],
        fetch_pm_fn=lambda: pm_markets,
    )

    cache.refresh()
    assert cache.get_entry("c1")["linked_match_key"] != _NO_LINK

    cache.refresh()
    assert cache.get_entry("c1")["linked_match_key"] == _NO_LINK


def test_active_set_window_filter():
    """gameStartTime within [-2h, +20min] of now passes; outside is dropped."""
    now = datetime(2026, 5, 16, 14, 0, tzinfo=timezone.utc)
    inside = (now + timedelta(minutes=10)).isoformat()
    past_recent = (now - timedelta(minutes=90)).isoformat()  # live
    past_old = (now - timedelta(hours=3)).isoformat()  # match ended
    future_far = (now + timedelta(hours=2)).isoformat()  # too far ahead
    mt = now
    pm_markets = [
        _pm("c_inside", "P1", "T: P1 vs O1", other_player="O1", pm_match_time=inside),
        _pm("c_past_recent", "P2", "T: P2 vs O2", other_player="O2", pm_match_time=past_recent),
        _pm("c_past_old", "P3", "T: P3 vs O3", other_player="O3", pm_match_time=past_old),
        _pm("c_future_far", "P4", "T: P4 vs O4", other_player="O4", pm_match_time=future_far),
    ]
    sharp = [
        _odds("P1", "O1", mt),
        _odds("P2", "O2", mt - timedelta(minutes=90)),
        _odds("P3", "O3", mt - timedelta(hours=3)),
        _odds("P4", "O4", mt + timedelta(hours=2)),
    ]
    cache = PMDiscoveryCache(
        smarkets_provider=_provider(sharp),
        tours=["ATP"],
        max_event_date_delta_days=10.0,  # widen so date guard doesn't reject
        fetch_pm_fn=lambda: pm_markets,
    )
    cache.refresh()

    active = cache.active_set(now=now)
    cids = {a["condition_id"] for a in active}
    assert cids == {"c_inside", "c_past_recent"}


def test_active_set_liquidity_gate():
    now = datetime(2026, 5, 16, 14, 0, tzinfo=timezone.utc)
    mt = now + timedelta(minutes=5)
    pm_markets = [
        _pm("c_thick", "P1", "T: P1 vs O1", other_player="O1",
            pm_match_time=mt.isoformat(), liquidity=10000.0),
        _pm("c_thin", "P2", "T: P2 vs O2", other_player="O2",
            pm_match_time=mt.isoformat(), liquidity=500.0),
    ]
    sharp = [_odds("P1", "O1", mt), _odds("P2", "O2", mt)]
    cache = PMDiscoveryCache(
        smarkets_provider=_provider(sharp),
        tours=["ATP"],
        fetch_pm_fn=lambda: pm_markets,
    )
    cache.refresh()

    active = cache.active_set(now=now, min_liquidity=5000.0)
    cids = {a["condition_id"] for a in active}
    assert cids == {"c_thick"}


def test_active_set_excludes_no_link_by_default():
    now = datetime(2026, 5, 16, 14, 0, tzinfo=timezone.utc)
    mt = now + timedelta(minutes=5)
    pm_markets = [
        _pm("c_linked", "P1", "T: P1 vs O1", other_player="O1", pm_match_time=mt.isoformat()),
        _pm("c_orphan", "Obscure", "T: Obscure vs OtherObscure",
            other_player="OtherObscure", pm_match_time=mt.isoformat()),
    ]
    sharp = [_odds("P1", "O1", mt)]
    cache = PMDiscoveryCache(
        smarkets_provider=_provider(sharp),
        tours=["ATP"],
        fetch_pm_fn=lambda: pm_markets,
    )
    cache.refresh()

    active = cache.active_set(now=now)
    cids = {a["condition_id"] for a in active}
    assert cids == {"c_linked"}


def test_pm_fetch_failure_preserves_prior_entries():
    """Gamma 503 between refreshes must NOT wipe the cache — the scan
    loop runs every 20s and 10 min of empty cache = 30 zero-signal scans.
    Preserve the last good snapshot until the next successful refresh."""
    mt = datetime(2026, 5, 16, 14, 0, tzinfo=timezone.utc)
    good_pm = [_pm(
        "c1", "Sinner", "T: Sinner vs Alcaraz",
        other_player="Alcaraz", pm_match_time=mt.isoformat(),
    )]
    sharp = [_odds("Sinner", "Alcaraz", mt)]
    call_count = [0]

    def _fetch_pm():
        call_count[0] += 1
        if call_count[0] == 1:
            return good_pm
        raise RuntimeError("gamma 503")

    cache = PMDiscoveryCache(
        smarkets_provider=_provider(sharp),
        tours=["ATP"],
        fetch_pm_fn=_fetch_pm,
    )

    s1 = cache.refresh()
    assert s1["cache_size"] == 1
    assert s1["linked"] == 1

    s2 = cache.refresh()
    assert s2["pm_fetch_failed"] is True
    assert s2["preserved_prior_entries"] is True
    assert s2["cache_size"] == 1  # prior entry retained
    assert s2["linked"] == 1
    assert cache.get_entry("c1") is not None  # still there


def test_smarkets_fetch_failure_preserves_prior_entries():
    """Same principle as PM-fetch failure but for Smarkets."""
    mt = datetime(2026, 5, 16, 14, 0, tzinfo=timezone.utc)
    pm_markets = [_pm(
        "c1", "Sinner", "T: Sinner vs Alcaraz",
        other_player="Alcaraz", pm_match_time=mt.isoformat(),
    )]
    sharp_cycles = iter([
        [_odds("Sinner", "Alcaraz", mt)],
        RuntimeError("smarkets 500"),
    ])

    def _fetch_or_raise(**kw):
        val = next(sharp_cycles)
        if isinstance(val, Exception):
            raise val
        return val

    provider = MagicMock()
    provider.fetch_tennis_odds.side_effect = _fetch_or_raise

    cache = PMDiscoveryCache(
        smarkets_provider=provider,
        tours=["ATP"],
        fetch_pm_fn=lambda: pm_markets,
    )

    s1 = cache.refresh()
    assert s1["linked"] == 1

    s2 = cache.refresh()
    assert s2["smarkets_fetch_failed"] is True
    assert s2["preserved_prior_entries"] is True
    assert s2["cache_size"] == 1  # prior link survives even though sharp fetch died
    assert s2["linked"] == 1


def test_first_refresh_with_fetch_failure_yields_empty_cache():
    """No prior state to preserve → cache is empty, but we still don't crash
    and we don't claim to have entries."""
    def _boom() -> list[dict]:
        raise RuntimeError("gamma 503 cold start")
    cache = PMDiscoveryCache(
        smarkets_provider=_provider([]),
        tours=["ATP"],
        fetch_pm_fn=_boom,
    )
    stats = cache.refresh()
    assert stats["pm_fetch_failed"] is True
    assert stats["cache_size"] == 0
    assert cache.active_set() == []


