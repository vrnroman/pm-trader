"""Set Z's exit door: a member is re-read against the gate every day it sits
in Z, and leaves on its own when it has stayed below the door for a run of
days (the owner, 2026-10-01: "not necessary to remove immediately if a
wallet does not satisfy the gates any more by a little, but if that happens
for a week or two then it makes sense to auto delete").

Why a window and not a day. The gate re-run daily over the 45 days before
this shipped showed two populations and nothing in between: members that
dipped and came back were below the door for one to three consecutive
days (0x3f3a 1-2, 0x09b0 3); members in real decay stayed below it for
six days and counting (0x0011), twenty-four (0xd251), and the one eviction
the owner did by hand (0x57b2) had been below for fifteen. ``DECAY_DAYS``
is seven: more than twice the longest flicker, the lower edge of the
owner's "week or two" (the manager's number, s-k7m2qa; the owner's at review).

What counts as "below the door". Only the checks that say the wallet has
stopped being worth real money: paper ROI, the promotion floor (which
carries the second-half decay test), the trimmed-ROI rail, the execution
rail (real-quote slice or book A), at-their-price ROI. A sample-size check
cannot fail for a member that already passed it, an idle wallet costs
nothing (the form rail benches it), the book-wide persistence check fails
for everyone at once and would empty Z on a book statistic, and the
scalper rail measures copyability, not decay (see DECAY_LABELS). Those
never count.

Mechanics. One row per member per UTC day, written by the same scan that
refreshes the floor rows, from the same read of the books. A failing day
increments the member's counter; a passing day resets it and says so when
the wallet had been in the red. The counter and the window are on
``/zset`` next to the member. The first red day and the eviction reach the
phone; the days between are ledger rows. Eviction goes through
``zset.evict`` and is as sticky as the owner's own: ``/zset readmit`` is
the way back, and the gate must pass the wallet again.

The first run seeds each counter from the books as they stood on each past
day, counting only the checks a replay can date (the scalper rail and the
real-quote slice read today's tables and are counted from day one, never
backdated).

Idempotent by construction: a second check on the same UTC day re-reads
the same verdict and changes nothing; a member already evicted is skipped. A leaf over ``zset_candidates``,
``zset`` and ``ops_watch``; nothing here places, sizes or arms.
"""

from __future__ import annotations

import os
import time
from typing import Callable, Iterable, Optional

from src.config import CONFIG
from src.logger import logger

STATE_FILE = "zset-decay.json"


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


# Consecutive UTC days below the door before the member leaves on its own.
DECAY_DAYS = int(_env_f("ZSET_DECAY_DAYS", 7))

# The check labels that count as "below the door" (prefix match, so a
# label that carries its threshold in the text, like "paper ROI ≥ +10%
# now", still matches when the threshold moves).
DECAY_LABELS = (
    "paper ROI",
    "at-their-price ROI",
    "promotion floor still holds",
    "still positive with its best",
    "does not lose at the prices we would really pay",
    "the other book does not contradict it",
)
# Not counted on purpose: "not a scalper at our latency". The scalper rail
# measures whether a wallet's EXITS can be mirrored, which is an admission
# question; the exit door is for decay. The four members the form table
# calls scalpers win when their entries are held (+27..+47% at their price,
# one of them the best real-money net of any wallet followed), and the form
# rail already benches them reversibly. A sticky eviction on a label the
# data contradicts is the false positive this door must not fire (the
# manager, s-k7m2qa round 3). ZSET_DECAY_SCALPER=true counts it again.
if str(os.environ.get("ZSET_DECAY_SCALPER", "")).strip().lower() in ("1", "true", "yes", "on"):
    DECAY_LABELS = DECAY_LABELS + ("not a scalper at our latency",)


# Checks that read LIVE state (today's form table, today's shadow quotes),
# not the books as they stood: a replay cannot date them, so the history
# seed never counts them (the verifier, s-k7m2qa round 3: seeding from
# them handed five members a fabricated fifteen-day streak on day one).
LIVE_ONLY_LABELS = (
    "not a scalper at our latency",
    "does not lose at the prices we would really pay",
)


