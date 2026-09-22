"""One trade id for every detection source.

The data api and the chain see the same fill: the api hands back a
``transactionHash`` string with its ``0x``; web3 8 / hexbytes 2 hand back a
``HexBytes`` whose ``.hex()`` has no prefix. Both sources built the id as
``f"{tx}-{token}-{side}"`` from their own spelling, so the same fill had two
ids and ``is_seen_trade`` could not join them: in hybrid mode the second
source would have copied a fill the first had already copied. A leaf module
(no project imports) so both sources, the store and the tests read one rule.
"""
from __future__ import annotations


def normalize_tx_hash(tx_hash) -> str:
    """Lowercase, ``0x``-prefixed. Accepts str, bytes, or anything with
    ``.hex()``; an empty or None value stays empty (a row without a hash
    keeps whatever fallback the source chose)."""
    if tx_hash is None:
        return ""
    if isinstance(tx_hash, (bytes, bytearray)):
        h = tx_hash.hex()
    elif hasattr(tx_hash, "hex") and not isinstance(tx_hash, str):
        h = tx_hash.hex()
    else:
        h = str(tx_hash)
    h = h.strip().lower()
    if not h:
        return ""
    if not h.startswith("0x"):
        h = "0x" + h
    return h


def canonical_trade_id(tx_hash, token_id, side: str) -> str:
    """``<0x-tx>-<token>-<SIDE>``, the same string from either source."""
    return f"{normalize_tx_hash(tx_hash)}-{str(token_id)}-{str(side).upper()}"
