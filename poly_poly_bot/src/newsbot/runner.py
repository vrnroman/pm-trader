"""The news bot's supervisor: sockets, pollers, the index, the judge, four
paper books, the lead ledger, the phone.

Shape (run s-pw9rom, 2026-10-25): one asyncio loop in one daemon thread.
Items arrive on a queue from the pollers (RSS, Telegram previews, Tree of
Alpha, HN) and the Bluesky socket; the Polymarket live-data socket fills the
trade buckets; the CLOB socket keeps quotes for every token we care about.
Per item: deterministic FTS candidates, a REST book seed for tokens the tape
has not met, the tape's freshness verdict, one bounded LLM call, then the
books decide: ``llm`` fires on material + fresh, ``headline-any`` on
material, ``random`` matches the llm book's fire count, ``tape-first`` fires
when a jump finds its headline within five minutes. Every number the brief
prints comes from the ledgers on disk, so a restart changes nothing: dedup
and open rows reload, open rows resume their own exit timers.

Memory: buckets, quote ring buffers and the recent-items window are bounded;
nothing raw is kept. The box has OOM-hung before (project memory 2026-10-10).
"""

from __future__ import annotations

import asyncio
import collections
import json
import os
import random
import threading
import time
from typing import Optional

from src.logger import logger
from src.newsbot import brief as brief_mod
from src.newsbot import freshness as fresh_mod
from src.newsbot import index as index_mod
from src.newsbot import judge as judge_mod
from src.newsbot import leads as leads_mod
from src.newsbot import llm as llm_mod
from src.newsbot import paper as paper_mod
from src.newsbot.items import DedupStore, Item, make_id
from src.newsbot.sources import bluesky, poller, roster as roster_mod
from src.newsbot.tape import clob_ws, jumps as jumps_mod, livedata


def _env(name: str, default):
    raw = os.environ.get(name, "")
    if raw == "":
        return default
    try:
        return type(default)(raw) if not isinstance(default, bool) else raw.strip().lower() in ("1", "true", "yes", "on")
    except ValueError:
        return default


def data_dir() -> str:
    return os.environ.get("NEWS_DATA_DIR", "data/news")


