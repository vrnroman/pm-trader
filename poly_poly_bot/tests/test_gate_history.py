"""Gate-decision history log + summary, and that the discovery gate records to it.

Pins the observability the 2026-07-02 analysis was missing: every LLM-gate
review is appended as one JSON line (with the qualifying theories), so /gate can
show the admit/reject mix — the thing that silently sat at ~93% reject for days.
"""

from __future__ import annotations

from src.copy_trading import gate_history


def test_append_and_load_roundtrip(tmp_path):
    p = str(tmp_path / "gate-history.jsonl")
    gate_history.append(p, {"wallet": "0xa", "admitted": True, "theories": ["1b"]})
    gate_history.append(p, {"wallet": "0xb", "admitted": False, "theories": ["1e"]})
    rows = gate_history.load(p)
    assert [r["wallet"] for r in rows] == ["0xa", "0xb"]


def test_append_none_path_is_noop():
    gate_history.append(None, {"wallet": "0xa"})   # must not raise


def test_load_missing_file_is_empty(tmp_path):
    assert gate_history.load(str(tmp_path / "nope.jsonl")) == []


def test_load_tolerates_corrupt_lines(tmp_path):
    p = tmp_path / "gate-history.jsonl"
    p.write_text('{"wallet": "0xa", "admitted": true}\nnot json\n{"wallet": "0xb", "admitted": false}\n')
    rows = gate_history.load(str(p))
    assert [r["wallet"] for r in rows] == ["0xa", "0xb"]


def test_load_limit_keeps_last_n(tmp_path):
    p = str(tmp_path / "gate-history.jsonl")
    for i in range(10):
        gate_history.append(p, {"wallet": f"0x{i}", "admitted": True})
    rows = gate_history.load(p, limit=3)
    assert [r["wallet"] for r in rows] == ["0x7", "0x8", "0x9"]


def test_summarize_counts_and_per_theory():
    rows = [
        {"wallet": "0xa", "admitted": True, "theories": ["1b", "1i"]},
        {"wallet": "0xb", "admitted": False, "theories": ["1e"], "reasoning": "artifact", "confidence": 0.9},
        {"wallet": "0xc", "admitted": False, "theories": ["1e", "1b"], "reasoning": "negative capture"},
    ]
    s = gate_history.summarize(rows)
    assert s["total"] == 3 and s["admitted"] == 1 and s["rejected"] == 2
    assert s["per_theory"]["1e"] == {"admit": 0, "reject": 2}
    assert s["per_theory"]["1b"] == {"admit": 1, "reject": 1}
    assert s["recent_rejections"][-1]["reasoning"] == "negative capture"


def test_summarize_excludes_requeued_provisional_rows():
    # a deferred wallet has a provisional row (requeued, admitted) AND a later
    # re-check row (admitted=False). It must count ONCE (as the re-check), not as
    # both an admit and a reject.
    rows = [
        {"wallet": "0xd", "admitted": True, "requeued": True, "theories": ["1e"]},   # provisional
        {"wallet": "0xd", "admitted": False, "recheck": True, "theories": ["1e"]},   # real
        {"wallet": "0xa", "admitted": True, "theories": ["1b"]},
    ]
    s = gate_history.summarize(rows)
    assert s["total"] == 2 and s["admitted"] == 1 and s["rejected"] == 1
    assert s["deferred"] == 1
    assert s["per_theory"]["1e"] == {"admit": 0, "reject": 1}   # not admit:1,reject:1


# --- the discovery gate actually writes history (end-to-end via run_once) ---- #

def test_llm_gate_records_each_decision(tmp_path):
    from src.copy_trading.discovery import DiscoveryConfig, Eval
    from src.copy_trading.discovery_runner import DiscoveryRunner
    from src.copy_trading.llm_review import LLMVerdict

    cfg = DiscoveryConfig(min_capture_cents=1.5, min_tstat=10.0,
                          drop_capture_cents=1.0, watchlist_cap=5, auto_remove=True)

    def ev(w, theory):
        # theory-qualified, no lead-lag sample (the case that used to auto-skip)
        return Eval(wallet=w, capture_cents=0.0, lead_cents=0.0, hit_rate=0.0, n=0,
                    roi=0.5, tstat=12.0, flagged_by=(theory,))

    seq = [
        {"0xkeep": ev("0xkeep", "1b")},                       # sweep 1: init (no gate)
        {"0xkeep": ev("0xkeep", "1b"), "0xreject": ev("0xreject", "1e")},  # sweep 2: 0xreject is new
    ]
    calls = {"i": 0}

    def fake_eval(config, **kw):
        d = seq[min(calls["i"], len(seq) - 1)]
        calls["i"] += 1
        return d

    def verdict_fn(dossier, model=None):
        if dossier["wallet"] == "0xreject":
            return LLMVerdict("skip", "high", False, 0.88, "variance artifact")
        return LLMVerdict("follow", "low", True, 0.7, "solid")

    r = DiscoveryRunner(
        config=cfg,
        watchlist_path=str(tmp_path / "wl.json"),
        state_path=str(tmp_path / "discovery_state.json"),
        evaluate=fake_eval,
        llm_review=verdict_fn,
        llm_review_enabled=True,
        now=lambda: 123.0,
    )
    r.run_once()   # init: 0xkeep admitted without gate
    r.run_once()   # 0xreject is newly-qualified -> gated -> rejected

    rows = gate_history.load(r.gate_history_path)
    by_wallet = {row["wallet"]: row for row in rows}
    assert by_wallet["0xreject"]["admitted"] is False
    assert by_wallet["0xreject"]["theories"] == ["1e"]
    assert by_wallet["0xreject"]["reasoning"] == "variance artifact"
    assert by_wallet["0xreject"]["had_leadlag"] is False
    assert by_wallet["0xreject"]["ts"] == 123.0
