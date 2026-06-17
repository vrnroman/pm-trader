# Will this make money? — honest analysis

_Synthesis after building the theory framework, exit-following copy, and the
calibration backtest (incl. a slippage sweep). Read with THEORY_FINDINGS.md and
COPY_TRADING_FINDINGS.md._

## What we can now say with evidence

1. **Selection has a real, robust *relative* edge.** Wallets flagged by 1g
   (category specialist), 1b (consistent skill, t-stat≈3), 1f (early-exit swing)
   and 1i (low-variance whale) beat the population of all copy bets by +0.10 to
   +0.45 ROI/$ at 80–85% hit. Crucially, the slippage sweep shows this edge is
   **robust to execution drag** — at 500 bps (5%) of slippage on entry *and*
   exit, 1g still nets +0.62 ROI/$ (vs pop +0.40) and 1b +0.49 (vs pop +0.27).
   The relative ranking barely moves because flagged and baseline pay the same
   drag. That is the single most encouraging finding.

2. **Exit-following matters and works.** Modelling the target's early sells (not
   holding to resolution) is now in both the backtest and the live copy engine.
   Many of the best wallets (1f) are swing traders; scoring them on round-trips
   is what surfaces them.

3. **Some hypotheses are dead.** 1a (news/geo early insider) has *negative* edge
   and its hit rate craters under slippage (70%→29%) — independently
   reconfirming INSIDER_FINDINGS. It's off by default. 1j (fresh sniper) is n=3
   variance. The old `min_tstat=10` absolute gate flagged **nobody** — a latent
   bug that would have made the live funnel find ~nothing.

## Why this is NOT yet "yes, it makes money"

The numbers above are **optimistic by construction**, and three gaps stand
between them and real PnL:

1. **Fill rate is unmodelled — the biggest hole.** The backtest haircuts the
   *price* for slippage but assumes every copyable-band BUY is *fillable*.
   COPY_TRADING_FINDINGS measured real fill rates of **7–30%** (in-play sports
   move past us before we can follow; slow politics/research ~4× more copyable).
   We capture ROI on bets we could copy — we don't penalise the ones we can't
   enter at all. Net edge depends heavily on *which* bets survive to a fill.

2. **The absolute ROI is inflated.** Survivorship (the universe is
   currently-active winners) lifts the baseline; resolution-payoff asymmetry
   (a winning $0.20 longshot pays +4.0/$) fattens the mean. Trust the *spread*
   (vsPop) and the *hit rate*, not the headline +0.5.

3. **One window, one universe.** Thresholds were calibrated on a single 30-day
   forward window on a recent universe. That risks overfitting; 1e/1a couldn't
   be tested at all (only 8% of these recent markets have resolved).

## What's needed next (in priority order)

1. **The live paper ledger, net of execution — the gating test.** We have
   `copy_paper` with exit-following now. Run it on the theory-flagged wallets,
   entering at the price we could *actually* get (best ask + slippage at our
   detection latency) and **recording skipped/unfillable signals**. Positive
   realised PnL net of drag, per theory and per segment, is the green light for
   real capital. Nothing else should gate ahead of this.

2. **Model fill rate / latency in the backtest** — drop bets whose price had
   already moved past a copier reacting N minutes late (use the CLOB
   price-history we already fetch for lead-lag). This converts the optimistic
   copy-ROI into an expected *capturable* ROI.

3. **Route by copyability, not raw ROI.** The edge that survives is in slow
   markets. Weight/route theory flags toward segments with high historical fill
   rates (politics/research), de-weight in-play sports.

4. **Walk-forward calibration** across several cutoffs (as the 1b backtest
   already does for the validated path) to de-risk overfitting; pull an older,
   resolution-rich universe to finally test 1e (longshot calibration) and 1a.

## A strategic option worth considering

If 1e (longshot calibration) or 1g (category mispricing) reflect a *real market
inefficiency* rather than a specific trader's skill, the higher-EV move may be
to **trade the inefficiency directly** rather than copy wallets — direct trading
has no copy latency and no adverse selection (the two biggest drags above).
Copy-trading inherits the target's edge *minus* execution lag; a direct
calibration/mispricing strategy keeps the edge and pays only our own spread.
Worth a small research spike alongside the paper ledger.

## Bottom line

The discovery system is a genuinely good **funnel**: it surfaces wallets with a
real, drag-robust *relative* edge and explains why (per-theory reasons + an
optional Claude verdict). But "does copying them net money after costs" is
**still unproven**, and the honest gating experiment is the **execution-aware
paper ledger**. Build that next; treat everything here as the candidate-
generation layer feeding it, not as a profit guarantee.
