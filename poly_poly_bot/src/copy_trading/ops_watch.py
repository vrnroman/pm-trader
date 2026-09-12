"""The watcher: the bot reads its own logs so the owner does not have to.

Two grammars, one verb. A PRESENCE line is a bad line that appeared
(DISARMED, "exposure full", "could not read equity", SEND FAILED, TRIPPED); an
ABSENCE is a good line that did not appear by its deadline (no copy for days
while the followed wallets kept trading; no daily line by 09:00 UTC; the
guard pass failing pass after pass). Each has a playbook: heal on its own
inside the auto tier, or escalate with the evidence. Every action writes one
factual receipt, state before -> state after, to ``data/ops-ledger.jsonl``;
the daily and weekly lines are rendered from that ledger, never narrated.

Money policy (manager s-g8int5 r1, at a bankroll of about $67): push on a
single settled loss of at least 15% of the bankroll, a day's losses of at
least 10%, four losing copies in a row, equity within 20% of the floor (with
the top-up that would restore it), every eviction, a bankroll milestone
crossed either way ($50, $100), every auto-admission (receipt card with an
Evict button), every self-heal that failed or hit its cap, every floor trip.
Confidence numbers stay in the ledger, never in a message.

This month's failures were all silent until a human read the logs a week
late: the arm fell off and 22 h of copies were skipped; the exposure ledger
read "full" for four days with nothing open; the guard loop threw on every
pass for a week. None of them should have needed a human.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from src.config import CONFIG
from src.logger import logger

LEDGER_FILE = "ops-ledger.jsonl"
STATE_FILE = "ops-watch.json"
MONEY_STATE_FILE = "money-state.json"
ESCALATION_FILE = "ops-escalation.json"
PROBATION_FILE = "ops-probation.json"


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def _env_i(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return int(default)


# --- the numbers (env-tunable; the manager's LOW-CONFIDENCE ones are named) ---
LOSS_SINGLE_FRAC = _env_f("OPS_PUSH_SINGLE_LOSS_FRAC", 0.15)
LOSS_DAILY_FRAC = _env_f("OPS_PUSH_DAILY_LOSS_FRAC", 0.10)
LOSS_STREAK_N = _env_i("OPS_PUSH_LOSS_STREAK", 4)          # manager: 4, LOW-CONFIDENCE
FLOOR_NEAR_FRAC = _env_f("OPS_PUSH_FLOOR_NEAR_FRAC", 0.20)
MILESTONES = tuple(float(x) for x in os.environ.get("OPS_PUSH_MILESTONES", "50,100").split(",") if x.strip())
REARM_CLEAR_S = _env_f("OPS_REARM_CLEAR_S", 900.0)            # manager: 15 min, LOW-CONFIDENCE
REARM_MAX_PER_DAY = _env_i("OPS_REARM_MAX_PER_DAY", 3)        # manager: K=3, LOW-CONFIDENCE
NO_COPY_DAYS = _env_f("OPS_NO_COPY_DAYS", 3.0)
NO_COPY_MIN_SIGNALS = _env_i("OPS_NO_COPY_MIN_SIGNALS", 3)
GUARD_FAIL_STREAK = _env_i("OPS_GUARD_FAIL_STREAK", 6)        # six passes = 30 min
DAILY_LINE_DEADLINE_UTC_H = _env_f("OPS_DAILY_LINE_DEADLINE_H", 9.0)
PROBATION_SETTLED_N = _env_i("ZSET_PROBATION_SETTLED_N", 5)
PROBATION_COPIES_PER_DAY = _env_i("ZSET_PROBATION_COPIES_PER_DAY", 1)


def auto_admit_enabled() -> bool:
    v = str(os.environ.get("ZSET_AUTO_ADMIT", "true")).strip().lower()
    return v in ("1", "true", "yes", "on")


# --- the presence grammar: lines the splitter keeps and the watcher reads ---
IMPORTANT_PATTERNS = [
    r"\[LIVE\]", r"\[verify\] (FILLED|UNFILLED|PARTIAL)", r"\[recovery\]",
    r"\[live\] (ARMED|DISARMED|HARD DISARM|disarm)", r"DISARMED",
    r"\[guard\] (cancelled|could not|pass failed|disarm|exposure reconcile failed)",
    r"Self-disarmed", r"\[tiered-risk\] .*(released|Recorded|carried a legacy|unreadable)",
    r"exposure full", r"\[daily-cap\]", r"spend guard closed", r"cash on chain",
    r"\[zset\] (EVICTED|ADMITTED|admitted)", r"\[ops\]", r"\[disk-watch\] (TRIPPED|still)",
    r"\[redeemer\] .*(ERROR|cannot|winner)", r"SEND FAILED", r"real-money line",
    r"Traceback", r"\bERROR\b", r"\bCRITICAL\b", r"Bot started", r"shutting down",
    r"pending orders file unreadable", r"\[testorder\]", r"Test order",
]
_IMPORTANT_RE = re.compile("|".join(f"(?:{p})" for p in IMPORTANT_PATTERNS))


def is_important(line: str) -> bool:
    """The deterministic split: no model, one regex, the same one everywhere."""
    return bool(_IMPORTANT_RE.search(line or ""))


# --------------------------------------------------------------------------- #
# Paths and small io
# --------------------------------------------------------------------------- #

def _p(name: str) -> str:
    return os.path.join(CONFIG.data_dir, name)


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: str, d: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, path)
        return True
    except OSError as exc:
        logger.error(f"[ops] state write failed for {os.path.basename(path)}: {exc}")
        return False


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# The ledger: one factual line per autonomous action or money event
# --------------------------------------------------------------------------- #

def receipt(kind: str, *, before=None, after=None, detail: str = "",
            push: Optional[str] = None, now: Optional[float] = None,
            extra: Optional[dict] = None) -> dict:
    """Append one row. ``push`` is the message class if the row was also
    pushed (DEAL/WALLET/BOT), else None. Never raises."""
    now = time.time() if now is None else now
    row = {"ts": now, "day": _day(now), "kind": kind, "before": before, "after": after,
           "detail": detail, "push": push}
    if extra:
        row.update(extra)
    try:
        os.makedirs(CONFIG.data_dir, exist_ok=True)
        with open(_p(LEDGER_FILE), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.error(f"[ops] ledger append failed: {exc}")
    logger.info(f"[ops] {kind}: {before!r} -> {after!r}{(' | ' + detail) if detail else ''}")
    return row


def ledger_rows(since_ts: float = 0.0, kinds: Optional[set] = None) -> list[dict]:
    out: list[dict] = []
    try:
        with open(_p(LEDGER_FILE), encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(r, dict):
                    continue
                if float(r.get("ts") or 0) < since_ts:
                    continue
                if kinds and r.get("kind") not in kinds:
                    continue
                out.append(r)
    except OSError:
        pass
    return out


# --------------------------------------------------------------------------- #
# Money state snapshot (read by the digest and by the routine)
# --------------------------------------------------------------------------- #

def write_money_state(d: dict, now: Optional[float] = None) -> None:
    now = time.time() if now is None else now
    d = dict(d)
    d["ts"] = now
    d["day"] = _day(now)
    _write_json(_p(MONEY_STATE_FILE), d)


# --------------------------------------------------------------------------- #
# Settlements and the push policy
# --------------------------------------------------------------------------- #

@dataclass
class Settlement:
    token_id: str
    wallet: str
    cost: float
    payout: float
    tier: str = ""
    title: str = ""

    @property
    def pnl(self) -> float:
        return round(self.payout - self.cost, 2)

    @property
    def won(self) -> bool:
        return self.payout > self.cost


def record_settlements(settled: list[Settlement], *, equity: Optional[float],
                       stated: Optional[float], floor: Optional[float],
                       send: Optional[Callable[[str], None]], now: Optional[float] = None) -> list[str]:
    """Book each settlement as a ledger row and apply the push policy. Returns
    the messages pushed (for tests)."""
    now = time.time() if now is None else now
    st = _read_json(_p(STATE_FILE))
    pushed: list[str] = []
    bank = float(equity) if equity is not None else (float(stated) if stated else None)
    streak = int(st.get("loss_streak") or 0)
    day = _day(now)
    day_pnl = float(st.get("day_pnl") or 0.0) if st.get("day_pnl_day") == day else 0.0
    for s in settled:
        receipt("settled", before=f"open ${s.cost:.2f}", after=f"paid ${s.payout:.2f}",
                detail=f"{'won' if s.won else 'lost'} {s.pnl:+.2f} on '{s.title[:40]}' "
                       f"({s.wallet[:10]}, tier {s.tier or '?'})", now=now,
                extra={"token_id": s.token_id, "wallet": s.wallet, "pnl": s.pnl, "won": s.won})
        day_pnl = round(day_pnl + s.pnl, 2)
        streak = 0 if s.won else streak + 1
        _probation_settled(s.wallet, now)
        if bank and s.pnl < 0 and abs(s.pnl) >= LOSS_SINGLE_FRAC * bank:
            pushed.append(_push(send, f"💸 <b>Loss of ${abs(s.pnl):.2f}</b> on "
                                      f"'{s.title[:40]}' ({s.wallet[:10]}). Bankroll ${bank:,.2f}.",
                                "single_loss", now))
        if streak and streak == LOSS_STREAK_N:
            pushed.append(_push(send, f"📉 <b>{streak} losing copies in a row</b>, "
                                      f"day {day_pnl:+.2f}. Bankroll ${bank:,.2f}." if bank else
                                      f"📉 <b>{streak} losing copies in a row</b>, day {day_pnl:+.2f}.",
                                "loss_streak", now))
    if bank and day_pnl < 0 and abs(day_pnl) >= LOSS_DAILY_FRAC * bank and not st.get("day_loss_pushed") == day:
        pushed.append(_push(send, f"📉 <b>Today's losses reach ${abs(day_pnl):.2f}</b> "
                                  f"({LOSS_DAILY_FRAC * 100:.0f}% of the ${bank:,.2f} bankroll).",
                            "daily_loss", now))
        st["day_loss_pushed"] = day
    st.update({"loss_streak": streak, "day_pnl": day_pnl, "day_pnl_day": day})
    _write_json(_p(STATE_FILE), st)
    return [m for m in pushed if m]


def check_bankroll(*, equity: Optional[float], floor: Optional[float],
                   send: Optional[Callable[[str], None]], now: Optional[float] = None) -> list[str]:
    """Floor distance and milestones, say-once by edge."""
    now = time.time() if now is None else now
    if equity is None:
        return []
    st = _read_json(_p(STATE_FILE))
    pushed: list[str] = []
    eq = float(equity)
    if floor is not None and float(floor) > 0:
        # Edge with hysteresis: enters inside the band, leaves only once the
        # bankroll is clear of it by another half band, and never more than
        # once a day. At an $80 budget the band is $56 to $67, where the
        # bankroll sits most days; without this it said so every crossing.
        band = float(floor) * (1.0 + FLOOR_NEAR_FRAC)
        clear = float(floor) * (1.0 + 1.5 * FLOOR_NEAR_FRAC)
        was = bool(st.get("floor_near"))
        near = eq <= band if not was else eq < clear
        last_day = st.get("floor_near_day")
        if near and not was and last_day != _day(now):
            gap = max(0.0, band - eq)
            pushed.append(_push(send, f"⚠️ <b>Bankroll ${eq:,.2f} is within {FLOOR_NEAR_FRAC * 100:.0f}% "
                                      f"of the ${float(floor):,.0f} floor.</b> A top-up of about "
                                      f"${gap + 5:,.0f} would restore the margin; under the floor the "
                                      f"arm comes off and stays off until /live CONFIRM.",
                                "floor_near", now))
            st["floor_near_day"] = _day(now)
        st["floor_near"] = bool(near)
    last = st.get("last_equity")
    if last is not None:
        for m in MILESTONES:
            lo, hi = sorted((float(last), eq))
            if lo < m <= hi and eq >= m:
                pushed.append(_push(send, f"🏁 <b>Bankroll crossed ${m:,.0f}</b> upward: ${eq:,.2f}.", "milestone", now))
            elif lo < m <= hi and eq < m:
                pushed.append(_push(send, f"🏁 <b>Bankroll fell under ${m:,.0f}</b>: ${eq:,.2f}.", "milestone", now))
    st["last_equity"] = eq
    _write_json(_p(STATE_FILE), st)
    return [m for m in pushed if m]


def _push(send: Optional[Callable[[str], None]], text: str, kind: str, now: float) -> str:
    receipt(f"push:{kind}", after=text[:120], push="DEAL", now=now)
    if send is not None:
        try:
            send(text)
        except Exception as exc:
            logger.warn(f"[ops] push failed ({kind}): {exc}")
    return text


# --------------------------------------------------------------------------- #
# Absence grammar: deadline clocks
# --------------------------------------------------------------------------- #

def note_guard_pass(ok: bool, error: str = "", now: Optional[float] = None,
                    send: Optional[Callable[[str], None]] = None) -> Optional[str]:
    """The guard loop reports each pass. A streak of failures is escalated
    once per streak (this is how 'could not read equity' hid for a week)."""
    now = time.time() if now is None else now
    st = _read_json(_p(STATE_FILE))
    streak = 0 if ok else int(st.get("guard_fail_streak") or 0) + 1
    st["guard_fail_streak"] = streak
    st["guard_last_error"] = "" if ok else error[:200]
    msg = None
    if streak == GUARD_FAIL_STREAK:
        msg = _push(send, f"🚨 <b>The guard loop has failed {streak} passes in a row.</b> "
                          f"Last error: {error[:160]}. The bankroll floor is not being watched "
                          f"until this clears.", "guard_failing", now)
        receipt("guard_failing", before="passing", after=f"{streak} failed passes", detail=error[:160], now=now)
    if ok and int(st.get("guard_fail_streak_prev") or 0) >= GUARD_FAIL_STREAK:
        receipt("guard_recovered", before="failing", after="passing", now=now)
    st["guard_fail_streak_prev"] = streak
    _write_json(_p(STATE_FILE), st)
    return msg


def note_daily_line(sent: bool, now: Optional[float] = None) -> None:
    st = _read_json(_p(STATE_FILE))
    st["daily_line_day"] = _day(now if now is not None else time.time())
    st["daily_line_sent"] = bool(sent)
    _write_json(_p(STATE_FILE), st)


def check_absences(*, followed_signals_3d: int, copies_3d: int, armed: bool,
                   send: Optional[Callable[[str], None]], now: Optional[float] = None) -> list[str]:
    """No copy for days while the wallets kept trading; no daily line by the
    deadline. Each escalates once per episode."""
    now = time.time() if now is None else now
    st = _read_json(_p(STATE_FILE))
    pushed: list[str] = []
    quiet = armed and copies_3d == 0 and followed_signals_3d >= NO_COPY_MIN_SIGNALS
    if quiet and not st.get("no_copy_pushed"):
        pushed.append(_push(send, f"🔇 <b>No copy in {NO_COPY_DAYS:.0f} days</b> while the followed "
                                  f"wallets made {followed_signals_3d} qualifying trades and the arm is on. "
                                  f"Something is refusing every copy; the last refusals are in the ledger.",
                            "no_copy", now))
        receipt("no_copy", before=f"{followed_signals_3d} signals", after="0 copies", now=now)
    st["no_copy_pushed"] = bool(quiet)
    dt = datetime.fromtimestamp(now, tz=timezone.utc)
    day = dt.strftime("%Y-%m-%d")
    hour = dt.hour + dt.minute / 60.0
    if hour >= DAILY_LINE_DEADLINE_UTC_H and st.get("daily_line_day") != day and st.get("daily_line_missing_day") != day:
        if st.get("daily_line_day"):  # never on the very first day of the watcher
            pushed.append(_push(send, f"🕘 <b>No 08:00 real-money line today</b> by "
                                      f"{DAILY_LINE_DEADLINE_UTC_H:.0f}:00 UTC. The reporter did not run or "
                                      f"its send failed; check the ledger and the log.", "no_daily_line", now))
            receipt("no_daily_line", before="expected by 09:00 UTC", after="missing", now=now)
        st["daily_line_missing_day"] = day
    _write_json(_p(STATE_FILE), st)
    return [m for m in pushed if m]


# --------------------------------------------------------------------------- #
# Self re-arm after a transient trigger
# --------------------------------------------------------------------------- #

TRANSIENT_MARKERS = ("consecutive cycle failures", "no trade data for", "redeemer is not working")


def is_transient_reason(why: str) -> bool:
    w = str(why or "")
    return any(m in w for m in TRANSIENT_MARKERS)


def maybe_rearm(*, arm: dict, guard_state: dict, condition_clear: bool,
                now: Optional[float] = None, send: Optional[Callable[[str], None]] = None,
                arm_fn: Optional[Callable] = None) -> Optional[dict]:
    """The guard pulled the arm for a reason about OUR reliability (crash
    streak, dead feed, stuck redemption) and the condition has been clear
    for REARM_CLEAR_S: re-arm with a receipt, at most REARM_MAX_PER_DAY per
    signature per day; the next one escalates instead. A floor trip never
    self-clears."""
    now = time.time() if now is None else now
    if arm.get("armed") is True:
        return None
    by = str(arm.get("by") or "")
    if not by.startswith("live-guard"):
        return None  # the owner or a run disarmed it: theirs to arm
    why = str(guard_state.get("self_disarm_reason") or "")
    if by == "live-guard:floor" or not is_transient_reason(why):
        return None
    st = _read_json(_p(STATE_FILE))
    sig = why.split(":")[0][:60]
    key = f"clear_since:{sig}"
    if not condition_clear:
        st.pop(key, None)
        _write_json(_p(STATE_FILE), st)
        return None
    since = st.get(key)
    if since is None:
        st[key] = now
        _write_json(_p(STATE_FILE), st)
        return None
    if now - float(since) < REARM_CLEAR_S:
        return None
    day = _day(now)
    counts = st.get("rearms") if isinstance(st.get("rearms"), dict) else {}
    n = int(counts.get(f"{day}:{sig}") or 0)
    if n >= REARM_MAX_PER_DAY:
        if st.get("rearm_cap_pushed") != f"{day}:{sig}":
            _push(send, f"🚨 <b>Re-armed {n} times today for '{sig}' and it keeps coming back.</b> "
                        f"Not re-arming again; send /live CONFIRM when you have looked.", "rearm_cap", now)
            receipt("rearm_cap", before=f"{n} self re-arms", after="escalated", detail=sig, now=now)
            st["rearm_cap_pushed"] = f"{day}:{sig}"
            _write_json(_p(STATE_FILE), st)
        return None
    if arm_fn is None:
        from src.copy_trading import live_mode
        arm_fn = live_mode.arm
    ok, detail = arm_fn(reason=f"watcher: '{sig}' clear for {REARM_CLEAR_S / 60:.0f} min", by=f"watcher:{sig[:24]}")
    counts[f"{day}:{sig}"] = n + 1
    st["rearms"] = {k: v for k, v in counts.items() if k.startswith(day)}
    st.pop(key, None)
    _write_json(_p(STATE_FILE), st)
    row = receipt("rearm", before=f"disarmed by {by}: {why[:60]}", after="armed" if ok else f"arm refused: {detail}",
                  detail=f"self re-arm {n + 1}/{REARM_MAX_PER_DAY} today", now=now,
                  push="DEAL" if ok else "BOT")
    if send is not None:
        try:
            send(("✅ <b>Re-armed</b> on its own: " if ok else "⚠️ <b>Could not re-arm</b>: ")
                 + f"'{sig}' had been clear for {REARM_CLEAR_S / 60:.0f} minutes"
                 + ("" if ok else f" ({detail})") + f". Self re-arm {n + 1} of {REARM_MAX_PER_DAY} today.")
        except Exception as exc:
            logger.warn(f"[ops] re-arm message failed: {exc}")
    return row


# --------------------------------------------------------------------------- #
# Escalations delivered from the routine (via the digest workflow)
# --------------------------------------------------------------------------- #

def deliver_escalation(send: Optional[Callable[[str], None]], now: Optional[float] = None) -> Optional[dict]:
    """``data/ops-escalation.json`` is written by the digest workflow when the
    cloud routine left one. Send it once, keyed on its id, then move it aside."""
    now = time.time() if now is None else now
    path = _p(ESCALATION_FILE)
    d = _read_json(path)
    if not d:
        return None
    st = _read_json(_p(STATE_FILE))
    eid = str(d.get("id") or "")
    text = str(d.get("message") or "").strip()
    if not eid or not text:
        try:
            os.replace(path, f"{path}.bad-{int(now)}")
        except OSError:
            pass
        return None
    if st.get("last_escalation_id") == eid:
        try:
            os.replace(path, f"{path}.sent-{eid[:12]}")
        except OSError:
            pass
        return None
    kind = str(d.get("kind") or "escalation")
    if send is not None:
        try:
            if kind == "fix":
                commit = str(d.get("commit") or "")[:10]
                send(f"🔧 <b>The watcher pushed a fix</b>{(' (' + commit + ')') if commit else ''}: {text[:1400]}")
            else:
                send(f"🧭 <b>From the watcher</b> ({kind}): {text[:1500]}")
        except Exception as exc:
            logger.warn(f"[ops] escalation send failed: {exc}")
            return None
    st["last_escalation_id"] = eid
    _write_json(_p(STATE_FILE), st)
    try:
        os.replace(path, f"{path}.sent-{eid[:12]}")
    except OSError:
        pass
    return receipt("escalation_delivered", before=f"routine {kind}", after="sent", detail=text[:120], push="BOT", now=now)


# --------------------------------------------------------------------------- #
# Probation for auto-admitted wallets
# --------------------------------------------------------------------------- #

def probation_start(wallet: str, now: Optional[float] = None) -> None:
    now = time.time() if now is None else now
    d = _read_json(_p(PROBATION_FILE))
    d[wallet.lower()] = {"since": now, "settled": 0}
    _write_json(_p(PROBATION_FILE), d)


def _probation_settled(wallet: str, now: float) -> None:
    d = _read_json(_p(PROBATION_FILE))
    w = (wallet or "").lower()
    if w in d:
        d[w]["settled"] = int(d[w].get("settled") or 0) + 1
        if d[w]["settled"] >= PROBATION_SETTLED_N:
            # The graduation shows its work: the trial's own settled rows.
            since = float(d[w].get("since") or 0.0)
            trial = [r for r in ledger_rows(since_ts=since, kinds={"settled"})
                     if str(r.get("wallet") or "").lower() == w][-PROBATION_SETTLED_N:]
            pnl = round(sum(float(r.get("pnl") or 0) for r in trial), 2)
            won = sum(1 for r in trial if r.get("won"))
            receipt("probation_over", before=f"{w[:10]} on probation",
                    after=f"{d[w]['settled']} settled live copies: {won} won, {pnl:+.2f}",
                    detail="; ".join(f"{str(r.get('detail') or '')[:38]}" for r in trial), now=now,
                    extra={"wallet": w, "trial": [{"token_id": r.get("token_id"), "pnl": r.get("pnl"), "won": r.get("won")} for r in trial]})
            d.pop(w, None)
        _write_json(_p(PROBATION_FILE), d)


def probation_cap(wallet: str) -> Optional[int]:
    """Copies per day allowed while on probation, or None when not on it."""
    d = _read_json(_p(PROBATION_FILE))
    return PROBATION_COPIES_PER_DAY if (wallet or "").lower() in d else None


# --------------------------------------------------------------------------- #
# Rendering from the ledger
# --------------------------------------------------------------------------- #

def wallet_ledger(now: Optional[float] = None, days: float = 30.0) -> list[dict]:
    """Per followed wallet, from the settled rows only: n settled, wins, net
    pnl. An aggregation, not a grade; nothing here ranks or decides."""
    now = time.time() if now is None else now
    out: dict = {}
    for r in ledger_rows(since_ts=now - days * 86400, kinds={"settled"}):
        w = str(r.get("wallet") or "").lower() or "?"
        a = out.setdefault(w, {"wallet": w, "settled": 0, "won": 0, "pnl": 0.0, "cost": 0.0})
        a["settled"] += 1
        a["won"] += 1 if r.get("won") else 0
        a["pnl"] = round(a["pnl"] + float(r.get("pnl") or 0), 2)
        try:
            a["cost"] = round(a["cost"] + float(str(r.get("before") or "").split("$")[-1]), 2)
        except ValueError:
            pass
    return sorted(out.values(), key=lambda a: a["wallet"])


def wallet_ledger_lines(now: Optional[float] = None, days: float = 30.0) -> list[str]:
    rows = wallet_ledger(now, days)
    if not rows:
        return [f"no settled live copies in the last {days:.0f} days"]
    return [f"{a['wallet'][:10]}: {a['settled']} settled, {a['won']} won, {a['pnl']:+.2f} on ${a['cost']:.2f}"
            for a in rows]


def weekly_line(now: Optional[float] = None) -> str:
    now = time.time() if now is None else now
    rows = ledger_rows(since_ts=now - 7 * 86400)
    settled = [r for r in rows if r.get("kind") == "settled"]
    pnl = round(sum(float(r.get("pnl") or 0) for r in settled), 2)
    won = sum(1 for r in settled if r.get("won"))
    heals = [r for r in rows if r.get("kind") in ("rearm", "guard_recovered", "escalation_delivered")]
    admits = [r for r in rows if r.get("kind") == "auto_admit"]
    evicts = [r for r in rows if r.get("kind") == "evict"]
    pushes = [r for r in rows if str(r.get("kind", "")).startswith("push:")]
    return (f"📒 This week from the ledger: {len(settled)} settled ({won} won), realized "
            f"{pnl:+.2f}; {len(heals)} self-heal(s), {len(admits)} auto-admission(s), "
            f"{len(evicts)} eviction(s), {len(pushes)} push(es) to you.")


def daily_line(now: Optional[float] = None) -> str:
    now = time.time() if now is None else now
    rows = ledger_rows(since_ts=now - 86400)
    settled = [r for r in rows if r.get("kind") == "settled"]
    pnl = round(sum(float(r.get("pnl") or 0) for r in settled), 2)
    won = sum(1 for r in settled if r.get("won"))
    heals = [r for r in rows if r.get("kind") in ("rearm", "guard_recovered")]
    if not rows:
        return "📒 ledger: nothing happened in the last 24h"
    return (f"📒 ledger, last 24h: {len(settled)} settled ({won} won) {pnl:+.2f}; "
            f"{len(heals)} self-heal(s); {sum(1 for r in rows if r.get('kind') == 'auto_admit')} auto-admission(s)")
