# Conditional market ecology and price response

This follow-up asks what price does **after combinations of observed market activity**. It uses the same 36 million September aggregate trades. September has already been examined; every result here is exploratory and needs replication on a new period. No strategy is promoted.

## Mathematics and observable activity

For horizon h, estimate $E[10^4\log(P_{t+h}/P_t)\mid X_t]$. X includes current signed trade imbalance, lagged imbalance, three-block flow memory, current return, log activity count, log volume and range, plus flow/activity, flow/volume and signed nonlinear flow interactions. Fit a standardized ridge regression with fixed penalty 0.1.

Training uses 1–20 September with labels purged at the boundary. Response comparisons use 21–30 September. Five-, fifteen- and thirty-minute evaluation targets are clock-subsampled to avoid overlapping target intervals. Scaling, thresholds and model fitting use training only. Daily-cluster bootstrap intervals preserve observations within each day. Ten days still give limited regime coverage; comparisons are not corrected for multiple testing.

Strong flow means absolute imbalance above the training 80th percentile (approximately 0.358). High activity means aggregate-trade count above its training 75th percentile. Low current movement means absolute current return below its training 25th percentile. These are anonymous activity measurements, not retail/institution labels. Aggregate-trade count is not raw execution count.

## What price did

Aligned return is positive for movement in the flow direction and negative for reversal. Zero returns count as neither positive continuation nor positive reversal.

| Horizon | Condition | Observations | Mean aligned return, bps | Same-direction frequency | 95% day-cluster interval for mean, bps |
|---|---|---:|---:|---:|---|
| 5 min | strong flow high activity | 117 | -1.36 | 46.2% | [-3.09, -0.06] |
| 5 min | strong flow normal activity | 391 | -0.34 | 48.6% | [-1.22, 0.30] |
| 5 min | strong flow low current move | 66 | 0.26 | 53.0% | [-1.84, 3.22] |
| 15 min | strong flow high activity | 46 | -2.88 | 39.1% | [-8.66, 3.22] |
| 15 min | strong flow normal activity | 123 | -2.04 | 45.5% | [-4.37, -0.34] |
| 15 min | strong flow low current move | 18 | 0.16 | 55.6% | [-4.87, 8.27] |
| 30 min | strong flow high activity | 23 | -11.05 | 34.8% | [-24.69, 2.62] |
| 30 min | strong flow normal activity | 64 | -4.56 | 40.6% | [-12.86, -0.20] |
| 30 min | strong flow low current move | 9 | 3.93 | 66.7% | [-1.91, 15.11] |

Strong-flow/high-activity windows averaged a **1.36 bps reversal over five minutes** across 117 observations. That does not clear the previously assumed 6 bps roundtrip cost. At thirty minutes the same condition averaged an 11.05 bps reversal, but there are only 23 observations across eight days and its interval includes both reversal and continuation. It is a hypothesis for replication, not a reliable entry rule. Low-current-movement flow has particularly small groups and broad intervals; it cannot establish absorption.

## Did the richer mathematical model improve forecasting?

| Horizon | Model MSE, bps² | Constant training-mean MSE, bps² |
|---|---:|---:|
| 5 min | 137.99 | 137.94 |
| 15 min | 408.41 | 408.78 |
| 30 min | 793.93 | 800.00 |

The five-minute model is slightly worse; fifteen- and thirty-minute errors are slightly lower (approximately 0.09% and 0.76%). These small exploratory differences do not establish a profitable model. Returns use last-trade prices, without spread, fills, fees, funding or latency. No causal identification is claimed.

## Research foundation and missing measurements

Cont, Kukanov and Stoikov study order-book-event imbalance and show why depth matters to price impact in their equity sample. This motivates the ecology question, but trade imbalance is not their book-event OFI: September lacks limit additions, reductions and depth. We have not reproduced their full model here. Source: https://arxiv.org/abs/1011.6402

Bouchaud, Farmer and Lillo discuss trade-sign dependence and time-dependent impact. This motivates testing lagged flow and multiple response horizons. Our block regression is an adaptation, not a fitted transaction-level propagator or reproduction of their results. Source: https://arxiv.org/abs/0809.0822

We cannot infer replenishment, cancellations, hidden liquidity, actor identity or GEX from this archive. The next independent study should freeze these conditions and test them on a different month, then add matching L2 to distinguish weak liquidity from replenishment. Do not tune on September and call it untouched validation.

Run `python -m src.simulation.ecology_conditional_response docs/history30/results` after the monthly archive runner. [Machine-readable results](results/conditional_responses.json).
