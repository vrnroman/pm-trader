"""Consensus-of-sharps signal — signal-only (no fill, so no slippage).

The lag-sweep kill-test showed single-wallet copy-and-hold is structurally −EV at
any lag. Convergence is a different, slower object: when K **independent**,
**copy-validated** wallets all BUY the same (market, outcome) inside a window,
that agreement is the signal. It can't be a fast tick (independent actors reaching
the same view takes time, so it survives our latency), and it's harder to fake
than any one wallet's print. We emit it as a Telegram signal the owner can act on
by hand — no capital deployed here.

Detection is pure (recent buys + a funder map injected), so it unit-tests offline.
``independence`` collapses wallets that share a non-CEX USDC funder to a single
voice, so one entity's sybil cluster can't masquerade as a consensus.
"""

from __future__ import annotations

import html
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class ConsensusMember:
    """One wallet's BUY into the consensus outcome."""
    wallet: str
    usd: float
    price: float
    ts: float


@dataclass
class ConsensusSignal:
    condition_id: str
    outcome_index: int
    title: str
    slug: str
    category: str
    members: tuple = ()      # tuple[ConsensusMember] — independent, size desc

    @property
    def key(self) -> tuple:
        return (self.condition_id, self.outcome_index)

    @property
    def n(self) -> int:
        return len(self.members)

    @property
    def total_usd(self) -> float:
        return sum(m.usd for m in self.members)

    @property
    def avg_price(self) -> float:
        tot = self.total_usd
        return (sum(m.usd * m.price for m in self.members) / tot) if tot > 0 else 0.0

    @property
    def time_spread_s(self) -> float:
        ts = [m.ts for m in self.members]
        return (max(ts) - min(ts)) if ts else 0.0


def _independent_members(rows: list, funder_of) -> list:
    """Collapse wallets that share a non-CEX funder into one voice (the largest
    bet of the cluster). ``funder_of`` maps a lowercased wallet to its funder
    address, or "" for unknown/CEX (treated as independent). One BUY per wallet
    already (largest kept upstream); here we dedup across wallets by funder."""
    funder_of = funder_of or {}
    by_cluster: dict = {}
    for m in rows:
        funder = (funder_of.get(m.wallet.lower(), "") or "")
        # empty funder -> unique per wallet (independent); shared funder -> cluster
        cluster = funder if funder else f"solo:{m.wallet.lower()}"
        cur = by_cluster.get(cluster)
        if cur is None or m.usd > cur.usd:
            by_cluster[cluster] = m
    return sorted(by_cluster.values(), key=lambda m: m.usd, reverse=True)


def detect_consensus(
    buys: list,
    *,
    k: int,
    window_s: float,
    min_usd: float,
    now: float,
    funder_of=None,
) -> list:
    """Find (market, outcome) cells that ≥``k`` independent wallets bought within
    ``window_s``. ``buys`` are dicts with: ``wallet``, ``condition_id``,
    ``outcome_index``, ``usd``, ``price``, ``ts``, and (optional) ``title``,
    ``slug``, ``category``. Only buys ≥ ``min_usd`` and within the window count.
    One BUY per wallet per cell (its largest). Returns signals, strongest first."""
    cutoff = now - window_s
    # group by (cid, oi) -> wallet -> best member
    cells: dict = defaultdict(dict)
    meta: dict = {}
    for b in buys:
        usd = float(b.get("usd") or 0.0)
        ts = float(b.get("ts") or 0.0)
        cid = b.get("condition_id")
        oi = b.get("outcome_index")
        wallet = (b.get("wallet") or "").lower()
        if not cid or oi is None or not wallet or usd < min_usd or ts < cutoff:
            continue
        key = (cid, int(oi))
        meta.setdefault(key, {"title": b.get("title", ""), "slug": b.get("slug", ""),
                              "category": b.get("category", "other")})
        m = ConsensusMember(wallet=wallet, usd=usd,
                            price=float(b.get("price") or 0.0), ts=ts)
        cur = cells[key].get(wallet)
        if cur is None or m.usd > cur.usd:
            cells[key][wallet] = m

    signals: list = []
    for (cid, oi), wallet_members in cells.items():
        members = _independent_members(list(wallet_members.values()), funder_of)
        if len(members) >= k:
            md = meta[(cid, oi)]
            signals.append(ConsensusSignal(
                condition_id=cid, outcome_index=oi,
                title=md["title"], slug=md["slug"], category=md["category"],
                members=tuple(members)))
    signals.sort(key=lambda s: (s.n, s.total_usd), reverse=True)
    return signals


