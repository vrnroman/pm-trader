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


def _target_paths(
    data_dir: str,
    copy_paper_ledger: Optional[str],
    s4_paper_ledger: Optional[str] = None,
) -> list[str]:
    """Absolute paths to every file the reset clears. ``copy_paper_ledger``
    (System B) and ``s4_paper_ledger`` (the long-horizon book) may live at custom
    paths, so they're passed in explicitly."""
    paths = [copy_paper_ledger or os.path.join(data_dir, "copy_paper_ledger.jsonl")]
    paths += [s4_paper_ledger or os.path.join(data_dir, "s4_paper_ledger.jsonl")]
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
    s4_paper_ledger: Optional[str] = None,
    reset_memory: bool = True,
) -> ResetResult:
    """Archive + clear all P&L/risk/spend files and (optionally) reset live
    in-memory state. A no-op unless ``confirm`` is True."""
    res = ResetResult()
    if not confirm:
        return res

    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = os.path.join(data_dir, "archive")

    for path in _target_paths(data_dir, copy_paper_ledger, s4_paper_ledger):
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


@dataclass
class SelectiveResetResult:
    kept_wallets: list = field(default_factory=list)    # net-positive wallets retained
    kept_rows: int = 0                                  # positions retained
    dropped_rows: int = 0                               # positions wiped (incl. dust)
    archived: str = ""                                  # backup path (or "")
    applied: bool = False                               # False on dry-run / missing file

    def summary(self) -> str:
        return (
            f"kept {self.kept_rows} rows across {len(self.kept_wallets)} positive "
            f"wallet(s), dropped {self.dropped_rows} rows"
            + (f", archived -> {self.archived}" if self.archived else "")
        )


def selective_reset_system_b(
    copy_paper_ledger: str,
    *,
    confirm: bool,
    archive: bool = True,
    keep_positive: bool = True,
    now: Optional[datetime] = None,
) -> SelectiveResetResult:
    """Restart the System-B paper book from zero, KEEPING net-positive wallets.

    For every wallet in ``copy_paper_ledger``, sum realized P&L over its *closed*
    positions (dust fills excluded). Wallets with net realized P&L > 0 keep ALL
    their rows (open + closed) so their track record and settled-deal count carry
    forward; every other wallet's rows are dropped so it starts from zero. Dust
    fills are dropped regardless. The original ledger is archived first.

    Run with the bot STOPPED — the live runner holds the ledger in memory and
    would re-persist it over the cleared file. A no-op unless ``confirm`` (a
    dry-run still reports the kept/dropped counts).
    """
    from src.copy_trading.copy_paper import PaperCopyLedger, is_dust_fill

    res = SelectiveResetResult()
    if not os.path.exists(copy_paper_ledger):
        return res

    ledger = PaperCopyLedger(copy_paper_ledger)
    positions = list(ledger.positions.values())

    net: dict[str, float] = {}
    for p in positions:
        if is_dust_fill(p) or not p.closed:
            continue
        w = (p.target or "").lower()
        net[w] = net.get(w, 0.0) + p.pnl
    keep_wallets = {w for w, v in net.items() if v > 0} if keep_positive else set()

    kept = [p for p in positions
            if not is_dust_fill(p) and (p.target or "").lower() in keep_wallets]
    res.kept_wallets = sorted(keep_wallets)
    res.kept_rows = len(kept)
    res.dropped_rows = len(positions) - len(kept)

    if not confirm:
        return res  # dry-run: counts only, no file changes

    if archive:
        stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
        archive_dir = os.path.join(os.path.dirname(copy_paper_ledger) or ".", "archive")
        try:
            os.makedirs(archive_dir, exist_ok=True)
            dst = os.path.join(archive_dir,
                               f"{os.path.basename(copy_paper_ledger)}.{stamp}")
            shutil.copy2(copy_paper_ledger, dst)
            res.archived = dst
        except Exception as e:  # noqa: BLE001
            logger.error(f"[reset] selective archive failed: {e}")

    ledger.positions = {p.copy_id: p for p in kept}
    ledger.save()
    res.applied = True
    logger.warning(f"[reset] selective System-B reset complete: {res.summary()}")
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
