"""A copy floor per wallet, chosen by the gate (the owner's doc of
2026-09-24, part 3 §3.4 item 2).

The backward replay in that doc said the $150..300 bets of the watched
wallets are about as good as their $300+ bets in aggregate, and that the
set of good wallets changes with the floor: eleven wallets pass at $300 and
fail at $150 (their smaller bets lose), four the reverse. "A single global
threshold is the wrong knob." So the gate evaluates each set-Z wallet at
{300, 200, 150, 100}, keeps the WHOLE row on the Z record (n, ROI, trimmed
ROI at each floor, labelled for what it is), and picks the floor with the
best trimmed ROI among the ones that clear the gate's own bars, the higher
floor on a tie.

What the row is: copy-and-hold at the wallet's own price, first entry per
market, clean era, resolved via the resolution cache. It is the relative
effect of the floor, not the absolute answer (no mirrored exits, no
execution drag); the forward books B150 and B100 give that. The row says
so on every line.

What moves real money: nothing, until the owner sets
``LIVE_PER_WALLET_MIN_USD``. Off (the default), the row is evidence on the
record and on the phone and the live path keeps the global floor
(``LIVE_MIN_TRADER_BET_USD``, else the paper floor). ``true``: a Z wallet
whose record carries a chosen floor is copied from THAT floor, and a wallet
with no chosen floor keeps the global. A comma-separated wallet list: only
those wallets, the canary shape, so his first flip can be one wallet read
on the DEAL lines. Anything else reads as off and is said once. The switch
ships off because a limit that changes what real money copies is his to
move (the merge and the env), never the run's.

A leaf: config, promotion_state and the replay helpers; no logger writes
of its own beyond what the callers say.
"""
from __future__ import annotations

import os
import statistics
import time
from typing import Iterable, Optional

from src.config import CONFIG
from src.copy_trading import promotion_state
from src.logger import logger

THRESHOLDS = (300.0, 200.0, 150.0, 100.0)

# The row's own label, printed wherever the row is: the reader must never
# mistake a replay ROI for a ledger ROI.
ROW_LABEL = "backward replay (copy-and-hold at their price, first entry, clean era)"

# The record keys on the Z record. ``floor_usd`` is what the live path reads
# when the switch is on; ``floor_row`` is the evidence behind it.
ROW_KEY = "floor_row"
FLOOR_KEY = "floor_usd"

# A wallet's row is recomputed at most this often (the activity read is a
# cached disk file or a few data-api pages).
REFRESH_S = 24 * 3600.0

# Trimmed like set Z's concentration rail: the best three copies deleted.
DROP_TOP_N = 3


MODE_NONE, MODE_ALL, MODE_LIST = "none", "all", "list"
_TRUE = ("true", "1", "yes", "on", "all")
_FALSE = ("", "false", "0", "no", "off", "none")
_mode_said: set = set()


def mode(raw=None) -> tuple[str, frozenset]:
    """``LIVE_PER_WALLET_MIN_USD`` read fail-closed: ``(mode, wallets)``.

    ``true`` is every Z wallet with a chosen floor; a comma-separated list of
    addresses is those wallets only (the canary shape: one wallet's floor
    moves while the rest keep the global); ``false`` or unset is none. A
    value that is neither, or a list with a token that is not an address,
    reads as none and is said once on an [ops] line: a floor that moves
    real money must never switch on by a typo.
    """
    v = getattr(CONFIG, "live_per_wallet_min_usd", "false") if raw is None else raw
    text = str(v if v is not None else "").strip().lower()
    if text in _TRUE:
        return (MODE_ALL, frozenset())
    if text in _FALSE:
        return (MODE_NONE, frozenset())
    toks = [t.strip() for t in text.split(",") if t.strip()]
    good = [t for t in toks if t.startswith("0x") and len(t) == 42 and all(c in "0123456789abcdef" for c in t[2:])]
    if toks and len(good) == len(toks):
        return (MODE_LIST, frozenset(good))
    if text not in _mode_said:
        _mode_said.add(text)
        logger.warning(f"[ops] LIVE_PER_WALLET_MIN_USD={text[:60]!r} is neither true, false nor a wallet list: "
                       f"read as false, real money keeps the global floor")
    return (MODE_NONE, frozenset())


