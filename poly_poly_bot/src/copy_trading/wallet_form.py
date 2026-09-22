"""Form: is a followed wallet winning NOW, on its own money?

The gate admits on a wallet's whole paper history. Nothing judged current
form until 2026-09-13, when all three "proven" wallets turned out to be at
or below break-even for the week we went live on them (our 14 copies: 7
won, 7 lost, -20%, with fills within a cent of theirs). The owner: "this is
exactly what the watcher should be doing: which one wins now, which don't,
pausing and unpausing."

Every FORM_EVERY_S the guard loop reads each set-Z wallet's own trades from
Polymarket's public data api, takes the last FORM_DAYS on the slice we copy
(bets of at least the evidence base's minimum), and computes: settled n,
hit rate, average buy price (the break-even hit rate), net percent. A
wallet is IN FORM when n >= FORM_MIN_N, hit rate exceeds break-even by
FORM_MIN_EDGE_PTS points, and net >= FORM_MIN_NET_PCT. Anything else,
including too few recent bets to know, is BENCHED: the sink skips it with a
row and a receipt. The arm, the gate and eviction are untouched: the bench
is a rolling filter. With no wallet in form, live copying pauses on its own
and resumes when one qualifies; the owner is told once per episode.

The cloud routine may override within set Z (verdict kind wallet_action,
bench or unbench, applied at the next guard pass with a receipt); the rail
re-evaluates on its own schedule and the routine's call holds until then
only if it agrees with the numbers, or for FORM_OVERRIDE_S when it does not.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Callable, Optional

from src.config import CONFIG
from src.logger import logger

FORM_FILE = "wallet-form.json"
DATA_API = "https://data-api.polymarket.com"


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


FORM_DAYS = _env_f("FORM_DAYS", 14.0)
FORM_MIN_N = int(_env_f("FORM_MIN_N", 30))
FORM_MIN_EDGE_PTS = _env_f("FORM_MIN_EDGE_PTS", 3.0)
FORM_MIN_NET_PCT = _env_f("FORM_MIN_NET_PCT", 2.0)
FORM_EVERY_S = _env_f("FORM_EVERY_S", 6 * 3600.0)
FORM_OVERRIDE_S = _env_f("FORM_OVERRIDE_S", 24 * 3600.0)
# The read is TIME-scoped (see fetch_rows). Rows this far before the window
# are still read so a market's FIRST buy is seen even when it predates the
# window; FORM_MAX_ROWS is a hard stop on a runaway wallet, not the window.
FORM_LOOKBACK_DAYS = _env_f("FORM_LOOKBACK_DAYS", 28.0)
FORM_MAX_ROWS = int(_env_f("FORM_MAX_ROWS", 20000))
FORM_STALE_S = _env_f("FORM_STALE_S", 4 * FORM_EVERY_S)   # a kept verdict this old is shown as stale
# A read that failed is retried with this backoff (doubling, capped), never
# every guard pass: 2026-09-19..22 the catch-up hit the same wall 342 times a
# day for two wallets, one page walk from offset 0 each time.
FORM_RETRY_MIN_S = _env_f("FORM_RETRY_MIN_S", 15 * 60.0)
FORM_RETRY_MAX_S = _env_f("FORM_RETRY_MAX_S", 6 * 3600.0)
# A set-Z wallet unreadable this long is said once, on the phone, not only in
# a warning line among thousands.
FORM_UNREAD_ALERT_S = _env_f("FORM_UNREAD_ALERT_S", 6 * 3600.0)
# The data api refuses to page past this offset (HTTP 400 "max historical
# activity offset of 5000 exceeded", measured 2026-09-20). With 500-row pages
# the read ceiling is 5,500 rows, about 12 days of a wallet that trades 430
# rows a day. A capped read is a SHORTER window, said so on the record, not a
# failed read: the old code threw the 5,500 rows away, called it "throttled",
# and benched the three best wallets in set Z on a record 172 hours old.
DATA_API_MAX_OFFSET = 5000
FORM_VERSION = 3   # bump when compute() changes: a table from an older compute is rescanned at boot


@dataclass
class Form:
    wallet: str
    n: int = 0
    won: int = 0
    cost: float = 0.0
    back: float = 0.0
    avg_price: float = 0.0
    worst_day: float = 0.0            # display only: the worst net day in the window
    ok: bool = False
    reason: str = ""
    ts: float = 0.0
    # Coverage of the read behind this verdict (T1, 2026-09-22): how many
    # rows, how many days they reach back, and whether the api's offset cap
    # cut the window short. A verdict over 12.8 days says so; it never
    # pretends to be 14.
    rows: int = 0
    covered_days: float = 0.0
    capped: bool = False

    @property
    def hit(self) -> float:
        return self.won / self.n if self.n else 0.0

    @property
    def net_pct(self) -> float:
        return (self.back - self.cost) / self.cost * 100.0 if self.cost else 0.0

    def line(self) -> str:
        cap = ""
        if self.capped:
            # The api's offset cap stopped the read. Either the window itself
            # is short (the days say how short) or only the older lookback
            # for the first-buy exclusion was cut.
            cap = (f" (capped: {self.covered_days:.1f} of {FORM_DAYS:.0f} days read, {self.rows} rows)"
                   if self.covered_days < FORM_DAYS - 0.05
                   else f" (capped: window read in full, older lookback cut, {self.rows} rows)")
        if not self.n:
            return f"{self.wallet[:10]}: no settled bets on our slice in {FORM_DAYS:.0f} days{cap}"
        return (f"{self.wallet[:10]}: {self.n} settled, {self.hit * 100:.0f}% won vs "
                f"{self.avg_price * 100:.0f}% needed, net {self.net_pct:+.1f}% on ${self.cost:,.0f}"
                f", worst day {self.worst_day:+,.0f}{cap}")


def _p() -> str:
    return os.path.join(CONFIG.data_dir, FORM_FILE)


def _read() -> dict:
    try:
        with open(_p(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(d: dict) -> None:
    try:
        os.makedirs(CONFIG.data_dir, exist_ok=True)
        tmp = _p() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, _p())
    except OSError as exc:
        logger.error(f"[form] state write failed: {exc}")


# --------------------------------------------------------------------------- #
# The read: public data api, no key
# --------------------------------------------------------------------------- #

class ReadFailed(RuntimeError):
    """A page could not be read: the reason names the HTTP status, never
    "throttled" unless it was a 429. Tracked here, never through the
    discovery sweep's shared failure list (issue #34.4b)."""


