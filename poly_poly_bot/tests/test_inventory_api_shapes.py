"""Contract tests for sync_inventory_from_api.

The Polymarket data-api shifted between two response shapes for positions:

  - older / one endpoint: ``asset`` is a {"id": "..."} dict, ``market`` is a
    {"question": ..., "conditionId": ...} dict
  - current: ``asset`` is the raw token-id string, ``market`` is the raw
    question string with ``conditionId`` at the top level

The bot crashed on 2026-05-10 because it only handled the first shape.
These tests pin both shapes so a future regression can't silently
re-break inventory sync.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _fake_httpx_client(payload: Any):
    """Build an AsyncClient context manager that returns ``payload`` as JSON."""
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status = MagicMock()

    client = MagicMock()
    client.get = AsyncMock(return_value=response)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def _reset_inventory_state():
    from src.copy_trading import inventory
    inventory._positions = {}


@pytest.fixture(autouse=True)
def _isolate_inventory(tmp_path, monkeypatch):
    # Point the inventory persistence file at a tmp dir so the test
    # doesn't write into ``data/`` or leak state between cases.
    from src.copy_trading import inventory
    monkeypatch.setattr(inventory, "_INVENTORY_FILE", str(tmp_path / "inv.json"))
    _reset_inventory_state()
    yield
    _reset_inventory_state()


def test_dict_shape_asset_and_market():
    """Older shape: ``asset``/``market`` as dicts."""
    payload = [
        {
            "asset": {"id": "tok-1"},
            "market": {"question": "Will X happen?", "conditionId": "cond-1"},
            "size": 12.5,
            "avgPrice": 0.42,
        }
    ]
    from src.copy_trading import inventory

    with patch("src.copy_trading.inventory.httpx.AsyncClient", return_value=_fake_httpx_client(payload)):
        synced = _run(inventory.sync_inventory_from_api("0xproxy"))

    assert synced == 1
    pos = inventory._positions["tok-1"]
    assert pos["shares"] == 12.5
    assert pos["avg_price"] == 0.42
    assert pos["market"] == "Will X happen?"
    assert pos["market_key"] == "cond-1"


def test_string_shape_asset_and_market():
    """Current shape: ``asset`` is token-id string, ``market`` is the question string."""
    payload = [
        {
            "asset": "tok-2",
            "market": "Will Y happen?",
            "conditionId": "cond-2",
            "size": 100.0,
            "avgPrice": 0.10,
        }
    ]
    from src.copy_trading import inventory

    with patch("src.copy_trading.inventory.httpx.AsyncClient", return_value=_fake_httpx_client(payload)):
        synced = _run(inventory.sync_inventory_from_api("0xproxy"))

    assert synced == 1
    pos = inventory._positions["tok-2"]
    assert pos["shares"] == 100.0
    assert pos["market"] == "Will Y happen?"
    assert pos["market_key"] == "cond-2"


def test_mixed_shapes_in_one_response():
    """Be defensive: a single response may mix shapes during a rollout."""
    payload = [
        {"asset": "tok-3", "market": "Q3", "conditionId": "cond-3", "size": 5, "avgPrice": 0.5},
        {"asset": {"id": "tok-4"}, "market": {"question": "Q4", "conditionId": "cond-4"}, "size": 7, "avgPrice": 0.3},
    ]
    from src.copy_trading import inventory

    with patch("src.copy_trading.inventory.httpx.AsyncClient", return_value=_fake_httpx_client(payload)):
        synced = _run(inventory.sync_inventory_from_api("0xproxy"))

    assert synced == 2
    assert inventory._positions["tok-3"]["market_key"] == "cond-3"
    assert inventory._positions["tok-4"]["market_key"] == "cond-4"


def test_zero_shares_filtered():
    payload = [{"asset": "tok-5", "market": "Q5", "conditionId": "c", "size": 0, "avgPrice": 0.5}]
    from src.copy_trading import inventory

    with patch("src.copy_trading.inventory.httpx.AsyncClient", return_value=_fake_httpx_client(payload)):
        synced = _run(inventory.sync_inventory_from_api("0xproxy"))

    assert synced == 0
    assert "tok-5" not in inventory._positions


def test_empty_proxy_skips():
    from src.copy_trading import inventory
    assert _run(inventory.sync_inventory_from_api("")) == 0
