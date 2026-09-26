"""Auto-admission into set Z, through the one door.

The owner's words on 2026-09-12 ("wallet selection, wallet approval ... runs
itself, full control") override the 2026-08-16 ruling that admission is his
tap. What survives of that ruling is the shape: he is informed with an
override in hand, never asked. The gate verdict IS the admission
(``zset_candidates.admit`` re-runs ``promotion_gate`` and ``zset.admit``
applies the rails; there is no force path here either), the receipt is the
same card he used to tap, with one button: Evict. ``ZSET_AUTO_ADMIT=false``
shuts the door in one line. A newly admitted wallet is on probation: one copy
a day until its first five live copies have settled.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from src.logger import logger

# A Z wallet judged by book A (the slice still thin) for this long is said
# on an [ops] line, which the important-lines file and the sidecar's
# fingerprint table read: the thin-slice path is an event the box can
# name, not a quiet default. Seven days, the manager's number (s-wo3xsp).
FALLBACK_SAID_AFTER_DAYS = 7.0
RAIL_STATE_FILE = "zset-rail-state.json"


def scan(*, send: Optional[Callable[[str, dict], None]] = None,
         now: Optional[float] = None, limit: int = 1) -> list[str]:
    """Admit every gate-passing wallet not yet in Z and not evicted, up to
    ``limit`` per scan (one wallet at a time keeps the probation honest).
    Returns the admitted wallets. Never raises."""
    from src.copy_trading import ops_watch, zset, zset_candidates as zc
    now = time.time() if now is None else now
    if not ops_watch.auto_admit_enabled():
        return []
    try:
        era, b_pos, a_pos = zc.load_books()
        passers, near, _corr = zc.candidates(b_pos, a_pos, era=era, now=now)
    except Exception as exc:
        logger.warn(f"[ops] auto-admit scan could not read the books: {exc}")
        return []
    in_z = zset.wallet_set()
    evicted = zset.evicted_set()
    admitted: list[str] = []
    for c in passers:
        w = (getattr(c, "wallet", "") or "").lower()
        if not w or w in in_z or w in evicted:
            continue
        if len(admitted) >= limit:
            break
        try:
            ok, checks, cand = zc.admit(w, era=era, b_positions=b_pos, a_positions=a_pos, now=now)
        except Exception as exc:
            logger.warn(f"[ops] auto-admit of {w[:10]} raised: {exc}")
            continue
        if not ok:
            fails = [lab for lab, good, det in checks if not good]
            ops_watch.receipt("auto_admit_refused", before=f"{w[:10]} passed the card",
                              after="gate refused at admission", detail="; ".join(fails)[:160], now=now)
            continue
        admitted.append(w)
        ops_watch.probation_start(w, now=now)
        detail = _card_line(cand)
        floor_line = _floor_line_on_admit(w, era=era, now=now)
        ops_watch.receipt("auto_admit", before=f"{w[:10]} not in Z", after="in set Z, on probation",
                          detail=detail, push="WALLET", now=now,
                          extra={"wallet": w, "rail": getattr(cand, "exec_rail", ""), "floor": floor_line})
        if send is not None:
            try:
                send(f"🟢 <b>Admitted to set Z on its own</b> <code>{w}</code>\n{detail}\n{floor_line}\n"
                     f"On probation: one copy a day until five live copies settle. "
                     f"Tap Evict to take it out; the eviction sticks.",
                     {"inline_keyboard": [[{"text": "Evict from set Z", "callback_data": f"zevict:{w}"}]]})
            except Exception as exc:
                logger.warn(f"[ops] auto-admit message failed: {exc}")
    try:
        rail_watch(passers + near, in_z=in_z | set(admitted), now=now)
    except Exception as exc:  # noqa: BLE001
        logger.warn(f"[ops] rail watch failed: {exc}")
    try:
        refresh_floors(in_z | set(admitted), skip=set(admitted), era=era, now=now, send=send)
    except Exception as exc:  # noqa: BLE001
        logger.warn(f"[ops] floor rows failed: {exc}")
    return admitted


def _floor_line_on_admit(w: str, *, era, now: float) -> str:
    """The wallet's floor row, computed at admission so the card carries it."""
    from src.copy_trading import wallet_floor
    try:
        r = wallet_floor.refresh(w, now=now, era=era, force=True)
        return wallet_floor.line(r[0] if r else None)
    except Exception as exc:  # noqa: BLE001
        logger.warn(f"[ops] floor row for {w[:10]} failed: {exc}")
        return "floor row: not measured (read failed)"


