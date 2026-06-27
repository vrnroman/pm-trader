"""Tests for the real-money execution cost model (copy_cost)."""
from __future__ import annotations

import pytest

from src.copy_trading.copy_cost import (
    DEFAULT_CATEGORY_COST,
    DEFAULT_EDGE_MARGIN,
    CostModel,
    _parse_cost_env,
)


def test_cost_of_known_and_unknown_category():
    m = CostModel(category_cost={"crypto": 0.05, "sports": 0.12}, fallback=0.10)
    assert m.cost_of("crypto") == 0.05
    assert m.cost_of("sports") == 0.12
    assert m.cost_of("nonsense") == 0.10        # falls back
    assert m.cost_of("CRYPTO") == 0.05          # case-insensitive


def test_edge_floor_is_cost_plus_margin():
    m = CostModel(category_cost={"sports": 0.12}, fallback=0.10, margin=0.03)
    assert m.edge_floor("sports") == pytest.approx(0.15)
    assert m.edge_floor("other") == pytest.approx(0.13)   # fallback + margin


def test_net_roi_deducts_cost():
    m = CostModel(category_cost={"sports": 0.12}, fallback=0.10)
    assert m.net_roi(0.20, "sports") == pytest.approx(0.08)
    assert m.net_roi(0.20, "crypto") == pytest.approx(0.10)  # fallback cost


def test_sports_is_costlier_than_crypto_in_defaults():
    # the empirically-anchored ordering that drives the gate: thin sports books
    # cost more round-trip than liquid crypto.
    assert DEFAULT_CATEGORY_COST["sports"] > DEFAULT_CATEGORY_COST["crypto"]


def test_parse_cost_env():
    assert _parse_cost_env("crypto:0.05,sports:0.12") == {"crypto": 0.05, "sports": 0.12}
    assert _parse_cost_env("") == {}
    assert _parse_cost_env("garbage,sports:nope,research:0.06") == {"research": 0.06}


def test_from_env_overrides(monkeypatch):
    monkeypatch.setenv("COPY_CATEGORY_COST", "sports:0.20")
    monkeypatch.setenv("COPY_EDGE_MARGIN", "0.05")
    m = CostModel.from_env()
    assert m.cost_of("sports") == 0.20             # overridden
    assert m.cost_of("crypto") == DEFAULT_CATEGORY_COST["crypto"]  # default kept
    assert m.margin == 0.05
    assert m.edge_floor("sports") == pytest.approx(0.25)


def test_from_env_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("COPY_CATEGORY_COST", raising=False)
    monkeypatch.delenv("COPY_EDGE_MARGIN", raising=False)
    monkeypatch.delenv("COPY_COST_FALLBACK", raising=False)
    m = CostModel.from_env()
    assert m.cost_of("sports") == DEFAULT_CATEGORY_COST["sports"]
    assert m.margin == DEFAULT_EDGE_MARGIN
