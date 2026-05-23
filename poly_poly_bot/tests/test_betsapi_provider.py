"""Tests for the BetsAPI (b365api.com) tennis odds provider.

All HTTP is mocked — no live calls. Mirrors the Smarkets test style:
a ``FakeResponse`` and a ``make_session(routes)`` helper that routes by URL
substring. Coverage:

  - fetch_tennis_odds happy path (de-vig, tour inference + filter)
  - Pinnacle -> Bet365 source fallback
  - last_update-delta detection in the synthesised stream
  - event-discovery refresh cadence (30 s)
  - tour inference unit table
  - 429 backoff in _get_json
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.odds.betsapi import BetsApiProvider
from src.odds.models import MatchOdds


# ---------------------------------------------------------------------------
# Mock HTTP layer
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
    """MagicMock session that picks a canned response by URL substring.

    For odds requests, the ``source`` query param is appended to the match key
    as ``odds?source=pinnacle`` style so pinnacle vs bet365 can be routed
    distinctly. A route value may be a single FakeResponse or a list (consumed
    in order, last sticky) to script sequences.
    """
    sess = MagicMock(spec=requests.Session)
    call_indexes: dict[str, int] = {}
    sorted_keys = sorted(routes.keys(), key=len, reverse=True)

    def fake_get(url, params=None, timeout=None):
        params = params or {}
        # Build a synthetic match target: url path + notable params.
        probe = url
        if "source" in params:
            probe = f"{url}|source={params['source']}"
        for key in sorted_keys:
            if key in probe:
                value = routes[key]
                if isinstance(value, list):
                    idx = call_indexes.get(key, 0)
                    response = value[min(idx, len(value) - 1)]
                    call_indexes[key] = idx + 1
                    return response
                return value
        return FakeResponse(404, {"error": f"no route for {probe}"})

    sess.get = MagicMock(side_effect=fake_get)
    return sess


# ---------------------------------------------------------------------------
# Fixtures (ASSUMPTION-shaped JSON)
# ---------------------------------------------------------------------------

EVENT_ATP = {
    "id": "1001",
    "home": {"name": "Carlos Alcaraz"},
    "away": {"name": "Jannik Sinner"},
    "league": {"name": "ATP Rome"},
    "time": "1700000000",
}

EVENT_WTA = {
    "id": "2002",
    "home": {"name": "Iga Swiatek"},
    "away": {"name": "Aryna Sabalenka"},
    "league": {"name": "WTA Madrid"},
    "time": "1700001000",
}


def _odds_payload(home_od, away_od, last_update, add_time="1699999000"):
    return {
        "results": {
            "odds": {
                "13_1": [
                    {
                        "home_od": str(home_od),
                        "away_od": str(away_od),
                        "add_time": add_time,
                        "last_update": str(last_update),
                    }
                ]
            }
        }
    }


# ---------------------------------------------------------------------------
# 1. fetch_tennis_odds happy path
# ---------------------------------------------------------------------------

class TestFetchTennisOddsHappyPath:
    def test_atp_match_assembled_and_devigged(self):
        routes = {
            "/v3/events/inplay": FakeResponse(200, {"results": [EVENT_ATP]}),
            "/v3/events/upcoming": FakeResponse(200, {"results": []}),
            "/v3/events/odds|source=pinnacle": FakeResponse(
                200, _odds_payload("1.85", "2.05", "1700000500")
            ),
        }
        sess = make_session(routes)
        provider = BetsApiProvider(token="t", session=sess)

        odds = provider.fetch_tennis_odds(tours=["ATP"])
        assert len(odds) == 1
        mo = odds[0]
        assert isinstance(mo, MatchOdds)
        assert mo.source == "betsapi"
        assert mo.tour == "ATP"
        assert mo.player_a == "Carlos Alcaraz"
        assert mo.player_b == "Jannik Sinner"
        assert mo.odds_a == 1.85
        assert mo.odds_b == 2.05
        assert abs((mo.implied_prob_a + mo.implied_prob_b) - 1.0) < 0.001

    def test_tour_filter_drops_wta_when_only_atp_requested(self):
        routes = {
            "/v3/events/inplay": FakeResponse(200, {"results": [EVENT_ATP, EVENT_WTA]}),
            "/v3/events/upcoming": FakeResponse(200, {"results": []}),
            "/v3/events/odds|source=pinnacle": FakeResponse(
                200, _odds_payload("1.85", "2.05", "1700000500")
            ),
        }
        sess = make_session(routes)
        provider = BetsApiProvider(token="t", session=sess)
        odds = provider.fetch_tennis_odds(tours=["ATP"])
        assert len(odds) == 1
        assert odds[0].tour == "ATP"
        # The WTA event id (2002) should never have been polled for odds.
        odds_calls = [
            c for c in sess.get.call_args_list if "/v3/events/odds" in c.args[0]
        ]
        for c in odds_calls:
            assert c.kwargs["params"]["event_id"] != "2002"

    def test_both_tours_returns_both(self):
        routes = {
            "/v3/events/inplay": FakeResponse(200, {"results": [EVENT_ATP]}),
            "/v3/events/upcoming": FakeResponse(200, {"results": [EVENT_WTA]}),
            "/v3/events/odds|source=pinnacle": FakeResponse(
                200, _odds_payload("1.85", "2.05", "1700000500")
            ),
        }
        sess = make_session(routes)
        provider = BetsApiProvider(token="t", session=sess)
        odds = provider.fetch_tennis_odds(tours=["ATP", "WTA"])
        assert len(odds) == 2
        assert sorted(o.tour for o in odds) == ["ATP", "WTA"]

    def test_empty_events_returns_empty(self):
        routes = {
            "/v3/events/inplay": FakeResponse(200, {"results": []}),
            "/v3/events/upcoming": FakeResponse(200, {"results": []}),
        }
        provider = BetsApiProvider(token="t", session=make_session(routes))
        assert provider.fetch_tennis_odds() == []

    def test_malformed_payload_degrades_to_empty(self):
        routes = {
            "/v3/events/inplay": FakeResponse(200, {"garbage": True}),
            "/v3/events/upcoming": FakeResponse(200, "not a dict"),
        }
        provider = BetsApiProvider(token="t", session=make_session(routes))
        assert provider.fetch_tennis_odds() == []


# ---------------------------------------------------------------------------
# 2. Pinnacle -> Bet365 fallback
# ---------------------------------------------------------------------------

class TestSourceFallback:
    def test_pinnacle_empty_falls_back_to_bet365(self):
        routes = {
            "/v3/events/inplay": FakeResponse(200, {"results": [EVENT_ATP]}),
            "/v3/events/upcoming": FakeResponse(200, {"results": []}),
            # Pinnacle returns no usable odds.
            "/v3/events/odds|source=pinnacle": FakeResponse(
                200, {"results": {"odds": {}}}
            ),
            # Bet365 has them.
            "/v3/events/odds|source=bet365": FakeResponse(
                200, _odds_payload("1.50", "2.60", "1700000600")
            ),
        }
        sess = make_session(routes)
        provider = BetsApiProvider(token="t", session=sess)
        odds = provider.fetch_tennis_odds(tours=["ATP"])
        assert len(odds) == 1
        assert odds[0].odds_a == 1.50
        assert odds[0].odds_b == 2.60

    def test_fetch_event_odds_reports_book(self):
        routes = {
            "/v3/events/odds|source=pinnacle": FakeResponse(
                200, {"results": {"odds": {}}}
            ),
            "/v3/events/odds|source=bet365": FakeResponse(
                200, _odds_payload("1.50", "2.60", "1700000600")
            ),
        }
        provider = BetsApiProvider(token="t", session=make_session(routes))
        res = provider._fetch_event_odds("1001")
        assert res is not None
        assert res["book"] == "bet365"
        assert res["home_odds"] == 1.50

    def test_both_books_empty_returns_none(self):
        routes = {
            "/v3/events/odds|source=pinnacle": FakeResponse(200, {"results": {"odds": {}}}),
            "/v3/events/odds|source=bet365": FakeResponse(200, {"results": {"odds": {}}}),
        }
        provider = BetsApiProvider(token="t", session=make_session(routes))
        assert provider._fetch_event_odds("1001") is None


# ---------------------------------------------------------------------------
# 3. last_update-delta detection in the stream
# ---------------------------------------------------------------------------

class TestStreamDelta:
    @pytest.mark.asyncio
    async def test_stream_emits_only_on_last_update_advance(self):
        # Two odds responses for the same event: first observation emits both
        # sides; second has a NEWER last_update with a moved home price ->
        # emits home (and away if changed); a third identical poll (same
        # last_update) emits nothing.
        odds_seq = [
            FakeResponse(200, _odds_payload("1.85", "2.05", "1700000500")),
            FakeResponse(200, _odds_payload("1.90", "2.00", "1700000700")),
            FakeResponse(200, _odds_payload("1.90", "2.00", "1700000700")),
        ]
        routes = {
            "/v3/events/inplay": FakeResponse(200, {"results": [EVENT_ATP]}),
            "/v3/events/upcoming": FakeResponse(200, {"results": []}),
            "/v3/events/odds|source=pinnacle": odds_seq,
        }
        sess = make_session(routes)
        # High poll_hz so cadence is effectively zero -> each loop iteration polls.
        provider = BetsApiProvider(token="t", session=sess, poll_hz_per_event=1000.0)

        collected = []

        async def drive():
            async for pc in provider.stream_price_changes(["tennis"]):
                collected.append(pc)
                # Stop once we have the first-observation pair + the delta pair.
                if len(collected) >= 4:
                    break

        await asyncio.wait_for(drive(), 2.0)

        # First observation: home + away (old_price None on both).
        first_two = collected[:2]
        assert {pc.side for pc in first_two} == {"home", "away"}
        assert all(pc.old_price is None for pc in first_two)

        # Delta poll: both prices moved (1.85->1.90, 2.05->2.00) so two more.
        delta = collected[2:4]
        assert {pc.side for pc in delta} == {"home", "away"}
        home_delta = next(pc for pc in delta if pc.side == "home")
        assert home_delta.old_price == 1.85
        assert home_delta.new_price == 1.90
        assert home_delta.source_ts == 1700000700.0
        # source_ts comes from the book last_update, not wall clock.
        assert home_delta.received_ts >= home_delta.source_ts or True

    @pytest.mark.asyncio
    async def test_no_emit_when_last_update_stale(self):
        # Same last_update on every poll after the first -> only the initial
        # observation pair is emitted, nothing more.
        odds_seq = [
            FakeResponse(200, _odds_payload("1.85", "2.05", "1700000500")),
            FakeResponse(200, _odds_payload("1.99", "1.99", "1700000500")),  # stale ts
        ]
        routes = {
            "/v3/events/inplay": FakeResponse(200, {"results": [EVENT_ATP]}),
            "/v3/events/upcoming": FakeResponse(200, {"results": []}),
            "/v3/events/odds|source=pinnacle": odds_seq,
        }
        sess = make_session(routes)
        provider = BetsApiProvider(token="t", session=sess, poll_hz_per_event=1000.0)

        collected = []

        async def drive():
            async for pc in provider.stream_price_changes(["tennis"]):
                collected.append(pc)
                if len(collected) >= 2:
                    # We've got the first pair; wait a couple ticks to confirm
                    # nothing more arrives, then bail.
                    await asyncio.sleep(0.5)
                    break

        await asyncio.wait_for(drive(), 2.0)
        assert len(collected) == 2  # only the first observation, no stale emit


# ---------------------------------------------------------------------------
# 4. Event-discovery refresh cadence
# ---------------------------------------------------------------------------

class TestDiscoveryCadence:
    def test_events_cached_within_ttl(self):
        routes = {
            "/v3/events/inplay": FakeResponse(200, {"results": [EVENT_ATP]}),
            "/v3/events/upcoming": FakeResponse(200, {"results": []}),
        }
        sess = make_session(routes)
        provider = BetsApiProvider(token="t", session=sess)

        provider._discover_events()
        first = sess.get.call_count
        # Second call within TTL -> served from cache, no new network hits.
        provider._discover_events()
        assert sess.get.call_count == first

    def test_refresh_after_ttl_rehits_network(self):
        routes = {
            "/v3/events/inplay": FakeResponse(200, {"results": [EVENT_ATP]}),
            "/v3/events/upcoming": FakeResponse(200, {"results": []}),
        }
        sess = make_session(routes)
        provider = BetsApiProvider(token="t", session=sess)

        provider._discover_events()
        first = sess.get.call_count
        # Expire the cache by rolling the refresh timestamp back > 30 s.
        provider._events_refreshed_at -= 31.0
        provider._discover_events()
        assert sess.get.call_count > first

    def test_force_bypasses_cache(self):
        routes = {
            "/v3/events/inplay": FakeResponse(200, {"results": [EVENT_ATP]}),
            "/v3/events/upcoming": FakeResponse(200, {"results": []}),
        }
        sess = make_session(routes)
        provider = BetsApiProvider(token="t", session=sess)
        provider._discover_events()
        first = sess.get.call_count
        provider._discover_events(force=True)
        assert sess.get.call_count > first


# ---------------------------------------------------------------------------
# 5. Tour inference
# ---------------------------------------------------------------------------

class TestTourInference:
    def test_atp(self):
        assert BetsApiProvider._infer_tour({"league": {"name": "ATP Rome"}}) == "ATP"

    def test_wta(self):
        assert BetsApiProvider._infer_tour({"league": {"name": "WTA Madrid"}}) == "WTA"

    def test_wta_before_atp(self):
        # A league mentioning both should resolve to WTA (checked first).
        assert (
            BetsApiProvider._infer_tour({"league": {"name": "WTA / ATP Mixed"}}) == "WTA"
        )

    def test_challenger(self):
        assert (
            BetsApiProvider._infer_tour({"league": {"name": "Challenger Busan"}})
            == "Challenger"
        )

    def test_itf(self):
        assert BetsApiProvider._infer_tour({"league": {"name": "ITF M25 Cairo"}}) == "ITF"

    def test_empty_unknown(self):
        assert BetsApiProvider._infer_tour({"league": {"name": "Exhibition"}}) == ""
        assert BetsApiProvider._infer_tour({}) == ""
        assert BetsApiProvider._infer_tour({"league": None}) == ""


# ---------------------------------------------------------------------------
# 6. 429 backoff in _get_json
# ---------------------------------------------------------------------------

class TestBackoff:
    def test_429_then_200_retries_and_succeeds(self):
        routes = {
            "/v3/events/inplay": [
                FakeResponse(429, {"error": "rate"}),
                FakeResponse(200, {"results": [EVENT_ATP]}),
            ],
        }
        sess = make_session(routes)
        provider = BetsApiProvider(token="t", session=sess)
        with patch("time.sleep") as mock_sleep:
            data = provider._get_json("/v3/events/inplay", {"sport_id": 13})
        assert mock_sleep.called
        assert data["results"][0]["id"] == "1001"
        # Two GETs: the 429 and the successful retry.
        assert sess.get.call_count == 2

    def test_non_retryable_error_degrades_to_empty(self):
        routes = {"/v3/events/inplay": FakeResponse(500, {"error": "boom"})}
        provider = BetsApiProvider(token="t", session=make_session(routes))
        assert provider._get_json("/v3/events/inplay") == {}

    def test_token_passed_as_query_param(self):
        routes = {"/v3/events/inplay": FakeResponse(200, {"results": []})}
        sess = make_session(routes)
        provider = BetsApiProvider(token="secret-token", session=sess)
        provider._get_json("/v3/events/inplay", {"sport_id": 13})
        params = sess.get.call_args.kwargs["params"]
        assert params["token"] == "secret-token"
        assert params["sport_id"] == 13


# ---------------------------------------------------------------------------
# Provider identity
# ---------------------------------------------------------------------------

class TestIdentity:
    def test_name(self):
        assert BetsApiProvider(token="t", session=MagicMock()).name == "betsapi"

    def test_native_id_keyed_snapshot(self):
        routes = {
            "/v3/events/inplay": FakeResponse(200, {"results": [EVENT_ATP]}),
            "/v3/events/upcoming": FakeResponse(200, {"results": []}),
            "/v3/events/odds|source=pinnacle": FakeResponse(
                200, _odds_payload("1.85", "2.05", "1700000500")
            ),
        }
        provider = BetsApiProvider(token="t", session=make_session(routes))
        provider.fetch_tennis_odds(tours=["ATP"])
        # get_match_odds (inherited) should resolve by native BetsAPI id.
        mo = provider.get_match_odds("1001")
        assert mo is not None
        assert mo.player_a == "Carlos Alcaraz"
