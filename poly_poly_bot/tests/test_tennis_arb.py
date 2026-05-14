"""Tests for Strategy #3: Tennis Odds Arbitrage."""

import json
import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.odds.models import MatchOdds, OddsComparison
from src.tennis.tennis_arb import (
    TennisArbStrategy,
    _extract_player_from_question,
    _match_player_to_odds,
    _normalize_name,
)


# ── Player name extraction tests ────────────────────────────────────────


class TestExtractPlayerFromQuestion:
    def test_will_pattern(self):
        assert _extract_player_from_question(
            "Will Jannik Sinner win the 2026 ATP Monte-Carlo Masters?"
        ) == "Jannik Sinner"

    def test_to_win_pattern(self):
        assert _extract_player_from_question(
            "Jannik Sinner to win ATP Monte Carlo"
        ) == "Jannik Sinner"

    def test_vs_pattern(self):
        assert _extract_player_from_question(
            "Sinner vs Rublev: Who will win?"
        ) == "Sinner"

    def test_empty_question(self):
        assert _extract_player_from_question("") == ""

    def test_unrecognized_format(self):
        assert _extract_player_from_question("Random market question") == ""


# ── Name normalization tests ────────────────────────────────────────────


class TestNormalizeName:
    def test_lowercase(self):
        assert _normalize_name("Jannik SINNER") == "jannik sinner"

    def test_strips_whitespace(self):
        assert _normalize_name("  Sinner  ") == "sinner"

    def test_removes_jr_suffix(self):
        assert _normalize_name("John Smith Jr.") == "john smith"

    def test_removes_special_chars(self):
        assert _normalize_name("O'Brien-Smith") == "obriensmith"


# ── Player matching tests ───────────────────────────────────────────────


class TestMatchPlayerToOdds:
    def test_exact_match_player_a(self):
        side, prob = _match_player_to_odds(
            "Jannik Sinner", "Jannik Sinner", "Andrey Rublev", 0.72, 0.28
        )
        assert side == "A"
        assert prob == 0.72

    def test_exact_match_player_b(self):
        side, prob = _match_player_to_odds(
            "Andrey Rublev", "Jannik Sinner", "Andrey Rublev", 0.72, 0.28
        )
        assert side == "B"
        assert prob == 0.28

    def test_last_name_match(self):
        side, prob = _match_player_to_odds(
            "Sinner", "Jannik Sinner", "Andrey Rublev", 0.72, 0.28
        )
        assert side == "A"
        assert prob == 0.72

    def test_substring_match(self):
        side, prob = _match_player_to_odds(
            "J. Sinner", "Jannik Sinner", "Andrey Rublev", 0.72, 0.28
        )
        # Should match via last name
        assert side == "A"
        assert prob == 0.72

    def test_no_match(self):
        side, prob = _match_player_to_odds(
            "Carlos Alcaraz", "Jannik Sinner", "Andrey Rublev", 0.72, 0.28
        )
        assert side is None
        assert prob == 0.0

    def test_case_insensitive(self):
        side, prob = _match_player_to_odds(
            "jannik sinner", "Jannik Sinner", "Andrey Rublev", 0.72, 0.28
        )
        assert side == "A"


# ── Kelly sizing tests ──────────────────────────────────────────────────


class TestKellySizing:
    def setup_method(self):
        self.strategy = TennisArbStrategy(
            max_bet_size=100.0,
            kelly_fraction=0.25,
            preview_mode=True,
        )

    def test_positive_edge_gives_positive_size(self):
        size = self.strategy._calculate_bet_size(sharp_prob=0.72, market_price=0.58)
        assert size > 0
        assert size <= 100.0

    def test_no_edge_gives_zero(self):
        size = self.strategy._calculate_bet_size(sharp_prob=0.50, market_price=0.55)
        assert size == 0.0

    def test_capped_at_max(self):
        # Very large edge should still be capped
        size = self.strategy._calculate_bet_size(sharp_prob=0.95, market_price=0.20)
        assert size <= 100.0

    def test_zero_price_gives_zero(self):
        size = self.strategy._calculate_bet_size(sharp_prob=0.72, market_price=0.0)
        assert size == 0.0

    def test_edge_price_at_one(self):
        size = self.strategy._calculate_bet_size(sharp_prob=0.72, market_price=1.0)
        assert size == 0.0

    def test_kelly_below_min_is_floored(self):
        """A small-but-positive Kelly recommendation must be rounded up to
        ``min_bet_size`` so the resulting order is still above Polymarket's
        minimum (~$5). Otherwise we'd emit unfillable signals every scan
        for low-edge / extreme-price markets."""
        strategy = TennisArbStrategy(
            max_bet_size=100.0,
            kelly_fraction=0.25,
            min_bet_size=5.0,
            preview_mode=True,
        )
        # The exact case the user reported: sharp 28% vs PM 19% → Kelly
        # produces ~$2.78, below the $5 floor.
        size = strategy._calculate_bet_size(sharp_prob=0.28, market_price=0.19)
        assert size == pytest.approx(5.0, abs=1e-6)

    def test_kelly_fraction_override_scales_size_down(self):
        """The second-bet path passes a smaller kelly_fraction so the add
        is strictly smaller than the first bet at the same edge."""
        strategy = TennisArbStrategy(
            max_bet_size=100.0,
            kelly_fraction=0.30,
            preview_mode=True,
        )
        full = strategy._calculate_bet_size(0.70, 0.40)
        small = strategy._calculate_bet_size(0.70, 0.40, kelly_fraction=0.20)
        assert small < full
        # The ratio matches the kelly fraction ratio (clamped by min_bet_size).
        if small > strategy.min_bet_size:
            assert small == pytest.approx(full * (0.20 / 0.30), rel=1e-4)

    def test_kelly_zero_is_not_floored(self):
        """No-edge / negative-edge cases must still return 0 — the floor
        only kicks in when Kelly is positive but tiny."""
        strategy = TennisArbStrategy(
            max_bet_size=100.0,
            kelly_fraction=0.25,
            min_bet_size=5.0,
            preview_mode=True,
        )
        assert strategy._calculate_bet_size(sharp_prob=0.50, market_price=0.55) == 0.0
        assert strategy._calculate_bet_size(sharp_prob=0.72, market_price=0.0) == 0.0