class Runner:
    def __init__(self, shutdown: threading.Event):
        self.shutdown = shutdown
        self.stop = asyncio.Event()
        d = data_dir()
        os.makedirs(d, exist_ok=True)
        self.domains = tuple(x.strip() for x in str(_env("NEWS_DOMAINS", "politics,crypto,geo,corp")).split(",") if x.strip())
        self.model = str(_env("NEWS_JUDGE_MODEL", "claude-sonnet-5-5"))
        self.fresh_cents = float(_env("NEWS_FRESH_CENTS", 3.0))
        self.fresh_min = int(_env("NEWS_FRESH_MIN", 15))
        self.jump_cents = float(_env("NEWS_JUMP_CENTS", 8.0))
        self.jump_window_min = int(_env("NEWS_JUMP_WINDOW_MIN", 10))
        self.move_cents = float(_env("NEWS_MOVE_CENTS", 5.0))
        self.silent_hours = float(_env("NEWS_SILENT_HOURS", 6.0))
        self.brief_utc = str(_env("NEWS_BRIEF_UTC", "08:00"))
        self.lead_lookback_s = float(_env("NEWS_LEAD_LOOKBACK_MIN", 60)) * 60
        self.watch_seed = int(_env("NEWS_WATCH_SEED", 300))
        self.day_judged: dict[str, int] = {}
        self.day_material: dict[str, int] = {}
        # A news bot trades fresh news. At boot every feed hands over its
        # whole backlog (about 3,000 items, hours to days old, seen 2026-10-25);
        # judging those would spend the LLM budget on history and seed REST
        # books for nothing. Older than this is counted as stale and dropped;
        # the owner's own forwards are never stale.
        self.max_item_age_s = float(_env("NEWS_MAX_ITEM_AGE_MIN", 30)) * 60
        self.day_stale: dict[str, int] = {}
        # The first live hour judged seven items a minute, most of them an
        # NFL preview against a Macron market: FTS returns a candidate for
        # almost any sentence. Two bars before the LLM (2026-10-25): the
        # item and the market must share at least NEWS_MIN_OVERLAP meaningful
        # words, and the day's budget is paced per hour so the cap is not
        # gone by lunch (NEWS_LLM_HOURLY_CAP, default budget/12).
        self.min_overlap = int(_env("NEWS_MIN_OVERLAP", 2))
        self.hourly_cap = int(_env("NEWS_LLM_HOURLY_CAP", 0)) or max(1, int(_env("NEWS_LLM_DAILY_BUDGET", 300)) // 12)
        self.hour_calls: dict[str, int] = {}
        self.day_unmatched: dict[str, int] = {}
        self.day_paced: dict[str, int] = {}
        # state
        self.roster = roster_mod.load()
        self.counters = roster_mod.Counters(os.path.join(d, "roster.json"))
        self.dedup = DedupStore(os.path.join(d, "seen.json"))
        self.index = index_mod.MarketIndex(os.path.join(d, "index.sqlite"))
        self.book = clob_ws.QuoteBook()
        self.buckets = livedata.TradeBuckets()
        self.comments = livedata.CommentCounter()
        self.jumps = jumps_mod.JumpDetector(self.buckets, jump_cents=self.jump_cents,
                                            window_min=self.jump_window_min, exclude=self._exclude_cid,
                                            min_trades=int(_env("NEWS_JUMP_MIN_TRADES", 3)),
                                            min_notional=float(_env("NEWS_JUMP_MIN_USD", 150)))
        self.leads = leads_mod.LeadLedger(os.path.join(d, "leads.jsonl"))
        self.budget = llm_mod.DailyBudget(os.path.join(d, "llm-budget.json"),
                                          int(_env("NEWS_LLM_DAILY_BUDGET", 300)))
        from src.copy_trading import fee_rate
        self.books = {b: paper_mod.PaperBook(b, ask_ladder=self._ask_ladder, bid_ladder=self._bid_ladder,
                                             fee_bps=fee_rate.fee_bps) for b in paper_mod.BOOKS}
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=5000)
        # Items of the last day, for lead attribution. Persisted: four
        # restarts on the first day each emptied this window and every jump
        # in the next hour read "dark" for no reason (owner, 2026-10-25).
        self._recent_path = os.path.join(d, "recent.jsonl")
        self.recent: collections.deque = collections.deque(self._load_recent(), maxlen=4000)
        self.watch: collections.OrderedDict = collections.OrderedDict()   # token -> last touched ts
        self.item_by_id: dict[str, Item] = {}
        self.item_dir: dict[str, tuple[str, str]] = {}   # item_id -> (token, direction)
        self.day_items: dict[str, int] = {}
        # Surprise pings fire once; the set lives on disk so a restart does not
        # repeat them (verifier, 2026-10-25).
        self._pinged_path = os.path.join(d, "pinged.json")
        self.pinged: set = self._load_pinged()
        self.rng = random.Random()
        self.started = time.time()
        self.last_item_ts = 0.0
        self.hwm = {"watch": 0, "recent": 0, "queue": 0}
        self._cid_cache: dict = {}
        # The same story from three sources was judged three times (the Saudi
        # intercept, 2026-10-25). A judged item is remembered for 30 minutes;
        # a later item with mostly the same words on the same markets is not
        # judged again.
        self.judged_recent: collections.deque = collections.deque(maxlen=400)
        self.day_repeat: dict[str, int] = {}
        # The day's funnel counts survive a restart; seven restarts on
        # 2026-10-25 left the brief's counts unreadable (verifier round 3).
        self._day_path = os.path.join(d, "day-counters.json")
        self._load_day()
        _register(self)

    # ---- ladders for the paper books: the socket's book, else one REST read ----
    def _ladder(self, token: str):
        lad = self.book.ladder(token)
        if lad is None or (not lad.asks and not lad.bids):
            lad = self._rest_book(token)
            if lad is not None:
                self.book.set_ladder(token, lad)
        return lad

    def _rest_book(self, token: str):
        """One synchronous GET /book for a token the socket has not met yet
        (the item path runs in a worker thread, so no awaiting here)."""
        try:
            import httpx
            r = httpx.get(clob_ws.CLOB_REST_BOOK, params={"token_id": token}, timeout=5.0)
            if r.status_code != 200:
                return None
            return clob_ws.parse_ladder(r.json())
        except Exception as exc:  # noqa: BLE001
            logger.warn(f"[news] REST book failed for {token[:12]}: {exc}")
            return None

    def _ask_ladder(self, token: str):
        lad = self._ladder(token)
        return list(lad.asks) if lad else None

    def _bid_ladder(self, token: str):
        lad = self._ladder(token)
        return list(lad.bids) if lad else None

    def _exclude_cid(self, condition_id: str) -> bool:
        """Sports and short up/down markets never count as jumps; a market the
        index does not know is excluded too (thin, or outside our domains)."""
        c = self._by_condition(condition_id)
        if c is None:
            return True
        return bool(c.is_sports) or not (set(c.domains) & set(self.domains))

    def _by_condition(self, condition_id: str):
        cached = self._cid_cache
        if condition_id in cached:
            return cached[condition_id]
        try:
            c = self.index.by_condition(condition_id)
        except Exception:  # noqa: BLE001
            c = None
        if len(cached) > 20000:
            cached.clear()
        cached[condition_id] = c
        return c

    def _touch(self, token: str, now: float) -> None:
        self.watch[token] = now
        self.watch.move_to_end(token)
        while len(self.watch) > 450:   # one CLOB connection; the socket shards above 500
            self.watch.popitem(last=False)
        self.hwm["watch"] = max(self.hwm["watch"], len(self.watch))

    def watched_tokens(self) -> list[str]:
        return list(self.watch.keys())

    def seed_watch(self, now: Optional[float] = None) -> int:
        """Quotes for the biggest markets in our domains from the start, so a
        jump there is 'watched', not 'unknown': on day one every jump was
        unwatched because only mapped items filled the set."""
        now = time.time() if now is None else now
        try:
            toks = self.index.all_token_ids(self.domains)[: self.watch_seed]
        except Exception as exc:  # noqa: BLE001
            logger.warn(f"[news] watch seed failed: {exc}")
            return 0
        n = 0
        for tok in toks:
            if tok not in self.watch:
                self.watch[tok] = now
                n += 1
        while len(self.watch) > 450:
            self.watch.popitem(last=False)
        return n

    # ---- the item path ----
    def freshness_for(self, token: str, condition_id: str, now: float) -> tuple[str, str]:
        if self.book.best(token) is None:
            self._ladder(token)   # seed one quote so the verdict has a baseline
        try:
            return fresh_mod.verdict(self.book, self.buckets, token, condition_id, now,
                                     fresh_cents=self.fresh_cents, fresh_min=self.fresh_min)
        except Exception as exc:  # noqa: BLE001
            return ("unknown", f"freshness failed: {exc}")

    def process_item(self, item: Item, now: Optional[float] = None) -> Optional[dict]:
        now = time.time() if now is None else now
        self.last_item_ts = now
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        self.day_items[day] = self.day_items.get(day, 0) + 1
        self.recent.append(item)
        self.item_by_id[item.id] = item
        if len(self.item_by_id) > 6000:
            for k in list(self.item_by_id)[:2000]:
                self.item_by_id.pop(k, None)
        self.hwm["recent"] = max(self.hwm["recent"], len(self.recent))
        if item.domains and not (set(item.domains) & set(self.domains)):
            return None
        if item.source != "owner" and item.published_ts and now - item.published_ts > self.max_item_age_s:
            self.day_stale[day] = self.day_stale.get(day, 0) + 1
            return None
        text = f"{item.title} {item.text}".strip()
        if len(text) < 12:
            return None
        try:
            cands = self.index.candidates(text, k=8, domains=list(item.domains) or list(self.domains), now=now)
        except Exception as exc:  # noqa: BLE001
            logger.warn(f"[news] candidates failed: {exc}")
            return None
        if not cands:
            return None
        cands = [c for c in cands if item.source == "owner"
                 or leads_mod.overlap(text, f"{c.question} {c.event_title}") >= self.min_overlap]
        if not cands:
            self.day_unmatched[day] = self.day_unmatched.get(day, 0) + 1
            return None
        item_stems = leads_mod.stems(text)
        cand_ids = {str(c.market_id) for c in cands}
        if item.source != "owner" and self._is_repeat(item_stems, cand_ids, now):
            self.day_repeat[day] = self.day_repeat.get(day, 0) + 1
            return None
        hour = time.strftime("%Y-%m-%dT%H", time.gmtime(now))
        if self.hour_calls.get(hour, 0) >= self.hourly_cap and item.source != "owner":
            self.day_paced[day] = self.day_paced.get(day, 0) + 1
            logger.info(f"[news] paced: hourly LLM cap {self.hourly_cap} reached, '{item.title[:50]}' not judged")
            return None
        self.hour_calls[hour] = self.hour_calls.get(hour, 0) + 1
        if len(self.hour_calls) > 48:
            for k in sorted(self.hour_calls)[:-24]:
                self.hour_calls.pop(k, None)
        if item.source == "owner":
            # The owner's late forward explains a dark jump after the fact
            # (idea 1): FTS only, no LLM, the dark count untouched.
            n_exp = self.leads.attribute_owner(item, [c.condition_id for c in cands])
            if n_exp:
                logger.info(f"[news] owner forward explained {n_exp} dark jump(s): '{item.title[:50]}'")
        fresh_by_tok: dict = {}
        quotes_by_tok: dict = {}
        for c in cands[:2]:          # the top two get a quote seed; the rest ride Gamma's numbers
            for tok in c.token_ids:
                self._touch(tok, now)
                fresh_by_tok[tok] = self.freshness_for(tok, c.condition_id, now)
                b = self.book.best(tok)
                if b:
                    quotes_by_tok[tok] = {"bid": b[0], "ask": b[1]}
        j = judge_mod.judge(item, cands, fresh_by_tok, budget=self.budget, model=self.model,
                            quotes_by_token=quotes_by_tok, now=now)
        decided_at = time.time()
        if j is None:
            return None
        self.day_judged[day] = self.day_judged.get(day, 0) + 1
        self.judged_recent.append((now, frozenset(item_stems), frozenset(cand_ids)))
        if j.material:
            self.day_material[day] = self.day_material.get(day, 0) + 1
        if not j.material or j.market_id is None or j.outcome_index is None:
            logger.info(f"[news] not material: {item.source} '{item.title[:60]}' ({j.why[:80]})")
            return None
        cand = next((c for c in cands if str(c.market_id) == str(j.market_id)), None)
        if cand is None or j.outcome_index >= len(cand.token_ids):
            return None
        token = str(cand.token_ids[j.outcome_index])
        outcome = cand.outcomes[j.outcome_index] if j.outcome_index < len(cand.outcomes) else ""
        self._touch(token, now)
        state, detail = fresh_by_tok.get(token) or self.freshness_for(token, cand.condition_id, now)
        mid = None
        b = self.book.best(token)
        if b and b[0] is not None and b[1] is not None:
            mid = (b[0] + b[1]) / 2
        common = dict(item_id=item.id, source=item.source, domains=tuple(item.domains or cand.domains),
                      market_id=str(cand.market_id), condition_id=str(cand.condition_id), token_id=token,
                      outcome=str(outcome), question=cand.question, published_ts=item.published_ts,
                      seen_ts=item.seen_ts, decided_ts=decided_at, freshness=state,
                      confidence=j.confidence, why=j.why)
        fired = False
        row = None
        # headline-any: every material mapping, no tape rule
        self.books["headline-any"].fire(**common)
        if state == "fresh":
            row = self.books["llm"].fire(**common)
            fired = row is not None
            if fired:
                self._fire_random(common, now)
                self._say_fire(row, item, detail)
        else:
            logger.info(f"[news] mapped but tape says {state}: '{cand.question[:50]}' ({detail})")
        self.item_dir[item.id] = (token, j.direction or "yes")
        self.leads.add_item(leads_mod.ItemRow(
            item_id=item.id, source=item.source, domains=tuple(item.domains or cand.domains),
            market_id=str(cand.market_id), token_id=token, question=cand.question,
            published_ts=item.published_ts, seen_ts=item.seen_ts, decided_ts=decided_at,
            quote_ts=now, material=True, fired=fired, freshness=state, mid_at_decision=mid,
            direction=j.direction or "yes"))
        return {"fired": fired, "state": state, "market": cand.question}

    def _fire_random(self, common: dict, now: float) -> None:
        """The random book: one fire per llm fire, on a random active market
        in our domains, same stake, so the LLM has to beat chance."""
        try:
            toks = self.index.all_token_ids(self.domains)
            if not toks:
                return
            tok = self.rng.choice(toks)
            c = self.index.by_token(tok)
            if c is None:
                return
            i = c.token_ids.index(tok) if tok in c.token_ids else 0
            self.books["random"].fire(**{**common, "item_id": f"rnd:{common['item_id']}", "source": "random",
                                         "market_id": str(c.market_id), "condition_id": str(c.condition_id),
                                         "token_id": tok, "outcome": c.outcomes[i] if i < len(c.outcomes) else "",
                                         "question": c.question, "freshness": "n/a", "confidence": 0.0,
                                         "why": "random control"})
            self._touch(tok, now)
        except Exception as exc:  # noqa: BLE001
            logger.warn(f"[news] random book fire failed: {exc}")

    def _say_fire(self, row, item: Item, detail: str) -> None:
        try:
            from src import telegram_bot
            lad = self.book.ladder(row.token_id)
            depth = sum(p * s for p, s in (lad.asks if lad else [])) if lad else None
            telegram_bot.send_message(brief_mod.fire_message(row, headline=item.title or item.text,
                                                             source=item.source, freshness_detail=detail,
                                                             depth_usd=depth), kind=telegram_bot.KIND_NEWS)
        except Exception as exc:  # noqa: BLE001
            logger.warn(f"[news] fire message failed: {exc}")

    # ---- jumps: tape first ----
    def scan_jumps(self, now: Optional[float] = None) -> int:
        now = time.time() if now is None else now
        n = 0
        try:
            found = self.jumps.scan(now)
        except Exception as exc:  # noqa: BLE001
            logger.warn(f"[news] jump scan failed: {exc}")
            return 0
        for jp in found:
            c = self._by_condition(jp.condition_id)
            if c is None:
                continue
            watched = any(self.book.best(str(t)) is not None for t in c.token_ids)
            row = leads_mod.JumpRow(jump_id=f"{jp.condition_id}:{int(jp.ts // 60)}", ts=jp.ts,
                                    condition_id=jp.condition_id, market_id=str(c.market_id),
                                    question=c.question, domains=tuple(c.domains), delta_cents=jp.delta_cents,
                                    from_price=jp.from_price, to_price=jp.to_price, notional=jp.notional,
                                    n_trades=jp.n_trades, watched=watched)
            if not self.leads.add_jump(row):
                continue
            self.leads.attribute(row, list(self.recent), lookback_s=self.lead_lookback_s)
            n += 1
            logger.info(f"[news] jump {jp.delta_cents:+.0f}c '{c.question[:50]}' "
                        f"{'dark' if row.dark else f'first {row.first_source} lead {row.lead_s:+.0f}s'}")
            # tape-first book: a jump explained by a headline within five minutes
            if not row.dark and row.lead_s is not None and -120 <= row.lead_s <= 300:
                it = self.item_by_id.get(row.first_item_id)
                side = 0 if jp.delta_cents >= 0 else (1 if len(c.token_ids) > 1 else 0)
                tok = str(c.token_ids[side]) if c.token_ids else ""
                if tok and it is not None:
                    self._touch(tok, now)
                    self.books["tape-first"].fire(
                        item_id=it.id, source=it.source, domains=tuple(c.domains), market_id=str(c.market_id),
                        condition_id=jp.condition_id, token_id=tok,
                        outcome=c.outcomes[side] if side < len(c.outcomes) else "", question=c.question,
                        published_ts=it.published_ts, seen_ts=it.seen_ts, decided_ts=now, freshness="moving",
                        confidence=0.0, why=f"tape-first: jump {jp.delta_cents:+.0f}c explained by {it.source}")
        return n

    # ---- marks, surprise pings, settlement ----
    def mark_all(self, now: Optional[float] = None) -> int:
        now = time.time() if now is None else now
        n = 0
        for b in self.books.values():
            try:
                n += b.mark(now)
            except Exception as exc:  # noqa: BLE001
                logger.warn(f"[news] mark failed for {b.book}: {exc}")
        # the item ledger: cents moved our way since decision, per horizon
        for it in list(self.leads.items.values()):
            if it.mid_at_decision is None:
                continue
            tok, direction = self.item_dir.get(it.item_id, (it.token_id, it.direction))
            for h, secs in paper_mod.HORIZONS_S.items():
                if h in it.moved or now < it.quote_ts + secs:
                    continue
                b = self.book.best(tok)
                mid = (b[0] + b[1]) / 2 if (b and b[0] is not None and b[1] is not None) else None
                cents = None if mid is None else round((mid - it.mid_at_decision) * 100 * (1 if direction != "no" else -1), 1)
                self.leads.mark_item(it.item_id, h, cents)
                if (cents is not None and not it.fired and cents >= self.move_cents
                        and h in ("30m", "2h") and it.item_id not in self.pinged):
                    self.pinged.add(it.item_id)
                    self._ping(brief_mod.missed_move_message(it.question, cents, h, it.source))
        return n

    def settle_all(self) -> int:
        from src.copy_trading.copy_paper import REFUNDED
        from src.copy_trading.copy_paper_live import resolve

        def resolver(condition_id: str):
            idx = resolve(condition_id)
            if idx is None:
                return None
            if idx == REFUNDED:
                return "REFUND"
            c = self._by_condition(condition_id)
            if c is None or idx >= len(c.token_ids):
                return None
            return str(c.token_ids[idx])
        n = 0
        for b in self.books.values():
            try:
                n += b.settle(resolver)
            except Exception as exc:  # noqa: BLE001
                logger.warn(f"[news] settle failed for {b.book}: {exc}")
        return n

    def _is_repeat(self, item_stems: set, cand_ids: set, now: float, window_s: float = 1800.0,
                   min_jaccard: float = 0.5) -> bool:
        for ts, st, ids in reversed(self.judged_recent):
            if now - ts > window_s:
                break
            if not (ids & cand_ids) or not st:
                continue
            union = len(st | item_stems)
            if union and len(st & item_stems) / union >= min_jaccard:
                return True
        return False

    _DAY_FIELDS = ("day_items", "day_stale", "day_unmatched", "day_paced", "day_judged", "day_material",
                   "day_repeat")

    def _load_day(self) -> None:
        try:
            with open(self._day_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        for name in self._DAY_FIELDS:
            row = data.get(name)
            if isinstance(row, dict):
                getattr(self, name).update({str(k): int(v) for k, v in row.items() if isinstance(v, (int, float))})

    def _save_day(self, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        keep = {time.strftime("%Y-%m-%d", time.gmtime(now - 86400 * i)) for i in range(3)}
        data = {name: {k: v for k, v in getattr(self, name).items() if k in keep} for name in self._DAY_FIELDS}
        try:
            tmp = self._day_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self._day_path)
        except OSError as exc:
            logger.warn(f"[news] day counters not saved: {exc}")

    def _load_recent(self) -> list:
        out = []
        try:
            cutoff = time.time() - 86400
            with open(self._recent_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        it = Item.from_dict(json.loads(line))
                    except Exception:  # noqa: BLE001
                        continue
                    if it.published_ts >= cutoff:
                        out.append(it)
        except OSError:
            pass
        return out

    def _save_recent(self) -> None:
        try:
            tmp = self._recent_path + ".tmp"
            cutoff = time.time() - 86400
            with open(tmp, "w", encoding="utf-8") as f:
                for it in self.recent:
                    if it.published_ts >= cutoff:
                        f.write(json.dumps(it.to_dict()) + "\n")
            os.replace(tmp, self._recent_path)
        except OSError as exc:
            logger.warn(f"[news] recent window not saved: {exc}")

    def _load_pinged(self) -> set:
        try:
            with open(self._pinged_path, encoding="utf-8") as f:
                return set(json.load(f))
        except (OSError, ValueError):
            return set()

    def _save_pinged(self) -> None:
        try:
            tmp = self._pinged_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(sorted(self.pinged)[-5000:], f)
            os.replace(tmp, self._pinged_path)
        except OSError as exc:
            logger.warn(f"[news] pinged set not saved: {exc}")

    def _ping(self, text: str) -> None:
        self._save_pinged()
        try:
            from src import telegram_bot
            telegram_bot.send_message(text, kind=telegram_bot.KIND_NEWS)
        except Exception as exc:  # noqa: BLE001
            logger.warn(f"[news] ping failed: {exc}")

    def check_silence(self, now: float) -> None:
        """A silent source is a count in the brief's machinery line, never a
        message (owner, 2026-10-25: "messages should be when something is
        found"). The one alarm left is the whole box going quiet."""
        if self.last_item_ts and now - self.last_item_ts > 1800 and "quiet" not in self.pinged:
            self.pinged.add("quiet")
            self._ping(brief_mod.quiet_box_message((now - self.last_item_ts) / 60))
        if self.last_item_ts and now - self.last_item_ts <= 1800:
            self.pinged.discard("quiet")

    # ---- the brief and /news ----
    def report_text(self, since_ts: float = 0.0, label: str = "", now: Optional[float] = None) -> str:
        now = time.time() if now is None else now
        books = {b: paper_mod.summary(pb.ledger) for b, pb in self.books.items()}
        stats = self.leads.stats(since_ts=since_ts, move_cents=self.move_cents)
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        today = {"items": self.day_items.get(day, 0), "stale": self.day_stale.get(day, 0),
                 "unmatched": self.day_unmatched.get(day, 0), "paced": self.day_paced.get(day, 0),
                 "judged": self.day_judged.get(day, 0), "material": self.day_material.get(day, 0),
                 "repeat": self.day_repeat.get(day, 0)}
        llm = {"today": self.budget.count_today(), "limit": self.budget.limit,
               "exhausted": self.budget.count_today() >= self.budget.limit}
        return brief_mod.brief_text(stats=stats, books=books, today=today, roster=self.counters.snapshot(),
                                    llm=llm, since_label=label or "since boot")

    async def brief_loop(self):
        hh, mm = (int(x) for x in self.brief_utc.split(":"))
        while not self.stop.is_set():
            now = time.time()
            t = time.gmtime(now)
            target = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, hh, mm, 0, 0, 0, 0)) - time.timezone
            if target <= now:
                target += 86400
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=target - now)
                return
            except asyncio.TimeoutError:
                pass
            try:
                self._ping(self.report_text(since_ts=time.time() - 86400, label="last 24h"))
            except Exception as exc:  # noqa: BLE001
                logger.warn(f"[news] brief failed: {exc}")

    # ---- the owner's thumb ----
    def owner_text(self, text: str, msg: dict) -> None:
        ts = float(msg.get("forward_date") or msg.get("date") or time.time())
        item = Item(id=make_id("owner", str(msg.get("message_id") or int(time.time()))), source="owner",
                    domains=self.domains, published_ts=ts, seen_ts=time.time(),
                    title=text[:200], text=text, url="")
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            logger.warn("[news] queue full; owner item dropped")

    # ---- loops ----
    async def consume(self):
        while not self.stop.is_set():
            try:
                item = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            self.hwm["queue"] = max(self.hwm["queue"], self.queue.qsize())
            try:
                await asyncio.get_running_loop().run_in_executor(None, self.process_item, item)
            except Exception as exc:  # noqa: BLE001
                logger.warn(f"[news] item failed: {exc}")

    async def periodic(self):
        last_index = 0.0
        last_settle = 0.0
        last_hwm = 0.0
        while not self.stop.is_set():
            now = time.time()
            loop = asyncio.get_running_loop()
            try:
                if now - last_index > 600:
                    last_index = now
                    await loop.run_in_executor(None, self.index.refresh)
                    self._cid_cache = {}
                    self.seed_watch(now)
                    st = self.index.stats()
                    logger.info(f"[news] index: {st.get('n_markets')} markets")
                await loop.run_in_executor(None, self.scan_jumps, now)
                await loop.run_in_executor(None, self.mark_all, now)
                if now - last_settle > 1800:
                    last_settle = now
                    await loop.run_in_executor(None, self.settle_all)
                self.check_silence(now)
                self.buckets.prune(now)
                self.comments.prune(now)
                self.counters.save(now)
                self.dedup.save()
                self._save_recent()
                self._save_day(now)
                if now - last_hwm > 3600:
                    last_hwm = now
                    logger.info(f"[news] high-water: watch {self.hwm['watch']} tokens, recent {self.hwm['recent']} "
                                f"items, queue {self.hwm['queue']}, buckets {len(list(self.buckets.keys()))} markets, "
                                f"llm {self.budget.count_today()}/{self.budget.limit}, jumps under the money bar {self.jumps.below_bar}")
            except Exception as exc:  # noqa: BLE001
                logger.warn(f"[news] periodic failed: {exc}")
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass

    async def watch_shutdown(self):
        while not self.shutdown.is_set():
            await asyncio.sleep(1.0)
        self.stop.set()

    async def main(self):
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self.index.refresh)
        except Exception as exc:  # noqa: BLE001
            logger.warn(f"[news] first index refresh failed: {exc}")
        self.seed_watch()
        st = self.index.stats()
        logger.info(f"[news] started: {len(self.roster)} sources, domains {','.join(self.domains)}, "
                    f"index {st.get('n_markets')} markets, model {self.model}, "
                    f"llm budget {self.budget.limit}/day, stake ${paper_mod.stake_usd():.0f}")
        try:
            from src import telegram_bot
            telegram_bot.on_owner_text = self.owner_text
        except Exception:  # noqa: BLE001
            pass
        bsky = [s for s in self.roster if s.kind == "bsky"]
        dids = {}
        if bsky:
            try:
                dids = await loop.run_in_executor(None, bluesky.resolve_dids, [s.handle for s in bsky])
            except Exception as exc:  # noqa: BLE001
                logger.warn(f"[news] bluesky DID resolution failed: {exc}")
        domains_by_handle = {s.handle: s.domains for s in bsky}
        tasks = [
            asyncio.create_task(poller.run_pollers(self.roster, self.queue, self.dedup, self.counters, stop=self.stop)),
            asyncio.create_task(livedata.stream_trades(self._on_trade, self._on_comment, stop=self.stop)),
            asyncio.create_task(clob_ws.stream_quotes(self.watched_tokens, self.book, stop=self.stop)),
            asyncio.create_task(self.consume()),
            asyncio.create_task(self.periodic()),
            asyncio.create_task(self.brief_loop()),
            asyncio.create_task(self.watch_shutdown()),
        ]
        if dids:
            tasks.append(asyncio.create_task(bluesky.stream(
                self.queue, dids, domains_by_handle=domains_by_handle, stop=self.stop,
                dedup=self.dedup, counters=self.counters)))
        tasks.extend(self.optional_source_tasks())
        await asyncio.gather(*tasks, return_exceptions=True)
        self.counters.save(force=True)
        self.dedup.save(force=True)

    def optional_source_tasks(self) -> list:
        """Sources that need the owner's own credentials (2026-10-25): the
        Telegram client API (his user session) and X (his cookies). Each runs
        only when its keys are in the environment; absent keys mean the bot
        runs on the free sources and says so once."""
        tasks = []
        from src.newsbot.sources import telegram_mtproto
        if telegram_mtproto.enabled():
            tasks.append(asyncio.create_task(telegram_mtproto.stream(
                self.queue, self.dedup, self.counters, stop=self.stop)))
            logger.info("[news] telegram client API source on (owner session)")
        else:
            logger.info("[news] telegram client API source off: TELEGRAM_API_ID/HASH/USER_SESSION not set")
        try:
            from src.newsbot.sources import x_cookies
        except ImportError:
            x_cookies = None
        if x_cookies is not None and x_cookies.enabled():
            tasks.append(asyncio.create_task(x_cookies.run(
                self.queue, self.dedup, self.counters, stop=self.stop)))
            logger.info("[news] X source on (owner cookies, one List)")
        else:
            logger.info("[news] X source off: X_AUTH_TOKEN/X_CT0/X_LIST_ID not set")
        return tasks

    def _on_trade(self, t):
        self.buckets.add(t)

    def _on_comment(self, c):
        self.comments.add(c)


