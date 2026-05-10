"""Smoke test: every module that runs in production must import.

This is the cheapest test we have. The deployment failures we hit on
2026-05-10 were all module-level NameErrors / ImportErrors that lived in
cold paths (``recover_pending_orders``, lazy ``_trade_store()`` imports,
etc.) and only surfaced when ``PRIVATE_KEY`` was finally populated.

Running these imports from a test means we catch the same class of bug
before deploy. The lazy-import helpers (``_trade_store``, ``_trade_queue``,
``_inventory``, etc.) are also exercised so the inner ``from ... import
foo`` lines actually resolve.

Skipped automatically when ``py_clob_client`` isn't installed (e.g. in a
local venv that doesn't ship the trading deps); still runs in the Docker
build where the prod deps are present.
"""

from __future__ import annotations

import importlib

import pytest

py_clob_client = pytest.importorskip("py_clob_client")  # noqa: F401


def test_main_imports():
    """Top-level entry module must import without side effects failing."""
    importlib.import_module("main")


@pytest.mark.parametrize(
    "module",
    [
        "src.runtime_state",
        "src.tennis.tennis_arb",
        "src.tennis.paper_book",
        "src.tennis.order_placer",
        "src.copy_trading.runner",
        "src.copy_trading.trade_executor",
        "src.copy_trading.trade_queue",
        "src.copy_trading.trade_store",
        "src.copy_trading.inventory",
        "src.copy_trading.clob_client",
        "src.copy_trading.order_executor",
        "src.copy_trading.risk_manager",
        "src.copy_trading.tiered_risk_manager",
        "src.telegram_bot",
        "src.config",
    ],
)
def test_module_imports(module):
    importlib.import_module(module)


def test_lazy_import_helpers_resolve():
    """trade_executor uses lazy ``from ... import x`` inside helpers.

    F821 doesn't catch a name that's later referenced outside the helper
    that imported it (this is exactly the bug class we hit). Calling each
    helper here forces its inner import block to execute, surfacing
    missing names at test time.
    """
    from src.copy_trading import trade_executor as te

    te._trade_store()
    te._trade_queue()
    te._inventory()
    te._risk_manager()
    te._tiered_risk()
    te._strategy_config()
