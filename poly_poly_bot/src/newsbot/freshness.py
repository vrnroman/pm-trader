"""The tape rule: is the market still unaware of the news, or already moving?

``verdict`` is a pure function over the two tape structures (``QuoteBook`` for
the token's quotes, ``TradeBuckets`` for the market's prints); ``now`` is the
caller's clock in seconds. States (DESIGN.md, 2026-10-25):

- ``fresh``   no |move| > fresh_cents in the last fresh_min minutes on the
              token's quotes or the market's trades, and the current ask within
              fresh_cents of the mid 15 minutes ago (the pre-window mid).
- ``moving``  a move > fresh_cents inside the last 3 minutes: the item is late
              and the move is in progress; log, do not fire.
- ``late``    the move happened earlier in the window (or the ask has already
              walked away from the pre-window mid).
- ``unknown`` no quotes and no trades yet. Unknown is not fresh: the book never
              fires on it.

Quote moves are measured as the range of mids over a sub-window, seeded with
the mid just before the sub-window opened, so a jump that happened 4 minutes
ago and then went flat reads ``late`` (not ``moving``) and a jump that straddles
the 3-minute edge still reads ``moving``. Trade moves are the range of bucket
prices (YES space) in the sub-window; a single stray print therefore marks a
market not-fresh, which is the conservative side.
"""
from __future__ import annotations

from typing import Any, Protocol


class _Book(Protocol):
    def history(self, token: str) -> list[tuple[int, float | None, float | None, float | None]]: ...

    def best(self, token: str) -> tuple[float | None, float | None, int] | None: ...

    def mid_at(self, token: str, ts_ms: int) -> float | None: ...


class _Buckets(Protocol):
    def recent(self, condition_id: str, minutes: int, now: float | None = None) -> list[tuple[int, Any]]: ...


def _quote_range_cents(book: _Book, token: str, start_s: float, end_s: float) -> float | None:
    """max - min of mids observed in (start, end], seeded with the mid at
    ``start``. None when the token has no quote at or before ``end``."""
    start_ms, end_ms = int(start_s * 1000), int(end_s * 1000)
    mids = [m for ts, _, _, m in book.history(token) if start_ms < ts <= end_ms and m is not None]
    seed = book.mid_at(token, start_ms)
    if seed is not None:
        mids.append(seed)
    if not mids:
        return None
    return (max(mids) - min(mids)) * 100.0


def _trade_range(buckets: _Buckets, cid: str, start_s: float, end_s: float) -> tuple[float | None, int]:
    """(range in cents over the bucket prices in [start, end], n trades)."""
    minutes = max(1, int((end_s - start_s + 59) // 60))
    lo = hi = None
    n = 0
    for _, b in buckets.recent(cid, minutes, end_s):
        if b.last_ts < start_s:
            continue
        n += b.n
        lo = b.min if lo is None else min(lo, b.min)
        hi = b.max if hi is None else max(hi, b.max)
    if lo is None:
        return None, 0
    return (hi - lo) * 100.0, n


def verdict(
    book: _Book,
    buckets: _Buckets,
    token_id: str,
    condition_id: str,
    now: float,
    *,
    fresh_cents: float,
    fresh_min: int,
    moving_min: int = 3,
    pre_window_min: int = 15,
) -> tuple[str, str]:
    token_id = str(token_id)
    window_start = now - fresh_min * 60
    moving_start = now - moving_min * 60

    best = book.best(token_id)
    q_window = _quote_range_cents(book, token_id, window_start, now) if best else None
    q_moving = _quote_range_cents(book, token_id, moving_start, now) if best else None
    t_window, t_n_window = _trade_range(buckets, condition_id, window_start, now)
    t_moving, t_n_moving = _trade_range(buckets, condition_id, moving_start, now)

    if best is None and t_window is None:
        return "unknown", "no quotes and no trades yet"

    def _c(x: float | None) -> str:
        return "-" if x is None else f"{x:.1f}c"

    moving_parts = [f"quotes {_c(q_moving)}", f"trades {_c(t_moving)} n={t_n_moving}"]
    if (q_moving is not None and q_moving > fresh_cents) or (t_moving is not None and t_moving > fresh_cents):
        return "moving", f"move in last {moving_min}m: " + ", ".join(moving_parts)

    window_parts = [f"quotes {_c(q_window)}", f"trades {_c(t_window)} n={t_n_window}"]
    if (q_window is not None and q_window > fresh_cents) or (t_window is not None and t_window > fresh_cents):
        return "late", f"moved earlier in last {fresh_min}m: " + ", ".join(window_parts) + f"; last {moving_min}m quiet"

    if best is None:
        # Trades alone can prove a move; they cannot prove the ask is still
        # where it was. Without a quote the fresh claim is unverifiable.
        return "unknown", f"no quotes yet; trades {_c(t_window)} n={t_n_window} in {fresh_min}m"

    _, ask, _ = best
    if ask is None:
        return "unknown", "no ask on the book"

    pre_ms = int((now - pre_window_min * 60) * 1000)
    pre_mid = book.mid_at(token_id, pre_ms)
    baseline_note = f"pre-mid({pre_window_min}m)"
    if pre_mid is None:
        hist = [(ts, m) for ts, _, _, m in book.history(token_id) if m is not None]
        if not hist:
            return "unknown", "quotes carry no mid yet"
        ts0, pre_mid = hist[0]
        baseline_note = f"oldest mid ({max(0.0, now - ts0 / 1000) / 60:.1f}m old)"
    gap = (ask - pre_mid) * 100.0
    numbers = ", ".join(window_parts) + f"; ask {ask:.3f} vs {baseline_note} {pre_mid:.3f} ({gap:+.1f}c)"
    if abs(gap) > fresh_cents:
        return "late", "ask already away from " + numbers
    return "fresh", f"quiet {fresh_min}m: " + numbers