_RUNNER: Optional[Runner] = None


def _register(r: Runner) -> None:
    global _RUNNER
    _RUNNER = r


def run_forever(shutdown: threading.Event) -> None:
    """Thread target: one asyncio loop for the whole news bot."""
    try:
        r = Runner(shutdown)
        asyncio.run(r.main())
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[news] runner died: {exc}")


def news_text(command: str = "") -> str:
    """/news: the current picture from the running bot, or from the ledgers on
    disk when the bot is not running in this process."""
    if _RUNNER is not None:
        since = 0.0
        label = "since boot"
        if "today" in command:
            t = time.gmtime()
            since = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, 0)) - time.timezone
            label = "today (UTC)"
        return _RUNNER.report_text(since_ts=since, label=label)
    d = data_dir()
    books = {b: paper_mod.summary(paper_mod.PaperLedger(b, os.path.join(d, f"paper-{b}.jsonl")))
             for b in paper_mod.BOOKS}
    leads = leads_mod.LeadLedger(os.path.join(d, "leads.jsonl"))
    return brief_mod.brief_text(stats=leads.stats(), books=books, today={"items": 0},
                                roster=brief_mod.load_roster_counters(os.path.join(d, "roster.json")),
                                llm={"today": 0, "limit": 0}, since_label="from disk (bot not running here)")
