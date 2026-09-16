"""Where the real money actually went — the one surface that counts dollars.

Every other P&L surface in this repo mixes paper and real. ``/pnl`` is the
unified paper+preview book, ``/status`` counts copies, ``/live`` shows the
caps that *would* apply. ``/real`` answers the owner's plainest question:
**what is in the wallet, what is it holding, and what did the deals do?**

Polymarket is the only source it trusts for money:

* the Data API's ``/activity`` for the proxy wallet — every trade the
  exchange matched and every payout the chain made, at the cash that moved
  (fees included);
* the Data API's ``/positions`` — what is still held, at the entry price and
  at the current price, and which of it has resolved.

The bot's own ``realized-pnl.jsonl`` is NOT read here. It only learns of a
settlement the bot's redeemer saw, and winners are paid out on-chain without
the redeemer (a payout empties the position before the redeemer's pass), so
until 2026-09-16 ``/real`` showed every loss and none of the wins: 0W/8L and
-$47 realized on a book that was 12W/8L and -$2.63 net of fees.

``trade-history.jsonl`` is still read, for two things Polymarket cannot say:
when live trading started (the first real order), and which followed wallet
each deal copied. A row's ``status`` says which side of the interlock it
fell on, and that is the whole classification:

    - ``PLACED`` / ``FILLED`` / ``PARTIAL`` / ``UNFILLED`` / ``ABANDONED``
      are written only *past* the ``live_mode.is_preview()`` gate, so every
      one of them is an order that went to the exchange with real money.
    - ``PREVIEW`` is paper, ``DISARMED`` is a copy the arm refused, and
      ``SKIPPED`` / ``ALERT_ONLY`` never reached an order at all.

Rows are collapsed per ``order_id`` because one order writes several rows
(``PLACED`` then ``FILLED``); summing them raw double-counts the ticket.

Everything below is pure — rows in, dataclasses out — so it unit-tests with
no network and no disk. The two network reads (``fetch_chain_positions``,
``fetch_activity``) are isolated at the bottom and return raw rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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




def iso_epoch(ts) -> Optional[int]:
    """Epoch seconds of an ISO timestamp (naive means UTC), or None."""
    s = str(ts or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def live_start_ts(orders: Iterable[RealOrder]) -> Optional[int]:
    """When real money first moved: the earliest real order, or None."""
    stamps = [e for e in (iso_epoch(o.ts) for o in orders) if e is not None]
    return min(stamps) if stamps else None


# ---------------------------------------------------------------------------
# Polymarket's word: deals (activity) and holdings (positions).
# ---------------------------------------------------------------------------

BUY, SELL, PAYOUT = "BUY", "SELL", "PAYOUT"

# A resolved position worth less than this is spent: nothing to collect.
DUST_USD = 0.01

# How far a Polymarket fill may sit from the ledger row that placed it and
# still be tied to that row's followed wallet. The ledger stamps the copied
# trade; the exchange stamps the match, minutes later for a resting order.
ATTRIBUTION_GAP_S = 3600


@dataclass
class Deal:
    """One money movement Polymarket recorded for the proxy wallet."""

    ts: int
    kind: str                 # BUY | SELL | PAYOUT
    title: str = ""
    outcome: str = ""
    shares: float = 0.0
    price: float = 0.0
    usd: float = 0.0          # signed: a buy is negative, a sell or payout positive
    condition_id: str = ""
    asset: str = ""
    wallet: str = ""          # the followed wallet copied, when the ledger ties it


def parse_deals(rows: Iterable[dict], *, since_ts: int = 0) -> tuple[list[Deal], int]:
    """``(deals newest first, n rows of a type this does not count)``.

    Only TRADE and REDEEM are money this bot makes move. Anything else
    (split, merge, reward, conversion) is counted and reported rather than
    guessed at, so a new row type can never silently skew the totals.
    """
    deals: list[Deal] = []
    other = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        try:
            ts = int(row.get("timestamp"))
        except (TypeError, ValueError):
            continue
        if ts < since_ts:
            continue
        typ = str(row.get("type") or "").upper()
        usdc = _num(row.get("usdcSize"))
        if typ == "TRADE":
            side = str(row.get("side") or "").upper()
            if side not in (BUY, SELL):
                other += 1
                continue
            kind, usd = side, (-usdc if side == BUY else usdc)
        elif typ == "REDEEM":
            kind, usd = PAYOUT, usdc
        else:
            other += 1
            continue
        deals.append(Deal(
            ts=ts, kind=kind,
            title=str(row.get("title") or ""),
            outcome=str(row.get("outcome") or ""),
            shares=_num(row.get("size")),
            price=_num(row.get("price")),
            usd=usd,
            condition_id=str(row.get("conditionId") or ""),
            asset=str(row.get("asset") or ""),
        ))
    deals.sort(key=lambda d: d.ts, reverse=True)
    return deals, other


def attribute_wallets(deals: Iterable[Deal], orders: Iterable[RealOrder], *,
                      max_gap_s: int = ATTRIBUTION_GAP_S) -> None:
    """Stamp each BUY/SELL deal with the followed wallet its real order copied.

    Matched on token and side, nearest in time within ``max_gap_s``. A payout
    has no order behind it and keeps no wallet here (its market carries one).
    """
    index: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for o in orders or []:
        ep = iso_epoch(o.ts)
        if ep is None or not o.token_id:
            continue
        index.setdefault((o.token_id, o.side), []).append((ep, o.wallet_label))
    for d in deals or []:
        if d.kind not in (BUY, SELL) or not d.asset:
            continue
        best = None
        for ep, wallet in index.get((d.asset, d.kind), ()):
            gap = abs(ep - d.ts)
            if gap <= max_gap_s and (best is None or gap < best[0]):
                best = (gap, wallet)
        if best is not None:
            d.wallet = best[1]


@dataclass
class Position:
    """One holding as Polymarket marks it."""

    title: str = ""
    outcome: str = ""
    condition_id: str = ""
    shares: float = 0.0
    avg_price: float = 0.0
    cur_price: float = 0.0
    cost_usd: float = 0.0
    value_usd: float = 0.0
    resolved: bool = False
    end_date: str = ""

    @property
    def pnl(self) -> float:
        return self.value_usd - self.cost_usd

    @property
    def pnl_pct(self) -> Optional[float]:
        return self.pnl / self.cost_usd if self.cost_usd > 0 else None

    @property
    def state(self) -> str:
        """``open`` (market still trading) | ``collect`` (resolved, worth
        something) | ``spent`` (resolved, worth nothing)."""
        if not self.resolved:
            return "open"
        return "collect" if self.value_usd >= DUST_USD else "spent"


def parse_positions(rows: Iterable[dict]) -> list[Position]:
    """Data API position rows as ``Position``s; empty holdings dropped.

    ``initialValue`` is the API's cost basis and ``currentValue`` its mark;
    ``size * avgPrice`` and ``size * curPrice`` stand in when a key is absent.
    """
    out: list[Position] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        size = _num(row.get("size"))
        if size <= 0:
            continue
        avg = _num(row.get("avgPrice"))
        cur = _num(row.get("curPrice"))
        cost = (_num(row.get("initialValue")) if row.get("initialValue") is not None
                else size * avg)
        value = (_num(row.get("currentValue")) if row.get("currentValue") is not None
                 else size * cur)
        out.append(Position(
            title=str(row.get("title") or ""),
            outcome=str(row.get("outcome") or ""),
            condition_id=str(row.get("conditionId") or ""),
            shares=size, avg_price=avg, cur_price=cur,
            cost_usd=cost, value_usd=value,
            resolved=bool(row.get("redeemable")),
            end_date=str(row.get("endDate") or ""),
        ))
    return out


@dataclass
class MarketResult:
    """Everything real money did in one market, from Polymarket's rows."""

    condition_id: str
    title: str = ""
    outcome: str = ""
    first_buy_ts: int = 0
    wallet: str = ""
    paid_usd: float = 0.0       # buys, fees included
    sold_usd: float = 0.0
    paid_out_usd: float = 0.0
    held_usd: float = 0.0       # what its positions are worth now
    open: bool = False
    unseen: bool = False        # bought, but Polymarket shows no holding and no cash back yet

    @property
    def back_usd(self) -> float:
        return self.sold_usd + self.paid_out_usd

    @property
    def pnl(self) -> float:
        return self.back_usd + self.held_usd - self.paid_usd

    @property
    def state(self) -> str:
        if self.open:
            return "open"
        return "won" if self.pnl > 0 else "lost"


