"""Paper-evidence retention override + gate autopsy (starvation RCA 2026-07).

Covers the whole path: the realized-ledger reader (``paper_proven_wallets``),
the pure cycle override in ``run_discovery_cycle`` (bypass predictive gates,
proven-negative still binds, never sticky), the runner's force-include +
gate-skip suppression, the cull-attribution autopsy, and the dossier's
realized-paper block.
"""

from __future__ import annotations

import json

from src.copy_trading import governance
from src.copy_trading.discovery import (
    DiscoveryConfig,
    DiscoveryState,
    Eval,
    run_discovery_cycle,
)
from src.copy_trading.discovery_runner import DiscoveryRunner
from src.copy_trading.llm_review import build_dossier

CFG = DiscoveryConfig(
    min_capture_cents=1.5, min_tstat=10.0, drop_capture_cents=1.0,
    watchlist_cap=5, auto_remove=True,
)


def _ev(w, cap=2.0, tstat=12.0, **kw):
    return Eval(wallet=w, capture_cents=cap, tstat=tstat, roi=0.5,
                hit_rate=0.6, n=20, **kw)


def _decayed(w, **kw):
    # fails every entry path: no capture, no t-stat, no theory flags
    return Eval(wallet=w, capture_cents=0.0, tstat=0.0, roi=0.0,
                hit_rate=0.0, n=20, **kw)


# --------------------------------------------------------------------------- #
# run_discovery_cycle: the override itself
# --------------------------------------------------------------------------- #

def test_paper_proven_qualifies_despite_decayed_stats():
    r = run_discovery_cycle({"0xp": _decayed("0xp")}, DiscoveryState(), CFG,
                            paper_proven={"0xp"})
    assert [e.wallet for e in r.watchlist] == ["0xp"]
    assert r.paper_proven == ["0xp"]


def test_no_paper_proven_set_keeps_legacy_behaviour():
    evaluated = {"0xp": _decayed("0xp"), "0xa": _ev("0xa")}
    legacy = run_discovery_cycle(evaluated, DiscoveryState(), CFG)
    explicit = run_discovery_cycle(evaluated, DiscoveryState(), CFG,
                                   paper_proven=set())
    assert [e.wallet for e in legacy.watchlist] == ["0xa"]
    assert ([e.wallet for e in legacy.watchlist]
            == [e.wallet for e in explicit.watchlist])
    assert explicit.paper_proven == []


def test_paper_proven_bypasses_tail_and_curve_gates():
    cfg = DiscoveryConfig(
        min_capture_cents=1.5, min_tstat=10.0, drop_capture_cents=1.0,
        watchlist_cap=5, max_tail_ratio=0.4, max_curve_drawdown=1.5,
        max_hit_rate=0.95, min_curve_n=20,
    )
    # tail-dominated AND catastrophic drawdown AND scooper hit-profile
    ugly = Eval(wallet="0xp", capture_cents=2.0, tstat=25.0, n=30,
                tail_ratio=0.9, curve_drawdown=4.0, closed_hit_rate=0.99,
                n_closed=100, net_pnl=-500.0, curve_sharpe=-1.0)
    culled = run_discovery_cycle({"0xp": ugly}, DiscoveryState(), cfg)
    assert culled.watchlist == []
    rescued = run_discovery_cycle({"0xp": ugly}, DiscoveryState(), cfg,
                                  paper_proven={"0xp"})
    assert [e.wallet for e in rescued.watchlist] == ["0xp"]


def test_blacklist_binds_even_for_paper_proven():
    r = run_discovery_cycle({"0xp": _ev("0xp")}, DiscoveryState(), CFG,
                            blacklisted={"0xp"}, paper_proven={"0xp"})
    assert r.watchlist == []
    assert "blacklist" in r.culled["0xp"]


def test_replay_proven_negative_binds_even_for_paper_proven():
    cfg = DiscoveryConfig(
        min_capture_cents=1.5, min_tstat=10.0, drop_capture_cents=1.0,
        watchlist_cap=5, copy_replay_gate=True, min_copy_replay_n=10,
        min_copy_replay_roi=0.02,
    )
    loser = _ev("0xp", copy_n=50, copy_roi=-0.10)
    r = run_discovery_cycle({"0xp": loser}, DiscoveryState(), cfg,
                            paper_proven={"0xp"})
    assert r.watchlist == []
    assert "replay-proven-negative" in r.culled["0xp"]