def enabled() -> bool:
    """Does a chosen floor move real money for anyone? False unless the
    owner set the switch to true or to a wallet list."""
    return mode()[0] != MODE_NONE


def applies_to(wallet: str) -> tuple[bool, str]:
    """Whether this wallet's chosen floor is live, and why in three words."""
    m, wallets = mode()
    key = (wallet or "").lower()
    if m == MODE_ALL:
        return (True, "all Z wallets")
    if m == MODE_LIST and key in wallets:
        return (True, "listed wallet")
    if m == MODE_LIST:
        return (False, "not listed")
    return (False, "switch off")


# --------------------------------------------------------------------------- #
# The row
# --------------------------------------------------------------------------- #

def _rois_at(buys: Iterable[object], min_usd: float) -> list[float]:
    from src.copy_trading.copy_replay import copy_and_hold_rois
    return copy_and_hold_rois(buys, min_usd=min_usd, first_entry_only=True)


def _cell(rois: list[float], *, min_n: int, min_roi: float, trimmed_min: float) -> dict:
    n = len(rois)
    if n == 0:
        return {"n": 0, "roi": None, "trimmed": None, "ok": False}
    mean = statistics.mean(rois)
    rest = sorted(rois)[:-DROP_TOP_N] if n > DROP_TOP_N else []
    trimmed = statistics.mean(rest) if rest else None
    ok = bool(n >= min_n and mean >= min_roi and trimmed is not None and trimmed >= trimmed_min)
    return {"n": n, "roi": round(mean, 4), "trimmed": (round(trimmed, 4) if trimmed is not None else None), "ok": ok}


def row_for(wallet: str, acts: list[dict], *, era: Optional[float], now: float,
            res_cache_dir: Optional[str], min_n: int, min_roi: float,
            trimmed_min: float = 0.0) -> dict:
    """The four-way row from a wallet's own activity. Pure given its inputs:
    resolutions come from the cache dir, never the network."""
    from src.copy_trading import market_resolution, wallet_context
    cids = {ev.get("conditionId") for ev in acts if ev.get("type") == "TRADE" and ev.get("conditionId")}
    res = {}
    for cid in cids:
        r = market_resolution._read_cache(cid, res_cache_dir)
        if r is not None:
            res[cid] = r
    ctx = wallet_context.build_context(wallet, acts, now=now, resolutions=res)
    buys = [b for b in ctx.buys if float(getattr(b, "ts", 0.0) or 0.0) >= float(era or 0.0)]
    at = {}
    for m in THRESHOLDS:
        at[str(int(m))] = _cell(_rois_at(buys, m), min_n=min_n, min_roi=min_roi, trimmed_min=trimmed_min)
    row = {"label": ROW_LABEL, "ts": now, "n_acts": len(acts), "n_resolved_markets": len(res),
           "era": era, "bars": {"min_n": min_n, "min_roi": min_roi, "trimmed_min": trimmed_min},
           "at": at}
    row["chosen"] = choose(row)
    return row


def choose(row: dict) -> Optional[float]:
    """The floor with the best trimmed ROI among those that clear the bars;
    the higher floor on a tie; None when none clears."""
    best = None
    for k, c in (row.get("at") or {}).items():
        if not c.get("ok"):
            continue
        key = (float(c.get("trimmed") if c.get("trimmed") is not None else -9.0), float(k))
        if best is None or key > best[0]:
            best = (key, float(k))
    return best[1] if best else None


def line(row: Optional[dict]) -> str:
    """One phone line for a row: ``copies at $150: 300 no (n=12) · 200 no
    (n=15, +4%) · 150 YES +16% (trimmed +9%, n=22) · 100 yes +12% ...``."""
    if not row:
        return "floor row: not measured yet"
    parts = []
    chosen = row.get("chosen")
    for k in (str(int(m)) for m in THRESHOLDS):
        c = (row.get("at") or {}).get(k) or {}
        n = int(c.get("n") or 0)
        if n == 0:
            parts.append(f"{k} none")
            continue
        roi = c.get("roi")
        tr = c.get("trimmed")
        tag = "YES" if chosen is not None and float(k) == float(chosen) else ("yes" if c.get("ok") else "no")
        s = f"{k} {tag} {roi * 100:+.0f}%" if roi is not None else f"{k} {tag}"
        s += f" (n={n}" + (f", trimmed {tr * 100:+.0f}%" if tr is not None else "") + ")"
        parts.append(s)
    head = (f"copies at ${chosen:.0f}" if chosen is not None else "no floor clears the bars, global floor stays")
    return f"{head}: " + " · ".join(parts) + f"; {ROW_LABEL}"


