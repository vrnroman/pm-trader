"""One-shot reset of all copy P&L + risk/spend state to zero.

Archives each target file (timestamped copy under ``<data_dir>/archive/``) and
then clears it, across BOTH copy systems, and resets the in-memory state of the
live modules so the running process doesn't immediately re-persist stale
counters over the cleared files.

Open/unredeemed positions are intentionally dropped — the reset means "start
from zero, ignore prior bets". Discovery state + the watchlist, the dedup caches
(``seen-trades.json``, ``watchlist-alerted.json``) and the immutable market
resolution cache are left untouched, so measurement resumes on the same wallets
without re-pinging or re-detecting old trades.

Pure-ish + testable: the file set is derived from an injected ``data_dir`` and
the timestamp is injectable. The in-memory reset is opt-out (``reset_memory``)
so the CLI can run it with the bot stopped without importing the live modules.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.logger import logger

# Ledgers + state files cleared on reset. Both systems' realized/open P&L, the
# audit trail, and the risk/spend counters. Loaders all treat a missing file as
# empty, so we archive-then-delete for a true clean slate.
_LEDGER_NAMES = (
    "realized-pnl.jsonl",      # System A realized
    "trade-history.jsonl",     # System A audit trail
)
_STATE_NAMES = (
    "inventory.json",          # System A open positions (live)
    "preview-inventory.json",  # System A open positions (preview)
    "tiered-risk-state.json",  # per-tier exposure + daily volume
    "risk-state.json",         # global daily volume
    "daily-spend.json",        # daily spend cap
    "trader-counts.json",      # per-trader copy counts
)


@dataclass
class ResetResult:
    archived: list = field(default_factory=list)   # backup paths created
    cleared: list = field(default_factory=list)     # files removed
    skipped: list = field(default_factory=list)     # files that didn't exist

    def summary(self) -> str:
        return (
            f"archived {len(self.archived)}, cleared {len(self.cleared)}, "
            f"skipped {len(self.skipped)}"
        )


def _target_paths(data_dir: str, copy_paper_ledger: Optional[str]) -> list[str]:
    """Absolute paths to every file the reset clears. ``copy_paper_ledger``
    (System B) may live at a custom path, so it's passed in explicitly."""
    paths = [copy_paper_ledger or os.path.join(data_dir, "copy_paper_ledger.jsonl")]
    paths += [os.path.join(data_dir, n) for n in _LEDGER_NAMES]
    paths += [os.path.join(data_dir, n) for n in _STATE_NAMES]
    # de-dupe while preserving order (custom ledger could equal the default)
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        ap = os.path.abspath(p)
        if ap not in seen:
            seen.add(ap)
            out.append(ap)
    return out


def reset_pnl(
    data_dir: str,
    *,
    confirm: bool,
    archive: bool = True,
    now: Optional[datetime] = None,
    copy_paper_ledger: Optional[str] = None,
    reset_memory: bool = True,
) -> ResetResult:
    """Archive + clear all P&L/risk/spend files and (optionally) reset live
    in-memory state. A no-op unless ``confirm`` is True."""
    res = ResetResult()
    if not confirm:
        return res

    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = os.path.join(data_dir, "archive")

    for path in _target_paths(data_dir, copy_paper_ledger):
        if not os.path.exists(path):
            res.skipped.append(path)
            continue
        if archive:
            try:
                os.makedirs(archive_dir, exist_ok=True)
                dst = os.path.join(archive_dir, f"{os.path.basename(path)}.{stamp}")
                shutil.copy2(path, dst)
                res.archived.append(dst)
            except Exception as e:  # noqa: BLE001
                logger.error(f"[reset] archive failed for {path}: {e}")
        try:
            os.remove(path)
            res.cleared.append(path)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[reset] clear failed for {path}: {e}")

    if reset_memory:
        _reset_memory()

    logger.warning(f"[reset] P&L reset complete: {res.summary()}")
    return res


def _reset_memory() -> None:
    """Reset the live modules' in-memory state so a running process doesn't
    re-persist stale counters over the just-cleared files. Best-effort per
    module — a failure in one must not abort the others."""
    targets = (
        ("src.copy_trading.inventory", "reset_state"),
        ("src.copy_trading.risk_manager", "reset_state"),
        ("src.copy_trading.tiered_risk_manager", "reset_state"),
        ("src.copy_trading.daily_spend_guard", "reset_state"),
    )
    import importlib

    for modname, fn in targets:
        try:
            mod = importlib.import_module(modname)
            getattr(mod, fn)()
        except Exception as e:  # noqa: BLE001
            logger.error(f"[reset] in-memory reset failed for {modname}: {e}")
