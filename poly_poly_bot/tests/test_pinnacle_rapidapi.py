"""Tests for the RapidAPI 'Pinnacle Odds' tennis provider.

Everything is mocked — no live HTTP. We reuse the Smarkets test pattern:
``FakeResponse`` + a ``make_session(routes)`` MagicMock that routes by URL
substring. The streaming test drives ``stream_price_changes`` with a scripted
fake session, patches ``asyncio.sleep`` to be instant, and breaks the
``async for`` after a bounded number of yields under ``asyncio.wait_for``.

NOTE: all wire formats here mirror the ``# ASSUMPTION:`` shapes documented in
``pinnacle_rapidapi.py`` and must be reconciled with the real RapidAPI docs at
signup (rewrite §11).
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.odds.models import MatchOdds, PriceChange
from src.odds.pinnacle_rapidapi import PinnacleRapidApiProvider


# ---------------------------------------------------------------------------
# Mock HTTP session (mirrors tests/test_smarkets_provider.py)
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code: int, body, headers: dict | None = None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


def make_session(routes) -> MagicMock:
    """MagicMock session returning canned responses keyed by URL substring.

    A route value may be a single FakeResponse or a list of them (consumed in
    order on successive calls — last one repeats). Longest key wins.
    """
    sess = MagicMock(spec=requests.Session)
    call_indexes: dict[str, int] = {}
    sorted_keys = sorted(routes.keys(), key=len, reverse=True)

    def fake_get(url, params=None, headers=None, timeout=None):
        # Fold query params into the match string so /markets routes can be
        # disambiguated by event_type if a test wants that granularity.
        match_str = url
        if params:
            match_str = url + "?" + "&".join(f"{k}={v}" for k, v in params.items())
        for key in sorted_keys:
            if key in match_str:
                value = routes[key]
                if isinstance(value, list):
                    idx = call_indexes.get(key, 0)
                    response = value[min(idx, len(value) - 1)]
                    call_indexes[key] = idx + 1
                    return response
                return value
        return FakeResponse(404, {"error": f"no route for {match_str}"})

    sess.get = MagicMock(side_effect=fake_get)
    return sess


# ---------------------------------------------------------------------------
# Canned payloads (ASSUMPTION shapes — see provider docstring)
# ---------------------------------------------------------------------------

SPORTS_RESPONSE = [
    {"id": 3, "name": "Soccer"},
    {"id": 2, "name": "Tennis"},
    {"id": 4, "name": "Basketball"},
]

EVENT_ATP = {
    "event_id": 1001,
    "home": "Carlos Alcaraz",
    "away": "Jannik Sinner",
    "league_name": "ATP Rome",
    "starts": "2026-05-25T13:00:00Z",
    "last": 1716000000,
    "periods": {"num_0": {"money_line": {"home": 1.80, "away": 2.10}}},
}

EVENT_WTA = {
    "event_id": 1002,
    "home": "Iga Swiatek",
    "away": "Aryna Sabalenka",
    "league_name": "WTA Rome",
    "starts": "2026-05-25T15:00:00Z",
    "last": 1716000001,
    "periods": {"num_0": {"money_line": {"home": 1.50, "away": 2.70}}},
}

EVENT_NO_MONEYLINE = {
    "event_id": 1003,
    "home": "Player X",
    "away": "Player Y",
    "league_name": "ATP Rome",
    "starts": "2026-05-25T17:00:00Z",
    "last": 1716000002,
    "periods": {"num_0": {}},  # no money_line → skipped
}


# ---------------------------------------------------------------------------
# 1. /sports startup cache
# ---------------------------------------------------------------------------

class TestFetchSportId:
    def test_resolves_and_caches_tennis_id(self):
        routes = {"/kit/v1/sports": FakeResponse(200, SPORTS_RESPONSE)}
        sess = make_session(routes)
        p = PinnacleRapidApiProvider(api_key="k", session=sess)

        assert p.fetch_sport_id() == 2
        assert p._sport_id == 2

        # Second call must be served from cache (no extra HTTP hit).
        calls_before = sess.get.call_count
        assert p.fetch_sport_id() == 2
        assert sess.get.call_count == calls_before

    def test_tennis_match_is_case_insensitive(self):
        routes = {"/kit/v1/sports": FakeResponse(200, [{"id": 9, "name": "tennis"}])}
        p = PinnacleRapidApiProvider(api_key="k", session=make_session(routes))
        assert p.fetch_sport_id() == 9

    def test_missing_tennis_returns_none(self):
        routes = {"/kit/v1/sports": FakeResponse(200, [{"id": 1, "name": "Soccer"}])}
        p = PinnacleRapidApiProvider(api_key="k", session=make_session(routes))
        assert p.fetch_sport_id() is None

    def test_does_not_hardcode_id(self):
        # A different canned id must flow through (proves no hardcoding).
        routes = {"/kit/v1/sports": FakeResponse(200, [{"id": 77, "name": "Tennis"}])}
        p = PinnacleRapidApiProvider(api_key="k", session=make_session(routes))
        assert p.fetch_sport_id() == 77

    def test_envelope_shape_supported(self):
        routes = {"/kit/v1/sports": FakeResponse(200, {"sports": SPORTS_RESPONSE})}
        p = PinnacleRapidApiProvider(api_key="k", session=make_session(routes))
        assert p.fetch_sport_id() == 2


# ---------------------------------------------------------------------------
# 2. fetch_tennis_odds happy path
# ---------------------------------------------------------------------------

class TestFetchTennisOdds:
    def _routes(self, events):
        return {
            "/kit/v1/sports": FakeResponse(200, SPORTS_RESPONSE),
            "/kit/v1/markets": FakeResponse(200, {"events": events, "last": 1716000099}),
        }

    def test_parses_and_devigs(self):
        sess = make_session(self._routes([EVENT_ATP]))
        p = PinnacleRapidApiProvider(api_key="k", session=sess)
        odds = p.fetch_tennis_odds(tours=["ATP"])

        # Both event_types poll the same /markets route → ATP event returned twice.
        assert len(odds) == 2
        mo = odds[0]
        assert isinstance(mo, MatchOdds)
        assert mo.source == "pinnacle"
        assert mo.tour == "ATP"
        assert mo.player_a == "Carlos Alcaraz"
        assert mo.player_b == "Jannik Sinner"
        assert mo.odds_a == 1.80
        assert mo.odds_b == 2.10
        # De-vigged implied probs sum to ~1.
        assert abs((mo.implied_prob_a + mo.implied_prob_b) - 1.0) < 1e-6
        # Alcaraz is favourite → higher implied prob.
        assert mo.implied_prob_a > mo.implied_prob_b

    def test_seeds_stream_snapshot(self):
        sess = make_session(self._routes([EVENT_ATP]))
        p = PinnacleRapidApiProvider(api_key="k", session=sess)
        odds = p.fetch_tennis_odds(tours=["ATP"])
        # Snapshot keyed by synthetic id, retrievable via get_match_odds.
        from src.odds.base import synthetic_event_id
        sid = synthetic_event_id(odds[0])
        snap = p.get_match_odds(sid)
        assert snap is not None
        assert snap.player_a == "Carlos Alcaraz"
        assert snap.odds_a == 1.80

    def test_tour_filter_drops_wta(self):
        sess = make_session(self._routes([EVENT_ATP, EVENT_WTA]))
        p = PinnacleRapidApiProvider(api_key="k", session=sess)
        odds = p.fetch_tennis_odds(tours=["ATP"])
        assert all(o.tour == "ATP" for o in odds)
        assert all(o.player_a == "Carlos Alcaraz" for o in odds)

    def test_default_filter_keeps_atp_and_wta(self):
        sess = make_session(self._routes([EVENT_ATP, EVENT_WTA]))
        p = PinnacleRapidApiProvider(api_key="k", session=sess)
        odds = p.fetch_tennis_odds()  # default ["ATP","WTA"]
        tours = {o.tour for o in odds}
        assert tours == {"ATP", "WTA"}

    def test_event_without_moneyline_skipped(self):
        sess = make_session(self._routes([EVENT_ATP, EVENT_NO_MONEYLINE]))
        p = PinnacleRapidApiProvider(api_key="k", session=sess)
        odds = p.fetch_tennis_odds(tours=["ATP"])
        # Only the ATP event with money_line survives (×2 event_types).
        assert all(o.player_a == "Carlos Alcaraz" for o in odds)
        assert len(odds) == 2

    def test_no_sport_id_returns_empty(self):
        routes = {"/kit/v1/sports": FakeResponse(200, [{"id": 1, "name": "Soccer"}])}
        p = PinnacleRapidApiProvider(api_key="k", session=make_session(routes))
        assert p.fetch_tennis_odds() == []


# ---------------------------------------------------------------------------
# 3. since-delta merging via the stream
# ---------------------------------------------------------------------------

class TestSinceDeltaStream:
    @pytest.mark.asyncio
    async def test_advances_since_and_yields_only_changed(self):
        # Round 1 (prematch since=0): EVENT_ATP at 1.80/2.10, last=100.
        # Round 1 (live since=0): empty, last=50.
        # Round 2 (prematch since=100): EVENT_ATP with home moved 1.80→1.70.
        # Subsequent rounds repeat the round-2 prematch payload (no change),
        # so no further PriceChanges are emitted.
        ev_r1 = dict(EVENT_ATP, last=99, periods={"num_0": {"money_line": {"home": 1.80, "away": 2.10}}})
        ev_r2 = dict(EVENT_ATP, last=199, periods={"num_0": {"money_line": {"home": 1.70, "away": 2.10}}})
        ev_r3 = dict(EVENT_ATP, last=299, periods={"num_0": {"money_line": {"home": 1.65, "away": 2.10}}})

        prematch_responses = [
            FakeResponse(200, {"events": [ev_r1], "last": 100}),   # round 1: home+away
            FakeResponse(200, {"events": [ev_r2], "last": 200}),   # round 2: home delta
            FakeResponse(200, {"events": [ev_r3], "last": 300}),   # round 3: home delta
            FakeResponse(200, {"events": [ev_r3], "last": 300}),   # round 4+: no change
        ]
        live_responses = FakeResponse(200, {"events": [], "last": 50})

        # Route both event_types to /kit/v1/markets, disambiguated by the
        # event_type param embedded in the match string by make_session.
        routes = {
            "/kit/v1/sports": FakeResponse(200, SPORTS_RESPONSE),
            "/kit/v1/markets?sport_id=2&event_type=prematch": prematch_responses,
            "/kit/v1/markets?sport_id=2&event_type=live": live_responses,
        }
        sess = make_session(routes)
        p = PinnacleRapidApiProvider(api_key="k", session=sess)

        changes: list[PriceChange] = []

        async def collect():
            # Yields happen mid-round, so a round's watermark advance only
            # commits when the NEXT round's yield arrives. We collect 4 changes
            # (round1 home+away, round2 home delta, round3 home delta); by the
            # 4th, round 2's advance to 200 has committed.
            async for ch in p.stream_price_changes(["tennis"]):
                changes.append(ch)
                if len(changes) >= 4:
                    break

        with patch("asyncio.sleep", new=_instant_sleep):
            await asyncio.wait_for(collect(), 2.0)

        # since high-watermark advanced from the response ``last`` fields. At
        # the 4th yield, round 2's advance (200) has committed; round 3's
        # advance (300) lands after that yield, so we assert >= 200.
        assert p._last_since["prematch"] >= 200
        assert p._last_since["live"] == 50

        # First two are the initial home+away observation (old_price None).
        first_two = changes[:2]
        assert {c.side for c in first_two} == {"home", "away"}
        assert all(c.old_price is None for c in first_two)
        assert all(c.event_id == "1001" for c in changes)

        # Third change is the home delta only (away unchanged → not re-emitted).
        third = changes[2]
        assert third.side == "home"
        assert third.old_price == 1.80
        assert third.new_price == 1.70
        assert third.source_ts == 199.0  # event ``last``

        # Fourth change is the next home delta.
        fourth = changes[3]
        assert fourth.side == "home"
        assert fourth.old_price == 1.70
        assert fourth.new_price == 1.65

    @pytest.mark.asyncio
    async def test_no_tennis_sport_id_stream_exits(self):
        routes = {"/kit/v1/sports": FakeResponse(200, [{"id": 1, "name": "Soccer"}])}
        p = PinnacleRapidApiProvider(api_key="k", session=make_session(routes))
        out = []
        with patch("asyncio.sleep", new=_instant_sleep):
            async for ch in p.stream_price_changes(["tennis"]):
                out.append(ch)
        assert out == []


async def _instant_sleep(*_args, **_kwargs):
    return None


# ---------------------------------------------------------------------------
# 4. Tour inference unit test
# ---------------------------------------------------------------------------

class TestTourInference:
    def test_atp(self):
        assert PinnacleRapidApiProvider._infer_tour("ATP Rome") == "ATP"

    def test_wta(self):
        assert PinnacleRapidApiProvider._infer_tour("WTA Madrid") == "WTA"

    def test_wta_before_atp_ordering(self):
        # A name containing both should resolve to WTA (checked first).
        assert PinnacleRapidApiProvider._infer_tour("WTA / ATP mixed") == "WTA"

    def test_challenger(self):
        assert PinnacleRapidApiProvider._infer_tour("ATP Challenger Busan") == "ATP"
        assert PinnacleRapidApiProvider._infer_tour("Challenger Tour Event") == "Challenger"

    def test_itf(self):
        assert PinnacleRapidApiProvider._infer_tour("ITF Cancun") == "ITF"

    def test_unknown(self):
        assert PinnacleRapidApiProvider._infer_tour("Some Exhibition") == ""
        assert PinnacleRapidApiProvider._infer_tour(None) == ""


# ---------------------------------------------------------------------------
# 5. 429 backoff in _get_json
# ---------------------------------------------------------------------------

class TestBackoff:
    def test_429_then_200_retries_and_succeeds(self):
        routes = {
            "/kit/v1/sports": [
                FakeResponse(429, {"message": "rate limited"}),
                FakeResponse(200, SPORTS_RESPONSE),
            ],
        }
        sess = make_session(routes)
        p = PinnacleRapidApiProvider(api_key="k", session=sess)

        with patch("time.sleep") as mock_sleep:
            result = p._get_json("sports")

        assert result == SPORTS_RESPONSE
        assert mock_sleep.called
        # First backoff step is 1s.
        assert mock_sleep.call_args_list[0][0][0] == 1
        # One 429 then success → exactly 2 GETs.
        assert sess.get.call_count == 2

    def test_repeated_429_eventually_gives_up(self):
        routes = {"/kit/v1/sports": FakeResponse(429, {"message": "rate limited"})}
        sess = make_session(routes)
        p = PinnacleRapidApiProvider(api_key="k", session=sess)
        with patch("time.sleep"):
            result = p._get_json("sports")
        assert result is None