@dataclass
class Coverage:
    rows: int = 0
    pages: int = 0
    oldest_ts: float = 0.0
    capped: bool = False

    def covered_days(self, now: float) -> float:
        return max(0.0, (now - self.oldest_ts) / 86400.0) if self.oldest_ts else 0.0


def _page_reader(wallet: str, page_size: int, get=None):
    """The page function: ``get`` (tests) or the data api with its own retry.
    Returns a list, or raises ReadFailed with the status in the message. A
    400 past DATA_API_MAX_OFFSET raises ReadFailed("offset cap") and the
    caller treats it as the end of what can be read, not as a failure."""
    if get is not None:
        def get_page(offset: int):
            if offset > DATA_API_MAX_OFFSET:
                raise ReadFailed("offset cap")
            return get(f"{DATA_API}/activity?user={wallet}&limit={page_size}&offset={offset}")
        return get_page
    import requests
    session = requests.Session()

    def get_page(offset: int):
        if offset > DATA_API_MAX_OFFSET:
            raise ReadFailed("offset cap")
        last = "no response"
        for attempt in range(4):
            try:
                r = session.get(f"{DATA_API}/activity", params={"user": wallet, "limit": page_size, "offset": offset},
                                timeout=30, headers={"User-Agent": "pm-trader-form"})
            except requests.RequestException as exc:
                last = f"network error ({type(exc).__name__})"
                time.sleep(0.25 * (attempt + 1))
                continue
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    raise ReadFailed("HTTP 200 with a non-JSON body")
            if r.status_code == 400 and "offset" in (r.text or "").lower():
                raise ReadFailed("offset cap")
            if r.status_code == 429:
                try:
                    wait = float(r.headers.get("Retry-After") or 0)
                except ValueError:
                    wait = 0.0
                last = "HTTP 429 (throttled)"
                time.sleep(max(wait, 1.0) * (attempt + 1))
                continue
            if 400 <= r.status_code < 500:
                raise ReadFailed(f"HTTP {r.status_code}")
            last = f"HTTP {r.status_code}"
            time.sleep(0.5 * (attempt + 1))
        raise ReadFailed(f"{last} after 4 attempts")
    return get_page


