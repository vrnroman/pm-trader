#!/usr/bin/env python3
"""Selectively reset the System-B paper-copy book — keep net-positive wallets.

Restarts the copy-following paper ledger from zero EXCEPT for wallets that are
currently net-positive (those keep their full history + settled-deal count). The
original ledger is archived to ``data/archive/`` first. System A, Strategy-4, and
the discovery watchlist/state are NOT touched.

Run with the bot STOPPED so the running process can't re-persist its in-memory
ledger over the rewritten file:

    # on the VM, over IAP SSH (one-off container):
    docker stop poly-poly-bot
    docker run --rm -v /home/tianyuezhou/app/data:/app/data --entrypoint python \\
      asia-northeast1-docker.pkg.dev/roman-vm/poly-poly-bot/poly-poly-bot:latest \\
      -m scripts.reset_paper_selective --confirm
    docker start poly-poly-bot

Usage:
    python -m scripts.reset_paper_selective            # dry run (counts only)
    python -m scripts.reset_paper_selective --confirm  # archive + rewrite
    python -m scripts.reset_paper_selective --confirm --no-archive
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import CONFIG  # noqa: E402
from src.copy_trading.reset_pnl import selective_reset_system_b  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Reset the System-B paper book to zero, keeping net-positive wallets.")
    ap.add_argument("--confirm", action="store_true",
                    help="actually rewrite the ledger (without it, this is a dry run)")
    ap.add_argument("--no-archive", action="store_true",
                    help="skip the timestamped backup (still rewrites)")
    args = ap.parse_args()

    res = selective_reset_system_b(
        CONFIG.copy_paper_ledger,
        confirm=args.confirm,
        archive=not args.no_archive,
    )
    if not args.confirm:
        print("DRY RUN — would keep net-positive wallets, drop the rest:")
        print(f"  ledger: {CONFIG.copy_paper_ledger}")
        print(f"  {res.summary()}")
        if res.kept_wallets:
            print("  keeping: " + ", ".join(res.kept_wallets))
        print("\nPass --confirm to apply (run with the bot stopped).")
        return 0

    print(f"Selective reset complete: {res.summary()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
