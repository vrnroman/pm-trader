"""Error fingerprints: the deterministic step before any model reads a log.

The watcher on the box (scripts/ai_sre.py) is woken by a NEW fingerprint or a
rate crossing, never by raw log volume, and it reasons over these rows, not
over prose (owner: "compute the deterministic fingerprint before the LLM
role"). A fingerprint is the important line with everything that varies
between occurrences of the same fault collapsed: hex ids, numbers, quoted
strings, wallet prefixes, block ranges. The same fault on two days is one
row with a count, first seen, last seen and, once the watcher acted on it,
the action and when.

Proof of a fix is two counters, not an opinion: hits of the fingerprint
after the action, and runs of the code path that used to produce it
(``path_runs``, bumped by the watcher from a path marker it names when it
acts). "Done" is hits 0 with runs > 0 over PROOF_WINDOW_S; hits > 0 is
"recurred"; runs 0 is "unproven", never "done". Silence is not proof.

A leaf module: no project imports beyond the config, so the logger and the
watcher can both read it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Optional

from src.config import CONFIG

TABLE_FILE = "ops-fingerprints.json"
PROOF_WINDOW_S = 24 * 3600.0
# A known fingerprint wakes the watcher again only when its rate crosses this
# many hits within RATE_WINDOW_S; below that it is the same fault, counted.
RATE_HITS = 20
RATE_WINDOW_S = 3600.0

_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\s*")
_HEX_RE = re.compile(r"0x[0-9a-fA-F]{6,}")
_ADDR_SHORT_RE = re.compile(r"\b0x[0-9a-fA-F]{2,10}(?:\.\.\.|…|\.\.)?[0-9a-fA-F]{0,6}\b")
_QUOTED_RE = re.compile(r"'[^']{0,200}'|\"[^\"]{0,200}\"")
_NUM_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?%?")
_WS_RE = re.compile(r"\s+")
_TRACE_LINE_RE = re.compile(r'File "[^"]+", line \d+')


def normalize(line: str) -> str:
    """The line with its variable parts collapsed: what two occurrences of
    one fault have in common. The log level and the component tag survive,
    the timestamp, ids, amounts and titles do not."""
    s = (line or "").strip()
    s = _TS_RE.sub("", s, count=1)
    s = _TRACE_LINE_RE.sub('File "F", line N', s)
    s = _QUOTED_RE.sub("'S'", s)
    # Placeholders carry no digits, so the number pass below cannot eat them.
    s = _HEX_RE.sub("<hex>", s)
    s = _ADDR_SHORT_RE.sub("<hex>", s)
    s = _NUM_RE.sub("N", s)
    s = _WS_RE.sub(" ", s)
    return s[:240]


def fingerprint(line: str) -> str:
    return hashlib.sha1(normalize(line).encode("utf-8")).hexdigest()[:12]


def _path() -> str:
    return os.path.join(CONFIG.data_dir, TABLE_FILE)


def read() -> dict:
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def write(d: dict) -> bool:
    try:
        os.makedirs(CONFIG.data_dir, exist_ok=True)
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, _path())
        return True
    except OSError:
        return False


def ingest(lines: list, now: Optional[float] = None) -> tuple[dict, list]:
    """Count the lines into the table. Returns ``(table, wake)`` where
    ``wake`` lists the fingerprints that should wake the watcher: new ones,
    and known ones whose hits in the last RATE_WINDOW_S crossed RATE_HITS on
    this ingest. Persisted; never raises."""
    now = time.time() if now is None else now
    d = read()
    wake: list = []
    for line in lines:
        if not (line or "").strip():
            continue
        fp = fingerprint(line)
        rec = d.get(fp)
        if rec is None:
            rec = {"first": now, "last": now, "count": 0, "sample": (line or "").strip()[:300],
                   "norm": normalize(line), "recent": [], "action": None, "action_ts": None,
                   "path_runs": 0, "path_runs_ts": None}
            d[fp] = rec
            wake.append(fp)
        rec["count"] = int(rec.get("count") or 0) + 1
        rec["last"] = now
        recent = [t for t in (rec.get("recent") or []) if now - float(t) <= RATE_WINDOW_S]
        was_under = len(recent) < RATE_HITS
        recent.append(now)
        rec["recent"] = recent[-(RATE_HITS * 2):]
        if was_under and len(recent) >= RATE_HITS and fp not in wake:
            wake.append(fp)
    write(d)
    return d, wake


def mark_action(fp: str, action: str, now: Optional[float] = None, detail: str = "") -> bool:
    """The watcher acted on this fingerprint: the proof clock starts here."""
    now = time.time() if now is None else now
    d = read()
    rec = d.get(fp)
    if rec is None:
        return False
    rec["action"] = action
    rec["action_ts"] = now
    rec["action_detail"] = (detail or "")[:200]
    rec["path_runs"] = 0
    rec["path_runs_ts"] = None
    return write(d)


def bump_path_runs(fp: str, n: int = 1, now: Optional[float] = None) -> bool:
    """The code path that used to produce this fingerprint ran again."""
    now = time.time() if now is None else now
    d = read()
    rec = d.get(fp)
    if rec is None:
        return False
    rec["path_runs"] = int(rec.get("path_runs") or 0) + int(n)
    rec["path_runs_ts"] = now
    return write(d)


def proof(fp: str, now: Optional[float] = None) -> tuple[str, str]:
    """One of ``done`` / ``recurred`` / ``unproven`` / ``open`` (no action
    yet), with the two counters spelled out."""
    now = time.time() if now is None else now
    rec = read().get(fp)
    if rec is None:
        return ("unknown", "no such fingerprint")
    ats = rec.get("action_ts")
    if not ats:
        return ("open", f"{int(rec.get('count') or 0)} hits, no action yet")
    hits_after = sum(1 for t in (rec.get("recent") or []) if float(t) > float(ats))
    if float(rec.get("last") or 0) > float(ats) and hits_after == 0:
        hits_after = 1
    runs = int(rec.get("path_runs") or 0)
    age = now - float(ats)
    if hits_after > 0:
        return ("recurred", f"{hits_after} hit(s) since the {rec.get('action')} {age / 3600:.1f} h ago")
    if runs <= 0:
        return ("unproven", f"0 hits but the path ran 0 times in {age / 3600:.1f} h; silence is not proof")
    if age < PROOF_WINDOW_S:
        return ("unproven", f"0 hits over {runs} run(s) in {age / 3600:.1f} h; {PROOF_WINDOW_S / 3600:.0f} h needed")
    return ("done", f"0 hits over {runs} run(s) in {age / 3600:.1f} h")


def rows(now: Optional[float] = None, limit: int = 40) -> list[str]:
    """The table as plain lines, most recent first, for the digest and the
    watcher's prompt."""
    now = time.time() if now is None else now
    d = read()
    out = []
    for fp, r in sorted(d.items(), key=lambda kv: -float(kv[1].get("last") or 0))[:limit]:
        state, why = proof(fp, now)
        out.append(f"{fp} x{int(r.get('count') or 0)} last {(now - float(r.get('last') or now)) / 3600:.1f}h ago"
                   f" [{state}: {why}] :: {str(r.get('norm') or '')[:120]}")
    return out