# ── Signal saving tests ─────────────────────────────────────────────────


class TestSignalSaving:
    def test_saves_to_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                preview_mode=True,
                data_dir=tmpdir,
            )

            signals = [
                {
                    "strategy": "tennis_arb",
                    "player_a": "Sinner",
                    "player_b": "Rublev",
                    "divergence": 0.14,
                    "timestamp": "2026-04-08T15:00:00+08:00",
                }
            ]

            strategy._save_signals(signals)

            history_path = os.path.join(tmpdir, "tennis_trades.jsonl")
            assert os.path.exists(history_path)

            with open(history_path) as f:
                lines = f.readlines()
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["strategy"] == "tennis_arb"
            assert data["divergence"] == 0.14

    def test_appends_to_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                preview_mode=True,
                data_dir=tmpdir,
            )

            strategy._save_signals([{"signal": 1}])
            strategy._save_signals([{"signal": 2}])

            history_path = os.path.join(tmpdir, "tennis_trades.jsonl")
            with open(history_path) as f:
                lines = f.readlines()
            assert len(lines) == 2

    def test_no_data_dir_skips(self):
        strategy = TennisArbStrategy(
            preview_mode=True,
            data_dir="",
        )
        # Should not raise
        strategy._save_signals([{"signal": 1}])


# ── Full scan integration test (mocked) ─────────────────────────────────


