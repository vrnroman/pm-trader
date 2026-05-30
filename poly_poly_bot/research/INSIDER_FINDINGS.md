# Insider Trade-Shape Following — Findings (Strategy 1a)

_Backtest on archived on-chain trades + resolved geo markets, May 2026._

## Thesis

A large, concentrated bet from a young / first-time account on a
news/geopolitical market is an informed-trader (insider) fingerprint; copying it
and holding to resolution should be profitable. The signal is the *shape* of the
trade, independent of the trader's track record (which is Strategy 1b).

## Method

`backtest/insider_backtest.py`: for ~50–60 resolved geopolitical markets, pull
every large BUY (`/trades?market=...`), reconstruct the trader's account age (#
prior trades at the moment of the bet via `/activity`), flag the insider shape
(`is_insider_shaped`: geo + ≥ $1k + ≤ 5 prior trades), simulate copy PnL to
resolution, and compare to controls with Wilson 95% CIs. EV is measured per $1
staked relative to entry price, so an efficient market gives EV ≈ 0.

## Results

**Without a timing control (all large geo BUYs):**

| Group | n | EV / $ | Hit rate (95% CI) |
|---|---|---|---|
| Insider-shaped (young+large+geo) | 230 | +0.11 | 64% (58–70%) |
| Veteran large (control) | 71 | +0.50 | **97% (90–99%)** |
| All large geo BUYs | 301 | +0.20 | 72% (67–77%) |

This is the **opposite** of the thesis — veterans crush young accounts — and the
97% veteran hit-rate is the tell: it is **settlement-lag scooping**, not
insider edge. `/trades` is newest-first and geo-market volume is concentrated
near resolution, so this sample is dominated by people buying a near-certain
$1 outcome for < $1 in the final hours. Real but zero-capacity and not copyable.

**With a timing control (only bets > 24h before resolution, deep-paged to reach
early trades):**

- **134 of 137** large geo bets were placed within 24h of resolution.
- Only **3** were genuinely early — too few for any statistical power
  (insider-shaped n=1).

## Verdict

**Not a provable / copyable edge.** Two independent reasons:

1. Large geopolitical bets are overwhelmingly placed *near resolution* (~98%
   within 24h). Genuine early informed positioning is vanishingly rare, so
   there is nothing to copy at scale.
2. In the late-dominated flow that does exist, the naive insider shape
   (young + large) *underperforms* experienced traders; the apparent profit is
   settlement-lag arbitrage, which is capacity-zero and not actionable for a
   copy bot reacting after the fact.

This stands in deliberate contrast to **Strategy 1b**
(`research/COPY_TRADING_FINDINGS.md`), where ranking wallets by realized
closed-position ROI *does* show robust out-of-sample edge. Effort should go to
1b's forward validation, not 1a.

The backtest and the `is_insider_shaped` signal are retained: the existing live
`pattern_detector` (alert-only) can still surface the rare early-insider shape
for manual review, and the backtest can be re-run on future regimes (e.g. a
spike in true insider activity) to re-test the thesis.
