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

- ``study`` (s-ye5990): a what-if over the box's own data from a fixed
  menu (``scripts/exp_study.py``), frozen as a who-stays/enters/leaves
  table, read back by the model once for a conclusion and, if it earns
  one, an experiment card.
- ``experiment`` (s-ye5990): a card (hypothesis, knobs or a diff behind an
  ``exp_flag``, win/kill bars in numbers, max days). A control that IS book
  B and a treatment run side by side in a fenced child process
  (``scripts/exp_book.py``); every day CODE applies the card's bars
  (``exp_cards.check``); on WIN a branch ``analyst/exp-<id>`` for the owner
  to merge, on KILL or VOID a backlog row and one phone line. One
  experiment at a time; the rest queue.

Owner (2026-09-24): "analyst should change code for experiments (but paper
run), write experiment somewhere, then every day ... see how experiment is
going, adjust if needed, then after some time conclude experiment results
and reject idea or offer me PR ... budget should go up to 150 for run."

It runs at most once a day (ANALYST_HOUR_UTC), spends at most
ANALYST_MAX_USD a day and ANALYST_MAX_USD_PER_CALL a call, and is OFF
unless ANALYST_ENABLED=true. Every run writes a row to the same thought
ledger the SRE writes (kind "analyst"), so the 08:00 line and the digest
show it. ``supervise`` runs every SRE tick and keeps the live
experiment's process up.
"""
from __future__ import annotations

import html
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from typing import Callable, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.config import CONFIG  # noqa: E402
from src.copy_trading import exp_cards, live_limits  # noqa: E402
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
MAX_USD = _env_f("ANALYST_MAX_USD", 150.0)            # the day (owner: 150 for the experimenting analyst)
MAX_USD_PER_CALL = _env_f("ANALYST_MAX_USD_PER_CALL", 60.0)
LOOKBACK_S = _env_f("ANALYST_LOOKBACK_S", 7 * 86400.0)
CLAUDE_TIMEOUT_S = int(_env_f("ANALYST_CLAUDE_TIMEOUT_S", 900))
WORK_ROOT = os.environ.get("SRE_WORK_ROOT", "/app/sre")   # experiment clones live at <WORK_ROOT>/exp/<id>
EXP_LOGS_DIR = os.environ.get("LOGS_DIR", "/app/sre/logs")
SPAWN_MIN_GAP_S = _env_f("EXP_SPAWN_MIN_GAP_S", 600.0)
MAX_SPAWNS_PER_DAY = int(_env_f("EXP_MAX_SPAWNS_PER_DAY", 5))
HEARTBEAT_STALE_S = _env_f("EXP_HEARTBEAT_STALE_S", 900.0)
# Same image, no new dependencies, no deploy change, and never the harness
# itself: an experiment is code and knobs, never the box or the fence. (The
# SRE's MONEY_PATH is allowed here: the child process is the fence, and the
# class is printed on the WIN message.)
EXP_FORBIDDEN = ("poly_poly_bot/deploy.sh", "poly_poly_bot/Dockerfile", "poly_poly_bot/requirements.txt",
                 "poly_poly_bot/scripts/exp_book.py", "poly_poly_bot/scripts/exp_study.py",
                 "poly_poly_bot/src/copy_trading/exp_flag.py", "poly_poly_bot/src/copy_trading/exp_cards.py",
                 "poly_poly_bot/src/copy_trading/book_recipes.py", "poly_poly_bot/src/copy_trading/copy_paper_runner.py",
                 "poly_poly_bot/src/copy_trading/live_mode.py", "poly_poly_bot/src/copy_trading/zset.py",
                 "poly_poly_bot/src/config.py")
# Words an experiment's diff may not contain: the child shares the sidecar's
# uid and mounts, so the fence is the environment plus this screen plus the
# harness check, not a kernel boundary (code review, s-ye5990). A real
# boundary is a third container with the data dir read-only: the owner's.
EXP_FORBIDDEN_WORDS = ("live_arm", "promoted_wallets", "sre_deploy_key", "subprocess", "os.system", "os.exec",
                       "PRIVATE_KEY", "OAUTH_TOKEN", "git push", "shutil.rmtree")
PROPOSAL_KINDS = ("limit", "pr", "note", "study", "experiment")


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
- "study": a what-if over the box's own data, computed by code and frozen as a
  who-stays / who-enters / who-leaves table you will read back once. Menu:
{study_menu}
  {"kind": "study", "study": "<menu name>", "params": {...}, "question": "<the question, one line>"}
- "experiment": a paper experiment. A control that IS book B and a treatment
  (book B plus your change) run side by side on the same fills for max_days; the
  code applies your bars every day (WIN, KILL, VOID, or one 7-day EXTEND when
  starved) and you cannot move them afterwards. Knobs you may change:
  {knobs}. A code change is a unified diff (same path rules as "pr", plus
  never deploy.sh, Dockerfile, requirements.txt) whose new behaviour is read
  through exp_flag.on("<flag>") from src/copy_trading/exp_flag.py, so the
  control runs with it off and the treatment with it on. On WIN the owner gets
  a branch to merge; nothing reaches real trades without his merge.
  {"kind": "experiment", "id": "<2..32 chars of a-z 0-9 ->", "title": "<title>",
   "hypothesis": "<what you expect and why, from the evidence>", "knobs": {"<knob>": <value>},
   "diff": "<optional unified diff>", "flag": "<required with a diff>",
   "win_bar": {"roi_pp": <at least 2.0: treatment minus control, net ROI at their price, percentage points>, "min_n": <at least {min_n} settled treatment copies>},
   "kill_bar": {"roi_pp": <0 or below>, "min_n": <at least 10>}, "max_days": <3..30>,
   "parent_id": "<optional: the experiment this follows>", "study_ref": "<optional: the study that argued for it>"}
- "note": {"kind": "note", "why": "<one line worth the owner's minute>"}

Rules: only what the evidence supports; the first sentence of each "why" is
the number; no em-dashes or en-dashes; never propose raising exposure (budget,
floor, set Z, stakes or caps above the owner's value): that is his alone. At
most ONE study or ONE experiment a day; one experiment runs at a time, a second
queues behind it. Prefer a study before an experiment when the data on the box
can answer the question. Ideas that were killed stay in the backlog: a new card
that follows one names it in parent_id and says what it changes.

Answer shape: {"proposals": [ ... ], "summary": "<one line for the phone>"}

# Experiment in flight
{experiment}

# Experiments so far (backlog, newest last)
{backlog}

# Studies on file
{studies}

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

STUDY_PROMPT = """You are the AI analyst of poly_poly_bot. Earlier today you asked for the study
below; the code ran it and froze the table. Read it and answer with ONE JSON
object, nothing else:

