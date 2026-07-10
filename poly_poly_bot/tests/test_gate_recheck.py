"""Deferred-gate re-check: rate-limit detection + provisional-admit + drain."""

from __future__ import annotations

from types import SimpleNamespace

from src.copy_trading import gate_history, gate_recheck_queue
from src.copy_trading import llm_review
from src.copy_trading.discovery import DiscoveryConfig, Eval
from src.copy_trading.discovery_runner import DiscoveryRunner
from src.copy_trading.llm_review import RATE_LIMITED, LLMVerdict

CFG = DiscoveryConfig(min_capture_cents=1.5, min_tstat=10.0,
                      drop_capture_cents=1.0, watchlist_cap=10, auto_remove=True)


# --------------------------------------------------------------------------- #
# rate-limit detection in the runner (guardrail 1: the marker strings)
# --------------------------------------------------------------------------- #

def test_looks_rate_limited_matches_real_message():
    real = "You've hit your monthly spend limit · raise it at claude.ai/settings/usage"
    assert llm_review._looks_rate_limited(real) is True
    assert llm_review._looks_rate_limited("some rate limit hit") is True
    assert llm_review._looks_rate_limited("normal output OK") is False
    assert llm_review._looks_rate_limited(None, "") is False


def test_cli_runner_returns_sentinel_on_limited_exit(monkeypatch):
    def fake_run(cmd, **kw):
        return SimpleNamespace(
            returncode=1, stdout="",
            stderr="You've hit your monthly spend limit · claude.ai/settings/usage")
    monkeypatch.setattr(llm_review.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(llm_review.subprocess, "run", fake_run)
    assert llm_review._claude_cli_runner("p", model="m", timeout_s=1) is RATE_LIMITED


def test_cli_runner_returns_sentinel_on_error_envelope(monkeypatch):
    import json
    env = {"is_error": True, "subtype": "error",
           "result": "rate limit exceeded, see claude.ai/settings/usage"}

    def fake_run(cmd, **kw):
        return SimpleNamespace(returncode=0, stdout=json.dumps(env), stderr="")
    monkeypatch.setattr(llm_review.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(llm_review.subprocess, "run", fake_run)
    assert llm_review._claude_cli_runner("p", model="m", timeout_s=1) is RATE_LIMITED


def test_cli_runner_generic_failure_is_none(monkeypatch):
    def fake_run(cmd, **kw):
        return SimpleNamespace(returncode=1, stdout="", stderr="segfault")
    monkeypatch.setattr(llm_review.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(llm_review.subprocess, "run", fake_run)
    assert llm_review._claude_cli_runner("p", model="m", timeout_s=1) is None


def test_review_wallet_passes_sentinel_through():
    v = llm_review.review_wallet({"wallet": "0xA"}, runner=lambda *a, **k: RATE_LIMITED)
    assert v is RATE_LIMITED


# --------------------------------------------------------------------------- #
# discovery integration: provisional admit + enqueue + drain
# --------------------------------------------------------------------------- #

def _ev(w, theory="1b"):
    return Eval(wallet=w, capture_cents=0.0, lead_cents=0.0, hit_rate=0.0, n=0,
                roi=0.5, tstat=12.0, flagged_by=(theory,))


def _runner(tmp_path, *, seq, review_fn):
    calls = {"i": 0}

    def fake_eval(config, **kw):
        d = seq[min(calls["i"], len(seq) - 1)]
        calls["i"] += 1
        return d

    sent = []
    r = DiscoveryRunner(
        config=CFG,
        watchlist_path=str(tmp_path / "wl.json"),
        state_path=str(tmp_path / "state.json"),
        evaluate=fake_eval, llm_review=review_fn, llm_review_enabled=True,
        now=lambda: 100.0, notify=lambda m: sent.append(m),
    )
    gate_recheck_queue.clear_cache()
    return r, sent


def test_rate_limited_wallet_is_provisionally_admitted_and_queued(tmp_path):
    seq = [{"0xk": _ev("0xk")},
           {"0xk": _ev("0xk"), "0xlim": _ev("0xlim")}]   # 0xlim is new in sweep 2

    def review(dossier, model=None):
        return RATE_LIMITED if dossier["wallet"] == "0xlim" else LLMVerdict(
            "follow", "low", True, 0.7, "ok")

    r, _ = _runner(tmp_path, seq=seq, review_fn=review)
    r.run_once()
    result = r.run_once()
    # provisionally admitted (not lost)
    assert any(e.wallet == "0xlim" for e in result.watchlist)
    # parked for re-check
    assert "0xlim" in {e["wallet"] for e in gate_recheck_queue.pending(r.gate_recheck_queue_path)}
    # logged as a deferred provisional admit
    rows = {row["wallet"]: row for row in gate_history.load(r.gate_history_path)}
    assert rows["0xlim"]["verdict"] == "skip-deferred"
    assert rows["0xlim"]["admitted"] is True and rows["0xlim"]["requeued"] is True


def test_drain_removes_when_recheck_says_skip(tmp_path):
    # 0xlim persists on the watchlist across sweeps; the review is rate-limited on
    # sweep 2, then (subscription restored) says skip on the drain in sweep 3.
    seq = [{"0xk": _ev("0xk")},
           {"0xk": _ev("0xk"), "0xlim": _ev("0xlim")},
           {"0xk": _ev("0xk"), "0xlim": _ev("0xlim")}]
    state = {"phase": 0}

    def review(dossier, model=None):
        if dossier["wallet"] != "0xlim":
            return LLMVerdict("follow", "low", True, 0.7, "ok")
        # first time (sweep-2 gate) -> rate limited; later (sweep-3 drain) -> skip
        state["phase"] += 1
        return RATE_LIMITED if state["phase"] == 1 else LLMVerdict(
            "skip", "high", False, 0.9, "artifact on re-check")

    r, sent = _runner(tmp_path, seq=seq, review_fn=review)
    r.run_once()                 # init
    r.run_once()                 # sweep 2: 0xlim rate-limited -> provisional + queued
    result = r.run_once()        # sweep 3: drain re-checks -> skip -> removed
    assert not any(e.wallet == "0xlim" for e in result.watchlist)     # removed
    assert "0xlim" not in {e["wallet"] for e in gate_recheck_queue.pending(r.gate_recheck_queue_path)}
    assert any("Deferred gate re-check" in m for m in sent)


def test_drain_keeps_when_still_rate_limited(tmp_path):
    seq = [{"0xk": _ev("0xk")},
           {"0xk": _ev("0xk"), "0xlim": _ev("0xlim")},
           {"0xk": _ev("0xk"), "0xlim": _ev("0xlim")}]

    def review(dossier, model=None):
        return RATE_LIMITED if dossier["wallet"] == "0xlim" else LLMVerdict(
            "follow", "low", True, 0.7, "ok")

    r, _ = _runner(tmp_path, seq=seq, review_fn=review)
    r.run_once(); r.run_once()
    result = r.run_once()        # still limited on the drain -> stays parked + on wl
    assert any(e.wallet == "0xlim" for e in result.watchlist)
    assert "0xlim" in {e["wallet"] for e in gate_recheck_queue.pending(r.gate_recheck_queue_path)}


def test_drain_keeps_parked_on_transient_failure(tmp_path):
    # A re-check that fails NON-rate-limited (e.g. a timeout -> None) must NOT
    # dequeue the wallet while it stays admitted — that would be fail-open-and-
    # forget. It stays parked for the next sweep.
    seq = [{"0xk": _ev("0xk")},
           {"0xk": _ev("0xk"), "0xlim": _ev("0xlim")},
           {"0xk": _ev("0xk"), "0xlim": _ev("0xlim")}]
    state = {"phase": 0}

    def review(dossier, model=None):
        if dossier["wallet"] != "0xlim":
            return LLMVerdict("follow", "low", True, 0.7, "ok")
        state["phase"] += 1
        return RATE_LIMITED if state["phase"] == 1 else None   # sweep-3 drain: None

    r, _ = _runner(tmp_path, seq=seq, review_fn=review)
    r.run_once(); r.run_once()
    result = r.run_once()        # drain re-check returns None -> keep parked
    assert any(e.wallet == "0xlim" for e in result.watchlist)     # NOT lost
    assert "0xlim" in {e["wallet"] for e in gate_recheck_queue.pending(r.gate_recheck_queue_path)}


def test_recheck_skip_ping_is_html_escaped(tmp_path):
    # Claude reasoning with HTML metacharacters must be escaped or Telegram 400s
    # and the removal alert is silently dropped.
    seq = [{"0xk": _ev("0xk")},
           {"0xk": _ev("0xk"), "0xlim": _ev("0xlim")},
           {"0xk": _ev("0xk"), "0xlim": _ev("0xlim")}]
    state = {"phase": 0}

    def review(dossier, model=None):
        if dossier["wallet"] != "0xlim":
            return LLMVerdict("follow", "low", True, 0.7, "ok")
        state["phase"] += 1
        return RATE_LIMITED if state["phase"] == 1 else LLMVerdict(
            "skip", "high", False, 0.9, "win rate < 50% & ROI > 0")

    r, sent = _runner(tmp_path, seq=seq, review_fn=review)
    r.run_once(); r.run_once(); r.run_once()
    ping = next(m for m in sent if "Deferred gate re-check" in m)
    assert "&lt;" in ping and "&gt;" in ping and "&amp;" in ping   # escaped
    assert "< 50%" not in ping                                     # not raw


def test_gate_and_drain_share_one_budget(tmp_path):
    # top_n=3: a recovery sweep that gates 2 new wallets AND has 3 parked must make
    # at most top_n LLM calls total (2 gate + 1 drain), not 2 + 3.
    par = {f"0xp{i}": _ev(f"0xp{i}") for i in range(3)}
    new = {f"0xn{i}": _ev(f"0xn{i}") for i in range(2)}
    seq = [{"0xk": _ev("0xk")},
           {"0xk": _ev("0xk"), **par},
           {"0xk": _ev("0xk"), **par, **new}]
    calls = {"n": 0}

    def review(dossier, model=None):
        calls["n"] += 1
        return RATE_LIMITED if dossier["wallet"].startswith("0xp") else LLMVerdict(
            "follow", "low", True, 0.7, "ok")

    r = DiscoveryRunner(
        config=CFG, watchlist_path=str(tmp_path / "wl.json"),
        state_path=str(tmp_path / "state.json"),
        evaluate=lambda config, **kw: seq[min(_seq_i(calls, seq), len(seq) - 1)],
        llm_review=review, llm_review_enabled=True, llm_review_top_n=3, now=lambda: 100.0)
    gate_recheck_queue.clear_cache()
    r.run_once()               # init
    r.run_once()               # sweep 2: 3 parked (gate budget spent), no drain
    calls["n"] = 0
    r.run_once()               # sweep 3: 2 new gated + shared budget 1 for the drain
    assert calls["n"] == 3     # NOT 5


def test_drain_dequeues_wallet_that_decayed_off(tmp_path):
    # 0xlim is queued, then EVALUATED as decayed -> removed -> dequeued. (A
    # sweep that simply never evaluated it CARRIES it instead — see below —
    # so the dequeue needs a real, evaluated decay, not mere absence.)
    decayed = Eval(wallet="0xlim", capture_cents=0.0, lead_cents=0.0,
                   hit_rate=0.0, n=0, roi=0.0, tstat=0.0)
    seq = [{"0xk": _ev("0xk")},
           {"0xk": _ev("0xk"), "0xlim": _ev("0xlim")},
           {"0xk": _ev("0xk"), "0xlim": decayed}]   # evaluated + decayed -> drop

    def review(dossier, model=None):
        return RATE_LIMITED if dossier["wallet"] == "0xlim" else LLMVerdict(
            "follow", "low", True, 0.7, "ok")

    r, _ = _runner(tmp_path, seq=seq, review_fn=review)
    r.run_once(); r.run_once(); r.run_once()
    assert q_empty(r)


def test_unevaluated_wallet_is_carried_and_stays_queued(tmp_path):
    # Interrupted-sweep semantics (2026-07-10): a queued wallet that was NOT
    # evaluated this sweep is carried on the watchlist and its re-check stays
    # owed — absence is not evidence of decay.
    seq = [{"0xk": _ev("0xk")},
           {"0xk": _ev("0xk"), "0xlim": _ev("0xlim")},
           {"0xk": _ev("0xk")}]                 # 0xlim not swept -> carried

    def review(dossier, model=None):
        return RATE_LIMITED if dossier["wallet"] == "0xlim" else LLMVerdict(
            "follow", "low", True, 0.7, "ok")

    r, _ = _runner(tmp_path, seq=seq, review_fn=review)
    r.run_once(); r.run_once(); r.run_once()
    assert not q_empty(r)
    import json
    wl = {t["wallet"] for t in json.load(open(tmp_path / "wl.json"))["targets"]}
    assert "0xlim" in wl


def test_wallet_parked_this_sweep_is_not_rechecked_immediately(tmp_path):
    # A wallet the gate parks THIS sweep must not also be re-checked THIS sweep
    # (that would burn a second rate-limited call for nothing).
    seq = [{"0xk": _ev("0xk")},
           {"0xk": _ev("0xk"), "0xlim": _ev("0xlim")}]
    calls = {"lim": 0}

    def review(dossier, model=None):
        if dossier["wallet"] == "0xlim":
            calls["lim"] += 1
            return RATE_LIMITED
        return LLMVerdict("follow", "low", True, 0.7, "ok")

    r, _ = _runner(tmp_path, seq=seq, review_fn=review)
    r.run_once()          # init
    r.run_once()          # sweep 2: gate parks 0xlim; drain must NOT re-check it now
    assert calls["lim"] == 1                      # exactly ONE call (the gate), not two


def test_drain_caps_rechecks_per_sweep(tmp_path):
    # Park 5 wallets (still rate-limited), cap the re-checks at top_n=2 per sweep.
    news = {f"0xw{i}": _ev(f"0xw{i}") for i in range(5)}
    seq = [{"0xk": _ev("0xk")},
           {"0xk": _ev("0xk"), **news},
           {"0xk": _ev("0xk"), **news}]
    calls = {"n": 0}

    def review(dossier, model=None):
        if dossier["wallet"].startswith("0xw"):
            calls["n"] += 1
            return RATE_LIMITED
        return LLMVerdict("follow", "low", True, 0.7, "ok")

    r = DiscoveryRunner(
        config=CFG, watchlist_path=str(tmp_path / "wl.json"),
        state_path=str(tmp_path / "state.json"),
        evaluate=lambda config, **kw: seq[min(_seq_i(calls, seq), len(seq) - 1)],
        llm_review=review, llm_review_enabled=True, llm_review_top_n=2,
        now=lambda: 100.0)
    gate_recheck_queue.clear_cache()
    r.run_once()                       # init
    r.run_once()                       # sweep 2: 5 parked (gate calls), no same-sweep drain
    calls["n"] = 0                     # count only the sweep-3 DRAIN re-checks
    r.run_once()                       # sweep 3: drain, capped at 2
    assert calls["n"] == 2             # cap honored; the other 3 wait for next sweep


def _seq_i(calls, seq):
    calls.setdefault("i", 0)
    i = calls["i"]
    calls["i"] += 1
    return i


def q_empty(r):
    return gate_recheck_queue.pending(r.gate_recheck_queue_path) == []
