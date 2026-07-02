"""LLM admission gate must be theory-aware.

Root cause of the ~93% prod rejection rate (2026-07-02 analysis): discovery
qualifies a wallet by lead-lag copyability OR any independent theory. Theories
1a/1b/1d/1e/1f/1g/1i/1j have needs_capture=False, so a wallet qualified on, say,
1e (longshot-EV) legitimately has capture=lead=n=0. The old dossier sent those
as literal zeros with no context, and the LLM read them as an artifact -> skip.

The fix, and what these tests pin (both directions — the load-bearing constraint):

  (a) UNMEASURED (e.n == 0, theory-qualified): the `copyability` block is ABSENT
      from the dossier, and the qualifying theories are named, so the gate judges
      on the theory / copy-replay / skill / curve instead of auto-skipping.

  (b) MEASURED-NEGATIVE (e.n > 0, capture < 0, the settlement-lag scoopers): the
      `copyability` block is PRESENT with the negative value, so the gate can and
      must still skip it. The fix must NOT drift to "capture <= 0" and hide these.
"""

from __future__ import annotations

from src.copy_trading.discovery import Eval
from src.copy_trading.discovery_runner import _dossier_from_eval, _theory_brief
from src.copy_trading.llm_review import build_dossier


# --- direction (a): unmeasured lead-lag, theory-qualified -------------------- #

def test_unmeasured_copyability_block_is_absent_not_zeroed():
    e = Eval(
        wallet="0xtheoryonly",
        roi=0.9, tstat=18.0,
        capture_cents=0.0, lead_cents=0.0, hit_rate=0.0, n=0,   # lead-lag never ran
        flagged_by=("1e", "1b"),
        reason="longshot calibration edge | consistent closed-position skill",
    )
    d = _dossier_from_eval(e)
    # the block that made the LLM cry "artifact" must simply not be there
    assert "copyability" not in d
    # ...and the gate is told WHY the wallet qualified, with per-theory context
    assert "qualifying_theories" in d
    ids = {t["id"] for t in d["qualifying_theories"]}
    assert ids == {"1e", "1b"}
    assert all(t["needs_capture"] is False for t in d["qualifying_theories"])
    assert d["why_flagged"]


def test_copy_replay_block_carries_the_real_copyability_signal():
    # a theory wallet with no lead-lag sample but a solid copy-and-hold record
    e = Eval(
        wallet="0xreplay",
        roi=0.5, tstat=12.0, n=0,
        copy_roi=0.22, copy_n=140, copy_hit=0.63, exit_roi=0.3,
        flagged_by=("1g",),
    )
    d = _dossier_from_eval(e)
    assert "copyability" not in d           # lead-lag absent
    assert d["copy_replay"]["n_resolved"] == 140
    assert d["copy_replay"]["copy_and_hold_roi"] == 0.22


def test_copy_replay_block_omitted_when_no_resolved_sample():
    e = Eval(wallet="0xnone", n=0, copy_n=0, flagged_by=("1b",))
    d = _dossier_from_eval(e)
    assert "copy_replay" not in d


# --- direction (b): measured-negative capture must remain skippable ---------- #

def test_measured_negative_capture_keeps_its_block():
    # settlement-lag scooper: lead-lag DID run (n>0) and found negative capture.
    e = Eval(
        wallet="0xscooper",
        roi=0.8, tstat=14.0,
        capture_cents=-8.66, lead_cents=-10.08, hit_rate=0.33, n=12,
        flagged_by=("1b",),
    )
    d = _dossier_from_eval(e)
    # the block MUST be present with the negative value so the gate can skip it
    assert "copyability" in d
    assert d["copyability"]["capture_cents"] == -8.66
    assert d["copyability"]["n_trades"] == 12


def test_measured_positive_capture_keeps_its_block():
    e = Eval(wallet="0xgood", capture_cents=17.1, lead_cents=17.0, hit_rate=0.61,
             n=62, flagged_by=("1c",))
    d = _dossier_from_eval(e)
    assert d["copyability"]["capture_cents"] == 17.1
    assert d["copyability"]["n_trades"] == 62


# --- helpers ----------------------------------------------------------------- #

def test_theory_brief_maps_ids_to_desc_and_capture_flag():
    brief = _theory_brief(("1c", "1e", "zz"))
    by_id = {t["id"]: t for t in brief}
    assert by_id["1c"]["needs_capture"] is True        # lead-lag theory
    assert by_id["1e"]["needs_capture"] is False       # longshot theory
    assert by_id["1c"]["desc"]                          # human-readable desc present
    assert by_id["zz"] == {"id": "zz"}                  # unknown id degrades gracefully


def test_build_dossier_still_omits_new_blocks_when_not_supplied():
    # additive change must not fabricate the new keys on the bare call
    d = build_dossier("0xabc")
    assert d == {"wallet": "0xabc"}