{"conclusion": "<two sentences at most: the number first, then what it means for the bot>",
 "card": <null, or an experiment card exactly as in the daily rules, with "study_ref": "{study_id}">,
 "wanted": "<optional: one follow-up question this menu cannot compute>",
 "why_not": "<with wanted: what is missing to compute it>"}

A card is worth writing only when the table argues for a change the paper books
can test; its bars are numbers (win_bar.roi_pp at least 2.0, win_bar.min_n at
least {min_n}, kill_bar.roi_pp at or below 0, max_days 3..30). Knobs you may
change: {knobs}. No em-dashes or en-dashes. Never propose raising exposure.

# The study
{table}
"""


def _exp_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("exp_study", os.path.join(ROOT, "scripts", "exp_study.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def experiment_lines(now: float) -> list[str]:
    live = exp_cards.live_card()
    if live is None:
        q = exp_cards.next_queued()
        return [f"(none live; queued: {q['id']}: {q['title']})" if q else "(none)"]
    return exp_cards.table(live)


def backlog_lines(limit: int = 12) -> list[str]:
    rows = exp_cards.backlog_rows()[-limit:]
    if not rows:
        return ["(empty)"]
    return [f"{r.get('day')} {r.get('id')}: {r.get('event')}" + (f" ({r.get('why')})" if r.get("why") else "")
            + (f" [follows {r.get('parent_id')}]" if r.get("parent_id") else "") for r in rows]


def study_lines(limit: int = 8) -> list[str]:
    st = exp_cards.studies(limit=limit)
    if not st:
        return ["(none)"]
    return [f"{d.get('id')}: {d.get('question') or d.get('kind')}: {d.get('totals_line')}" for d in st]


def build_prompt(now: float, cf: dict) -> str:
    from src.copy_trading import ops_watch, ops_fingerprint, two_clocks, wallet_form, book_recipes
    from src.copy_trading.promotion_gate import FALSIFY_MIN_N
    days = LOOKBACK_S / 86400.0
    try:
        form = "\n".join(wallet_form.lines()[:20])
    except Exception as exc:  # noqa: BLE001
        form = f"(form unavailable: {exc})"
    try:
        clocks = two_clocks.line(since_ts=now - LOOKBACK_S, now=now)
    except Exception as exc:  # noqa: BLE001
        clocks = f"(two clocks unavailable: {exc})"
    try:
        menu = "\n".join(_exp_module().menu_lines())
    except Exception as exc:  # noqa: BLE001
        menu = f"  (menu unavailable: {exc})"
    watcher = "\n".join(json.dumps({k: r.get(k) for k in ("day", "kind", "woke_because", "concluded", "did")
                                    if r.get(k)}, ensure_ascii=False)[:300]
                        for r in ops_watch.watcher_thoughts(since_ts=now - LOOKBACK_S)[-30:])
    receipts = "\n".join(json.dumps(r, ensure_ascii=False)[:200] for r in ops_watch.ledger_rows(since_ts=now - LOOKBACK_S)[-60:])
    fields = {
        "max_proposals": str(MAX_PROPOSALS),
        "limits_table": "\n".join(f"  {n}: band {s['band'][0]}..{s['band'][1]} ({s['kind']})" for n, s in live_limits.TABLE.items()),
        "study_menu": menu,
        "knobs": ", ".join(f"{k} ({t.__name__})" for k, t in book_recipes.KNOBS.items()),
        "min_n": str(FALSIFY_MIN_N),
        "days": f"{days:.0f}",
        "experiment": "\n".join(experiment_lines(now)),
        "backlog": "\n".join(backlog_lines()),
        "studies": "\n".join(study_lines()),
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


def build_study_prompt(record: dict, table_md: str) -> str:
    from src.copy_trading import book_recipes
    from src.copy_trading.promotion_gate import FALSIFY_MIN_N
    out = STUDY_PROMPT
    for k, v in {"study_id": record.get("id", ""), "min_n": str(FALSIFY_MIN_N),
                 "knobs": ", ".join(f"{k} ({t.__name__})" for k, t in book_recipes.KNOBS.items()),
                 "table": table_md[:12000]}.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _sre():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ai_sre", os.path.join(ROOT, "scripts", "ai_sre.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _runner(prompt: str) -> Optional[dict]:
    """Reuse the SRE's claude -p runner: one shape, one auth."""
    return _sre()._claude_runner(prompt, model=MODEL, timeout_s=CLAUDE_TIMEOUT_S)


