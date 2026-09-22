"""The AI analyst: once a day, on the box, it studies how the bot behaved and
proposes improvements with a price on them.

Owner (2026-09-22): "AI analytic, that thinks how bot can behave better and
improves bot (commits to github and also can adjust live parameters and
redeploy)". Manager (s-qbzbrw): the analyst never holds money authority; it
may move only the parameters in ``live_limits.TABLE``, inside their bands,
for a day, and every code proposal carries a priced counterfactual computed
from the bot's own fills. Code goes to a branch and to the owner's phone,
never to main on the analyst's word.

What it reads: the day's SKIPPED rows (why the bot declined a fill, per
reason and per wallet) joined to the paper book at their price (what the
declined copies would have made), the live fills and settlements, the form
table, the two-clocks line, the watcher's ledger, the limits in force, the
fingerprint table. It asks Claude for at most ANALYST_MAX_PROPOSALS
proposals, each one of:

- ``limit``: {name, value, why}: applied through ``live_limits.propose``
  (band, direction and expiry enforced in code), announced on Telegram
  with the counterfactual line, receipted.
- ``pr``: {title, diff, counterfactual, why}: applied to a fresh clone,
  the FULL suite, pushed to ``analyst/<day>-<slug>``, announced with the
  compare link; the owner merges from the phone.
- ``note``: a ledger row, nothing else.

It runs at most once a day (ANALYST_HOUR_UTC), spends at most
ANALYST_MAX_USD a run, and is OFF unless ANALYST_ENABLED=true (the manager
sequenced it after the SRE ledger shows one clean day). Every run writes a
row to the same thought ledger the SRE writes (kind "analyst"), so the
08:00 line and the digest show it.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Callable, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.config import CONFIG  # noqa: E402
from src.copy_trading import live_limits  # noqa: E402
from src.logger import logger  # noqa: E402

STATE_FILE = "ops-analyst-state.json"
MODEL = os.environ.get("ANALYST_MODEL", "claude-opus-4-8")


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def enabled() -> bool:
    return str(os.environ.get("ANALYST_ENABLED", "false")).strip().lower() in ("1", "true", "yes", "on")


HOUR_UTC = int(_env_f("ANALYST_HOUR_UTC", 6))
MAX_PROPOSALS = int(_env_f("ANALYST_MAX_PROPOSALS", 2))
MAX_USD = _env_f("ANALYST_MAX_USD", 10.0)
LOOKBACK_S = _env_f("ANALYST_LOOKBACK_S", 7 * 86400.0)
CLAUDE_TIMEOUT_S = int(_env_f("ANALYST_CLAUDE_TIMEOUT_S", 900))


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
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def _sanitize(text: str) -> str:
    return (text or "").replace("—", ",").replace("–", "-")


# --------------------------------------------------------------------------- #
# The priced counterfactual: what the declined copies would have made
# --------------------------------------------------------------------------- #

def _history_rows(since_ts: float) -> list[dict]:
    path = os.path.join(CONFIG.data_dir, "trade-history.jsonl")
    out: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                ts = float(r.get("received_at_ms") or 0) / 1000.0
                if ts >= since_ts:
                    out.append(r)
    except OSError:
        return []
    return out


def _paper_b_by_key() -> dict:
    """Settled book-B rows keyed by (target, token_id): at-their-price ROI
    per fill is what a declined copy would have returned."""
    try:
        from src.copy_trading.copy_paper import PaperCopyLedger
        rows = list(PaperCopyLedger(CONFIG.copy_paper_b_ledger).positions.values())
    except Exception:  # noqa: BLE001
        return {}
    by: dict = {}
    for p in rows:
        if not getattr(p, "closed", False):
            continue
        spent = float(getattr(p, "spent", 0) or 0)
        if spent <= 0:
            continue
        key = ((getattr(p, "target", "") or "").lower(), str(getattr(p, "token_id", "") or ""))
        by[key] = float(getattr(p, "ideal_pnl", 0) or 0) / spent
    return by


def counterfactual(since_ts: float, stake_usd: float) -> dict:
    """Declined fills by reason, priced at their-price ROI from book B when
    the same (wallet, token) settled there; unpriced ones are counted, never
    guessed. Raw counts and sums, no opinion."""
    from src.copy_trading.ops_fingerprint import normalize
    rows = [r for r in _history_rows(since_ts) if r.get("status") == "SKIPPED" and str(r.get("side") or "").upper() == "BUY"]
    book = _paper_b_by_key()
    by_reason: dict = {}
    for r in rows:
        # The same normaliser the fingerprints use: one reason, one row.
        reason = normalize(str(r.get("reason") or ""))[:60]
        slot = by_reason.setdefault(reason, {"declined": 0, "priced": 0, "pnl_usd": 0.0, "won": 0})
        slot["declined"] += 1
        key = ((r.get("trader_address") or "").lower(), str(r.get("token_id") or ""))
        roi = book.get(key)
        if roi is None:
            continue
        slot["priced"] += 1
        slot["pnl_usd"] += roi * stake_usd
        if roi > 0:
            slot["won"] += 1
    placed = [r for r in _history_rows(since_ts) if r.get("status") in ("PLACED", "FILLED")]
    return {"declined_total": len(rows), "placed_total": len(placed), "stake_usd": stake_usd,
            "by_reason": {k: {**v, "pnl_usd": round(v["pnl_usd"], 2)} for k, v in by_reason.items()}}


def counterfactual_lines(cf: dict) -> list[str]:
    out = [f"declined BUY signals: {cf['declined_total']}, placed: {cf['placed_total']}, stake per copy ${cf['stake_usd']:.2f}"]
    for reason, v in sorted(cf["by_reason"].items(), key=lambda kv: -kv[1]["declined"]):
        if v["priced"]:
            out.append(f"  {reason}: {v['declined']} declined, {v['priced']} priced at their price: "
                       f"{v['won']} would have won, {v['pnl_usd']:+.2f} USD at ${cf['stake_usd']:.2f} each")
        else:
            out.append(f"  {reason}: {v['declined']} declined, none settled in book B yet (unpriced)")
    return out


# --------------------------------------------------------------------------- #
# The prompt and the model
# --------------------------------------------------------------------------- #

PROMPT = """You are the AI analyst of poly_poly_bot, a live real-money Polymarket copy-trading
bot. Once a day you study how it behaved and propose at most {max_proposals}
improvements. Answer with ONE JSON object, nothing else.