def market_results(deals: Iterable[Deal], positions: Iterable[Position]) -> list[MarketResult]:
    """One ``MarketResult`` per market the deals bought into, oldest first.

    A market is settled when no holding in it is still trading: its result
    is the cash back plus whatever resolved value is left to collect, minus
    what was paid. A winner that has already paid out has no position row at
    all, which is exactly the case the redeemer-fed ledger never counted.

    A market with a buy but neither a holding nor any cash back is one
    Polymarket has not caught up with yet: it is reported as open at cost,
    never as a loss (a real loser keeps its worthless position row).
    """
    by_cid: dict[str, list[Position]] = {}
    for p in positions or []:
        by_cid.setdefault(p.condition_id, []).append(p)
    markets: dict[str, MarketResult] = {}
    for d in sorted(deals or [], key=lambda d: d.ts):
        if not d.condition_id:
            continue
        m = markets.get(d.condition_id)
        if m is None:
            if d.kind != BUY:
                continue   # cash for a market this window never bought into
            m = markets[d.condition_id] = MarketResult(
                condition_id=d.condition_id, title=d.title, outcome=d.outcome,
                first_buy_ts=d.ts, wallet=d.wallet)
        if d.kind == BUY:
            m.paid_usd += -d.usd
            m.wallet = m.wallet or d.wallet
        elif d.kind == SELL:
            m.sold_usd += d.usd
        else:
            m.paid_out_usd += d.usd
    for m in markets.values():
        held = by_cid.get(m.condition_id, [])
        m.held_usd = sum(p.value_usd for p in held)
        m.open = any(p.state == "open" for p in held)
        if not held and m.back_usd <= 0:
            m.open = m.unseen = True
            m.held_usd = m.paid_usd
    return sorted(markets.values(), key=lambda m: m.first_buy_ts)