def test_paper_proven_ranks_first_under_cap_pressure():
    # 3 slots, 3 strong incumbents + 1 paper-proven wallet with zeroed stats:
    # without the rank boost the proven wallet (ranked dead-last on predictive
    # signals) would be the one ranked out — self-defeating for the override.
    cfg = DiscoveryConfig(
        min_capture_cents=1.5, min_tstat=10.0, drop_capture_cents=1.0,
        watchlist_cap=3, auto_remove=True,
    )
    evaluated = {
        "0xa": _ev("0xa", cap=5.0, flagged_by=("1b", "1c")),
        "0xb": _ev("0xb", cap=4.0, flagged_by=("1b",)),
        "0xc": _ev("0xc", cap=3.0, flagged_by=("1b",)),
        "0xp": _decayed("0xp"),
    }
    r = run_discovery_cycle(evaluated, DiscoveryState(), cfg,
                            paper_proven={"0xp"})
    on = [e.wallet for e in r.watchlist]
    assert on[0] == "0xp"           # realized evidence outranks predictions
    assert len(on) == 3 and "0xp" in on


def test_paper_proven_is_not_sticky_across_sweeps():
    # sweep 1: proven -> on the list; sweep 2: no longer proven -> decays off
    s1 = run_discovery_cycle({"0xp": _decayed("0xp")}, DiscoveryState(), CFG,
                             paper_proven={"0xp"})
    assert [e.wallet for e in s1.watchlist] == ["0xp"]
    s2 = run_discovery_cycle({"0xp": _decayed("0xp")}, s1.new_state, CFG,
                             paper_proven=set())
    assert s2.watchlist == []
    assert s2.removed == ["0xp"]
    assert "decayed" in s2.culled["0xp"]


# --------------------------------------------------------------------------- #
# gate autopsy (cull attribution)
# --------------------------------------------------------------------------- #

def test_cull_reasons_are_attributed_per_gate():
    cfg = DiscoveryConfig(
        min_capture_cents=1.5, min_tstat=10.0, drop_capture_cents=1.0,
        watchlist_cap=5, max_tail_ratio=0.4, max_curve_drawdown=1.5,
        max_hit_rate=0.95, min_curve_n=20,
    )
    evaluated = {
        "0xtail": _ev("0xtail", tail_ratio=0.9),
        "0xdd": Eval(wallet="0xdd", capture_cents=2.0, tstat=25.0, n=30,
                     n_closed=100, curve_drawdown=4.0),
        "0xhit": Eval(wallet="0xhit", capture_cents=2.0, tstat=25.0, n=30,
                      n_closed=100, closed_hit_rate=0.99, net_pnl=-100.0,
                      curve_sharpe=-1.0),
        "0xok": _ev("0xok"),
    }
    r = run_discovery_cycle(evaluated, DiscoveryState(), cfg)
    assert [e.wallet for e in r.watchlist] == ["0xok"]
    assert r.culled["0xtail"].startswith("tail-ratio")
    assert "0.900" in r.culled["0xtail"]          # metric value included
    assert r.culled["0xdd"].startswith("curve-drawdown")
    assert "4.00" in r.culled["0xdd"]
    assert r.culled["0xhit"].startswith("hit-rate-scooper")


def test_removed_wallet_without_gate_hit_reads_as_decay():
    s1 = run_discovery_cycle({"0xa": _ev("0xa")}, DiscoveryState(), CFG)
    s2 = run_discovery_cycle({"0xa": _decayed("0xa")}, s1.new_state, CFG)
    assert s2.removed == ["0xa"]
    assert "decayed" in s2.culled["0xa"]


def test_removed_wallet_not_swept_is_attributed():
    s1 = run_discovery_cycle({"0xa": _ev("0xa")}, DiscoveryState(), CFG)
    s2 = run_discovery_cycle({"0xb": _ev("0xb")}, s1.new_state, CFG)
    assert s2.removed == ["0xa"]
    assert "not-swept" in s2.culled["0xa"]


# --------------------------------------------------------------------------- #
# governance.paper_proven_wallets: the realized-ledger reader
# --------------------------------------------------------------------------- #

def _ledger_row(target, pnl, spent=50.0, closed=True, **kw):
    row = {
        "copy_id": f"{target}-{pnl}-{kw.get('token_id', 't')}",
        "target": target, "condition_id": "c", "token_id": kw.get("token_id", "t"),
        "outcome_index": 0, "category": "sports", "their_price": 0.5,
        "entry_price": 0.5, "shares": spent / 0.5, "spent": spent,
        "drag_bps": 0, "opened_ts": 1.0, "closed": closed,
        "won": pnl > 0, "pnl": pnl, "closed_ts": 2.0,
    }
    row.update(kw)
    return row


def _write_ledger(tmp_path, rows):
    p = tmp_path / "ledger.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return str(p)


