"""Live limits the analyst may move, and the last number the owner typed.

Manager ruling (s-qbzbrw, 2026-09-22, "Last Number You Typed", unsigned):
each live parameter the AI analyst is allowed to touch has an OWNER value
(the number he last ruled on, which lives in deploy.yml / the env), an
ANALYST value with an expiry, and a BAND the analyst value must sit in. The
analyst may only reduce money at risk or move timing; anything that raises
exposure is owner-only forever (budget, drawdown floor, set Z, stake or cap
above the owner value). The band is a table in code, not a file the analyst
can edit. When the analyst value expires it snaps back to the owner's, so a
forgotten experiment costs at most ANALYST_TTL_S.

Readers call ``current(name)``; the bot never reads the analyst file
directly. Unknown parameter, malformed file, out-of-band value, expired
value: the owner's number. A leaf module: config only.
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

from src.config import CONFIG

FILE = "live-limits.json"
ANALYST_TTL_S = 24 * 3600.0

# name -> (owner attribute on CONFIG or env, band as (lo, hi), kind)
# ``lo``/``hi`` are absolute; the analyst may only move DOWN from the owner
# value for money parameters ("money"), either way for timing ("timing").
TABLE = {
    "LIVE_MAX_PER_WALLET_DAY": {"env": "LIVE_MAX_PER_WALLET_DAY", "attr": "live_max_per_wallet_day", "default": 3, "band": (1, 3), "kind": "money", "type": int},
    # Not the per-copy fraction: at the current budget a lower fraction puts a
    # copy under Polymarket's $5 order minimum and the governor refuses to
    # trade at all, so "reduce the stake" would read as "stop trading" with
    # no line saying why. It returns when the band can be tied to the budget.
    "FETCH_INTERVAL": {"env": "FETCH_INTERVAL", "attr": "fetch_interval", "default": 3, "band": (2, 5), "kind": "timing", "type": float},
    "OPS_REARM_CLEAR_S": {"env": "OPS_REARM_CLEAR_S", "default": 900.0, "band": (600.0, 1800.0), "kind": "timing", "type": float},
    "OPS_REARM_MAX_PER_DAY": {"env": "OPS_REARM_MAX_PER_DAY", "default": 3, "band": (1, 3), "kind": "money", "type": int},
    "FORM_DAYS": {"env": "FORM_DAYS", "default": 14.0, "band": (7.0, 21.0), "kind": "timing", "type": float},
}


def _path() -> str:
    return os.path.join(CONFIG.data_dir, FILE)


def _read() -> dict:
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(d: dict) -> bool:
    try:
        os.makedirs(CONFIG.data_dir, exist_ok=True)
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, _path())
        return True
    except OSError:
        return False


def owner_value(name: str):
    """The number the owner last ruled on: the env (deploy.yml writes his
    rulings there), else the table's default."""
    spec = TABLE.get(name)
    if spec is None:
        return None
    # The validated CONFIG first (it is what the bot and its tests set), the
    # raw env for parameters that live only as module constants, then the
    # table default.
    attr = spec.get("attr")
    if attr and hasattr(CONFIG, attr):
        try:
            return spec["type"](getattr(CONFIG, attr))
        except (TypeError, ValueError):
            pass
    raw = os.environ.get(spec["env"])
    try:
        return spec["type"](raw) if raw not in (None, "") else spec["type"](spec["default"])
    except (TypeError, ValueError):
        return spec["type"](spec["default"])


def propose(name: str, value, *, why: str, now: Optional[float] = None,
            ttl_s: float = ANALYST_TTL_S) -> tuple[bool, str]:
    """The analyst's move. Refused unless the parameter is in the table, the
    value sits in its band, and, for a money parameter, it does not exceed
    the owner's value. Never raises."""
    now = time.time() if now is None else now
    spec = TABLE.get(name)
    if spec is None:
        return (False, f"{name} is not a parameter the analyst may move")
    try:
        v = spec["type"](value)
    except (TypeError, ValueError):
        return (False, f"{name}: {value!r} is not a {spec['type'].__name__}")
    lo, hi = spec["band"]
    if not (lo <= v <= hi):
        return (False, f"{name}: {v} is outside the band [{lo}, {hi}]")
    own = owner_value(name)
    if spec["kind"] == "money" and own is not None and v > own:
        return (False, f"{name}: {v} exceeds the owner's {own}; money moves down only")
    d = _read()
    d[name] = {"analyst_value": v, "owner_value": own, "since": now, "expires_at": now + ttl_s,
               "why": str(why or "")[:200]}
    if not _write(d):
        return (False, "could not persist the limit")
    return (True, f"{name} = {v} until {time.strftime('%m-%d %H:%M', time.gmtime(now + ttl_s))} UTC (owner {own})")


def clear(name: str) -> bool:
    d = _read()
    if name not in d:
        return False
    d.pop(name, None)
    return _write(d)


def current(name: str, now: Optional[float] = None):
    """What the bot uses now: the analyst's value while it is valid and
    in band, else the owner's."""
    now = time.time() if now is None else now
    own = owner_value(name)
    spec = TABLE.get(name)
    if spec is None:
        return own
    rec = _read().get(name)
    if not isinstance(rec, dict):
        return own
    try:
        v = spec["type"](rec.get("analyst_value"))
        exp = float(rec.get("expires_at") or 0)
    except (TypeError, ValueError):
        return own
    lo, hi = spec["band"]
    if now >= exp or not (lo <= v <= hi):
        return own
    if spec["kind"] == "money" and own is not None and v > own:
        return own
    return v


def lines(now: Optional[float] = None) -> list[str]:
    """For the digest: every parameter, the owner's number, and the analyst's
    where one is in force."""
    now = time.time() if now is None else now
    out = []
    d = _read()
    for name, spec in TABLE.items():
        own = owner_value(name)
        cur = current(name, now)
        rec = d.get(name) if isinstance(d.get(name), dict) else None
        if rec and cur != own:
            left = (float(rec.get("expires_at") or 0) - now) / 3600.0
            out.append(f"{name}: {cur} (analyst, {left:.1f} h left, owner {own}): {str(rec.get('why') or '')[:80]}")
        else:
            out.append(f"{name}: {own} (owner) band {spec['band'][0]}..{spec['band'][1]}")
    return out
