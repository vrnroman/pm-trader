"""Two clocks on every followed fill: when the chain showed it, when the api did.

Measured 2026-09-22 on the VM: the data api hands us a set-Z fill 18.4 s
after it happened at the median (p90 32.6 s) on a 3 s poll, so the floor is
the api's own indexing lag. The on-chain reader sees the OrderFilled event
a block or two after the fill. Before the chain is allowed to TRIGGER a copy,
it runs as a shadow: both sources stamp the same trade id here, and the
report says, from retained rows, how much earlier the chain saw each fill,
how many ids matched, how many the chain missed, and whether any id was
seen twice (the double-copy the id normalisation exists to prevent).

The cutover is a rule the bot applies itself and reports, never a tap
(owner ruling s-kac3t7: pre-approved words are the authorization; manager
s-qbzbrw: numbers LOW-CONFIDENCE, env-tunable): after ONCHAIN_SHADOW_DAYS or
ONCHAIN_SHADOW_MIN_MATCHED matched fills, whichever first, with zero
duplicate ids and at most ONCHAIN_MAX_MISSED_FRAC of api fills unseen by the
chain, the chain becomes the primary trigger and the api stays as the
deduplicated fallback. Any doubt keeps the shadow. A leaf module: no project
imports beyond the config.
"""
from __future__ import annotations

import json
import os
import statistics
import time
from typing import Optional

from src.config import CONFIG

ROWS_FILE = "two-clocks.jsonl"
PRIMARY_FILE = "onchain-primary.json"


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


SHADOW_DAYS = _env_f("ONCHAIN_SHADOW_DAYS", 7.0)
SHADOW_MIN_MATCHED = int(_env_f("ONCHAIN_SHADOW_MIN_MATCHED", 30))
MAX_MISSED_FRAC = _env_f("ONCHAIN_MAX_MISSED_FRAC", 0.05)
# A forced answer, either way: "true" pins the shadow, "false" pins primary.
_FORCE = os.environ.get("ONCHAIN_SHADOW", "").strip().lower()


def _rows_path() -> str:
    return os.path.join(CONFIG.data_dir, ROWS_FILE)


def _primary_path() -> str:
    return os.path.join(CONFIG.data_dir, PRIMARY_FILE)


