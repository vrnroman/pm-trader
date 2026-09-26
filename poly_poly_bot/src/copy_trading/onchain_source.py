"""On-chain trade source — polls OrderFilled events via web3.py."""

from __future__ import annotations

import asyncio
import json
import os
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

# Blocks per eth_getLogs. With the maker/taker topic filters below a chunk
# returns a handful of logs, so it can be wide (200 blocks read at 75 to 90
# blocks/s on the public RPC, 2026-09-22): 9 unfiltered blocks (about
# 1,000 OrderFilled logs on the v2 exchanges) took ~2 minutes a chunk on the
# box and the cursor fell 300 blocks behind in the first hour (2026-09-22).
MAX_BLOCK_RANGE = int(float(os.environ.get("ONCHAIN_BLOCK_RANGE", 200)))
MAX_BLOCKS_BEHIND = 10000
LAG_LOG_EVERY = 30
# Stay this many blocks behind the reported head. The public RPC is a pool of
# nodes: eth_getLogs up to the very block one node just reported fails on
# another with "invalid block range params" (1 of 3 tries at the head, 0 of 3
# one block back, measured 2026-09-22). One block is two seconds of latency.
HEAD_MARGIN_BLOCKS = 1
USDC_DECIMALS = 6
POLL_INTERVAL_S = 2.0
# A chunk the node refused is read again from the SAME cursor, this many
# times, before the reader gives those blocks up to the data-api fallback.
# One block back still races the pool about 2% of the time (229 refused
# chunks in 12,240 on 2026-09-26, every one at the head) and each refusal used
# to advance the cursor past the blocks it never read: a fill in them reached
# the bot only through the api, 18 s later, and the ERROR line woke the AI SRE,
# which read 184 of them as "the chain feed is fully down" and disarmed real
# money twice. A retry two seconds later lands on a node that has the block.
CHUNK_RETRIES = int(float(os.environ.get("ONCHAIN_CHUNK_RETRIES", 5)))
CHUNK_RETRY_DELAY_S = 2.0
# The health record is stale when the last good read is older than this.
HEALTH_STALE_S = 180.0

_CURSOR_PATH = Path(CONFIG.data_dir) / "onchain-cursor.json"


class ChunkReadError(Exception):
    """A block range the node would not read (either exchange). The chunk is
    whole or nothing: a range half read and then advanced past would lose
    the other exchange's fills for good."""

    def __init__(self, contract: str, from_block: int, to_block: int, exc: BaseException) -> None:
        self.contract = contract
        self.from_block = from_block
        self.to_block = to_block
        self.message = error_message(exc)
        super().__init__(f"{contract} [{from_block}-{to_block}]: {self.message}")

    @property
    def head_race(self) -> bool:
        """The pool's own inconsistency: one node reported the head, another
        has not got the block yet. Not an outage; a retry reads it."""
        return "invalid block range" in self.message.lower()


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
# Health record: what the reader is doing, for the AI SRE and the owner
# ---------------------------------------------------------------------------

def _health_path() -> Path:
    # Read at call time: the SRE sidecar and the tests point CONFIG elsewhere.
    return Path(CONFIG.data_dir) / "onchain-health.json"


def _save_health(d: dict) -> None:
    try:
        p = _health_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d))
    except Exception as exc:  # noqa: BLE001
        logger.warn(f"Failed to save onchain health: {error_message(exc)}")


def health(now: Optional[float] = None) -> Optional[dict]:
    """The last health record, or None before the first chunk."""
    try:
        return json.loads(_health_path().read_text())
    except Exception:  # noqa: BLE001
        return None


def health_line(now: Optional[float] = None) -> str:
    """One line the SRE prompt carries: a refused chunk at the head is a
    retry, an outage is a stale last good read or a growing lag. Without it
    the SRE saw only the ERROR lines (successful chunks log nothing it reads)
    and called 2% refusals a dead feed (2026-09-26)."""
    now = time.time() if now is None else now
    h = health(now)
    if not h:
        return "chain reader: no health record yet (not started, or an older build)"
    ok_age = now - float(h.get("ok_ts") or 0.0)
    state = "STALE" if ok_age > HEALTH_STALE_S else "reading"
    return (f"chain reader: {state}, last good read {ok_age:.0f}s ago, cursor {h.get('cursor')}, "
            f"head {h.get('head')}, lag {h.get('lag')} block(s); last hour: "
            f"{h.get('retries_1h', 0)} refused chunk(s) retried, {h.get('skipped_1h', 0)} chunk(s) skipped "
            f"to the data-api fallback; {h.get('tracked', 0)} tracked")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _canonical_trade_id(tx_hash, token_id: str, side: str) -> str:
    """One id with the data api: web3 8 / hexbytes 2 ``.hex()`` has no ``0x``,
    the api's ``transactionHash`` does; the leaf normaliser makes them one."""
    from src.copy_trading.trade_ids import canonical_trade_id
    return canonical_trade_id(tx_hash, token_id, side)


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


