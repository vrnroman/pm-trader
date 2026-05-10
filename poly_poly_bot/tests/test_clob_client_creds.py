"""Contract test for CLOB client API-creds normalization.

py-clob-client's ``create_or_derive_api_creds()`` returns an ``ApiCreds``
dataclass in current versions and (historically) a dict. The bot's
``create_clob_client()`` must handle both shapes — the dict-only path
crashed the bot on 2026-05-10 once a real ``PRIVATE_KEY`` exposed the
code path.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

py_clob_client = pytest.importorskip("py_clob_client")
from py_clob_client.clob_types import ApiCreds  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_singleton():
    from src.copy_trading import clob_client
    clob_client._client = None
    yield
    clob_client._client = None


def _patched_clob_constructor(creds_returned):
    """Build a mock ClobClient class whose L1 instance returns ``creds_returned``
    from create_or_derive_api_creds(), and whose L2 instance is the final client."""
    final_client = MagicMock(name="L2ClobClient")
    l1_client = MagicMock(name="L1ClobClient")
    l1_client.create_or_derive_api_creds.return_value = creds_returned

    # Two construction calls — first returns L1, second returns L2.
    return MagicMock(side_effect=[l1_client, final_client]), final_client


def test_api_creds_dataclass_passthrough():
    """Current py-clob-client returns an ApiCreds dataclass; pass through directly."""
    creds = ApiCreds(api_key="k", api_secret="s", api_passphrase="p")
    ctor, final = _patched_clob_constructor(creds)

    with patch("src.copy_trading.clob_client.ClobClient", ctor), \
         patch("src.copy_trading.clob_client.get_private_key", return_value="ab" * 32):
        from src.copy_trading.clob_client import create_clob_client
        client = create_clob_client()

    assert client is final
    # Two constructions: L1 (key only) + L2 (key + creds).
    assert ctor.call_count == 2
    second_kwargs = ctor.call_args_list[1].kwargs
    assert isinstance(second_kwargs["creds"], ApiCreds)
    assert second_kwargs["creds"].api_key == "k"
    assert second_kwargs["creds"].api_secret == "s"


def test_api_creds_dict_shape_normalized():
    """Older py-clob-client returned a dict; normalize into ApiCreds."""
    creds_dict = {"apiKey": "k2", "secret": "s2", "passphrase": "p2"}
    ctor, final = _patched_clob_constructor(creds_dict)

    with patch("src.copy_trading.clob_client.ClobClient", ctor), \
         patch("src.copy_trading.clob_client.get_private_key", return_value="cd" * 32):
        from src.copy_trading.clob_client import create_clob_client
        client = create_clob_client()

    assert client is final
    second_kwargs = ctor.call_args_list[1].kwargs
    assert isinstance(second_kwargs["creds"], ApiCreds)
    assert second_kwargs["creds"].api_key == "k2"
    assert second_kwargs["creds"].api_secret == "s2"
    assert second_kwargs["creds"].api_passphrase == "p2"


def test_no_private_key_returns_none():
    with patch("src.copy_trading.clob_client.get_private_key", return_value=""):
        from src.copy_trading.clob_client import create_clob_client
        assert create_clob_client() is None


def test_reset_clob_client_drops_singleton():
    from src.copy_trading import clob_client
    clob_client._client = MagicMock()
    clob_client.reset_clob_client()
    assert clob_client._client is None
