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
    and the most recent rejection reasons."""
    admitted = [r for r in rows if r.get("admitted")]
    rejected = [r for r in rows if not r.get("admitted")]
    per_theory: dict[str, dict[str, int]] = defaultdict(lambda: {"admit": 0, "reject": 0})
    for r in rows:
        key = "admit" if r.get("admitted") else "reject"
        for t in r.get("theories", []) or []:
            per_theory[t][key] += 1
    recent_rejections = [
        {"wallet": r.get("wallet"), "reasoning": r.get("reasoning"),
         "confidence": r.get("confidence")}
        for r in rejected
    ][-5:]
    return {
        "total": len(rows),
        "admitted": len(admitted),
        "rejected": len(rejected),
        "per_theory": dict(per_theory),
        "recent_rejections": recent_rejections,
    }
