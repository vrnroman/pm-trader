"""Tiered risk manager for 1a/1b/1c strategy tiers.

Each tier has independent exposure tracking with its own limits.
Sizing algorithm:
  1. raw_size = trader_bet * COPY_PERCENTAGE / 100
  2. size = max(raw_size, MIN_BET)
  3. size = min(size, MAX_BET)
  4. remaining = MAX_TOTAL_EXPOSURE - current_open_total
  5. if size > remaining: size = remaining
  6. if size < MIN_BET: SKIP

State persisted to data/tiered-risk-state.json with atomic writes.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.config import CONFIG
from src.copy_trading.daily_spend_guard import can_spend
from src.copy_trading.strategy_config import (
    StrategyTier,
    TierConfig,
    get_tier_config,
)
from src.logger import logger
from src.models import DetectedTrade, TieredCopyDecision
from src.utils import round_cents, today_utc


# ---------------------------------------------------------------------------
# Tier exposure tracking
# ---------------------------------------------------------------------------

@dataclass
class TierExposure:
    """Per-tier open exposure and daily volume tracking.

    ``placements`` names what the exposure is made of: one row per live
    copy (token id, cost, when). ``open_total`` is their sum. Before this
    the total was a running sum that nothing ever released (the release
    function had no caller), so eleven $6 copies filled a $64 cap and every
    copy from 2026-09-08 on was refused as "exposure full" while the
    positions had long resolved and paid out.
    """

    open_total: float = 0.0
    daily_date: str = ""
    daily_volume: float = 0.0
    placements: list = field(default_factory=list)

    def recount(self) -> None:
        self.open_total = round(sum(float(p.get("cost") or 0.0) for p in self.placements), 2)


_tier_exposures: dict[str, TierExposure] = {
    "1a": TierExposure(),
    "1b": TierExposure(),
    "1c": TierExposure(),
}

_STATE_FILE = os.path.join(CONFIG.data_dir, "tiered-risk-state.json")


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _atomic_write_json(path: str, data: dict) -> None:
    """Write JSON atomically: write to tmp file then rename."""
    dir_path = os.path.dirname(path)
    os.makedirs(dir_path, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _load_state() -> None:
    """Load tiered risk state from disk."""
    global _tier_exposures
    try:
        with open(_STATE_FILE, "r") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return

    today = today_utc()
    for tier_key in ("1a", "1b", "1c"):
        tier_data = raw.get(tier_key, {})
        exp = _tier_exposures[tier_key]
        exp.daily_date = tier_data.get("daily_date", "")
        exp.daily_volume = float(tier_data.get("daily_volume", 0))
        rows = tier_data.get("placements")
        exp.placements = [dict(r) for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
        if rows is None:
            # Legacy state: a running total with no rows behind it. Nothing
            # can say what it is made of, so it is not evidence of exposure;
            # the next reconcile against the wallet's positions rebuilds it.
            legacy = float(tier_data.get("open_total", 0) or 0)
            if legacy:
                logger.warn(f"[tiered-risk] tier {tier_key} carried a legacy open total "
                            f"${legacy:.2f} with no placements behind it: dropped")
        exp.recount()
        # Reset daily volume on new day
        if exp.daily_date != today:
            exp.daily_volume = 0.0
            exp.daily_date = today


def _save_state() -> None:
    """Persist tiered risk state to disk."""
    data: dict = {}
    for tier_key in ("1a", "1b", "1c"):
        exp = _tier_exposures[tier_key]
        data[tier_key] = {
            "open_total": exp.open_total,
            "daily_date": exp.daily_date,
            "daily_volume": exp.daily_volume,
            "placements": list(exp.placements),
        }
    _atomic_write_json(_STATE_FILE, data)


# Load on import
_load_state()


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def _evaluate_tiered_trade_with_state(
    trade: DetectedTrade,
    tier: StrategyTier,
    exposure: TierExposure,
    cfg: TierConfig,
) -> TieredCopyDecision:
    """Evaluate a trade against tiered risk rules.

    Checks (in order):
    1. NaN guard
    2. Trade age
    3. Min trader bet
    4. Price bounds (min_price, max_price)
    5. Sizing algorithm
    6. Alert-only mode (1c)
    """

    def skip(reason: str) -> TieredCopyDecision:
        return TieredCopyDecision(
            should_copy=False,
            copy_size=0,
            tier=tier,
            alert_only=cfg.alert_only,
            reason=reason,
        )

    # 1. NaN guard
    if math.isnan(trade.price) or math.isnan(trade.size):
        return skip("NaN price or size")

    # 2. Trade age
    try:
        trade_ts = datetime.fromisoformat(trade.timestamp.replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - trade_ts).total_seconds() / 3600
        if age_hours > CONFIG.max_trade_age_hours:
            return skip(f"Trade too old: {age_hours:.1f}h > {CONFIG.max_trade_age_hours}h")
    except (ValueError, TypeError):
        pass

    # 3. Min trader bet, ENTRIES ONLY.
    # The threshold says which of the target's BUYS are worth copying. Applying
    # it to their SELLS gated our own exits behind the size of their exit, so a
    # target trimming $150 of a position we hold left us holding it. Book B,
    # whose record is the evidence for going live, mirrors exits from $100 and
    # takes its edge there; an entry filter must not quietly switch that off.
    if (trade.side == "BUY" and cfg.min_trader_bet > 0
            and trade.size < cfg.min_trader_bet):
        return skip(
            f"Trader bet ${trade.size:.2f} < min_trader_bet ${cfg.min_trader_bet:.2f} for tier {tier}"
        )

    # 4. Price bounds
    if trade.price < cfg.min_price:
        return skip(f"Price {trade.price:.4f} < tier {tier} min {cfg.min_price}")
    if trade.price > cfg.max_price:
        return skip(f"Price {trade.price:.4f} > tier {tier} max {cfg.max_price}")

    # 5. Sizing algorithm
    #    Step 1: raw_size = trader_bet * COPY_PERCENTAGE / 100
    raw_size = trade.size * cfg.copy_percentage / 100.0

    #    Step 2: size = max(raw_size, MIN_BET)
    size = max(raw_size, cfg.min_bet)

    #    Step 3: size = min(size, MAX_BET)
    size = min(size, cfg.max_bet)

    #    Step 4: remaining = MAX_TOTAL_EXPOSURE - current_open_total
    remaining = cfg.max_total_exposure - exposure.open_total

    #    Step 5: if size > remaining: size = remaining
    if size > remaining:
        size = remaining

    #    Step 6: if size < MIN_BET: SKIP
    if size < cfg.min_bet:
        return skip(
            f"Tier {tier} exposure full: remaining=${remaining:.2f} < min_bet=${cfg.min_bet:.2f}"
        )

    size = round_cents(size)

    # Global daily-spend cap (BUY only; SELLs are exits, not new exposure)
    if trade.side == "BUY":
        ok, reason = can_spend(size)
        if not ok:
            return skip(reason)

    # 6. Alert-only mode (1c tier)
    if cfg.alert_only:
        return TieredCopyDecision(
            should_copy=False,
            copy_size=size,
            tier=tier,
            alert_only=True,
            reason=f"Alert-only mode for tier {tier} (would copy ${size:.2f})",
        )

    return TieredCopyDecision(
        should_copy=True,
        copy_size=size,
        tier=tier,
        alert_only=False,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_tiered_trade(
    trade: DetectedTrade,
    tier: StrategyTier,
) -> TieredCopyDecision:
    """Evaluate a trade for a specific tier using global state."""
    _load_state()
    cfg = get_tier_config(tier)
    if not cfg.enabled:
        return TieredCopyDecision(
            should_copy=False,
            copy_size=0,
            tier=tier,
            alert_only=False,
            reason=f"Tier {tier} is disabled",
        )
    # The bankroll governor: the tier's caps lowered to fractions of the money
    # that is actually there, and the copy trigger aligned to the evidence
    # base. Closed (live, no budget) means refused with the reason, not sized
    # on caps written for a bankroll that does not exist.
    from src.copy_trading import live_budget
    cfg, closed = live_budget.govern_tier(cfg)
    if closed:
        return TieredCopyDecision(
            should_copy=False,
            copy_size=0,
            tier=tier,
            alert_only=False,
            reason=closed,
        )
    exposure = _tier_exposures.get(tier, TierExposure())
    return _evaluate_tiered_trade_with_state(trade, tier, exposure, cfg)


def record_tiered_placement(tier: StrategyTier, copy_size: float,
                            token_id: Optional[str] = None,
                            now: Optional[float] = None) -> None:
    """Record a placed trade for a tier (increases open exposure and daily volume)."""
    import time as _time
    exp = _tier_exposures.get(tier)
    if exp is None:
        logger.warn(f"[tiered-risk] Unknown tier: {tier}")
        return

    today = today_utc()
    if exp.daily_date != today:
        exp.daily_volume = 0.0
        exp.daily_date = today

    exp.placements.append({"token_id": str(token_id or ""), "cost": round(float(copy_size), 2),
                           "ts": float(now if now is not None else _time.time())})
    exp.recount()
    exp.daily_volume += copy_size
    _save_state()
    logger.info(
        f"[tiered-risk] Recorded tier {tier} placement: ${copy_size:.2f} | "
        f"open: ${exp.open_total:.2f} / ${get_tier_config(tier).max_total_exposure:.2f}"
    )


def release_tiered_exposure(tier: StrategyTier, amount: float) -> None:
    """Release exposure when a position is closed or settled.

    Args:
        tier: Which tier to release from.
        amount: USD amount to release (positive).
    """
    exp = _tier_exposures.get(tier)
    if exp is None:
        logger.warn(f"[tiered-risk] Unknown tier for release: {tier}")
        return

    # Release the oldest rows first, up to the amount.
    left = float(amount)
    kept = []
    for row in exp.placements:
        c = float(row.get("cost") or 0.0)
        if left <= 0:
            kept.append(row)
        elif c <= left + 1e-9:
            left -= c
        else:
            kept.append({**row, "cost": round(c - left, 2)})
            left = 0.0
    exp.placements = kept
    exp.recount()
    _save_state()
    logger.info(
        f"[tiered-risk] Released tier {tier} exposure: ${amount:.2f} | "
        f"open now: ${exp.open_total:.2f}"
    )


# A copy placed less than this long ago may not be in the synced inventory
# yet; it is never dropped for being absent from it.
RECONCILE_GRACE_S = 3600.0


def reconcile_tiered_exposure(*, resolved_tokens: set, live_tokens: Optional[set],
                              now: Optional[float] = None) -> dict:
    """Drop placements whose position has resolved (paid out or lost) or has
    left the wallet, so exposure is what is actually open.

    ``resolved_tokens``: token ids the chain has resolved (the redeemer's
    list). ``live_tokens``: token ids the synced inventory still holds with
    shares, or None when the inventory is not known this pass (then only
    the resolved set releases). Returns {tier: released_usd} for the log.
    """
    import time as _time
    now = float(now if now is not None else _time.time())
    resolved = {str(t) for t in (resolved_tokens or set())}
    live = {str(t) for t in live_tokens} if live_tokens is not None else None
    released: dict[str, float] = {}
    changed = False
    for tier_key, exp in _tier_exposures.items():
        kept = []
        for row in exp.placements:
            tok = str(row.get("token_id") or "")
            age = now - float(row.get("ts") or now)
            gone = bool(tok) and (tok in resolved
                                  or (live is not None and tok not in live
                                      and age > RECONCILE_GRACE_S))
            if gone:
                released[tier_key] = round(released.get(tier_key, 0.0)
                                           + float(row.get("cost") or 0.0), 2)
                changed = True
            else:
                kept.append(row)
        exp.placements = kept
        exp.recount()
    if changed:
        _save_state()
        for tier_key, amt in released.items():
            logger.info(f"[tiered-risk] tier {tier_key}: released ${amt:.2f} of exposure "
                        f"from resolved or closed positions | open now: "
                        f"${_tier_exposures[tier_key].open_total:.2f}")
    return released


def reset_state() -> None:
    """Reset every tier's open exposure + daily volume to zero (paired with a
    P&L reset). Does not write disk — the reset routine clears the state file."""
    for tier_key in _tier_exposures:
        _tier_exposures[tier_key] = TierExposure()


def get_tiered_risk_status() -> dict:
    """Return current tiered risk state summary for Telegram status commands."""
    _load_state()
    result: dict = {}
    for tier_key in ("1a", "1b", "1c"):
        exp = _tier_exposures[tier_key]
        try:
            cfg = get_tier_config(tier_key)  # type: ignore[arg-type]
            max_exposure = cfg.max_total_exposure
            enabled = cfg.enabled
        except ValueError:
            max_exposure = 0
            enabled = False
        result[tier_key] = {
            "enabled": enabled,
            "open_total": round_cents(exp.open_total),
            "max_total_exposure": max_exposure,
            "daily_volume": round_cents(exp.daily_volume),
            "daily_date": exp.daily_date,
        }
    return result
