# Backlog

## Backfill the LLM gate against the current shortlist

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

## Decouple Gamma from per-scan pricing (tennis arb)

### Problem
`/tennis-metrics` over 8893 scans (2026-05-11 → 2026-05-14):

- `gamma_s` 0.71s avg per scan (2nd largest phase after Smarkets).
- **2038 / 2239 = 91 % of detected signals die at CLOB revalidation** with `live_edge_too_low`. Gamma's `bestAsk` is stale relative to CLOB, so divergence is being computed against a fictional price.
- `pm_markets_count` (post current gates): p50=20, p95=25, max=27.
- `sharp_odds_count`: p50=12 outcomes (~6 matches).
- Live Gamma probe with prod gates, time-windowed: ~15 singles markets at any moment.

### Proposed architecture

Two-tier:

1. **Discovery cache (slow, every 5–10 min)** — Gamma page with current `tag_slug=tennis, active=true, closed=false` query, but only on a TTL refresh, not every scan. Cache size **up to 400 markets**, keyed by `condition_id`. Cache fields: `token_id_yes`, `token_id_no`, `tick`, player names, `groupItemTitle`, `gameStartTime`, `question`, `volume`, `liquidity`. All static for the market's life.

2. **Active set (per scan)** — filter the cache to markets with `gameStartTime ∈ [now − 2 h, now + 20 min]`. Should yield ~10–50 markets typically; ≤80 in heavy overlap windows. This is what gets price-checked.

3. **Live pricing (per scan)** — one or N batched CLOB calls (`POST /books` via `clob_client.get_order_books(params)`) over the active-set token_ids. Compute divergence vs Smarkets against **live CLOB asks**. No revalidation step — there's no stale layer in between any more.

### Cache size: 400 (not 25)

Cheap. 400 entries × ~150 bytes = ~60 KB. The 25 in my earlier sketch was the *active-set* size by accident; the discovery cache should be wide so the next match starting in 30 min is already in memory. If we add the 20-min `gameStartTime` filter on the active set, the per-scan CLOB load stays small regardless of cache breadth.

### Parallel vs single batched CLOB call — analysis

User suggestion: 1–4 parallel requests, ~10 events (20 tokens) each.

| Shape | Latency model | Pros | Cons |
|---|---|---|---|
| 1 × 40-token batch | RTT + server_proc(40) ≈ 300–500 ms (extrapolating from p50=272 ms single-book) | Simplest. One rate-limit slot. | Single point of failure: if the call 5xx's, whole scan loses CLOB picture. |
| 2 × 20-token parallel | max(RTT + proc(20), RTT + proc(20)) ≈ 200–350 ms | Failure isolation. Modest latency win. | 2× connections (mitigated by `requests.Session` keep-alive). |
| 4 × 10-token parallel | max(4 × small) ≈ 150–300 ms | More isolation. | Diminishing returns: at small N, RTT dominates over server_proc, so going wider stops paying off. 4× TLS slots. |

**Recommendation:** start with **1 × batched** call. Only shard if (a) active set grows past ~80 token_ids, or (b) single-call p95 latency creeps past ~600 ms. If we shard, **2-way is the sweet spot** — 4-way doesn't beat the RTT floor much. Keep `requests.Session` reuse so TLS handshake amortizes.

The table above is a back-of-envelope estimate. **Before any implementation, Claude must empirically benchmark** the call shapes against the real CLOB and pick the winner:

1. Pick a representative token_id set (~40 tokens, real tennis match-winner markets currently active — pull live from Gamma at test time).
2. Run each shape **at least 10 times back-to-back** to wash out single-call noise:
   - `A`: 1 × `get_order_books(40 tokens)`
   - `B`: 2 × `get_order_books(20 tokens)` in parallel (`ThreadPoolExecutor`, `Session` reused)
   - `C`: 4 × `get_order_books(10 tokens)` in parallel
3. Record p50, p95, max per shape. Spread the runs over a few minutes so they don't share CDN/server-cache state.
4. Note any failed/throttled calls per shape — if 4-way trips a rate limit while 1-way doesn't, that decides it.
5. Pick the shape with the best p95 latency, **unless the gap is <100 ms**, in which case prefer 1-way (simpler code, fewer failure modes).

Freshness is independent of call shape — all three options read live CLOB. The 1-vs-4 question is *only* about latency and failure isolation, not data quality.

### Lowering vol/liq gates: caveat first

User proposal: `vol ≥ 30k, liq ≥ 8k` (was 50k / 10k).

Live Gamma probe shows looser gates add 5 markets — but **3 of those 5 are derivatives the current `_DERIVATIVE_QUESTION_KEYWORDS` filter misses**:

