"""Experiment flags: the switch a code-change experiment sits behind.

An experiment that needs new code (s-ye5990) runs a CONTROL and a TREATMENT
paper book in one process, on one trade feed, so the two see the same
fills. The diff must therefore read its switch from here, not from the
environment (one process has one environment): ``exp_flag.on("name")`` is
False everywhere the bot runs and True only while the experiment driver
turns it on around the treatment's cycle. A merged experiment ships
default-off; the owner turns it on by a config knob of his own in the PR
he merges. A leaf module: no imports.
"""
from __future__ import annotations

import contextlib

_on: set[str] = set()


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