def fetch_rows(wallet: str, *, max_rows: int = FORM_MAX_ROWS, get=None,
               now: Optional[float] = None, days: float = FORM_DAYS) -> tuple[list, list, Coverage]:
    """(activity rows newest first, positions, coverage) for a wallet. ``get``
    is the JSON fetcher (injected for tests).

    Pages newest-first and stops once a page reaches FORM_LOOKBACK_DAYS
    before the window, at ``max_rows``, or at the api's offset cap. The old
    read took the newest 1500 rows with no time bound: a wallet with more
    rows than that in the window had its window silently truncated and a
    large pre-window position redeemed in-window inflated the form (issue
    #34.4a). The cap is the same shape, so it is never silent: the coverage
    says how far back the rows reach, ``compute`` measures over exactly that
    span, and the record prints it.

    A page that cannot be read raises ReadFailed naming the status; the read
    is then a failed read (the last verdict is kept and the retry backs off),
    never a shorter window.
    """
    now = time.time() if now is None else now
    cutoff = now - (days + FORM_LOOKBACK_DAYS) * 86400
    page_size = 500 if get is None else 100
    get_page = _page_reader(wallet, page_size, get)
    if get is None:
        import httpx

        def get_positions():
            r = httpx.get(f"{DATA_API}/positions?user={wallet}&sizeThreshold=1&limit=500",
                          timeout=30.0, headers={"User-Agent": "pm-trader-form"})
            r.raise_for_status()
            return r.json() or []
    else:
        def get_positions():
            return get(f"{DATA_API}/positions?user={wallet}&sizeThreshold=1&limit=500") or []

    acts: list = []
    cov = Coverage()
    offset = 0
    while offset < max_rows:
        try:
            page = get_page(offset)
        except ReadFailed as exc:
            if "offset cap" in str(exc) and acts:
                cov.capped = True
                break
            raise
        if not page:
            break
        acts.extend(page)
        cov.pages += 1
        offset += page_size
        oldest = min((_ts(a) for a in page), default=0.0)
        if oldest:
            cov.oldest_ts = oldest if not cov.oldest_ts else min(cov.oldest_ts, oldest)
        if len(page) < page_size:
            break
        if oldest and oldest < cutoff:
            break
    cov.rows = len(acts)
    return acts, get_positions(), cov


def _ts(row: dict) -> float:
    try:
        return float(row.get("timestamp") or 0)
    except (TypeError, ValueError, AttributeError):
        return 0.0