@dataclass
class WalletResult:
    wallet: str
    n_markets: int = 0
    wins: int = 0
    losses: int = 0
    n_open: int = 0
    paid_usd: float = 0.0
    pnl: float = 0.0            # settled markets only


def by_wallet(markets: Iterable[MarketResult]) -> list[WalletResult]:
    """Results per followed wallet, the biggest spend first."""
    out: dict[str, WalletResult] = {}
    for m in markets or []:
        key = m.wallet or UNKNOWN_WALLET
        w = out.setdefault(key, WalletResult(wallet=key))
        w.n_markets += 1
        w.paid_usd += m.paid_usd
        if m.state == "open":
            w.n_open += 1
            continue
        w.pnl += m.pnl
        if m.state == "won":
            w.wins += 1
        else:
            w.losses += 1
    return sorted(out.values(), key=lambda w: w.paid_usd, reverse=True)


@dataclass
class RealBook:
    """Everything ``/real`` renders, computed once."""

    since_ts: int = 0                                   # the window's floor
    live_ts: Optional[int] = None                       # first real order
    deals: list[Deal] = field(default_factory=list)     # in the window, newest first
    positions: Optional[list[Position]] = None          # None: could not read
    markets: list[MarketResult] = field(default_factory=list)
    n_other_rows: int = 0
    live_condition_ids: set[str] = field(default_factory=set)   # every live-era market, unwindowed
    activity_ok: bool = True                            # False: the trade history could not be read

    @property
    def open_positions(self) -> list[Position]:
        return sorted((p for p in self.positions or [] if p.state == "open"),
                      key=lambda p: p.cost_usd, reverse=True)

    @property
    def to_collect(self) -> list[Position]:
        return sorted((p for p in self.positions or [] if p.state == "collect"),
                      key=lambda p: p.value_usd, reverse=True)

    @property
    def value_usd(self) -> float:
        return sum(p.value_usd for p in self.positions or [])

    @property
    def spent_before_live(self) -> list[Position]:
        """Worthless resolved holdings that no live-era market accounts for:
        the pre-live wallet's leftovers, reported once and never counted.
        Unknowable without the trade history, so empty then."""
        if not self.activity_ok:
            return []
        return [p for p in self.positions or []
                if p.state == "spent" and p.condition_id not in self.live_condition_ids]

    @property
    def settled(self) -> list[MarketResult]:
        return [m for m in self.markets if m.state != "open"]

    @property
    def wins(self) -> int:
        return sum(1 for m in self.markets if m.state == "won")

    @property
    def losses(self) -> int:
        return sum(1 for m in self.markets if m.state == "lost")

    @property
    def n_open(self) -> int:
        return sum(1 for m in self.markets if m.state == "open")

    @property
    def n_unseen(self) -> int:
        return sum(1 for m in self.markets if m.unseen)

    @property
    def paid_usd(self) -> float:
        return sum(m.paid_usd for m in self.markets)

    @property
    def sold_usd(self) -> float:
        return sum(m.sold_usd for m in self.markets)

    @property
    def paid_out_usd(self) -> float:
        return sum(m.paid_out_usd for m in self.markets)

    @property
    def held_usd(self) -> float:
        return sum(m.held_usd for m in self.markets)

    @property
    def net_usd(self) -> float:
        """Cash back plus what is still held, minus what was paid."""
        return self.sold_usd + self.paid_out_usd + self.held_usd - self.paid_usd

    @property
    def result_for(self) -> dict[str, MarketResult]:
        return {m.condition_id: m for m in self.markets}


