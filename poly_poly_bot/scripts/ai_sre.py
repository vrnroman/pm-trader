"""The AI SRE on the box: a Claude process next to the bot that monitors,
thinks, acts, and writes down what it did.

Owner (2026-09-22): "AI SRE to be triggered by errors in logs and acting on
those errors: fixing, redeploying, switching to paper-only mode if needed";
"I want to know that you have claude process on remote VM and that process
actually monitors, thinks how to improve, acts." This is that process. It
runs in its own container from the same image (deploy.sh, `poly-poly-sre`),
so a fix it pushes restarts the bot, never itself, and it holds no trading
key: it structurally cannot sign an order.

How it works, one cycle every SRE_TICK_S:

1. Read the new important lines (the deterministic split the owner ruled
   on: `ops_grammar.is_important`), fingerprint them
   (`ops_fingerprint.ingest`). A NEW fingerprint or a rate crossing is a
   wake; volume alone never is.
2. On a wake, ask Claude ONCE (`claude -p`, the subscription the wallet gate
   already uses) with the fingerprint rows, the tail of important lines,
   the money state, the arm, the form table and the two-clocks line. It
   answers a JSON verdict: kind in {nothing, note, escalate, disarm, fix}.
3. Act inside the envelope, never outside it:
   - nothing / note: a thought-ledger row.
   - escalate: one Telegram line (the bot's own token), a receipt.
   - disarm: `live_mode.disarm(by="ai-sre", reason)`, the bot's own path
     (it reads live_arm.json every pass), a receipt, a Telegram line. Never
     the reverse: the SRE never arms.
   - fix: apply the unified diff to a fresh clone at the deployed commit,
     run the FULL suite, and, if the diff touches no money-path file, push
     to main (the Deploy workflow's test gate is the second check and the
     deploy restarts the bot). A money-path diff is pushed to a branch
     `sre/<fingerprint>` and escalated with its compare link; the owner
     merges from the phone. Rate limits: SRE_MAX_PUSHES_PER_DAY,
     SRE_MAX_WAKES_PER_HOUR, SRE_MAX_USD_PER_DIAGNOSIS on the envelope's own
     cost figure.
4. Proof: the fingerprint's action clock starts; a recurrence within
   PROOF_WINDOW_S of the SRE's OWN push reverts that push (git revert,
   pushed) and says so. Silence is not proof: "done" needs the path to have
   run again.
5. Every wake writes one row to data/ops-thoughts.jsonl (woke_because,
   looked_at, concluded, did, proof, cost) that the hourly digest carries
   to the ops-digest branch and the 08:00 UTC line summarises.

Never: touch the signer key or any secret, place or resize an order, arm,
change set Z, raise a budget, edit its own trigger or prompt or a test to
make it pass, add a dependency. Those are code-enforced below (the
money-path list, the forbidden-path list, the arm direction), not asked of
the model.

Idempotent by construction: state (last log offsets, wake counts, pushes,
last verdict id) lives in data/ops-sre-state.json; a second cycle over the
same lines wakes nothing and pushes nothing.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Callable, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.config import CONFIG  # noqa: E402
from src.copy_trading import ops_fingerprint as fpm  # noqa: E402
from src.copy_trading.ops_grammar import is_important  # noqa: E402
from src.logger import logger  # noqa: E402

STATE_FILE = "ops-sre-state.json"
THOUGHTS_FILE = "ops-thoughts.jsonl"
REPO_SSH = os.environ.get("SRE_REPO_SSH", "git@github.com:vrnroman/pm-trader.git")
REPO_HTTPS = os.environ.get("SRE_REPO_HTTPS", "https://github.com/vrnroman/pm-trader")
DEPLOY_KEY = os.environ.get("SRE_DEPLOY_KEY_PATH", "/run/sre_deploy_key")
MODEL = os.environ.get("SRE_MODEL", "claude-opus-4-8")


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


TICK_S = _env_f("SRE_TICK_S", 120.0)
# Off by default (manager ruling s-qbzbrw, round 2): a standing process
# pushing to main is a self-graded deploy check on a live-money box with no
# branch protection behind it. Every fix goes to a branch sre/<fingerprint>
# with the compare link on the phone; the owner flips SRE_PUSH_MAIN=true in
# the secret to let money-path-free fixes land on main by themselves.
PUSH_MAIN = str(os.environ.get("SRE_PUSH_MAIN", "false")).strip().lower() in ("1", "true", "yes", "on")
MAX_WAKES_PER_HOUR = int(_env_f("SRE_MAX_WAKES_PER_HOUR", 4))
MAX_PUSHES_PER_DAY = int(_env_f("SRE_MAX_PUSHES_PER_DAY", 3))
MAX_USD_PER_DIAGNOSIS = _env_f("SRE_MAX_USD_PER_DIAGNOSIS", 10.0)
CLAUDE_TIMEOUT_S = int(_env_f("SRE_CLAUDE_TIMEOUT_S", 600))
TAIL_LINES = int(_env_f("SRE_TAIL_LINES", 160))

# Files whose change means real money behaves differently. A diff touching
# any of these never goes to main on the SRE's word: it goes to a branch and
# to the owner. The list is code, not prompt.
MONEY_PATH = (
    "poly_poly_bot/src/copy_trading/trade_executor.py",
    "poly_poly_bot/src/copy_trading/order_executor.py",
    "poly_poly_bot/src/copy_trading/clob_client.py",
    "poly_poly_bot/src/copy_trading/live_mode.py",
    "poly_poly_bot/src/copy_trading/live_guard.py",
    "poly_poly_bot/src/copy_trading/live_budget.py",
    "poly_poly_bot/src/copy_trading/daily_spend_guard.py",
    "poly_poly_bot/src/copy_trading/tiered_risk.py",
    "poly_poly_bot/src/copy_trading/zset.py",
    "poly_poly_bot/src/copy_trading/zset_candidates.py",
    "poly_poly_bot/src/copy_trading/ops_admit.py",
    "poly_poly_bot/src/copy_trading/redeemer.py",
    "poly_poly_bot/src/copy_trading/canary.py",
    "poly_poly_bot/src/copy_trading/promotion_gate.py",
    "poly_poly_bot/src/copy_trading/wallet_form.py",
    "poly_poly_bot/src/copy_trading/two_clocks.py",
    "poly_poly_bot/src/copy_trading/live_limits.py",
    "poly_poly_bot/src/config.py",
    "poly_poly_bot/src/constants.py",
    ".github/workflows/deploy.yml",
    "poly_poly_bot/deploy.sh",
    "poly_poly_bot/Dockerfile",
    "poly_poly_bot/requirements.txt",
)
# Files the SRE may never touch at all: its own trigger, its own prompt, the
# tests that would grade it, and the pipeline that runs it.
FORBIDDEN_PATH = (
    "poly_poly_bot/scripts/ai_sre.py",
    "poly_poly_bot/scripts/ai_analyst.py",
    "poly_poly_bot/src/copy_trading/ops_grammar.py",
    "poly_poly_bot/src/copy_trading/ops_fingerprint.py",
    "poly_poly_bot/tests/",
    ".github/",
    "CLAUDE.md",
)


# --------------------------------------------------------------------------- #
# State and the thought ledger
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
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except OSError as exc:
        logger.error(f"[sre] state write failed: {exc}")
        return False


def thought(row: dict, now: Optional[float] = None) -> dict:
    """One row per wake, the record the owner reads: why it woke, what it
    looked at, what it concluded, what it did, how it will know."""
    now = time.time() if now is None else now
    row = {"ts": now, "day": time.strftime("%Y-%m-%d", time.gmtime(now)), **row}
    try:
        os.makedirs(CONFIG.data_dir, exist_ok=True)
        with open(_p(THOUGHTS_FILE), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.error(f"[sre] thought append failed: {exc}")
    logger.info(f"[sre] {row.get('did') or row.get('concluded') or 'thought'}: {str(row.get('woke_because') or '')[:100]}")
    return row


def thoughts(since_ts: float = 0.0) -> list[dict]:
    out: list[dict] = []
    try:
        with open(_p(THOUGHTS_FILE), encoding="utf-8") as f:
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


# --------------------------------------------------------------------------- #
# Reading the box
# --------------------------------------------------------------------------- #

def new_lines(state: dict, logs_dir: str) -> tuple[list[str], list[str]]:
    """``(important, raw)`` lines appended since the last cycle, across
    today's and yesterday's files. The important subset feeds the
    fingerprints; the raw lines carry the path markers a fix names as its
    proof (ordinary INFO output by design). Byte offsets per file live in the
    state so a restart of this process never re-reads (and never re-wakes
    on) old lines."""
    offsets = dict(state.get("offsets") or {})
    out: list[str] = []
    raw: list[str] = []
    files = sorted(glob.glob(os.path.join(logs_dir, "important-*.log")))[-2:]
    if not files:
        files = sorted(glob.glob(os.path.join(logs_dir, "signals-*.log")))[-2:]
    for path in files:
        try:
            size = os.path.getsize(path)
            start = int(offsets.get(path) or 0)
            if start > size:  # rotated or truncated
                start = 0
            if start == size:
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                f.seek(start)
                chunk = f.read()
                offsets[path] = f.tell()
        except OSError:
            continue
        for ln in chunk.splitlines():
            if not ln.strip():
                continue
            raw.append(ln.rstrip())
            if is_important(ln):
                out.append(ln.rstrip())
    state["offsets"] = {k: v for k, v in offsets.items() if k in files}
    return out, raw


def box_snapshot(now: float) -> dict:
    """What the model gets to look at besides the fingerprints."""
    from src.copy_trading import live_guard, live_mode, ops_watch
    # The bot's own readers for the bot's own files (the CI invariant test
    # refuses a direct path to any ledger or the arm record from this file).
    try:
        guard_state = live_guard._read_state()
    except Exception:  # noqa: BLE001
        guard_state = {}
    snap = {
        "money": _read_json(_p(ops_watch.MONEY_STATE_FILE)),
        "arm": live_mode.read_arm(),
        "guard": guard_state,
        "form": [],
        "two_clocks": "",
        "receipts_tail": [],
        "deployed_sha": "",
    }
    try:
        from src.copy_trading import wallet_form
        snap["form"] = wallet_form.lines()[:20]
    except Exception as exc:  # noqa: BLE001
        snap["form"] = [f"(form unavailable: {exc})"]
    try:
        from src.copy_trading import two_clocks
        snap["two_clocks"] = two_clocks.line(since_ts=now - 86400, now=now)
    except Exception as exc:  # noqa: BLE001
        snap["two_clocks"] = f"(two clocks unavailable: {exc})"
    try:
        snap["receipts_tail"] = [json.dumps(r, ensure_ascii=False)[:200]
                                 for r in ops_watch.ledger_rows(since_ts=now - 6 * 3600)[-30:]]
    except Exception:  # noqa: BLE001
        pass
    try:
        # The host's ~/app/logs is mounted at the bot logs dir in both containers.
        logs_dir = os.environ.get("SRE_BOT_LOGS_DIR") or "/app/logs"
        with open(os.path.join(logs_dir, "hygiene.log"), encoding="utf-8") as f:
            for ln in f:
                if " build-manifest " in ln:
                    m = re.search(r"sha=(\w+)", ln)
                    if m:
                        snap["deployed_sha"] = m.group(1)
    except OSError:
        pass
    return snap


# --------------------------------------------------------------------------- #
# The model call
# --------------------------------------------------------------------------- #

PROMPT = """You are the AI SRE of poly_poly_bot, a live real-money Polymarket copy-trading
bot. You woke because a new error fingerprint appeared in its important log
lines (or a known one crossed a rate). Diagnose from the evidence below and
answer with ONE JSON object, nothing else.

