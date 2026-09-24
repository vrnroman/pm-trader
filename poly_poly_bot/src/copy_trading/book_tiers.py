"""Book B at more than one slice floor (2026-09-24 requirements, part 3 §3.4).

The backward replay said the $150..300 bets of the watched wallets are about
as good as their $300+ bets, that evidence would arrive twice as fast at
$150, and that the set of good wallets changes with the floor, not only its
size. That is a forward question: run B300 (today's book, untouched) next
to B150 and B100 as separate paper books, with exits and drag, and decide
after weeks which one feeds the Z gate.

``COPY_PAPER_B_BOOKS`` names the books: ``"b300:300,b150:150,b100:100"``.
The FIRST is the primary: its files are today's (ledger
``copy_paper_ledger_b.jsonl``, scope ``b``), so nothing moves; every other
book gets ``copy_paper_ledger_<id>.jsonl`` and governance scope ``<id>``.
Consumers hard-wired to the primary keep reading it; ``ZSET_GATE_BOOK``
points the Z gate at another book with one env change. Live money copies
from ``LIVE_MIN_TRADER_BET_USD`` (default: the paper floor), so lowering a
paper book never lowers what real money copies. A leaf: config and os.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from src.config import CONFIG

DEFAULT_SPEC = "b300:300"


@dataclass(frozen=True)
class Book:
    id: str
    min_usd: float
    primary: bool

    @property
    def scope(self) -> str:
        return "b" if self.primary else self.id

    @property
    def tag(self) -> str:
        return "COPY-PAPER-B" if self.primary else f"COPY-PAPER-{self.id.upper()}"


def parse_spec(spec: str | None) -> list[Book]:
    """``"b300:300,b150:150"`` -> books, the first primary. A bad entry is
    skipped, a bad spec is the default: the primary book always runs."""
    out: list[Book] = []
    seen: set = set()
    for i, part in enumerate(str(spec or DEFAULT_SPEC).split(",")):
        part = part.strip()
        if not part or ":" not in part:
            continue
        bid, val = part.split(":", 1)
        bid = bid.strip().lower()
        try:
            usd = float(val)
        except ValueError:
            continue
        if not bid.isalnum() or usd <= 0 or bid in seen:
            continue
        seen.add(bid)
        out.append(Book(id=bid, min_usd=usd, primary=not out))
    return out or [Book(id="b300", min_usd=float(getattr(CONFIG, "copy_paper_min_usd", 300.0) or 300.0), primary=True)]


def books(cfg=CONFIG) -> list[Book]:
    return parse_spec(getattr(cfg, "copy_paper_b_books", None) or os.environ.get("COPY_PAPER_B_BOOKS"))


def primary(cfg=CONFIG) -> Book:
    return books(cfg)[0]


def ledger_path(book: Book, cfg=CONFIG) -> str:
    if book.primary:
        return cfg.copy_paper_b_ledger
    return os.path.join(cfg.data_dir, f"copy_paper_ledger_{book.id}.jsonl")


def gate_history_path(book: Book, cfg=CONFIG) -> str:
    return os.path.join(os.path.dirname(cfg.wallet_discovery_state), f"promotion-gate-history_{book.scope}.jsonl")


def gate_book(cfg=CONFIG) -> Book:
    """The book the Z gate reads (ZSET_GATE_BOOK, default the primary)."""
    want = str(getattr(cfg, "zset_gate_book", "") or os.environ.get("ZSET_GATE_BOOK", "") or "").strip().lower()
    for b in books(cfg):
        if b.id == want:
            return b
    return primary(cfg)


def gate_ledger_path(cfg=CONFIG) -> str:
    return ledger_path(gate_book(cfg), cfg)


def live_min_trader_bet(cfg=CONFIG) -> float:
    """What real money copies from: LIVE_MIN_TRADER_BET_USD, else the paper
    floor. Decoupled so a lower paper book never lowers live."""
    try:
        v = float(getattr(cfg, "live_min_trader_bet_usd", 0.0) or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    return v if v > 0 else float(cfg.copy_paper_min_usd)


def lines(now: float | None = None, *, min_settled: int = 1) -> list[str]:
    """One line per book from its ledger: settled, realized ROI, ROI at
    their price, net of modeled costs. Raw numbers, no verdict."""
    from src.copy_trading.strategy_compare import _book_stats, _load_rows
    out = []
    for b in books():
        rows = _load_rows(ledger_path(b))
        s = _book_stats(rows)
        if s["n_settled"] < min_settled:
            out.append(f"{b.id} (floor ${b.min_usd:.0f}): {s['n_settled']} settled, {s['n_open']} open; too few to read")
            continue
        out.append(f"{b.id} (floor ${b.min_usd:.0f}): {s['n_settled']} settled, {s['n_open']} open, "
                   f"realized {s['roi'] * 100:+.1f}%, at their price {s['ideal_roi'] * 100:+.1f}% "
                   f"(net {s['ideal_roi_net'] * 100:+.1f}%), win rate {s['win_rate'] * 100:.0f}%"
                   + (", feeds the Z gate" if b.id == gate_book().id else ""))
    return out
