#!/usr/bin/env python3
"""Print the ops digest: the important log lines of the last N hours, the
money state, the arm, set Z, the tier ledger, the ledger tail. Runs on the
VM inside the container (``python scripts/ops_digest.py --hours 24``) and is
what the hourly digest workflow commits to the ops-digest branch, and what
the cloud routine reads. Deterministic: no model, one regex (ops_watch)."""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import CONFIG  # noqa: E402
from src.copy_trading import ops_watch  # noqa: E402


def _read(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def important_lines(logs_dir: str, hours: float, now: float) -> list[str]:
    since = datetime.fromtimestamp(now - hours * 3600, tz=timezone.utc)
    out: list[str] = []
    files = sorted(glob.glob(os.path.join(logs_dir, "bot-*.log")) + glob.glob(os.path.join(logs_dir, "signals-*.log")))
    for path in files:
        day = os.path.basename(path)[len(os.path.basename(path).split("-")[0]) + 1:-4]
        if day < since.strftime("%Y-%m-%d"):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line[:10] >= since.strftime("%Y-%m-%d") and ops_watch.is_important(line):
                        if line[:19] >= since.strftime("%Y-%m-%d %H:%M:%S"):
                            out.append(line.rstrip("\n"))
        except OSError:
            continue
    seen = set(); dedup = []
    for l in out:
        if l not in seen:
            seen.add(l); dedup.append(l)
    return dedup


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--json", action="store_true", help="machine shape (state.json)")
    a = ap.parse_args()
    now = time.time()
    d = CONFIG.data_dir
    logs = os.environ.get("LOGS_DIR", "logs")
    state = {
        "generated": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        "money": _read(os.path.join(d, ops_watch.MONEY_STATE_FILE)),
        "arm": _read(os.path.join(d, "live_arm.json")),
        "spend": _read(os.path.join(d, "daily-spend.json")),
        "tier": _read(os.path.join(d, "tiered-risk-state.json")),
        "zset": _read(os.path.join(d, "promoted_wallets_z.json")),
        "watch": _read(os.path.join(d, ops_watch.STATE_FILE)),
        "probation": _read(os.path.join(d, ops_watch.PROBATION_FILE)),
        "ledger_tail": ops_watch.ledger_rows(since_ts=now - a.hours * 3600)[-200:],
        "important": important_lines(logs, a.hours, now)[-400:],
    }
    # Sentinels: gcloud's SSH wrapper writes key-generation chatter around the
    # payload the first time a runner connects; the workflow cuts to these.
    print("@@OPS_DIGEST_BEGIN@@")
    if a.json:
        print(json.dumps(state, ensure_ascii=False, indent=1))
        print("@@OPS_DIGEST_END@@")
        return 0
    m = state["money"] or {}
    print(f"# ops digest {state['generated']} (last {a.hours:.0f}h)")
    print()
    print("## money state")
    print(json.dumps(m, ensure_ascii=False))
    print()
    print(f"## arm: {json.dumps(state['arm'])}")
    print(f"## spend today: {json.dumps(state['spend'])}")
    print(f"## set Z: {json.dumps(state['zset'])}")
    print(f"## tier exposure: {json.dumps({k: (v.get('open_total'), len(v.get('placements') or [])) for k, v in (state['tier'] or {}).items()})}")
    print(f"## probation: {json.dumps(state['probation'])}")
    print()
    print(f"## ledger ({len(state['ledger_tail'])} rows)")
    for r in state["ledger_tail"]:
        print(json.dumps(r, ensure_ascii=False))
    print()
    print(f"## important lines ({len(state['important'])})")
    for l in state["important"]:
        print(l)
    print("@@OPS_DIGEST_END@@")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