You may act only inside this envelope (the code enforces it, so do not ask
for more):
- "nothing": the fault is benign or already handled; say why in one line.
- "note": worth a line in the ledger for the owner, no action.
- "escalate": the owner must know now; "message" is one plain line for his
  phone, no em-dashes, no hedging, the number that matters first.
- "disarm": real money must stop until a human looks: the bot goes back to
  paper (its own disarm path); "reason" is one line. Use it when the fault
  can place, size or double an order wrongly, or the box cannot verify what
  it did. Never arm.
- "fix": a code change you are confident in. "diff" is a unified diff
  against the repository at the deployed commit, paths relative to the repo
  root (poly_poly_bot/src/..., poly_poly_bot/main.py). Small and surgical.
  Every fix must keep the full test suite green; you may add a test file
  under poly_poly_bot/tests/ ONLY as a new file that pins the fix, never
  edit existing tests. Name "path_marker": a literal substring of a log line
  that proves the fixed code path ran again (the proof of the fix is that
  marker appearing while the fingerprint does not).
  A diff touching the money path (executor, order placement, sizing, arm,
  guard, budget, set Z, redeemer, config, deploy files) will NOT be pushed to
  main by you; it goes to a branch and to the owner. Name "risk_change": one
  plain line on what the fix changes for real money (what trades, when, how
  much, what stops), or exactly "none" when nothing about money behaviour
  changes. A fix whose risk_change is not "none" also goes to a branch, with
  that line on the owner's phone, so he can read the change in risk before
  merging. Prefer diagnosis over a speculative diff: an "escalate" with the
  right sentence beats a wrong fix.

