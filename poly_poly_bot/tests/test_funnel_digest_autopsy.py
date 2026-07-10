"""funnel_digest parses the 2026-07 cull-autopsy + paper-proven log lines."""

from __future__ import annotations

from scripts.funnel_digest import digest


def test_digest_parses_autopsy_and_paper_proven_lines(tmp_path):
    log = tmp_path / "bot-2026-07-09.log"
    log.write_text("\n".join([
        "2026-07-09 12:00:00 INFO  [DISCOVERY] swept=40 qualified=20 new=2 removed=2 watchlist=20",
        "2026-07-09 12:00:01 INFO  [DISCOVERY] paper-proven (realized-ledger override): "
        "0xaaa1111111111111111111111111111111111111, 0xbbb2222222222222222222222222222222222222",
        "2026-07-09 12:00:02 INFO  [DISCOVERY] cull: 0xccc3333333333333333333333333333333333333 "
        "— curve-drawdown (2.31 > 1.50 @ n_closed=44)",
        "2026-07-09 12:00:02 INFO  [DISCOVERY] cull: 0xddd4444444444444444444444444444444444444 "
        "— decayed (no theory flag, capture/t-stat below retention)",
        "2026-07-09 12:00:03 INFO  [DISCOVERY] LLM gate REJECTED paper-proven "
        "0xaaa1111111111111111111111111111111111111 (paper n=5 roi +12.0%, conf 70%): thin sample",
        "2026-07-09 12:00:04 INFO  [DISCOVERY] paper-proven reacquire FAILED: "
        "0xeee5555555555555555555555555555555555555 — replay-proven-negative "
        "(copy_roi -0.058 < +0.020 @ n=112) (realized: 7 settled, ROI +80.5%, $+246.24)",
    ]) + "\n")
    d = digest([str(tmp_path)])
    assert d["sweeps"] == [(40, 20, 2, 2, 20)]
    assert len(d["paper_proven"]) == 2
    assert d["cull_hist"] == {"curve-drawdown": 1,
                              "decayed": 1}
    assert d["culled"]["0xccc3333333333333333333333333333333333333"].startswith(
        "curve-drawdown")
    w = "0xaaa1111111111111111111111111111111111111"
    assert w in d["pp_rejected"]
    assert w in d["all_rejected"]           # counts into the reject taxonomy too
    wf = "0xeee5555555555555555555555555555555555555"
    assert d["pp_reacquire_failed"][wf].startswith("replay-proven-negative")


def test_digest_separates_strategy_b_counters(tmp_path):
    log = tmp_path / "bot-2026-07-11.log"
    log.write_text("\n".join([
        "2026-07-11 12:00:00 INFO  [COPY-PAPER] opened=2 resolved=1 open=3 closed=10",
        "2026-07-11 12:00:01 INFO  [COPY-PAPER] guardrail skips: fill-gate=5 "
        "first-entry=1 slate-cap=2 category-gate=3",
        "2026-07-11 12:01:00 INFO  [COPY-PAPER-B] opened=7 resolved=0 open=7 closed=0",
        "2026-07-11 12:01:01 INFO  [COPY-PAPER-B] guardrail skips: fill-gate=0 "
        "first-entry=4 slate-cap=9 category-gate=1",
        "2026-07-11 12:01:02 INFO  [COPY-PAPER-B] cap-bind: 0x161a7f66…×9 (wallet-day)",
        "2026-07-11 12:02:00 INFO  [COPY-PAPER-B] cross-routed "
        "0x161a7f666ca49d592848cf415b42f49a84714103 to strategy B "
        "(replay-fit; A auto-demote (ROI -21% @ n=15))",
    ]) + "\n")
    d = digest([str(tmp_path)])
    assert d["opened"] == 2 and d["opened_b"] == 7
    assert d["guard"]["fill-gate"] == 5 and d["guard"]["slate-cap"] == 2
    assert d["guard_b"]["slate-cap"] == 9 and d["guard_b"]["fill-gate"] == 0
    assert d["cap_binds_b"] == {"0x161a7f66 (wallet-day)": 9}
    w = "0x161a7f666ca49d592848cf415b42f49a84714103"
    assert d["cross_routed"][w].startswith("replay-fit")


def test_print_report_cap_bind_loop_does_not_shadow_reject_count(tmp_path, capsys):
    # Regression (verifier, 2026-07-10): the [2b] cap-bind print loop used
    # `for k, n in …`, shadowing `n = len(all_rejected)` so section [4]'s
    # rejected-wallet count silently became the last cap-bind count.
    from scripts.funnel_digest import _print_report
    log = tmp_path / "bot-2026-07-11.log"
    log.write_text("\n".join([
        "2026-07-11 12:00:00 INFO  [DISCOVERY] LLM gate REJECTED "
        "0xaaa1111111111111111111111111111111111111 (conf 80%): pure scooper",
        "2026-07-11 12:00:01 INFO  [DISCOVERY] LLM gate REJECTED "
        "0xbbb2222222222222222222222222222222222222 (conf 70%): drawdown",
        "2026-07-11 12:01:02 INFO  [COPY-PAPER-B] cap-bind: 0x161a7f66…×9 (wallet-day)",
    ]) + "\n")
    d = digest([str(tmp_path)])
    _print_report(d)
    out = capsys.readouterr().out
    assert "distinct rejected wallets: 2" in out          # not 9 (the cap-bind count)
    assert "cap-bind" in out
