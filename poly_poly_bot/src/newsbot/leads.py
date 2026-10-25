"""The lead-time ledger: for every price jump, the first free mention of it,
or "dark"; for every item we mapped, its four clocks and whether the market
moved after it.

Why (2026-10-25). The whole thesis of the news bot is that free sources
sometimes lead Polymarket's price. That is a measurement, not an opinion:
``lead_s`` is the source's own timestamp against the exchange's own
timestamp of the first move, and ``dark`` is the share of moves no free
source explained. The two-week report stands or falls on these two numbers;
the paper book is the footnote.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from typing import Iterable, Optional

from src.logger import logger

_WORD = re.compile(r"[a-z0-9]{3,}")
_STOP = {"the", "and", "for", "with", "will", "that", "this", "from", "have", "has", "are",
         "was", "were", "been", "its", "than", "then", "into", "over", "after", "before",
         "about", "says", "said", "new", "news", "breaking", "update", "report", "reports",
         "market", "markets", "price", "yes", "not", "who", "what", "when", "where", "which",
         "polymarket", "odds", "win", "wins", "2026", "october", "november", "december"}


def tokens(text: str) -> set:
    return {w for w in _WORD.findall((text or "").lower()) if w not in _STOP}


def stems(text: str) -> set:
    """Crude stems: the first five letters of each meaningful word, so
    Ukrainian/Ukraine, Brazilian/Brazil and Serbian/Serbia match (the verifier
    found single-entity geo headlines dropped by exact tokens, 2026-10-25).
    Words shorter than five letters stay whole."""
    return {w[:5] for w in tokens(text)}


_PROPER = re.compile(r"\b([A-Z][a-zA-Z]{5,})")


def overlap(a: str, b: str) -> int:
    """Shared stems between two texts. One shared stem that is a proper noun of
    six letters or more in ``a`` (the item) counts as two: a headline naming the
    one entity the market is about is a match even when nothing else is."""
    shared = stems(a) & stems(b)
    if len(shared) == 1:
        proper = {m[:5].lower() for m in _PROPER.findall(a or "")}
        if shared & proper:
            return 2
    return len(shared)


def ledger_dir() -> str:
    return os.environ.get("NEWS_DATA_DIR", "data/news")


@dataclass
class JumpRow:
    jump_id: str                  # f"{condition_id}:{minute}"
    ts: float                     # the exchange's clock, first minute of the move
    condition_id: str
    market_id: str
    question: str
    domains: tuple
    delta_cents: float
    from_price: float
    to_price: float
    notional: float
    n_trades: int
    # the explaining item, or dark
    first_source: str = ""
    first_item_id: str = ""
    first_published_ts: Optional[float] = None
    lead_s: Optional[float] = None    # first_published_ts -> ts; positive = the source was first
    candidates_n: int = 0
    dark: Optional[bool] = None       # None until judged; True = no free source had it
    judged_by: str = ""               # "llm" | "overlap" | ""
    # Did the tape have quotes for this market when it jumped? False means the
    # freshness verdict there would have read "unknown": an unwatched token,
    # counted as such in the brief, never as a verdict (manager, 2026-10-25).
    watched: Optional[bool] = None
    # The owner's late forward that explained a dark jump (idea 1, 2026-10-25).
    # Additive: the jump stays dark in the dark count; this row is printed
    # beside it as "explained later by owner", with how late, never in the
    # lead stats (its lead is negative by construction).
    owner_explained: bool = False
    owner_item_id: str = ""
    owner_late_s: Optional[float] = None


@dataclass
class ItemRow:
    """One mapped item: the four clocks and the price path after it."""
    item_id: str
    source: str
    domains: tuple
    market_id: str
    token_id: str
    question: str
    published_ts: float
    seen_ts: float
    decided_ts: float
    quote_ts: float
    material: bool
    fired: bool
    freshness: str
    mid_at_decision: Optional[float]
    moved: dict = field(default_factory=dict)   # horizon -> cents moved in OUR direction (None = no quote)
    direction: str = "yes"


class LeadLedger:
    def __init__(self, path: Optional[str] = None):
        self.path = path or os.path.join(ledger_dir(), "leads.jsonl")
        self.jumps: dict[str, JumpRow] = {}
        self.items: dict[str, ItemRow] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = d.pop("kind", None)
                try:
                    if kind == "jump":
                        d["domains"] = tuple(d.get("domains") or ())
                        self.jumps[d["jump_id"]] = JumpRow(**d)
                    elif kind == "item":
                        d["domains"] = tuple(d.get("domains") or ())
                        self.items[d["item_id"]] = ItemRow(**d)
                except TypeError:
                    continue  # a row from another schema version is skipped, not fatal

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with self._lock:
            with open(tmp, "w", encoding="utf-8") as f:
                for j in self.jumps.values():
                    f.write(json.dumps({"kind": "jump", **asdict(j)}) + "\n")
                for i in self.items.values():
                    f.write(json.dumps({"kind": "item", **asdict(i)}) + "\n")
            os.replace(tmp, self.path)

    # ---- jumps ----
    def add_jump(self, row: JumpRow) -> bool:
        if row.jump_id in self.jumps:
            return False
        with self._lock:
            self.jumps[row.jump_id] = row
        self.save()
        return True

    def unjudged_jumps(self) -> list[JumpRow]:
        return [j for j in self.jumps.values() if j.dark is None]

    def attribute(self, jump: JumpRow, items: Iterable, *, lookback_s: float,
                  pick=None) -> JumpRow:
        """Find the first free mention among ``items`` (anything with
        published_ts, title, text, id, source) published in the ``lookback_s``
        before the jump (and up to 2 min after, for a source that posts the
        move itself). ``pick(jump, candidates) -> item | None`` is the LLM
        when given; without it the best token overlap wins (>= 2 tokens)."""
        cands = [it for it in items
                 if jump.ts - lookback_s <= float(getattr(it, "published_ts", 0) or 0) <= jump.ts + 120
                 and overlap(jump.question, f"{getattr(it, 'title', '')} {getattr(it, 'text', '')}") >= 2]
        jump.candidates_n = len(cands)
        chosen = None
        if cands:
            if pick is not None:
                try:
                    chosen = pick(jump, cands)
                    jump.judged_by = "llm"
                except Exception as exc:  # noqa: BLE001
                    logger.warn(f"[news-leads] pick failed, falling back to overlap: {exc}")
                    chosen = None
            if chosen is None and pick is None:
                chosen = max(cands, key=lambda it: (overlap(jump.question, f"{getattr(it, 'title', '')} {getattr(it, 'text', '')}"),
                                                    -float(getattr(it, "published_ts", 0) or 0)))
                jump.judged_by = "overlap"
        if chosen is None:
            jump.dark = True
        else:
            jump.dark = False
            jump.first_source = str(getattr(chosen, "source", ""))
            jump.first_item_id = str(getattr(chosen, "id", ""))
            jump.first_published_ts = float(getattr(chosen, "published_ts", 0) or 0)
            jump.lead_s = round(jump.ts - jump.first_published_ts, 1)
        self.save()
        return jump

    def attribute_owner(self, item, condition_ids: Iterable[str], *, window_s: float = 86400.0) -> int:
        """An owner forward that maps to a market with a DARK jump in the last
        ``window_s`` explains it after the fact. Returns how many jumps it
        explained. The dark flag is left as it is."""
        cids = {str(c) for c in condition_ids}
        ts = float(getattr(item, "published_ts", 0) or 0)
        n = 0
        for j in self.jumps.values():
            if not j.dark or j.owner_explained or j.condition_id not in cids:
                continue
            if not (ts - window_s <= j.ts <= ts + 120):
                continue
            j.owner_explained = True
            j.owner_item_id = str(getattr(item, "id", ""))
            j.owner_late_s = round(ts - j.ts, 1)
            n += 1
        if n:
            self.save()
        return n

    # ---- items ----
    def add_item(self, row: ItemRow) -> None:
        with self._lock:
            self.items[row.item_id] = row
        self.save()

    def mark_item(self, item_id: str, horizon: str, cents_our_way: Optional[float]) -> None:
        it = self.items.get(item_id)
        if it is None or horizon in it.moved:
            return
        it.moved[horizon] = cents_our_way
        self.save()

    # ---- the report ----
    def stats(self, since_ts: float = 0.0, move_cents: float = 5.0) -> dict:
        """Per domain: jumps, dark fraction, median lead; items mapped/fired,
        moved our way within 24h, moved before seen, never moved; our latency.
        Every cell carries n; empty is n=0."""
        import statistics
        out: dict = {"domains": {}, "jumps_total": 0, "items_total": 0}
        doms = {d for j in self.jumps.values() for d in j.domains} | {d for i in self.items.values() for d in i.domains} | {"all"}
        for dom in sorted(doms):
            js = [j for j in self.jumps.values() if j.ts >= since_ts and (dom == "all" or dom in j.domains) and j.dark is not None]
            its = [i for i in self.items.values() if i.seen_ts >= since_ts and (dom == "all" or dom in i.domains)]
            leads = [j.lead_s for j in js if not j.dark and j.lead_s is not None]
            fired = [i for i in its if i.fired]
            moved = [i for i in fired if i.moved.get("24h") is not None and i.moved["24h"] >= move_cents]
            against = [i for i in fired if i.moved.get("24h") is not None and i.moved["24h"] <= -move_cents]
            flat = [i for i in fired if i.moved.get("24h") is not None and abs(i.moved["24h"]) < move_cents]
            lat = [i.decided_ts - i.seen_ts for i in its if i.decided_ts and i.seen_ts]
            out["domains"][dom] = {
                "jumps": len(js), "dark": sum(1 for j in js if j.dark),
                "watched": sum(1 for j in js if j.watched is True),
                "unknown": sum(1 for j in js if j.watched is False),
                "owner_explained": sum(1 for j in js if j.owner_explained),
                "owner_late_median_s": (statistics.median([j.owner_late_s for j in js if j.owner_explained and j.owner_late_s is not None])
                                        if any(j.owner_explained for j in js) else None),
                "dark_frac": (sum(1 for j in js if j.dark) / len(js)) if js else None,
                "lead_n": len(leads), "lead_median_s": statistics.median(leads) if leads else None,
                "lead_positive": sum(1 for x in leads if x > 0),
                "items": len(its), "mapped": sum(1 for i in its if i.material), "fired": len(fired),
                "fired_moved_our_way": len(moved), "fired_moved_against": len(against),
                "fired_flat": len(flat), "fired_unmarked": len(fired) - len(moved) - len(against) - len(flat),
                "late_at_decision": sum(1 for i in its if i.freshness in ("moving", "late")),
                "latency_median_s": statistics.median(lat) if lat else None,
            }
        out["jumps_total"] = len(self.jumps)
        out["items_total"] = len(self.items)
        return out
