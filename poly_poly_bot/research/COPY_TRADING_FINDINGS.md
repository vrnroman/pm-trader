# Copy-Trading Selection — Empirical Findings (Strategy 1b)

_Generated from live Polymarket data-api analysis, May 2026._

## Question

Can we pick *which* Polymarket wallets to copy such that the selection has
**out-of-sample** predictive power? (Copy-trading only works if past performance
predicts future performance — otherwise you're paying fees + adverse selection
to clone a coin flip.)

## Method

- **Universe:** ~850 currently-active, large-stake wallets (sampled from the
  data-api taker trade feed at $500–$3000+ ticket sizes).
- **PnL reconstruction:** replay each wallet's `/activity` feed. Per market,
  realized PnL = (SELL + REDEEM cash) − (BUY cash). Liquidity rewards
  (`REWARD/MAKER_REBATE/YIELD`) are excluded so market makers aren't mistaken
  for skilled bettors. Share accounting was validated against PM's own
  `/positions` sizes (**13/13 exact match** on a spot-checked wallet).
- **Out-of-sample design:** split each wallet's history at a cutoff date; rank
  by lookback (P1) realized ROI; measure forward (P2) realized ROI. Repeated at
  three cutoffs (2026-02-01 / 03-01 / 04-01) to guard against a single-regime
  fluke.

## The critical methodology finding

Realized PnL **must be measured only over provably-closed positions** — markets
the wallet has either redeemed or fully exited (net shares ≈ 0). If you instead
include still-open slow positions (mark-to-market guesses), the noise destroys
the signal:

| Measurement | Out-of-sample Spearman (P1→P2 ROI) |
|---|---|
| Naive (all positions, open marked to market) | **≈ 0.00** (no predictive power) |
| Provably-closed positions only | **+0.29 … +0.37** (robust, significant) |

This is why naive leaderboard-copy bots fail. The fix is in
`src/copy_trading/trader_scoring.py`.

## Validated result (provably-closed, reliability-filtered: ≥$5k deployed, ≥10 closed markets)

`python -m backtest.trader_scoring_backtest validate`

| Category | Spearman P1→P2 | Top-20 copy portfolio — forward ROI | % of picks profitable |
|---|---|---|---|
| **All** | +0.30 … +0.37 | **+43% … +62%** | 75–85% |
| **Sports** | +0.29 … +0.46 | **+42% … +58%** (softest markets, strongest signal) | 65–85% |
| Research/geo | +0.19 … +0.42 | +0% … +10% (weak, noisy) | 45–80% |
| Crypto | ~+0.33 | low | mixed |

Population median forward ROI is ~0% (all) / ~+5-10% (sports); the **top
quartile selected by closed ROI** is what carries the edge.

## Selection rule (productionised)

1. Reconstruct realized PnL over **provably-closed** positions only.
2. Reliability filter: ≥ $5,000 capital deployed AND ≥ 10 closed markets in the
   lookback window.
3. Rank by realized ROI; take the top K.
4. **Sports is the priority segment.**

Implemented in `select_copy_targets()`; current targets via
`python -m backtest.trader_scoring_backtest watchlist --category sports`.

## Caveats — why this is NOT yet a green light for real capital

1. **Execution drag is unmeasured.** The backtest assumes you fill at the
   wallet's prices. Real copying enters *after* they move the price (adverse
   selection), pays the spread, and PM sports books are thin. The forward
   paper-copy ledger must enter at the price *we* could actually get (best
   ask/bid + slippage at our detection latency) to see how much of the +40-60%
   survives. **This is the gating test before going live.**
2. **Survivorship.** The universe is currently-active survivors; absolute ROI
   levels are inflated. The top-vs-bottom *spread* (the skill signal) is robust
   to this, but live sizing must assume far lower returns.
3. **One forward regime** (early–mid 2026), mitigated but not eliminated by the
   three overlapping cutoffs.
4. **Capacity.** ROI is on a few-$k of deployed capital per wallet per window;
   absolute $ edge is bounded by their bet sizes and market depth.

## Execution / copyability (forward harness, first live cycles)

The forward paper-copy harness (`src/copy_trading/copy_paper.py`,
`scripts/copy_paper_run.py`) copies each detected target BUY against the
*current* live book (max 200bps chase) instead of the target's price. First
live cycles over the watchlists:

| Watchlist | Detected | Filled at realistic price | Fill rate |
|---|---|---|---|
| Sports (top by ROI) | 29 | 2 | **7%** |
| Research (top by ROI) | 33 | 10 | **30%** |