Rules: no em-dashes or en-dashes in anything you write; plain sentences; the
first sentence of "reasoning" states the cause.

Answer shape:
{"kind": "nothing|note|escalate|disarm|fix", "fingerprint": "<id>",
 "reasoning": "<2-6 sentences>", "message": "<one line for the phone or empty>",
 "reason": "<disarm reason or empty>", "diff": "<unified diff or empty>",
 "path_marker": "<substring or empty>", "risk_change": "none|<one line>",
 "confidence": 0.0-1.0}

# Fingerprints that woke you (id, count, last seen, proof state, normalised line)
{wake_rows}

# All recent fingerprints
{all_rows}

# Last important lines (newest last)
{tail}

# Box state
money: {money}
arm: {arm}
guard: {guard}
deployed sha: {sha}
form:
{form}
{two_clocks}
receipts (6h):
{receipts}
"""


def build_prompt(wake: list, table: dict, tail: list, snap: dict, now: float) -> str:
    def row(fp):
        r = table.get(fp) or {}
        st, why = fpm.proof(fp, now)
        return f"{fp} x{int(r.get('count') or 0)} last {(now - float(r.get('last') or now)) / 60:.0f} min ago [{st}: {why}] :: {str(r.get('norm') or '')[:200]}\n    sample: {str(r.get('sample') or '')[:240]}"
    # Token replacement, not str.format: the template carries JSON braces.
    fields = {
        "wake_rows": "\n".join(row(fp) for fp in wake) or "(none)",
        "all_rows": "\n".join(fpm.rows(now, limit=25)) or "(none)",
        "tail": "\n".join(tail[-TAIL_LINES:]) or "(none)",
        "money": json.dumps(snap.get("money") or {}, ensure_ascii=False)[:600],
        "arm": json.dumps(snap.get("arm") or {}, ensure_ascii=False)[:300],
        "guard": json.dumps(snap.get("guard") or {}, ensure_ascii=False)[:300],
        "sha": snap.get("deployed_sha") or "unknown",
        "form": "\n".join(snap.get("form") or [])[:2400],
        "two_clocks": snap.get("two_clocks") or "",
        "receipts": "\n".join(snap.get("receipts_tail") or [])[:3000],
    }
    out = PROMPT
    for k, v in fields.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _claude_runner(prompt: str, *, model: str = MODEL, timeout_s: int = CLAUDE_TIMEOUT_S) -> Optional[dict]:
    """One `claude -p` call in a throwaway cwd (no project context), the
    envelope dict or None. The same shape the wallet gate uses."""
    exe = shutil.which("claude")
    if not exe:
        logger.warning("[sre] `claude` CLI not found on PATH")
        return None
    cmd = [exe, "-p", prompt, "--output-format", "json", "--model", model]
    try:
        with tempfile.TemporaryDirectory(prefix="ai-sre-") as cwd:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s,
                                  cwd=cwd, env=os.environ.copy())
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning(f"[sre] claude -p failed to run: {exc!r}")
        return None
    if proc.returncode != 0:
        logger.warning(f"[sre] claude -p exit {proc.returncode}: {(proc.stderr or '')[:300]} | {(proc.stdout or '')[:300]}")
        return None
    try:
        env = json.loads(proc.stdout)
    except ValueError:
        logger.warning(f"[sre] claude -p non-JSON stdout: {(proc.stdout or '')[:200]}")
        return None
    if env.get("is_error") or env.get("subtype") not in (None, "success"):
        logger.warning(f"[sre] claude -p error envelope: {env.get('subtype')}")
        return None
    return env


_JSON_RE = re.compile(r"\{.*\}", re.S)


def parse_verdict(envelope: Optional[dict]) -> Optional[dict]:
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
    if not isinstance(v, dict) or v.get("kind") not in ("nothing", "note", "escalate", "disarm", "fix"):
        return None
    for k in ("reasoning", "message", "reason", "diff", "path_marker", "fingerprint", "risk_change"):
        v[k] = str(v.get(k) or "")
    try:
        v["confidence"] = float(v.get("confidence") or 0.0)
    except (TypeError, ValueError):
        v["confidence"] = 0.0
    v["cost_usd"] = float(envelope.get("total_cost_usd") or 0.0)
    return v


# --------------------------------------------------------------------------- #
# The envelope, enforced in code
# --------------------------------------------------------------------------- #

def diff_paths(diff: str) -> list[str]:
    paths = []
    for ln in (diff or "").splitlines():
        if ln.startswith("+++ ") or ln.startswith("--- "):
            p = ln[4:].strip()
            if p == "/dev/null":
                continue
            if p.startswith("a/") or p.startswith("b/"):
                p = p[2:]
            paths.append(p)
    return sorted(set(paths))


def classify_diff(diff: str) -> tuple[str, list[str]]:
    """``("forbidden"|"money"|"safe", paths)``. Forbidden wins over money."""
    paths = diff_paths(diff)
    if not paths:
        return ("forbidden", paths)
    for p in paths:
        if any(p == f or p.startswith(f) for f in FORBIDDEN_PATH):
            # a NEW test file that pins the fix is the one allowed test change
            if p.startswith("poly_poly_bot/tests/") and _is_new_file(diff, p):
                continue
            return ("forbidden", paths)
    if any(p in MONEY_PATH for p in paths):
        return ("money", paths)
    return ("safe", paths)


def _is_new_file(diff: str, path: str) -> bool:
    lines = (diff or "").splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("+++ ") and ln[4:].strip().lstrip("ab/") == path:
            prev = lines[i - 1] if i else ""
            return prev.startswith("--- /dev/null")
    return False


def _sanitize(text: str) -> str:
    return (text or "").replace("—", ",").replace("–", "-")


# --------------------------------------------------------------------------- #
# Git: clone, apply, test, push
# --------------------------------------------------------------------------- #

def _git_env() -> dict:
    env = os.environ.copy()
    if os.path.exists(DEPLOY_KEY):
        env["GIT_SSH_COMMAND"] = f"ssh -i {DEPLOY_KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
    env.setdefault("GIT_AUTHOR_NAME", "ai-sre")
    env.setdefault("GIT_AUTHOR_EMAIL", "ai-sre@poly-poly-bot")
    env.setdefault("GIT_COMMITTER_NAME", "ai-sre")
    env.setdefault("GIT_COMMITTER_EMAIL", "ai-sre@poly-poly-bot")
    return env


def _run(cmd: list, cwd: str, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=_git_env())


def can_push() -> bool:
    return os.path.exists(DEPLOY_KEY) and shutil.which("git") is not None


def apply_fix(diff: str, *, fp: str, message: str, work_root: str = "/app/sre") -> tuple[bool, str, str]:
    """Clone main, apply, run the FULL suite, commit. Returns
    ``(ok, sha_or_empty, detail)``. Nothing is pushed here."""
    if not can_push():
        return (False, "", "no push path (deploy key or git missing)")
    os.makedirs(work_root, exist_ok=True)
    wd = tempfile.mkdtemp(prefix=f"fix-{fp}-", dir=work_root)
    try:
        r = _run(["git", "clone", "--depth", "50", "--branch", "main", REPO_SSH, wd], cwd=work_root, timeout=300)
        if r.returncode != 0:
            return (False, "", f"clone failed: {(r.stderr or '')[-300:]}")
        with open(os.path.join(wd, "sre.patch"), "w", encoding="utf-8") as f:
            f.write(diff if diff.endswith("\n") else diff + "\n")
        r = _run(["git", "apply", "--check", "sre.patch"], cwd=wd)
        if r.returncode != 0:
            return (False, "", f"patch does not apply: {(r.stderr or '')[-300:]}")
        _run(["git", "apply", "sre.patch"], cwd=wd)
        os.remove(os.path.join(wd, "sre.patch"))
        py = sys.executable
        r = _run([py, "-m", "pytest", "tests/", "-q", "-x", "-p", "no:cacheprovider"],
                 cwd=os.path.join(wd, "poly_poly_bot"), timeout=1500)
        tail = (r.stdout or "").strip().splitlines()[-1:] or [""]
        if r.returncode != 0:
            return (False, "", f"suite red: {tail[0][:200]}")
        m = re.search(r"(\d+) passed", tail[0])
        count = m.group(1) if m else "?"
        _run(["git", "add", "-A"], cwd=wd)
        msg = f"{_sanitize(message)[:72]}\n\nPushed by the AI SRE on the box (fingerprint {fp}). {count} passed.\n"
        r = _run(["git", "commit", "-q", "-m", msg], cwd=wd)
        if r.returncode != 0:
            return (False, "", f"commit failed: {(r.stderr or '')[-200:]}")
        sha = _run(["git", "rev-parse", "--short", "HEAD"], cwd=wd).stdout.strip()
        return (True, sha, f"{count} passed at {sha} in {wd}")
    except subprocess.TimeoutExpired as exc:
        return (False, "", f"timed out: {exc}")
    finally:
        pass  # the clone is kept for the push step; pruned by prune_work()


def push_work(fp: str, *, branch: Optional[str], work_root: str = "/app/sre") -> tuple[bool, str]:
    """Push the newest clone for this fingerprint to main, or to ``branch``."""
    dirs = sorted(glob.glob(os.path.join(work_root, f"fix-{fp}-*")), key=os.path.getmtime)
    if not dirs:
        return (False, "no work dir")
    wd = dirs[-1]
    target = f"HEAD:refs/heads/{branch}" if branch else "HEAD:main"
    r = _run(["git", "push", "-q", "origin", target], cwd=wd, timeout=300)
    if r.returncode != 0:
        return (False, f"push failed: {(r.stderr or '')[-300:]}")
    return (True, branch or "main")


def revert_push(sha: str, *, fp: str, work_root: str = "/app/sre") -> tuple[bool, str]:
    """The SRE's own push recurred: revert it on main."""
    if not can_push():
        return (False, "no push path")
    wd = tempfile.mkdtemp(prefix=f"revert-{fp}-", dir=work_root)
    r = _run(["git", "clone", "--depth", "50", "--branch", "main", REPO_SSH, wd], cwd=work_root, timeout=300)
    if r.returncode != 0:
        return (False, f"clone failed: {(r.stderr or '')[-200:]}")
    r = _run(["git", "revert", "--no-edit", sha], cwd=wd)
    if r.returncode != 0:
        return (False, f"revert failed: {(r.stderr or '')[-200:]}")
    r = _run(["git", "push", "-q", "origin", "HEAD:main"], cwd=wd, timeout=300)
    if r.returncode != 0:
        return (False, f"push failed: {(r.stderr or '')[-200:]}")
    return (True, _run(["git", "rev-parse", "--short", "HEAD"], cwd=wd).stdout.strip())