class TestScanIntegration:
    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_scan_finds_divergence(self, mock_odds, mock_pm):
        mock_odds.return_value = [
            MatchOdds.from_decimal_odds(
                source="pinnacle",
                tournament="ATP Monte-Carlo",
                tour="ATP",
                player_a="Jannik Sinner",
                player_b="Andrey Rublev",
                odds_a=1.40,
                odds_b=3.00,
            )
        ]

        mock_pm.return_value = [
            {
                "event_title": "Sinner vs Rublev (ATP Monte-Carlo)",
                "event_slug": "sinner-vs-rublev-monte-carlo",
                "event_end_date": "",
                "question": "Will Jannik Sinner beat Andrey Rublev?",
                "player": "Jannik Sinner",
                "group_item_title": "Jannik Sinner",
                "yes_price": 0.58,
                "volume": 200000,
                "liquidity": 50000,
                "market_id": "mkt_123",
                "condition_id": "cond_123",
                "token_id_yes": "tok_123",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.10,
                max_bet_size=100,
                kelly_fraction=0.25,
                preview_mode=True,
                data_dir=tmpdir,
            )

            signals = strategy.scan()

        assert len(signals) >= 1
        sig = signals[0]
        assert sig["strategy"] == "tennis_arb"
        assert sig["player_a"] == "Jannik Sinner"
        assert sig["polymarket_price"] == 0.58
        assert sig["divergence"] > 0.10
        assert sig["side"] == "BUY YES"
        assert sig["bet_size"] > 0
        assert sig["preview"] is True

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_scan_no_signals_below_threshold(self, mock_odds, mock_pm):
        mock_odds.return_value = [
            MatchOdds.from_decimal_odds(
                source="pinnacle",
                tournament="ATP Test",
                tour="ATP",
                player_a="A",
                player_b="B",
                odds_a=2.0,
                odds_b=2.0,
            )
        ]

        mock_pm.return_value = [
            {
                "event_title": "A vs B",
                "event_slug": "a-vs-b",
                "event_end_date": "",
                "question": "Will A beat B in the test?",
                "player": "A",
                "group_item_title": "A",
                "yes_price": 0.48,  # Close to sharp 0.50, divergence ~0.02
                "volume": 100000,
                "liquidity": 20000,
                "market_id": "mkt_1",
                "condition_id": "cond_1",
                "token_id_yes": "tok_1",
            }
        ]

        strategy = TennisArbStrategy(
            min_divergence=0.10,
            preview_mode=True,
        )

        signals = strategy.scan()
        assert len(signals) == 0

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_scan_empty_odds(self, mock_odds, mock_pm):
        mock_odds.return_value = []
        mock_pm.return_value = []

        strategy = TennisArbStrategy(
            preview_mode=True,
        )

        signals = strategy.scan()
        assert signals == []


# ── Paper-book + auto-resolve integration ─────────────────────────────


class TestPaperBookIntegration:
    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_signal_opens_paper_position(self, mock_odds, mock_pm):
        mock_odds.return_value = [
            MatchOdds.from_decimal_odds(
                source="smarkets", tournament="Atp Rome", tour="ATP",
                player_a="Hugo Dellien", player_b="Jesper de Jong",
                odds_a=1.55, odds_b=2.55,
            )
        ]
        mock_pm.return_value = [{
            "event_title": "Hugo Dellien vs Jesper de Jong",
            "event_slug": "rome-2026-dellien", "event_end_date": "",
            "question": "Will Hugo Dellien beat Jesper de Jong?",
            "player": "Hugo Dellien", "group_item_title": "Hugo Dellien",
            "yes_price": 0.50, "volume": 200000, "liquidity": 50000,
            "market_id": "mkt_1", "condition_id": "0xMATCH1",
            "token_id_yes": "TOKA",
        }]
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.05, preview_mode=True, data_dir=tmpdir,
            )
            signals = strategy.scan()
            assert len(signals) == 1
            assert signals[0]["paper_action"] == "OPEN"
            assert strategy.paper_book.open_position_count() == 1

    @patch.object(TennisArbStrategy, "_fetch_market_resolution")
    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_open_position_auto_resolves_when_market_settles(
        self, mock_odds, mock_pm, mock_resolve,
    ):
        # Open a position on the first scan, then on the second scan have
        # the resolution helper report TOKA as the winner. The book should
        # close the position at exit_price 1.0.
        mock_odds.return_value = [
            MatchOdds.from_decimal_odds(
                source="smarkets", tournament="Atp Rome", tour="ATP",
                player_a="Hugo Dellien", player_b="Jesper de Jong",
                odds_a=1.55, odds_b=2.55,
            )
        ]
        mock_pm.return_value = [{
            "event_title": "Hugo Dellien vs Jesper de Jong",
            "event_slug": "rome-2026-dellien", "event_end_date": "",
            "question": "Will Hugo Dellien beat Jesper de Jong?",
            "player": "Hugo Dellien", "group_item_title": "Hugo Dellien",
            "yes_price": 0.50, "volume": 200000, "liquidity": 50000,
            "market_id": "mkt_1", "condition_id": "0xMATCH1",
            "token_id_yes": "TOKA",
        }]
        # First scan: market still open → no resolution.
        mock_resolve.return_value = None
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.05, preview_mode=True, data_dir=tmpdir,
            )
            strategy._resolve_min_interval_s = 0.0  # disable throttle
            strategy.scan()
            assert strategy.paper_book.open_position_count() == 1

            # Second scan: market resolved with TOKA winning.
            mock_resolve.return_value = "TOKA"
            strategy.scan()
            assert strategy.paper_book.open_position_count() == 0
            closed = strategy.paper_book.closed_positions()
            assert len(closed) == 1
            assert closed[0]["exit_reason"] == "RESOLVED"
            assert closed[0]["exit_price"] == 1.0
            assert closed[0]["realized_pnl_usd"] > 0

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_take_profit_closes_position_when_price_triples(
        self, mock_odds, mock_pm,
    ):
        # Open at 0.20 on the first scan, then on the second scan the PM
        # price is 0.60 (exactly 3×) — the take-profit gate should close
        # the position and emit a TAKE_PROFIT signal alongside any new
        # divergence signals.
        mock_odds.return_value = [
            MatchOdds.from_decimal_odds(
                source="smarkets", tournament="Atp Rome", tour="ATP",
                player_a="Hugo Dellien", player_b="Jesper de Jong",
                odds_a=2.5, odds_b=1.6,
            )
        ]
        # First scan: PM price 0.20, sharp implies ~0.40 → big edge → OPEN.
        first_pm = [{
            "event_title": "Hugo Dellien vs Jesper de Jong",
            "event_slug": "rome-2026-dellien", "event_end_date": "",
            "question": "Will Hugo Dellien beat Jesper de Jong?",
            "player": "Hugo Dellien", "group_item_title": "Hugo Dellien",
            "yes_price": 0.20, "volume": 200000, "liquidity": 50000,
            "market_id": "mkt_1", "condition_id": "0xMATCH1",
            "token_id_yes": "TOKA",
        }]
        mock_pm.return_value = first_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.05, preview_mode=True, data_dir=tmpdir,
                take_profit_ratio=3.0,
            )
            signals = strategy.scan()
            assert any(s.get("paper_action") == "OPEN" for s in signals)
            assert strategy.paper_book.open_position_count() == 1

            # Second scan: same market but PM has rallied to 0.60 (exactly
            # 3× entry). Sharp is unchanged at ~0.40, so no fresh BUY signal
            # should appear (PM is now above sharp). The TP gate fires.
            second_pm = [dict(first_pm[0], yes_price=0.60)]
            mock_pm.return_value = second_pm
            signals = strategy.scan()

            tp = [s for s in signals if s.get("paper_action") == "TAKE_PROFIT"]
            assert len(tp) == 1
            assert tp[0]["entry_price"] == pytest.approx(0.20, abs=1e-4)
            assert tp[0]["exit_price"] == pytest.approx(0.60, abs=1e-4)
            assert tp[0]["ratio"] == pytest.approx(3.0, abs=1e-4)
            # Realized PnL = shares × (exit − entry); shares depends on the
            # Kelly-sized bet, so we just assert the quadrupling left us in
            # the green by the right multiplier.
            assert tp[0]["paper_realized_pnl_usd"] > 0
            assert strategy.paper_book.open_position_count() == 0

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_take_profit_holds_below_threshold(self, mock_odds, mock_pm):
        mock_odds.return_value = [
            MatchOdds.from_decimal_odds(
                source="smarkets", tournament="Atp Rome", tour="ATP",
                player_a="Hugo Dellien", player_b="Jesper de Jong",
                odds_a=2.5, odds_b=1.6,
            )
        ]
        first_pm = [{
            "event_title": "Hugo Dellien vs Jesper de Jong",
            "event_slug": "rome-2026-dellien", "event_end_date": "",
            "question": "Will Hugo Dellien beat Jesper de Jong?",
            "player": "Hugo Dellien", "group_item_title": "Hugo Dellien",
            "yes_price": 0.20, "volume": 200000, "liquidity": 50000,
            "market_id": "mkt_1", "condition_id": "0xMATCH1",
            "token_id_yes": "TOKA",
        }]
        mock_pm.return_value = first_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.05, preview_mode=True, data_dir=tmpdir,
                take_profit_ratio=3.0,
            )
            strategy.scan()
            assert strategy.paper_book.open_position_count() == 1

            # Price moves to 0.55 — only 2.75× entry, below the 3× gate.
            mock_pm.return_value = [dict(first_pm[0], yes_price=0.55)]
            signals = strategy.scan()
            assert not any(s.get("paper_action") == "TAKE_PROFIT" for s in signals)
            assert strategy.paper_book.open_position_count() == 1

    def test_fetch_market_resolution_reads_clob_tokens(self):
        """The resolver must read winner state from the CLOB
        ``/markets/{condition_id}`` shape: dict with ``tokens=[{token_id,
        winner, price}, ...]`` and a ``closed`` flag.

        We use CLOB instead of Gamma because Gamma's
        ``/markets?condition_ids=`` filter silently returns ``[]`` for
        closed markets — that's the bug that left tennis paper positions
        showing OPEN forever.
        """
        from unittest.mock import patch as up
        strategy = TennisArbStrategy(preview_mode=True)
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.raise_for_status = lambda: None

        # Closed, winner=A → return TA.
        fake_resp.json.return_value = {
            "closed": True,
            "tokens": [
                {"token_id": "TA", "outcome": "A", "winner": True, "price": 1},
                {"token_id": "TB", "outcome": "B", "winner": False, "price": 0},
            ],
        }
        with up("src.tennis.tennis_arb.requests.get", return_value=fake_resp):
            assert strategy._fetch_market_resolution("0xC") == "TA"

        # Closed, winner=B → return TB.
        fake_resp.json.return_value = {
            "closed": True,
            "tokens": [
                {"token_id": "TA", "outcome": "A", "winner": False, "price": 0},
                {"token_id": "TB", "outcome": "B", "winner": True, "price": 1},
            ],
        }
        with up("src.tennis.tennis_arb.requests.get", return_value=fake_resp):
            assert strategy._fetch_market_resolution("0xC") == "TB"

        # Closed, winner flag missing but prices are 1/0 → fall back to price.
        fake_resp.json.return_value = {
            "closed": True,
            "tokens": [
                {"token_id": "TA", "price": 0},
                {"token_id": "TB", "price": 1},
            ],
        }
        with up("src.tennis.tennis_arb.requests.get", return_value=fake_resp):
            assert strategy._fetch_market_resolution("0xC") == "TB"

        # Open market → None, leaves paper position untouched.
        fake_resp.json.return_value = {
            "closed": False,
            "archived": False,
            "tokens": [
                {"token_id": "TA", "winner": False, "price": 0.4},
                {"token_id": "TB", "winner": False, "price": 0.6},
            ],
        }
        with up("src.tennis.tennis_arb.requests.get", return_value=fake_resp):
            assert strategy._fetch_market_resolution("0xC") is None

        # Archived (some tennis markets archive before closed flips) →
        # treated as settled.
        fake_resp.json.return_value = {
            "closed": False,
            "archived": True,
            "tokens": [
                {"token_id": "TA", "winner": True, "price": 1},
                {"token_id": "TB", "winner": False, "price": 0},
            ],
        }
        with up("src.tennis.tennis_arb.requests.get", return_value=fake_resp):
            assert strategy._fetch_market_resolution("0xC") == "TA"

        # 404 (market unknown to CLOB) → leave open.
        fake_404 = MagicMock()
        fake_404.status_code = 404
        fake_404.raise_for_status = lambda: None
        fake_404.json.return_value = {}
        with up("src.tennis.tennis_arb.requests.get", return_value=fake_404):
            assert strategy._fetch_market_resolution("0xC") is None