def compute(wallet: str, acts: list, pos: list, *, now: Optional[float] = None,
            days: float = FORM_DAYS, min_bet: Optional[float] = None,
            coverage: Optional[Coverage] = None) -> Form:
    """Form from the rows. A market counts once, on the rows the bot would
    have copied (each BUY row of at least the slice minimum, the sink's own
    trigger); a market whose first buy predates the window is left out so a
    stale payout cannot inflate the window; SELL rows are inflow (an exit is
    not a loss); a REDEEM counts its usdcSize only; a market is open while
    the wallet still holds it; it is WON when it came out ahead."""
    now = time.time() if now is None else now
    since = now - days * 86400
    capped = bool(coverage and coverage.capped)
    if capped and coverage.oldest_ts > since:
        # The api's cap cut the rows before the window's start: measure over
        # the days actually read. A market whose first SEEN buy is before
        # this point is left out exactly as before, so a payout without its
        # cost in the rows cannot inflate the form (issue #34.4a's rule, kept).
        since = coverage.oldest_ts
    floor = float(min_bet if min_bet is not None else getattr(CONFIG, "copy_paper_min_usd", 300.0) or 300.0)
    first_buy: dict = {}
    by_cond: dict = {}
    inflow: dict = {}
    day_of: dict = {}
    for a in acts:
        try:
            ts = float(a.get("timestamp") or 0)
        except (TypeError, ValueError):
            continue
        cid = str(a.get("conditionId") or "")
        if not cid:
            continue
        t = a.get("type")
        if t == "TRADE" and a.get("side") == "BUY":
            first_buy[cid] = min(first_buy.get(cid, ts), ts)
            usd = float(a.get("usdcSize") or 0)
            if ts >= since and usd >= floor:
                c = by_cond.setdefault(cid, {"cost": 0.0, "sh": 0.0})
                c["cost"] += usd
                c["sh"] += float(a.get("size") or 0)
                day_of.setdefault(cid, time.strftime("%Y-%m-%d", time.gmtime(ts)))
        elif t == "TRADE" and a.get("side") == "SELL" and ts >= since:
            inflow[cid] = inflow.get(cid, 0.0) + float(a.get("usdcSize") or 0)
        elif t == "REDEEM" and ts >= since:
            inflow[cid] = inflow.get(cid, 0.0) + float(a.get("usdcSize") or 0)
    open_c: set = set()
    unclaimed: dict = {}
    for p in pos or []:
        cid = str(p.get("conditionId") or "")
        cur = float(p.get("curPrice") or 0)
        val = float(p.get("currentValue") or 0)
        if p.get("redeemable"):
            if val >= 1:
                unclaimed[cid] = val
        elif val > 1 and 0.0 < cur < 1.0:
            open_c.add(cid)
    f = Form(wallet=wallet.lower(), ts=now, capped=capped,
             rows=(coverage.rows if coverage else len(acts)),
             covered_days=min(days, (now - since) / 86400.0) if capped else days)
    sh = 0.0
    per_day: dict = {}
    for cid, c in by_cond.items():
        if cid in open_c or first_buy.get(cid, since) < since:
            continue
        f.n += 1
        f.cost += c["cost"]
        sh += c["sh"]
        back = inflow.get(cid, 0.0) + unclaimed.get(cid, 0.0)
        if back > c["cost"]:
            f.won += 1
        f.back += back
        d0 = day_of.get(cid, "")
        per_day[d0] = per_day.get(d0, 0.0) + (back - c["cost"])
    f.worst_day = round(min(per_day.values()), 2) if per_day else 0.0
    f.avg_price = (f.cost / sh) if sh else 0.0
    f.cost = round(f.cost, 2)
    f.back = round(f.back, 2)
    span = f.covered_days if capped else days
    if f.n < FORM_MIN_N:
        f.ok, f.reason = False, f"only {f.n} settled bets on our slice in {span:.0f} days (need {FORM_MIN_N})"
    else:
        edge = (f.hit - f.avg_price) * 100.0
        if edge < FORM_MIN_EDGE_PTS:
            f.ok, f.reason = False, (f"{f.hit * 100:.0f}% came out ahead vs {f.avg_price * 100:.0f}% needed "
                                     f"({edge:+.0f} points, need +{FORM_MIN_EDGE_PTS:.0f})")
        elif f.net_pct < FORM_MIN_NET_PCT:
            f.ok, f.reason = False, f"net {f.net_pct:+.1f}% (need +{FORM_MIN_NET_PCT:.0f}%)"
        else:
            f.ok, f.reason = True, f"{f.hit * 100:.0f}% came out ahead vs {f.avg_price * 100:.0f}% needed, net {f.net_pct:+.1f}%"
    return f


# --------------------------------------------------------------------------- #
# The bench
# --------------------------------------------------------------------------- #

