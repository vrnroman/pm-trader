"""Where the real money actually went — the one surface that counts dollars.

Every other P&L surface in this repo mixes paper and real. ``/pnl`` is the
unified paper+preview book, ``/status`` counts copies, ``/live`` shows the
caps that *would* apply. None of them answer the owner's plainest question:
**how much real money has this bot spent, what came back, and what is still
out there?**

This module answers exactly that, from the three records real money leaves:

* ``trade-history.jsonl`` — the audit trail. A row's ``status`` says which
  side of the interlock it fell on, and that is the whole classification:

    - ``PLACED`` / ``FILLED`` / ``PARTIAL`` / ``UNFILLED`` / ``ABANDONED``
      are written only *past* the ``live_mode.is_preview()`` gate, so every
      one of them is an order that went to the exchange with real money.
    - ``PREVIEW`` is paper, ``DISARMED`` is a copy the arm refused (real
      money the bot did **not** spend — worth showing, never counted), and
      ``SKIPPED`` / ``ALERT_ONLY`` never reached an order at all.

  Rows are collapsed per ``order_id`` because one order writes several rows
  (``PLACED`` then ``FILLED``); summing them raw double-counts the ticket.

* ``realized-pnl.jsonl`` — what settled. ``source="redeemer"`` rows are real
  by construction: the redeemer only runs when ``PREVIEW_MODE=false``
  (``runner.py``), and it reads the proxy wallet's on-chain positions.
  ``source="preview"`` rows are the paper analogue. Anything else is tied to
  real money only when its ``token_id`` matches a token a real order bought;
  what cannot be tied is reported as unattributed rather than folded in, so
  the headline never quietly inherits pre-schema debris.

* the Data API's ``/positions`` for the proxy wallet — the chain's own word
  on what is still open, at cost and at the current mark. Local inventory
  cannot serve here: in a ``PREVIEW_MODE=true`` process the inventory file is
  the *simulated* one, so reading it would report paper as real.

Everything below is pure — rows in, dataclasses out — so it unit-tests with
no network and no disk. The one network call (``fetch_chain_positions``) is
isolated at the bottom and returns raw rows for ``summarize_chain_positions``
to fold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

# Statuses written only on the real-money path (past the interlock gate).
REAL_STATUSES = frozenset({"PLACED", "FILLED", "PARTIAL", "UNFILLED", "ABANDONED"})
# Paper copies: a preview process booking into the simulated inventory.
PAPER_STATUSES = frozenset({"PREVIEW"})
# A followed wallet traded and no order went out. DISARMED is the interesting
# one: it is real money the bot was told to spend and did not, because the arm
# was off. The others never got as far as sizing a live ticket.
NOT_PLACED_STATUSES = frozenset({"DISARMED", "SKIPPED", "ALERT_ONLY"})

# Which row wins when one order wrote several. Later, more-final states
# outrank earlier ones — and FILLED outranks UNFILLED on purpose: a cancel
# that failed because the order had just matched writes UNFILLED first and
# the fill arrives after it (order_verifier round 4).
_STATUS_RANK = {"PLACED": 1, "PARTIAL": 2, "UNFILLED": 3, "ABANDONED": 3, "FILLED": 4}
_SETTLED = frozenset({"FILLED", "UNFILLED", "ABANDONED"})

# A wallet-less real order is the pipeline test (/testorder, /canary), which
# carries no followed trader. It is still real money and gets its own bucket.
TEST_ORDER_WALLET = "(test order)"
UNKNOWN_WALLET = "(unknown)"


def _num(x, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if v == v else default  # NaN -> default


def _day(ts) -> str:
    """The UTC date of an ISO timestamp, or "" when unreadable."""
    s = str(ts or "")
    return s[:10] if len(s) >= 10 and s[4] == "-" and s[7] == "-" else ""


def classify_row(row: dict) -> str:
    """``real`` | ``paper`` | ``not-placed`` | ``unknown`` for one history row."""
    status = str((row or {}).get("status") or "").upper()
    if status in REAL_STATUSES:
        return "real"
    if status in PAPER_STATUSES:
        return "paper"
    if status in NOT_PLACED_STATUSES:
        return "not-placed"
    return "unknown"


@dataclass
class RealOrder:
    """One real order, collapsed from every history row that mentions it."""

    order_id: str
    ts: str = ""
    wallet: str = ""
    market: str = ""
    side: str = "BUY"
    token_id: str = ""
    source: str = ""
    status: str = "PLACED"
    posted_usd: float = 0.0
    filled_usd: float = 0.0
    filled_shares: float = 0.0
    fill_price: Optional[float] = None

    @property
    def settled(self) -> bool:
        """The exchange has spoken: filled, cancelled, or abandoned."""
        return self.status in _SETTLED

    @property
    def pending(self) -> bool:
        """Posted, nothing final heard yet — money committed but not confirmed."""
        return not self.settled

    @property
    def unfilled_usd(self) -> float:
        """Committed and not taken (cancelled, or still open on the book)."""
        return max(0.0, self.posted_usd - self.filled_usd)

    @property
    def day(self) -> str:
        return _day(self.ts)

    @property
    def wallet_label(self) -> str:
        if self.wallet:
            return self.wallet.lower()
        return TEST_ORDER_WALLET if self.source == "testorder" else UNKNOWN_WALLET


def _row_filled(row: dict) -> tuple[float, float, Optional[float]]:
    """``(filled_usd, filled_shares, fill_price)`` for one row.

    A FILLED row usually carries both legs of the fill; when it does not, the
    ticket's own size is the best available truth. An UNFILLED/ABANDONED row
    carries the shares that *were* accounted before the cancel but no fill
    price, so the copied trade's price stands in — flagged here rather than
    silently: it is the only estimate in this module, and it only ever applies
    to the partial remainder of a cancelled order.
    """
    status = str(row.get("status") or "").upper()
    shares = _num(row.get("fill_shares"))
    price = row.get("fill_price")
    price = _num(price) if price is not None else None
    if shares > 0 and price:
        return (shares * price, shares, price)
    if status == "FILLED":
        # Filled but no fill legs recorded: the order's own size is what left.
        return (_num(row.get("copy_size")), shares, price)
    if shares > 0:
        est = _num(row.get("price"))
        return (shares * est, shares, price)
    return (0.0, 0.0, price)


def collapse_orders(rows: Iterable[dict], *, since_day: str = "") -> list[RealOrder]:
    """Every real order in the history, one ``RealOrder`` each, oldest first.

    ``since_day`` is an inclusive ``YYYY-MM-DD`` floor on the row timestamp.
    Rows without an ``order_id`` but with a real status (a shape the current
    code never writes, but old rows might) are keyed on their own identity so
    they are counted once rather than dropped.
    """
    by_id: dict[str, RealOrder] = {}
    order: list[str] = []
    for row in rows or []:
        if not isinstance(row, dict) or classify_row(row) != "real":
            continue
        ts = str(row.get("timestamp") or "")
        if since_day and _day(ts) and _day(ts) < since_day:
            continue
        oid = str(row.get("order_id") or "")
        key = oid or f"~{ts}|{row.get('token_id', '')}|{row.get('side', '')}"
        status = str(row.get("status") or "").upper()
        filled_usd, filled_shares, fill_price = _row_filled(row)
        cur = by_id.get(key)
        if cur is None:
            by_id[key] = RealOrder(
                order_id=oid,
                ts=ts,
                wallet=str(row.get("trader_address") or ""),
                market=str(row.get("market") or ""),
                side=str(row.get("side") or "BUY").upper(),
                token_id=str(row.get("token_id") or ""),
                source=str(row.get("source") or ""),
                status=status,
                posted_usd=_num(row.get("copy_size")),
                filled_usd=filled_usd,
                filled_shares=filled_shares,
                fill_price=fill_price,
            )
            order.append(key)
            continue
        # A later row for the same order: keep the most final status, the
        # largest posted size, and the best fill information seen.
        if _STATUS_RANK.get(status, 0) >= _STATUS_RANK.get(cur.status, 0):
            cur.status = status
        cur.posted_usd = max(cur.posted_usd, _num(row.get("copy_size")))
        if filled_usd > cur.filled_usd:
            cur.filled_usd = filled_usd
            cur.filled_shares = max(cur.filled_shares, filled_shares)
            cur.fill_price = fill_price if fill_price is not None else cur.fill_price
        if not cur.market:
            cur.market = str(row.get("market") or "")
        if not cur.token_id:
            cur.token_id = str(row.get("token_id") or "")
        if not cur.wallet:
            cur.wallet = str(row.get("trader_address") or "")
    out = [by_id[k] for k in order]
    # A cancelled order took nothing; an abandoned one is unknown but the
    # exposure was released, so neither keeps a fill it never reported.
    for o in out:
        if o.status in ("UNFILLED", "ABANDONED") and o.filled_shares <= 0:
            o.filled_usd = 0.0
    out.sort(key=lambda o: o.ts)
    return out


@dataclass
class OrderStats:
    n_orders: int = 0
    n_filled: int = 0
    n_unfilled: int = 0
    n_pending: int = 0
    posted_usd: float = 0.0
    filled_usd: float = 0.0
    pending_usd: float = 0.0
    returned_usd: float = 0.0   # committed, never taken by the exchange
    n_buy: int = 0
    n_sell: int = 0
    sell_proceeds_usd: float = 0.0
    first_ts: str = ""
    last_ts: str = ""


def summarize_orders(orders: Iterable[RealOrder]) -> OrderStats:
    """Fold real orders into the headline counters.

    ``filled_usd`` counts BUY fills only — the money that *left*. A SELL fill
    is money coming back and is tracked separately, so the two are never
    netted into one misleading "deployed" number.
    """
    st = OrderStats()
    for o in orders:
        st.n_orders += 1
        if o.side == "SELL":
            st.n_sell += 1
            st.sell_proceeds_usd += o.filled_usd
        else:
            st.n_buy += 1
            st.posted_usd += o.posted_usd
            st.filled_usd += o.filled_usd
        if o.status == "FILLED":
            st.n_filled += 1
        elif o.status in ("UNFILLED", "ABANDONED"):
            st.n_unfilled += 1
        if o.pending:
            st.n_pending += 1
            st.pending_usd += o.posted_usd
        elif o.side != "SELL":
            st.returned_usd += o.unfilled_usd
        if o.ts:
            st.first_ts = min(st.first_ts, o.ts) if st.first_ts else o.ts
            st.last_ts = max(st.last_ts, o.ts)
    return st


@dataclass
class NotSpent:
    """What the interlock kept in the wallet: copies the arm refused."""

    n_disarmed: int = 0
    disarmed_usd: float = 0.0
    n_preview: int = 0
    preview_usd: float = 0.0


def summarize_not_spent(rows: Iterable[dict], *, since_day: str = "") -> NotSpent:
    """Followed-wallet buys that did NOT become real orders.

    ``DISARMED`` is the number the owner asks about after an outage ("what
    did I miss?"); ``PREVIEW`` is the paper book's size for contrast.
    """
    out = NotSpent()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        kind = classify_row(row)
        if kind not in ("paper", "not-placed"):
            continue
        ts = str(row.get("timestamp") or "")
        if since_day and _day(ts) and _day(ts) < since_day:
            continue
        status = str(row.get("status") or "").upper()
        size = _num(row.get("copy_size"))
        if status == "DISARMED":
            out.n_disarmed += 1
            out.disarmed_usd += size
        elif status == "PREVIEW":
            out.n_preview += 1
            out.preview_usd += size
    return out


def split_realized(rows: Iterable[dict], real_token_ids: set[str],
                   *, since_day: str = "") -> tuple[list[dict], list[dict]]:
    """``(real, other)`` realized rows.

    Real by construction when the redeemer wrote it (it runs only in a live
    process, against the chain). Otherwise real only when the row's token was
    bought by a real order in this history — a preview-sourced row never
    qualifies. Everything else lands in ``other`` and is *reported* as
    unattributed rather than assumed either way.
    """
    real: list[dict] = []
    other: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if since_day and _day(row.get("timestamp")) and _day(row.get("timestamp")) < since_day:
            continue
        source = str(row.get("source") or "").lower()
        token = str(row.get("token_id") or "")
        if source == "redeemer":
            real.append(row)
        elif source != "preview" and token and token in real_token_ids:
            real.append(row)
        else:
            other.append(row)
    return (real, other)


@dataclass
class RealizedStats:
    n_rows: int = 0
    pnl: float = 0.0
    cost_basis: float = 0.0
    returned_usd: float = 0.0
    wins: int = 0
    losses: int = 0

    @property
    def roi(self) -> Optional[float]:
        return (self.pnl / self.cost_basis) if self.cost_basis > 0 else None


def summarize_realized(rows: Iterable[dict]) -> RealizedStats:
    """Settled real money: what it cost, what came back, what it made."""
    st = RealizedStats()
    for row in rows or []:
        st.n_rows += 1
        pnl = _num(row.get("pnl"))
        st.pnl += pnl
        st.cost_basis += _num(row.get("cost_basis"))
        st.returned_usd += _num(row.get("returned"))
        won = row.get("won")
        if won is None:
            won = pnl > 0
        if won:
            st.wins += 1
        else:
            st.losses += 1
    return st


@dataclass
class DayLine:
    date: str
    n_orders: int = 0
    filled_usd: float = 0.0
    realized_pnl: float = 0.0


def by_day(orders: Iterable[RealOrder], realized_rows: Iterable[dict]) -> list[DayLine]:
    """One line per UTC day that saw real money move, newest first."""
    days: dict[str, DayLine] = {}

    def _line(d: str) -> DayLine:
        if d not in days:
            days[d] = DayLine(date=d)
        return days[d]

    for o in orders:
        if not o.day or o.side == "SELL":
            continue
        ln = _line(o.day)
        ln.n_orders += 1
        ln.filled_usd += o.filled_usd
    for row in realized_rows or []:
        d = _day(row.get("timestamp"))
        if d:
            _line(d).realized_pnl += _num(row.get("pnl"))
    return sorted(days.values(), key=lambda x: x.date, reverse=True)


@dataclass
class WalletLine:
    wallet: str
    n_orders: int = 0
    n_filled: int = 0
    filled_usd: float = 0.0
    realized_pnl: float = 0.0
    wins: int = 0
    losses: int = 0

    @property
    def roi(self) -> Optional[float]:
        return (self.realized_pnl / self.filled_usd) if self.filled_usd > 0 else None


def by_wallet(orders: Iterable[RealOrder], realized_rows: Iterable[dict]) -> list[WalletLine]:
    """Real dollars and real settled P&L per followed wallet, biggest first.

    Realized rows are attributed by their stamped ``trader_address``; a row
    the redeemer could not attribute falls back to the wallet that bought the
    token, so a settled loss is never orphaned away from the wallet that
    caused it.
    """
    wallets: dict[str, WalletLine] = {}
    token_owner: dict[str, str] = {}

    def _line(w: str) -> WalletLine:
        if w not in wallets:
            wallets[w] = WalletLine(wallet=w)
        return wallets[w]

    for o in orders:
        if o.side == "SELL":
            continue
        w = o.wallet_label
        ln = _line(w)
        ln.n_orders += 1
        ln.filled_usd += o.filled_usd
        if o.status == "FILLED":
            ln.n_filled += 1
        if o.token_id and o.filled_usd > 0:
            token_owner.setdefault(o.token_id, w)
    for row in realized_rows or []:
        w = str(row.get("trader_address") or "").lower()
        if not w:
            w = token_owner.get(str(row.get("token_id") or ""), UNKNOWN_WALLET)
        ln = _line(w)
        pnl = _num(row.get("pnl"))
        ln.realized_pnl += pnl
        won = row.get("won")
        if won is None:
            won = pnl > 0
        if won:
            ln.wins += 1
        else:
            ln.losses += 1
    return sorted(wallets.values(), key=lambda x: x.filled_usd, reverse=True)


@dataclass
class ChainStats:
    """The chain's own word on open real positions (Data API ``/positions``)."""

    n_positions: int = 0
    cost_usd: float = 0.0
    value_usd: float = 0.0
    n_redeemable: int = 0
    redeemable_usd: float = 0.0

    @property
    def unrealized(self) -> float:
        return self.value_usd - self.cost_usd


def summarize_chain_positions(rows: Iterable[dict]) -> ChainStats:
    """Fold Data API position rows into cost / mark / collectable.

    ``initialValue`` is the API's own cost basis; ``size * avgPrice`` is the
    fallback when it is absent. A resolved-and-unredeemed position still
    counts as open money — it IS money, sitting in a token instead of in
    USDC — and is called out separately so "go collect it" is visible.
    """
    st = ChainStats()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        size = _num(row.get("size"))
        if size <= 0:
            continue
        cost = _num(row.get("initialValue"))
        if cost <= 0:
            cost = size * _num(row.get("avgPrice"))
        value = _num(row.get("currentValue"))
        if value <= 0:
            value = size * _num(row.get("curPrice"))
        st.n_positions += 1
        st.cost_usd += cost
        st.value_usd += value
        flag = row.get("redeemable")
        if flag is None:
            flag = row.get("resolved")
        if flag:
            st.n_redeemable += 1
            st.redeemable_usd += value
    return st


@dataclass
class RealMoneyReport:
    """Everything ``/real`` renders, computed once."""

    orders: list[RealOrder] = field(default_factory=list)
    stats: OrderStats = field(default_factory=OrderStats)
    realized: RealizedStats = field(default_factory=RealizedStats)
    not_spent: NotSpent = field(default_factory=NotSpent)
    days: list[DayLine] = field(default_factory=list)
    wallets: list[WalletLine] = field(default_factory=list)
    chain: Optional[ChainStats] = None
    n_unattributed_realized: int = 0
    since_day: str = ""

    @property
    def net_usd(self) -> float:
        """Realized P&L on real money, before anything still open."""
        return self.realized.pnl

    @property
    def at_work_usd(self) -> float:
        """Real money currently out there: open positions at cost when the
        chain could be read, else the unsettled part of what was filled."""
        if self.chain is not None:
            return self.chain.cost_usd
        return max(0.0, self.stats.filled_usd - self.realized.cost_basis)

    @property
    def has_real_activity(self) -> bool:
        return bool(self.orders) or self.realized.n_rows > 0


def build_report(history_rows: Iterable[dict], realized_rows: Iterable[dict],
                 *, chain_rows: Optional[Iterable[dict]] = None,
                 since_day: str = "") -> RealMoneyReport:
    """The whole real-money picture from the raw ledger rows.

    Pure: pass ``chain_rows=None`` when the chain could not be read and every
    number that does not depend on it still renders.
    """
    history_rows = list(history_rows or [])
    orders = collapse_orders(history_rows, since_day=since_day)
    real_tokens = {o.token_id for o in orders if o.token_id}
    real_realized, other = split_realized(realized_rows, real_tokens, since_day=since_day)
    return RealMoneyReport(
        orders=orders,
        stats=summarize_orders(orders),
        realized=summarize_realized(real_realized),
        not_spent=summarize_not_spent(history_rows, since_day=since_day),
        days=by_day(orders, real_realized),
        wallets=by_wallet(orders, real_realized),
        chain=(summarize_chain_positions(chain_rows) if chain_rows is not None else None),
        n_unattributed_realized=len(other),
        since_day=since_day,
    )


# ---------------------------------------------------------------------------
# The one impure edge: the chain read.
# ---------------------------------------------------------------------------

def fetch_chain_positions(proxy_wallet: str, *, timeout: float = 10.0) -> Optional[list[dict]]:
    """Open positions for the proxy wallet from the Data API, or None.

    None means "could not read", never "nothing there" — the caller says so
    rather than reporting a confident zero, which is the exact failure mode
    that left the bankroll floor inert (see ``auto_redeemer``).
    """
    if not proxy_wallet:
        return None
    try:
        import requests

        from src.config import CONFIG

        resp = requests.get(f"{CONFIG.data_api_url}/positions",
                            params={"user": proxy_wallet}, timeout=timeout)
        if not resp.ok:
            return None
        data = resp.json()
    except Exception:  # noqa: BLE001 - a read failure is reported, never raised
        return None
    return data if isinstance(data, list) else None
