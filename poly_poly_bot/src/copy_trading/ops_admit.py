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


def scan(*, send: Optional[Callable[[str, dict], None]] = None,
         now: Optional[float] = None, limit: int = 2) -> list[str]:
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
        ops_watch.receipt("auto_admit", before=f"{w[:10]} not in Z", after="in set Z, on probation",
                          detail=detail, push="WALLET", now=now, extra={"wallet": w})
        if send is not None:
            try:
                send(f"🟢 <b>Admitted to set Z on its own</b> <code>{w}</code>\n{detail}\n"
                     f"On probation: one copy a day until five live copies settle. "
                     f"Tap Evict to take it out; the eviction sticks.",
                     {"inline_keyboard": [[{"text": "Evict from set Z", "callback_data": f"zevict:{w}"}]]})
            except Exception as exc:
                logger.warn(f"[ops] auto-admit message failed: {exc}")
    return admitted


def _card_line(c) -> str:
    try:
        n = len(getattr(c, "settled", []) or [])
        parts = [f"{n} settled paper copies"]
        for label, attr in (("paper ROI", "paper_roi"), ("trimmed", "trimmed_roi"), ("ideal", "ideal_roi")):
            v = getattr(c, attr, None)
            if v is not None:
                parts.append(f"{label} {float(v) * 100:+.1f}%")
        return ", ".join(parts)
    except Exception:
        return "gate passed"
