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
