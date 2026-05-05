"""Odds data fetching module — Smarkets is the only supported provider."""

from src.odds.base import OddsProvider
from src.odds.models import MatchOdds, OddsComparison
from src.odds.smarkets import SmarketsProvider

__all__ = [
    "OddsProvider",
    "MatchOdds",
    "OddsComparison",
    "SmarketsProvider",
]
