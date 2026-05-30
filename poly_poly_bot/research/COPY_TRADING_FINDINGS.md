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

## Next step

Forward paper-copy harness: track the watchlist wallets live, simulate copies
at realistic entry prices, and accumulate realized out-of-sample PnL. Graduate a
wallet to small live capital only once its *copied* PnL (net of spread/fees) is
positive in our own ledger.