_JSON_RE = re.compile(r"\{.*\}", re.S)


def _json_of(envelope: Optional[dict]) -> Optional[dict]:
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
    return v if isinstance(v, dict) else None


def parse(envelope: Optional[dict]) -> Optional[dict]:
    v = _json_of(envelope)
    if v is None or not isinstance(v.get("proposals"), list):
        return None
    props = []
    seen_big = False
    for p in v["proposals"][:MAX_PROPOSALS]:
        if not isinstance(p, dict) or p.get("kind") not in PROPOSAL_KINDS:
            continue
        if p["kind"] in ("study", "experiment"):
            if seen_big:
                continue            # at most one study or experiment a day
            seen_big = True
        props.append({**p, "why": _sanitize(str(p.get("why") or "")), "counterfactual": _sanitize(str(p.get("counterfactual") or ""))})
    return {"proposals": props, "summary": _sanitize(str(v.get("summary") or ""))[:300],
            "cost_usd": float(envelope.get("total_cost_usd") or 0.0)}


def parse_conclusion(envelope: Optional[dict]) -> Optional[dict]:
    v = _json_of(envelope)
    if v is None or "conclusion" not in v:
        return None
    card = v.get("card") if isinstance(v.get("card"), dict) else None
    return {"conclusion": _sanitize(str(v.get("conclusion") or ""))[:400], "card": card,
            "wanted": _sanitize(str(v.get("wanted") or ""))[:300], "why_not": _sanitize(str(v.get("why_not") or ""))[:300],
            "cost_usd": float(envelope.get("total_cost_usd") or 0.0)}


# --------------------------------------------------------------------------- #
# Experiments: start, keep alive, check daily, conclude
# --------------------------------------------------------------------------- #

