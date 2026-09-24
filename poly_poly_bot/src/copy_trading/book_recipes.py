"""The paper books' recipes, in one place.

Book B's knobs used to live only inside ``main.py``'s B loop. The analyst's
experiments (s-ye5990) run a CONTROL that must be this book to the letter,
so the knobs are a function of the config here and ``main.py`` spreads it.
The callables (detector factories, blacklist, on_cycle, observer) stay with
the caller: they are the process, not the recipe.

``KNOBS`` names the recipe entries an experiment card may override, with the
type the value must have; anything else on a card is refused before it
runs. A leaf module: config and os only.
"""
from __future__ import annotations

import os
from typing import Any

from src.config import CONFIG


def _cap(v):
    return v if v and v > 0 else None


def book_b_kwargs(cfg=CONFIG) -> dict[str, Any]:
    """Book B: instant copies at the target's price, no fill-gate censoring,
    A's caps and evidence gates, its own ledger and era file."""
    return dict(
        ledger_path=cfg.copy_paper_b_ledger,
        watchlist_path=cfg.copy_paper_watchlist,
        extra_watchlist_paths=[cfg.copy_paper_b_extra_watchlist],
        max_copy_usd=cfg.copy_paper_max_usd,
        copy_pct=cfg.copy_paper_copy_pct,
        max_slippage_bps=cfg.copy_paper_max_slippage_bps,
        max_age_s=cfg.copy_paper_max_age_s,
        min_usd=cfg.copy_paper_min_usd,
        cycle_interval_s=cfg.copy_paper_interval_s,
        # B's thesis: NO fill-gate censoring; fills at the target's own price.
        fill_gate_bps=None,
        fill_at_their_price_bps=cfg.copy_paper_b_slippage_bps,
        first_entry_only=cfg.copy_paper_first_entry_only,
        max_copies_per_wallet_day=_cap(cfg.copy_paper_b_max_per_wallet_day),
        max_copies_per_category_day=_cap(cfg.copy_paper_b_max_per_category_day),
        # same event cap + stake tiering as A (identical across books, so the
        # race variable stays lagged-vs-instant).
        max_copies_per_wallet_event=_cap(cfg.copy_paper_b_max_per_wallet_event),
        low_conf_stake_frac=cfg.copy_paper_low_conf_stake_frac,
        low_conf_until_n=cfg.copy_paper_low_conf_until_n,
        gate_history_path=os.path.join(
            # SAME derivation as the writer (discovery_runner puts gate-history
            # beside the discovery state file); deriving from data_dir instead
            # would silently read a never-written path if the state file is
            # relocated, disabling the stake tiering with no warning.
            os.path.dirname(cfg.wallet_discovery_state), "gate-history.jsonl"),
        starved_priority=cfg.copy_paper_starved_priority,
        relief_evidence_n=None,   # caps already sized for take-all; no relief lane
        relief_max_per_category_day=None,
        category_gate=cfg.copy_paper_category_gate,
        # P1-6 book-evidence gates + P1-7 modeled costs, identical to A's, so
        # the race variable stays lagged-vs-instant. B's own ledger feeds its
        # evidence gates.
        category_evidence_min_n=_cap(cfg.copy_paper_category_evidence_min_n),
        category_evidence_era_only=cfg.copy_paper_category_evidence_era_only,
        era_state_path=os.path.join(cfg.data_dir, "ab_race_state.json"),
        costs_enabled=cfg.copy_paper_costs_enabled,
        gas_usd_per_trade=cfg.copy_paper_gas_usd,
        trade_fee_bps=cfg.copy_paper_trade_fee_bps,
        conviction_base_usd=(cfg.copy_paper_conviction_base_usd
                             if cfg.copy_paper_conviction_base_usd > 0 else None),
        conviction_min=cfg.copy_paper_conviction_min,
        conviction_max=cfg.copy_paper_conviction_max,
        max_horizon_days=(cfg.strategy_4_long_horizon_days
                          if cfg.strategy_4_enabled else None),
        strategy="B",
    )


# What an experiment card may change on top of book B: name -> type. Paths,
# the strategy tag and the callables are never knobs.
KNOBS: dict[str, type] = {
    "min_usd": float,
    "max_copy_usd": float,
    "copy_pct": float,
    "max_age_s": float,
    "fill_at_their_price_bps": int,
    "first_entry_only": bool,
    "max_copies_per_wallet_day": int,
    "max_copies_per_category_day": int,
    "max_copies_per_wallet_event": int,
    "low_conf_stake_frac": float,
    "low_conf_until_n": int,
    "category_gate": bool,
    "category_evidence_min_n": int,
    "category_evidence_era_only": bool,
    "conviction_base_usd": float,
    "conviction_min": float,
    "conviction_max": float,
    "starved_priority": bool,
    "min_horizon_days": float,
    "max_horizon_days": float,
    "costs_enabled": bool,
}

# The env name the owner would set in deploy.yml to make a winning knob the
# bot's own; printed in the PR body, never written by the analyst.
KNOB_ENV: dict[str, str] = {
    "min_usd": "COPY_PAPER_MIN_USD",
    "max_copy_usd": "COPY_PAPER_MAX_USD",
    "copy_pct": "COPY_PAPER_COPY_PCT",
    "max_age_s": "COPY_PAPER_MAX_AGE_S",
    "fill_at_their_price_bps": "COPY_PAPER_B_SLIPPAGE_BPS",
    "first_entry_only": "COPY_PAPER_FIRST_ENTRY_ONLY",
    "max_copies_per_wallet_day": "COPY_PAPER_B_MAX_PER_WALLET_DAY",
    "max_copies_per_category_day": "COPY_PAPER_B_MAX_PER_CATEGORY_DAY",
    "max_copies_per_wallet_event": "COPY_PAPER_B_MAX_PER_WALLET_EVENT",
    "low_conf_stake_frac": "COPY_PAPER_LOW_CONF_STAKE_FRAC",
    "low_conf_until_n": "COPY_PAPER_LOW_CONF_UNTIL_N",
    "category_gate": "COPY_PAPER_CATEGORY_GATE",
    "category_evidence_min_n": "COPY_PAPER_CATEGORY_EVIDENCE_MIN_N",
    "category_evidence_era_only": "COPY_PAPER_CATEGORY_EVIDENCE_ERA_ONLY",
    "conviction_base_usd": "COPY_PAPER_CONVICTION_BASE_USD",
    "conviction_min": "COPY_PAPER_CONVICTION_MIN",
    "conviction_max": "COPY_PAPER_CONVICTION_MAX",
    "starved_priority": "COPY_PAPER_STARVED_PRIORITY",
    "costs_enabled": "COPY_PAPER_COSTS_ENABLED",
}


def coerce_knobs(knobs: dict) -> tuple[dict, str]:
    """``(typed knobs, "")`` or ``({}, why)``. Unknown names and wrong types
    are refused whole: a card is all right or not run."""
    out: dict = {}
    for k, v in (knobs or {}).items():
        t = KNOBS.get(str(k))
        if t is None:
            return ({}, f"{k} is not a knob an experiment may change")
        try:
            if t is bool:
                out[k] = as_bool(v)
            else:
                out[k] = t(v)
        except (TypeError, ValueError):
            return ({}, f"{k}: {v!r} is not a {t.__name__}")
        if str(k).startswith("max_copies_") and out[k] <= 0:
            # In the recipe 0 means "cap off" (_cap); on a card it would
            # mean a treatment that opens nothing, which is not an
            # experiment. Off is not a knob.
            return ({}, f"{k}: {out[k]} is not a cap; caps on a card are 1 or more")
    return (out, "")


def as_bool(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)