def is_benched(wallet: str, now: Optional[float] = None) -> tuple[bool, str]:
    """May the sink copy this wallet? Benched until the first scan says it is
    in form (unknown is benched: the owner's 'better less deals')."""
    now = time.time() if now is None else now
    d = _read()
    w = (wallet or "").lower()
    ov = (d.get("overrides") or {}).get(w)
    if ov and ov.get("action") == "bench" and now - float(ov.get("ts") or 0) < FORM_OVERRIDE_S:
        return (True, f"routine bench: {str(ov.get('why') or '')[:80]}")
    rec = (d.get("wallets") or {}).get(w)
    if not rec:
        un = (d.get("unread") or {}).get(w)
        if un:
            return (True, f"no form record: {str(un.get('why') or 'read failed')[:60]}, "
                          f"{int(un.get('tries') or 0)} tries")
        return (True, "no form record yet (the scan runs every 6 hours)")
    age = now - float(rec.get("ts") or now)
    verdict = (not bool(rec.get("ok")), str(rec.get("reason") or ""))
    if age >= FORM_STALE_S:
        # Reads kept failing. The last MEASURED verdict holds (manager ruling
        # s-qbzbrw, 2026-09-22: the three best wallets in Z were benched for
        # three days on a read bug, not on evidence), and the staleness is
        # said on the row and pushed once by the scan, never hidden.
        return (verdict[0], f"{verdict[1]} [stale {age / 3600:.0f} h, reads failing]")
    return verdict


def needs_rescan() -> bool:
    """A table written by an older compute() (or none): the guard scans at
    once instead of honouring the old clock."""
    d = _read()
    return bool(d.get("wallets")) and int(d.get("version") or 0) != FORM_VERSION


def in_form_wallets(now: Optional[float] = None) -> list[str]:
    """The wallets not benched at ``now`` (the wall clock when not given).

    The clock is injectable because ``scan`` computes every verdict at its own
    ``now`` and then asks this question: reading the wall clock here answered
    it at a *different* instant. Harmless in production, where the two are the
    same second, and wrong everywhere the clock is supplied — a scan replayed
    over historical rows, and the tests, which pin a fixed ``NOW`` and started
    failing the moment real time passed it by more than FORM_OVERRIDE_S.
    """
    d = _read()
    now = time.time() if now is None else now
    out = []
    for w, rec in (d.get("wallets") or {}).items():
        b, _ = is_benched(w, now)
        if not b:
            out.append(w)
    return sorted(out)


def apply_override(wallet: str, action: str, why: str, now: Optional[float] = None) -> bool:
    """The cloud routine's call, within set Z only. Holds for FORM_OVERRIDE_S."""
    now = time.time() if now is None else now
    action = str(action or "").lower()
    if action not in ("bench", "unbench"):
        return False
    from src.copy_trading import zset
    w = (wallet or "").lower()
    if w not in zset.wallet_set():
        return False
    d = _read()
    ovs = d.setdefault("overrides", {})
    if action == "unbench":
        # Monotone: the routine lifts only its own ACTIVE bench, never the bar's.
        prev = ovs.get(w)
        if not prev or prev.get("action") != "bench" or now - float(prev.get("ts") or 0) >= FORM_OVERRIDE_S:
            return False
        ovs.pop(w, None)
        _write(d)
        return True
    ovs[w] = {"action": action, "why": str(why or "")[:200], "ts": now}
    _write(d)
    return True


def wallets_without_record() -> list[str]:
    """Set-Z wallets the table has never measured (admitted by another path,
    or read failed on their first scan)."""
    from src.copy_trading import zset
    have = set((_read().get("wallets") or {}).keys())
    return sorted(w for w in zset.wallet_set() if w not in have)


def wallets_due_for_catchup(now: Optional[float] = None) -> list[str]:
    """The wallets whose retry is due: unmeasured ones, and ones holding a
    kept verdict whose last read failed (their row says "next try HH:MM",
    and that line was a lie while only record-less wallets were retried,
    verifier s-qbzbrw). A failed read schedules the next try with a doubling
    backoff (FORM_RETRY_MIN_S .. FORM_RETRY_MAX_S); before that the guard
    leaves the wallet alone instead of walking the same pages into the same
    wall every pass."""
    from src.copy_trading import zset
    now = time.time() if now is None else now
    unread = _read().get("unread") or {}
    z = zset.wallet_set()
    due = set(wallets_without_record())
    due |= {w for w in unread if w in z}
    return sorted(w for w in due if float((unread.get(w) or {}).get("next") or 0) <= now)