# ── Live-ask revalidation gate ──────────────────────────────────────────


def _stub_book(ask_price: float, bid_price: float = 0.0, tick: float = 0.01):
    """Build a CLOB get_order_book mock response."""
    return {
        "asks": [{"price": str(ask_price + 0.01), "size": "100"}, {"price": str(ask_price), "size": "200"}],
        "bids": [{"price": str(max(bid_price - 0.01, 0.001)), "size": "100"}, {"price": str(bid_price or 0.40), "size": "100"}],
        "tick_size": str(tick),
    }


def _odds_sinner_v_rublev(prob_a: float = 0.71):
    """Sharp gives Sinner prob_a (default 71%)."""
    odds_a = 1.0 / prob_a
    odds_b = 1.0 / (1.0 - prob_a)
    return [
        MatchOdds.from_decimal_odds(
            source="pinnacle",
            tournament="ATP Monte-Carlo",
            tour="ATP",
            player_a="Jannik Sinner",
            player_b="Andrey Rublev",
            odds_a=odds_a,
            odds_b=odds_b,
        )
    ]


def _pm_sinner(yes_price: float = 0.58):
    """Gamma quotes Sinner YES at yes_price."""
    return [{
        "event_title": "Sinner vs Rublev (ATP Monte-Carlo)",
        "event_slug": "sinner-vs-rublev",
        "event_end_date": "",
        "question": "Will Jannik Sinner beat Andrey Rublev?",
        "player": "Jannik Sinner",
        "group_item_title": "Jannik Sinner",
        "yes_price": yes_price,
        "volume": 200000,
        "liquidity": 50000,
        "market_id": "mkt_123",
        "condition_id": "cond_123",
        "token_id_yes": "tok_123",
    }]