# --------------------------------------------------------------------------- #
# The record
# --------------------------------------------------------------------------- #

def stored(wallet: str) -> Optional[dict]:
    from src.copy_trading import zset
    rec = promotion_state.promoted_map(zset.SCOPE).get((wallet or "").lower())
    if not isinstance(rec, dict):
        return None
    row = rec.get(ROW_KEY)
    return row if isinstance(row, dict) else None


def stored_floor(wallet: str) -> Optional[float]:
    from src.copy_trading import zset
    rec = promotion_state.promoted_map(zset.SCOPE).get((wallet or "").lower())
    if not isinstance(rec, dict):
        return None
    try:
        v = float(rec.get(FLOOR_KEY) or 0.0)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def live_floor(wallet: str, default: float) -> float:
    """What real money copies this wallet from. The global floor unless the
    owner's switch covers this wallet AND the record carries a chosen floor."""
    return live_floor_why(wallet, default)[0]


def live_floor_why(wallet: str, default: float) -> tuple[float, str]:
    """``(floor, why)``: the floor and the reason it applies, for the phone."""
    on, why = applies_to(wallet)
    if not on:
        return (float(default), f"the global floor ({why})")
    v = stored_floor(wallet)
    if not v:
        return (float(default), f"the global floor (no chosen floor on the record; {why})")
    return (float(v), f"this wallet's own floor ({why})")


def _activity(wallet: str) -> Optional[list[dict]]:
    """The wallet's own activity: the discovery cache when fresh, else a
    read. None when the read failed (a failed read is never a row)."""
    from src.copy_trading import discovery_data
    try:
        before = len(discovery_data._activity_fetch_failures)
        acts = discovery_data.fetch_activity(
            wallet, getattr(CONFIG, "wallet_discovery_cache_dir", None),
            float(getattr(CONFIG, "wallet_discovery_activity_ttl_s", 108000) or 108000))
        if len(discovery_data._activity_fetch_failures) > before:
            return None
        return list(acts or [])
    except Exception as exc:  # noqa: BLE001
        logger.warn(f"[floor] {wallet[:10]} activity unreadable: {exc}")
        return None


def refresh(wallet: str, *, now: Optional[float] = None, era: Optional[float] = None,
            force: bool = False) -> Optional[tuple[dict, Optional[float], Optional[float]]]:
    """Recompute a Z wallet's row when it is older than REFRESH_S and store
    it on the record. Returns ``(row, floor_before, floor_after)`` when a row
    was written, None when nothing was (fresh, no record, unreadable)."""
    now = time.time() if now is None else now
    key = (wallet or "").lower()
    from src.copy_trading import zset
    rec = promotion_state.promoted_map(zset.SCOPE).get(key)
    if not isinstance(rec, dict):
        return None
    old = rec.get(ROW_KEY) if isinstance(rec.get(ROW_KEY), dict) else None
    if old and not force and now - float(old.get("ts") or 0.0) < REFRESH_S:
        return None
    acts = _activity(wallet)
    if acts is None:
        return None
    if era is None:
        from src.copy_trading import era_state
        era = era_state.era_floor_ts(os.path.join(CONFIG.data_dir, "ab_race_state.json"))
    row = row_for(wallet, acts, era=era, now=now,
                  res_cache_dir=getattr(CONFIG, "wallet_discovery_res_cache", None),
                  min_n=int(getattr(CONFIG, "copy_golive_min_settled", 15) or 15),
                  min_roi=float(getattr(CONFIG, "copy_promote_min_roi", 0.10) or 0.0))
    before = stored_floor(wallet)
    after = row.get("chosen")
    promotion_state.update_promoted(key, {ROW_KEY: row, FLOOR_KEY: after}, scope=zset.SCOPE)
    return (row, before, after)
