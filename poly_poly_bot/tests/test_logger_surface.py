"""BotLogger must expose every stdlib logging method we (and future-us) reach for.

Failure #4 in the 2026-05-10 retrospective was ``logger.exception()``
crashing because ``BotLogger`` didn't have that method. The fix was to
add it (and friends) to BotLogger, mirroring stdlib ``logging.Logger``.
This test pins that surface so a refactor can't quietly remove the
methods and re-introduce the same trap.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

from src.logger import BotLogger, logger

# BotLogger mirrors stdlib *names* but NOT stdlib lazy %-formatting: each
# method takes a single pre-formatted ``msg`` string (``log`` takes
# ``level, msg``). Passing extra positional args — the ``logger.warning(fmt,
# a, b)`` idiom — raises TypeError at call time. That took copy-paper down on
# 2026-06-15 (main.py had `logger.warning("... %s ...", wl, wl)`). The scan
# below pins call-site arity so the trap can't come back.
_PKG_ROOT = Path(__file__).resolve().parent.parent
# method name -> exact positional-arg count BotLogger accepts
_ARITY = {
    "debug": 1, "info": 1, "warn": 1, "warning": 1, "error": 1,
    "critical": 1, "exception": 1, "trade": 1, "skip": 1, "log": 2,
}


def _files_using_botlogger():
    """Yield (path, tree) for every package .py file that binds the BotLogger
    singleton to the name ``logger`` (``from src.logger import logger``).
    Files that use a stdlib ``logging.getLogger`` are skipped — %-args are
    fine there."""
    paths = [_PKG_ROOT / "main.py", *(_PKG_ROOT / "src").rglob("*.py")]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("logger"):
                if any(a.name == "logger" and (a.asname or "logger") == "logger"
                       for a in node.names):
                    yield path, tree
                    break


def test_botlogger_call_sites_have_correct_arity():
    violations = []
    for path, tree in _files_using_botlogger():
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _ARITY
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "logger"
            ):
                # *args / **kwargs aren't part of BotLogger's surface either.
                has_star = any(isinstance(a, ast.Starred) for a in node.args)
                if len(node.args) != _ARITY[node.func.attr] or node.keywords or has_star:
                    violations.append(
                        f"{path.relative_to(_PKG_ROOT)}:{node.lineno} "
                        f"logger.{node.func.attr}() got {len(node.args)} positional "
                        f"arg(s), expected {_ARITY[node.func.attr]} "
                        "(BotLogger takes a single pre-formatted string — use an f-string)"
                    )
    assert not violations, "BotLogger call-site arity violations:\n" + "\n".join(violations)


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
