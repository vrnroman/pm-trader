"""Daily log rotation + retention purge.

Two prod bugs this pins (both found in the 2026-07-02 log analysis):

1. The date was baked into the filename ONCE at process start, so a container
   running across UTC midnight kept appending a week of logs into the start
   day's file (``bot-2026-06-29.log`` still growing on 07-02).
2. The retention purge ran only at startup and keyed on mtime — so it never ran
   mid-process, and the always-fresh mtime of the open file made the cutoff
   meaningless (203 MB logs from May still on disk).

The fix rolls the file at midnight and purges by the *date in the filename*.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.logger import _DailyRotatingFileHandler, _purge_old_bot_logs


class _Clock:
    """Injectable UTC clock whose date we can advance in a test."""

    def __init__(self, dt: datetime) -> None:
        self.dt = dt

    def __call__(self) -> datetime:
        return self.dt


def _date(s: str):
    return datetime.strptime(s, "%Y-%m-%d").date()


def test_handler_writes_to_todays_dated_file(tmp_path):
    import logging

    clock = _Clock(datetime(2026, 6, 29, 23, 30, tzinfo=timezone.utc))
    h = _DailyRotatingFileHandler(tmp_path, "bot", clock=clock)
    try:
        h.emit(logging.LogRecord("x", logging.INFO, __file__, 1, "hi", None, None))
        h.flush()
    finally:
        h.close()
    assert (tmp_path / "bot-2026-06-29.log").exists()
    assert "hi" in (tmp_path / "bot-2026-06-29.log").read_text()


def test_handler_rolls_to_new_file_at_midnight(tmp_path):
    import logging

    clock = _Clock(datetime(2026, 6, 29, 23, 59, tzinfo=timezone.utc))
    h = _DailyRotatingFileHandler(tmp_path, "bot", clock=clock)
    try:
        h.emit(logging.LogRecord("x", logging.INFO, __file__, 1, "before", None, None))
        # cross UTC midnight
        clock.dt = datetime(2026, 6, 30, 0, 1, tzinfo=timezone.utc)
        h.emit(logging.LogRecord("x", logging.INFO, __file__, 1, "after", None, None))
        h.flush()
    finally:
        h.close()

    before = tmp_path / "bot-2026-06-29.log"
    after = tmp_path / "bot-2026-06-30.log"
    assert before.exists() and after.exists()
    assert "before" in before.read_text() and "before" not in after.read_text()
    assert "after" in after.read_text() and "after" not in before.read_text()


def test_rollover_fires_on_rollover_callback(tmp_path):
    import logging

    seen = []
    clock = _Clock(datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc))
    h = _DailyRotatingFileHandler(
        tmp_path, "bot", clock=clock, on_rollover=lambda d: seen.append(d)
    )
    try:
        h.emit(logging.LogRecord("x", logging.INFO, __file__, 1, "a", None, None))
        assert seen == []  # no roll yet
        clock.dt = datetime(2026, 6, 30, 0, 5, tzinfo=timezone.utc)
        h.emit(logging.LogRecord("x", logging.INFO, __file__, 1, "b", None, None))
        assert seen == [tmp_path]  # rollover triggered the purge hook exactly once
    finally:
        h.close()


def test_purge_deletes_by_filename_date_not_mtime(tmp_path):
    # today = 2026-07-02, retention 2 => keep 07-02 and 07-01, drop 06-30 & older.
    for name in (
        "bot-2026-05-23.log",  # ancient
        "bot-2026-06-30.log",  # == today-2 -> dropped
        "bot-2026-07-01.log",  # kept
        "bot-2026-07-02.log",  # today, kept
        "signals-2026-05-23.log",  # signals kept forever, never touched
    ):
        (tmp_path / name).write_text("x")

    _purge_old_bot_logs(tmp_path, 2, today=_date("2026-07-02"))

    assert not (tmp_path / "bot-2026-05-23.log").exists()
    assert not (tmp_path / "bot-2026-06-30.log").exists()
    assert (tmp_path / "bot-2026-07-01.log").exists()
    assert (tmp_path / "bot-2026-07-02.log").exists()
    # signals must survive regardless of age
    assert (tmp_path / "signals-2026-05-23.log").exists()


def test_purge_never_deletes_the_active_file_even_if_touched_now(tmp_path):
    """The open file is always today's; a fresh mtime must not save an old-dated
    file nor endanger today's. Keying on filename date makes both correct."""
    active = tmp_path / "bot-2026-07-02.log"
    active.write_text("live")  # mtime = now
    old = tmp_path / "bot-2026-06-01.log"
    old.write_text("old")
    # even if the old file was just touched (fresh mtime), it must still go.
    old.touch()

    _purge_old_bot_logs(tmp_path, 2, today=_date("2026-07-02"))

    assert active.exists()
    assert not old.exists()


def test_purge_ignores_malformed_names(tmp_path):
    (tmp_path / "bot-notadate.log").write_text("x")
    (tmp_path / "bot-.log").write_text("x")
    _purge_old_bot_logs(tmp_path, 2, today=_date("2026-07-02"))
    # non-conforming names are left alone (no crash, no delete)
    assert (tmp_path / "bot-notadate.log").exists()
    assert (tmp_path / "bot-.log").exists()