def _clone_branch(branch: str, dest: str, sre) -> tuple[bool, str]:
    """Clone one branch into ``dest`` (the experiment process's cwd)."""
    if os.path.isdir(os.path.join(dest, ".git")):
        r = sre._run(["git", "pull", "-q", "--ff-only"], cwd=dest, timeout=300)
        return (r.returncode == 0, "updated" if r.returncode == 0 else f"pull failed: {(r.stderr or '')[-200:]}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    r = sre._run(["git", "clone", "-q", "--depth", "50", "--branch", branch, sre.REPO_SSH, dest], cwd=os.path.dirname(dest), timeout=300)
    return (r.returncode == 0, "cloned" if r.returncode == 0 else f"clone failed: {(r.stderr or '')[-200:]}")


def start_experiment(card: dict, now: float, *, send, apply, push, sre, clone=None) -> dict:
    """Write the card, push its code (if any) to exp/<id>, launch it when
    nothing else is live. Returns the ledger row."""
    row = {"kind": "analyst", "proposal": "experiment", "woke_because": "daily study",
           "concluded": str(card.get("hypothesis") or "")[:400], "did": "", "cost_usd": 0.0}
    # the proposal's "kind" is "experiment"; a card's kind (live/replay) is its own key
    card = {k: v for k, v in card.items() if k != "kind"}
    if card.get("card_kind"):
        card["kind"] = card.pop("card_kind")
    diff = str(card.get("diff") or "")
    if diff:
        cls, paths = sre.classify_diff(diff)
        if cls == "forbidden" or any(p in EXP_FORBIDDEN for p in paths):
            row["did"] = f"experiment refused: forbidden path {paths[:3]}"
            return row
        added = "\n".join(ln for ln in diff.splitlines() if ln.startswith("+"))
        hit = next((w for w in EXP_FORBIDDEN_WORDS if w in added), None)
        if hit:
            row["did"] = f"experiment refused: the diff mentions {hit!r}"
            return row
    ok, why, c = exp_cards.create(card, now)
    if not ok:
        row["did"] = f"experiment refused: {why}"
        return row
    exp_id = c["id"]
    if diff:
        fp = f"exp-{exp_id}"
        branch = f"exp/{exp_id}"
        ok, sha, detail = apply(diff, fp=fp, message=f"exp({exp_id}): {c['title']}\n\n{c['hypothesis']}\n\nBehind exp_flag {c['flag']}; control off, treatment on.")
        if ok:
            ok, where = push(fp, branch=branch)
            detail = where if not ok else f"{detail}; pushed {branch}"
        if ok:
            dest = os.path.join(WORK_ROOT, "exp", exp_id)
            ok, msg = (clone or (lambda b, d: _clone_branch(b, d, sre)))(branch, dest)
            detail = f"{detail}; {msg}"
            if ok:
                exp_cards.set_branch(exp_id, branch=branch, workdir=dest, diff_class=cls)
        if not ok:
            c = exp_cards.load(exp_id) or c
            exp_cards.apply_verdict(c, {"status": "void", "why": f"code did not land: {detail}"[:300]}, now)
            row["did"] = f"experiment {exp_id} void: {detail}"[:300]
            return row
    launched, msg = exp_cards.launch(exp_id, now)
    state = "live" if launched else "queued"
    row["did"] = f"experiment {exp_id} {state}: {msg if launched else msg}"[:300]
    from src.copy_trading import ops_watch
    lines = exp_cards.table(exp_cards.load(exp_id) or c)
    delivered = send(f"\U0001f9ea <b>AI analyst</b> experiment <code>{exp_id}</code> {state}: {html.escape(c['title'])}\n"
                     f"<blockquote expandable>{html.escape(chr(10).join(lines[1:6]))}</blockquote>")
    ops_watch.receipt("analyst_experiment", before=exp_id, after=state, detail=c["title"][:160], now=now,
                      push="BOT" if delivered else None)
    return row


TELEGRAM_MAX = 4096


def _fit(text: str, budget: int) -> str:
    """Escaped text that fits ``budget`` characters after escaping (the
    escape grows "->" to "-&gt;"; a 40-wallet table came out near 4,200)."""
    out = html.escape(text)
    while len(out) > max(budget, 0) and text:
        text = text[: int(len(text) * 0.8)]
        out = html.escape(text) + "\n..."
    return out


def run_study(p: dict, now: float, *, send, study) -> dict:
    """Run one study from the menu, freeze it, put the totals on the phone.
    Returns the ledger row (with the study id when it ran)."""
    row = {"kind": "analyst", "proposal": "study", "woke_because": "daily study",
           "concluded": str(p.get("question") or "")[:300], "did": "", "cost_usd": 0.0}
    kind = str(p.get("study") or "")
    params = p.get("params") if isinstance(p.get("params"), dict) else {}
    try:
        rec, path, written = study(kind, params, now=now, question=str(p.get("question") or ""))
    except Exception as exc:  # noqa: BLE001
        row["did"] = f"study refused: {exc!s}"[:300]
        return row
    row["study_id"] = rec["id"]
    row["did"] = f"study {rec['id']} {'frozen' if written else 'already on file'}: {rec['totals_line']}"[:400]
    from src.copy_trading import ops_watch
    table = _exp_module().markdown(rec)
    head = (f"\U0001f52c <b>AI analyst</b> study <code>{rec['id']}</code>: {html.escape(str(p.get('question') or kind))}\n"
            f"{html.escape(rec['totals_line'])}\n")
    tail = f"\n{html.escape(rec['caveat'])}\n{path}"
    delivered = send(head + f"<blockquote expandable>{_fit(table, TELEGRAM_MAX - len(head) - len(tail) - 40)}</blockquote>" + tail)
    ops_watch.receipt("analyst_study", before=rec["id"], after=rec["totals_line"][:120], detail=rec["caveat"][:160], now=now,
                      push="BOT" if delivered else None)
    return row


def conclude_study(study_id: str, now: float, *, runner, send, apply, push, sre, clone=None) -> tuple[Optional[dict], float]:
    """The one read-back: the model concludes on the frozen table and may
    hand in a card. ``(ledger row, cost)``."""
    rec = next((d for d in exp_cards.studies(limit=50) if d.get("id") == study_id), None)
    if rec is None:
        return (None, 0.0)
    v = parse_conclusion(runner(build_study_prompt(rec, _exp_module().markdown(rec))))
    if v is None:
        return (sre.thought({"kind": "analyst", "proposal": "study", "woke_because": f"study {study_id}",
                             "concluded": "no usable conclusion", "did": "nothing", "cost_usd": 0.0}, now), 0.0)
    if v["cost_usd"] > MAX_USD_PER_CALL:
        return (sre.thought({"kind": "analyst", "proposal": "study", "woke_because": f"study {study_id}",
                             "concluded": f"conclusion cost ${v['cost_usd']:.2f} > ${MAX_USD_PER_CALL:.0f}", "did": "nothing",
                             "cost_usd": v["cost_usd"]}, now), v["cost_usd"])
    did = "concluded"
    if v.get("wanted"):
        # What the menu could not compute, written down plain: the menu
        # grows from real asks, not guesses.
        exp_cards.unanswered_add({"study": study_id, "wanted": v["wanted"], "why_not": v.get("why_not", "")}, now)
        did = "concluded; one question the menu cannot compute noted"
    if v["card"]:
        card = {**v["card"], "study_ref": study_id}
        r = start_experiment(card, now, send=send, apply=apply, push=push, sre=sre, clone=clone)
        did = r["did"]
    send(f"\U0001f52c <b>AI analyst</b> on study <code>{study_id}</code>: {html.escape(v['conclusion'])}")
    return (sre.thought({"kind": "analyst", "proposal": "study", "woke_because": f"study {study_id}",
                         "concluded": v["conclusion"], "did": did, "cost_usd": v["cost_usd"]}, now), v["cost_usd"])


def _record_markdown(card: dict) -> str:
    from src.copy_trading import book_recipes
    lines = [f"# experiment {card['id']}: {card['title']}", ""] + exp_cards.table(card) + [""]
    if card.get("knobs"):
        lines += ["## what this branch changes", "deploy.yml (the lines the owner's merge makes real):"]
        for k, v in deploy_lines_for({"knobs": card["knobs"]}).items():
            lines.append(f"- `ensure_env {k} {v}`" if "." not in k else f"- the primary book's floor in `COPY_PAPER_B_BOOKS` becomes {v}")
        lines.append("")
    if card.get("branch"):
        lines += ["## the code", f"Branch `{card['branch']}`, behind `exp_flag.on(\"{card.get('flag')}\")`; "
                                f"switched on at boot by `ensure_env EXP_FLAGS_ON {card.get('flag')}` in deploy.yml. "
                                f"Paths: {card.get('diff_class')} class.", ""]
    lines += ["## caveat", "Paper books at their price with modeled costs; the control is book B's recipe run next to book B "
              "(the harness column says how far it strayed). Nothing here traded real money.", ""]
    return "\n".join(lines)


def _env_value(v) -> str:
    return str(v).lower() if isinstance(v, bool) else (str(int(v)) if isinstance(v, float) and float(v).is_integer() else str(v))


def _new_file_diff(path: str, text: str) -> str:
    body = text.rstrip("\n").split("\n")     # never splitlines(): \u2028 would miscount the hunk
    out = [f"--- /dev/null", f"+++ b/{path}", f"@@ -0,0 +1,{len(body)} @@"] + ["+" + ln for ln in body]
    return "\n".join(out) + "\n"


DEPLOY_YML = ".github/workflows/deploy.yml"


def deploy_lines_for(card: dict) -> dict[str, str]:
    """The ``ensure_env`` lines a WIN needs in deploy.yml: one per knob with
    an env name, and EXP_FLAGS_ON for a code change."""
    from src.copy_trading import book_recipes
    out: dict[str, str] = {}
    for k, v in (card.get("knobs") or {}).items():
        env = book_recipes.KNOB_ENV.get(k)
        if env:
            out[env] = _env_value(v)
        if k == "min_usd":
            # Real money copies from LIVE_MIN_TRADER_BET_USD and the primary
            # paper book from its COPY_PAPER_B_BOOKS entry (PR #44), so the
            # line that brings a floor to real trades is those two, not the
            # recipe default alone (verifier round 2, s-ye5990).
            out["LIVE_MIN_TRADER_BET_USD"] = _env_value(v)
            out["COPY_PAPER_B_BOOKS.primary_floor"] = _env_value(v)
    if card.get("flag"):
        out["EXP_FLAGS_ON"] = str(card["flag"])
    return out


def edit_deploy_yml(text: str, lines: dict[str, str]) -> str:
    """``ensure_env NAME VALUE`` replaced in place, or added after the
    first ensure_env line; EXP_FLAGS_ON accumulates (comma-separated)."""
    rows = text.split("\n")
    for name, value in lines.items():
        if name == "COPY_PAPER_B_BOOKS.primary_floor":
            # the primary book's floor inside the spec: "b300:300,b150:150" -> "b300:150,b150:150"
            pat = re.compile(r"^(\s*)ensure_env COPY_PAPER_B_BOOKS (\S+)(.*)$")
            hit = next((i for i, r in enumerate(rows) if pat.match(r)), None)
            if hit is not None:
                m = pat.match(rows[hit])
                parts = m.group(2).split(",")
                pid = parts[0].split(":")[0]
                parts[0] = f"{pid}:{value}"
                rows[hit] = f"{m.group(1)}ensure_env COPY_PAPER_B_BOOKS {','.join(parts)}{m.group(3)}"
            continue
        pat = re.compile(rf"^(\s*)ensure_env {re.escape(name)} (.*)$")
        hit = next((i for i, r in enumerate(rows) if pat.match(r)), None)
        if hit is not None:
            m = pat.match(rows[hit])
            cur = m.group(2).strip()
            if name == "EXP_FLAGS_ON" and cur and value not in cur.split(","):
                value = f"{cur},{value}"
            rows[hit] = f"{m.group(1)}ensure_env {name} {value}"
            continue
        first = next((i for i, r in enumerate(rows) if re.match(r"^\s*ensure_env \S+ ", r)), None)
        indent = re.match(r"^(\s*)", rows[first]).group(1) if first is not None else "          "
        at = first if first is not None else len(rows)
        rows.insert(at, f"{indent}ensure_env {name} {value}")
    return "\n".join(rows)


def win_branch(card: dict, md: str, *, sre, work_root: Optional[str] = None) -> tuple[bool, str, str]:
    """The branch the owner merges: the record under docs/experiments/, the
    deploy.yml lines that make the change real, and, for a code card, the
    code itself (the clone of exp/<id>). ``(ok, branch, detail)``. Written
    with git directly: this is the one place a branch for the owner may
    touch .github/, and it goes nowhere without his merge."""
    exp_id = card["id"]
    branch = f"analyst/exp-{exp_id}"
    rel = f"poly_poly_bot/docs/experiments/{exp_id}.md"
    wd = card.get("workdir")
    if not (wd and os.path.isdir(os.path.join(wd, ".git"))):
        root = work_root or WORK_ROOT
        os.makedirs(root, exist_ok=True)
        wd = tempfile.mkdtemp(prefix=f"fix-exp-{exp_id}-win-", dir=root)
        r = sre._run(["git", "clone", "-q", "--depth", "50", "--branch", "main", sre.REPO_SSH, wd], cwd=root, timeout=300)
        if r.returncode != 0:
            return (False, branch, f"clone failed: {(r.stderr or '')[-200:]}")
    try:
        os.makedirs(os.path.dirname(os.path.join(wd, rel)), exist_ok=True)
        with open(os.path.join(wd, rel), "w", encoding="utf-8") as f:
            f.write(md)
        lines = deploy_lines_for(card)
        touched = [rel]
        dy = os.path.join(wd, DEPLOY_YML)
        if lines and os.path.exists(dy):
            with open(dy, encoding="utf-8") as f:
                before = f.read()
            after = edit_deploy_yml(before, lines)
            if after != before:
                with open(dy, "w", encoding="utf-8") as f:
                    f.write(after)
                touched.append(DEPLOY_YML)
        r = sre._run(["git", "add"] + touched, cwd=wd)
        if r.returncode != 0:
            return (False, branch, f"git add failed: {(r.stderr or '')[-200:]}")
        msg = (f"exp({exp_id}): won its bars; the change for the owner's merge\n\n{card['hypothesis']}\n\n"
               + ("\n".join(f"deploy.yml: ensure_env {k} {v}" for k, v in lines.items() if "." not in k) or "no deploy line"))
        r = sre._run(["git", "commit", "-q", "-m", msg], cwd=wd)
        if r.returncode != 0:
            return (False, branch, f"commit failed: {(r.stderr or '')[-200:]}")
        r = sre._run(["git", "push", "-q", "origin", f"HEAD:refs/heads/{branch}"], cwd=wd, timeout=300)
        if r.returncode != 0:
            return (False, branch, f"push failed: {(r.stderr or '')[-200:]}")
        return (True, branch, "pushed: " + ", ".join(touched))
    except OSError as exc:
        return (False, branch, f"{exc!r}")


def conclude_win(card: dict, now: float, *, send, apply=None, push=None, sre) -> str:
    """WIN: a branch analyst/exp-<id> carrying the record AND the change
    (deploy.yml lines, the code for a diff card); the compare link on the
    phone. The owner's merge is the only way into real trades."""
    exp_id = card["id"]
    ok, branch, detail = win_branch(card, _record_markdown(card), sre=sre)
    from src.copy_trading import ops_watch
    if not ok:
        ops_watch.receipt("analyst_exp_pr_failed", before=exp_id, after="not pushed", detail=detail[:160], now=now)
        send(f"\U0001f9ea <b>AI analyst</b> experiment <code>{exp_id}</code> WON its bars but the branch failed: {html.escape(detail[:200])}")
        return f"win, branch failed: {detail}"[:300]
    link = f"{sre.REPO_HTTPS}/compare/main...{branch}?expand=1"
    money = " Touches the money path." if card.get("diff_class") == "money" else ""
    lines = deploy_lines_for(card)
    change = "; ".join((f"{k}={v}" if "." not in k else f"the primary book's floor {v}") for k, v in lines.items()) or "the record only"
    rows_ = exp_cards.journal_rows(exp_id)
    v = rows_[-1] if rows_ else {}
    delivered = send(f"\U0001f4dd <b>AI analyst</b> experiment <code>{exp_id}</code> WON: {html.escape(str(v.get('why') or ''))}.{money} "
                     f"The branch sets {html.escape(change)} in deploy.yml; merge it to bring it to real trades: {link}")
    ops_watch.receipt("analyst_exp_pr", before=exp_id, after=branch, detail=(card["title"] + " | " + change)[:160], now=now, push="BOT" if delivered else None)
    return f"win: branch {branch} pushed ({change}); owner asked to merge"


def journal_live(now: float, *, send, apply, push, sre) -> Optional[dict]:
    """The daily check of the live experiment: compare, verdict by code,
    journal row; then the conclusion's consequences. Once a day."""
    live = exp_cards.live_card()
    if live is None:
        return None
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    if exp_cards.journaled_on(live["id"], day):
        return None
    row = exp_cards.check(live, now)
    card = exp_cards.load(live["id"]) or live
    st = row.get("status")
    did = f"exp {card['id']} {st}: {row.get('why', '')}"[:300]
    if st == "win":
        did = conclude_win(card, now, send=send, apply=apply, push=push, sre=sre)
    elif st in ("kill", "void"):
        send(f"\U0001f9ea <b>AI analyst</b> experiment <code>{card['id']}</code> {st.upper()}: {html.escape(str(row.get('why') or ''))}")
    elif st == "extend":
        send(f"\U0001f9ea <b>AI analyst</b> experiment <code>{card['id']}</code> extended: {html.escape(str(row.get('why') or ''))}")
    sre.thought({"kind": "analyst", "proposal": "experiment", "woke_because": f"daily check of {card['id']}",
                 "concluded": str(row.get("why") or "")[:300], "did": did, "cost_usd": 0.0}, now)
    return row


_procs: dict[int, subprocess.Popen] = {}


# What the child may see: the paper harness reads these and nothing else.
# An allowlist, so a credential the sidecar gains later never reaches the
# child by default (code review + verifier, s-ye5990).
CHILD_ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "PYTHONPATH", "PYTHONUNBUFFERED", "VIRTUAL_ENV",
                  "MALLOC_ARENA_MAX", "MALLOC_TRIM_THRESHOLD_", "DATA_API_URL", "GAMMA_API_URL", "CLOB_API_URL",
                  "PREVIEW_MODE", "BOT_LOG_RETENTION_DAYS", "LOG_LEVEL")
