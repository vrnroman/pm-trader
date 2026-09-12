"""The presence grammar: which log lines are important. A leaf module on
purpose: ``src.logger`` builds the important-lines file handler from it at
import time, so it must not import the logger back (that circular import
swallowed the handler and the file was never written; verifier s-g8int5 r1).
"""
from __future__ import annotations

import re

IMPORTANT_PATTERNS = [
    r"\[LIVE\]", r"\[verify\] (FILLED|UNFILLED|PARTIAL)", r"\[recovery\]",
    r"\[live\] (ARMED|DISARMED|HARD DISARM|disarm)", r"DISARMED",
    r"\[guard\] (cancelled|could not|pass failed|disarm|exposure reconcile failed)",
    r"Self-disarmed", r"\[tiered-risk\] .*(released|Recorded|carried a legacy|unreadable)",
    r"exposure full", r"\[daily-cap\]", r"spend guard closed", r"cash on chain",
    r"\[zset\] (EVICTED|ADMITTED|admitted)", r"\[ops\]", r"\[disk-watch\] (TRIPPED|still)",
    r"\[redeemer\] .*(ERROR|cannot|winner)", r"SEND FAILED", r"real-money line",
    r"Traceback", r"\bERROR\b", r"\bCRITICAL\b", r"Bot started", r"shutting down",
    r"pending orders file unreadable", r"\[testorder\]", r"Test order",
]
_IMPORTANT_RE = re.compile("|".join(f"(?:{p})" for p in IMPORTANT_PATTERNS))


def is_important(line: str) -> bool:
    """The deterministic split: no model, one regex, the same one everywhere."""
    return bool(_IMPORTANT_RE.search(line or ""))