def refresh_floors(wallets: set, *, skip: set, era, now: float, send=None) -> list[str]:
    """Each Z wallet's four-way floor row, at most once a day per wallet.
    A row whose chosen floor MOVED is one line on the phone; an unchanged
    row is a ledger row only. Returns the wallets whose floor moved."""
    from src.copy_trading import ops_watch, wallet_floor
    moved: list[str] = []
    for w in sorted(wallets):
        if w in skip:
            continue
        r = wallet_floor.refresh(w, now=now, era=era)
        if r is None:
            continue
        row, before, after = r
        changed = (before or 0) != (after or 0)
        line = wallet_floor.line(row)
        ops_watch.receipt("floor_row", before=f"{w[:10]} floor {before or 'global'}",
                          after=f"floor {after or 'global'}" + (" (moved)" if changed else " (same)"),
                          detail=line[:300], push=("WALLET" if changed else None), now=now,
                          extra={"wallet": w, "floor_before": before, "floor_after": after,
                                 "live": wallet_floor.enabled()})
        if changed:
            moved.append(w)
            if send is not None:
                try:
                    live = ("real money copies it from there" if wallet_floor.enabled()
                            else "evidence only: LIVE_PER_WALLET_MIN_USD is off, real money keeps the global floor")
                    send(f"📏 <b>Floor moved</b> <code>{w}</code>: ${before or 0:.0f} to ${after or 0:.0f}\n{line}\n{live}", None)
                except Exception as exc:  # noqa: BLE001
                    logger.warn(f"[ops] floor message failed: {exc}")
    return moved


def rail_watch(cands: list, *, in_z: set, now: float) -> dict:
    """Which rail judged each Z wallet at this scan, with the day it went
    on the fallback. A wallet on book A for FALLBACK_SAID_AFTER_DAYS is said
    on an [ops] line the sidecar's fingerprint table reads."""
    from src.copy_trading import ops_watch, zset
    d = ops_watch._read_json(ops_watch._p(RAIL_STATE_FILE))
    seen = set()
    for c in cands:
        w = (getattr(c, "wallet", "") or "").lower()
        if not w or w not in in_z:
            continue
        seen.add(w)
        rail = getattr(c, "exec_rail", "") or ""
        rec = d.get(w) if isinstance(d.get(w), dict) else None
        if rec is None or rec.get("rail") != rail:
            rec = {"rail": rail, "since": now, "said": False}
        rec["n_matched"] = int(getattr(c, "real_n", 0) or 0)
        rec["last"] = now
        if rail == zset.RAIL_BOOK_A:
            days = (now - float(rec.get("since") or now)) / 86400.0
            if days >= FALLBACK_SAID_AFTER_DAYS and not rec.get("said"):
                logger.warning(f"[ops] {w[:10]} judged by book A for {days:.0f} days: the real-quote "
                               f"slice is still thin ({rec['n_matched']} of {zset.REAL_QUOTE_MIN_N} matched)")
                rec["said"] = True
        d[w] = rec
    for w in list(d):
        if w not in seen and w not in in_z:
            d.pop(w, None)
    ops_watch._write_json(ops_watch._p(RAIL_STATE_FILE), d)
    return d


def _card_line(c) -> str:
    try:
        n = len(getattr(c, "settled", []) or [])
        parts = [f"{n} settled paper copies"]
        for label, attr in (("paper ROI", "paper_roi"), ("trimmed", "trimmed_roi"), ("ideal", "ideal_roi")):
            v = getattr(c, attr, None)
            if v is not None:
                parts.append(f"{label} {float(v) * 100:+.1f}%")
        # Which rail answered the execution question, with its sample: the
        # slice's n, or book A because the slice is thin.
        from src.copy_trading import zset
        rail, rn, rr = getattr(c, "exec_rail", ""), int(getattr(c, "real_n", 0) or 0), getattr(c, "real_roi", None)
        if rail == zset.RAIL_SLICE and rr is not None:
            parts.append(f"real quotes {float(rr) * 100:+.1f}% over {rn} matched")
        elif rail:
            parts.append(f"execution judged by book A (slice thin, {rn} of {zset.REAL_QUOTE_MIN_N} matched)")
        return ", ".join(parts)
    except Exception:
        return "gate passed"
