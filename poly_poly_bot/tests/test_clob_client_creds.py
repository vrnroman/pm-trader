"""Contract test for CLOB client API-creds wiring.

Verifies that ``create_clob_client`` correctly walks the V2 SDK's two-step
flow: build an L1 client from the EOA private key, derive ApiCreds via
``create_or_derive_api_key()``, then build the final L2 client with both
the key and the derived creds.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

py_clob_client_v2 = pytest.importorskip("py_clob_client_v2")
from py_clob_client_v2 import ApiCreds  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_singleton():
    from src.copy_trading import clob_client
    clob_client._client = None
    yield
    clob_client._client = None


def _patched_clob_constructor(creds_returned):
    """Build a mock ClobClient class whose L1 instance returns ``creds_returned``
    from create_or_derive_api_key(), and whose L2 instance is the final client."""
    final_client = MagicMock(name="L2ClobClient")
    l1_client = MagicMock(name="L1ClobClient")
    l1_client.create_or_derive_api_key.return_value = creds_returned

    # Two construction calls — first returns L1, second returns L2.
    return MagicMock(side_effect=[l1_client, final_client]), final_client


def test_api_creds_passed_into_l2_client():
    """V2 returns an ApiCreds dataclass; the final client must be built with it."""
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
    assert second_kwargs["creds"].api_passphrase == "p"


def test_no_private_key_returns_none():
    with patch("src.copy_trading.clob_client.get_private_key", return_value=""):
        from src.copy_trading.clob_client import create_clob_client
        assert create_clob_client() is None


def test_reset_clob_client_drops_singleton():
    from src.copy_trading import clob_client
    clob_client._client = MagicMock()
    clob_client.reset_clob_client()
    assert clob_client._client is None
