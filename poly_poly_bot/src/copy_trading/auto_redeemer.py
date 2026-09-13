"""Automatic position redemption for resolved Polymarket markets.

Fetches redeemable positions from the Data API and calls CTF redeemPositions
on-chain. Skips neg-risk positions. Calculates P&L for reporting.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx
from web3 import Web3

from src.config import CONFIG
from src.constants import (
    CTF_CONTRACT,
    CTF_REDEEM_ABI,
    USDC_ADDRESS,
)
from src.logger import logger
from src.models import RedeemDetail, RedeemResult
from src.utils import error_message


# Bytes32 zero — parent collection ID for top-level positions
_ZERO_BYTES32 = b"\x00" * 32


def _build_index_sets(outcome_count: int) -> list[int]:
    """Build index sets for redemption (one bit per outcome)."""
    return [1 << i for i in range(outcome_count)]


class RedeemFetchError(RuntimeError):
    """The positions read failed after every retry.

    Raised, not swallowed. An empty list means "nothing to redeem"; a failed
    read means "we do not know", and the live guard's unredeemed trigger
    treats those two differently. Returning [] here made 27 rate-limit
    failures in 20 days read as 27 clean passes.
    """


# The data API answered 429 to the redeemer 27 times in 20 days. Three retries
# with backoff cover a rate-limit window; a longer outage is raised, not hidden.
_FETCH_RETRY_DELAYS_S: tuple[float, ...] = (1.0, 3.0, 9.0)


def _neg_risk_flag(row: dict) -> bool:
    """The live Data API row spells it ``negativeRisk``; this code read
    ``negRisk``, a key the row does not carry, so the flag was False for every
    real position and the neg-risk skip below never fired. Checked 2026-09-13
    on the proxy wallet: 68 redeemable rows, 5 of them negativeRisk, none
    carrying negRisk. A neg-risk winner would have gone to the CTF's
    redeemPositions with USDC as collateral, a call that succeeds with no
    payout (the tokens sit on the wrapped-collateral position id), and the
    receipt's status 1 would have booked the full payout as realized and
    sold the position out of the inventory while the shares stayed
    unredeemed on-chain. Accept both spellings."""
    for key in ("negativeRisk", "negRisk", "neg_risk"):
        v = row.get(key)
        if v is not None:
            return bool(v)
    return False


async def _fetch_redeemable_positions(
    proxy_wallet: str,
    *,
    sleep: Callable = asyncio.sleep,
) -> list[dict]:
    """Fetch positions eligible for redemption from the Data API.

    Returns a list of position dicts with at minimum:
      conditionId, tokenId, size, market/title, avgPrice, resolved, curPrice, negRisk
    Raises ``RedeemFetchError`` when the read fails after retries.
    """
    url = f"{CONFIG.data_api_url}/positions"
    params = {"user": proxy_wallet}

    data = None
    attempts = (*_FETCH_RETRY_DELAYS_S, None)
    for attempt, delay in enumerate(attempts, start=1):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
            break
        except Exception as exc:
            if delay is None:
                logger.error(f"[redeemer] Failed to fetch positions after "
                             f"{attempt} attempts: {error_message(exc)}")
                raise RedeemFetchError(error_message(exc)) from exc
            logger.warn(f"[redeemer] positions fetch failed (attempt {attempt}): "
                        f"{error_message(exc)}; retrying in {delay:.0f}s")
            await sleep(delay)

    if not isinstance(data, list):
        return []
    n_rows = len(data)

    redeemable: list[dict] = []
    unknown_schema = 0
    for entry in data:
        # The row's own word for "this can be redeemed now". The data API
        # carries `redeemable`; this code read `resolved`, a key the row does
        # not have, so `.get("resolved", False)` was False for EVERY position
        # forever. 61 of 61 real rows were redeemable and 0 passed. Because
        # the READ succeeded, the live guard saw a confident zero rather than
        # an error, which left its unredeemed trigger structurally unable to
        # fire and (through the equity number) the bankroll floor with it.
        # A missing key is now counted, not defaulted.
        flag = entry.get("redeemable")
        if flag is None:
            flag = entry.get("resolved")
        if flag is None:
            unknown_schema += 1
            continue
        if not flag:
            continue

        # Extract fields — handle nested market objects
        market_obj = entry.get("market", {})
        if isinstance(market_obj, dict):
            condition_id = market_obj.get("conditionId", "") or entry.get("conditionId", "")
            title = market_obj.get("question", "") or entry.get("title", "")
            neg_risk = _neg_risk_flag(market_obj) or _neg_risk_flag(entry)
            outcome_count = int(market_obj.get("outcomeCount", 2))
        else:
            condition_id = entry.get("conditionId", "")
            title = entry.get("title", "") or entry.get("market", "")
            neg_risk = _neg_risk_flag(entry)
            outcome_count = int(entry.get("outcomeCount", 2))

        if not condition_id:
            continue

        # `asset` is the token id as a STRING on the live API, not a nested
        # object. This line assumed a dict and raised AttributeError on every
        # real row; it was unreachable until the `redeemable` filter above was
        # fixed, so the crash arrived the moment rows started passing. Accept
        # both shapes and never index into a string.
        raw_asset = entry.get("asset")
        if isinstance(raw_asset, dict):
            token_id = raw_asset.get("id", "")
        else:
            token_id = str(raw_asset or "")
        token_id = token_id or str(entry.get("tokenId") or "")
        shares = float(entry.get("size", 0) or entry.get("shares", 0))
        avg_price = float(entry.get("avgPrice", 0) or entry.get("avg_price", 0))
        cur_price = float(entry.get("curPrice", 0) or entry.get("price", 0))

        if shares <= 0:
            continue

        redeemable.append({
            "conditionId": condition_id,
            "tokenId": token_id,
            "shares": shares,
            "avgPrice": avg_price,
            "curPrice": cur_price,
            "title": title,
            "negRisk": neg_risk,
            "outcomeCount": outcome_count,
            # What the position is worth NOW. A resolved loser is worth zero,
            # and zero is not stuck capital: the guard uses this to tell "the
            # redeemer is broken" from "these are old worthless tickets".
            "currentValue": float(entry.get("currentValue") or 0.0),
        })

    # Every row missing BOTH keys means the schema moved under us. Returning a
    # confident empty list is what made two safety triggers inert for weeks, so
    # this raises into the same "unknown, not zero" branch a network failure
    # takes.
    if n_rows and unknown_schema == n_rows:
        raise RedeemFetchError(
            f"none of the {n_rows} position row(s) carry a `redeemable` or "
            f"`resolved` field; the data API schema has changed and this list "
            f"cannot be trusted to be empty")
    if unknown_schema:
        logger.warn(f"[redeemer] {unknown_schema} of {n_rows} position row(s) "
                    f"carry neither `redeemable` nor `resolved`; they are excluded")
    return redeemable


def _payout_per_share(cur_price: float) -> float:
    """What one resolved share pays: $1 (won), $0 (lost), or $0.50 on a
    cancelled market (the CTF's 50/50 payout vector; verified 2026-09-13 on
    a real refunded market, every holder row at curPrice 0.5). The win
    threshold stays where the old `> 0.5` rule put it: a resolved winner the
    API reports at 0.97 must never be booked as a total loss."""
    if 0.45 <= cur_price <= 0.55:
        return 0.5
    return 1.0 if cur_price > 0.55 else 0.0


def settle_from_api(positions: list[dict], notify=None) -> list[RedeemDetail]:
    """Book realized P&L for resolved positions this bot will not redeem
    itself, from the API's resolution (issue #32).

    Two paths never reached realized-pnl.jsonl: neg-risk positions (a
    different adapter; skipped by design) and, in production, EVERY position,
    because the bot signs as a different address from the proxy wallet, sends
    no redeem, and Polymarket's own claim pays the wallet. The outcome is
    fixed at resolution whoever claims it, so a resolved position that the
    local inventory attributes to a followed wallet (stamped at buy time by
    the live copy path) is booked now, source "redeemer" so /pnl and the
    daily real-money line count it, settlement "api" so the row says how,
    and taken out of the inventory. The legacy tickets on the wallet carry no
    attribution and are left alone, as before. The ledger's
    (condition_id, token_id) resolution dedup keeps a later on-chain redeem
    from booking the same position twice."""
    from src.copy_trading.inventory import get_position, record_sell
    from src.copy_trading.pnl import append_realized, load_realized, _settled_resolution_keys

    booked = _settled_resolution_keys(load_realized())
    out: list[RedeemDetail] = []
    for pos in positions:
        token_id = str(pos.get("tokenId") or "")
        condition_id = str(pos.get("conditionId") or "")
        if not token_id or not condition_id:
            continue
        if (condition_id, token_id) in booked:
            continue
        try:
            inv_pos = get_position(token_id) or {}
        except Exception:
            inv_pos = {}
        if not inv_pos.get("trader_address"):
            continue  # not a live copy this bot made; no attribution, no row
        shares = float(inv_pos.get("shares") or pos.get("shares") or 0.0)
        avg_price = float(inv_pos.get("avg_price") or pos.get("avgPrice") or 0.0)
        if shares <= 0:
            continue
        payout = _payout_per_share(float(pos.get("curPrice") or 0.0))
        cost_basis = shares * avg_price
        returned = shares * payout
        title = str(pos.get("title") or inv_pos.get("market") or "")
        try:
            append_realized({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "title": title,
                "condition_id": condition_id,
                "token_id": token_id,
                "shares": round(shares, 6),
                "avg_price": round(avg_price, 6),
                "cost_basis": round(cost_basis, 6),
                "returned": round(returned, 6),
                "pnl": round(returned - cost_basis, 6),
                "won": payout >= 1.0,
                "refunded": payout == 0.5,
                "tier": inv_pos.get("tier", ""),
                "trader_address": inv_pos.get("trader_address", ""),
                "exit": "resolution",
                "source": "redeemer",
                "settlement": "api",
                "redeemed_onchain": False,
                "neg_risk": bool(pos.get("negRisk", False)),
            })
        except Exception as exc:
            logger.warn(f"[redeemer] settlement row not written for '{title[:60]}': {error_message(exc)}")
            continue
        try:
            record_sell(token_id, shares)
        except Exception as exc:
            logger.warn(f"[redeemer] settled position not dropped from inventory: {error_message(exc)}")
        out.append(RedeemDetail(title=title, shares=shares, cost_basis=cost_basis, returned=returned))
        logger.info(f"[redeemer] settled '{title[:60]}' from the API: {shares:.2f} sh, "
                    f"returned ${returned:.2f} on ${cost_basis:.2f}"
                    f"{' (refund)' if payout == 0.5 else ''}")
    if out and notify is not None:
        pnl = sum(d.returned - d.cost_basis for d in out)
        lines = [f"📒 <b>{len(out)} resolved position(s) settled</b> from the API "
                 f"(realized {pnl:+,.2f} USD). Claimed by Polymarket, not by this bot."]
        for d in out[:6]:
            lines.append(f"• {d.title[:50]}: {d.returned - d.cost_basis:+,.2f}")
        try:
            notify("\n".join(lines))
        except Exception as exc:
            logger.warn(f"[redeemer] settlement notify failed: {exc}")
    return out


# Conditions already reported, so a permanent situation speaks once, not every
# 30 minutes forever.
_warned: set = set()


# A resolved position worth less than this has nothing to collect.
DUST_VALUE_USD = 1.0


def _position_value(p: dict) -> float:
    """What the position is worth now: the API's figure, else shares times
    the current price (the rows a fake or an older schema hands over)."""
    v = float(p.get("currentValue") or 0.0)
    if v > 0:
        return v
    try:
        return float(p.get("shares") or 0.0) * float(p.get("curPrice") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _warn_once(key: str) -> bool:
    if key in _warned:
        return False
    _warned.add(key)
    return True


async def check_and_redeem_positions(private_key: str,
                                     notify=None) -> RedeemResult:
    """Check for resolved positions and redeem them on-chain.

    Args:
        private_key: Hex private key (without 0x prefix).

    Returns:
        RedeemResult with count, market names, total shares, and per-position details.
    """
    proxy_wallet = CONFIG.proxy_wallet
    if not proxy_wallet:
        logger.warn("[redeemer] No proxy wallet configured, skipping redemption")
        return RedeemResult()

    try:
        positions = await _fetch_redeemable_positions(proxy_wallet)
    except RedeemFetchError as exc:
        # Skip THIS pass and say so. The next pass (30 minutes) retries; the
        # guard sees the failed read as unknown, not as "nothing stuck".
        logger.warn(f"[redeemer] skipping this pass, positions unreadable: {exc}")
        return RedeemResult()
    if not positions:
        return RedeemResult()

    w3 = Web3(Web3.HTTPProvider(CONFIG.rpc_url))
    account = w3.eth.account.from_key(f"0x{private_key}")

    # WHO HOLDS THE TOKENS decides who may redeem them. `redeemPositions`
    # redeems for msg.sender, and these positions belong to the proxy while
    # this transaction would be signed by the EOA. The call does NOT revert on
    # a zero balance: it skips the burn, transfers nothing, and returns
    # status 1, which this function's success branch would then book as a
    # WINNING realized-P&L row that never happened, into the same ledger the
    # honest-metrics floor reads. So refuse before sending anything, say it
    # once, and leave the positions counted so the guard's unredeemed trigger
    # can still fire.
    if (CONFIG.proxy_wallet or "").lower() != account.address.lower():
        # This bot sends no redeem here; the outcome is booked from the API
        # for the positions it made (issue #32), then the standing warnings.
        settled = settle_from_api(positions, notify=notify)
        # Only positions with something to collect are worth a message. The
        # 61 April-era losers on this wallet are worth under $1 each; naming
        # them "worth $837 at cost" on every boot read as a loss six times in
        # one day. Their cost still counts, in the log, once.
        collectable = [p for p in positions if _position_value(p) >= DUST_VALUE_USD]
        if not collectable:
            if _warn_once("proxy-mismatch-dust"):
                logger.info(f"[redeemer] {len(positions)} resolved position(s) sit on "
                            f"the proxy wallet, each worth under ${DUST_VALUE_USD:.0f}: "
                            f"nothing to claim, nothing sent, no P&L recorded.")
            return RedeemResult(settled=len(settled), settled_details=settled)
        if _warn_once("proxy-mismatch"):
            value = sum(float(p.get("currentValue") or 0.0) for p in collectable)
            msg = (f"{len(collectable)} position(s) worth ${value:,.2f} are held by "
                   f"the proxy wallet, but this bot signs as a different address, "
                   f"so it sends no redeem. Nothing was sent and no P&L was "
                   f"recorded. Polymarket's own claim usually pays them to the "
                   f"wallet within hours; if one is still here tomorrow, claim "
                   f"it by hand in the Polymarket interface.")
            logger.error(f"[redeemer] {msg}")
            if notify is not None:
                try:
                    notify("💤 <b>Cannot redeem automatically.</b> " + msg)
                except Exception as exc:
                    logger.warn(f"[redeemer] notify failed: {exc}")
        return RedeemResult(settled=len(settled), settled_details=settled)

    ctf = w3.eth.contract(
        address=Web3.to_checksum_address(CTF_CONTRACT),
        abi=CTF_REDEEM_ABI,
    )

    # Gas overrides
    fee_history = w3.eth.fee_history(1, "latest")
    base_fee = fee_history["baseFeePerGas"][-1]
    max_fee = base_fee * 2
    max_priority_fee = Web3.to_wei(50, "gwei")

    redeemed_count = 0
    redeemed_markets: list[str] = []
    total_shares = 0.0
    details: list[RedeemDetail] = []

    # Neg-risk positions use a different redemption mechanism (the adapter);
    # they are not redeemed here, but their outcome is booked from the API
    # (issue #32) so the realized ledger sees them.
    settled = settle_from_api([p for p in positions if p.get("negRisk", False)], notify=notify)

    for pos in positions:
        if pos.get("negRisk", False):
            continue

        condition_id = pos["conditionId"]
        shares = pos["shares"]
        avg_price = pos["avgPrice"]
        cur_price = pos["curPrice"]
        title = pos["title"]
        outcome_count = pos.get("outcomeCount", 2)

        index_sets = _build_index_sets(outcome_count)

        try:
            logger.info(f"[redeemer] Redeeming {shares:.2f} shares of '{title[:60]}'...")

            tx = ctf.functions.redeemPositions(
                Web3.to_checksum_address(USDC_ADDRESS),
                _ZERO_BYTES32,
                Web3.to_bytes(hexstr=condition_id),
                index_sets,
            ).build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "maxFeePerGas": max_fee,
                "maxPriorityFeePerGas": max_priority_fee,
            })

            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

            if receipt["status"] == 1:
                redeemed_count += 1
                redeemed_markets.append(title)
                total_shares += shares

                # P&L calculation: a winning binary share redeems for $1, a
                # losing one for $0 — and a CANCELLED market's shares redeem
                # for $0.50 each. On a cancellation the CTF payout vector is
                # set 50/50 (both outcomes pay half), and curPrice sits at
                # 0.5; `cur_price > 0.5 ? shares : 0` turned that half-refund
                # into a total loss in realized-pnl.jsonl, overstating the
                # loss by half the position on every refunded market.
                cost_basis = shares * avg_price
                payout_per_share = _payout_per_share(cur_price)
                returned = shares * payout_per_share
                won = payout_per_share == 1.0

                details.append(RedeemDetail(
                    title=title,
                    shares=shares,
                    cost_basis=cost_basis,
                    returned=returned,
                ))

                # Persist realized P&L so /pnl can report it. This is the only
                # place a copy position is closed, so this ledger is the source
                # of truth for Strategy 1 realized P&L. We read the local
                # inventory position first to attribute the row to its strategy
                # tier and the followed wallet (stamped at buy time).
                try:
                    from src.copy_trading.inventory import get_position
                    inv_pos = get_position(pos.get("tokenId", "")) or {}
                except Exception:
                    inv_pos = {}
                try:
                    from src.copy_trading.pnl import append_realized
                    append_realized({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "title": title,
                        "condition_id": condition_id,
                        "token_id": pos.get("tokenId", ""),
                        "shares": round(shares, 6),
                        "avg_price": round(avg_price, 6),
                        "cost_basis": round(cost_basis, 6),
                        "returned": round(returned, 6),
                        "pnl": round(returned - cost_basis, 6),
                        "won": won,
                        "tier": inv_pos.get("tier", ""),
                        "trader_address": inv_pos.get("trader_address", ""),
                        "exit": "resolution",
                        # Provenance: the preview resolver writes the same
                        # shape into the same file. The daily real-money
                        # line must never count paper as realized.
                        "source": "redeemer",
                    })
                except Exception as led_err:
                    logger.warn(f"[redeemer] Failed to record realized P&L: {error_message(led_err)}")

                # Update local inventory
                try:
                    from src.copy_trading.inventory import record_sell
                    record_sell(pos["tokenId"], shares)
                except Exception as inv_err:
                    logger.warn(f"[redeemer] Failed to update inventory: {error_message(inv_err)}")

                logger.info(f"[redeemer] Redeemed '{title[:60]}'. TX: {tx_hash.hex()}")
            else:
                logger.warn(f"[redeemer] Redemption tx reverted for '{title[:60]}'. TX: {tx_hash.hex()}")

        except Exception as exc:
            logger.error(f"[redeemer] Failed to redeem '{title[:60]}': {error_message(exc)}")
            continue

    return RedeemResult(
        count=redeemed_count,
        markets=redeemed_markets,
        total_shares=total_shares,
        details=details,
        settled=len(settled),
        settled_details=settled,
    )
