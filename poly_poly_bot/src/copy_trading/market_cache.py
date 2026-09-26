"""Market metadata cache — in-memory with JSON persistence and a Gamma lookup.

Resolves a CLOB ``token_id`` to the market it belongs to (title, condition id,
and which outcome the token is), so an on-chain ``OrderFilled`` event can be
shown and keyed like a data-api trade.

History (2026-09-26): the lookup used to call the CLOB ``/markets?asset_id=``
endpoint. That endpoint ignores the filter and returns the first page of ALL
markets as a ``{"data": [...], "next_cursor": ...}`` envelope. The code read the
envelope as a market, found no ``question`` in it, and cached an empty record —
for every token, forever. Once the on-chain feed went live every copy it placed
read ``BUY $6.40 on ""`` on the phone, and every on-chain trade shared one
empty ``market_key`` in the max-copies guard. Rules now:

* the lookup is Gamma ``/markets?clob_token_ids=<id>`` (open first, then
  ``closed=true`` — Gamma hides closed markets by default), parsed by ONE
  function that also picks the outcome name by the token's index;
* an answer with no title is never cached to disk, and a short in-memory
  negative cache keeps the on-chain poller (which enriches every event in the
  block range, every poll) from hammering Gamma for a token it cannot name;
* a persisted entry with no title is a poisoned one from the old lookup and is
  dropped on load, so a deploy heals the cache without a manual step.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from src.config import CONFIG
from src.logger import logger
from src.models import MarketMeta
from src.utils import error_message

_CACHE_PATH = Path(CONFIG.data_dir) / "market-cache.json"
GAMMA_API_URL = "https://gamma-api.polymarket.com"

# How long a token that Gamma could not name stays "known unresolvable" in
# memory before we ask again. Long enough to absorb the poller re-reading the
# same block range, short enough that a market Gamma indexes late is picked up.
NEGATIVE_TTL_S = 600.0

# In-memory cache: token_id -> MarketMeta
_cache: dict[str, MarketMeta] = {}
_negative: dict[str, float] = {}  # token_id -> monotonic time of the miss
_loaded = False


def _ensure_loaded() -> None:
    """Load cache from disk on first access, dropping poisoned (untitled) rows."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        if _CACHE_PATH.exists():
            data = json.loads(_CACHE_PATH.read_text())
            dropped = 0
            for token_id, entry in data.items():
                meta = MarketMeta(**entry)
                if not meta.market:
                    dropped += 1
                    continue
                _cache[token_id] = meta
            logger.info(f"Market cache loaded: {len(_cache)} entries"
                        + (f" ({dropped} untitled rows dropped, will re-resolve)" if dropped else ""))
            if dropped:
                _save_cache()
    except Exception as exc:
        logger.warn(f"Failed to load market cache: {error_message(exc)}")


def _save_cache() -> None:
    """Persist in-memory cache to disk."""
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {tid: meta.model_dump() for tid, meta in _cache.items()}
        _CACHE_PATH.write_text(json.dumps(data, indent=2))
    except Exception as exc:
        logger.warn(f"Failed to save market cache: {error_message(exc)}")


def _rows(payload: Any) -> list[dict]:
    """The market rows in a Gamma answer: a bare list, or a ``data`` envelope."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        inner = payload.get("data")
        if isinstance(inner, list):
            return [r for r in inner if isinstance(r, dict)]
    return []


def _json_list(raw: Any) -> list[str]:
    """Gamma ships ``outcomes`` / ``clobTokenIds`` as JSON strings; accept lists too."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw]


def _row_tokens(row: dict) -> list[str]:
    """Every token id a market row names: Gamma's ``clobTokenIds`` list, or the
    CLOB shape's ``tokens: [{token_id, outcome}]``."""
    tokens = _json_list(row.get("clobTokenIds") or row.get("clob_token_ids"))
    for tok in row.get("tokens") or []:
        if isinstance(tok, dict):
            tid = tok.get("token_id") or tok.get("tokenId")
            if tid:
                tokens.append(str(tid))
    return tokens


