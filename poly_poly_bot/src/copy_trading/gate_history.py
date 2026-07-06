"""Append-only log of LLM wallet-gate decisions + a summary for ``/gate``.

Why this exists: the gate silently rejected ~93% of candidates for days before a
manual prod-log trawl surfaced it (2026-07-02). One JSON line per gate review
makes the accept/reject mix — and *which theory* each rejected wallet qualified
on — visible on demand instead of buried in the operational log. It is also the
substrate a later gate self-calibration job needs (join these decisions to the
paper-book outcomes of the wallets that got admitted).

Pure and defensive: append/load never raise into the sweep or a command handler.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict


def append(path: str | None, row: dict) -> None:
    """Append one decision row as a JSON line. No-op on missing path / IO error."""
    if not path:
        return
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass


def load(path: str | None, limit: int | None = None) -> list[dict]:
    """Load decision rows (oldest→newest). ``limit`` keeps only the last N."""
    if not path or not os.path.exists(path):
        return []
    rows: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows[-limit:] if limit else rows


def summarize(rows: list[dict]) -> dict:
    """Aggregate rows into admit/reject totals, per-theory admit/reject counts,
    and the most recent rejection reasons.

    A ``requeued`` row is a *provisional* deferral (claude -p was rate-limited when
    the wallet qualified); its real disposition is the later re-check row. Those
    rows are excluded from the admit/reject counts — otherwise a deferred wallet
    would be double-counted as both an admit (the provisional row) and a reject
    (the re-check) and skew the accept rate + any gate calibration. They're
    surfaced separately as ``deferred``."""
    deferred = [r for r in rows if r.get("requeued")]
    decided = [r for r in rows if not r.get("requeued")]
    admitted = [r for r in decided if r.get("admitted")]
    rejected = [r for r in decided if not r.get("admitted")]
    per_theory: dict[str, dict[str, int]] = defaultdict(lambda: {"admit": 0, "reject": 0})
    for r in decided:
        key = "admit" if r.get("admitted") else "reject"
        for t in r.get("theories", []) or []:
            per_theory[t][key] += 1
    recent_rejections = [
        {"wallet": r.get("wallet"), "reasoning": r.get("reasoning"),
         "confidence": r.get("confidence")}
        for r in rejected
    ][-5:]
    # Vetted vs never-vetted admits: "admitted" conflates a real Claude verdict
    # (follow/watch) with fail-open / over-cap / recheck-unavailable admits that
    # nothing actually judged. Split them so the accept mix doesn't read as "all
    # vetted" when a slice was ungated. A row's ``verdict`` string carries the
    # disposition (set by discovery_runner): only follow/watch are true vettings.
    _VETTED_VERDICTS = ("follow", "watch")
    admitted_vetted = [r for r in admitted if r.get("verdict") in _VETTED_VERDICTS]
    admitted_unvetted = [r for r in admitted if r.get("verdict") not in _VETTED_VERDICTS]
    unvetted_by_reason: dict[str, int] = defaultdict(int)
    for r in admitted_unvetted:
        unvetted_by_reason[r.get("verdict") or "unknown"] += 1
    return {
        "total": len(decided),
        "admitted": len(admitted),
        "admitted_vetted": len(admitted_vetted),
        "admitted_unvetted": len(admitted_unvetted),
        "unvetted_by_reason": dict(unvetted_by_reason),
        "rejected": len(rejected),
        "deferred": len(deferred),
        "per_theory": dict(per_theory),
        "recent_rejections": recent_rejections,
    }