def note(source: str, trade_id: str, *, their_ts: float, seen_at: float,
         target: str = "", token_id: str = "") -> None:
    """One row per (source, trade id): the fill's own time and when this
    source first saw it. Never raises."""
    row = {"ts": seen_at, "source": source, "id": trade_id, "their_ts": their_ts,
           "seen_at": seen_at, "lag_s": (seen_at - their_ts) if their_ts else None,
           "target": (target or "").lower(), "token_id": token_id}
    try:
        os.makedirs(CONFIG.data_dir, exist_ok=True)
        with open(_rows_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass


def load_rows(since_ts: float = 0.0) -> list[dict]:
    out: list[dict] = []
    try:
        with open(_rows_path(), encoding="utf-8") as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if float(r.get("ts") or 0) >= since_ts:
                    out.append(r)
    except OSError:
        return []
    return out


def _pct(v: list, q: float) -> Optional[float]:
    if not v:
        return None
    v = sorted(v)
    return round(v[min(len(v) - 1, int(q * len(v)))], 1)


def report(since_ts: float = 0.0, now: Optional[float] = None) -> dict:
    """Joined by trade id. ``matched`` fills carry both clocks; ``api_only``
    are fills the chain never showed; ``chain_only`` are fills the api never
    showed (a chain-side false positive if the api is right); ``dupes`` are
    ids one source recorded more than once."""
    rows = load_rows(since_ts)
    by: dict = {}
    dupes = 0
    for r in rows:
        k = r.get("id") or ""
        src = r.get("source") or ""
        slot = by.setdefault(k, {})
        if src in slot:
            dupes += 1
            continue
        slot[src] = r
    matched = [v for v in by.values() if "data-api" in v and "onchain" in v]
    api_only = sum(1 for v in by.values() if "data-api" in v and "onchain" not in v)
    chain_only = sum(1 for v in by.values() if "onchain" in v and "data-api" not in v)
    api_lag = [float(v["data-api"]["lag_s"]) for v in matched if v["data-api"].get("lag_s") is not None]
    chain_lag = [float(v["onchain"]["lag_s"]) for v in matched if v["onchain"].get("lag_s") is not None]
    gain = [float(v["data-api"]["seen_at"]) - float(v["onchain"]["seen_at"]) for v in matched]
    n_api = sum(1 for v in by.values() if "data-api" in v)
    first_ts = min((float(r.get("ts") or 0) for r in rows), default=0.0)
    now = time.time() if now is None else now
    return {
        "rows": len(rows), "n_api": n_api, "matched": len(matched),
        "api_only": api_only, "chain_only": chain_only, "dupes": dupes,
        "missed_frac": (api_only / n_api) if n_api else None,
        "api_lag_p50": _pct(api_lag, 0.5), "api_lag_p90": _pct(api_lag, 0.9),
        "chain_lag_p50": _pct(chain_lag, 0.5), "chain_lag_p90": _pct(chain_lag, 0.9),
        "gain_p50": _pct(gain, 0.5), "gain_median": round(statistics.median(gain), 1) if gain else None,
        "days": round((now - first_ts) / 86400.0, 2) if first_ts else 0.0,
    }


def line(since_ts: float = 0.0, now: Optional[float] = None) -> str:
    r = report(since_ts, now)
    if not r["rows"]:
        return "two clocks: no fills stamped yet"
    return (f"two clocks: {r['matched']} matched fills over {r['days']:.1f} d, "
            f"api lag p50 {r['api_lag_p50']}s, chain lag p50 {r['chain_lag_p50']}s, "
            f"chain earlier by {r['gain_p50']}s at the median; api-only {r['api_only']}, "
            f"chain-only {r['chain_only']}, duplicate ids {r['dupes']}; "
            f"{'CHAIN IS PRIMARY' if is_primary() else 'chain is a shadow'}")


def is_primary() -> bool:
    """May the chain trigger copies? Forced by ONCHAIN_SHADOW when set, else
    the persisted flip. Unreadable means shadow: the fallback that cannot
    double-copy."""
    if _FORCE in ("true", "1", "yes", "on"):
        return False
    if _FORCE in ("false", "0", "no", "off"):
        return True
    try:
        with open(_primary_path(), encoding="utf-8") as f:
            return bool(json.load(f).get("primary"))
    except (OSError, ValueError):
        return False


def cutover_ready(now: Optional[float] = None) -> tuple[bool, str, dict]:
    """The rule, with its evidence. Any missing number keeps the shadow."""
    now = time.time() if now is None else now
    r = report(0.0, now)
    if r["dupes"] > 0:
        return (False, f"{r['dupes']} duplicate id(s): the sources do not agree on one id yet", r)
    enough = r["matched"] >= SHADOW_MIN_MATCHED or r["days"] >= SHADOW_DAYS
    if not enough:
        return (False, f"{r['matched']} matched of {SHADOW_MIN_MATCHED}, {r['days']:.1f} of {SHADOW_DAYS:.0f} days", r)
    if r["matched"] < 5:
        return (False, f"only {r['matched']} matched fills: too few to judge", r)
    if r["missed_frac"] is None or r["missed_frac"] > MAX_MISSED_FRAC:
        return (False, f"chain missed {r['missed_frac']:.0%} of api fills (max {MAX_MISSED_FRAC:.0%})" if r["missed_frac"] is not None else "no api fills to compare", r)
    if r["gain_p50"] is None or r["gain_p50"] <= 0:
        return (False, f"chain is not earlier at the median ({r['gain_p50']}s)", r)
    return (True, f"{r['matched']} matched, chain earlier by {r['gain_p50']}s p50, missed {r['missed_frac']:.0%}, 0 dupes", r)


def set_primary(evidence: dict, now: Optional[float] = None) -> bool:
    now = time.time() if now is None else now
    try:
        os.makedirs(CONFIG.data_dir, exist_ok=True)
        tmp = _primary_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"primary": True, "ts": now, "evidence": evidence}, f)
        os.replace(tmp, _primary_path())
        return True
    except OSError:
        return False


def maybe_cutover(send=None, now: Optional[float] = None) -> Optional[dict]:
    """Called by the guard: flips once, says so once, never twice."""
    now = time.time() if now is None else now
    if is_primary():
        return None
    ok, why, ev = cutover_ready(now)
    if not ok:
        return None
    if not set_primary(ev, now):
        return None
    from src.copy_trading import ops_watch
    text = (f"⚡ <b>Chain detection is now primary</b>: {why}. The data api stays as the "
            f"deduplicated fallback. ONCHAIN_SHADOW=true pins the shadow back.")
    delivered = True
    if send is not None:
        try:
            r = send(text)
            delivered = r is None or bool(r)
        except Exception:
            delivered = False
    return ops_watch.receipt("onchain_primary", before="chain was a shadow", after="chain triggers copies",
                             detail=why[:160], now=now, push="BOT" if delivered else None)