def _p() -> str:
    return os.path.join(CONFIG.data_dir, STATE_FILE)


def _read() -> Optional[dict]:
    """The state, {} when there is none, None when the file is there but
    will not parse (then the door re-opens from the history, not from a
    silent zero)."""
    import json
    if not os.path.exists(_p()):
        return {}
    try:
        with open(_p(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _write(d: dict) -> bool:
    import json
    try:
        os.makedirs(CONFIG.data_dir, exist_ok=True)
        tmp = _p() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _p())
        return True
    except OSError as exc:
        logger.error(f"[zset-decay] state write failed: {exc}")
        return False


def _day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def decay_fails(checks: Iterable, *, replayable_only: bool = False) -> list[tuple[str, str]]:
    """The failing checks that count, as ``(label, detail)``.
    ``replayable_only`` drops the checks that read live state (the seed)."""
    out = []
    for item in checks or []:
        try:
            label, ok, detail = item[0], item[1], item[2]
        except (TypeError, IndexError):
            continue
        if ok:
            continue
        lab = str(label or "")
        if not any(lab.startswith(pfx) for pfx in DECAY_LABELS):
            continue
        if replayable_only and any(lab.startswith(pfx) for pfx in LIVE_ONLY_LABELS):
            continue
        out.append((lab, str(detail or "")))
    return out


def state() -> dict:
    """Per member: ``{"days": n, "since": first red day, "last_day": day,
    "fails": [labels]}``. Members not in the red are absent."""
    return _read() or {}


def line_for(wallet: str, st: Optional[dict] = None) -> str:
    """The member's exit-door line for ``/zset``: empty when it passes."""
    st = _read() if st is None else st
    rec = st.get((wallet or "").lower())
    if not isinstance(rec, dict) or not rec.get("days"):
        return ""
    fails = rec.get("fails") or []
    what = fails[0] if fails else "below the door"
    return (f"below the door {int(rec['days'])} of {DECAY_DAYS} days "
            f"({what}); leaves on its own at {DECAY_DAYS}")


def _book_as_of(positions, t: float) -> list:
    """The paper book as it stood at ``t``: rows opened later are gone, rows
    closed later are open again. Copies, never the live objects."""
    import copy as _copy
    out = []
    for p in positions:
        if float(getattr(p, "opened_ts", 0.0) or 0.0) > t:
            continue
        closed_ts = float(getattr(p, "closed_ts", 0.0) or 0.0)
        if getattr(p, "closed", False) and closed_ts and closed_ts > t:
            q = _copy.copy(p)
            q.closed = False
            q.won = None
            q.pnl = 0.0
            q.closed_ts = 0.0
            out.append(q)
        else:
            out.append(p)
    return out


def seed_from_history(members: Iterable[str], *, b_positions, a_positions,
                      era: Optional[float], now: float, max_days: Optional[int] = None) -> dict:
    """The counters as they would stand had the door been read every day:
    for each member, how many consecutive days up to yesterday it failed the
    gate, from the books as they stood on each of those days. The first run
    starts from this, not from zero, so a member already weeks below the
    door is not handed a fresh window on deploy (the manager, s-k7m2qa).
    Returns the state dict (members with a zero streak are absent)."""
    from src.copy_trading import promotion_gate, zset_candidates as zc
    cap = int(DECAY_DAYS + 7 if max_days is None else max_days)
    st: dict = {}
    for w in sorted({(m or "").lower() for m in members if m}):
        streak = 0
        fails_at_first: list = []
        for d in range(1, cap + 1):
            t = now - d * 86400.0
            b = _book_as_of(b_positions, t)
            a = _book_as_of(a_positions, t)
            try:
                corr = promotion_gate.split_half_corr(b, min_opened_ts=era)
                cand = zc.evaluate(w, b, a, era=era, now=t, book_corr=corr)
            except Exception as exc:  # noqa: BLE001
                logger.warn(f"[zset-decay] seed: {w[:10]} unreadable {d}d back: {exc}")
                break
            if cand is None:
                break
            fails = decay_fails(cand.checks, replayable_only=True)
            if not fails:
                break
            streak += 1
            fails_at_first = [lab for lab, _d in fails]
        if streak:
            st[w] = {"days": streak, "since": now - streak * 86400.0,
                     "last_day": _day(now - 86400.0), "fails": fails_at_first, "seeded": True}
    return st


def roster_lines(members: Iterable[str], st: dict, *, window: int,
                 notes: Optional[dict] = None) -> list[str]:
    """One line per member for the opening roster. ``notes`` carries what
    does not count but is worth seeing (an idle wallet's days)."""
    out = []
    notes = notes or {}
    for w in sorted({(m or "").lower() for m in members if m}):
        rec = st.get(w) if isinstance(st.get(w), dict) else None
        tail = f" ({_esc(notes[w])})" if notes.get(w) else ""
        if rec and rec.get("evicted"):
            out.append(f"  <code>{w[:10]}</code> LEFT: {int(rec['days'])} days below the door "
                       f"({_esc((rec.get('fails') or ['?'])[0])}){tail}")
        elif rec and rec.get("days"):
            out.append(f"  <code>{w[:10]}</code> below the door {int(rec['days'])} of {window} days: "
                       f"{_esc((rec.get('fails') or ['?'])[0])}{tail}")
        else:
            out.append(f"  <code>{w[:10]}</code> passes the door{tail}")
    return out


def check(members: Iterable[str], *, b_positions, a_positions, era: Optional[float],
          now: Optional[float] = None, send: Optional[Callable] = None,
          days: Optional[int] = None) -> dict:
    """Read every member against the gate once for this UTC day.

    Returns ``{"red": [...], "green": [...], "evicted": [...], "skipped": [...]}``
    (wallets). Never raises past a single member: one unreadable wallet is
    skipped and said, the rest are still read.
    """
    from src.copy_trading import ops_watch, promotion_gate, zset, zset_candidates as zc

    now = time.time() if now is None else now
    window = int(DECAY_DAYS if days is None else days)
    today = _day(now)
    st = _read()
    first_run = not os.path.exists(_p()) or st is None
    if st is None:
        logger.error("[zset-decay] zset-decay.json unreadable: the door re-opens from the history")
        st = {}
    out = {"red": [], "green": [], "evicted": [], "skipped": []}
    notes: dict = {}
    roster: dict = {}
    try:
        gone = zset.evicted_set()
    except Exception:  # noqa: BLE001
        gone = set()
    if first_run:
        # The door opens with the history already on the clock: a member
        # below it for weeks does not get a fresh window today. The roster
        # goes to the phone after today's read, below.
        st = seed_from_history(members, b_positions=b_positions, a_positions=a_positions,
                               era=era, now=now)
        _write(st)
    try:
        book_corr = promotion_gate.split_half_corr(b_positions, min_opened_ts=era)
    except Exception as exc:  # noqa: BLE001
        logger.warn(f"[zset-decay] book correlation unreadable: {exc}")
        book_corr = None
    changed = False
    for w in sorted({(m or "").lower() for m in members if m}):
        if w in gone:
            # Not a member any more (evicted this pass or earlier): a stale
            # member list must not restart its clock.
            st.pop(w, None)
            continue
        rec = st.get(w) if isinstance(st.get(w), dict) else None
        if rec and rec.get("last_day") == today:
            # Already read today: the second pass changes nothing.
            (out["red"] if rec.get("days") else out["green"]).append(w)
            roster[w] = dict(rec)
            continue
        try:
            cand = zc.evaluate(w, b_positions, a_positions, era=era, now=now, book_corr=book_corr)
        except Exception as exc:  # noqa: BLE001
            logger.warn(f"[zset-decay] {w[:10]} unreadable this pass: {exc}")
            out["skipped"].append(w)
            continue
        if cand is None:
            # No settled rows in the book the door reads: nothing to judge.
            out["skipped"].append(w)
            continue
        fails = decay_fails(cand.checks)
        idle = [d for lab, ok, d in cand.checks if not ok and str(lab).startswith("active within")]
        if idle:
            notes[w] = f"idle {idle[0]}"
        if not fails:
            if rec and int(rec.get("days") or 0) > 0:
                ops_watch.receipt(
                    "decay_recovered", before=f"{w[:10]} below the door {int(rec['days'])} day(s)",
                    after="passes the door again", detail="; ".join(rec.get("fails") or [])[:200],
                    push="WALLET", now=now, extra={"wallet": w, "days": int(rec["days"])})
                _say(send, f"🟢 <b>Back above the door</b> <code>{w}</code>\n"
                           f"It passes the gate again after {int(rec['days'])} day(s) below it.")
            st.pop(w, None)
            changed = True
            out["green"].append(w)
            roster[w] = {}
            continue
        n = (int(rec.get("days") or 0) if rec else 0) + 1
        labels = [lab for lab, _d in fails]
        detail = "; ".join(f"{lab}: {d}" for lab, d in fails)[:300]
        since = float(rec.get("since") or now) if rec else now
        st[w] = {"days": n, "since": since, "last_day": today, "fails": labels}
        roster[w] = dict(st[w])
        changed = True
        if n >= window:
            reason = (f"decayed: below the door {n} consecutive days "
                      f"(window {window}); {detail}")
            evicted = zset.evict(w, reason=reason)
            ops_watch.receipt(
                "decay_evict", before=f"{w[:10]} below the door {n} day(s)",
                after=("evicted (sticky)" if evicted else "EVICTION FAILED, still in Z"),
                detail=detail, push="WALLET", now=now,
                extra={"wallet": w, "days": n, "window": window, "fails": labels})
            if evicted:
                st.pop(w, None)
                gone.add(w)
                roster[w]["evicted"] = True
                out["evicted"].append(w)
                _say(send, f"🚫 <b>Left set Z on its own</b> <code>{w}</code>\n"
                           f"Below the door {n} days running (the window is {window}).\n"
                           f"{_esc(detail)}\n"
                           f"Real money no longer follows it. <code>/zset readmit</code> "
                           f"clears the record; the gate must pass it again.")
            else:
                out["red"].append(w)
                _say(send, f"⚠️ <b>EVICTION FAILED</b> <code>{w}</code>\n"
                           f"Below the door {n} days and the eviction record could not be "
                           f"written (check disk space on the VM). It is still in set Z.")
            continue
        out["red"].append(w)
        ops_watch.receipt(
            "decay_day", before=f"{w[:10]} in set Z", after=f"below the door {n} of {window}",
            detail=detail, push=("WALLET" if n == 1 else None), now=now,
            extra={"wallet": w, "days": n, "window": window, "fails": labels})
        if n == 1:
            _say(send, f"🟡 <b>Below the door</b> <code>{w}</code>\n{_esc(detail)}\n"
                       f"Day 1 of {window}: it stays in set Z and leaves on its own if this "
                       f"holds for {window} days. <code>/zset drop</code> ends it sooner.")
    if changed:
        _write(st)
    if first_run:
        lines = roster_lines(roster.keys(), roster, window=window, notes=notes)
        plain = " | ".join(l.replace("<code>", "").replace("</code>", "").strip() for l in lines)
        ops_watch.receipt("decay_roster", before="exit door opened", after=f"window {window} days",
                          detail=plain[:600], push="WALLET", now=now,
                          extra={"window": window, "days": {w: r.get("days") for w, r in st.items() if isinstance(r, dict)}})
        _say(send, "🚪 <b>Set Z's exit door is open</b>\n"
                   f"Every member is read against the gate once a day; {window} consecutive days below it "
                   f"and the wallet leaves on its own. Sample-size and idle checks never count. "
                   f"Counters start from the history, not from zero:\n" + "\n".join(lines))
    return out


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _say(send: Optional[Callable], text: str) -> None:
    if send is None:
        return
    try:
        send(text, None)
    except TypeError:
        try:
            send(text)
        except Exception as exc:  # noqa: BLE001
            logger.warn(f"[zset-decay] message failed: {exc}")
    except Exception as exc:  # noqa: BLE001
        logger.warn(f"[zset-decay] message failed: {exc}")
