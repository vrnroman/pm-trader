"""Singleton CLOB client factory.

Uses ``py-clob-client-v2`` because Polymarket's CLOB V2 migration on
2026-04-28 bumped the EIP-712 exchange domain version from "1" to "2";
every order signed by the V1 SDK is now rejected with
``order_version_mismatch`` and the V1 package is no longer maintained
against production.
"""

from __future__ import annotations
from typing import Optional
from py_clob_client_v2 import ClobClient, ApiCreds
from src.config import CONFIG, get_private_key
from src.logger import logger

_client: Optional[ClobClient] = None


def reset_clob_client() -> None:
    """Drop the singleton so the next ``create_clob_client()`` rebuilds it.

    Used by /setkey when the in-memory private key changes; the cached
    client was authenticated with the old key and must be discarded.
    """
    global _client
    _client = None


def create_clob_client() -> ClobClient | None:
    """Create and cache a singleton authenticated CLOB client.

    Returns None if private key is not configured (preview mode without wallet).
    """
    global _client
    if _client is not None:
        return _client

    private_key = get_private_key()
    if not private_key:
        logger.info("No private key configured — CLOB client disabled (preview/monitor only)")
        return None

    logger.info("Deriving API credentials from wallet...")

    # Initial client for key derivation
    l1_client = ClobClient(
        CONFIG.clob_api_url,
        chain_id=CONFIG.chain_id,
        key=f"0x{private_key}",
        signature_type=CONFIG.signature_type,
        funder=CONFIG.proxy_wallet,
    )

    creds = l1_client.create_or_derive_api_key()

    _client = ClobClient(
        CONFIG.clob_api_url,
        chain_id=CONFIG.chain_id,
        key=f"0x{private_key}",
        creds=creds,
        signature_type=CONFIG.signature_type,
        funder=CONFIG.proxy_wallet,
    )

    logger.info("CLOB client authenticated successfully")
    return _client
