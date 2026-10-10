"""The owner's own picks (2026-10-10): wallets real money follows because the
owner chose them, held to resolution.

Set Z is gate-only by design: nothing can force a wallet in. The owner's
ruling on 2026-10-10 ("put positive wallets, remove negative") rests on a
hold-to-resolution backtest of every followed buy since go-live (10,413
entries, real slippage, 2% fee): the picks' entries made money held to the
end, while their own quick exits (several are "scalpers", benched as
uncopyable at our latency) are exactly what we cannot copy. So a pick:

- counts as a member of set Z, tier 1b, unless evicted (an eviction still
  wins: the probation and decay rails keep their say);
- is never benched by the form rail;
- has its SELLs ignored and skips the flip gate: we hold its entries to
  resolution instead of chasing exits we arrive late for.

The list lives in deploy.yml (LIVE_HOLD_WALLETS), version-controlled, so the
decision has a commit and a reason. A leaf module: config only.
"""
from __future__ import annotations

import re

from src.config import CONFIG

_ADDR = re.compile(r"^0x[0-9a-f]{40}$")
TIER = "1b"


def hold_wallets() -> set:
    raw = str(getattr(CONFIG, "live_hold_wallets", "") or "")
    return {w.strip().lower() for w in raw.split(",") if _ADDR.match(w.strip().lower())}


def is_pick(wallet: str) -> bool:
    return (wallet or "").lower() in hold_wallets()


WHY = "owner pick (LIVE_HOLD_WALLETS): entries copied, held to resolution"