**Key execution finding:** the highest-ROI "sports" wallets are largely *in-play
tennis traders* — they buy a player at a low price mid-match that then comes
back to win. That edge is **un-copyable**: by the time their trade prints on the
data-api, the in-play price has already moved past our slippage tolerance (93%
of their trades were unfillable). Slow markets (research/politics) are ~4x more
copyable because the price barely moves between their trade and our copy.

This *reverses* the naive read of the backtest: sports has the highest raw ROI
but the lowest copyable ROI. **The copyable edge likely lives in slower
markets**, even though their raw ROI is lower. The forward ledger's realized
PnL — net of drag — is what decides, per wallet and per segment.

## Better selection 1 — robust scoring (t-stat + concentration + recency)

Ranking by raw ROI rewards one lucky bet. Re-tested on the full 1036-wallet
cache (273 qualified, cutoff 2026-03-15, ~2.5-month forward window), ranking by
the **t-statistic of per-market PnL** roughly triples forward returns, and a
combined filter does better still:

| Selection metric (TOP-20) | Forward agg ROI | % profitable |
|---|---|---|
| raw ROI (original) | +9.4% | 70% |
| median per-market ROI | +12.5% | 70% |
| **t-stat of per-market PnL** | **+26.2%** | 80% |
| recent-half-positive + concentration ≤ 0.6, ranked by t-stat | **+34.7%** | 75% |

Shipped as `select_targets(method="robust")` in `trader_scoring.py`. Raw ROI
rewards variance; t-stat rewards *repeatable* edge; the concentration cap drops
single-bet wallets; the recency check keeps only wallets still winning lately.

## Better selection 2 — lead-lag / informed-money (copyability, not outcome)

`backtest/lead_lag_backtest.py` + `src/copy_trading/lead_lag.py` ask a different
question: after a wallet BUYS, does the price move *its way* over the next hours
(informed timing), and how much of that survives a realistic 15-min copy delay
(*capture*)? Measured on the robust TOP-30 (40 most-recent BUYs each, 28-day
window, delay 15m / horizon 4h):

- Strong **dispersion**: per-trade capture ranges from **+43¢** (leads the
  market, 100% hit) down to **−12¢** (fades). Median ≈ 0 (market is efficient
  on average) — so the *ranking* is the value.
- **Copyability is now explicit**: the `lead − capture` gap is the latency tax.
  One wallet had lead +7.5¢ but **capture +0.0¢** — its whole edge vanishes in
  the delay. Outcome-ROI ranking can't see this; lead-lag rejects it correctly.
- **The decisive cross-check**: two wallets that ranked *top by realized ROI*
  (`0xd06c…`, `0xc33a…`) rank near the **bottom** on capture (−12¢, −4¢). Their
  ROI came from holding to resolution, **not** from copyable timing.

**Headline rule: ROI-good ≠ copyable.** Use realized-ROI/t-stat to find skilled
wallets, then **gate on positive delayed-capture** to keep only the ones a real
copier can actually ride. Rank/select on *capture*, not lead, not outcome ROI.

## Automation — continuous discovery (in-bot)

`src/copy_trading/discovery.py` + `discovery_data.py` + `discovery_runner.py`
turn the manual two-stage funnel into an always-on hunter, started as a daemon
thread from `main.py` (gated by `WALLET_DISCOVERY_ENABLED`, default off).

Each sweep (default every 6h): build universe → robust skill score → lead-lag
copyability on the skill pool *plus every wallet already on the watchlist* (so
decay is measurable). A **strict** bar qualifies wallets — capture ≥ 1.5¢/trade
AND t-stat ≥ 10 — with **hysteresis** (stays until capture < 1.0¢) so wallets
near the line don't flap. Then it:

- **writes `data/copy_watchlist.json` atomically** → the paper harness picks the
  wallet up within 120s (auto-paper while you analyze);
- **Telegram-pings each newly-qualified wallet** with its stats + Polymarket
  profile link (one init summary on the first sweep, not a ping storm);
- **auto-removes decayed wallets** from the paper watchlist (configurable);
- persists `data/discovery_state.json` so restarts don't re-ping.

It never places real orders and never edits the live `.env` tiers — promotion to
real capital stays a manual decision after you review the paper PnL. Enable with
`WALLET_DISCOVERY_ENABLED=true` (and `COPY_PAPER_ENABLED=true` to run the ledger);
tune via the `WALLET_DISCOVERY_*` env vars in `config.py`.

## Next step

With discovery + paper running, review the accumulating ledger and graduate a
wallet to small live capital (add to a `STRATEGY_1x_WALLETS` tier) only once its
copied PnL — net of spread/fees/drag — is positive.
