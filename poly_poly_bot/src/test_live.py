"""On-demand `/test-live` smoke test for live order placement.

Picks a geopolitics market resolving in the next ~36h whose favourite side
is priced above 90% and posts a small BUY through the same CLOB code path
the strategies use, so a single Telegram command exercises end-to-end live
trading without committing more than a few dollars.

Geopolitics markets currently carry no taker fee, so the bet round-trips
without paying a Polymarket fee on top of the spread.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional

import requests

from src.config import CONFIG
from src.logger import logger
from src.utils import error_message

GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"

# Default bet size for /test-live. $5 keeps the loss-on-NO bounded while
# still meeting MIN_ORDER_SIZE_USD (currently $5).
DEFAULT_BET_SIZE_USD = 5.0

# Resolution window — the market's endDate must fall within this many
# hours from "now" to be eligible. The geopolitics universe is sparse
# in the 0–48h horizon (most "happens by ..." markets resolve on
# weekly/monthly grid lines), so a one-week window is what reliably
# finds something to bet on while still keeping the round-trip short.
RESOLUTION_WINDOW_HOURS = 168

# Minimum favourite-side price for the market to be considered a safe
# test target. Above 90% the resolution is overwhelmingly likely to pay
# the bet back in full, modulo black-swan resolutions.
MIN_FAVOURITE_PRICE = 0.90

# Cap the BUY price so we never accidentally pay 99.9c chasing the book
# on a thin market.
MAX_BUY_PRICE = 0.99


@dataclass
class TestMarketCandidate:
    condition_id: str
    question: str
    event_title: str
    event_slug: str
    end_iso: str
    favourite_side: str          # "YES" or "NO" — which outcome is priced > MIN_FAVOURITE_PRICE
    favourite_price: float
    favourite_token_id: str
    best_ask: float
    polymarket_url: str


def _parse_list_field(market: dict, key: str) -> Optional[list]:
    raw = market.get(key)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else None
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(raw, list):
        return raw
    return None


def _parse_iso_to_epoch(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _classify_favourite(prices: list, token_ids: list) -> Optional[tuple[str, float, str]]:
    """If one side of a binary market is priced > MIN_FAVOURITE_PRICE, return
    (side_label, price, token_id) for that side. Otherwise return None.

    Polymarket binary markets store [YES, NO] in both arrays.
    """
    if len(prices) < 2 or len(token_ids) < 2:
        return None
    try:
        yes_price = float(prices[0])
        no_price = float(prices[1])
    except (TypeError, ValueError):
        return None
    if yes_price >= MIN_FAVOURITE_PRICE:
        return "YES", yes_price, str(token_ids[0])
    if no_price >= MIN_FAVOURITE_PRICE:
        return "NO", no_price, str(token_ids[1])
    return None


def find_test_market(
    *,
    now_ts: Optional[float] = None,
    events: Optional[list[dict]] = None,
) -> Optional[TestMarketCandidate]:
    """Return the first eligible geopolitics market resolving soon, or None.

    Eligibility requirements:
      - tag_slug=geopolitics, active=true, closed=false (handled by the
        Gamma query parameters)
      - one of YES/NO priced ≥ MIN_FAVOURITE_PRICE
      - endDate within the next RESOLUTION_WINDOW_HOURS hours
      - non-zero best ask on the favourite side so the order can actually
        match the book

    `events` and `now_ts` are injectable for testing.
    """
    if now_ts is None:
        now_ts = time.time()

    if events is None:
        try:
            resp = requests.get(
                GAMMA_EVENTS_URL,
                params={
                    "tag_slug": "geopolitics",
                    "closed": "false",
                    "active": "true",
                    "limit": 200,
                    "order": "endDate",
                    "ascending": "true",
                },
                timeout=15,
            )
            resp.raise_for_status()
            events = resp.json()
        except Exception as exc:
            logger.error(f"[test-live] Gamma events fetch failed: {error_message(exc)}")
            return None

    if not isinstance(events, list):
        return None

    cutoff_ts = now_ts + RESOLUTION_WINDOW_HOURS * 3600

    for event in events:
        ev_title = str(event.get("title") or "")
        ev_slug = str(event.get("slug") or "")
        markets = event.get("markets") or []
        for market in markets:
            if market.get("closed"):
                continue
            if market.get("active") is False:
                continue
            end_iso = market.get("endDate") or market.get("umaEndDate") or ""
            end_ts = _parse_iso_to_epoch(end_iso)
            if end_ts is None or end_ts <= now_ts or end_ts > cutoff_ts:
                continue
            prices = _parse_list_field(market, "outcomePrices")
            tokens = _parse_list_field(market, "clobTokenIds")
            if not prices or not tokens:
                continue
            picked = _classify_favourite(prices, tokens)
            if picked is None:
                continue
            side, price, token_id = picked
            if not token_id:
                continue
            try:
                best_ask_yes = float(market.get("bestAsk") or 0.0)
                best_bid_yes = float(market.get("bestBid") or 0.0)
            except (TypeError, ValueError):
                best_ask_yes = 0.0
                best_bid_yes = 0.0
            # bestAsk/bestBid are quoted on the YES side; flip for the NO leg.
            if side == "YES":
                best_ask = best_ask_yes
            else:
                best_ask = (1.0 - best_bid_yes) if best_bid_yes > 0 else 0.0
            if best_ask <= 0:
                continue
            cid = str(market.get("conditionId") or "")
            if not cid:
                continue
            return TestMarketCandidate(
                condition_id=cid,
                question=str(market.get("question") or ""),
                event_title=ev_title,
                event_slug=ev_slug,
                end_iso=end_iso,
                favourite_side=side,
                favourite_price=price,
                favourite_token_id=token_id,
                best_ask=best_ask,
                polymarket_url=(
                    f"https://polymarket.com/event/{ev_slug}" if ev_slug else ""
                ),
            )
    return None


def place_test_bet(
    *,
    clob_client,
    candidate: TestMarketCandidate,
    bet_size_usd: float = DEFAULT_BET_SIZE_USD,
) -> dict:
    """Place a single BUY on `candidate.favourite_token_id` for `bet_size_usd`.

    Returns a status dict suitable for posting to Telegram:
        {"status": "placed"|"failed"|"skipped:<reason>", ...}
    """
    if clob_client is None:
        return {"status": "skipped:no_clob_client"}
    if bet_size_usd < CONFIG.min_order_size_usd:
        return {
            "status": (
                f"skipped:bet_below_min(${bet_size_usd:.2f}<"
                f"${CONFIG.min_order_size_usd:.2f})"
            )
        }

    from src.copy_trading.daily_spend_guard import can_spend, record_spend
    ok, reason = can_spend(bet_size_usd)
    if not ok:
        return {"status": f"skipped:daily_cap({reason})"}

    # Use the favourite-side ask as the reference price; place_buy_yes will
    # add the standard 1.02× crossing buffer and clamp to [0.01, 0.99].
    ref_price = min(max(candidate.best_ask, 0.01), MAX_BUY_PRICE)

    from src.tennis.order_placer import place_buy_yes
    live = place_buy_yes(
        clob_client=clob_client,
        token_id=candidate.favourite_token_id,
        bet_size_usd=bet_size_usd,
        ref_price=ref_price,
    )
    if not live or not live.get("order_id"):
        err = (live or {}).get("error") or "no_order_id_in_response"
        return {"status": f"failed:{err}", "ref_price": ref_price}

    record_spend(bet_size_usd, source="test-live")
    return {
        "status": "placed",
        "order_id": live["order_id"],
        "shares": live["shares"],
        "order_price": live["order_price"],
        "ref_price": ref_price,
    }