CHILD_ENV_PREFIXES = ("COPY_", "STRATEGY", "WALLET_DISCOVERY_", "FORM_", "EXP_", "AB_RACE_", "MAX_", "MIN_")


def _child_env(card: dict, card_dir: str) -> dict:
    env = {k: v for k, v in os.environ.items()
           if (k in CHILD_ENV_KEYS or k.startswith(CHILD_ENV_PREFIXES)) and "KEY" not in k and "TOKEN" not in k and "SECRET" not in k}
    env["DATA_DIR"] = os.path.join(card_dir, "scratch")
    env["LOGS_DIR"] = os.path.join(EXP_LOGS_DIR, "exp", card["id"])
    env["EXP_REAL_DATA_DIR"] = CONFIG.data_dir
    env["LIVE_ARM_ENABLED"] = "false"
    env["PREVIEW_MODE"] = "true"
    env["SRE_ROLE"] = "exp"
    env.pop("EXP_FLAGS_ON", None)      # the treatment's flag is turned on by the driver, never by the env
    return env


def _spawn(card: dict) -> int:
    card_dir = exp_cards.card_dir(card["id"])
    wd = card.get("workdir")
    cwd = os.path.join(wd, "poly_poly_bot") if wd and os.path.isdir(os.path.join(wd, "poly_poly_bot")) else ROOT
    os.makedirs(os.path.join(card_dir, "scratch"), exist_ok=True)
    out = open(os.path.join(card_dir, "process.log"), "a", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, os.path.join(cwd, "scripts", "exp_book.py"), "--card",
                             os.path.join(card_dir, exp_cards.CARD_FILE), "--real-data-dir", CONFIG.data_dir],
                            cwd=cwd, env=_child_env(card, card_dir), stdout=out, stderr=subprocess.STDOUT)
    _procs[proc.pid] = proc
    return proc.pid


