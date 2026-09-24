"""Experiment flags: the switch a code-change experiment sits behind.

An experiment that needs new code (s-ye5990) runs a CONTROL and a TREATMENT
paper book in one process, on one trade feed, so the two see the same
fills. The diff must therefore read its switch from here, not from the
environment (one process has one environment): ``exp_flag.on("name")`` is
False everywhere the bot runs and True only while the experiment driver
turns it on around the treatment's cycle. A merged experiment ships
default-off; the WIN branch the owner merges adds ``ensure_env
EXP_FLAGS_ON <flag>`` to deploy.yml, read here at boot. A leaf module.
"""
from __future__ import annotations

import contextlib
import os

_on: set[str] = set()

# A merged experiment is switched on at boot by the deploy line its WIN
# branch adds (``ensure_env EXP_FLAGS_ON <flag>``), never by the analyst:
# the owner's merge is what brings it to real trades.
for _f in os.environ.get("EXP_FLAGS_ON", "").split(","):
    if _f.strip():
        _on.add(_f.strip())


def on(name: str) -> bool:
    return str(name or "") in _on


def enable(name: str) -> None:
    if name:
        _on.add(str(name))


def disable(name: str) -> None:
    _on.discard(str(name or ""))


def active() -> frozenset:
    return frozenset(_on)


@contextlib.contextmanager
def enabled(name: str):
    """``with exp_flag.enabled("x"): ...``: on inside, off after, always."""
    enable(name)
    try:
        yield
    finally:
        disable(name)