class TestRevalidationGate:
    """Gamma's price clears 8% but live ask may have moved closer to sharp.

    Floor is 6% of revalidated edge. Below that, drop the signal.
    """

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_no_clob_client_skips_revalidation(self, mock_odds, mock_pm):
        """When clob_client is None (preview/no-key) we fall through to Gamma."""
        mock_odds.return_value = _odds_sinner_v_rublev(0.71)
        mock_pm.return_value = _pm_sinner(0.58)  # Gamma edge ~13%
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=None,
                revalidation_min_divergence=0.06,
            )
            signals = strategy.scan()
        assert len(signals) == 1
        assert signals[0]["polymarket_price"] == 0.58
        assert signals[0]["live_ask"] is None

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_live_ask_above_floor_keeps_signal_with_revalidated_price(self, mock_odds, mock_pm):
        """Gamma 0.58 → ask 0.62 (sharp 0.71 → live edge 9%, > 6% floor)."""
        mock_odds.return_value = _odds_sinner_v_rublev(0.71)
        mock_pm.return_value = _pm_sinner(0.58)
        client = MagicMock()
        client.get_order_book.return_value = _stub_book(ask_price=0.62)
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=client,
                revalidation_min_divergence=0.06,
            )
            signals = strategy.scan()
        assert len(signals) == 1
        sig = signals[0]
        assert sig["polymarket_price"] == 0.62
        assert sig["polymarket_gamma_price"] == 0.58
        assert sig["live_ask"] == 0.62
        # Edge re-computed against live ask (0.71 - 0.62 ≈ 0.09)
        assert sig["divergence"] == pytest.approx(0.09, abs=1e-4)
        assert sig["gamma_divergence"] == pytest.approx(0.13, abs=1e-4)

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_live_ask_below_floor_drops_signal(self, mock_odds, mock_pm):
        """Gamma 0.58 → ask 0.66. Live edge 5% < 6% floor → drop."""
        mock_odds.return_value = _odds_sinner_v_rublev(0.71)
        mock_pm.return_value = _pm_sinner(0.58)
        client = MagicMock()
        client.get_order_book.return_value = _stub_book(ask_price=0.66)
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=client,
                revalidation_min_divergence=0.06,
            )
            signals = strategy.scan()
        assert signals == []

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_book_fetch_failure_drops_signal(self, mock_odds, mock_pm):
        """If the live book request raises, we'd rather miss the bet than fire on stale data."""
        mock_odds.return_value = _odds_sinner_v_rublev(0.71)
        mock_pm.return_value = _pm_sinner(0.58)
        client = MagicMock()
        client.get_order_book.side_effect = RuntimeError("connection reset")
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=client,
                revalidation_min_divergence=0.06,
            )
            signals = strategy.scan()
        assert signals == []

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_empty_book_drops_signal(self, mock_odds, mock_pm):
        """No asks on the book → can't actually buy → drop the signal."""
        mock_odds.return_value = _odds_sinner_v_rublev(0.71)
        mock_pm.return_value = _pm_sinner(0.58)
        client = MagicMock()
        client.get_order_book.return_value = {"asks": [], "bids": [], "tick_size": "0.01"}
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=client,
                revalidation_min_divergence=0.06,
            )
            signals = strategy.scan()
        assert signals == []

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_revalidation_disabled_when_floor_zero(self, mock_odds, mock_pm):
        """revalidation_min_divergence <= 0 turns the gate off entirely."""
        mock_odds.return_value = _odds_sinner_v_rublev(0.71)
        mock_pm.return_value = _pm_sinner(0.58)
        client = MagicMock()
        client.get_order_book.return_value = _stub_book(ask_price=0.99)  # would trip the floor
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=client,
                revalidation_min_divergence=0.0,
            )
            signals = strategy.scan()
        assert len(signals) == 1
        # Falls through to Gamma price
        assert signals[0]["polymarket_price"] == 0.58


# ── Re-bet gate: pyramid-up on widening divergence ───────────────────────


def _dellien_odds(prob_a: float):
    """Smarkets fixture where Dellien (player A) has sharp_prob = prob_a."""
    odds_a = 1.0 / prob_a
    odds_b = 1.0 / (1.0 - prob_a)
    return [
        MatchOdds.from_decimal_odds(
            source="smarkets", tournament="Atp Rome", tour="ATP",
            player_a="Hugo Dellien", player_b="Jesper de Jong",
            odds_a=odds_a, odds_b=odds_b,
        )
    ]


def _dellien_pm(yes_price: float):
    return [{
        "event_title": "Hugo Dellien vs Jesper de Jong",
        "event_slug": "rome-2026-dellien", "event_end_date": "",
        "question": "Will Hugo Dellien beat Jesper de Jong?",
        "player": "Hugo Dellien", "group_item_title": "Hugo Dellien",
        "yes_price": yes_price, "volume": 200000, "liquidity": 50000,
        "market_id": "mkt_1", "condition_id": "0xMATCH1",
        "token_id_yes": "TOKA",
    }]