_exited: set = set()     # pids of children WE held that exited on their own


def _alive(pid: int) -> bool:
    """Ours (a Popen we hold) by poll(); a pid from before a restart only
    when it still runs exp_book.py: after a container restart small pids
    are reused by the SRE's own git, pytest or claude children, and a
    liveness check that trusted the number alone would SIGTERM them."""
    p = _procs.get(pid)
    if p is not None:
        if p.poll() is not None:
            _procs.pop(pid, None)
            _exited.add(pid)
            return False
        return True
    if not pid:
        return False
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return b"exp_book.py" in f.read()
    except OSError:
        pass
    if os.path.isdir("/proc"):
        return False        # no such pid on a /proc system
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def crashed_hint(pid: int) -> bool:
    """A pid we did not hold (a previous supervisor's) tells nothing about
    a crash: False. Tests may monkeypatch this to say a child died."""
    return False


def _stop(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    p = _procs.pop(pid, None)
    if p is not None:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()


def run_requests(now: float, *, send, study=None, sre=None) -> list[dict]:
    """The owner's one-tap studies (request files under studies/): run
    each, the table to the phone, the request renamed. No model call, no
    cap of the model's; the day's dollar caps are untouched."""
    out = []
    for path, req in exp_cards.pending_requests():
        p = {"kind": "study", "study": req.get("kind"), "params": req.get("params") or {}, "question": req.get("question") or ""}
        ok = False
        try:
            row = run_study(p, now, send=send, study=study or _default_study)
            ok = bool(row.get("study_id"))
        except Exception as exc:  # noqa: BLE001  a request runs once, whatever happened
            row = {"kind": "analyst", "proposal": "study", "concluded": f"tapped study failed: {exc!r}"[:300], "did": "nothing", "cost_usd": 0.0}
        finally:
            exp_cards.finish_request(path, ok=ok)
        row["woke_because"] = f"owner tapped {req.get('preset')}"
        out.append(sre.thought(row, now) if sre is not None else row)
    return out


def supervise(now: Optional[float] = None, *, spawn=_spawn, alive=_alive, stop=_stop, send=None, sre=None, study=None) -> dict:
    """Every tick: the owner's tapped studies run, the live card's process
    is up, concluded cards' processes are down, the next queued card starts
    when nothing is live. A process that will not stay up
    (MAX_SPAWNS_PER_DAY) voids its card."""
    now = time.time() if now is None else now
    st = _read_json(_p(STATE_FILE))
    ex = st.setdefault("exp", {})
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    did = ""
    if not enabled():
        # Off is off: nothing starts, and a child still running from before
        # the switch is stopped; the owner's taps stay queued (the tap
        # itself says the analyst is off).
        for exp_id, rec in ex.items():
            if rec.get("pid") and alive(int(rec["pid"])):
                stop(int(rec["pid"]))
                rec["pid"] = 0
                did = f"stopped {exp_id}: analyst off"
        _write_json(_p(STATE_FILE), st)
        return {"live": None, "did": did or "off"}
    if send is not None:
        ran = run_requests(now, send=send, study=study, sre=sre)
        if ran:
            did = f"ran {len(ran)} tapped study(ies)"
    for c in exp_cards.cards():
        rec = ex.get(c["id"]) or {}
        if c.get("status") in exp_cards.CONCLUDED and rec.get("pid") and alive(int(rec["pid"])):
            stop(int(rec["pid"]))
            rec["pid"] = 0
            ex[c["id"]] = rec
            did = f"stopped {c['id']}"
    live = exp_cards.live_card()
    if live is None:
        q = exp_cards.next_queued()
        if q is not None:
            ok, msg = exp_cards.launch(q["id"], now)
            if ok:
                live = exp_cards.load(q["id"])
                did = f"launched {q['id']}"
    if live is not None:
        rec = ex.setdefault(live["id"], {"pid": 0, "spawned_ts": 0.0, "spawns": {}})
        hb = exp_cards.heartbeat(live["id"])
        up = bool(rec.get("pid")) and alive(int(rec["pid"]))
        spawned = float(rec.get("spawned_ts") or 0)
        hb_ts = float(hb.get("ts") or 0) if hb and int(hb.get("pid") or 0) == int(rec.get("pid") or -1) else 0.0
        # Stale: this process's own heartbeat is old, or it never wrote one
        # within the window (hung in its first read). A heartbeat from the
        # previous process (another pid) does not count either way.
        stale = up and (now - max(hb_ts, spawned)) > HEARTBEAT_STALE_S
        if (not up or stale) and now - float(rec.get("spawned_ts") or 0) >= SPAWN_MIN_GAP_S:
            # A start counts toward the day's five only when a child THIS
            # supervisor held died or hung: a container restart (every
            # deploy) is not the experiment crashing (verifier, s-ye5990).
            crashed = stale or (int(rec.get("pid") or 0) in _exited or crashed_hint(int(rec.get("pid") or 0)))
            n_today = int((rec.get("spawns") or {}).get(day, 0)) + (1 if crashed else 0)
            if n_today > MAX_SPAWNS_PER_DAY:
                c = exp_cards.load(live["id"]) or live
                exp_cards.apply_verdict(c, {"status": "void", "why": f"its process would not stay up ({n_today} starts today)"}, now)
                did = f"{live['id']} void: process would not stay up"
                if send:
                    send(f"\U0001f9ea <b>AI analyst</b> experiment <code>{live['id']}</code> VOID: its process would not stay up ({n_today} starts today); see {exp_cards.card_dir(live['id'])}/process.log")
            else:
                if up and stale:
                    stop(int(rec["pid"]))
                try:
                    pid = spawn(live)
                except Exception as exc:  # noqa: BLE001
                    pid = 0
                    did = f"spawn failed for {live['id']}: {exc!r}"[:200]
                rec["pid"] = int(pid or 0)
                rec["spawned_ts"] = now
                rec.setdefault("spawns", {})[day] = n_today
                if pid:
                    did = f"started {live['id']} (pid {pid}, {'restart ' + str(n_today) + ' after a crash today' if crashed else 'first start since this supervisor came up'})"
                if sre is not None and did:
                    sre.thought({"kind": "analyst", "proposal": "experiment", "woke_because": "supervise",
                                 "concluded": did, "did": did, "cost_usd": 0.0}, now)
    st["exp"] = ex
    _write_json(_p(STATE_FILE), st)
    return {"live": live["id"] if live else None, "did": did}


# --------------------------------------------------------------------------- #
# Acting
# --------------------------------------------------------------------------- #

def _default_study(kind: str, params: dict, *, now: float, question: str = ""):
    return _exp_module().run_and_freeze(kind, params, now=now, question=question)


def act(verdict: dict, now: float, *, send: Callable[[str], bool], apply, push, sre, study=None, clone=None) -> list[dict]:
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
        elif kind == "study":
            row = run_study(p, now, send=send, study=study or _default_study)
        elif kind == "experiment":
            row = start_experiment(p, now, send=send, apply=apply, push=push, sre=sre, clone=clone)
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


def spent_today(st: dict, day: str) -> float:
    try:
        return float((st.get("spent") or {}).get(day) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _spend(st: dict, day: str, usd: float) -> None:
    sp = st.setdefault("spent", {})
    sp[day] = round(spent_today(st, day) + float(usd or 0.0), 4)
    for k in list(sp):
        if k != day and len(sp) > 7:
            sp.pop(k, None)
    _write_json(_p(STATE_FILE), st)


def maybe_run(now: Optional[float] = None, *, runner=_runner, send=None, apply=None, push=None, force: bool = False,
              study=None, clone=None) -> Optional[dict]:
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
    sre = _sre()
    send = send or sre._send
    apply = apply or sre.apply_fix
    push = push or sre.push_work
    st["last_day"] = day
    _write_json(_p(STATE_FILE), st)   # stamped first: a crash below never re-runs the day
    # 1. the live experiment's daily check (code, no model, no cost)
    try:
        journal_live(now, send=send, apply=apply, push=push, sre=sre)
        exp_cards.prune(now)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[analyst] experiment check failed: {exc!r}")
    # 2. the study of the day
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
    cost = verdict["cost_usd"]
    if cost > MAX_USD_PER_CALL or spent_today(st, day) + cost > MAX_USD:
        _spend(st, day, cost)
        sre.thought({"kind": "analyst", "woke_because": "daily study",
                     "concluded": f"study cost ${cost:.2f} over the cap (${MAX_USD_PER_CALL:.0f} a call, ${MAX_USD:.0f} a day, ${spent_today(st, day):.2f} spent)",
                     "did": "nothing", "cost_usd": cost}, now)
        return {"proposals": 0, "acted": [], "cost_usd": cost}
    _spend(st, day, cost)
    rows = act(verdict, now, send=send, apply=apply, push=push, sre=sre, study=study, clone=clone)
    # 3. a study that ran is read back once, when the day's budget leaves room
    #    for a call at the per-call cap (the cost is only known afterwards)
    for r in rows:
        if r.get("study_id") and spent_today(st, day) + MAX_USD_PER_CALL <= MAX_USD:
            _row, c2 = conclude_study(r["study_id"], now, runner=runner, send=send, apply=apply, push=push, sre=sre, clone=clone)
            _spend(st, day, c2)
            cost += c2
            if _row is not None:
                rows.append(_row)
    if rows:
        rows[-1]["cost_usd"] = cost
    sre.thought({"kind": "analyst", "woke_because": "daily study", "concluded": verdict["summary"] or "studied the week",
                 "did": f"{len(rows)} proposal(s): " + "; ".join(r.get("did", "")[:60] for r in rows), "cost_usd": cost}, now)
    return {"proposals": len(rows), "acted": [r.get("did") for r in rows], "cost_usd": cost}