def _cents(price: float) -> str:
    return f"{price * 100:.0f}¢"


def _dur(seconds: float) -> str:
    s = int(max(0, seconds))
    h, rem = divmod(s, 3600)
    m = rem // 60
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m" if m else "<1m"


def _short(wallet: str) -> str:
    return wallet[:8] + "…" if len(wallet) > 9 else wallet


def format_consensus_signal(sig: "ConsensusSignal", resolver) -> str:
    """Telegram (HTML) signal that says exactly what the sharps are buying.

    Leads with the action + the *named* outcome so it's unmissable; the outcome
    name comes from ``resolver`` (the real market array, honest ``Outcome #idx``
    fallback — never a guessed YES/NO). Per-member breakdown shows who, how much,
    and at what price."""
    outcome = resolver.label(sig.condition_id, sig.outcome_index)
    title = html.escape(sig.title) if sig.title else "(market)"
    lines = [
        f"\U0001f91d <b>{sig.n} sharps → BUY “{html.escape(outcome)}”</b>",
        f"<b>{title}</b>",
        f"avg <b>{_cents(sig.avg_price)}</b> · total <b>${sig.total_usd:,.0f}</b>"
        f" · {sig.n} wallets over {_dur(sig.time_spread_s)}",
    ]
    for m in sig.members:
        lines.append(
            f" • <code>{_short(m.wallet)}</code> "
            f"<b>${m.usd:,.0f}</b> @ {_cents(m.price)}")
    if sig.slug:
        lines.append(f"\U0001f517 https://polymarket.com/event/{sig.slug}")
    return "\n".join(lines)


def run_consensus_scan(
    wallets: list,
    *,
    fetch_buys,
    resolver,
    send,
    fired: dict,
    now: float,
    k: int,
    window_s: float,
    min_usd: float,
    cooldown_s: float,
    funder_of=None,
    log=None,
) -> list:
    """Orchestrate one consensus scan (all I/O injected, so it unit-tests offline).

    ``fetch_buys(wallet) -> list[buy-dict]`` pulls each wallet's recent BUYs;
    ``funder_of`` maps wallet->funder for independence; ``resolver`` names the
    outcome; ``send(text)`` emits a signal; ``fired`` is the persisted dedup state
    (mutated). Returns the fresh signals sent this scan."""
    buys: list = []
    for w in wallets:
        try:
            buys.extend(fetch_buys(w) or [])
        except Exception:  # one wallet's fetch must not kill the scan
            if log:
                log(f"consensus: fetch failed for {w}")
    signals = detect_consensus(
        buys, k=k, window_s=window_s, min_usd=min_usd, now=now, funder_of=funder_of)
    fresh = new_signals(signals, fired, now=now, cooldown_s=cooldown_s)
    if log:
        log(f"consensus: {len(wallets)} sharps · {len(buys)} recent buys · "
            f"{len(signals)} cells>=k · {len(fresh)} new (k={k})")
    for s in fresh:
        send(format_consensus_signal(s, resolver))
    return fresh


def new_signals(signals: list, fired: dict, now: float, cooldown_s: float) -> list:
    """Filter to consensus cells not already alerted within ``cooldown_s``, and
    record the fires in ``fired`` (mutated: ``"cid:oi" -> last_ts``). Re-fires only
    after the cooldown OR when the independent member count grows past what last
    fired (a strengthening consensus is worth a fresh ping)."""
    out = []
    for s in signals:
        key = f"{s.condition_id}:{s.outcome_index}"
        prev = fired.get(key)
        grew = isinstance(prev, dict) and s.n > prev.get("n", 0)
        last_ts = prev.get("ts", 0.0) if isinstance(prev, dict) else (prev or 0.0)
        if prev is None or grew or (now - last_ts) >= cooldown_s:
            fired[key] = {"ts": now, "n": s.n}
            out.append(s)
    return out