def build_book(activity_rows: Optional[Iterable[dict]],
               position_rows: Optional[Iterable[dict]],
               orders: Iterable[RealOrder] = (), *,
               since_ts: int = 0) -> RealBook:
    """The whole real-money picture from Polymarket's rows.

    Markets are grouped over every deal since live trading started, then the
    window (``since_ts``) keeps the markets first bought inside it and the
    deals made inside it. A payout inside the window for a market bought
    before it therefore never reads as a free win.

    ``None`` for either read means it failed: the book says so
    (``activity_ok``, ``positions is None``) and never guesses.
    """
    orders = list(orders or [])
    live_ts = live_start_ts(orders)
    floor = live_ts if live_ts is not None else 0
    deals, other = parse_deals(activity_rows or [], since_ts=floor)
    attribute_wallets(deals, orders)
    positions = parse_positions(position_rows) if position_rows is not None else None
    everything = market_results(deals, positions or [])
    return RealBook(
        since_ts=max(since_ts, floor),
        live_ts=live_ts,
        deals=[d for d in deals if d.ts >= since_ts],
        positions=positions,
        markets=[m for m in everything if m.first_buy_ts >= since_ts],
        n_other_rows=other,
        live_condition_ids={m.condition_id for m in everything},
        activity_ok=activity_rows is not None,
    )


# ---------------------------------------------------------------------------
# The impure edge: Polymarket's Data API.
# ---------------------------------------------------------------------------

_PAGE = 500
_MAX_PAGES = 20


def _fetch_pages(path: str, params: dict, timeout: float) -> Optional[list[dict]]:
    """Every page of a Data API list, or None when any page fails.

    A partial read is no read: half the deals would print a confident,
    wrong total.
    """
    try:
        import requests

        from src.config import CONFIG

        rows: list[dict] = []
        for page in range(_MAX_PAGES):
            resp = requests.get(f"{CONFIG.data_api_url}{path}",
                                params={**params, "limit": _PAGE,
                                        "offset": page * _PAGE},
                                timeout=timeout)
            if not resp.ok:
                return None
            data = resp.json()
            if not isinstance(data, list):
                return None
            rows.extend(data)
            if len(data) < _PAGE:
                return rows
    except Exception:  # noqa: BLE001 - a read failure is reported, never raised
        return None
    return None   # more pages than the cap: refuse rather than truncate


def fetch_chain_positions(proxy_wallet: str, *, timeout: float = 10.0) -> Optional[list[dict]]:
    """Every holding of the proxy wallet from the Data API, or None.

    None means "could not read", never "nothing there" — the caller says so
    rather than reporting a confident zero, which is the exact failure mode
    that left the bankroll floor inert (see ``auto_redeemer``).
    ``sizeThreshold=0`` because the API's default hides holdings under one
    share, and a resolved winner's leftover is often exactly that.
    """
    if not proxy_wallet:
        return None
    return _fetch_pages("/positions", {"user": proxy_wallet, "sizeThreshold": 0},
                        timeout)


def fetch_activity(proxy_wallet: str, *, since_ts: int = 0,
                   timeout: float = 10.0) -> Optional[list[dict]]:
    """The proxy wallet's trades and payouts since ``since_ts``, or None."""
    if not proxy_wallet:
        return None
    params: dict = {"user": proxy_wallet}
    if since_ts:
        params["start"] = int(since_ts)
    return _fetch_pages("/activity", params, timeout)
