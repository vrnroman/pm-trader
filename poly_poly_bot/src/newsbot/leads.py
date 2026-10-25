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
import unicodedata
from typing import Iterable, Optional

from src.logger import logger

_WORD = re.compile(r"[a-z0-9]{3,}")
_STOP = {"the", "and", "for", "with", "will", "that", "this", "from", "have", "has", "are",
         "was", "were", "been", "its", "than", "then", "into", "over", "after", "before",
         "about", "says", "said", "new", "news", "breaking", "update", "report", "reports",
         "market", "markets", "price", "yes", "not", "who", "what", "when", "where", "which",
         "polymarket", "odds", "win", "wins", "2026", "october", "november", "december"}


def fold(text: str) -> str:
    """Strip accents so "Vučić" and "Vucic" are one word; without it the
    tokenizer split the Serbian PM's name into nothing (2026-10-25 election)."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(ch))


def tokens(text: str) -> set:
    return {w for w in _WORD.findall(fold(text).lower()) if w not in _STOP}


def stems(text: str) -> set:
    """Crude stems: the first five letters of each meaningful word, so
    Ukrainian/Ukraine, Brazilian/Brazil and Serbian/Serbia match (the verifier
    found single-entity geo headlines dropped by exact tokens, 2026-10-25).
    Words shorter than five letters stay whole."""
    return {w[:5] for w in tokens(text)}


_CAPWORD = re.compile(r"\b([A-Z][a-z]{2,})")
# Capitalised words that name nothing in particular; a market question has
# them mid-sentence ("the President of France", "the Senate vote").
_GENERIC = {"will", "president", "minister", "prime", "government", "senate", "congress", "house",
            "white", "court", "supreme", "united", "states", "state", "national", "nation", "federal",
            "reserve", "bank", "central", "election", "elections", "party", "republic", "kingdom",
            "north", "south", "east", "west", "world", "cup", "league", "open", "final", "finals",
            "game", "match", "series", "season", "week", "day", "month", "year", "yes", "no",
            "october", "november", "december", "january", "february", "march", "april", "may",
            "june", "july", "august", "september", "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday", "before", "after", "between", "above", "below", "over",
            "under", "up", "down", "win", "lose", "the", "and", "or", "of", "in", "on", "at", "by",
            # title-case question words ("Which Bloc Wins More Seats?" matched a
            # JPMorgan headline on "More", 2026-10-25)
            "more", "most", "less", "other", "any", "which", "best", "exact", "total", "wins", "seats"}


def proper_stems(text: str) -> set:
    """Stems of the Capitalised words (first letter upper, the rest lower, so an
    ALL-CAPS wire headline gives none) that are not generic. Taken from the
    MARKET question, whose casing is reliable; a lowercase tweet still matches
    when it shares that stem (verifier, 2026-10-25: "starlink" was dropped and
    "*PRESIDENT TO ADDRESS NATION*" was matched)."""
    return {w[:5].lower() for w in _CAPWORD.findall(fold(text)) if w.lower() not in _GENERIC}


def overlap(a: str, b: str) -> int:
    """Shared stems between an item ``a`` and a market ``b``, scored for the
    relevance bar: a shared stem that is a proper noun of the market counts as
    two on its own (the one entity the market is about), common words alone
    count one each and never clear the bar by themselves."""
    shared = stems(a) & stems(b)
    if not shared:
        return 0
    proper = shared & proper_stems(b)
    if proper:
        return max(2, len(shared))
    return min(1, len(shared))


def explains(item_text: str, question: str) -> bool:
    """The stricter bar for pinning a price jump on a headline, which the
    tape-first book then trades with no model in the loop: at least two shared
    stems, one of them a proper noun of the market. One shared entity is enough
    to ASK the judge about an item (``overlap``), never to claim it moved the
    price: on the 2026-10-25 replay every one-stem attribution was wrong (an
    Israel-Hebron story for the Israel election bloc market, a JPMorgan story
    via "More", an Algerian parliament story via "parliamentary vote")."""
    shared = stems(item_text) & stems(question)
    return len(shared) >= 2 and bool(shared & proper_stems(question))


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
        when given; without it the best token overlap wins. A candidate must
        clear ``explains``, the two-stem bar, not the judge's one-entity bar."""
        cands = [it for it in items
                 if jump.ts - lookback_s <= float(getattr(it, "published_ts", 0) or 0) <= jump.ts + 120
                 and explains(f"{getattr(it, 'title', '')} {getattr(it, 'text', '')}", jump.question)]
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
