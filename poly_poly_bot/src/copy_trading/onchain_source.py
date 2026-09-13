"""On-chain trade source — polls OrderFilled events via web3.py."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from web3 import Web3
from web3.contract import Contract

from src.config import CONFIG
from src.constants import (
    CTF_EXCHANGE,
    NEG_RISK_CTF_EXCHANGE,
    ORDER_FILLED_ABI,
    USDC_ADDRESS,
)
from src.logger import logger
from src.models import DetectedTrade
from src.utils import error_message, short_address

MAX_BLOCK_RANGE = 9
MAX_BLOCKS_BEHIND = 10000
USDC_DECIMALS = 6
POLL_INTERVAL_S = 2.0

_CURSOR_PATH = Path(CONFIG.data_dir) / "onchain-cursor.json"


# ---------------------------------------------------------------------------
# Cursor persistence
# ---------------------------------------------------------------------------

def _load_cursor() -> int:
    """Load last-processed block from disk, or 0 if absent."""
    try:
        if _CURSOR_PATH.exists():
            data = json.loads(_CURSOR_PATH.read_text())
            return int(data.get("lastBlock", 0))
    except Exception:
        pass
    return 0


def _save_cursor(block: int) -> None:
    """Persist the last-processed block number."""
    try:
        _CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CURSOR_PATH.write_text(json.dumps({"lastBlock": block}))
    except Exception as exc:
        logger.warn(f"Failed to save onchain cursor: {error_message(exc)}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _canonical_trade_id(tx_hash: str, token_id: str, side: str) -> str:
    return f"{tx_hash}-{token_id}-{side}"


def _determine_side(maker_asset_id: int, taker_asset_id: int) -> str:
    """Determine BUY/SELL from maker/taker asset IDs — from the MAKER's side.

    makerAssetId == 0 means the MAKER is paying USDC, i.e. the maker is buying
    outcome tokens and the taker is selling them. Kept for compatibility;
    `_process_events` does NOT use this for the stamped side, because the
    tracked wallet can be the taker (see _tracked_side).
    """
    if maker_asset_id == 0:
        return "BUY"
    return "SELL"


def _tracked_side(maker_asset_id: int, tracked_is_maker: bool) -> str:
    """BUY/SELL from the TRACKED WALLET's side.

    makerAssetId == 0 → the maker buys outcome tokens, the taker sells.
    The old code stamped the maker's side on the trade regardless of which
    role the tracked wallet played, so a tracked TAKER hitting a resting bid
    (the common case for a whale taking the book) was mirrored as a BUY of
    the thing it had just SOLD.
    """
    maker_buys = maker_asset_id == 0
    return "BUY" if maker_buys == tracked_is_maker else "SELL"


def _trade_legs(maker_asset_id: int, taker_asset_id: int,
                maker_amount: int, taker_amount: int) -> tuple[str, int, int]:
    """Split a fill into (token_id, usdc_amount, outcome_amount) from the
    asset IDs — never from a side convention. USDC is asset id 0; the token
    is the other leg, on whichever side holds it."""
    if maker_asset_id == 0:
        return str(taker_asset_id), maker_amount, taker_amount
    return str(maker_asset_id), taker_amount, maker_amount


def _usdc_to_float(amount: int) -> float:
    """Convert raw USDC amount (6 decimals) to float."""
    return amount / (10 ** USDC_DECIMALS)


class OnchainSource:
    """Polls OrderFilled events from Polymarket exchange contracts."""

    name = "onchain"

    def __init__(self) -> None:
        self._running = False
        self._w3: Optional[Web3] = None
        self._ctf_contract: Optional[Contract] = None
        self._neg_risk_contract: Optional[Contract] = None
        self._block_ts_cache: dict[int, int] = {}
        self._tracked_addresses: set[str] = set()

    def _init_web3(self) -> None:
        """Initialize web3 provider and contract objects."""
        self._w3 = Web3(Web3.HTTPProvider(CONFIG.rpc_url))
        self._ctf_contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(CTF_EXCHANGE),
            abi=ORDER_FILLED_ABI,
        )
        self._neg_risk_contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(NEG_RISK_CTF_EXCHANGE),
            abi=ORDER_FILLED_ABI,
        )
        # Build tracked address set (lowercase)
        for addr in CONFIG.user_addresses:
            self._tracked_addresses.add(addr.lower())

    def _get_block_timestamp(self, block_number: int) -> int:
        """Fetch block timestamp with caching."""
        if block_number in self._block_ts_cache:
            return self._block_ts_cache[block_number]
        assert self._w3 is not None
        try:
            block = self._w3.eth.get_block(block_number)
            ts = int(block["timestamp"])
            self._block_ts_cache[block_number] = ts
            # Prune cache if too large
            if len(self._block_ts_cache) > 500:
                oldest = sorted(self._block_ts_cache.keys())[:250]
                for k in oldest:
                    del self._block_ts_cache[k]
            return ts
        except Exception:
            return int(time.time())

    def _process_events(
        self,
        events: list,
        contract_name: str,
    ) -> list[DetectedTrade]:
        """Process OrderFilled events and return matching DetectedTrade objects.

        The stamped side is the TRACKED WALLET's side (see _tracked_side).

        A matchOrders tx emits one OrderFilled per MAKER order (its ``taker``
        field is the taker order's signer) and one for the taker order itself
        (``maker`` = that signer, ``taker`` = the exchange). A tracked wallet
        taking the book therefore appears twice in one tx: as ``taker`` on
        every maker leg and as ``maker`` on its own leg. The own leg is the
        wallet's actual order: its side, its token, the whole fill. The maker
        legs are partial and, for a MINT/MERGE match, on the complementary
        token. When the own leg is in the batch the maker legs are dropped;
        when it is not (defensive; Trading.sol always emits it) the maker legs
        of one order are summed into one trade.
        """
        own_legs: set[tuple[str, str]] = set()
        for event in events:
            m = event["args"]["maker"].lower()
            if m in self._tracked_addresses:
                own_legs.add((event["transactionHash"].hex(), m))

        by_id: dict[str, dict] = {}
        for event in events:
            args = event["args"]
            maker = args["maker"].lower()
            taker = args["taker"].lower()
            tx_hash = event["transactionHash"].hex()

            # Check if either maker or taker is a tracked address
            trader_address: Optional[str] = None
            tracked_is_maker = False
            if maker in self._tracked_addresses:
                trader_address = maker
                tracked_is_maker = True
            elif taker in self._tracked_addresses:
                trader_address = taker
                if (tx_hash, taker) in own_legs:
                    # A maker leg of the wallet's own taker order; the own
                    # leg in this tx carries the trade.
                    continue
            else:
                continue

            maker_asset_id = int(args["makerAssetId"])
            taker_asset_id = int(args["takerAssetId"])
            maker_amount = int(args["makerAmountFilled"])
            taker_amount = int(args["takerAmountFilled"])

            side = _tracked_side(maker_asset_id, tracked_is_maker)

            # Token id, USDC size, and outcome size from the asset IDs, so the
            # amounts stay right whichever role the tracked wallet played.
            token_id, usdc_amount, outcome_amount = _trade_legs(
                maker_asset_id, taker_asset_id, maker_amount, taker_amount)
            if usdc_amount <= 0:
                continue

            trade_id = _canonical_trade_id(tx_hash, token_id, side)
            agg = by_id.get(trade_id)
            if agg is not None:
                # Several maker legs of one tracked taker order, no own leg
                # seen: one order, summed.
                agg["usdc"] += usdc_amount
                agg["outcome"] += outcome_amount
                continue
            by_id[trade_id] = {
                "trader_address": trader_address,
                "token_id": token_id,
                "side": side,
                "usdc": usdc_amount,
                "outcome": outcome_amount,
                "block_number": event["blockNumber"],
            }

        trades: list[DetectedTrade] = []
        for trade_id, agg in by_id.items():
            size = _usdc_to_float(agg["usdc"])
            # Price: USDC / outcome tokens
            price = size / (_usdc_to_float(agg["outcome"]) or 1.0)
            block_ts = self._get_block_timestamp(agg["block_number"])

            from datetime import datetime, timezone
            timestamp = datetime.fromtimestamp(block_ts, tz=timezone.utc).isoformat()

            # Enrich with market metadata
            market = ""
            condition_id = ""
            outcome = ""
            try:
                from src.copy_trading.market_cache import get_market_meta
                meta = get_market_meta(agg["token_id"])
                if meta is not None:
                    market = meta.market
                    condition_id = meta.condition_id
                    outcome = meta.outcome
            except Exception:
                pass

            trades.append(DetectedTrade(
                id=trade_id,
                trader_address=agg["trader_address"],
                timestamp=timestamp,
                market=market,
                condition_id=condition_id,
                token_id=agg["token_id"],
                side=agg["side"],  # type: ignore[arg-type]
                size=size,
                price=round(price, 4),
                outcome=outcome,
            ))

        return trades

    def _fetch_events_range(
        self,
        from_block: int,
        to_block: int,
    ) -> list[DetectedTrade]:
        """Fetch OrderFilled events for a block range from both exchanges."""
        assert self._ctf_contract is not None
        assert self._neg_risk_contract is not None

        all_trades: list[DetectedTrade] = []

        for contract, name in [
            (self._ctf_contract, "CTF"),
            (self._neg_risk_contract, "NEG_RISK_CTF"),
        ]:
            try:
                event_filter = contract.events.OrderFilled.create_filter(
                    fromBlock=from_block,
                    toBlock=to_block,
                )
                events = event_filter.get_all_entries()
                trades = self._process_events(events, name)
                all_trades.extend(trades)
            except Exception as exc:
                logger.error(f"Error fetching {name} events [{from_block}-{to_block}]: {error_message(exc)}")

        return all_trades

    async def start(self) -> None:
        """Start polling for on-chain OrderFilled events."""
        self._running = True
        self._init_web3()
        assert self._w3 is not None

        cursor = _load_cursor()
        if cursor == 0:
            cursor = self._w3.eth.block_number
            logger.info(f"Onchain source: no cursor, starting at block {cursor}")

        logger.info(f"Onchain source started, cursor at block {cursor}")

        while self._running:
            try:
                latest = self._w3.eth.block_number
                # A successful chain read is this poller's heartbeat for the
                # guard's stale-feed trigger (the data-api source stamps its own).
                from src.copy_trading.trade_store import record_poll_ok
                record_poll_ok()

                # Skip if cursor is too far behind
                if latest - cursor > MAX_BLOCKS_BEHIND:
                    logger.warn(
                        f"Onchain cursor {cursor} is {latest - cursor} blocks behind, "
                        f"skipping ahead to {latest - 100}"
                    )
                    cursor = latest - 100
                    _save_cursor(cursor)

                if cursor >= latest:
                    await asyncio.sleep(POLL_INTERVAL_S)
                    continue

                # Process in chunks of MAX_BLOCK_RANGE
                from_block = cursor + 1
                to_block = min(from_block + MAX_BLOCK_RANGE - 1, latest)

                trades = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._fetch_events_range,
                    from_block,
                    to_block,
                )

                if trades:
                    logger.info(f"Onchain: {len(trades)} trades in blocks {from_block}-{to_block}")
                    for trade in trades:
                        try:
                            from src.copy_trading.trade_store import is_seen_trade, is_max_retries
                            from src.copy_trading.trade_queue import enqueue_trade
                            from src.models import QueuedTrade
                            if not is_seen_trade(trade.id) and not is_max_retries(trade.id):
                                from datetime import datetime
                                from src.copy_trading.trade_store import (
                                    record_reaction_latency)
                                ts_ms = datetime.fromisoformat(
                                    trade.timestamp.replace("Z", "+00:00")
                                ).timestamp() * 1000
                                # ts_ms = the target's trade time; now = when
                                # we saw it. Same latency contract as the
                                # data-api source (see QueuedTrade).
                                received_ms = time.time() * 1000
                                record_reaction_latency(received_ms - ts_ms)
                                enqueue_trade(QueuedTrade(
                                    trade=trade,
                                    enqueued_at=ts_ms,
                                    source_detected_at=ts_ms,
                                    received_at_ms=received_ms,
                                    source="onchain",
                                ))
                        except Exception as exc:
                            logger.error(f"Error enqueueing onchain trade: {error_message(exc)}")

                cursor = to_block
                _save_cursor(cursor)

            except Exception as exc:
                logger.error(f"Onchain poll error: {error_message(exc)}")
                await asyncio.sleep(5.0)

            await asyncio.sleep(POLL_INTERVAL_S)

    def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        logger.info("Onchain source stopped")