class TestRebetPyramid:
    """The re-bet gate allows a second bet only when sharp is the mover.

    Same-side rebet requires (in order):
        edge grew ≥ min_edge_step  AND
        pm_price ≥ first_pm_price  AND
        sharp_prob > first_sharp_prob
    capped at max_bets_per_event=2 per condition_id (FLIPs count).
    """

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_second_bet_fires_when_sharp_widens_with_pm_held(
        self, mock_odds, mock_pm,
    ):
        # Scan 1: sharp 0.60, PM 0.40 → edge 0.20 → first bet.
        # Scan 2: sharp 0.70, PM 0.40 → edge 0.30, PM unchanged, sharp +0.10.
        #         All three gates clear → second bet fires.
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=None,
                revalidation_min_divergence=0.0,
                min_edge_step=0.05,
            )
            mock_odds.return_value = _dellien_odds(0.60)
            mock_pm.return_value = _dellien_pm(0.40)
            first = strategy.scan()
            assert len(first) == 1
            assert first[0]["paper_action"] == "OPEN"
            first_bet = first[0]["bet_size"]

            mock_odds.return_value = _dellien_odds(0.70)
            mock_pm.return_value = _dellien_pm(0.40)
            second = strategy.scan()
            assert len(second) == 1
            assert second[0]["paper_action"] == "ADD"
            # Second bet was sized with the smaller second_bet_kelly_fraction
            # — comparing dollar sizes alone is ambiguous because a sharper
            # edge grows the Kelly recommendation, which can offset the
            # fraction cut. Verify against the formula directly.
            expected_full = strategy._calculate_bet_size(0.70, 0.40)
            expected_small = strategy._calculate_bet_size(
                0.70, 0.40, kelly_fraction=strategy.second_bet_kelly_fraction,
            )
            assert second[0]["bet_size"] == pytest.approx(expected_small, abs=1e-2)
            assert expected_small < expected_full
            assert first_bet == pytest.approx(
                strategy._calculate_bet_size(0.60, 0.40), abs=1e-2
            )
            # Paper book now holds a single DCA'd position.
            assert strategy.paper_book.open_position_count() == 1
            pos = strategy.paper_book.open_positions()[0]
            assert pos["entries"] == 2

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_second_bet_blocked_when_pm_dropped(self, mock_odds, mock_pm):
        # Scan 1: sharp 0.60, PM 0.40. Scan 2: sharp 0.75, PM 0.35.
        # Edge grew (0.20 → 0.40), but PM fell — the falling-knife case the
        # new gate explicitly filters out.
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=None,
                revalidation_min_divergence=0.0,
                min_edge_step=0.05,
            )
            mock_odds.return_value = _dellien_odds(0.60)
            mock_pm.return_value = _dellien_pm(0.40)
            strategy.scan()

            mock_odds.return_value = _dellien_odds(0.75)
            mock_pm.return_value = _dellien_pm(0.35)
            second = strategy.scan()
            assert second == []
            assert strategy.paper_book.open_positions()[0]["entries"] == 1

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_third_bet_blocked_by_cap(self, mock_odds, mock_pm):
        # Cap = 2. Even if every gate clears on scan 3, no signal fires.
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=None,
                revalidation_min_divergence=0.0,
                min_edge_step=0.05,
                max_bets_per_event=2,
            )
            mock_odds.return_value = _dellien_odds(0.60)
            mock_pm.return_value = _dellien_pm(0.40)
            strategy.scan()
            mock_odds.return_value = _dellien_odds(0.70)
            mock_pm.return_value = _dellien_pm(0.40)
            strategy.scan()
            mock_odds.return_value = _dellien_odds(0.85)
            mock_pm.return_value = _dellien_pm(0.40)
            third = strategy.scan()
            assert third == []
            # Position is still DCA'd with 2 legs.
            assert strategy.paper_book.open_positions()[0]["entries"] == 2

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_min_edge_step_still_required_on_second_bet(
        self, mock_odds, mock_pm,
    ):
        # Sharp moves up but only marginally — edge grew by <5%. The
        # existing min_edge_step gate must still apply.
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=None,
                revalidation_min_divergence=0.0,
                min_edge_step=0.05,
            )
            mock_odds.return_value = _dellien_odds(0.60)
            mock_pm.return_value = _dellien_pm(0.40)
            strategy.scan()
            # Edge went 0.20 → 0.22 (delta 0.02 < 0.05 step).
            mock_odds.return_value = _dellien_odds(0.62)
            mock_pm.return_value = _dellien_pm(0.40)
            second = strategy.scan()
            assert second == []

    def test_legacy_state_keys_are_migrated_to_condition_id(self):
        """Old ``condition_id:token_id`` keys must migrate cleanly so the
        deploy doesn't accidentally reset bet counters on in-flight markets.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                preview_mode=True, data_dir=tmpdir,
            )
            legacy = {
                "0xCOND:TOKA": {
                    "last_divergence": 0.12,
                    "last_price": 0.38,
                    "last_bet_size": 12.5,
                    "last_ts": "2026-05-11T01:00:00+08:00",
                    "times_emitted": 1,
                    "question": "Will A beat B?",
                    "event_title": "A vs B",
                },
            }
            with open(strategy._bet_state_path(), "w") as f:
                json.dump(legacy, f)
            migrated = strategy._load_bet_state()
            assert "0xCOND" in migrated
            entry = migrated["0xCOND"]
            assert entry["times_emitted"] == 1
            assert entry["first_token_id"] == "TOKA"
            # last_price falls through to first_pm_price for the anchor.
            assert entry["first_pm_price"] == 0.38


# ── bestAsk filter + NO-side evaluation ─────────────────────────────────


def _pm_sinner_rublev(yes_ask: float, yes_bid: float | None = None,
                      yes_price: float | None = None):
    """Sinner-vs-Rublev head-to-head with explicit bid/ask.

    yes_price defaults to the mid of (yes_bid, yes_ask) so take-profit and
    other mid-consumers stay reasonable.
    """
    if yes_bid is None:
        yes_bid = max(0.01, yes_ask - 0.01)
    if yes_price is None:
        yes_price = round((yes_ask + yes_bid) / 2, 4)
    return [{
        "event_title": "Sinner vs Rublev (ATP Monte-Carlo)",
        "event_slug": "sinner-vs-rublev",
        "event_end_date": "",
        "question": "Will Jannik Sinner beat Andrey Rublev?",
        "player": "Jannik Sinner",
        "group_item_title": "Jannik Sinner",
        "yes_price": yes_price,
        "yes_ask": yes_ask,
        "yes_bid": yes_bid,
        "volume": 200000,
        "liquidity": 50000,
        "market_id": "mkt_sr",
        "condition_id": "cond_sr",
        "token_id_yes": "TOK_YES",
        "token_id_no": "TOK_NO",
    }]


def _sinner_rublev_odds(sharp_sinner: float):
    """Smarkets fixture with sharp_sinner probability for Sinner.

    Sharp probabilities are no-vig normalized in from_decimal_odds so
    implied_prob_a + implied_prob_b == 1.
    """
    odds_a = 1.0 / sharp_sinner
    odds_b = 1.0 / (1.0 - sharp_sinner)
    return [
        MatchOdds.from_decimal_odds(
            source="smarkets",
            tournament="ATP Monte-Carlo",
            tour="ATP",
            player_a="Jannik Sinner",
            player_b="Andrey Rublev",
            odds_a=odds_a,
            odds_b=odds_b,
        )
    ]


class TestBothSidesEvaluated:
    """The bot must consider buying NO when the OTHER player is undervalued.

    Worked example from the design conversation:
      Sinner-Rublev head-to-head, YES=0.70, NO=0.31 (yes_bid=0.69).
        sharp_Sinner=0.80  → YES div = +0.10 → BUY YES.
        sharp_Sinner=0.60  → YES div = -0.10 (skip),
                             but sharp_Rublev=0.40 vs NO ask 0.31 → NO div = +0.09 → BUY NO.
    """

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_sharp_favors_yes_player_buys_yes(self, mock_odds, mock_pm):
        mock_odds.return_value = _sinner_rublev_odds(sharp_sinner=0.80)
        mock_pm.return_value = _pm_sinner_rublev(yes_ask=0.70, yes_bid=0.69)
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=None,
                revalidation_min_divergence=0.0,
            )
            signals = strategy.scan()
        assert len(signals) == 1
        sig = signals[0]
        assert sig["side"] == "BUY YES"
        assert sig["token_id"] == "TOK_YES"
        assert sig["target_player"] == "Jannik Sinner"
        assert sig["outcome_label"] == "Jannik Sinner"
        assert sig["polymarket_price"] == pytest.approx(0.70, abs=1e-4)
        assert sig["divergence"] == pytest.approx(0.10, abs=1e-4)

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_sharp_favors_no_player_buys_no(self, mock_odds, mock_pm):
        """Previously this scenario produced zero signals — half the universe."""
        mock_odds.return_value = _sinner_rublev_odds(sharp_sinner=0.60)
        mock_pm.return_value = _pm_sinner_rublev(yes_ask=0.70, yes_bid=0.69)
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=None,
                revalidation_min_divergence=0.0,
            )
            signals = strategy.scan()
        assert len(signals) == 1
        sig = signals[0]
        assert sig["side"] == "BUY NO"
        assert sig["token_id"] == "TOK_NO"
        # The NO bet is on the OTHER player winning.
        assert sig["target_player"] == "Andrey Rublev"
        assert sig["outcome_label"] == "Andrey Rublev"
        # NO ask = 1 - yes_bid = 1 - 0.69 = 0.31
        assert sig["polymarket_price"] == pytest.approx(0.31, abs=1e-4)
        # sharp_Rublev = 1 - 0.60 = 0.40 → div = 0.40 - 0.31 = 0.09
        assert sig["divergence"] == pytest.approx(0.09, abs=1e-4)
        assert sig["sharp_prob"] == pytest.approx(0.40, abs=1e-4)

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_sharp_at_market_neither_side_fires(self, mock_odds, mock_pm):
        """When sharp matches PM closely, neither YES nor NO crosses min_divergence."""
        mock_odds.return_value = _sinner_rublev_odds(sharp_sinner=0.70)
        mock_pm.return_value = _pm_sinner_rublev(yes_ask=0.70, yes_bid=0.69)
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=None,
                revalidation_min_divergence=0.0,
            )
            signals = strategy.scan()
        assert signals == []

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_no_side_skipped_when_token_id_missing(self, mock_odds, mock_pm):
        """If clobTokenIds[1] wasn't populated, drop the NO leg silently."""
        pm = _pm_sinner_rublev(yes_ask=0.70, yes_bid=0.69)
        pm[0]["token_id_no"] = ""
        mock_odds.return_value = _sinner_rublev_odds(sharp_sinner=0.60)
        mock_pm.return_value = pm
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=None,
                revalidation_min_divergence=0.0,
            )
            signals = strategy.scan()
        # YES doesn't qualify, NO would have but token id is missing.
        assert signals == []


