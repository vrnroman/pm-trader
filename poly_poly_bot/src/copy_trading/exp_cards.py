"""Experiment cards: the analyst's experiments, written down before they run.

Owner (2026-09-24): "analyst should change code for experiments (but paper
run), write experiment somewhere, then every day not only analyze logs, but
also see how experiment is going, adjust if needed, then after some time
conclude experiment results and reject idea or offer me PR which will bring
idea to real trades after I merge PR."

Manager (s-ye5990): one live experiment at a time; a card names its bars in
numbers on day 0 (win, kill, max days) and CODE applies them to the paper
books' comparison on day N; the model writes two sentences after the
number is printed and cannot override it. Mid-run "adjust" is exactly:
KILL early, EXTEND once (7 days, when starved), or VOID. The owner's merge
is the only way into real trades.

Layout under ``<data_dir>/exp/``:
  <id>/card.json        the card (hypothesis, knobs or diff+flag, bars, status)
  <id>/control.jsonl    paper book: book B's recipe, run by the experiment process
  <id>/treatment.jsonl  paper book: the same recipe plus the card's change
  <id>/journal.jsonl    one row per daily check
  <id>/heartbeat.json   the experiment process says it is alive
  <id>/verdict.json     the conclusion, once
  backlog.jsonl         every card's fate, and ideas parked for later
  studies/<id>.md|json  frozen historical studies (exp_study.py)

A leaf on config; the comparison itself is ``strategy_compare.compare``,
imported where it is used so the bot's 08:00 line can print the last
journal row without loading the comparison machinery.
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import time
import zlib
from typing import Optional

from src.config import CONFIG
from src.copy_trading import book_recipes

EXP_DIR = "exp"
BACKLOG_FILE = "backlog.jsonl"
STUDIES_DIR = "studies"
CARD_FILE = "card.json"
JOURNAL_FILE = "journal.jsonl"
CONTROL_LEDGER = "control.jsonl"
TREATMENT_LEDGER = "treatment.jsonl"
HEARTBEAT_FILE = "heartbeat.json"
VERDICT_FILE = "verdict.json"
POSTMORTEM_FILE = "postmortem.json"
# Causes a post-mortem may name. The first is the idea failing on its merits;
# the rest are the machinery, which a rerun (after a fix) can answer.
POSTMORTEM_CAUSES = ("idea", "harness", "process", "rule", "data")
MACHINERY_CAUSES = ("harness", "process", "rule", "data")

# The floor under the win bar: the treatment must beat the control by this
# many percentage points of net ROI at their price. The analyst may set a
# higher bar, never a lower one, so a card cannot be trivially winnable.
MIN_WIN_PP = 2.0
MIN_DAYS, MAX_DAYS_DEFAULT, MAX_DAYS_CAP = 3, 14, 30
EXTEND_DAYS = 7
KILL_MIN_N_DEFAULT = 20
# The harness check: the control runs book B's recipe, so on the copies BOTH
# took (same copy_id: their trade, their token) the two must agree on price
# and outcome. Which copies each takes differs by design: book B carries
# weeks of state (per-wallet-day counts, open events) the control starts
# without. Until 2026-09-25 the check compared whole-book ROI at a 1.5 pp
# tolerance; two books of 65 copies differ by chance with a 95% band near
# +-31 pp (per-copy sd ~90 pp), so min150 voided on day 0.6 while its 48
# matched copies agreed to the cent. Now a matched copy disagrees when its
# ROI differs by more than HARNESS_TOL_PP (exit timing may move it a little),
# and the card voids only when more than HARNESS_MAX_MISMATCH of at least
# HARNESS_MIN_N matched settled copies disagree: the harness is broken.
HARNESS_TOL_PP = 2.0
HARNESS_MAX_MISMATCH = 0.2
HARNESS_MIN_N = 20
# The bars are checked against noise too: a win or a kill needs the gap to
# clear SIG_Z standard errors of the delta, from a paired bootstrap over the
# union of copies (a copy both books took moves both sides together). The
# seed is the card id, so the same ledgers give the same verdict.
SIG_Z = 2.0
BOOT_N = 400
# A void the code can blame on the harness or the process (not on the idea
# being starved) is requeued by the supervisor as <id>-r<k>, at most this
# many times, so a broken run does not need the owner's Mac to restart.
MAX_RETRIES = 2
LEGACY_RETRY_WHY = "control differs from book B by"   # the whole-book rule, retired 2026-09-25
STATUSES = ("queued", "live", "win", "kill", "void")
CONCLUDED = ("win", "kill", "void")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")
_FLAG_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,39}$")


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


EXP_MAX_MB = _env_f("EXP_MAX_MB", 300.0)
PRUNE_AFTER_S = _env_f("EXP_PRUNE_AFTER_S", 30 * 86400.0)


# --------------------------------------------------------------------------- #
# Files
# --------------------------------------------------------------------------- #

def root() -> str:
    return os.path.join(CONFIG.data_dir, EXP_DIR)


def card_dir(exp_id: str) -> str:
    return os.path.join(root(), exp_id)


def path(exp_id: str, name: str) -> str:
    return os.path.join(card_dir(exp_id), name)


def studies_dir() -> str:
    return os.path.join(root(), STUDIES_DIR)


def _read_json(p: str) -> dict:
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(p: str, d: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
        return True
    except OSError:
        return False


def _append(p: str, row: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def _rows(p: str) -> list[dict]:
    out: list[dict] = []
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


def _sanitize(text: str) -> str:
    return (text or "").replace("—", ",").replace("–", "-")


# --------------------------------------------------------------------------- #
# The card
# --------------------------------------------------------------------------- #

def validate(card: dict) -> tuple[bool, str, dict]:
    """``(ok, why, normalized card)``. Every number the verdict needs must be
    on the card, in bounds; a card without a computable done never runs."""
    from src.copy_trading.strategy_compare import FALSIFY_MIN_N
    if not isinstance(card, dict):
        return (False, "card is not an object", {})
    exp_id = str(card.get("id") or "").strip().lower()
    if not _ID_RE.match(exp_id):
        return (False, f"id {exp_id!r} must be 2..32 of [a-z0-9-]", {})
    title = _sanitize(str(card.get("title") or "")).strip()[:120]
    hyp = _sanitize(str(card.get("hypothesis") or "")).strip()[:600]
    if not title or not hyp:
        return (False, "title and hypothesis are required", {})
    kind = str(card.get("kind") or "live")
    if kind != "live":
        # A card is a paper trial; a look at history is a study (manager,
        # s-ye5990 phase 2: a kind the code accepts and never runs is a
        # false green).
        return (False, "replay over history is a study: use kind study", {})
    knobs, why = book_recipes.coerce_knobs(card.get("knobs") or {})
    if why:
        return (False, why, {})
    diff = str(card.get("diff") or "")
    flag = str(card.get("flag") or "").strip()
    if diff and not _FLAG_RE.match(flag):
        return (False, "a code change needs a flag name (exp_flag.on(<flag>)) the diff sits behind", {})
    if diff and f"exp_flag.on(\"{flag}\")" not in diff and f"exp_flag.on('{flag}')" not in diff:
        return (False, f"the diff must read its switch through exp_flag.on({flag!r}); nothing else can tell control from treatment", {})
    if not knobs and not diff:
        return (False, "a card changes at least one knob or carries a diff", {})
    try:
        win = {"roi_pp": float((card.get("win_bar") or {}).get("roi_pp")),
               "min_n": int((card.get("win_bar") or {}).get("min_n"))}
        kill = {"roi_pp": float((card.get("kill_bar") or {}).get("roi_pp")),
                "min_n": int((card.get("kill_bar") or {}).get("min_n") or KILL_MIN_N_DEFAULT)}
    except (TypeError, ValueError):
        return (False, "win_bar {roi_pp, min_n} and kill_bar {roi_pp} must be numbers", {})
    if win["roi_pp"] < MIN_WIN_PP:
        return (False, f"win bar {win['roi_pp']:+.1f} pp is under the floor of +{MIN_WIN_PP:.1f} pp", {})
    if win["min_n"] < FALSIFY_MIN_N:
        return (False, f"win bar needs at least {FALSIFY_MIN_N} settled treatment copies, not {win['min_n']}", {})
    if kill["roi_pp"] > 0:
        return (False, f"kill bar {kill['roi_pp']:+.1f} pp must be at or under 0", {})
    if kill["min_n"] < 10:
        return (False, "kill bar needs at least 10 settled copies", {})
    try:
        max_days = int(card.get("max_days") or MAX_DAYS_DEFAULT)
    except (TypeError, ValueError):
        return (False, "max_days must be an integer", {})
    if not (MIN_DAYS <= max_days <= MAX_DAYS_CAP):
        return (False, f"max_days {max_days} must be {MIN_DAYS}..{MAX_DAYS_CAP}", {})
    out = {
        "id": exp_id, "title": title, "hypothesis": hyp, "kind": kind,
        "knobs": knobs, "diff": diff, "flag": flag if diff else "",
        "win_bar": win, "kill_bar": kill, "max_days": max_days, "extended": False,
        "parent_id": (str(card.get("parent_id") or "").strip().lower() or None),
        "study_ref": (str(card.get("study_ref") or "").strip() or None),
        "branch": None, "workdir": None, "diff_class": None,
        "status": "queued", "created_ts": None, "started_ts": None, "concluded_ts": None,
    }
    return (True, "", out)


def load(exp_id: str) -> Optional[dict]:
    c = _read_json(path(exp_id, CARD_FILE))
    return c if c.get("id") == exp_id else None


def save(card: dict) -> bool:
    return _write_json(path(card["id"], CARD_FILE), card)


def cards() -> list[dict]:
    out = []
    try:
        names = sorted(os.listdir(root()))
    except OSError:
        return out
    for n in names:
        c = load(n)
        if c:
            out.append(c)
    return out


def live_card() -> Optional[dict]:
    for c in cards():
        if c.get("status") == "live":
            return c
    return None


def next_queued() -> Optional[dict]:
    q = [c for c in cards() if c.get("status") == "queued"]
    q.sort(key=lambda c: float(c.get("created_ts") or 0))
    return q[0] if q else None


def create(card: dict, now: float) -> tuple[bool, str, Optional[dict]]:
    """Write a validated card as queued. Refused over the disk cap or when
    the id exists: a card is written once and its bars never change."""
    ok, why, c = validate(card)
    if not ok:
        return (False, why, None)
    if load(c["id"]) is not None:
        return (False, f"experiment {c['id']} already exists", None)
    if over_cap():
        return (False, f"data/exp is over {EXP_MAX_MB:.0f} MB; prune first", None)
    c["created_ts"] = now
    if not save(c):
        return (False, "could not write the card", None)
    backlog_add({"id": c["id"], "event": "queued", "title": c["title"], "parent_id": c.get("parent_id"),
                 "study_ref": c.get("study_ref")}, now)
    return (True, "", c)


def launch(exp_id: str, now: float) -> tuple[bool, str]:
    """Queued -> live, when nothing else is live. One experiment at a time."""
    c = load(exp_id)
    if c is None:
        return (False, f"no card {exp_id}")
    if c.get("status") != "queued":
        return (False, f"{exp_id} is {c.get('status')}, not queued")
    live = live_card()
    if live is not None:
        return (False, f"{live['id']} is live; one experiment at a time")
    c["status"], c["started_ts"] = "live", now
    if not save(c):
        return (False, "could not write the card")
    backlog_add({"id": exp_id, "event": "live"}, now)
    return (True, f"{exp_id} live from {time.strftime('%m-%d %H:%M', time.gmtime(now))} UTC for {c['max_days']} days")


def set_branch(exp_id: str, *, branch: Optional[str], workdir: Optional[str], diff_class: Optional[str]) -> bool:
    c = load(exp_id)
    if c is None:
        return False
    c["branch"], c["workdir"], c["diff_class"] = branch, workdir, diff_class
    return save(c)


# --------------------------------------------------------------------------- #
# Journal, heartbeat, backlog
# --------------------------------------------------------------------------- #

def journal(exp_id: str, row: dict, now: float) -> dict:
    r = {"ts": now, "day": time.strftime("%Y-%m-%d", time.gmtime(now)), **row}
    _append(path(exp_id, JOURNAL_FILE), r)
    return r


def journal_rows(exp_id: str) -> list[dict]:
    return _rows(path(exp_id, JOURNAL_FILE))


def journaled_on(exp_id: str, day: str) -> bool:
    return any(r.get("day") == day for r in journal_rows(exp_id))


def write_heartbeat(exp_id: str, *, pid: int, cycles: int, rss_mb: float, now: float) -> bool:
    return _write_json(path(exp_id, HEARTBEAT_FILE), {"ts": now, "pid": pid, "cycles": cycles, "rss_mb": round(rss_mb, 1)})


def heartbeat(exp_id: str) -> dict:
    return _read_json(path(exp_id, HEARTBEAT_FILE))


def backlog_add(row: dict, now: float) -> dict:
    r = {"ts": now, "day": time.strftime("%Y-%m-%d", time.gmtime(now)), **row}
    _append(os.path.join(root(), BACKLOG_FILE), r)
    return r


def backlog_rows(since_ts: float = 0.0) -> list[dict]:
    return [r for r in _rows(os.path.join(root(), BACKLOG_FILE)) if float(r.get("ts") or 0) >= since_ts]


# --------------------------------------------------------------------------- #
# The verdict: the card's bars applied to the comparison, by code
# --------------------------------------------------------------------------- #

def _pp(cmp: dict) -> tuple[float, int, int]:
    """Treatment minus control, net ROI at their price, in percentage points;
    treatment and control settled counts. ``compare``'s "b" side is the
    treatment (its first open starts the era), "a" the control."""
    t, c = cmp.get("b") or {}, cmp.get("a") or {}
    delta = (float(t.get("ideal_roi_net") or 0.0) - float(c.get("ideal_roi_net") or 0.0)) * 100.0
    return (round(delta, 2), int(t.get("n_settled") or 0), int(c.get("n_settled") or 0))


def verdict(card: dict, cmp: dict, now: float, *, harness_pp: Optional[float] = None,
            harness_n: int = 0, harness_mismatch: Optional[int] = None, se_pp: Optional[float] = None) -> dict:
    """Pure. ``{"status": live|win|kill|void|extend, "why", "delta_pp", "n",
    "n_control", "days", "se_pp"}``. The order is the card's: a harness
    whose matched copies disagree voids first; the kill bar is checked
    before the win bar; the clock is checked last. With ``se_pp`` a bar
    counts only when the gap also clears SIG_Z standard errors. A void
    carries ``retry``: True when the harness or a stall is to blame."""
    delta, n, n_c = _pp(cmp)
    started = float(card.get("started_ts") or now)
    days = round((now - started) / 86400.0, 1)
    win, kill = card["win_bar"], card["kill_bar"]
    base = {"delta_pp": delta, "n": n, "n_control": n_c, "days": days,
            "harness_pp": harness_pp, "harness_n": harness_n, "harness_mismatch": harness_mismatch, "se_pp": se_pp}
    if harness_mismatch is not None and harness_n >= HARNESS_MIN_N and harness_mismatch > HARNESS_MAX_MISMATCH * harness_n:
        return {**base, "status": "void", "retry": True,
                "why": f"{harness_mismatch} of {harness_n} copies the control and book B both took disagree by more than "
                       f"{HARNESS_TOL_PP:.1f} pp: the harness, not the idea, is what moved"}
    validity = cmp.get("validity") or {}
    if not validity.get("valid", True) and days >= 2 and n > 0:
        return {**base, "status": "void", "retry": True, "why": "; ".join(validity.get("reasons") or ["a book stalled"])}
    noise = SIG_Z * float(se_pp) if se_pp is not None else 0.0
    sig = f" (noise {SIG_Z:.0f}x se {se_pp:.1f} pp)" if se_pp is not None else ""
    if n >= kill["min_n"] and delta <= kill["roi_pp"] and delta <= -noise:
        return {**base, "status": "kill",
                "why": f"{delta:+.1f} pp vs control on {n} settled copies, kill bar {kill['roi_pp']:+.1f} pp at n>={kill['min_n']}{sig}"}
    if n >= win["min_n"] and delta >= win["roi_pp"] and delta >= noise:
        return {**base, "status": "win",
                "why": f"{delta:+.1f} pp vs control on {n} settled copies, win bar {win['roi_pp']:+.1f} pp at n>={win['min_n']}{sig}"}
    if days >= float(card.get("max_days") or MAX_DAYS_DEFAULT):
        if n < win["min_n"] and not card.get("extended"):
            return {**base, "status": "extend",
                    "why": f"{n} of {win['min_n']} settled copies after {days:.0f} days: extended once by {EXTEND_DAYS} days"}
        if n < win["min_n"]:
            return {**base, "status": "void", "retry": False,
                    "why": f"{n} of {win['min_n']} settled copies after {days:.0f} days, already extended: starved"}
        return {**base, "status": "kill",
                "why": f"{delta:+.1f} pp vs control on {n} settled copies after {days:.0f} days: did not clear the win bar {win['roi_pp']:+.1f} pp"}
    return {**base, "status": "live",
            "why": f"{delta:+.1f} pp vs control on {n} settled copies, day {days:.0f} of {card.get('max_days')}"}


def apply_verdict(card: dict, v: dict, now: float) -> dict:
    """Write the verdict into the card: extend once, or conclude once. A
    concluded card is never touched again."""
    if card.get("status") in CONCLUDED:
        return card
    st = v["status"]
    if st == "extend":
        card["extended"] = True
        card["max_days"] = int(card.get("max_days") or MAX_DAYS_DEFAULT) + EXTEND_DAYS
        save(card)
        backlog_add({"id": card["id"], "event": "extended", "why": v["why"]}, now)
    elif st in CONCLUDED:
        card["status"], card["concluded_ts"] = st, now
        save(card)
        _write_json(path(card["id"], VERDICT_FILE), {**v, "ts": now})
        backlog_add({"id": card["id"], "event": st, "why": v["why"], "delta_pp": v.get("delta_pp"), "n": v.get("n")}, now)
    return card


def _settled(path_: str, floor: float) -> dict[str, dict]:
    """Settled rows opened at or after ``floor``, by copy_id."""
    out: dict[str, dict] = {}
    for r in _rows(path_):
        if r.get("closed") and float(r.get("opened_ts") or 0.0) >= floor and float(r.get("spent") or 0.0) > 0:
            out[str(r.get("copy_id") or id(r))] = r
    return out


def _net_pair(r: dict) -> tuple[float, float]:
    """``(net pnl at their price, spent)`` for one settled row, with the
    modeled costs ``strategy_compare`` derives, so the pieces sum to its
    ideal_roi_net."""
    from src.copy_trading.strategy_compare import _cost_env, _row_costs
    cm, gas, fee = _cost_env()
    _, icost = _row_costs(r, cm, gas, fee)
    return (float(r.get("ideal_pnl") or 0.0) - icost, float(r.get("spent") or 0.0))


def harness_check(control: dict[str, dict], book_b: dict[str, dict]) -> dict:
    """The control against book B on the copies both took. ``{"n": matched
    settled, "mismatch": how many differ by more than HARNESS_TOL_PP of ROI,
    "pp": mean control-minus-B ROI on them, "overlap": matched share of the
    control's copies}``. Pure."""
    ids = [k for k in control if k in book_b]
    diffs = []
    for k in ids:
        (pc, sc), (pb, sb) = _net_pair(control[k]), _net_pair(book_b[k])
        diffs.append((pc / sc - pb / sb) * 100.0)
    return {"n": len(ids), "mismatch": sum(1 for d in diffs if abs(d) > HARNESS_TOL_PP),
            "pp": round(sum(diffs) / len(diffs), 2) if diffs else None,
            "overlap": round(len(ids) / len(control), 2) if control else 0.0}


def delta_se(control: dict[str, dict], treatment: dict[str, dict], *, seed: str, n_boot: int = BOOT_N) -> Optional[float]:
    """Standard error, in pp, of treatment-minus-control net ROI: a paired
    bootstrap over the union of copies (a copy both books took is drawn
    once and moves both sides). None under 10 copies a side. Deterministic
    for a given seed."""
    if len(control) < 10 or len(treatment) < 10:
        return None
    ids = sorted(set(control) | set(treatment))
    z = (0.0, 0.0)
    pairs = [(_net_pair(control[k]) if k in control else z, _net_pair(treatment[k]) if k in treatment else z) for k in ids]
    rng = random.Random(zlib.crc32(seed.encode("utf-8")))
    deltas = []
    for _ in range(n_boot):
        cp = cs = tp = ts = 0.0
        for _ in range(len(pairs)):
            (a, b), (c, d) = pairs[rng.randrange(len(pairs))]
            cp += a; cs += b; tp += c; ts += d
        if cs > 0 and ts > 0:
            deltas.append((tp / ts - cp / cs) * 100.0)
    if len(deltas) < n_boot // 2:
        return None
    m = sum(deltas) / len(deltas)
    return round((sum((x - m) ** 2 for x in deltas) / len(deltas)) ** 0.5, 2)


def compare_card(card: dict, now: float, *, b_ledger: Optional[str] = None) -> tuple[dict, dict]:
    """``(cmp, harness)``: the treatment against the control, and the
    control against the real book B on the copies both took (the harness
    check), both from the card's start. ``harness`` also carries ``se_pp``,
    the noise on the treatment-minus-control gap. Reads ledgers only."""
    from src.copy_trading.strategy_compare import compare
    exp_id = card["id"]
    floor = float(card.get("started_ts") or now)
    cmp = compare(path(exp_id, CONTROL_LEDGER), path(exp_id, TREATMENT_LEDGER), now=now, era_floor=floor)
    control = _settled(path(exp_id, CONTROL_LEDGER), floor)
    treatment = _settled(path(exp_id, TREATMENT_LEDGER), floor)
    harness: dict = {"pp": None, "n": 0, "mismatch": None, "overlap": None}
    b_path = b_ledger or CONFIG.copy_paper_b_ledger
    if b_path and os.path.exists(b_path) and control:
        harness = harness_check(control, _settled(b_path, floor))
    harness["se_pp"] = delta_se(control, treatment, seed=exp_id)
    return (cmp, harness)


def check(card: dict, now: float, *, b_ledger: Optional[str] = None) -> dict:
    """One daily check: compare, verdict, journal row, verdict applied.
    Returns the journal row. Once per UTC day per card."""
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    if journaled_on(card["id"], day):
        return journal_rows(card["id"])[-1]
    cmp, harness = compare_card(card, now, b_ledger=b_ledger)
    v = verdict(card, cmp, now, harness_pp=harness["pp"], harness_n=harness["n"],
                harness_mismatch=harness["mismatch"], se_pp=harness["se_pp"])
    row = journal(card["id"], {"status": v["status"], "why": v["why"], "delta_pp": v["delta_pp"], "n": v["n"],
                               "n_control": v["n_control"], "days": v["days"], "harness_pp": harness["pp"],
                               "harness_n": harness["n"], "harness_mismatch": harness["mismatch"],
                               "overlap": harness["overlap"], "se_pp": harness["se_pp"],
                               "treatment": _slim(cmp.get("b") or {}), "control": _slim(cmp.get("a") or {})}, now)
    apply_verdict(card, v, now)
    return row


# --------------------------------------------------------------------------- #
# Requeue: a run the harness or the process spoiled starts again by itself
# --------------------------------------------------------------------------- #

def postmortem(exp_id: str) -> dict:
    return _read_json(path(exp_id, POSTMORTEM_FILE))


def write_postmortem(exp_id: str, row: dict, now: float) -> bool:
    return _write_json(path(exp_id, POSTMORTEM_FILE), {**row, "ts": now})


def pending_postmortems() -> list[dict]:
    """Voided cards nobody has explained yet, oldest first."""
    out = [c for c in cards() if c.get("status") == "void" and not postmortem(c["id"])]
    return sorted(out, key=lambda c: float(c.get("concluded_ts") or 0))


def retryable(card: dict) -> bool:
    """A void the code blames on the harness, a stall or the process, or
    one the analyst's post-mortem blamed on the machinery. A verdict without
    the flag (written before 2026-09-25) is retryable when the retired
    whole-book harness rule voided it."""
    if card.get("status") != "void":
        return False
    v = _read_json(path(card["id"], VERDICT_FILE))
    if v.get("retry") is True:
        return True
    # The analyst's post-mortem blamed the machinery (a rule, the harness,
    # the process, the data), not the idea: the idea gets another run.
    if postmortem(card["id"]).get("cause") in MACHINERY_CAUSES:
        return True
    if "retry" in v:
        return bool(v["retry"])
    return str(v.get("why") or "").startswith(LEGACY_RETRY_WHY)


def requeue_next(now: float) -> Optional[dict]:
    """When nothing is live or queued: the most recent retryable void, as a
    fresh card ``<base>-r<k>`` with the same change and bars, once per void
    and at most MAX_RETRIES times per idea. Returns the new card or None."""
    cs = cards()
    if any(c.get("status") in ("live", "queued") for c in cs):
        return None
    retried = {c.get("retry_of") for c in cs if c.get("retry_of")}
    cand = [c for c in cs if retryable(c) and c["id"] not in retried and int(c.get("attempt") or 0) < MAX_RETRIES]
    if not cand:
        return None
    old = max(cand, key=lambda c: float(c.get("concluded_ts") or 0))
    attempt = int(old.get("attempt") or 0) + 1
    base = re.sub(r"-r\d+$", "", old["id"])[:32 - len(f"-r{attempt}")]
    new_id = f"{base}-r{attempt}"
    why = str(_read_json(path(old["id"], VERDICT_FILE)).get("why") or "void")
    spec = {k: old.get(k) for k in ("title", "knobs", "diff", "flag", "win_bar", "kill_bar", "max_days", "study_ref")}
    spec.update({"id": new_id, "kind": "live", "parent_id": old["id"],
                 "hypothesis": (f"Rerun {attempt} of {old['id']}, voided by the harness or the process, not the idea. "
                                + str(old.get("hypothesis") or ""))[:600]})
    ok, err, c = create(spec, now)
    if not ok or c is None:
        backlog_add({"id": old["id"], "event": "requeue refused", "why": err}, now)
        return None
    c.update({"retry_of": old["id"], "attempt": attempt, "branch": old.get("branch"),
              "workdir": old.get("workdir"), "diff_class": old.get("diff_class")})
    save(c)
    backlog_add({"id": new_id, "event": "requeued", "retry_of": old["id"], "why": why[:200]}, now)
    return c


def _slim(s: dict) -> dict:
    return {k: s.get(k) for k in ("n_settled", "n_open", "pnl", "spent", "ideal_roi", "ideal_roi_net", "win_rate") if k in s}


# --------------------------------------------------------------------------- #
# Text: the table for the phone and the PR, the 08:00 line
# --------------------------------------------------------------------------- #

def _pct(v) -> str:
    try:
        return f"{float(v) * 100:+.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def table(card: dict, rows: Optional[list[dict]] = None) -> list[str]:
    """The card and its journal as lines. Numbers, then the bars, then the
    day rows; no adjective."""
    rows = journal_rows(card["id"]) if rows is None else rows
    out = [f"exp {card['id']}: {card['title']}", f"hypothesis: {card['hypothesis']}"]
    if card.get("knobs"):
        out.append("change: " + ", ".join(f"{k}={v}" for k, v in card["knobs"].items()))
    if card.get("branch"):
        out.append(f"code: branch {card['branch']} behind flag {card.get('flag')} ({card.get('diff_class') or 'unclassified'} path)")
    out.append(f"bars: win at {card['win_bar']['roi_pp']:+.1f} pp on n>={card['win_bar']['min_n']}, "
               f"kill at {card['kill_bar']['roi_pp']:+.1f} pp on n>={card['kill_bar']['min_n']}, "
               f"{card['max_days']} days{' (extended once)' if card.get('extended') else ''}")
    if card.get("parent_id"):
        out.append(f"follows: {card['parent_id']}")
    if card.get("study_ref"):
        out.append(f"study: {card['study_ref']}")
    for r in rows[-21:]:
        t, c = r.get("treatment") or {}, r.get("control") or {}
        out.append(f"{r.get('day')}: {str(r.get('status')).upper():6} treatment {_pct(t.get('ideal_roi_net'))} on {t.get('n_settled', 0)} "
                   f"vs control {_pct(c.get('ideal_roi_net'))} on {c.get('n_settled', 0)}; {r.get('delta_pp', 0):+.1f} pp"
                   + (f"; harness {r['harness_pp']:+.1f} pp" if r.get("harness_pp") is not None else ""))
    if rows:
        out.append(f"verdict: {rows[-1].get('why', '')}")
    return out


def line(now: Optional[float] = None) -> str:
    """One line under the 08:00 message. The live card from its last journal
    row; a card concluded in the last 24 h, once; nothing when nothing runs."""
    now = time.time() if now is None else now
    parts = []
    live = live_card()
    if live is not None:
        rows = journal_rows(live["id"])
        if rows:
            r = rows[-1]
            t, c = r.get("treatment") or {}, r.get("control") or {}
            parts.append(f"exp {live['id']} day {r.get('days', 0):.0f}/{live['max_days']}: treatment {_pct(t.get('ideal_roi_net'))} "
                         f"vs control {_pct(c.get('ideal_roi_net'))} at their price (n {t.get('n_settled', 0)}/{live['win_bar']['min_n']}), "
                         f"win at {live['win_bar']['roi_pp']:+.0f}, kill at {live['kill_bar']['roi_pp']:+.0f}")
        else:
            days = (now - float(live.get("started_ts") or now)) / 86400.0
            parts.append(f"exp {live['id']} day {days:.0f}/{live['max_days']}: no check yet")
    for c in cards():
        if c.get("status") in CONCLUDED and now - float(c.get("concluded_ts") or 0) < 86400:
            v = _read_json(path(c["id"], VERDICT_FILE))
            parts.append(f"exp {c['id']} {c['status'].upper()}: {v.get('why', '')[:120]}")
    q = sum(1 for c in cards() if c.get("status") == "queued")
    if q and parts:
        parts[-1] += f"; queued {q}"
    return ("\U0001f9ea " + " | ".join(parts)) if parts else ""


def chain(card: dict) -> str:
    """The card's lineage as one computed phrase: "min150 <- study
    2026-09-25-min_usd-ab12" or "min150-first <- min150". Empty when it has
    none. No diagram: a line the digest and the phone can carry."""
    parts = []
    if card.get("parent_id"):
        parts.append(str(card["parent_id"]))
    if card.get("study_ref"):
        parts.append(f"study {card['study_ref']}")
    return f"{card['id']} <- " + ", ".join(parts) if parts else ""


def rows(now: Optional[float] = None, limit: int = 20) -> list[str]:
    """For the digest: every card, one line, newest first."""
    now = time.time() if now is None else now
    out = []
    for c in sorted(cards(), key=lambda c: -float(c.get("created_ts") or 0))[:limit]:
        j = journal_rows(c["id"])
        last = j[-1] if j else {}
        out.append(f"{c['id']:16} {c['status']:6} {c['title'][:50]:50} "
                   f"{'n ' + str(last.get('n')) + ' ' + f'{last.get('delta_pp', 0):+.1f} pp' if last else 'no check'}"
                   + (f"  branch {c['branch']}" if c.get("branch") else "")
                   + (f"  ({chain(c)})" if chain(c) else ""))
    return out


# --------------------------------------------------------------------------- #
# The owner's one-tap studies, and the questions nobody could compute
# --------------------------------------------------------------------------- #

# Three presets on the 08:00 line (manager, s-ye5990 phase 2): a tap writes a
# request file; the sidecar runs it next tick and the table lands on the
# phone. The menu is fixed; what it cannot answer goes to the unanswered
# ledger, never to free text.
STUDY_PRESETS: dict[str, dict] = {
    "min150": {"label": "floor 300 -> 150", "kind": "min_usd", "params": {"from": 300, "to": 150},
               "question": "slice floor 300 -> 150: who stays in form, who enters, who leaves, what the copies earn"},
    "form7": {"label": "form on 7 days", "kind": "form", "params": {"days": 7},
              "question": "the form rail on 7 days instead of 14: who is in, who is out"},
    "cap3": {"label": "cap 3 a wallet-day", "kind": "wallet_cap", "params": {"from": 25, "to": 3},
             "question": "3 copies a wallet a day in book B: which wallets keep their edge"},
}
REQUEST_PREFIX = "request-"
UNANSWERED_FILE = "unanswered.jsonl"
UNANSWERED_KEEP = 200


def study_keyboard() -> dict:
    """Inline buttons for the 08:00 line, one per preset."""
    return {"inline_keyboard": [[{"text": f"study: {v['label']}", "callback_data": f"study:{k}"}
                                 for k, v in STUDY_PRESETS.items()]]}


def request_study(preset: str, now: float, *, by: str = "owner") -> tuple[bool, str]:
    """A tap: one request file under studies/. ``(ok, message for the toast)``."""
    spec = STUDY_PRESETS.get(str(preset or ""))
    if spec is None:
        return (False, f"no study preset {preset!r}")
    req = {"preset": preset, "kind": spec["kind"], "params": spec["params"], "question": spec["question"], "by": by, "ts": now}
    p = os.path.join(studies_dir(), f"{REQUEST_PREFIX}{int(now)}-{preset}.json")
    if not _write_json(p, req):
        return (False, "could not write the request")
    return (True, f"queued: {spec['label']}; the table lands here when it is done")


def pending_requests() -> list[tuple[str, dict]]:
    out = []
    try:
        names = sorted(n for n in os.listdir(studies_dir()) if n.startswith(REQUEST_PREFIX) and n.endswith(".json"))
    except OSError:
        return out
    for n in names:
        d = _read_json(os.path.join(studies_dir(), n))
        if d.get("kind"):
            out.append((os.path.join(studies_dir(), n), d))
    return out


def finish_request(path: str, *, ok: bool) -> None:
    """The request is renamed, never deleted: what was asked stays visible."""
    try:
        os.replace(path, path[:-5] + (".done" if ok else ".failed"))
    except OSError:
        pass


def unanswered_add(row: dict, now: float) -> dict:
    """A question the menu could not compute: one plain row. Capped at
    UNANSWERED_KEEP rows; no count, no score."""
    r = {"ts": now, "day": time.strftime("%Y-%m-%d", time.gmtime(now)), **row}
    p = os.path.join(root(), UNANSWERED_FILE)
    rows_ = _rows(p) + [r]
    if len(rows_) > UNANSWERED_KEEP:
        rows_ = rows_[-UNANSWERED_KEEP:]
        try:
            with open(p + ".tmp", "w", encoding="utf-8") as f:
                for x in rows_:
                    f.write(json.dumps(x, ensure_ascii=False) + "\n")
            os.replace(p + ".tmp", p)
        except OSError:
            pass
    else:
        _append(p, r)
    return r


def unanswered_rows(since_ts: float = 0.0) -> list[dict]:
    return [r for r in _rows(os.path.join(root(), UNANSWERED_FILE)) if float(r.get("ts") or 0) >= since_ts]


# --------------------------------------------------------------------------- #
# Disk: the cap the owner was burned by
# --------------------------------------------------------------------------- #

def usage_mb() -> float:
    total = 0
    for dp, _dn, fns in os.walk(root()):
        for fn in fns:
            try:
                total += os.path.getsize(os.path.join(dp, fn))
            except OSError:
                pass
    return total / 1e6


def over_cap() -> bool:
    return usage_mb() >= EXP_MAX_MB


def prune(now: Optional[float] = None) -> list[str]:
    """Drop the ledgers of cards concluded more than PRUNE_AFTER_S ago; the
    card, journal and verdict stay. Returns what was removed."""
    now = time.time() if now is None else now
    gone = []
    for c in cards():
        if c.get("status") not in CONCLUDED:
            continue
        if now - float(c.get("concluded_ts") or now) < PRUNE_AFTER_S:
            continue
        for name in (CONTROL_LEDGER, TREATMENT_LEDGER, HEARTBEAT_FILE):
            p = path(c["id"], name)
            if os.path.exists(p):
                try:
                    os.remove(p)
                    gone.append(p)
                except OSError:
                    pass
        wd = c.get("workdir")
        if wd and os.path.isdir(wd):
            shutil.rmtree(wd, ignore_errors=True)
            gone.append(wd)
    return gone


# --------------------------------------------------------------------------- #
# Studies: frozen tables
# --------------------------------------------------------------------------- #

def freeze_study(study_id: str, markdown: str, record: dict) -> tuple[str, bool]:
    """Write ``studies/<id>.md`` and ``.json`` once. ``(path, written)``:
    an existing study is never rewritten."""
    md = os.path.join(studies_dir(), f"{study_id}.md")
    if os.path.exists(md):
        return (md, False)
    os.makedirs(studies_dir(), exist_ok=True)
    with open(md + ".tmp", "w", encoding="utf-8") as f:
        f.write(markdown)
    os.replace(md + ".tmp", md)
    _write_json(os.path.join(studies_dir(), f"{study_id}.json"), record)
    return (md, True)


def studies(limit: int = 20) -> list[dict]:
    out = []
    try:
        names = sorted(n for n in os.listdir(studies_dir()) if n.endswith(".json"))
    except OSError:
        return out
    for n in names[-limit:]:
        d = _read_json(os.path.join(studies_dir(), n))
        if d:
            out.append(d)
    return out
