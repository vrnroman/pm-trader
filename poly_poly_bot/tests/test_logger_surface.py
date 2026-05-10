"""BotLogger must expose every stdlib logging method we (and future-us) reach for.

Failure #4 in the 2026-05-10 retrospective was ``logger.exception()``
crashing because ``BotLogger`` didn't have that method. The fix was to
add it (and friends) to BotLogger, mirroring stdlib ``logging.Logger``.
This test pins that surface so a refactor can't quietly remove the
methods and re-introduce the same trap.
"""

from __future__ import annotations

import logging

import pytest

from src.logger import BotLogger, logger


@pytest.mark.parametrize(
    "method",
    [
        # The stdlib idioms anyone who has ever read the logging docs
        # will reach for. Each must exist and accept a single string arg.
        "debug",
        "info",
        "warning",
        "warn",
        "error",
        "critical",
        "exception",
        "log",
        # Project-specific custom levels — keep them too.
        "trade",
        "skip",
    ],
)
def test_bot_logger_has_method(method):
    assert hasattr(BotLogger, method), f"BotLogger.{method} missing"
    assert callable(getattr(logger, method)), f"BotLogger.{method} not callable"


def test_exception_logs_at_error_level_with_traceback(caplog):
    """logger.exception("X") must produce an ERROR record with the traceback."""
    with caplog.at_level(logging.DEBUG, logger="poly_poly_bot"):
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            logger.exception("crashed during X")

    err_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert err_records, "expected an ERROR-level log record"
    rec = err_records[-1]
    assert "crashed during X" in rec.getMessage()
    # exc_info must be attached so the formatter can render the traceback;
    # this is what differentiates .exception() from .error().
    assert rec.exc_info is not None