class TestBestAskReplacesMidInFilter:
    """The cheap filter now uses bestAsk, not the outcomePrices mid.

    On thin tennis books the mid sits halfway between a wide bid/ask, so
    using the mid as filter price routinely generates phantom signals that
    die at CLOB revalidation. Switching to bestAsk closes that gap.
    """

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_phantom_signal_from_wide_spread_is_filtered(self, mock_odds, mock_pm):
        """mid=0.50 looks like 30% edge vs sharp=0.80; bestAsk=0.78 only 2%."""
        mock_odds.return_value = _sinner_rublev_odds(sharp_sinner=0.80)
        # Wide spread: bid 0.22, ask 0.78, mid 0.50. The cheap filter must
        # see only the 2pp ask-side edge and reject — the 30pp mid-vs-sharp
        # gap is illusory.
        mock_pm.return_value = _pm_sinner_rublev(
            yes_ask=0.78, yes_bid=0.22, yes_price=0.50,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=None,
                revalidation_min_divergence=0.0,
            )
            signals = strategy.scan()
        assert signals == []

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_signal_fires_against_bestask_not_mid(self, mock_odds, mock_pm):
        """When the real bestAsk still leaves edge, a YES signal must fire at the ask."""
        mock_odds.return_value = _sinner_rublev_odds(sharp_sinner=0.80)
        mock_pm.return_value = _pm_sinner_rublev(
            yes_ask=0.65, yes_bid=0.60, yes_price=0.625,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=None,
                revalidation_min_divergence=0.0,
            )
            signals = strategy.scan()
        assert len(signals) == 1
        # polymarket_price reflects the actual buy cost (the ask), not the mid.
        assert signals[0]["polymarket_price"] == pytest.approx(0.65, abs=1e-4)
        assert signals[0]["divergence"] == pytest.approx(0.15, abs=1e-4)

    @patch.object(TennisArbStrategy, "_fetch_polymarket_tennis_markets")
    @patch("src.tennis.tennis_arb.SmarketsProvider.fetch_tennis_odds")
    def test_legacy_pm_dict_without_ask_bid_falls_back_to_yes_price(
        self, mock_odds, mock_pm,
    ):
        """A pm dict missing yes_ask/yes_bid should behave like the old path.

        Keeps every pre-existing test fixture working without refactoring;
        also covers the migration window before the next production fetch.
        """
        mock_odds.return_value = _sinner_rublev_odds(sharp_sinner=0.80)
        legacy_pm = _pm_sinner_rublev(yes_ask=0.58, yes_bid=0.58, yes_price=0.58)
        del legacy_pm[0]["yes_ask"]
        del legacy_pm[0]["yes_bid"]
        mock_pm.return_value = legacy_pm
        with tempfile.TemporaryDirectory() as tmpdir:
            strategy = TennisArbStrategy(
                min_divergence=0.08,
                preview_mode=True,
                data_dir=tmpdir,
                clob_client=None,
                revalidation_min_divergence=0.0,
            )
            signals = strategy.scan()
        assert len(signals) == 1
        assert signals[0]["polymarket_price"] == pytest.approx(0.58, abs=1e-4)


