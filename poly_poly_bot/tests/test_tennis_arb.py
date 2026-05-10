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

    def test_fetch_market_resolution_reads_outcome_prices(self):
        # Smoke-test the Gamma response parser against the documented
        # shape: outcomePrices = ["1", "0"], clobTokenIds = ["TA", "TB"].
        from unittest.mock import patch as up
        strategy = TennisArbStrategy(preview_mode=True)
        fake_resp = MagicMock()
        fake_resp.json.return_value = [{
            "closed": True,
            "outcomePrices": '["1", "0"]',
            "clobTokenIds": '["TA", "TB"]',
        }]
        fake_resp.raise_for_status = lambda: None
        with up("src.tennis.tennis_arb.requests.get", return_value=fake_resp):
            assert strategy._fetch_market_resolution("0xC") == "TA"

        fake_resp.json.return_value = [{
            "closed": True,
            "outcomePrices": '["0", "1"]',
            "clobTokenIds": '["TA", "TB"]',
        }]
        with up("src.tennis.tennis_arb.requests.get", return_value=fake_resp):
            assert strategy._fetch_market_resolution("0xC") == "TB"

        # Open market → None, leaves paper position untouched.
        fake_resp.json.return_value = [{
            "closed": False, "outcomePrices": '["0.4","0.6"]',
        }]
        with up("src.tennis.tennis_arb.requests.get", return_value=fake_resp):
            assert strategy._fetch_market_resolution("0xC") is None