def prune_work(work_root: str = "/app/sre", keep: int = 4) -> None:
    dirs = sorted(glob.glob(os.path.join(work_root, "*-*")), key=os.path.getmtime)
    for d in dirs[:-keep]:
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Acting
# --------------------------------------------------------------------------- #

def _send(text: str) -> bool:
    try:
        from src import telegram_bot
        r = telegram_bot.send_message(_sanitize(text), kind=telegram_bot.KIND_BOT)
        return r is None or bool(r)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[sre] telegram send failed: {exc}")
        return False


def _receipt(kind: str, **kw) -> None:
    try:
        from src.copy_trading import ops_watch
        ops_watch.receipt(kind, **kw)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[sre] receipt failed: {exc}")


def act(verdict: dict, wake: list, state: dict, now: float, *, send: Callable[[str], bool] = _send,
        apply=apply_fix, push=push_work) -> dict:
    """Apply one verdict inside the envelope. Returns the thought row."""
    kind = verdict["kind"]
    fp = verdict.get("fingerprint") or (wake[0] if wake else "")
    row = {"woke_because": ", ".join(wake)[:200], "fingerprint": fp, "kind": kind,
           "looked_at": "fingerprints, important tail, money/arm/guard, form, two clocks, receipts",
           "concluded": _sanitize(verdict.get("reasoning", ""))[:600],
           "confidence": verdict.get("confidence", 0.0), "cost_usd": verdict.get("cost_usd", 0.0),
           "did": "", "proof": "", "question": ""}
    if kind in ("nothing", "note"):
        row["did"] = "nothing" if kind == "nothing" else "noted"
        return row
    if kind == "escalate":
        msg = _sanitize(verdict.get("message") or verdict.get("reasoning") or "")[:900]
        delivered = send(f"\U0001f6a8 <b>AI SRE</b> ({fp}): {msg}")
        _receipt("sre_escalate", before=f"fingerprint {fp}", after="owner told" if delivered else "NOT delivered",
                 detail=msg[:160], now=now, push="BOT" if delivered else None, extra={"fingerprint": fp})
        row["did"] = "escalated" if delivered else "escalation NOT delivered"
        return row
    if kind == "disarm":
        from src.copy_trading import live_mode
        reason = _sanitize(verdict.get("reason") or verdict.get("reasoning") or "ai-sre")[:180]
        # The lever is the arm FILE, the bot's own record: clear it whenever
        # it is set, whatever the second interlock key says this second.
        was = live_mode.read_arm().get("armed") is True
        ok = live_mode.disarm(by="ai-sre", reason=reason) if was else True
        fpm.mark_action(fp, "disarm", now=now, detail=reason)
        text = (f"⏸ <b>AI SRE disarmed real money</b> ({fp}): {reason}. Back to paper until you /live CONFIRM."
                if was else f"⏸ <b>AI SRE</b> ({fp}): {reason}. Real money was already off.")
        delivered = send(text)
        _receipt("sre_disarm", before="armed" if was else "already off", after="disarmed" if ok else "disarm FAILED",
                 detail=reason[:160], now=now, push="DEAL" if delivered else None, extra={"fingerprint": fp})
        row["did"] = "disarmed" if (was and ok) else ("disarm failed" if was else "nothing to disarm")
        return row
    # kind == "fix"
    diff = verdict.get("diff") or ""
    cls, paths = classify_diff(diff)
    if cls == "forbidden":
        row["did"] = f"fix refused: touches a forbidden path {paths[:3]}" if paths else "fix refused: empty diff"
        _receipt("sre_fix_refused", before=f"fingerprint {fp}", after="refused", detail=row["did"][:160], now=now)
        return row
    pushes_today = [t for t in (state.get("pushes") or []) if now - float(t) < 86400]
    if len(pushes_today) >= MAX_PUSHES_PER_DAY:
        row["did"] = f"fix held: {MAX_PUSHES_PER_DAY} pushes already today"
        _receipt("sre_fix_held", before=f"fingerprint {fp}", after="held", detail=row["did"], now=now)
        return row
    ok, sha, detail = apply(diff, fp=fp, message=verdict.get("message") or f"fix({fp}): {verdict.get('reasoning', '')[:60]}")
    if not ok:
        row["did"] = f"fix not applied: {detail}"
        _receipt("sre_fix_failed", before=f"fingerprint {fp}", after="not applied", detail=detail[:160], now=now)
        return row
    # Owner ruling 2026-09-24: fixes go to main directly unless the fix
    # changes the risk profile; then a branch, and the change in risk on his
    # phone. The money-path list is the code's reading of "risk profile"; the
    # model's own risk_change line is the second, and either one is enough.
    risk = _sanitize(verdict.get("risk_change") or "").strip()
    risky = bool(risk) and risk.lower() != "none"
    branch = None if (cls == "safe" and PUSH_MAIN and not risky) else f"sre/{fp}"
    pushed, where = push(fp, branch=branch)
    if not pushed:
        row["did"] = f"fix tested ({detail}) but push failed: {where}"
        _receipt("sre_fix_failed", before=f"fingerprint {fp}", after="push failed", detail=where[:160], now=now)
        return row
    state.setdefault("pushes", []).append(now)
    state.setdefault("own_pushes", {})[fp] = {"sha": sha, "ts": now, "where": where}
    fpm.mark_action(fp, "fix", now=now, detail=f"{sha} -> {where}")
    if branch:
        link = f"{REPO_HTTPS}/compare/main...{branch}?expand=1"
        why_branch = ("on the money path" if cls == "money" else ("it changes the risk profile" if risky else "SRE_PUSH_MAIN is off"))
        msg = (f"\U0001f527 <b>AI SRE</b> ({fp}) has a fix, {why_branch}, not pushed to main: "
               f"{sha} on {branch} ({detail}). Risk change: {risk if risky else 'none stated'}. "
               f"Open and merge it here: {link}")
        delivered = send(msg)
        row["did"] = f"fix pushed to {branch} ({sha}); owner asked to merge"
        _receipt("sre_fix_branch", before=f"fingerprint {fp}", after=f"{branch} {sha}", detail=detail[:160],
                 now=now, push="BOT" if delivered else None, extra={"fingerprint": fp, "sha": sha})
    else:
        msg = f"\U0001f527 <b>AI SRE pushed a fix</b> ({fp}): {sha} to main, deploying. {_sanitize(verdict.get('reasoning', ''))[:300]}"
        delivered = send(msg)
        row["did"] = f"fix pushed to main ({sha}), deploy in flight"
        _receipt("sre_fix_pushed", before=f"fingerprint {fp}", after=f"main {sha}", detail=detail[:160],
                 now=now, push="BOT" if delivered else None, extra={"fingerprint": fp, "sha": sha})
    marker = verdict.get("path_marker") or ""
    if marker:
        state.setdefault("markers", {})[fp] = marker
    row["proof"] = f"fingerprint must stay at 0 while '{marker[:40]}' appears; recurrence within 24h reverts {sha}" if marker else f"recurrence within 24h reverts {sha}"
    return row


