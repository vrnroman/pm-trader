"""Singleton CLOB client factory."""

from __future__ import annotations
from typing import Optional
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
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

    raw_creds = l1_client.create_or_derive_api_creds()
    # py-clob-client returns ApiCreds directly in current versions; older
    # versions returned a dict. Normalize to ApiCreds.
    if isinstance(raw_creds, ApiCreds):
        creds = raw_creds
    else:
        creds = ApiCreds(
            api_key=raw_creds.get("apiKey") or raw_creds.get("key", ""),
            api_secret=raw_creds["secret"],
            api_passphrase=raw_creds["passphrase"],
        )

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
