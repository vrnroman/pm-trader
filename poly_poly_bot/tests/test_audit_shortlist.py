"""Tests for the shortlist LLM-gate backfill audit (read-only, no auto-purge)."""

from __future__ import annotations

import json

from scripts import audit_shortlist_llm_gate as audit
from src.copy_trading.llm_review import RATE_LIMITED, LLMVerdict


def test_eval_like_from_row_maps_fields():
    row = {"wallet": "0xA", "roi": 0.5, "tstat": 12.0, "n": 20,
           "copy_roi": 0.1, "copy_n": 14, "flagged_by": ["1b", "1f"], "reason": "why"}
    e = audit.eval_like_from_row(row)
    assert e.wallet == "0xA" and e.roi == 0.5 and e.n == 20
    assert e.flagged_by == ("1b", "1f")
    # a field absent from the row falls back to the default (omitted downstream)
    assert e.net_pnl is None


def test_run_audit_joins_verdict_and_paper():
    rows = [
        {"wallet": "0xKEEP", "rank": 1, "flagged_by": ["1b"], "roi": 0.4, "n": 30, "copy_n": 20, "copy_roi": 0.12},
        {"wallet": "0xSKIP", "rank": 2, "flagged_by": ["1e"], "roi": 0.9, "n": 3},
    ]
    paper = {"0xkeep": {"roi": 0.15, "n_closed": 20, "net_pnl": 120.0},
             "0xskip": {"roi": 0.20, "n_closed": 8, "net_pnl": 40.0}}

    def review(dossier, model=None):
        if dossier["wallet"] == "0xSKIP":
            return LLMVerdict("skip", "high", False, 0.88, "variance artifact")
        return LLMVerdict("follow", "low", True, 0.7, "solid")

    report = audit.run_audit(rows, paper, review_fn=review, model="m")
    by = {r["wallet"]: r for r in report}
    assert by["0xKEEP"]["verdict"] == "follow"
    assert by["0xSKIP"]["verdict"] == "skip"
    # cross-referenced to realized paper PnL (the audit's whole point)
    assert by["0xSKIP"]["paper_roi"] == 0.20
    assert by["0xKEEP"]["paper_n"] == 20


def test_run_audit_flags_rate_limited():
    # if claude is rate-limited during the audit, those wallets are marked (not
    # silently rendered as a verdict) so the operator knows the audit is incomplete.
    rows = [{"wallet": "0xA", "rank": 1, "flagged_by": ["1b"]}]
    report = audit.run_audit(rows, {}, review_fn=lambda d, model=None: RATE_LIMITED,
                             model="m")
    assert report[0]["rate_limited"] is True
    assert report[0]["verdict"] is None            # sentinel not treated as a verdict


def test_run_audit_dry_run_skips_llm():
    rows = [{"wallet": "0xA", "rank": 1, "flagged_by": ["1b"]}]
    called = {"n": 0}

    def review(dossier, model=None):
        called["n"] += 1
        return LLMVerdict("follow", "low", True, 0.7, "x")

    report = audit.run_audit(rows, {}, review_fn=review, model="m", dry_run=True)
    assert called["n"] == 0                       # no LLM call in dry-run
    assert report[0]["verdict"] is None


def test_run_audit_limit():
    rows = [{"wallet": f"0x{i}", "rank": i, "flagged_by": []} for i in range(5)]
    report = audit.run_audit(rows, {}, review_fn=lambda d, model=None: None,
                             model="m", dry_run=True, limit=2)
    assert len(report) == 2


def test_load_watchlist_roundtrip(tmp_path):
    p = tmp_path / "wl.json"
    p.write_text(json.dumps({"targets": [{"wallet": "0xA", "rank": 1}]}))
    rows = audit.load_watchlist(str(p))
    assert rows == [{"wallet": "0xA", "rank": 1}]
