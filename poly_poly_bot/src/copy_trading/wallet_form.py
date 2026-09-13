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
FORM_MAX_ROWS = int(_env_f("FORM_MAX_ROWS", 1500))
FORM_STALE_S = _env_f("FORM_STALE_S", 4 * FORM_EVERY_S)   # a kept verdict this old is no verdict
FORM_VERSION = 2   # bump when compute() changes: a table from an older compute is rescanned at boot


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

    @property
    def hit(self) -> float:
        return self.won / self.n if self.n else 0.0

    @property
    def net_pct(self) -> float:
        return (self.back - self.cost) / self.cost * 100.0 if self.cost else 0.0

    def line(self) -> str:
        if not self.n:
            return f"{self.wallet[:10]}: no settled bets on our slice in {FORM_DAYS:.0f} days"
        return (f"{self.wallet[:10]}: {self.n} settled, {self.hit * 100:.0f}% won vs "
                f"{self.avg_price * 100:.0f}% needed, net {self.net_pct:+.1f}% on ${self.cost:,.0f}"
                f", worst day {self.worst_day:+,.0f}")


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

def fetch_rows(wallet: str, *, max_rows: int = FORM_MAX_ROWS, get=None) -> tuple[list, list]:
    """(activity rows newest first, positions) for a wallet. ``get`` is the
    JSON fetcher (injected for tests)."""
    if get is None:
        # The discovery fetcher: retries, and a throttled page is never
        # mistaken for "no more trades" (its docstring tells that story). It
        # returns a TRUNCATED list on exhaustion and records the wallet in
        # _activity_fetch_failures instead of raising; here that is a failed
        # read (code review, finding 1).
        from src.copy_trading import discovery_data as _dd
        import httpx
        before = len(_dd._activity_fetch_failures)
        acts = list(_dd.fetch_activity(wallet, None, 0.0, cap=max_rows) or [])
        if len(_dd._activity_fetch_failures) > before:
            del _dd._activity_fetch_failures[before:]
            raise RuntimeError("activity read incomplete (throttled)")
        r = httpx.get(f"{DATA_API}/positions?user={wallet}&sizeThreshold=1&limit=500",
                      timeout=30.0, headers={"User-Agent": "pm-trader-form"})
        r.raise_for_status()
        return acts, (r.json() or [])
    acts: list = []
    offset = 0
    while offset < max_rows:
        page = get(f"{DATA_API}/activity?user={wallet}&limit=100&offset={offset}")
        if not page:
            break
        acts.extend(page)
        offset += 100
        if len(page) < 100:
            break
    pos = get(f"{DATA_API}/positions?user={wallet}&sizeThreshold=1&limit=500") or []
    return acts, pos


def compute(wallet: str, acts: list, pos: list, *, now: Optional[float] = None,
            days: float = FORM_DAYS, min_bet: Optional[float] = None) -> Form:
    """Form from the rows. A market counts once, on the rows the bot would
    have copied (each BUY row of at least the slice minimum, the sink's own
    trigger); a market whose first buy predates the window is left out so a
    stale payout cannot inflate the window; SELL rows are inflow (an exit is
    not a loss); a REDEEM counts its usdcSize only; a market is open while
    the wallet still holds it; it is WON when it came out ahead."""
    now = time.time() if now is None else now
    since = now - days * 86400
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
    f = Form(wallet=wallet.lower(), ts=now)
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
    if f.n < FORM_MIN_N:
        f.ok, f.reason = False, f"only {f.n} settled bets on our slice in {days:.0f} days (need {FORM_MIN_N})"
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
        return (True, "no form record yet (the scan runs every 6 hours)")
    age = now - float(rec.get("ts") or now)
    if age >= FORM_STALE_S:
        # Reads kept failing: the last verdict is not carried forever.
        return (True, f"form record stale ({age / 3600:.0f} h, reads failing)")
    return (not bool(rec.get("ok")), str(rec.get("reason") or ""))


def needs_rescan() -> bool:
    """A table written by an older compute() (or none): the guard scans at
    once instead of honouring the old clock."""
    d = _read()
    return bool(d.get("wallets")) and int(d.get("version") or 0) != FORM_VERSION


def in_form_wallets() -> list[str]:
    d = _read()
    now = time.time()
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
    or read failed on their first scan): the guard catches them up each pass."""
    from src.copy_trading import zset
    have = set((_read().get("wallets") or {}).keys())
    return sorted(w for w in zset.wallet_set() if w not in have)


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
    measured = 0
    for w in ws:
        try:
            acts, pos = fetch_rows(w, get=get)
            f = compute(w, acts, pos, now=now)
        except Exception as exc:
            logger.warn(f"[form] could not read {w[:10]}: {exc}")
            old = prev_w.get(w)
            if old:
                table[w] = old
            continue
        measured += 1
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
    d = {"ts": now, "version": ver, "wallets": table, "overrides": ovs,
         "paused": bool(prev.get("paused")), "paused_told": bool(prev.get("paused_told"))}
    _write(d)
    active = in_form_wallets()
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
    if not out:
        out.append("no form scan yet")
    elif d.get("paused"):
        out.append("live copying is paused: nobody in form")
    return out


if __name__ == "__main__":  # python -m src.copy_trading.wallet_form <wallet> [<wallet> ...]
    import sys as _sys
    for _w in _sys.argv[1:]:
        _acts, _pos = fetch_rows(_w)
        print(compute(_w, _acts, _pos).line())
