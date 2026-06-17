# Strategy Theories — Calibration Findings (1a..1j)

_Out-of-sample backtest, 400-wallet recent universe, 30-day forward window,
exit-following copy-PnL. `backtest/theory_backtest.py`, run 1 recorded in
`theory_calibration_run1.txt`._

## Design

The discovery funnel moved from a single AND-gate to a registry of **independent
detector theories** (`theories.py`), OR'd: a wallet graduates if *any* theory
flags it, tagged with which one and why. Each theory is one hypothesis with its
own backtest-calibrated thresholds. Features are extracted once per wallet into a
`WalletContext` (closed results, resolution-enriched buys, **round-trips** for
early exits, entry profile, PnL curve, lead-lag scalars).

## Method

Split each wallet's `/activity` at a cutoff: lookback (≤ cutoff) builds the
context and runs the detectors; forward (> cutoff) measures what copying it would
have earned. **Forward copy-PnL follows the target's exits** — a copied BUY is
closed at the wallet's later SELL price, falling back to the resolution payoff
only if they held to settlement. Edge is reported vs the population of all
forward copy bets.

## Results (run 1)

Population copy-ROI/$ = **+0.346** (n=13,341) — note this baseline is high and
**survivorship-/payoff-inflated**: the universe is currently-active large-stake
wallets, and forward ROI counts asymmetric resolution payoffs (a winning $0.20
longshot pays +4.0). Treat the **relative edge (vsPop)** as the trustworthy
signal, not the absolute number.

| Theory | best variant | flagged/day | copy-ROI | hit% | vs pop |
|--------|-------------|------------:|---------:|-----:|-------:|
| **1g category specialist** | roi≥0.30 | 0.5 | +0.79 | 85% | **+0.45** |
| **1b consistent skill** | t-stat≥3 | 0.9 | +0.64 | 85% | **+0.30** |
| **1f early-exit swing** | win≥0.60 | 1.8 | +0.55 | 84% | **+0.20** |
| **1i low-variance whale** | default | 1.3 | +0.45 | 80% | **+0.11** |
| 1a news/geo early insider | default | 0.9 | +0.16 | 70% | **−0.19** |
| 1j fresh-account sniper | bet≥$5k | 0.1 | +3.19 | 84% | +2.85 (n=3) |
| 1c, 1d, 1e, 1h | — | 0 | — | — | — |

## Read-out

- **Winners (enable live): 1g, 1b, 1f, 1i.** All beat a survivorship-inflated
  baseline at sane flag rates and 80–85% hit. 1g (category specialist) and 1b
  (consistent skill) are the strongest.
- **The `min_tstat=10` gate was miscalibrated.** At 10, theory 1b — and by
  extension the old AND-funnel — flagged **zero** wallets in this universe; at
  t-stat≈3 it's the second-best signal. The validated COPY_TRADING_FINDINGS used
  t-stat to *rank* top-K, not as an absolute cutoff; as an absolute gate, 3 is
  the productive threshold. **Default lowered 10 → 3.**
- **1a (news/geo early insider) has negative edge** — independently reconfirms
  INSIDER_FINDINGS that geo-early shape isn't a copyable edge. **Disabled by
  default**, kept available.
- **1j (fresh sniper)** shows a huge ROI on n=3 — pure variance (a couple of
  longshot wins). **Disabled by default.**
- **1c, 1d, 1h fired zero only because the backtest doesn't run the live
  lead-lag (capture) or PnL-curve stages** — diagnostics confirm 0 ctxs had
  capture/curve data. They fire **live** (where those stages run); 1c is already
  validated by COPY_TRADING_FINDINGS. 
- **1e (longshot calibration) is starved**: only 8% (4,243/52,861) of the markets
  this recent universe touched have resolved, so no wallet had ≥8 resolved
  longshot buys. Validating 1e/1a properly needs an **older, resolution-rich
  universe** — a follow-up (the `/trades` feed is recent-only, so it needs a
  market-iterating historical source).

## Caveats (do not over-fit)

One 30-day window on one recent, survivorship-biased universe. The copy-ROI
numbers are **gross** — no spread, slippage, latency, or fill-rate drag, and
inflated by resolution payoffs. COPY_TRADING_FINDINGS already showed real fill
rates of 7–30% (in-play sports largely uncopyable). The **relative ranking** of
theories is the durable output; **absolute profitability is decided by the live
paper ledger net of execution** — unchanged as the gating test before real
capital.
