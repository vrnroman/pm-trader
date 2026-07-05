# Backlog

## Backfill the LLM gate against the current shortlist  ✅ SHIPPED 2026-07-03

Shipped `poly_poly_bot/scripts/audit_shortlist_llm_gate.py` — reads
`copy_watchlist.json`, rebuilds each wallet's dossier via the live
`discovery_runner._dossier_from_eval`, runs `review_wallet`, and cross-references
every verdict against the wallet's realized paper PnL (`copy_paper_ledger.jsonl`),
printing a per-wallet table + the would-skip list (flagging skips that are
paper-POSITIVE as "gate may be wrong / recovered"). Read-only, `--dry-run` /
`--limit` / `--json`. Audit, not auto-purge. (Original spec kept below.)

### Original spec

### Why
The Claude wallet gate (Strategy 1c) went live 2026-06-29 (commit `18d82c8`) and
only runs on *newly* qualified wallets. The wallets already on
`data/copy_watchlist.json` at activation time (~18, up to the 500 cap) were
**never gated** — they were admitted before the gate existed. We want to know,
retroactively: *if the LLM gate had been active when each shortlisted wallet
qualified, would it still have been added?* i.e. run the same `follow/watch/skip`
check over the whole current shortlist and surface the wallets the gate would
have **skipped**.

### How
One-off pass (script or a one-time branch in the next discovery sweep) — does
**not** need a full universe re-sweep, because the watchlist rows already carry
the metrics the dossier needs:

1. Read `data/copy_watchlist.json` (each `targets[]` row has `roi`, `tstat`,
   `capture_cents`, `lead_cents`, `hit_rate`, `tail_ratio`, `copy_roi`/`copy_n`,
   `curve_*`, etc. — see `discovery._meta`).
2. For each wallet, rebuild the dossier (reuse `discovery_runner._dossier_from_eval`
   shape, or map the row fields directly into `llm_review.build_dossier`).
3. Call `llm_review.review_wallet(dossier, model=CONFIG.wallet_discovery_llm_model)`
   for each — bounded/throttled (it's a real `claude -p` call, ~5–20 s each; the
   full shortlist is fine sequentially on the subscription).
4. Emit a report: per-wallet `verdict` + reasoning + cost, and the **skip list**
   (wallets that would not have been admitted). Tag the Langfuse traces (e.g.
   `audit:shortlist-backfill`) so they're separable from live-gate traffic.

### Decision discipline
This is an **audit, not an auto-purge**. A `skip` on a wallet that's *currently
paper-profitable* is a flag to investigate, not an automatic removal — cross-check
each skip against its live paper PnL (`/pnl`, `copy_paper_ledger.jsonl`) before
deciding whether to demote/blacklist it. Decide the policy (alert-only vs prune
on N independent skips) after seeing the first report.

### Files / entry points
- New `poly_poly_bot/scripts/audit_shortlist_llm_gate.py` (read watchlist →
  dossier → `review_wallet` → table + skip list), or a `--once` audit flag on the
  discovery runner.
- Reuses: `src/copy_trading/llm_review.py`, `discovery_runner._dossier_from_eval`,
  `src/copy_trading/langfuse_telemetry.py` (already records every call).
- Run after the gate has accrued some live verdicts, so the audit's prompts/model
  match what production is actually using.

## Measure whether the LLM gate is actually +EV (gate self-calibration)  ⏳ PHASE 1 SHIPPED 2026-07-03

**Phase 1 (holdout) shipped.** `discovery_runner._llm_gate` now: on a `skip`
verdict, with probability `GATE_HOLDOUT_FRAC` (default 0.0 = off; enable in prod)
and capped at `GATE_HOLDOUT_MAX_PER_SWEEP` (default 2), admits the wallet anyway,
flags the `gate-history.jsonl` row `holdout:true, admitted:true` (keeping the
original `skip` verdict + reasoning), and stamps a `confidence_band`
(high/medium/low) on every row for later slicing. The counterfactual clock is
running once the frac is turned on. **Phase 2 (the calibration report joining
gate-history to paper PnL, sliced by confidence band) is still pending** — it
genuinely needs weeks of holdout outcomes before it can say anything. `/gate` now
shows the holdout count. (Original spec below; Phase 1 items are done.)

