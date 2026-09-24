#!/usr/bin/env python3
"""Historical studies: what-ifs over data the box already holds.

Owner (2026-09-24): "some ideas no need to run, can be explored based on
historical data". His example: "what would be happening if I change 300 to
150. How will number of wallets change, which wallets still will be in,
which out, how it will affect pnl."

The unit of every study is the WHO-STAYS / WHO-ENTERS / WHO-LEAVES table
(ideator, s-ye5990): each wallet under both settings with its copy count and
at-their-price ROI, one totals line, and a caveat line the script prints
itself. Frozen once at ``data/exp/studies/<id>.md`` with an inputs hash;
never re-rendered. A fixed menu of parameterised, pure studies; the model
picks a study and its parameters and writes the question in its own words.

  min_usd      the slice floor (300 -> 150): form under both floors, copies
               replayed at their price from each wallet's own activity rows
  form         the form rail's window and floor (days, min_bet)
  first_entry  first entry per market only, or every buy (activity replay)
  wallet_cap   copies per wallet per day, over book B's own rows

Estimates, and said so: activity rows are capped at 5,500 per wallet by the
data api (capped wallets are marked), resolutions come from the bot's
cache, unresolved markets are skipped, replayed copies pay their price
with no drag.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from typing import Callable, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.config import CONFIG  # noqa: E402
from src.copy_trading.entry_profile import is_copyable_entry  # noqa: E402
from src.copy_trading.promotion_gate import FALSIFY_MIN_N  # noqa: E402

STUDY_MAX_WALLETS = int(float(os.environ.get("STUDY_MAX_WALLETS", 60)))
STUDY_DAYS = float(os.environ.get("STUDY_DAYS", 28))
MIN_B_SETTLED = 10

MENU: dict[str, dict] = {
    "min_usd": {"params": {"from": "number", "to": "number"},
                "doc": "the slice floor: who is in form and what the replayed copies earn at floor from vs to"},
    "form": {"params": {"days": "number", "min_bet": "number"},
             "doc": "the form rail's window and floor vs the current FORM_DAYS and slice floor"},
    "first_entry": {"params": {"to": "bool"},
                    "doc": "copy only a wallet's first entry per market (true) or every buy (false)"},
    "wallet_cap": {"params": {"to": "integer"},
                   "doc": "copies per wallet per UTC day over book B's own rows: the current cap vs to"},
}


def menu_lines() -> list[str]:
    return [f"  {k}: params {json.dumps(v['params'])}: {v['doc']}" for k, v in MENU.items()]


# --------------------------------------------------------------------------- #
# Inputs (all injectable)
# --------------------------------------------------------------------------- #

def population(b_rows: list, zset_wallets: set, *, max_wallets: int = STUDY_MAX_WALLETS) -> tuple[list[str], int]:
    """Set Z plus book B's wallets with settled copies, most settled first,
    capped. ``(wallets, total before the cap)``."""
    settled: dict[str, int] = {}
    for r in b_rows:
        if not r.get("closed"):
            continue
        w = str(r.get("target") or "").lower()
        if w:
            settled[w] = settled.get(w, 0) + 1
    pool = {w for w, n in settled.items() if n >= MIN_B_SETTLED} | {w.lower() for w in zset_wallets}
    ordered = sorted(pool, key=lambda w: (-(settled.get(w, 0)), w))
    return (ordered[:max_wallets], len(ordered))


def b_rows_from_disk(path: Optional[str] = None) -> list[dict]:
    p = path or CONFIG.copy_paper_b_ledger
    out = []
    try:
        with open(p, encoding="utf-8") as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    out.append(r)
    except OSError:
        pass
    return out


def resolution_reader(res_dir: Optional[str] = None) -> Callable[[str], Optional[int]]:
    """``winning_index`` for a condition id from the bot's resolution cache,
    None when unresolved or unknown."""
    d = res_dir or CONFIG.wallet_discovery_res_cache
    cache: dict = {}

    def read(cid: str) -> Optional[int]:
        if cid in cache:
            return cache[cid]
        v = None
        try:
            with open(os.path.join(d, f"res_{cid}.json"), encoding="utf-8") as f:
                j = json.load(f)
            wi = j.get("winning_index") if isinstance(j, dict) else None
            v = int(wi) if wi is not None else None
        except (OSError, ValueError, TypeError):
            v = None
        cache[cid] = v
        return v
    return read


def default_fetch(now: float):
    from src.copy_trading import wallet_form

    def fetch(wallet: str):
        acts, pos, cov = wallet_form.fetch_rows(wallet, now=now, days=STUDY_DAYS)
        return acts, pos, cov
    return fetch


# --------------------------------------------------------------------------- #
# The replay: what a copy earns at their price
# --------------------------------------------------------------------------- #

def replay(acts: list, *, floor: float, since: float, first_entry_only: bool,
           resolve: Callable[[str], Optional[int]]) -> tuple[int, float, int]:
    """``(n resolved copies, mean ROI at their price, n unresolved)`` over
    the wallet's BUY rows from ``since`` at or above ``floor`` in the
    copyable band, each held to resolution."""
    seen: set = set()
    rois: list[float] = []
    unresolved = 0
    for a in sorted(acts, key=lambda r: float(r.get("timestamp") or 0)):
        if a.get("type") != "TRADE" or a.get("side") != "BUY":
            continue
        try:
            ts = float(a.get("timestamp") or 0)
            price = float(a.get("price") or 0)
            usd = float(a.get("usdcSize") or 0) or float(a.get("size") or 0) * price
        except (TypeError, ValueError):
            continue
        cid = str(a.get("conditionId") or "")
        if not cid or ts < since or usd < floor or price <= 0 or not is_copyable_entry(price):
            continue
        oi = a.get("outcomeIndex")
        if first_entry_only:
            key = (cid, oi)
            if key in seen:
                continue
            seen.add(key)
        wi = resolve(cid)
        if wi is None or oi is None:
            unresolved += 1
            continue
        rois.append((1.0 / price - 1.0) if int(oi) == int(wi) else -1.0)
    mean = sum(rois) / len(rois) if rois else 0.0
    return (len(rois), mean, unresolved)


# --------------------------------------------------------------------------- #
# The studies
# --------------------------------------------------------------------------- #

def _wallet_row(wallet: str, *, in_from: bool, in_to: bool, n_from: int, n_to: int,
                roi_from: float, roi_to: float, capped: bool, why_to: str = "") -> dict:
    move = "stay" if (in_from and in_to) else "enter" if (not in_from and in_to) else "leave" if (in_from and not in_to) else "out"
    return {"wallet": wallet, "move": move, "in_from": in_from, "in_to": in_to, "n_from": n_from, "n_to": n_to,
            "roi_from": round(roi_from, 4), "roi_to": round(roi_to, 4), "capped": capped, "why_to": why_to[:120]}


def study_activity(kind: str, params: dict, *, now: float, wallets: list[str], fetch, resolve) -> tuple[list[dict], dict]:
    """min_usd, form and first_entry share one read per wallet: the form
    under both settings says in or out; the replay says what the copies
    earn. ``(rows, settings)``."""
    from src.copy_trading import wallet_form
    cur_floor = float(getattr(CONFIG, "copy_paper_min_usd", 300.0) or 300.0)
    cur_days = float(wallet_form.FORM_DAYS)
    if kind == "min_usd":
        f_from, f_to = float(params.get("from", cur_floor)), float(params["to"])
        d_from = d_to = cur_days
        fe_from = fe_to = True
    elif kind == "form":
        f_from, f_to = cur_floor, float(params.get("min_bet", cur_floor))
        d_from, d_to = cur_days, float(params.get("days", cur_days))
        fe_from = fe_to = True
    elif kind == "first_entry":
        f_from = f_to = cur_floor
        d_from = d_to = cur_days
        fe_from, fe_to = True, bool(params.get("to", False))
    else:
        raise ValueError(kind)
    settings = {"from": {"floor": f_from, "days": d_from, "first_entry_only": fe_from},
                "to": {"floor": f_to, "days": d_to, "first_entry_only": fe_to}}
    rows = []
    for w in wallets:
        try:
            acts, pos, cov = fetch(w)
        except Exception as exc:  # noqa: BLE001  an unread wallet is a row, not a crash
            rows.append({"wallet": w, "move": "unread", "why_to": str(exc)[:120], "capped": False,
                         "in_from": False, "in_to": False, "n_from": 0, "n_to": 0, "roi_from": 0.0, "roi_to": 0.0})
            continue
        fa = wallet_form.compute(w, acts, pos, now=now, days=d_from, min_bet=f_from, coverage=cov)
        fb = wallet_form.compute(w, acts, pos, now=now, days=d_to, min_bet=f_to, coverage=cov)
        n_a, r_a, _ = replay(acts, floor=f_from, since=now - d_from * 86400, first_entry_only=fe_from, resolve=resolve)
        n_b, r_b, _ = replay(acts, floor=f_to, since=now - d_to * 86400, first_entry_only=fe_to, resolve=resolve)
        rows.append(_wallet_row(w, in_from=fa.ok, in_to=fb.ok, n_from=n_a, n_to=n_b, roi_from=r_a, roi_to=r_b,
                                capped=bool(getattr(cov, "capped", False)), why_to=fb.reason))
    return rows, settings


def study_wallet_cap(params: dict, *, b_rows: list[dict], wallets: list[str]) -> tuple[list[dict], dict]:
    """Copies per wallet per UTC day over book B's settled rows: the first
    ``to`` opens of a day stay. In = positive at their price on at least
    FALSIFY_MIN_N settled copies (the classifier, printed)."""
    cap_from = int(getattr(CONFIG, "copy_paper_b_max_per_wallet_day", 25) or 0) or 10 ** 6
    cap_to = int(params["to"])
    by: dict[str, list] = {}
    for r in b_rows:
        if not r.get("closed"):
            continue
        w = str(r.get("target") or "").lower()
        if w in set(wallets):
            by.setdefault(w, []).append(r)

    def keep(rows_w: list, cap: int) -> tuple[int, float]:
        per_day: dict = {}
        spent = ideal = 0.0
        n = 0
        for r in sorted(rows_w, key=lambda r: float(r.get("opened_ts") or 0)):
            day = time.strftime("%Y-%m-%d", time.gmtime(float(r.get("opened_ts") or 0)))
            per_day[day] = per_day.get(day, 0) + 1
            if per_day[day] > cap:
                continue
            n += 1
            spent += float(r.get("spent") or 0)
            ideal += float(r.get("ideal_pnl") or 0)
        return (n, (ideal / spent) if spent else 0.0)

    rows = []
    for w in wallets:
        n_a, r_a = keep(by.get(w, []), cap_from)
        n_b, r_b = keep(by.get(w, []), cap_to)
        rows.append(_wallet_row(w, in_from=(n_a >= FALSIFY_MIN_N and r_a > 0), in_to=(n_b >= FALSIFY_MIN_N and r_b > 0),
                                n_from=n_a, n_to=n_b, roi_from=r_a, roi_to=r_b, capped=False))
    return rows, {"from": {"cap": cap_from}, "to": {"cap": cap_to}}


def totals(rows: list[dict]) -> dict:
    def side(sfx: str) -> tuple[int, int, float]:
        rs = [r for r in rows if r.get("move") != "unread"]
        n_in = sum(1 for r in rs if r[f"in_{sfx}"])
        n = sum(int(r[f"n_{sfx}"]) for r in rs)
        w = sum(float(r[f"roi_{sfx}"]) * int(r[f"n_{sfx}"]) for r in rs)
        return (n_in, n, (w / n) if n else 0.0)
    a, b = side("from"), side("to")
    return {"wallets_in_from": a[0], "wallets_in_to": b[0], "copies_from": a[1], "copies_to": b[1],
            "roi_from": round(a[2], 4), "roi_to": round(b[2], 4),
            "stay": sum(1 for r in rows if r["move"] == "stay"), "enter": sum(1 for r in rows if r["move"] == "enter"),
            "leave": sum(1 for r in rows if r["move"] == "leave"), "out": sum(1 for r in rows if r["move"] == "out"),
            "unread": sum(1 for r in rows if r["move"] == "unread")}


def totals_line(t: dict) -> str:
    return (f"wallets in {t['wallets_in_from']} -> {t['wallets_in_to']} (stay {t['stay']}, enter {t['enter']}, leave {t['leave']}); "
            f"copies {t['copies_from']} -> {t['copies_to']}; ROI at their price {t['roi_from'] * 100:+.1f}% -> {t['roi_to'] * 100:+.1f}%")


def caveat(kind: str, n_studied: int, n_total: int, rows: list[dict]) -> str:
    capped = sum(1 for r in rows if r.get("capped"))
    base = f"estimate: {n_studied} of {n_total} wallets studied (most settled first)"
    if kind == "wallet_cap":
        return base + "; over book B's own settled rows at their price; in = positive at their price on at least " \
                      f"{FALSIFY_MIN_N} settled copies"
    return (base + f"; activity rows capped at 5,500 per wallet by the data api ({capped} capped, marked *); "
                   "in = the form rail's verdict; copies replayed at their price, held to resolution, no drag; "
                   "resolutions from the bot's cache, unresolved markets skipped")


def inputs_hash(kind: str, params: dict, wallets: list[str], now: float) -> str:
    h = hashlib.sha256(json.dumps({"kind": kind, "params": params, "wallets": sorted(wallets),
                                   "day": time.strftime("%Y-%m-%d", time.gmtime(now))}, sort_keys=True).encode()).hexdigest()
    return h[:12]


def markdown(record: dict) -> str:
    t = record["totals"]
    out = [f"# study {record['id']}: {record['kind']} {json.dumps(record['params'])}", "",
           f"question: {record.get('question') or ''}", f"frozen: {time.strftime('%Y-%m-%d %H:%M', time.gmtime(record['ts']))} UTC, inputs {record['inputs_hash']}",
           f"settings: from {json.dumps(record['settings']['from'])} to {json.dumps(record['settings']['to'])}", "",
           "## totals", totals_line(t), "", "## wallets",
           "| move | wallet | copies from -> to | ROI at their price from -> to | note |", "|---|---|---|---|---|"]
    order = {"enter": 0, "leave": 1, "stay": 2, "out": 3, "unread": 4}
    for r in sorted(record["rows"], key=lambda r: (order.get(r["move"], 9), r["wallet"])):
        star = "*" if r.get("capped") else ""
        out.append(f"| {r['move']} | {r['wallet'][:10]}{star} | {r['n_from']} -> {r['n_to']} | "
                   f"{r['roi_from'] * 100:+.1f}% -> {r['roi_to'] * 100:+.1f}% | {r.get('why_to', '')} |")
    out += ["", "## caveat", record["caveat"], ""]
    return "\n".join(out)


def run(kind: str, params: dict, *, now: float, question: str = "", fetch=None, resolve=None,
        b_rows: Optional[list] = None, zset_wallets: Optional[set] = None,
        max_wallets: int = STUDY_MAX_WALLETS) -> dict:
    """Run one study from the menu. Pure given its inputs; the defaults read
    the box. Returns the record (rows, totals, caveat, inputs hash)."""
    if kind not in MENU:
        raise ValueError(f"{kind} is not on the menu")
    for p, typ in MENU[kind]["params"].items():
        if p not in params and not (kind in ("min_usd",) and p == "from") and not (kind == "form"):
            raise ValueError(f"{kind} needs {p}")
    b_rows = b_rows if b_rows is not None else b_rows_from_disk()
    if zset_wallets is None:
        from src.copy_trading import zset
        zset_wallets = set(zset.wallet_set())
    wallets, n_total = population(b_rows, zset_wallets, max_wallets=max_wallets)
    if kind == "wallet_cap":
        rows, settings = study_wallet_cap(params, b_rows=b_rows, wallets=wallets)
    else:
        rows, settings = study_activity(kind, params, now=now, wallets=wallets,
                                        fetch=fetch or default_fetch(now), resolve=resolve or resolution_reader())
    t = totals(rows)
    h = inputs_hash(kind, params, wallets, now)
    sid = f"{time.strftime('%Y-%m-%d', time.gmtime(now))}-{kind}-{h[:8]}"
    return {"id": sid, "kind": kind, "params": params, "question": question[:300], "ts": now, "inputs_hash": h,
            "settings": settings, "rows": rows, "totals": t, "totals_line": totals_line(t),
            "caveat": caveat(kind, len(wallets), n_total, rows)}


def run_and_freeze(kind: str, params: dict, *, now: float, question: str = "", **inject) -> tuple[dict, str, bool]:
    """``(record, path, written)``; the table is frozen once."""
    from src.copy_trading import exp_cards
    rec = run(kind, params, now=now, question=question, **inject)
    p, written = exp_cards.freeze_study(rec["id"], markdown(rec), rec)
    return rec, p, written


def main(argv: Optional[list] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="a what-if over the box's own data, frozen as a table")
    ap.add_argument("kind", choices=sorted(MENU))
    ap.add_argument("--params", default="{}", help='JSON, e.g. {"from": 300, "to": 150}')
    ap.add_argument("--question", default="")
    ap.add_argument("--max-wallets", type=int, default=STUDY_MAX_WALLETS)
    a = ap.parse_args(argv)
    rec, p, written = run_and_freeze(a.kind, json.loads(a.params), now=time.time(), question=a.question,
                                     max_wallets=a.max_wallets)
    print(markdown(rec))
    print(f"[{'frozen at' if written else 'already at'} {p}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
