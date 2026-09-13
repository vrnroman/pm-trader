"""wallet_history must never read a failed lookup as an empty history.

A Data API failure used to return `WalletHistory(now, [], False)` — cached for
ten minutes — which is indistinguishable from "this wallet has zero prior
trades". The first-ever-bet guard fired for seasoned wallets (its explicit
"only on positive evidence" check passes on count 0), and the novelty gate
ungated the cluster/thin-market weak patterns, through an entire API hiccup.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.copy_trading import wallet_history as wh


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _clean_cache():
    wh._reset_wallet_history_cache()
    yield
    wh._reset_wallet_history_cache()


def _fake_client(*, status=200, payload=()):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = list(payload)

    client = MagicMock()
    client.get = AsyncMock(return_value=response)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def test_a_failed_lookup_is_none_count_and_is_never_cached():
    with patch.object(wh.httpx, "AsyncClient", return_value=_fake_client(status=429)) as ctor:
        prior, count, truncated = _run(wh.get_prior_trade_ts("0xWALLET"))
    assert prior is None
    assert count is None, "None is the fail-closed signal; 0 would read as 'no priors'"
    assert truncated is False

    # Not cached: the next lookup fetches again (and can succeed).
    good = [{"timestamp": 1_700_000_000, "transactionHash": "0xabc"}]
    with patch.object(wh.httpx, "AsyncClient", return_value=_fake_client(payload=good)):
        prior, count, truncated = _run(wh.get_prior_trade_ts("0xWALLET"))
    assert count == 1 and prior == 1_700_000_000


def test_a_successful_empty_history_is_zero_not_none_and_is_cached():
    with patch.object(wh.httpx, "AsyncClient", return_value=_fake_client(payload=[])) as ctor:
        prior, count, _ = _run(wh.get_prior_trade_ts("0xNEW"))
        # second call must hit the cache, not the API
        prior2, count2, _ = _run(wh.get_prior_trade_ts("0xNEW"))
    assert (prior, count) == (None, 0)
    assert (prior2, count2) == (None, 0)
    assert ctor.call_count == 1


def test_a_transport_error_is_a_failed_lookup():
    cm = MagicMock()
    client = MagicMock()
    client.get = AsyncMock(side_effect=TimeoutError("boom"))
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=None)
    with patch.object(wh.httpx, "AsyncClient", return_value=cm):
        prior, count, _ = _run(wh.get_prior_trade_ts("0xWALLET"))
    assert prior is None and count is None


def test_the_novelty_gate_fails_closed_on_a_failed_lookup():
    """prior_trade_ts=None with a SUCCESSFUL empty lookup is first-ever;
    with a FAILED lookup (count None) it must not ungate the weak patterns."""
    from src.copy_trading.pattern_detector import _is_novel_wallet

    assert _is_novel_wallet(age_days=None, prior_trade_ts=None,
                            polymarket_count_truncated=False,
                            polymarket_trade_count=None) is False
    assert _is_novel_wallet(age_days=None, prior_trade_ts=None,
                            polymarket_count_truncated=False,
                            polymarket_trade_count=0) is True