def test_paper_proven_wallets_applies_floors(tmp_path):
    rows = (
        # 0xgood: 5 settled, net positive -> proven
        [_ledger_row("0xgood", 10.0, token_id=f"g{i}") for i in range(5)]
        # 0xthin: only 4 settled -> under the n floor
        + [_ledger_row("0xthin", 10.0, token_id=f"t{i}") for i in range(4)]
        # 0xloser: 5 settled, net negative -> not proven
        + [_ledger_row("0xloser", -10.0, token_id=f"l{i}") for i in range(5)]
        # 0xopen: positions still open don't count as settled
        + [_ledger_row("0xopen", 0.0, closed=False, token_id=f"o{i}")
           for i in range(5)]
    )
    path = _write_ledger(tmp_path, rows)
    out = governance.paper_proven_wallets(path, min_n=5, min_roi=0.0)
    assert set(out) == {"0xgood"}
    assert out["0xgood"]["n_closed"] == 5
    assert out["0xgood"]["roi"] > 0
    assert out["0xgood"]["net_pnl"] == 50.0


def test_paper_proven_wallets_skips_dust_and_garbage_lines(tmp_path):
    dust = _ledger_row("0xdust", 100.0, token_id="d")
    dust["their_price"] = 0.5
    dust["entry_price"] = 0.001   # implausible deep-discount fill -> dust
    rows = [dust] + [_ledger_row("0xgood", 10.0, token_id=f"g{i}") for i in range(5)]
    path = _write_ledger(tmp_path, rows)
    with open(path, "a") as f:
        f.write("{not json}\n")   # torn line must not void the ledger
    out = governance.paper_proven_wallets(path, min_n=1, min_roi=0.0)
    assert "0xdust" not in out
    assert "0xgood" in out


def test_paper_proven_wallets_fails_safe(tmp_path):
    assert governance.paper_proven_wallets(
        str(tmp_path / "missing.jsonl"), min_n=5, min_roi=0.0) == {}
    bad = tmp_path / "bad.jsonl"
    bad.write_text('["not", "a", "dict"]\n')
    assert governance.paper_proven_wallets(str(bad), min_n=5, min_roi=0.0) == {}


# --------------------------------------------------------------------------- #
# DiscoveryRunner: force-include, re-acquire ping, gate-skip suppression
# --------------------------------------------------------------------------- #

def _runner(tmp_path, evaluated_seq, sink, ledger_rows=None, **kw):
    calls = {"i": 0, "must_include": []}

    def fake_eval(cfg, must_include=None, **_kw):
        calls["must_include"].append(set(must_include or ()))
        d = evaluated_seq[min(calls["i"], len(evaluated_seq) - 1)]
        calls["i"] += 1
        return d

    ledger_path = None
    if ledger_rows is not None:
        ledger_path = _write_ledger(tmp_path, ledger_rows)
    r = DiscoveryRunner(
        config=CFG,
        watchlist_path=str(tmp_path / "copy_watchlist.json"),
        state_path=str(tmp_path / "discovery_state.json"),
        notify=sink.append,
        evaluate=fake_eval,
        now=lambda: 1000.0,
        paper_ledger_path=ledger_path,
        paper_proven_min_n=5,
        paper_proven_min_roi=0.0,
        **kw,
    )
    return r, calls


def test_runner_force_includes_and_reacquires_paper_proven(tmp_path):
    rows = [_ledger_row("0xp", 10.0, token_id=f"p{i}") for i in range(5)]
    sink: list[str] = []
    # seed a prior state so the sweep isn't first_init (pings suppressed on init)
    r, calls = _runner(
        tmp_path,
        [{"0xa": _ev("0xa")},                                # sweep 1: init
         {"0xa": _ev("0xa"), "0xp": _decayed("0xp")}],       # sweep 2: 0xp re-swept
        sink, ledger_rows=rows)
    r.run_once()
    sink.clear()
    r.run_once()
    # the proven wallet was force-included in the sweep
    assert "0xp" in calls["must_include"][1]
    # ...and re-acquired onto the watchlist despite decayed stats
    wl = json.load(open(tmp_path / "copy_watchlist.json"))
    assert "0xp" in {t["wallet"] for t in wl["targets"]}
    # ...with the distinct re-acquire ping
    assert any("Paper-proven re-acquired" in m for m in sink)


def test_runner_without_ledger_path_is_legacy(tmp_path):
    sink: list[str] = []
    r, calls = _runner(tmp_path, [{"0xa": _ev("0xa"), "0xp": _decayed("0xp")}],
                       sink, ledger_rows=None)
    r.run_once()
    wl = json.load(open(tmp_path / "copy_watchlist.json"))
    assert {t["wallet"] for t in wl["targets"]} == {"0xa"}


