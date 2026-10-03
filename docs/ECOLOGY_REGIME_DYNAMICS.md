# Observed ecology regime dynamics

Completed 3 October 2026. This benchmark measures how the accepted observed liquidity/pressure labels follow one another. It adds empirical transition and persistence checks for future simulator validation; it does not establish a validated simulator or profitable policy.

## Definitions and continuity

The pressure cutoff is frozen from 25 May 00:00. Labels are no signed net flow, lower pressure, high pressure with reinforcing displayed liquidity, high pressure with opposing displayed liquidity, and high pressure with exactly neutral displayed pressure. No signed net flow may include trades that balance each other; it does not mean no trading activity. Reinforcement/opposition is relative to the current window's aggressive trade direction, so a state persisting does not imply persistent buying or selling.

A transition exists only if one accepted window ends exactly when the next accepted window starts and both are in the same reconstructed episode. Removing an invalid, missing-trade or stale window therefore breaks continuity. No transition crosses a recording boundary. Of the 8,300 accepted windows, **6,539 adjacent transitions** qualify; **1,753 within-recording adjacent boundaries** are excluded. These are selected discontinuous segments from the same inspected two-day archive.

| Period, UTC | Valid transitions | Excluded boundaries | Contiguous segments |
|---|---:|---:|---:|
| 2026-05-25_00 | 729 | 167 | 168 |
| 2026-05-25_04 | 461 | 69 | 70 |
| 2026-05-25_12 | 816 | 277 | 278 |
| 2026-05-25_18 | 847 | 292 | 293 |
| 2026-05-26_03 | 1066 | 106 | 107 |
| 2026-05-26_09 | 922 | 193 | 194 |
| 2026-05-26_15 | 560 | 314 | 315 |
| 2026-05-26_21 | 1138 | 335 | 336 |

## Observed runs and censoring

A run ends at a change of label or an observation boundary. Runs touching the beginning or end of a contiguous segment are censored. Their observed lengths are not complete lifetimes. The table reports medians of observed run lengths including boundary-censored runs; it must not be interpreted as a population duration estimate or subsecond event timing.

| Period | Median lower-pressure run, observed seconds | Median high/reinforcing run | Median high/opposing run | Completed high/reinforcing runs |
|---|---:|---:|---:|---:|
| 2026-05-25_00 | 2.016 | 1.016 | 1.012 | 72 |
| 2026-05-25_04 | 2.040 | 1.014 | 1.015 | 34 |
| 2026-05-25_12 | 2.018 | 1.012 | 1.015 | 49 |
| 2026-05-25_18 | 2.019 | 1.020 | 1.017 | 34 |
| 2026-05-26_03 | 2.042 | 1.016 | 1.015 | 106 |
| 2026-05-26_09 | 2.025 | 1.016 | 1.010 | 63 |
| 2026-05-26_15 | 1.019 | 1.024 | 1.017 | 79 |
| 2026-05-26_21 | 2.020 | 1.014 | 1.018 | 80 |

High-pressure labels generally have one-window observed median runs; lower-pressure runs are generally closer to two windows, except the busy 15:00 recording. This describes aggregate labels at approximately one-second resolution. It does not show that real pressure episodes last exactly one second, and repeated missing observations can shorten recorded runs.

## Frozen transition diagnostic

Two categorical benchmarks train only on valid adjacent transitions in 25 May 00:00:

* A first-order transition model conditions the next label on the previous label. Each transition cell receives a fixed 0.5 pseudocount.
* An IID model uses the marginal destination-label frequencies of those same training transitions, also with 0.5 pseudocounts. It ignores the previous label.

The conditional probability is P(j|i)=(Nij+0.5)/(sum_j Nij+5×0.5). This is a smoothed statistical benchmark, not proof that market states obey a Markov law. Neutral high pressure is never observed in these recordings; the smoothing nevertheless gives it prior probability. An unobserved source state's uniform row is entirely prior-generated and must not be represented as measured market behaviour.

Log loss is minus log2 of the assigned probability of the observed next label. Lower is better. Positive IID-minus-transition loss means the transition model is better. The paired intervals use 1,000 one-minute block-bootstrap draws, are exploratory and are not multiple-comparison adjusted.

| Period | Conditional log loss, bits | IID log loss, bits | IID minus conditional [95% interval] |
|---|---:|---:|---|
| 2026-05-25_00 | 1.2492 | 1.2523 | 0.00310 [-0.00258, 0.00957] |
| 2026-05-25_04 | 1.3314 | 1.3228 | -0.00855 [-0.02328, 0.00423] |
| 2026-05-25_12 | 1.0287 | 1.0217 | -0.00695 [-0.01468, -0.00002] |
| 2026-05-25_18 | 1.2919 | 1.3102 | 0.01822 [0.00990, 0.02669] |
| 2026-05-26_03 | 1.1582 | 1.1523 | -0.00592 [-0.01064, -0.00073] |
| 2026-05-26_09 | 1.2596 | 1.2678 | 0.00819 [0.00000, 0.01638] |
| 2026-05-26_15 | 2.3423 | 2.3316 | -0.01074 [-0.03346, 0.01010] |
| 2026-05-26_21 | 1.3338 | 1.3322 | -0.00156 [-0.00921, 0.00576] |

The conditional benchmark has lower point-estimate loss in only two of the seven comparison periods. Some intervals barely exclude zero and should not be elevated into strong discovery claims. There is no consistent advantage over the IID benchmark. The 15:00 distribution differs markedly from the training period, and both frozen benchmarks have much higher loss there. These results argue against treating a stationary first-order transition matrix as a validated event environment.

## Consequence for simulator development

A simulator can now be checked against the empirical transition counts, occupancy proportions, run-segment distributions, boundary-censoring rates and unchanged-price fractions. The benchmark keeps missing intervals from being mistaken for state persistence or transitions. It does not supply queue-event arrival intensities, participant identity, causal interventions, complete run-lifetime estimates or forward price alpha.

The conditional benchmark remains diagnostic. A richer semi-Markov, event-intensity or history-aware hypothesis would require a separate specification and evaluation, including additional contiguous same-venue days. Neither adding complexity nor replaying this archive creates independent validation. The live observer's synthetic participant roles remain assumptions.

Full transition counts, smoothed training probabilities, per-state run counts and freshness sensitivity: [ECOLOGY_REGIME_DYNAMICS_RESULTS.json](ECOLOGY_REGIME_DYNAMICS_RESULTS.json). Development gates: [MARKET_ECOLOGY_ROADMAP.md](MARKET_ECOLOGY_ROADMAP.md).

## Reproduce

```bash
python -m src.simulation.ecology_regime_dynamics --baseline docs/price_mechanics/summary.json --base-windows data/processed/ecology_price_mechanics --replication-windows data/processed/mechanics_replication --out data/processed/ecology_regime_dynamics
python tools/report_ecology_regime_dynamics.py --source data/processed/ecology_regime_dynamics/report.json --out docs/ECOLOGY_REGIME_DYNAMICS.md
python -m unittest discover -s tests -p 'test_simulation*.py'
```

Dependencies and accepted-window reconstruction are documented in the preceding ecology studies. Tests verify sign-relative labels, gap/episode boundaries, run censoring and smoothed-row normalization. No real-money or live-policy operation was enabled.