def check_proofs(new_lines: list, state: dict, now: float, *, send: Callable[[str], bool] = _send,
                 revert=revert_push) -> list[dict]:
    """Bump path runs from markers; revert an own push whose fingerprint
    recurred within the proof window; say so."""
    out: list[dict] = []
    markers = state.get("markers") or {}
    for fp, marker in list(markers.items()):
        n = sum(1 for ln in new_lines if marker in ln)
        if n:
            fpm.bump_path_runs(fp, n, now=now)
    own = state.get("own_pushes") or {}
    for fp, rec in list(own.items()):
        st, why = fpm.proof(fp, now)
        if st == "recurred" and rec.get("where") == "main" and not rec.get("reverted"):
            ok, detail = revert(rec["sha"], fp=fp)
            rec["reverted"] = True
            rec["revert"] = detail
            msg = (f"↩ <b>AI SRE reverted its own fix</b> ({fp}): {rec['sha']} recurred ({why}); "
                   f"{'revert ' + detail + ' pushed' if ok else 'revert FAILED: ' + detail}")
            delivered = send(msg)
            _receipt("sre_revert", before=f"{rec['sha']} on main", after=("reverted " + detail) if ok else "revert failed",
                     detail=why[:160], now=now, push="BOT" if delivered else None, extra={"fingerprint": fp})
            out.append(thought({"woke_because": f"own fix {rec['sha']} recurred", "fingerprint": fp, "kind": "revert",
                                "concluded": why, "did": f"reverted {rec['sha']}" if ok else f"revert failed: {detail}",
                                "proof": "", "cost_usd": 0.0}, now))
        elif st == "done" and not rec.get("proven"):
            rec["proven"] = True
            _receipt("sre_fix_proven", before=f"{rec['sha']}", after="done", detail=why[:160], now=now, extra={"fingerprint": fp})
    return out