- "Will Linda Nosková win the 2026 Women's French Open?" — tournament outright. Smarkets does not quote this.
- "Will Carlos Alcaraz be the 2026 Men's Wimbledon winner?" — same.
- "Set Handicap: Gauff (-1.5) vs Cirstea (+1.5)" — handicap, no sharp counterpart.

Only 2 of 5 (Zagreb / Bengaluru match-winners) are real arb candidates.

**Action before lowering gates:** harden the derivative filter. Add keywords:

```python
_DERIVATIVE_QUESTION_KEYWORDS = (
    "o/u",
    "total sets",
    "set 1 winner",
    "set winner",
    "completed match",
    "handicap",          # NEW: set/game handicaps
    "will ",             # NEW: outright "Will X win the YYYY Z?" shape — start anchor
    "win the 20",        # NEW: tournament-winner outrights ("win the 2026 ...")
)
```

`"will "` is broad — needs verification it doesn't false-positive on real match questions. Match-winner questions look like `"Tournament: Player A vs Player B"`, never `"Will …"`, so it should be safe; double-check at staging.

Once the filter is hardened, dropping gates to 30k/8k yields ~+1–2 real matches per scan based on the live probe.

### Open questions before shipping

- CLOB batched-endpoint payload cap — chunk into ≤25 if `POST /books` rejects 80-token requests.
- Measure 1-batch vs 2-shard p50/p95 on a real ~40-token call in prod before deciding.
- Newly-listed markets (no `gameStartTime` populated yet) — do they need a separate code path, or just exclude them from the active set?
- Backtest hypothesis: with no Gamma staleness, do the 2038 `live_edge_too_low` drops convert to real fills, or were the edges genuinely closed by the time CLOB looked? Replay the 2239 signals from `signal_latencies` against historical CLOB snapshots if available.

### Files to touch

- `poly_poly_bot/src/tennis/tennis_arb.py`
  - `_fetch_polymarket_tennis_markets` (line 634): split into `_refresh_discovery_cache` (TTL'd) and `_active_set` (per-scan filter).
  - `scan` (line 141 onward): add `_refresh_discovery_cache` call gated on TTL; replace per-scan Gamma pull with cache read; insert single `get_order_books` batched call for live pricing.
  - Drop the revalidation step entirely (lines 245–310) — no longer needed since divergence is computed on live CLOB.
  - `_DERIVATIVE_QUESTION_KEYWORDS` (line 1269): extend per above.
  - Defaults `min_volume=50_000` (line 53), `min_liquidity=10_000` (line 54): only lower AFTER derivative filter is hardened.
- `poly_poly_bot/src/config.py`: env knobs for cache TTL (default 300 s), active-set time window (default 20 min ahead / 2 h behind), CLOB shard count (default 1).

### Anchor numbers (so future-me doesn't re-do the math)

- Active scan-time universe today: p50=20, p95=25 markets (after current gates + derivative filter).
- Per-book CLOB latency now: p50=272 ms, p95=297 ms.
- Smarkets rate today: 9.9 calls/min vs 20 ceiling — still the binding constraint after this work.
- Effective scan cadence: ~28.8 s between scan starts.
- Orders placed in window: 34 / 2239 signals = 1.5 % conversion.

### Benchmark results (2026-05-16, 40 live tennis tokens, 30 iters/shape)

Script: `poly_poly_bot/scripts/clob_books_bench.py`. Iterations interleaved
across shapes, 3 s sleep between iters, warm-up call discarded.

| Shape           | min   | p50   | p95   | max   | errors |
|-----------------|------:|------:|------:|------:|-------:|
| A: 1 × 40       | 198.0 | 236.0 | 474.9 | 499.5 |      0 |
| B: 2 × 20 par   | 188.3 | 389.9 | 501.8 | 505.6 |      0 |
| C: 4 × 10 par   | 193.0 | 228.6 | **349.6** | 355.8 |      0 |

(all ms, fetched from prod `clob.polymarket.com` from laptop in SG)

**Empirical winner: C (4-way parallel)** — beats A by 125 ms at p95
(above the 100 ms decision threshold). Surprising vs the BACKLOG
prediction that "RTT dominates at small N": single-batch p95 has a
heavy tail (~475 ms), and sharding lets the slow chunk get drowned by
the other three. p50 is essentially tied (229 vs 236 ms); the win is
entirely in the tail.

**B is dominated by both A and C** — it alternates between fast (~190 ms)
and slow (~430-500 ms) runs, p50=390 ms. Don't ship 2-way; it's the
worst of both.

**No throttling** observed at 4-way during 30 interleaved iterations
(120 total batched calls in ~5 min). Safe to ship.

→ Two-tier-pricing refactor should call `get_order_books` as 4 parallel
shards over `ThreadPoolExecutor(max_workers=4)`. Keep the `BookParams`
chunking driven by `active_set_size // 4` (round up), so it gracefully
adapts to active sets <40 (4 × 5 etc.) without code changes.
