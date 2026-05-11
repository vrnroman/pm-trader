"""Strategy #3: Tennis Odds Arbitrage — Smarkets vs Polymarket.

Compares Smarkets exchange odds (live tick-resolution mid prices) against
Polymarket tennis match prices and generates trade signals on divergences
above a configurable threshold.

Core loop:
  1. Fetch sharp odds from Smarkets
  2. Fetch Polymarket tennis match markets via Gamma API
  3. Match Smarkets events to Polymarket markets by player names
  4. Calculate divergence = sharp_implied_prob - polymarket_price
  5. If divergence > threshold, generate signal (BUY YES on underpriced side)
  6. Size using fractional Kelly criterion, capped at max bet
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

import requests

from src import runtime_state
from src.config import CONFIG
from src.odds.models import MatchOdds, OddsComparison
from src.odds.smarkets import SmarketsProvider
from src.tennis.paper_book import TennisPaperBook

logger = logging.getLogger("strategy.tennis_arb")

SGT = timezone(timedelta(hours=8))

GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"


class TennisArbStrategy:
    """Tennis odds arbitrage: sharp books vs Polymarket."""

    def __init__(
        self,
        min_divergence: float = 0.08,
        max_bet_size: float = 165.0,
        kelly_fraction: float = 0.3,
        tournaments: list[str] | None = None,
        min_volume: float = 50_000.0,
        min_liquidity: float = 10_000.0,
        preview_mode: bool = True,
        data_dir: str = "",
        min_edge_step: float = 0.05,
        max_event_date_delta_days: float = 3.0,
        take_profit_ratio: float = 3.0,
        min_bet_size: float = 5.0,
        clob_client=None,
        revalidation_min_divergence: float = 0.06,
        second_bet_kelly_fraction: float = 0.2,
        max_bets_per_event: int = 2,
    ):
        self.min_divergence = min_divergence
        self.max_bet_size = max_bet_size
        # Polymarket rejects orders below ~$5; if Kelly recommends a tinier
        # bet, we bump it up to this floor. Without the floor we'd emit an
        # unfillable signal every scan.
        self.min_bet_size = max(0.0, float(min_bet_size))
        self.kelly_fraction = kelly_fraction
        self.tournaments = tournaments or ["ATP", "WTA"]
        self.min_volume = min_volume
        self.min_liquidity = min_liquidity
        # Initial preview default. Live state of record is runtime_state, which
        # is checked dynamically per scan so Telegram-driven flips take effect
        # without a restart. Constructor flag is just a fallback for tests /
        # first-run when no runtime_state file exists yet.
        self.preview_mode = preview_mode
        self.data_dir = data_dir
        self.clob_client = clob_client
        # Re-bet gate: only emit a new signal if edge grew by this much vs last
        # recorded bet on the same market (prevents spamming the same bet every
        # scan when edge stays roughly constant).
        self.min_edge_step = min_edge_step
        # Same-event guard: event endDate must be within ±N days of match_time
        self.max_event_date_delta_days = max_event_date_delta_days
        # After Gamma's edge clears min_divergence, we refetch the live CLOB
        # ask and recompute the edge against it. The signal only fires if
        # the live edge is still ≥ this floor — otherwise Gamma was lagging.
        # Set <= 0 to disable revalidation entirely.
        self.revalidation_min_divergence = revalidation_min_divergence
        # Take-profit gate: close any open paper position whose current PM
        # YES price is at least this multiple of its entry price. With the
        # default 3.0, a position bought at 0.20 fixes profit when the
        # market rallies to 0.60. After a DCA add, entry_price is the
        # share-weighted VWAP so the gate blends across legs.
        self.take_profit_ratio = take_profit_ratio
        # Pyramid-up sizing: when the re-bet gate clears for a 2nd bet on the
        # same event, size at this Kelly fraction instead of the full
        # ``kelly_fraction``. We're already long once at this point; the
        # smaller add caps tail exposure if PM never converges.
        self.second_bet_kelly_fraction = second_bet_kelly_fraction
        # Hard cap on bets per Polymarket event (condition_id). FLIPs to the
        # opposite side count against this cap.
        self.max_bets_per_event = max(1, int(max_bets_per_event))

        # Real-time tennis prices via Smarkets' public REST API. No account /
        # API key / payment required — see src/odds/smarkets.py for the
        # rationale and architecture notes. Older OddsPapi / The Odds API
        # providers were removed because they served closing-line snapshots
        # that froze the moment a match went in-play, defeating the live-arb
        # thesis.
        self._provider = SmarketsProvider()

        # Paper-trading book: keeps a notional position per market, lets a
        # contradicting signal close+flip into the new direction, and
        # auto-closes positions when the underlying Polymarket market
        # resolves. Disabled if data_dir is not configured (in tests).
        self.paper_book: TennisPaperBook | None = (
            TennisPaperBook(data_dir=data_dir) if data_dir else None
        )

        # Auto-resolve throttle: tennis markets settle hours after the
        # match ends, so polling Gamma every few minutes is plenty —
        # cheaper than once per scan when scan_interval is 60s.
        self._resolve_min_interval_s: float = 300.0
        self._last_resolve_at: float = 0.0

    def scan(self) -> list[dict]:
        """Run a single scan: fetch odds, find markets, detect divergences.

        Returns list of signal dicts ready for execution or logging.
        """
        scan_started_at = time.monotonic()
        metrics: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "preview": runtime_state.is_preview(3),
        }
        self._gamma_calls_in_scan = 0
        self._scan_clob_calls = 0
        self._scan_clob_s = 0.0
        smarkets_calls_baseline = getattr(self._provider, "call_count", 0)
        try:
            return self._scan_body(metrics, scan_started_at)
        finally:
            metrics["total_s"] = round(time.monotonic() - scan_started_at, 3)
            metrics["smarkets_calls"] = (
                getattr(self._provider, "call_count", 0) - smarkets_calls_baseline
            )
            metrics["gamma_calls"] = self._gamma_calls_in_scan
            metrics["clob_revalidation_calls"] = self._scan_clob_calls
            metrics["clob_revalidation_s"] = round(self._scan_clob_s, 3)
            self._save_metrics(metrics)

    def _scan_body(self, metrics: dict, scan_started_at: float) -> list[dict]:
        logger.info(f"Tennis arb scan starting (provider={self._provider.name})")

        # Step 0: Settle any open paper positions whose underlying Polymarket
        # market has resolved since the last scan. We do this before the
        # divergence work so realized PnL is up to date by the time we may
        # decide to flip into a new position on the same event.
        t_phase = time.monotonic()
        self._resolve_settled_paper_positions()
        metrics["resolve_s"] = round(time.monotonic() - t_phase, 3)

        # Step 1: Fetch sharp odds
        t_phase = time.monotonic()
        sharp_odds = self._provider.fetch_tennis_odds(tours=self.tournaments)
        metrics["smarkets_s"] = round(time.monotonic() - t_phase, 3)
        metrics["sharp_odds_count"] = len(sharp_odds)
        if not sharp_odds:
            logger.info("No sharp odds available")
            return []
        logger.info(f"Fetched {len(sharp_odds)} matches from {self._provider.name}")

        # Step 2: Fetch Polymarket tennis markets
        t_phase = time.monotonic()
        poly_markets = self._fetch_polymarket_tennis_markets()
        metrics["gamma_s"] = round(time.monotonic() - t_phase, 3)
        metrics["pm_markets_count"] = len(poly_markets)
        if not poly_markets:
            logger.info("No Polymarket tennis markets found")
            return []
        logger.info(f"Found {len(poly_markets)} Polymarket tennis markets")

        # Step 2b: Take-profit gate — close open positions whose current PM
        # price is ≥ take_profit_ratio × entry_price. Done before the
        # divergence work so a fix-profit close that happens to live on the
        # same market as a fresh signal can be reflected immediately.
        t_phase = time.monotonic()
        tp_events = self._check_take_profit(poly_markets)
        metrics["take_profit_s"] = round(time.monotonic() - t_phase, 3)
        metrics["take_profit_events"] = len(tp_events)

        # Step 3: Match and compare
        t_phase = time.monotonic()
        comparisons = self._match_and_compare(sharp_odds, poly_markets)
        metrics["match_compare_s"] = round(time.monotonic() - t_phase, 3)
        metrics["comparisons_count"] = len(comparisons)
        logger.info(f"Matched {len(comparisons)} market-odds pairs")

        for comp, pm in comparisons:
            logger.info(
                f"  >> {comp.match_odds.player_a} vs {comp.match_odds.player_b} | "
                f"Sharp: {comp.sharp_prob:.1%} / PM: {comp.polymarket_price:.1%} | "
                f"Edge: {comp.divergence:+.1%} | {pm.get('question', '')}"
            )

        # Step 4: Filter by divergence threshold + re-bet gate
        bet_state = self._load_bet_state()
        signals = []
        skipped_dedupe = 0
        # Per-signal "noticed divergence → order submitted" stopwatches. Stored
        # on metrics so we can answer "how fresh is the price our order hit?"
        # without grepping logs.
        signal_latencies: list[dict] = []
        for comp, pm in comparisons:
            if comp.divergence < self.min_divergence:
                continue

            # Stopwatch starts here: this is the moment we "noticed" the
            # divergence is large enough to act on. Everything below (live
            # revalidation, re-bet gate, sizing, order placement) is counted
            # against detect→order latency.
            t_detect = time.monotonic()
            revalidate_s = 0.0
            order_place_s = 0.0

            # Live revalidation: Gamma's outcomePrices is the last-trade
            # price and lags the live ask by several cents on low-volume
            # tennis markets. Refetch the CLOB book once the cheap filter
            # passes so the bet-or-skip decision uses the real fill cost.
            #
            #   Gamma edge ≥ min_divergence (8%)  →  cheap candidate
            #   live edge  ≥ revalidation_min_divergence (6%)  →  fire
            #   live edge below floor              →  drop, Gamma was stale
            #
            # The default 8% / 6% gap absorbs ~2¢ of normal Gamma drift.
            pm_price = comp.polymarket_price
            edge = comp.divergence
            gamma_price = comp.polymarket_price
            live_ask: float | None = None
            if (
                self.clob_client is not None
                and comp.polymarket_token_id
                and self.revalidation_min_divergence > 0
            ):
                from src.tennis.order_placer import _fetch_book
                t_clob = time.monotonic()
                self._scan_clob_calls += 1
                try:
                    best_ask, _, _ = _fetch_book(self.clob_client, comp.polymarket_token_id)
                except Exception as exc:
                    revalidate_s = time.monotonic() - t_clob
                    self._scan_clob_s += revalidate_s
                    signal_latencies.append({
                        "outcome": "revalidate_failed",
                        "revalidate_ms": round(revalidate_s * 1000),
                        "order_place_ms": 0,
                        "detect_to_order_ms": round((time.monotonic() - t_detect) * 1000),
                    })
                    logger.warning(
                        f"Tennis arb: live revalidation failed for "
                        f"{pm.get('question','')}: {exc} — skipping signal"
                    )
                    continue
                revalidate_s = time.monotonic() - t_clob
                self._scan_clob_s += revalidate_s
                if best_ask <= 0:
                    signal_latencies.append({
                        "outcome": "empty_book",
                        "revalidate_ms": round(revalidate_s * 1000),
                        "order_place_ms": 0,
                        "detect_to_order_ms": round((time.monotonic() - t_detect) * 1000),
                    })
                    logger.info(
                        f"Tennis arb: empty live book for {pm.get('question','')} — "
                        f"skipping signal"
                    )
                    continue
                live_ask = best_ask
                live_edge = comp.sharp_prob - best_ask
                if live_edge < self.revalidation_min_divergence:
                    signal_latencies.append({
                        "outcome": "live_edge_too_low",
                        "revalidate_ms": round(revalidate_s * 1000),
                        "order_place_ms": 0,
                        "detect_to_order_ms": round((time.monotonic() - t_detect) * 1000),
                    })
                    logger.info(
                        f"Tennis arb: signal dropped — Gamma edge "
                        f"{comp.divergence:.1%} but live edge {live_edge:.1%} "
                        f"< {self.revalidation_min_divergence:.1%} "
                        f"({pm.get('question','')})"
                    )
                    continue
                pm_price = best_ask
                edge = live_edge

            # Re-bet gate. State is keyed by condition_id (the Polymarket
            # event), so a FLIP to the opposite token counts against the
            # per-event bet cap.
            #
            # First bet: no gate beyond min_divergence + live revalidation.
            #
            # Re-bet on the *same* side (token_id matches first_token_id):
            #   1. bets_count must be < max_bets_per_event
            #   2. live edge must have grown by ≥ min_edge_step vs first bet
            #   3. PM price didn't drop vs first bet (else we're catching a
            #      falling knife — PM moved toward sharp, not away)
            #   4. Sharp probability moved further from PM since first bet
            #      (the move is sharp leading, not PM converging)
            #
            # FLIP (token_id differs from first_token_id): still counts
            # toward the cap, but the first-bet anchors don't apply (the
            # thesis is on a different side, comparing prices is meaningless).
            state_key = comp.polymarket_condition_id
            prev = bet_state.get(state_key)
            is_second_bet = False
            if prev is not None:
                bets_count = int(prev.get("times_emitted") or 0)
                if bets_count >= self.max_bets_per_event:
                    skipped_dedupe += 1
                    signal_latencies.append({
                        "outcome": "cap_reached",
                        "revalidate_ms": round(revalidate_s * 1000),
                        "order_place_ms": 0,
                        "detect_to_order_ms": round((time.monotonic() - t_detect) * 1000),
                    })
                    logger.debug(
                        f"Tennis arb: skip re-bet {pm.get('question','')} — "
                        f"bets_count {bets_count} ≥ cap {self.max_bets_per_event}"
                    )
                    continue

                first_edge = float(prev.get("first_divergence", prev.get("last_divergence", 0.0)))
                first_pm = float(prev.get("first_pm_price", prev.get("last_pm_price", 0.0)))
                first_sharp = float(prev.get("first_sharp_prob", prev.get("last_sharp_prob", 0.0)))
                first_token = prev.get("first_token_id") or prev.get("last_token_id") or ""
                same_side = (
                    first_token
                    and comp.polymarket_token_id
                    and first_token == comp.polymarket_token_id
                )

                if edge < first_edge + self.min_edge_step:
                    skipped_dedupe += 1
                    signal_latencies.append({
                        "outcome": "edge_step",
                        "revalidate_ms": round(revalidate_s * 1000),
                        "order_place_ms": 0,
                        "detect_to_order_ms": round((time.monotonic() - t_detect) * 1000),
                    })
                    logger.debug(
                        f"Tennis arb: skip re-bet {pm.get('question','')} — "
                        f"edge {edge:.1%} vs first {first_edge:.1%} "
                        f"(step {self.min_edge_step:.0%})"
                    )
                    continue

                if same_side:
                    if pm_price < first_pm:
                        skipped_dedupe += 1
                        signal_latencies.append({
                            "outcome": "pm_dropped",
                            "revalidate_ms": round(revalidate_s * 1000),
                            "order_place_ms": 0,
                            "detect_to_order_ms": round((time.monotonic() - t_detect) * 1000),
                        })
                        logger.debug(
                            f"Tennis arb: skip re-bet {pm.get('question','')} — "
                            f"PM dropped {first_pm:.3f}→{pm_price:.3f}"
                        )
                        continue
                    if comp.sharp_prob <= first_sharp:
                        skipped_dedupe += 1
                        signal_latencies.append({
                            "outcome": "sharp_flat",
                            "revalidate_ms": round(revalidate_s * 1000),
                            "order_place_ms": 0,
                            "detect_to_order_ms": round((time.monotonic() - t_detect) * 1000),
                        })
                        logger.debug(
                            f"Tennis arb: skip re-bet {pm.get('question','')} — "
                            f"sharp didn't move up {first_sharp:.3f}→{comp.sharp_prob:.3f}"
                        )
                        continue
                is_second_bet = True

            kelly_for_this_bet = (
                self.second_bet_kelly_fraction if is_second_bet else None
            )
            bet_size = self._calculate_bet_size(
                comp.sharp_prob, pm_price, kelly_fraction=kelly_for_this_bet,
            )

            event_slug = pm.get("event_slug", "")
            polymarket_url = (
                f"https://polymarket.com/event/{event_slug}" if event_slug else ""
            )
            outcome_label = (
                pm.get("group_item_title")
                or comp.polymarket_player
                or ""
            )

            signal = {
                "strategy": "tennis_arb",
                "tournament": comp.match_odds.tournament,
                "tour": comp.match_odds.tour,
                "player_a": comp.match_odds.player_a,
                "player_b": comp.match_odds.player_b,
                "target_player": comp.polymarket_player,
                "outcome_label": outcome_label,
                "sharp_source": comp.match_odds.source,
                "sharp_prob": round(comp.sharp_prob, 4),
                "sharp_odds_a": comp.match_odds.odds_a,
                "sharp_odds_b": comp.match_odds.odds_b,
                "polymarket_price": round(pm_price, 4),
                "polymarket_gamma_price": round(gamma_price, 4),
                "live_ask": round(live_ask, 4) if live_ask is not None else None,
                "divergence": round(edge, 4),
                "gamma_divergence": round(comp.divergence, 4),
                "side": comp.side,
                "bet_size": round(bet_size, 2),
                "kelly_size": round(bet_size, 2),
                "market_id": comp.polymarket_market_id,
                "condition_id": comp.polymarket_condition_id,
                "token_id": comp.polymarket_token_id,
                "event_title": pm.get("event_title", ""),
                "event_slug": event_slug,
                "polymarket_url": polymarket_url,
                "polymarket_question": pm.get("question", ""),
                "polymarket_volume": comp.polymarket_volume,
                "polymarket_liquidity": comp.polymarket_liquidity,
                "match_time": (
                    comp.match_odds.match_time.isoformat()
                    if comp.match_odds.match_time
                    else None
                ),
                "timestamp": datetime.now(SGT).isoformat(),
                "preview": runtime_state.is_preview(3),
            }

            # Live execution: place a real BUY YES order on the CLOB before
            # the paper book records the position so the recorded position
            # carries the actual order_id. If the live BUY fails the signal
            # still gets emitted/paper-booked so we don't lose the trail; it
            # just stays a paper-only position.
            #
            # signal["live_status"] is always populated so the Telegram alert
            # and downstream tooling can show why a live order did or didn't
            # post — the previous silent skip path made it look like live mode
            # was broken when it was just gated.
            in_preview = runtime_state.is_preview(3)
            if in_preview:
                signal["live_status"] = "preview"
            elif self.clob_client is None:
                signal["live_status"] = "skipped:no_clob_client"
                logger.warning(
                    f"Tennis arb: live BUY skipped — clob_client is None "
                    f"(token={comp.polymarket_token_id[:12] if comp.polymarket_token_id else ''})"
                )
            elif bet_size < CONFIG.min_order_size_usd:
                signal["live_status"] = (
                    f"skipped:bet_below_min(${bet_size:.2f}<${CONFIG.min_order_size_usd:.2f})"
                )
                logger.info(
                    f"Tennis arb: live BUY skipped — bet ${bet_size:.2f} < "
                    f"min ${CONFIG.min_order_size_usd:.2f}"
                )
            elif not comp.polymarket_token_id:
                signal["live_status"] = "skipped:no_token_id"
                logger.warning("Tennis arb: live BUY skipped — empty token_id")
            else:
                from src.copy_trading.daily_spend_guard import can_spend, record_spend
                ok, reason = can_spend(bet_size)
                if not ok:
                    logger.info(f"Tennis arb: live BUY skipped — {reason}")
                    signal["live_status"] = f"skipped:daily_cap({reason})"
                else:
                    from src.tennis.order_placer import place_buy_yes
                    t_order = time.monotonic()
                    live = place_buy_yes(
                        clob_client=self.clob_client,
                        token_id=comp.polymarket_token_id,
                        bet_size_usd=bet_size,
                        ref_price=pm_price,
                    )
                    order_place_s = time.monotonic() - t_order
                    if live and live.get("order_id"):
                        signal["live"] = True
                        signal["live_order_id"] = live["order_id"]
                        signal["live_order_price"] = live["order_price"]
                        signal["live_shares"] = live["shares"]
                        signal["live_status"] = "placed"
                        record_spend(bet_size, source="tennis")
                    else:
                        err = (live or {}).get("error") or "no_order_id_in_response"
                        signal["live_status"] = f"failed:{err}"

            # Paper-book: open / flip-close / hold based on existing position.
            # FLIP closes the existing YES at the implied current PM price for
            # our side (1 - new_signal_price) and opens the new YES position;
            # the realized PnL on the close is attached to the signal so the
            # Telegram alert can surface it.
            if self.paper_book is not None:
                action = self.paper_book.process_signal(signal)
                signal["paper_action"] = action["action"]
                if action.get("realized_pnl_usd") is not None:
                    signal["paper_realized_pnl_usd"] = action["realized_pnl_usd"]
                if action.get("position_id"):
                    signal["paper_position_id"] = action["position_id"]

            # Per-signal latency: from "noticed divergence" to "order placed
            # (or terminal skip reason)". Includes revalidation HTTP, dedupe
            # checks, sizing, daily-spend guard, and the place_buy_yes call.
            # Stored on the signal so it shows up in tennis_trades.jsonl and
            # on the scan-metrics record for aggregate analysis.
            detect_to_order_s = time.monotonic() - t_detect
            latency = {
                "outcome": signal.get("live_status", "unknown"),
                "revalidate_ms": round(revalidate_s * 1000),
                "order_place_ms": round(order_place_s * 1000),
                "detect_to_order_ms": round(detect_to_order_s * 1000),
            }
            signal["latency_ms"] = latency
            signal_latencies.append(latency)

            signals.append(signal)

            # Record in state for future gate checks. Stores both the
            # first-bet anchors (used by the same-side rebet gate to confirm
            # PM didn't drop and sharp moved up vs original entry) and a
            # snapshot of the latest bet for debugging.
            if prev is None:
                first_div = round(edge, 4)
                first_pm = round(pm_price, 4)
                first_sharp = round(comp.sharp_prob, 4)
                first_token = comp.polymarket_token_id
                first_ts = signal["timestamp"]
            else:
                first_div = float(prev.get("first_divergence", prev.get("last_divergence", round(edge, 4))))
                first_pm = float(prev.get("first_pm_price", prev.get("last_pm_price", round(pm_price, 4))))
                first_sharp = float(prev.get("first_sharp_prob", prev.get("last_sharp_prob", round(comp.sharp_prob, 4))))
                first_token = prev.get("first_token_id") or prev.get("last_token_id") or comp.polymarket_token_id
                first_ts = prev.get("first_ts") or prev.get("last_ts") or signal["timestamp"]
            bet_state[state_key] = {
                "first_divergence": first_div,
                "first_pm_price": first_pm,
                "first_sharp_prob": first_sharp,
                "first_token_id": first_token,
                "first_ts": first_ts,
                "last_divergence": round(edge, 4),
                "last_pm_price": round(pm_price, 4),
                "last_sharp_prob": round(comp.sharp_prob, 4),
                "last_token_id": comp.polymarket_token_id,
                "last_bet_size": round(bet_size, 2),
                "last_ts": signal["timestamp"],
                "times_emitted": int(prev.get("times_emitted", 0)) + 1 if prev else 1,
                "question": pm.get("question", ""),
                "event_title": pm.get("event_title", ""),
            }

        if skipped_dedupe:
            logger.info(
                f"Tennis arb: skipped {skipped_dedupe} re-bet(s) — edge did "
                f"not grow by {self.min_edge_step:.0%}"
            )

        metrics["signals_count"] = len(signals)
        metrics["dropped_dedupe"] = skipped_dedupe
        metrics["signal_latencies"] = signal_latencies

        if signals:
            self._save_bet_state(bet_state)

        # Sort by divergence descending
        signals.sort(key=lambda s: s["divergence"], reverse=True)

        if signals:
            logger.info(f"Tennis arb: {len(signals)} signal(s) above "
                        f"{self.min_divergence:.0%} threshold")
            for s in signals:
                logger.info(
                    f"  {s['tournament']}: {s['player_a']} vs {s['player_b']} — "
                    f"Sharp: {s['sharp_prob']:.1%} / PM: {s['polymarket_price']:.1%} — "
                    f"Edge: {s['divergence']:.1%} — {s['side']} @ ${s['bet_size']:.0f}"
                )
        else:
            logger.info("Tennis arb: no signals above threshold")

        # Save signals to history
        self._save_signals(signals)

        # Take-profit events surface alongside divergence signals so the
        # Telegram alert path renders them in the same scan output.
        return tp_events + signals

    def _fetch_polymarket_tennis_markets(self) -> list[dict]:
        """Fetch active tennis match markets from Polymarket Gamma API."""
        all_markets: list[dict] = []
        offset = 0

        while True:
            try:
                self._gamma_calls_in_scan = getattr(self, "_gamma_calls_in_scan", 0) + 1
                resp = requests.get(
                    f"{GAMMA_API_URL}/events",
                    params={
                        "tag_slug": "tennis",
                        "limit": 100,
                        "offset": offset,
                        "active": "true",
                        # Without closed=false, Gamma returns all-time tennis
                        # events (thousands of closed historical markets) and
                        # the currently-live ones (e.g. Monte Carlo final) get
                        # buried past offset=2000.
                        "closed": "false",
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                events = resp.json()

                if not events:
                    break

                for event in events:
                    markets = event.get("markets", [])
                    event_title = event.get("title", "")
                    event_slug = event.get("slug", "")
                    event_end_date = event.get("endDate", "") or event.get("end_date", "")

                    for market in markets:
                        # Gamma's event-level endDate is the tournament's UMA
                        # resolution deadline (often days after the match). The
                        # per-market `gameStartTime` is the actual scheduled
                        # match moment and should be preferred for the
                        # same-event-date guard. Fall back to endDate, then
                        # event endDate, only if gameStartTime is missing.
                        pm_match_time = (
                            market.get("gameStartTime")
                            or market.get("endDate")
                            or event_end_date
                        )
                        # Parse market metadata
                        volume_str = market.get("volume", "0")
                        try:
                            volume = float(volume_str)
                        except (ValueError, TypeError):
                            volume = 0.0

                        liquidity_str = market.get("liquidity", "0")
                        try:
                            liquidity = float(liquidity_str)
                        except (ValueError, TypeError):
                            liquidity = 0.0

                        # Filter by volume and liquidity thresholds
                        if volume < self.min_volume:
                            continue
                        if liquidity < self.min_liquidity:
                            continue

                        # Parse prices
                        prices = market.get("outcomePrices")
                        if isinstance(prices, str):
                            try:
                                prices = json.loads(prices)
                            except (json.JSONDecodeError, TypeError):
                                prices = None

                        yes_price = float(prices[0]) if prices and len(prices) > 0 else None
                        if yes_price is None or yes_price <= 0.01 or yes_price >= 0.99:
                            continue

                        # Parse token IDs
                        token_ids = market.get("clobTokenIds")
                        if isinstance(token_ids, str):
                            try:
                                token_ids = json.loads(token_ids)
                            except (json.JSONDecodeError, TypeError):
                                token_ids = None

                        question = market.get("question", "")
                        player = _extract_player_from_question(question)

                        all_markets.append({
                            "event_title": event_title,
                            "event_slug": event_slug,
                            "event_end_date": event_end_date,
                            "pm_match_time": pm_match_time,
                            "question": question,
                            "player": player,
                            "group_item_title": market.get("groupItemTitle", ""),
                            "yes_price": yes_price,
                            "volume": volume,
                            "liquidity": liquidity,
                            "market_id": market.get("id", ""),
                            "condition_id": market.get("conditionId", ""),
                            "token_id_yes": (
                                token_ids[0] if token_ids and len(token_ids) > 0 else ""
                            ),
                        })

                offset += 100
                if offset > 2000:
                    break
                time.sleep(0.15)

            except requests.RequestException as e:
                logger.error(f"Polymarket tennis fetch failed: {e}")
                break

        return all_markets

    # ------------------------------------------------------------------
    # Take-profit gate
    # ------------------------------------------------------------------
    def _check_take_profit(self, poly_markets: list[dict]) -> list[dict]:
        """Close paper positions whose current price has crossed the TP ratio.

        For each open position we look up the current YES price for its
        token in the freshly-fetched Gamma response. If
        ``current_price >= take_profit_ratio × entry_price`` we close the
        position via ``paper_book.take_profit`` and emit a synthetic
        signal so the Telegram alert path can surface the fix.

        Positions whose token isn't in this scan's ``poly_markets`` (e.g.
        the underlying market dropped below the volume / liquidity filter)
        are skipped — they'll be re-checked on the next scan, and
        resolution will close them eventually.
        """
        if self.paper_book is None or self.take_profit_ratio <= 0:
            return []

        open_positions = self.paper_book.open_positions()
        if not open_positions:
            return []

        # token_id → (current_yes_price, pm_dict)
        price_by_token: dict[str, tuple[float, dict]] = {
            pm["token_id_yes"]: (pm["yes_price"], pm)
            for pm in poly_markets
            if pm.get("token_id_yes")
        }

        events: list[dict] = []
        for pos in open_positions:
            token_id = pos.get("token_id") or ""
            entry_price = float(pos.get("entry_price") or 0.0)
            if not token_id or entry_price <= 0:
                continue
            quote = price_by_token.get(token_id)
            if quote is None:
                continue
            current_price, pm = quote
            # Compare via the ratio so floating-point noise like
            # 3.0 * 0.20 == 0.6000000000000001 doesn't push a clean 3×
            # move just below the threshold.
            ratio_now = current_price / entry_price
            if ratio_now + 1e-9 < self.take_profit_ratio:
                continue

            # Live SELL first if this position was opened live and we're
            # currently in live mode. Failure to submit the SELL doesn't
            # block the paper close — it just gets logged.
            live_sell_id = ""
            live_sell_price = None
            if (
                pos.get("live")
                and not runtime_state.is_preview(3)
                and self.clob_client is not None
            ):
                from src.tennis.order_placer import place_sell_yes
                live = place_sell_yes(
                    clob_client=self.clob_client,
                    token_id=token_id,
                    shares=float(pos.get("shares") or 0.0),
                    ref_price=current_price,
                )
                if live and live.get("order_id"):
                    live_sell_id = live["order_id"]
                    live_sell_price = live["order_price"]

            closed = self.paper_book.take_profit(token_id, exit_price=current_price)
            if closed is None:
                continue

            event_slug = pos.get("event_slug") or pm.get("event_slug") or ""
            polymarket_url = (
                pos.get("polymarket_url")
                or (f"https://polymarket.com/event/{event_slug}" if event_slug else "")
            )
            match = pos.get("match") or ""
            player_a, _, player_b = match.partition(" vs ")
            event = {
                "strategy": "tennis_arb",
                "paper_action": "TAKE_PROFIT",
                "paper_realized_pnl_usd": closed["realized_pnl_usd"],
                "paper_position_id": closed["id"],
                "tournament": pos.get("tournament", ""),
                "player_a": player_a,
                "player_b": player_b,
                "outcome_label": closed.get("outcome_player", ""),
                "target_player": closed.get("outcome_player", ""),
                "event_title": pos.get("event_title", ""),
                "event_slug": event_slug,
                "polymarket_url": polymarket_url,
                "polymarket_question": pm.get("question", ""),
                "match_time": pos.get("match_time"),
                "entry_price": round(entry_price, 4),
                "exit_price": round(current_price, 4),
                "ratio": round(ratio_now, 3),
                "shares": closed.get("shares"),
                "size_usd": closed.get("size_usd"),
                "timestamp": datetime.now(SGT).isoformat(),
                "preview": runtime_state.is_preview(3),
                "live": bool(closed.get("live")),
                "live_sell_order_id": live_sell_id,
                "live_sell_order_price": live_sell_price,
            }
            events.append(event)
            logger.info(
                f"Tennis arb: TAKE_PROFIT {closed['outcome_player']} entry "
                f"{entry_price:.3f} → exit {current_price:.3f} "
                f"(×{event['ratio']}) realized "
                f"${closed['realized_pnl_usd']:+.2f}"
            )

        # Persist TP events to the trade history file too — keeps the
        # JSONL the only source of truth for what the strategy did.
        if events:
            self._save_signals(events)

        return events

    # ------------------------------------------------------------------
    # Paper-book settlement (auto-resolve)
    # ------------------------------------------------------------------
    def _resolve_settled_paper_positions(self, force: bool = False) -> None:
        """Close paper positions whose underlying PM market has resolved.

        For each open-position condition_id, query Gamma for the market's
        current status. If `closed=true` and `outcomePrices` is binary
        (1.0/0.0), we know which side won and can close the position at the
        canonical exit price. Throttled to once per
        `_resolve_min_interval_s` to avoid hammering Gamma — match
        resolution is settled hours after the match ends so polling more
        often than every few minutes is wasted work. ``force=True`` skips
        the throttle (used by the on-demand /tennis_pnl path so the report
        reflects the freshest settlement state).
        """
        if self.paper_book is None:
            return
        condition_ids = self.paper_book.open_position_condition_ids()
        if not condition_ids:
            return

        now = time.time()
        if not force and now - getattr(self, "_last_resolve_at", 0.0) < self._resolve_min_interval_s:
            return
        self._last_resolve_at = now

        for cid in condition_ids:
            try:
                status = self._fetch_market_resolution(cid)
            except Exception as exc:
                logger.debug(f"Tennis arb: resolution fetch failed for {cid[:10]}…: {exc}")
                continue
            if status is None:
                continue
            self.paper_book.resolve(cid, winning_token_id=status)

    def force_resolve_open_positions(self) -> None:
        """Public wrapper that runs the resolve loop bypassing the throttle.

        Wired to /tennis_pnl: each report opportunistically settles any
        markets that closed since the last scheduled resolve tick.
        """
        self._resolve_settled_paper_positions(force=True)

    def _fetch_market_resolution(self, condition_id: str) -> str | None:
        """Look up a single market's resolution state from the CLOB.

        Returns:
          - winning token_id (str) if the market is closed and resolved binary
          - "" (empty string) if voided / non-binary resolution — caller
            treats this as winning_token_id=None and closes positions at
            entry price (zero-PnL settlement)
          - None if the market is still open or unknown — leave positions open

        Why CLOB and not Gamma: Gamma's ``/markets?condition_ids=`` filter
        silently returns ``[]`` for closed/archived markets (the canonical
        param appears to be ``conditionId``, not ``condition_ids``), so the
        resolver never saw any settlement. The CLOB exposes
        ``/markets/{condition_id}`` directly with a ``tokens[]`` array
        whose ``winner`` flag tells us which side resolved 1.0.
        """
        if not condition_id:
            return None
        resp = requests.get(
            f"{CLOB_API_URL}/markets/{condition_id}",
            timeout=15,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        market = resp.json()
        if not isinstance(market, dict):
            return None
        # CLOB also flips ``closed=true`` (sometimes ``archived=true``) once
        # UMA resolution lands. Anything else means "still trading" — leave
        # the position open.
        if not (market.get("closed") or market.get("archived")):
            return None

        tokens = market.get("tokens")
        if not isinstance(tokens, list) or len(tokens) != 2:
            return ""  # closed but non-binary → void-style close

        # ``winner: True`` is the canonical signal. Fall back to ``price``
        # (1.0 vs 0.0) if winner flags aren't populated yet on a freshly
        # closed market.
        for tok in tokens:
            if tok.get("winner") is True:
                tid = tok.get("token_id")
                if tid:
                    return str(tid)

        try:
            prices = [float(t.get("price") or 0.0) for t in tokens]
        except (TypeError, ValueError):
            return ""
        if prices[0] >= 0.99 and prices[1] <= 0.01:
            return str(tokens[0].get("token_id") or "")
        if prices[1] >= 0.99 and prices[0] <= 0.01:
            return str(tokens[1].get("token_id") or "")
        return ""

    def _match_and_compare(
        self, sharp_odds: list[MatchOdds], poly_markets: list[dict]
    ) -> list[tuple[OddsComparison, dict]]:
        """Match sharp odds to Polymarket markets by player name similarity.

        Also enforces a same-event guard: the PM market must reference BOTH
        players from the sharp fixture (rules out outright/tournament-winner
        markets that only name one player), and its event end date must be
        near the sharp match time (rules out same-player future tournaments).

        Returns a list of (OddsComparison, pm_dict) so the caller keeps
        access to event metadata for Telegram / state tracking.
        """
        comparisons: list[tuple[OddsComparison, dict]] = []

        for odds in sharp_odds:
            for pm in poly_markets:
                pm_player = pm.get("player", "")
                if not pm_player:
                    continue

                # Try to match PM player to either side of the sharp odds
                side, sharp_prob = _match_player_to_odds(
                    pm_player, odds.player_a, odds.player_b,
                    odds.implied_prob_a, odds.implied_prob_b
                )

                if side is None:
                    continue

                # Same-event guard: reject outright / future-tournament markets
                ok, reason = _validate_same_event(
                    pm, odds.player_a, odds.player_b,
                    odds.match_time, self.max_event_date_delta_days,
                )
                if not ok:
                    logger.debug(
                        f"Tennis arb: reject {odds.player_a} vs {odds.player_b} "
                        f"→ '{pm.get('question','')}' ({reason})"
                    )
                    continue

                divergence = sharp_prob - pm["yes_price"]

                comp = OddsComparison(
                    match_odds=odds,
                    polymarket_condition_id=pm["condition_id"],
                    polymarket_token_id=pm["token_id_yes"],
                    polymarket_market_id=pm["market_id"],
                    polymarket_question=pm["question"],
                    polymarket_player=pm_player,
                    polymarket_price=pm["yes_price"],
                    sharp_prob=sharp_prob,
                    divergence=divergence,
                    polymarket_volume=pm["volume"],
                    polymarket_liquidity=pm["liquidity"],
                )
                comparisons.append((comp, pm))

        return comparisons

    def _calculate_bet_size(
        self,
        sharp_prob: float,
        market_price: float,
        kelly_fraction: float | None = None,
    ) -> float:
        """Calculate bet size using fractional Kelly criterion.

        Kelly fraction = (bp - q) / b
        where b = (1/price) - 1 (net odds), p = sharp_prob, q = 1 - p

        ``kelly_fraction`` defaults to ``self.kelly_fraction`` (used for the
        first bet). The pyramid-up path passes ``self.second_bet_kelly_fraction``
        so re-bets are sized more conservatively.

        The result is clamped to [min_bet_size, max_bet_size]. If Kelly
        says zero or negative we return 0 (no edge → no bet); but a
        positive Kelly recommendation below the platform minimum is
        rounded up so the order remains fillable.
        """
        if market_price <= 0 or market_price >= 1:
            return 0.0

        b = (1.0 / market_price) - 1.0  # Net payout odds
        p = sharp_prob
        q = 1.0 - p

        kelly = (b * p - q) / b if b > 0 else 0.0

        if kelly <= 0:
            return 0.0

        frac = self.kelly_fraction if kelly_fraction is None else kelly_fraction
        size = kelly * frac * self.max_bet_size
        size = min(size, self.max_bet_size)
        if size < self.min_bet_size:
            size = self.min_bet_size
        return size

    def _bet_state_path(self) -> str:
        return os.path.join(self.data_dir or "", "tennis_bet_state.json")

    def _load_bet_state(self) -> dict:
        """Load persisted per-market last-edge state (for re-bet gate).

        Migrates legacy ``condition_id:token_id`` keys to plain
        ``condition_id`` keys on read so the new gate (which keys by event)
        keeps continuity for in-flight positions after a deploy. The
        last-bet snapshot fields are reused as the first-bet anchors so the
        new gates have a baseline immediately.
        """
        path = self._bet_state_path()
        if not path or not os.path.exists(path):
            return {}
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Could not read tennis bet state: {e}")
            return {}
        if not isinstance(data, dict):
            return {}

        migrated: dict = {}
        for key, val in data.items():
            if not isinstance(val, dict):
                continue
            new_key = key.split(":", 1)[0] if ":" in key else key
            # Use last_price as a fallback for old records that didn't track
            # last_pm_price explicitly.
            last_pm = val.get("last_pm_price", val.get("last_price", 0.0))
            last_sharp = val.get("last_sharp_prob", 0.0)
            last_token = val.get("last_token_id") or (
                key.split(":", 1)[1] if ":" in key else ""
            )
            entry = {
                "first_divergence": val.get("first_divergence", val.get("last_divergence", 0.0)),
                "first_pm_price": val.get("first_pm_price", last_pm),
                "first_sharp_prob": val.get("first_sharp_prob", last_sharp),
                "first_token_id": val.get("first_token_id") or last_token,
                "first_ts": val.get("first_ts") or val.get("last_ts", ""),
                "last_divergence": val.get("last_divergence", 0.0),
                "last_pm_price": last_pm,
                "last_sharp_prob": last_sharp,
                "last_token_id": last_token,
                "last_bet_size": val.get("last_bet_size", 0.0),
                "last_ts": val.get("last_ts", ""),
                "times_emitted": int(val.get("times_emitted") or 0),
                "question": val.get("question", ""),
                "event_title": val.get("event_title", ""),
            }
            # If two legacy keys collide on the same condition_id (one per
            # side), keep the one with the higher times_emitted so the cap
            # stays correct.
            existing = migrated.get(new_key)
            if existing is None or entry["times_emitted"] > existing["times_emitted"]:
                migrated[new_key] = entry
        return migrated

    def _save_bet_state(self, state: dict) -> None:
        if not self.data_dir:
            return
        os.makedirs(self.data_dir, exist_ok=True)
        try:
            with open(self._bet_state_path(), "w") as f:
                json.dump(state, f, indent=2)
        except OSError as e:
            logger.error(f"Failed to save tennis bet state: {e}")

    def _save_signals(self, signals: list[dict]) -> None:
        """Append signals to trade history JSONL file."""
        if not self.data_dir or not signals:
            return

        os.makedirs(self.data_dir, exist_ok=True)
        history_path = os.path.join(self.data_dir, "tennis_trades.jsonl")

        try:
            with open(history_path, "a") as f:
                for s in signals:
                    f.write(json.dumps(s) + "\n")
        except OSError as e:
            logger.error(f"Failed to save tennis signals: {e}")

    def _save_metrics(self, metrics: dict) -> None:
        """Append one scan's timing + call-count metrics to a JSONL file.

        One line per scan, dedicated file so `jq`/`awk` analysis stays simple
        and the regular trade-history JSONL isn't polluted with operational
        telemetry. Best-effort: a write failure is logged but never raised
        so it can't break a scan.
        """
        if not self.data_dir:
            return
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            path = os.path.join(self.data_dir, "tennis_scan_metrics.jsonl")
            with open(path, "a") as f:
                f.write(json.dumps(metrics) + "\n")
        except OSError as e:
            logger.warning(f"Failed to save tennis scan metrics: {e}")


# -- Helpers --


def _surname(name: str) -> str:
    parts = _normalize_name(name).split()
    return parts[-1] if parts else ""


def _validate_same_event(
    pm: dict,
    player_a: str,
    player_b: str,
    match_time: datetime | None,
    max_delta_days: float,
) -> tuple[bool, str]:
    """Reject PM markets that don't clearly describe the same head-to-head
    match as the sharp fixture.

    Checks:
      1. Both player surnames must appear somewhere in the market's question
         or its event title (rules out "Will X win the French Open?" which
         only mentions one player).
      2. If match_time is known, the event endDate must be within
         `max_delta_days` of match_time (rules out future tournaments
         featuring the same player).
    """
    a_last = _surname(player_a)
    b_last = _surname(player_b)
    if not a_last or not b_last:
        return False, "missing_surname"

    haystack = " ".join([
        pm.get("question", "") or "",
        pm.get("event_title", "") or "",
        pm.get("group_item_title", "") or "",
    ]).lower()
    haystack = re.sub(r"[^a-z\s]", " ", haystack)

    if a_last not in haystack or b_last not in haystack:
        return False, f"h2h_missing:need={a_last}+{b_last}"

    # Prefer the per-market `gameStartTime` (the actual match moment) over
    # the event-level `endDate` (which is a UMA resolution deadline usually
    # days later). Falling through event_end_date preserves behavior for any
    # market where gameStartTime isn't populated.
    ref_raw = (pm.get("pm_match_time") or pm.get("event_end_date") or "").strip()
    if match_time is not None and ref_raw:
        try:
            # Gamma sometimes returns "2026-04-12 13:05:00+00" with a space,
            # sometimes strict ISO "2026-04-12T13:05:00Z" — normalize both.
            iso = ref_raw.replace(" ", "T").replace("Z", "+00:00")
            ref = datetime.fromisoformat(iso)
            mt = match_time if match_time.tzinfo else match_time.replace(tzinfo=timezone.utc)
            delta_days = abs((ref - mt).total_seconds()) / 86400.0
            if delta_days > max_delta_days:
                return False, f"date_delta={delta_days:.1f}d"
        except (ValueError, TypeError):
            pass

    return True, "ok"


def _extract_player_from_question(question: str) -> str:
    """Extract player name from Polymarket market question.

    Common patterns:
      - "Will Jannik Sinner win the 2026 ATP Monte-Carlo Masters?"
      - "Sinner vs Rublev: Who will win?"
      - "Jannik Sinner to win ATP Monte Carlo"
    """
    # Pattern: "Will <player> win..."
    m = re.match(r"Will (.+?) win\b", question, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # Pattern: "<player> to win..."
    m = re.match(r"(.+?) to win\b", question, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # Pattern: "<player_a> vs <player_b>"
    m = re.search(r"(.+?)\s+vs\.?\s+(.+?)[\s:?]", question, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    return ""


def _normalize_name(name: str) -> str:
    """Normalize a player name for fuzzy matching."""
    name = name.lower().strip()
    # Remove common prefixes/suffixes
    name = re.sub(r"\b(jr\.?|sr\.?|ii|iii)\b", "", name)
    # Remove non-alpha chars except spaces
    name = re.sub(r"[^a-z\s]", "", name)
    return " ".join(name.split())


def _match_player_to_odds(
    pm_player: str,
    player_a: str,
    player_b: str,
    prob_a: float,
    prob_b: float,
    threshold: float = 0.6,
) -> tuple[str | None, float]:
    """Match a Polymarket player name to one side of the sharp odds.

    Uses fuzzy string matching (SequenceMatcher) on normalized names.
    Also checks if last name alone matches (common for tennis).

    Returns:
        (side, sharp_prob) or (None, 0.0) if no match.
    """
    pm_norm = _normalize_name(pm_player)
    a_norm = _normalize_name(player_a)
    b_norm = _normalize_name(player_b)

    # Full name similarity
    sim_a = SequenceMatcher(None, pm_norm, a_norm).ratio()
    sim_b = SequenceMatcher(None, pm_norm, b_norm).ratio()

    # Last name matching (common in tennis contexts)
    pm_last = pm_norm.split()[-1] if pm_norm.split() else ""
    a_last = a_norm.split()[-1] if a_norm.split() else ""
    b_last = b_norm.split()[-1] if b_norm.split() else ""

    if pm_last and a_last and pm_last == a_last:
        sim_a = max(sim_a, 0.85)
    if pm_last and b_last and pm_last == b_last:
        sim_b = max(sim_b, 0.85)

    # Check if PM player is contained in the sharp player name or vice versa
    if pm_norm in a_norm or a_norm in pm_norm:
        sim_a = max(sim_a, 0.90)
    if pm_norm in b_norm or b_norm in pm_norm:
        sim_b = max(sim_b, 0.90)

    best_sim = max(sim_a, sim_b)
    if best_sim < threshold:
        return None, 0.0

    if sim_a >= sim_b:
        return "A", prob_a
    else:
        return "B", prob_b