def meta_from_rows(rows: list[dict], token_id: str) -> Optional[MarketMeta]:
    """Pick the market row that carries ``token_id`` and name its outcome.

    Returns None when no row names a market (an empty answer, or the CLOB-style
    envelope the old lookup mistook for a market). The outcome is the name at
    the token's index in ``clobTokenIds``; a row that does not list the token
    at all still yields the title with an empty outcome, never a guessed one.
    """
    chosen: Optional[dict] = None
    saw_token_lists = False
    for row in rows:
        tokens = _row_tokens(row)
        saw_token_lists = saw_token_lists or bool(tokens)
        if token_id in tokens:
            chosen = row
            break
    if chosen is None and rows and not saw_token_lists:
        # An answer that names no tokens at all (an older shape): trust the
        # single row the filter returned. An answer that names tokens but not
        # ours is somebody else's market — the old CLOB envelope — never ours.
        chosen = rows[0]
    if chosen is None:
        return None
    market = chosen.get("question") or chosen.get("title") or chosen.get("market") or ""
    if not str(market).strip():
        return None
    condition_id = chosen.get("conditionId") or chosen.get("condition_id") or ""
    tokens = _json_list(chosen.get("clobTokenIds") or chosen.get("clob_token_ids"))
    outcomes = _json_list(chosen.get("outcomes"))
    outcome = ""
    if token_id in tokens:
        idx = tokens.index(token_id)
        if idx < len(outcomes):
            outcome = outcomes[idx]
    return MarketMeta(
        condition_id=str(condition_id),
        market=str(market),
        outcome=str(outcome),
        token_id=token_id,
    )


def _query_variants(token_id: str) -> list[dict]:
    # Open markets first (the common case for a trade we just saw), then the
    # closed variant: Gamma returns nothing for a closed market without it.
    return [{"clob_token_ids": token_id},
            {"clob_token_ids": token_id, "closed": "true"}]


def _fetch_from_api_sync(token_id: str) -> Optional[MarketMeta]:
    """Synchronous Gamma lookup for a single token_id."""
    url = f"{GAMMA_API_URL}/markets"
    try:
        with httpx.Client(timeout=5.0) as client:
            for params in _query_variants(token_id):
                resp = client.get(url, params=params)
                if resp.status_code != 200:
                    continue
                meta = meta_from_rows(_rows(resp.json()), token_id)
                if meta is not None:
                    return meta
    except Exception as exc:
        logger.debug(f"Market cache API miss for {token_id}: {error_message(exc)}")
    return None


def _negative_fresh(token_id: str) -> bool:
    at = _negative.get(token_id)
    return at is not None and (time.monotonic() - at) < NEGATIVE_TTL_S


def _remember(token_id: str, meta: Optional[MarketMeta]) -> None:
    if meta is None:
        _negative[token_id] = time.monotonic()
        return
    _negative.pop(token_id, None)
    _cache[token_id] = meta


def get_market_meta(token_id: str) -> Optional[MarketMeta]:
    """Get market metadata for a token_id, fetching from Gamma on cache miss.

    Returns None if the token cannot be resolved. A None is remembered in
    memory for ``NEGATIVE_TTL_S`` and never written to disk.
    """
    _ensure_loaded()

    if token_id in _cache:
        return _cache[token_id]
    if _negative_fresh(token_id):
        return None

    meta = _fetch_from_api_sync(token_id)
    _remember(token_id, meta)
    if meta is not None:
        _save_cache()
    return meta


async def warm_cache(token_ids: list[str]) -> None:
    """Pre-populate cache for a batch of token IDs.

    Fetches missing entries concurrently via Gamma.
    """
    _ensure_loaded()

    missing = [tid for tid in dict.fromkeys(token_ids)
               if tid not in _cache and not _negative_fresh(tid)]
    if not missing:
        return

    logger.info(f"Warming market cache for {len(missing)} tokens...")

    async def _fetch_one(token_id: str) -> Optional[MarketMeta]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                for params in _query_variants(token_id):
                    resp = await client.get(f"{GAMMA_API_URL}/markets", params=params)
                    if resp.status_code != 200:
                        continue
                    meta = meta_from_rows(_rows(resp.json()), token_id)
                    if meta is not None:
                        return meta
        except Exception:
            pass
        return None

    sem = asyncio.Semaphore(5)

    async def _bounded(tid: str) -> tuple[str, Optional[MarketMeta]]:
        async with sem:
            meta = await _fetch_one(tid)
            return tid, meta

    results = await asyncio.gather(*[_bounded(tid) for tid in missing])
    added = 0
    for tid, meta in results:
        _remember(tid, meta)
        if meta is not None:
            added += 1

    if added > 0:
        _save_cache()
        logger.info(f"Market cache warmed: {added} new entries")