def _legs_from_args(args) -> tuple[int, int, int, int]:
    """(maker_asset_id, taker_asset_id, maker_amount, taker_amount) from either
    exchange's OrderFilled.

    The v2 exchanges (the only ones matching orders since 2026-09) emit
    ``side`` (the MAKER order's side: 0 BUY, 1 SELL) and one ``tokenId``
    instead of two asset ids. A maker BUY gives USDC (asset 0) and takes the
    token; a maker SELL gives the token and takes USDC. Mapping that onto the
    v1 asset-id pair keeps ``_tracked_side`` and ``_trade_legs`` one rule for
    both shapes, and a log from a v1 contract still decodes.
    """
    maker_amount = int(args["makerAmountFilled"])
    taker_amount = int(args["takerAmountFilled"])
    if "makerAssetId" in args and "takerAssetId" in args:
        return int(args["makerAssetId"]), int(args["takerAssetId"]), maker_amount, taker_amount
    side = int(args["side"])
    token = int(args["tokenId"])
    if side == 0:
        return 0, token, maker_amount, taker_amount
    return token, 0, maker_amount, taker_amount


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
        self._w3 = Web3(Web3.HTTPProvider(CONFIG.rpc_url, request_kwargs={"timeout": 30}))
        # Polygon is proof-of-authority: its block headers carry more
        # extraData than web3 accepts by default, and eth_getBlock raised
        # ExtraDataLengthError on every call. The old helper swallowed that
        # and stamped the WALL CLOCK as the block time, so the chain's lag
        # read as seconds while the fill was minutes old (verifier, run
        # s-qbzbrw). The middleware decodes the header; without it a fill
        # has no time and is not stamped (see _get_block_timestamp).
        try:
            from web3.middleware import ExtraDataToPOAMiddleware
            self._w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Onchain: POA middleware not injected ({error_message(exc)}); block times unavailable")
        self._ctf_contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(CTF_EXCHANGE),
            abi=ORDER_FILLED_ABI,
        )
        self._neg_risk_contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(NEG_RISK_CTF_EXCHANGE),
            abi=ORDER_FILLED_ABI,
        )
        self._refresh_tracked()

    def _refresh_tracked(self) -> None:
        """Set Z ONLY, read every poll so an admission or eviction takes effect
        on the next pass without a restart: the same population the data-api
        poll watches, so the two clocks compare the same fills (the static
        env list made the chain stamp 21 wallets the api never sees, and
        every one of them counted as "chain-only"). The executor's own set-Z
        check still decides money, whatever source produced the trade."""
        try:
            from src.copy_trading import zset
            tracked = {a.lower() for a in zset.wallets() if a}
        except Exception as exc:
            logger.warn(f"Onchain: set Z unreadable this pass ({error_message(exc)}); keeping the last list")
            return
        self._tracked_addresses = tracked

    def _get_block_timestamp(self, block_number: int) -> Optional[int]:
        """The block's own timestamp, cached; None when the node cannot say.
        Never the wall clock: a fill with no time is not stamped and not
        copied, because every latency number and the executor's age gate
        would otherwise read a minutes-old fill as brand new."""
        if block_number in self._block_ts_cache:
            return self._block_ts_cache[block_number]
        assert self._w3 is not None
        try:
            block = self._w3.eth.get_block(block_number)
            ts = int(block["timestamp"])
        except Exception as exc:  # noqa: BLE001
            logger.warn(f"Onchain: block {block_number} time unavailable ({error_message(exc)[:120]}); fill not stamped")
            return None
        self._block_ts_cache[block_number] = ts
        if len(self._block_ts_cache) > 500:
            oldest = sorted(self._block_ts_cache.keys())[:250]
            for k in oldest:
                del self._block_ts_cache[k]
        return ts

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

            maker_asset_id, taker_asset_id, maker_amount, taker_amount = _legs_from_args(args)

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
            if block_ts is None:
                continue

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
        """Fetch OrderFilled events for a block range from both exchanges.

        Raises ChunkReadError when either exchange's read fails: nothing is
        processed from a half-read chunk, so the caller can read the same
        range again (the two-clocks rows and the shadow quotes would
        otherwise carry the good half twice)."""
        assert self._ctf_contract is not None
        assert self._neg_risk_contract is not None

        all_trades: list[DetectedTrade] = []
        tracked = sorted(self._tracked_addresses)
        if not tracked:
            return all_trades
        checksummed = [Web3.to_checksum_address(a) for a in tracked]

        read: list[tuple[list, str]] = []
        for contract, name in [
            (self._ctf_contract, "CTF"),
            (self._neg_risk_contract, "NEG_RISK_CTF"),
        ]:
            try:
                # ``get_logs`` with web3 >= 7 keyword names. The old call,
                # ``create_filter(fromBlock=..., toBlock=...)``, was the web3 6
                # spelling: on the deployed web3 8 it raised "unexpected keyword
                # argument 'fromBlock'" on every poll (found 2026-09-22 in a
                # read-only dry run; this source had never worked in prod).
                # ``maker`` and ``taker`` are indexed, so the node filters on
                # the tracked set and hands back only their fills: two small
                # queries per contract instead of every fill on the exchange.
                # A fill where a tracked wallet is BOTH sides comes back twice;
                # (tx, logIndex) dedupes it.
                seen: set = set()
                events: list = []
                for filt in ({"maker": checksummed}, {"taker": checksummed}):
                    for ev in contract.events.OrderFilled.get_logs(
                            from_block=from_block, to_block=to_block, argument_filters=filt):
                        h = ev["transactionHash"]
                        key = (h.hex() if hasattr(h, "hex") else str(h), ev.get("logIndex", 0))
                        if key in seen:
                            continue
                        seen.add(key)
                        events.append(ev)
                read.append((events, name))
            except Exception as exc:
                raise ChunkReadError(name, from_block, to_block, exc) from exc

        for events, name in read:
            all_trades.extend(self._process_events(events, name))
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
        iterations = 0
        t_started = time.time()
        blocks_done = 0
        # Refusals on the chunk at the cursor, in a row; the health record's
        # hour of retries and skips.
        chunk_failures = 0
        retry_ts: list[float] = []
        skip_ts: list[float] = []
        last_ok_ts = 0.0

        def _health_record(head: int, cur: int, now: float) -> None:
            del retry_ts[:max(0, len(retry_ts) - 10000)]
            _save_health({
                "ts": now, "ok_ts": last_ok_ts, "cursor": cur, "head": head, "lag": head - cur,
                "retries_1h": sum(1 for t in retry_ts if now - t < 3600),
                "skipped_1h": sum(1 for t in skip_ts if now - t < 3600),
                "tracked": len(self._tracked_addresses),
            })

        while self._running:
            try:
                self._refresh_tracked()
                latest = self._w3.eth.block_number - HEAD_MARGIN_BLOCKS
                # A read the chain answered is this poller's heartbeat for the
                # guard's stale-feed trigger (the data-api source stamps its
                # own). Stamped at the head, or after a chunk actually read:
                # a head that answers while every getLogs is refused is not a
                # live feed.
                from src.copy_trading.trade_store import record_poll_ok

                # Skip if cursor is too far behind
                if latest - cursor > MAX_BLOCKS_BEHIND:
                    logger.warn(
                        f"Onchain cursor {cursor} is {latest - cursor} blocks behind, "
                        f"skipping ahead to {latest - 100}"
                    )
                    cursor = latest - 100
                    _save_cursor(cursor)

                if cursor >= latest:
                    record_poll_ok()
                    last_ok_ts = time.time()
                    await asyncio.sleep(POLL_INTERVAL_S)
                    continue

                # Process in chunks of MAX_BLOCK_RANGE
                from_block = cursor + 1
                to_block = min(from_block + MAX_BLOCK_RANGE - 1, latest)

                try:
                    trades = await asyncio.get_event_loop().run_in_executor(
                        None,
                        self._fetch_events_range,
                        from_block,
                        to_block,
                    )
                except ChunkReadError as exc:
                    # The cursor HOLDS: the same range is read again after a
                    # breath. Before this the cursor advanced past a refused
                    # chunk and its fills were the data api's to find.
                    chunk_failures += 1
                    now = time.time()
                    what = "head race" if exc.head_race else "read refused"
                    if chunk_failures < CHUNK_RETRIES:
                        retry_ts.append(now)
                        logger.warn(f"Onchain: chunk {from_block}-{to_block} not read ({what}: {exc}); "
                                    f"retry {chunk_failures} of {CHUNK_RETRIES - 1} in {CHUNK_RETRY_DELAY_S:.0f}s, "
                                    f"cursor holds at {cursor}")
                        _health_record(latest, cursor, now)
                        await asyncio.sleep(CHUNK_RETRY_DELAY_S)
                        continue
                    skip_ts.append(now)
                    chunk_failures = 0
                    logger.error(f"Onchain: chunk {from_block}-{to_block} SKIPPED after {CHUNK_RETRIES} refused reads "
                                 f"({what}: {exc}); a set-Z fill in those blocks reaches the bot through the "
                                 f"data api only")
                    cursor = to_block
                    _save_cursor(cursor)
                    _health_record(latest, cursor, now)
                    continue
                chunk_failures = 0
                last_ok_ts = time.time()
                record_poll_ok()

                if trades:
                    from src.copy_trading import two_clocks
                    primary = two_clocks.is_primary()
                    logger.info(f"Onchain: {len(trades)} trades in blocks {from_block}-{to_block}"
                                + ("" if primary else " (shadow: stamped, not copied)"))
                    for trade in trades:
                        try:
                            from datetime import datetime
                            from src.copy_trading.trade_store import is_seen_trade, is_max_retries
                            ts_ms = datetime.fromisoformat(
                                trade.timestamp.replace("Z", "+00:00")
                            ).timestamp() * 1000
                            seen_at = time.time()
                            # The chain's clock on this fill, primary or not:
                            # the shadow report joins it with the api's.
                            two_clocks.note("onchain", trade.id, their_ts=ts_ms / 1000.0,
                                            seen_at=seen_at, target=trade.trader_address,
                                            token_id=trade.token_id)
                            if trade.side == "BUY":
                                # The same fill the fast prober quotes at the
                                # api's detection time, quoted again at the
                                # chain's, under its own copy_id (the observer
                                # dedupes by copy_id). The delay then has a
                                # price: two_clocks.lag_cost.
                                try:
                                    from src.copy_trading import shadow_quote
                                    shadow_quote.emit([{
                                        "copy_id": f"chain:{trade.id.rsplit('-', 1)[0]}",
                                        "target": (trade.trader_address or "").lower(),
                                        "condition_id": trade.condition_id, "token_id": trade.token_id,
                                        "outcome_index": 0, "category": "", "title": trade.market or "",
                                        "slug": "", "event_key": "", "their_price": trade.price,
                                        "their_usd": trade.size, "their_ts": ts_ms / 1000.0,
                                        "detected_at": seen_at, "age_s": seen_at - ts_ms / 1000.0,
                                        "actionable": True, "source": "onchain",
                                    }])
                                except Exception as exc:  # noqa: BLE001
                                    logger.warn(f"Onchain: shadow emit failed: {error_message(exc)}")
                            if not primary:
                                continue
                            if not is_seen_trade(trade.id) and not is_max_retries(trade.id):
                                from src.copy_trading.trade_queue import enqueue_trade
                                from src.copy_trading.trade_store import record_reaction_latency
                                from src.models import QueuedTrade
                                # ts_ms = the target's trade time; now = when
                                # we saw it. Same latency contract as the
                                # data-api source (see QueuedTrade).
                                received_ms = seen_at * 1000
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

                blocks_done += to_block - cursor
                cursor = to_block
                _save_cursor(cursor)
                _health_record(latest, cursor, last_ok_ts)
                iterations += 1
                if iterations % LAG_LOG_EVERY == 0:
                    rate = blocks_done / max(1.0, time.time() - t_started)
                    logger.info(f"Onchain: cursor {cursor}, head {latest}, lag {latest - cursor} block(s), "
                                f"{rate:.2f} blocks/s over {iterations} chunk(s), {len(self._tracked_addresses)} tracked")

            except Exception as exc:
                logger.error(f"Onchain poll error: {error_message(exc)}")
                await asyncio.sleep(5.0)

            # No pause while behind: the sleep is for an idle head, not a backlog.
            if cursor >= latest:
                await asyncio.sleep(POLL_INTERVAL_S)

    def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        logger.info("Onchain source stopped")
