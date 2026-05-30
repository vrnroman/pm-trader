# Basket / Neg-Risk Arbitrage — Findings (Strategy 3)

_Live depth-aware measurement, May 2026._

## Thesis

In a neg-risk multi-outcome event, exactly one outcome resolves $1. Buying one
share of *every* outcome for < $1 (net of fees) is risk-free profit (realisable
immediately via the neg-risk merge). Symmetrically, selling a complete set for
> $1 is risk-free.

## What a naive probe suggested (and why it was wrong)

A top-of-book probe summing only the legs that *had* quotes showed e.g. "World
Cup Winner: sum of bids = 1.013 → ~1.3% edge." That is an artifact: it ignored
the 12 of 60 legs with **empty books**. You cannot assemble (or unwind) a
complete set if some legs can't be traded, so that 1.3% was never executable.

## Depth-aware measurement (`scripts/basket_arb_scan.py`, walks full books)

Across the 20 most-liquid neg-risk events (liquidity ≥ $2M):

- **0 profitable buy-baskets. 0 profitable sell-baskets.**
- Large events (30–128 legs): essentially all have ≥1 long-tail leg with an
  empty ask (and/or bid) book → the complete basket is **not completable**.
- Small fully-liquid events (2–8 legs) are priced tight:

  | Event | legs | Σ best asks | Σ best bids |
  |---|---|---|---|
  | Fed Decision in June? | 5 | 1.001 | 0.996 |
  | PSG vs. Arsenal | 3 | 1.010 | 0.980 |

  Σasks ≥ 1 (no buy arb) and Σbids ≤ 1 (no sell arb). The ~1–2% gap between
  them is just the bid-ask spread — a cost, not an edge.

## Verdict

**Not a viable edge.** Polymarket's neg-risk mechanism plus incumbent arb bots
keep liquid baskets tight, and illiquid long-tail legs make large baskets
impossible to complete. We are **not** building a basket-arb executor.

The depth-aware edge math (`src/basket_arb/edge.py`, unit tested) and the
scanner are retained as a monitor: if a large event ever develops a transient,
fully-two-sided mispricing, the scanner will surface it (size + persistence).
But it is a watchdog, not a strategy.