def _note_unread(d: dict, w: str, why: str, now: float) -> dict:
    """Record a failed read: first failure, tries, and when to try again."""
    un = d.setdefault("unread", {})
    rec = dict(un.get(w) or {})
    tries = int(rec.get("tries") or 0) + 1
    backoff = min(FORM_RETRY_MAX_S, FORM_RETRY_MIN_S * (2 ** (tries - 1)))
    rec.update({"since": float(rec.get("since") or now), "tries": tries,
                "next": now + backoff, "why": str(why)[:120], "told": bool(rec.get("told"))})
    un[w] = rec
    return rec


def scan(*, get=None, send: Optional[Callable[[str], None]] = None,
         now: Optional[float] = None, wallets: Optional[list] = None) -> dict:
    """Recompute the form of the given (default: every set-Z) wallet, persist,
    receipt and push changes, and say once per episode when nobody is in
    form. A failed read keeps the last verdict and never flips one; a wallet
    never measured stays absent (benched, and caught up next pass). The
    pause notice is stamped only when it was delivered. Returns the table."""
    from src.copy_trading import ops_watch, zset
    now = time.time() if now is None else now
    prev = _read()
    prev_w = dict(prev.get("wallets") or {})
    ws = list(wallets) if wallets is not None else sorted(zset.wallet_set())
    table: dict = dict(prev_w) if wallets is not None else {}
    unread: dict = dict(prev.get("unread") or {})
    scratch = {"unread": unread}
    measured = 0
    for w in ws:
        try:
            acts, pos, cov = fetch_rows(w, get=get, now=now)
            f = compute(w, acts, pos, now=now, coverage=cov)
        except Exception as exc:
            rec = _note_unread(scratch, w, str(exc), now)
            logger.warn(f"[form] could not read {w[:10]}: {exc} (try {rec['tries']}, "
                        f"next in {(rec['next'] - now) / 60:.0f} min)")
            old = prev_w.get(w)
            if old:
                table[w] = old
            # Said once per episode, on the phone, when a followed wallet has
            # been unmeasurable for hours: a warning line among thousands is
            # how the 2026-09-19 failure stayed invisible for three days.
            if (now - float(rec["since"])) >= FORM_UNREAD_ALERT_S and not rec.get("told"):
                held = "the last verdict holds" if old else "it is benched until a read succeeds"
                delivered = _send(send, f"\U0001f4ed <b>Cannot measure</b> <code>{w}</code>: {rec['why'][:100]}; "
                                        f"{rec['tries']} tries since {time.strftime('%m-%d %H:%M', time.gmtime(rec['since']))} UTC; {held}.")
                ops_watch.receipt("form_unreadable", before=f"{w[:10]} {rec['tries']} failed reads",
                                  after=held, detail=rec["why"][:120], now=now,
                                  push="WALLET" if delivered else None, extra={"wallet": w})
                rec["told"] = bool(delivered)
            continue
        measured += 1
        unread.pop(w, None)
        table[w] = {**asdict(f), "hit": round(f.hit, 4), "net_pct": round(f.net_pct, 2)}
        was = prev_w.get(w, {}).get("ok")
        if was is not None and bool(was) != f.ok:
            delivered = _send(send, ("🟢 <b>Back in form</b>" if f.ok else "🪑 <b>Benched</b>") + f": <code>{w}</code>\n{f.line()}")
            ops_watch.receipt("form", before=f"{w[:10]} {'in form' if was else 'benched'}",
                              after="in form" if f.ok else "benched", detail=f.line(), now=now,
                              push="WALLET" if delivered else None, extra={"wallet": w})
        elif was is None:
            ops_watch.receipt("form", before=f"{w[:10]} unknown", after="in form" if f.ok else "benched",
                              detail=f.line(), now=now, extra={"wallet": w})
    # drop wallets that left set Z (a full scan only); purge expired routine overrides
    zs = zset.wallet_set() if wallets is None else (set(ws) | set(prev_w))
    table = {w: r for w, r in table.items() if w in zs}
    ovs = {w: o for w, o in (prev.get("overrides") or {}).items()
           if now - float(o.get("ts") or 0) < FORM_OVERRIDE_S and w in zs}
    # only a full scan vouches for the whole table's compute version
    ver = FORM_VERSION if wallets is None else int(prev.get("version") or 0)
    # A wallet can hold a kept (stale) verdict AND be unreadable: both facts
    # stay on the table, the row says so, the retry keeps its backoff.
    unread = {w: r for w, r in unread.items() if w in zs}
    d = {"ts": now, "version": ver, "wallets": table, "overrides": ovs, "unread": unread,
         "paused": bool(prev.get("paused")), "paused_told": bool(prev.get("paused_told"))}
    _write(d)
    active = in_form_wallets(now)
    paused_before = bool(prev.get("paused"))
    paused = (not active) and bool(table)  # nothing measured is not "nobody in form"
    d["paused"] = paused
    if paused and (not paused_before or not prev.get("paused_told")):
        text = ("⏸ <b>Live copying paused</b>: none of the followed wallets is in form on its own money "
                f"(last {FORM_DAYS:.0f} days, bets of ${float(getattr(CONFIG, 'copy_paper_min_usd', 300) or 300):.0f}+). "
                "It resumes on its own when one qualifies. Nothing else changed: the arm, the gate and the paper books keep running.\n"
                + "\n".join(_form_of(r).line() for r in table.values()))
        delivered = _send(send, text)
        ops_watch.receipt("form_pause", before=f"{len(table)} measured", after="0 in form: live copying paused", now=now,
                          push="DEAL" if delivered else None, detail="" if delivered else "NOT delivered")
        d["paused_told"] = bool(delivered)
    elif not paused and paused_before:
        delivered = _send(send, "▶️ <b>Live copying resumes</b>: in form now: " + ", ".join(a[:10] for a in active))
        ops_watch.receipt("form_resume", before="paused", after=f"{len(active)} in form: copying resumes", now=now,
                          push="DEAL" if delivered else None, detail=", ".join(a[:10] for a in active))
        d["paused_told"] = False
    _write(d)
    logger.info(f"[form] scanned {len(ws)} wallet(s), {measured} measured: {len(active)} in form" + (" (paused)" if paused else ""))
    return d