def test_gate_skip_suppresses_regate_until_new_evidence(tmp_path):
    # gate history: last decision for 0xp was a real skip judged WITH the same
    # paper record (paper_n=5) -> _paper_proven must exclude it this sweep.
    rows = [_ledger_row("0xp", 10.0, token_id=f"p{i}") for i in range(5)]
    sink: list[str] = []
    r, _ = _runner(tmp_path, [{"0xp": _decayed("0xp")}], sink, ledger_rows=rows)
    hist = tmp_path / "gate-history.jsonl"
    hist.write_text(json.dumps({
        "ts": 1.0, "wallet": "0xp", "verdict": "skip", "admitted": False,
        "paper_proven": True, "paper_n": 5,
    }) + "\n")
    assert r._paper_proven() == {}
    # new settled evidence (n changed) re-opens the question
    hist.write_text(json.dumps({
        "ts": 1.0, "wallet": "0xp", "verdict": "skip", "admitted": False,
        "paper_proven": True, "paper_n": 4,
    }) + "\n")
    assert set(r._paper_proven()) == {"0xp"}
    # a skip judged WITHOUT the paper record does not suppress
    hist.write_text(json.dumps({
        "ts": 1.0, "wallet": "0xp", "verdict": "skip", "admitted": False,
    }) + "\n")
    assert set(r._paper_proven()) == {"0xp"}


def test_failed_reacquire_is_attributed_in_logs(tmp_path, caplog):
    # A paper-proven wallet culled in-cycle (replay-proven-negative outvotes the
    # realized record) must leave an attributable autopsy line — before this,
    # only REMOVED-from-watchlist wallets were attributed, so a failed reacquire
    # vanished silently (2026-07-09: two +ROI earners, no trace in the logs).
    import logging

    cfg = DiscoveryConfig(
        min_capture_cents=1.5, min_tstat=10.0, drop_capture_cents=1.0,
        watchlist_cap=5, copy_replay_gate=True, min_copy_replay_n=10,
        min_copy_replay_roi=0.02,
    )
    rows = [_ledger_row("0xp", 10.0, token_id=f"p{i}") for i in range(5)]
    loser = _ev("0xp", copy_n=50, copy_roi=-0.10)
    r = DiscoveryRunner(
        config=cfg,
        watchlist_path=str(tmp_path / "copy_watchlist.json"),
        state_path=str(tmp_path / "discovery_state.json"),
        notify=lambda _m: None,
        evaluate=lambda *_a, **_k: {"0xa": _ev("0xa"), "0xp": loser},
        now=lambda: 1000.0,
        paper_ledger_path=_write_ledger(tmp_path, rows),
        paper_proven_min_n=5,
        paper_proven_min_roi=0.0,
    )
    with caplog.at_level(logging.INFO, logger="poly_poly_bot"):
        r.run_once()
    lines = [rec.getMessage() for rec in caplog.records
             if "paper-proven reacquire FAILED" in rec.getMessage()]
    assert len(lines) == 1
    assert "0xp" in lines[0]
    assert "replay-proven-negative" in lines[0]
    assert "5 settled" in lines[0]
    # the wallet that made the watchlist is not flagged
    assert "0xa" not in lines[0]


def test_successful_reacquire_logs_no_failure(tmp_path, caplog):
    import logging

    rows = [_ledger_row("0xp", 10.0, token_id=f"p{i}") for i in range(5)]
    sink: list[str] = []
    r, _ = _runner(tmp_path, [{"0xa": _ev("0xa"), "0xp": _decayed("0xp")}],
                   sink, ledger_rows=rows)
    with caplog.at_level(logging.INFO, logger="poly_poly_bot"):
        r.run_once()
    assert not any("paper-proven reacquire FAILED" in rec.getMessage()
                   for rec in caplog.records)


# --------------------------------------------------------------------------- #
# dossier: the realized paper record block
# --------------------------------------------------------------------------- #

def test_build_dossier_includes_realized_paper_record():
    d = build_dossier("0xp", paper_record={"n_closed": 7, "roi": 0.42,
                                           "net_pnl": 86.84, "wins": 5})
    blk = d["paper_record_realized"]
    assert blk["n_settled"] == 7
    assert blk["roi"] == 0.42
    assert blk["net_pnl_usd"] == 86.84
    assert blk["wins"] == 5


def test_build_dossier_omits_empty_paper_record():
    assert "paper_record_realized" not in build_dossier("0xp")
    assert "paper_record_realized" not in build_dossier(
        "0xp", paper_record={"n_closed": 0})
