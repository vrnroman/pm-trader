"""The market tape: what Polymarket itself is doing, minute by minute.

Three bounded structures (2026-10-25, run s-pw9rom):

- ``livedata``: every trade and comment from the live-data websocket, folded
  into per-market per-minute buckets the moment they arrive (never stored raw;
  the VM is an e2-small and the socket runs at ~35 trades/s).
- ``clob_ws``: best bid/ask ring buffers plus the latest sorted ladder for the
  token ids we are watching, from the CLOB market websocket.
- ``jumps``: the jump detector over the buckets, which is what the lead-time
  ledger and the surprise pings consume.

``src.newsbot.freshness`` is the pure rule that reads the first two.
"""
from __future__ import annotations

from .clob_ws import Fill, Ladder, QuoteBook, fetch_book_rest, stream_quotes
from .jumps import Jump, JumpDetector
from .livedata import Comment, CommentCounter, Trade, TradeBuckets, stream_trades

__all__ = [
    "Comment",
    "CommentCounter",
    "Fill",
    "Jump",
    "JumpDetector",
    "Ladder",
    "QuoteBook",
    "Trade",
    "TradeBuckets",
    "fetch_book_rest",
    "stream_quotes",
    "stream_trades",
]
