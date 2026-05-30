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

## Next step

Run `scripts/copy_paper_run.py --loop` over both watchlists through a multi-week
window to accumulate *closed* paper positions. Graduate a wallet to small live
capital only once its copied PnL (net of spread/fees/drag) is positive in our
ledger. Prioritise wallets whose edge is in slow, copyable markets.
