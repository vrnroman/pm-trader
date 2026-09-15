"""Run the suite as if it were N days from now: the time-bomb sweep.

Not collected by a normal run. Enable it explicitly::

    CLOCK_DRIFT_DAYS=90 .venv/bin/python -m pytest tests/ -q -p tests.clock_drift_plugin

Every test then executes with the wall clock shifted forward by that many
days, still ticking. A test that fails only under the shift is coupled to the
calendar rather than to the code — which is what took the deploy gate down on
2026-09-14, a full day after the commit that armed it passed green.

The clock moves; the fixtures do not. That asymmetry is the whole point: any
production path that reads ``time.time()`` where its caller supplied a ``now``
diverges under the shift and the test that pinned an absolute timestamp goes
red. Nothing else changes.
"""

from __future__ import annotations

import os

import pytest

_DAYS = float(os.environ.get("CLOCK_DRIFT_DAYS", "0") or 0)


@pytest.fixture(autouse=True)
def _drift_clock():
    """Shift the clock forward for the duration of each test."""
    if not _DAYS:
        yield
        return
    import datetime as _dt

    from freezegun import freeze_time

    start = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=_DAYS)
    # tick=True keeps time moving: a frozen clock breaks anything that measures
    # elapsed time, which would be a false positive, not a time bomb.
    with freeze_time(start, tick=True):
        yield