# --------------------------------------------------------------------------- #
# One cycle, and the loop
# --------------------------------------------------------------------------- #

def cycle(now: Optional[float] = None, *, logs_dir: Optional[str] = None, runner=_claude_runner,
          send: Callable[[str], bool] = _send, apply=apply_fix, push=push_work, revert=revert_push) -> dict:
    """One tick. Returns a small summary dict for tests and the log."""
    now = time.time() if now is None else now
    # The BOT's logs (mounted read-only), never LOGS_DIR: that is where this
    # process writes its own lines (/app/sre/logs); the first sidecar start
    # died in a restart loop opening the bot's signals file for writing.
    logs_dir = logs_dir or os.environ.get("SRE_BOT_LOGS_DIR") or "/app/logs"
    state = _read_json(_p(STATE_FILE))
    lines, raw = new_lines(state, logs_dir)
    table, wake = fpm.ingest(lines, now=now) if lines else (fpm.read(), [])
    reverts = check_proofs(raw, state, now, send=send, revert=revert)
    summary = {"lines": len(lines), "wake": list(wake), "acted": None, "reverts": len(reverts), "held": ""}
    wakes_hour = [t for t in (state.get("wakes") or []) if now - float(t) < 3600]
    if wake and len(wakes_hour) >= MAX_WAKES_PER_HOUR:
        summary["held"] = f"{len(wake)} wake(s) held: {MAX_WAKES_PER_HOUR} already this hour"
        thought({"woke_because": ", ".join(wake)[:200], "kind": "held", "concluded": summary["held"],
                 "did": "nothing (rate)", "cost_usd": 0.0}, now)
    elif wake:
        state.setdefault("wakes", []).append(now)
        state["wakes"] = [t for t in state["wakes"] if now - float(t) < 86400]
        snap = box_snapshot(now)
        prompt = build_prompt(wake, table, lines, snap, now)
        verdict = parse_verdict(runner(prompt))
        if verdict is None:
            row = thought({"woke_because": ", ".join(wake)[:200], "kind": "no-verdict",
                           "concluded": "the model gave no usable verdict", "did": "nothing", "cost_usd": 0.0}, now)
            _receipt("sre_no_verdict", before=", ".join(wake)[:60], after="no verdict", now=now)
        elif verdict.get("cost_usd", 0.0) > MAX_USD_PER_DIAGNOSIS:
            row = thought({"woke_because": ", ".join(wake)[:200], "kind": "over-budget",
                           "concluded": f"diagnosis cost ${verdict['cost_usd']:.2f} > ${MAX_USD_PER_DIAGNOSIS:.0f}",
                           "did": "nothing", "cost_usd": verdict["cost_usd"]}, now)
        else:
            row = thought(act(verdict, wake, state, now, send=send, apply=apply, push=push), now)
        summary["acted"] = row.get("did")
    _write_json(_p(STATE_FILE), state)
    return summary