class TestGammaFetchExtractsBidAsk:
    """The Gamma fetch must read bestAsk / bestBid / clobTokenIds[1] from the response."""

    def test_fetch_populates_new_fields_from_gamma_payload(self):
        from unittest.mock import patch as up
        gamma_event = {
            "title": "Sinner vs Rublev",
            "slug": "sinner-vs-rublev",
            "endDate": "",
            "markets": [{
                "id": "mkt_x",
                "conditionId": "cond_x",
                "question": "Will Jannik Sinner beat Andrey Rublev?",
                "outcomePrices": '["0.70", "0.30"]',
                "bestAsk": 0.71,
                "bestBid": 0.69,
                "clobTokenIds": '["TOK_YES_X", "TOK_NO_X"]',
                "volume": "200000",
                "liquidity": "50000",
                "groupItemTitle": "Jannik Sinner",
            }],
        }
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.side_effect = [[gamma_event], []]

        strategy = TennisArbStrategy(preview_mode=True)
        with up("src.tennis.tennis_arb.requests.get", return_value=resp):
            markets = strategy._fetch_polymarket_tennis_markets()

        assert len(markets) == 1
        m = markets[0]
        assert m["yes_ask"] == pytest.approx(0.71, abs=1e-9)
        assert m["yes_bid"] == pytest.approx(0.69, abs=1e-9)
        assert m["yes_price"] == pytest.approx(0.70, abs=1e-9)
        assert m["token_id_yes"] == "TOK_YES_X"
        assert m["token_id_no"] == "TOK_NO_X"

    def test_fetch_falls_back_when_bid_ask_absent(self):
        """Older market payloads without bestAsk/bestBid fall back to mid."""
        from unittest.mock import patch as up
        gamma_event = {
            "title": "Sinner vs Rublev",
            "slug": "sinner-vs-rublev",
            "endDate": "",
            "markets": [{
                "id": "mkt_y",
                "conditionId": "cond_y",
                "question": "Will Jannik Sinner beat Andrey Rublev?",
                "outcomePrices": '["0.60", "0.40"]',
                # bestAsk / bestBid intentionally omitted
                "clobTokenIds": '["TY", "TN"]',
                "volume": "200000",
                "liquidity": "50000",
                "groupItemTitle": "",
            }],
        }
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.side_effect = [[gamma_event], []]

        strategy = TennisArbStrategy(preview_mode=True)
        with up("src.tennis.tennis_arb.requests.get", return_value=resp):
            markets = strategy._fetch_polymarket_tennis_markets()

        assert len(markets) == 1
        m = markets[0]
        assert m["yes_ask"] == pytest.approx(0.60, abs=1e-9)
        assert m["yes_bid"] == pytest.approx(0.60, abs=1e-9)
        assert m["token_id_no"] == "TN"