Every proposal must be one of:
- "limit": move one live parameter for 24 hours. Allowed names and bands (the
  code enforces them; money parameters move DOWN only):
{limits_table}
  {"kind": "limit", "name": "<NAME>", "value": <number>, "why": "<one line>",
   "counterfactual": "<the number from the evidence that argues for it>"}
- "pr": a code change as a unified diff against the repository at the deployed
  commit (paths relative to the repo root: poly_poly_bot/src/..., poly_poly_bot/main.py).
  It goes to a branch and to the owner, never to main. It must keep the full
  test suite green; you may add a NEW test file under poly_poly_bot/tests/,
  never edit existing tests, never touch .github/, CLAUDE.md, scripts/ai_*.py,
  ops_grammar.py, ops_fingerprint.py.
  {"kind": "pr", "title": "<conventional title>", "diff": "<unified diff>",
   "why": "<2-4 sentences>", "counterfactual": "<what it would have been worth, from the evidence>"}
- "note": {"kind": "note", "why": "<one line worth the owner's minute>"}

Rules: only what the evidence supports; the first sentence of each "why" is
the number; no em-dashes or en-dashes; never propose raising exposure (budget,
floor, set Z, stakes or caps above the owner's value): that is his alone.

Answer shape: {"proposals": [ ... ], "summary": "<one line for the phone>"}

# Declined copies, priced at their price from the paper book (last {days:.0f} days)
{counterfactual}

# Limits in force
{limits}

# Form (each followed wallet on its own money)
{form}

# Two clocks
{two_clocks}

# Watcher ledger (last {days:.0f} days)
{watcher}

# Fingerprints
{fingerprints}

# Receipts (last {days:.0f} days, tail)
{receipts}

# Money state
{money}
"""


def build_prompt(now: float, cf: dict) -> str:
    from src.copy_trading import ops_watch, ops_fingerprint, two_clocks, wallet_form
    days = LOOKBACK_S / 86400.0
    try:
        form = "\n".join(wallet_form.lines()[:20])
    except Exception as exc:  # noqa: BLE001
        form = f"(form unavailable: {exc})"
    try:
        clocks = two_clocks.line(since_ts=now - LOOKBACK_S, now=now)
    except Exception as exc:  # noqa: BLE001
        clocks = f"(two clocks unavailable: {exc})"
    watcher = "\n".join(json.dumps({k: r.get(k) for k in ("day", "kind", "woke_because", "concluded", "did")
                                    if r.get(k)}, ensure_ascii=False)[:300]
                        for r in ops_watch.watcher_thoughts(since_ts=now - LOOKBACK_S)[-30:])
    receipts = "\n".join(json.dumps(r, ensure_ascii=False)[:200] for r in ops_watch.ledger_rows(since_ts=now - LOOKBACK_S)[-60:])
    fields = {
        "max_proposals": str(MAX_PROPOSALS),
        "limits_table": "\n".join(f"  {n}: band {s['band'][0]}..{s['band'][1]} ({s['kind']})" for n, s in live_limits.TABLE.items()),
        "days": f"{days:.0f}",
        "counterfactual": "\n".join(counterfactual_lines(cf)),
        "limits": "\n".join(live_limits.lines(now)),
        "form": form,
        "two_clocks": clocks,
        "watcher": watcher or "(none)",
        "fingerprints": "\n".join(ops_fingerprint.rows(now, limit=20)) or "(none)",
        "receipts": receipts or "(none)",
        "money": json.dumps(_read_json(_p(ops_watch.MONEY_STATE_FILE)), ensure_ascii=False)[:600],
    }
    out = PROMPT
    for k, v in fields.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _runner(prompt: str) -> Optional[dict]:
    """Reuse the SRE's claude -p runner: one shape, one auth."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ai_sre", os.path.join(ROOT, "scripts", "ai_sre.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._claude_runner(prompt, model=MODEL, timeout_s=CLAUDE_TIMEOUT_S)


_JSON_RE = re.compile(r"\{.*\}", re.S)


def parse(envelope: Optional[dict]) -> Optional[dict]:
    if not envelope:
        return None
    text = envelope.get("result") if isinstance(envelope.get("result"), str) else json.dumps(envelope.get("result"))
    m = _JSON_RE.search(text or "")
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(v, dict) or not isinstance(v.get("proposals"), list):
        return None
    props = []
    for p in v["proposals"][:MAX_PROPOSALS]:
        if isinstance(p, dict) and p.get("kind") in ("limit", "pr", "note"):
            props.append({**p, "why": _sanitize(str(p.get("why") or "")), "counterfactual": _sanitize(str(p.get("counterfactual") or ""))})
    return {"proposals": props, "summary": _sanitize(str(v.get("summary") or ""))[:300],
            "cost_usd": float(envelope.get("total_cost_usd") or 0.0)}


# --------------------------------------------------------------------------- #
# Acting
# --------------------------------------------------------------------------- #

def act(verdict: dict, now: float, *, send: Callable[[str], bool], apply, push, sre) -> list[dict]:
    """Each proposal inside its envelope. Returns the ledger rows written."""
    from src.copy_trading import ops_watch
    rows: list[dict] = []
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    for p in verdict["proposals"]:
        kind = p["kind"]
        row = {"kind": "analyst", "proposal": kind, "woke_because": "daily study", "concluded": p.get("why", "")[:400],
               "counterfactual": p.get("counterfactual", "")[:300], "did": "", "cost_usd": 0.0}
        if kind == "note":
            row["did"] = "noted"
        elif kind == "limit":
            ok, why = live_limits.propose(str(p.get("name") or ""), p.get("value"), why=p.get("why", ""), now=now)
            row["did"] = ("limit applied: " if ok else "limit refused: ") + why
            if ok:
                delivered = send(f"\U0001f9ee <b>AI analyst</b> moved a limit for a day: {why}. Why: {p.get('why', '')[:200]} "
                                 f"Evidence: {p.get('counterfactual', '')[:200]}")
                ops_watch.receipt("analyst_limit", before=str(p.get("name")), after=why[:120], detail=p.get("why", "")[:160],
                                  now=now, push="BOT" if delivered else None)
            else:
                ops_watch.receipt("analyst_limit_refused", before=str(p.get("name")), after="refused", detail=why[:160], now=now)
        elif kind == "pr":
            diff = str(p.get("diff") or "")
            cls, paths = sre.classify_diff(diff)
            if cls == "forbidden" or not paths:
                row["did"] = f"pr refused: forbidden or empty diff {paths[:3]}"
                ops_watch.receipt("analyst_pr_refused", before="pr", after="refused", detail=row["did"][:160], now=now)
            else:
                slug = re.sub(r"[^a-z0-9]+", "-", str(p.get("title") or "change").lower()).strip("-")[:40] or "change"
                branch = f"analyst/{day}-{slug}"
                fp = f"analyst-{day}-{slug}"
                ok, sha, detail = apply(diff, fp=fp, message=f"{p.get('title', 'analyst: change')}\n\n{p.get('why', '')}\n\nCounterfactual: {p.get('counterfactual', '')}")
                if not ok:
                    row["did"] = f"pr not applied: {detail}"
                    ops_watch.receipt("analyst_pr_failed", before=branch, after="not applied", detail=detail[:160], now=now)
                else:
                    pushed, where = push(fp, branch=branch)
                    if not pushed:
                        row["did"] = f"pr tested ({detail}) but push failed: {where}"
                        ops_watch.receipt("analyst_pr_failed", before=branch, after="push failed", detail=where[:160], now=now)
                    else:
                        link = f"{sre.REPO_HTTPS}/compare/main...{branch}?expand=1"
                        delivered = send(f"\U0001f4dd <b>AI analyst</b> has a change for you: {p.get('title', '')[:120]} ({sha}, {detail}). "
                                         f"Worth: {p.get('counterfactual', '')[:200]}. Open and merge it here: {link}")
                        row["did"] = f"pr pushed to {branch} ({sha}); owner asked to merge"
                        ops_watch.receipt("analyst_pr", before=branch, after=sha, detail=p.get("title", "")[:160],
                                          now=now, push="BOT" if delivered else None)
        rows.append(sre.thought(row, now))
    return rows


def maybe_run(now: Optional[float] = None, *, runner=_runner, send=None, apply=None, push=None, force: bool = False) -> Optional[dict]:
    """Once a day at HOUR_UTC when enabled. Returns a summary or None."""
    now = time.time() if now is None else now
    if not enabled() and not force:
        return None
    st = _read_json(_p(STATE_FILE))
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    hour = int(time.strftime("%H", time.gmtime(now)))
    if st.get("last_day") == day and not force:
        return None
    if hour < HOUR_UTC and not force:
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("ai_sre", os.path.join(ROOT, "scripts", "ai_sre.py"))
    sre = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sre)
    send = send or sre._send
    apply = apply or sre.apply_fix
    push = push or sre.push_work
    st["last_day"] = day
    _write_json(_p(STATE_FILE), st)   # stamped first: a crash below never re-runs the day
    try:
        from src.copy_trading import live_budget
        caps = live_budget.caps(live=True)
        stake = float(getattr(caps, "per_copy_usd", 0.0) or 0.0) if caps is not None else 0.0
    except Exception:  # noqa: BLE001
        stake = 0.0
    cf = counterfactual(now - LOOKBACK_S, stake or 6.4)
    prompt = build_prompt(now, cf)
    verdict = parse(runner(prompt))
    if verdict is None:
        sre.thought({"kind": "analyst", "woke_because": "daily study", "concluded": "no usable answer", "did": "nothing", "cost_usd": 0.0}, now)
        return {"proposals": 0, "acted": [], "cost_usd": 0.0}
    if verdict["cost_usd"] > MAX_USD:
        sre.thought({"kind": "analyst", "woke_because": "daily study", "concluded": f"study cost ${verdict['cost_usd']:.2f} > ${MAX_USD:.0f}",
                     "did": "nothing", "cost_usd": verdict["cost_usd"]}, now)
        return {"proposals": 0, "acted": [], "cost_usd": verdict["cost_usd"]}
    rows = act(verdict, now, send=send, apply=apply, push=push, sre=sre)
    if rows:
        rows[-1]["cost_usd"] = verdict["cost_usd"]
    sre.thought({"kind": "analyst", "woke_because": "daily study", "concluded": verdict["summary"] or "studied the week",
                 "did": f"{len(rows)} proposal(s): " + "; ".join(r.get("did", "")[:60] for r in rows), "cost_usd": verdict["cost_usd"]}, now)
    return {"proposals": len(rows), "acted": [r.get("did") for r in rows], "cost_usd": verdict["cost_usd"]}