def second_line(now: Optional[float] = None) -> str:
    """The line under the 08:00 UTC real-money line: one implementation, in
    ops_watch, read by the bot; the sidecar only writes the ledger."""
    from src.copy_trading import ops_watch
    return ops_watch.watcher_line(now)


def main() -> int:
    logger.info(f"[sre] AI SRE started: tick {TICK_S:.0f}s, model {MODEL}, push path {'ready' if can_push() else 'ABSENT'}, "
                f"fixes to {'main when off the money path' if PUSH_MAIN else 'branches only (SRE_PUSH_MAIN off)'}, "
                f"limits {MAX_WAKES_PER_HOUR}/h wakes, {MAX_PUSHES_PER_DAY}/day pushes, ${MAX_USD_PER_DIAGNOSIS:.0f}/diagnosis")
    if not can_push():
        _receipt("sre_started", before="sidecar", after="no push path", detail="deploy key or git missing; fixes will be escalated only")
    else:
        _receipt("sre_started", before="sidecar", after="watching", detail=f"tick {TICK_S:.0f}s")
    analyst = None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("ai_analyst", os.path.join(ROOT, "scripts", "ai_analyst.py"))
        analyst = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(analyst)
        logger.info(f"[sre] analyst {'ENABLED' if analyst.enabled() else 'off (ANALYST_ENABLED=false)'}: "
                    f"daily at {analyst.HOUR_UTC:02d}:00 UTC, at most {analyst.MAX_PROPOSALS} proposal(s), ${analyst.MAX_USD:.0f} a study")
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[sre] analyst not loaded: {exc!r}")
    while True:
        try:
            s = cycle()
            if s["wake"] or s["reverts"] or s["held"]:
                logger.info(f"[sre] cycle: {s}")
            prune_work()
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[sre] cycle failed: {exc!r}")
        if analyst is not None:
            try:
                r = analyst.maybe_run()
                if r is not None:
                    logger.info(f"[sre] analyst ran: {r}")
            except Exception as exc:  # noqa: BLE001
                logger.error(f"[sre] analyst failed: {exc!r}")
        time.sleep(TICK_S)


if __name__ == "__main__":
    raise SystemExit(main())