def _form_of(r: dict) -> "Form":
    return Form(**{k: v for k, v in r.items() if k in Form.__dataclass_fields__})


def _send(send, text: str) -> bool:
    """A sender that returns False has not delivered (the Telegram wrapper
    returns False on 4xx/5xx without raising)."""
    if send is None:
        return True
    try:
        r = send(text)
        return r is None or bool(r)
    except Exception as exc:
        logger.warn(f"[form] push failed: {exc}")
        return False


def lines() -> list[str]:
    d = _read()
    out = []
    for w, r in sorted((d.get("wallets") or {}).items()):
        f = _form_of(r)
        b, why = is_benched(w)
        out.append(("in form  " if not b else "benched  ") + f.line())
    for w, r in sorted((d.get("unread") or {}).items()):
        out.append(f"unread   {w[:10]}: {str(r.get('why') or '')[:60]}, {int(r.get('tries') or 0)} tries, "
                   f"next try {time.strftime('%H:%M', time.gmtime(float(r.get('next') or 0)))} UTC")
    if not out:
        out.append("no form scan yet")
    elif d.get("paused"):
        out.append("live copying is paused: nobody in form")
    return out


if __name__ == "__main__":  # python -m src.copy_trading.wallet_form <wallet> [<wallet> ...]
    import sys as _sys
    for _w in _sys.argv[1:]:
        _acts, _pos, _cov = fetch_rows(_w)
        print(compute(_w, _acts, _pos, coverage=_cov).line())