### Original spec

### Why
The Claude wallet gate decides which wallets reach the watchlist (and become
promotion candidates for real capital), but **nothing measures whether its
admit/reject calls are correct**. It says `skip … artifact` at high confidence
many times a day and we never learn if those wallets would have made money. The
gate's own edge is unmeasured — which, for a system built to distrust fake edges,
makes the gate itself an unvalidated one. This item scores the gate against
realized outcomes so we know if it's filtering **signal** (killing real artifacts)
or filtering **edge** (rejecting wallets that would have paid), *before* we trust
real money to its decisions.

### The measurement
1. **Admitted side (free — data already exists).** Join gate decisions in
   `data/gate-history.jsonl` (wallet, verdict, confidence, theories, ts — shipped
   2026-07-02) to the paper outcomes of the admitted wallets
   (`copy_paper_ledger.jsonl`). Yields "admitted wallets: median paper ROI +X%,
   hit Y%".
2. **Rejected side (the hard part — needs a holdout).** A naive join only sees
   admitted wallets, so it measures "the ones I let in did fine" — a
   selection-biased self-congratulation loop, not a test of the gate. To get the
   counterfactual you must occasionally **admit a wallet the gate would have
   rejected**, tag it, and let it accrue paper outcomes. Only then can you compare
   would-have-rejected ROI vs admitted ROI and know if the rejections were right.

### Phase 1 — the holdout (small, buildable now, unblocks everything)
In `discovery_runner._llm_gate`, when a verdict is `skip`, with probability
`GATE_HOLDOUT_FRAC` (default ~0.1) admit the wallet anyway, flag its gate-history
row `admitted:true, holdout:true` (keep the original skip verdict + reasoning),
and let the paper harness copy it like any other. Reversible, paper-side, no new
infra. It starts the counterfactual clock so Phase 2 has real data in a few weeks.
Cap the holdout exposure — by construction it is admitting wallets the gate thinks
are bad.

### Phase 2 — calibration report + optional feedback (after weeks of data)
- A job (or a `/gate --calibration` view) that joins gate-history to paper PnL and
  reports **admitted-ROI vs holdout-ROI**, sliced by confidence band and by
  qualifying theory. The money question: do the high-confidence skips we
  holdout-admitted actually lose? If yes, the gate is +EV; if the holdouts win,
  the gate is rejecting edge.
- Optional feedback loop: fold the measured calibration into the gate `_SYSTEM`
  prompt as running evidence ("wallets with capture ∈ [-1,0] we admitted returned
  −8%; theory-qualified null-capture wallets returned +12%") so the gate
  calibrates on outcomes, not static priors.

### Decision discipline
The holdout is the guard against a fake-edge loop — do **not** ship Phase 2
without it, or the report will only ever flatter the gate. Keep the holdout
fraction small and its exposure capped. Treat the first calibration report as
evidence to tune the gate prompt / thresholds by hand, not to auto-change them.

### Files / entry points
- `src/copy_trading/discovery_runner.py` — `_llm_gate` / `_record_gate`: the
  holdout branch + the `holdout` flag on the history row.
- `src/copy_trading/gate_history.py` — already the substrate; `summarize` grows a
  calibration mode, or a new `gate_calibration.py` joins it to
  `copy_paper_ledger.jsonl`.
- `src/telegram_bot.py` — `_handle_gate`: a calibration section.
- `src/config.py` — `GATE_HOLDOUT_FRAC` (default 0.1) + a holdout exposure cap.

### Dependency
Blocked on `gate-history.jsonl` accruing weeks of decisions AND resolved paper
outcomes for the admitted + holdout wallets. The observability shipped 2026-07-02
(gate-history + `/gate` + Langfuse per-theory tags) is deliberately this item's
substrate; **Phase 1 (holdout) can start now** to begin accumulating the
counterfactual.
