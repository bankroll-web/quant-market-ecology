# October research integration and adaptive liquidity baseline

## Source review

Ten uploaded PDFs were reviewed as extracted text, including two uploads with
the same title and DOI for Cheng et al. Full extracted-text coverage is recorded
in `OCTOBER_RESEARCH_SOURCES.json`. Their binary identity was not checked and
figures were not visually audited. Reported paper performance is not replicated.
Original PDFs are not redistributed in this repository.

| Paper | Useful direction | Fit to this laboratory / limits |
|---|---|---|
| Lin & Sun, Information-Entropic Deep Learning with Gaussian Process Regularisation (10.3390/e28050485) | Predictive distributions, empirical interval coverage, uncertainty-sensitive risk and cost-aware rebalancing | Candidate future uncertainty benchmark. CNN/Transformer/GP/Kelly/CVaR stack not implemented. Asymptotic coverage is not finite-sample coverage under regime changes. Stock results do not establish BTC performance. |
| Cheng, Tseng & Chu, Adaptive LLM-based multi-agent systems (10.7717/peerj-cs.3630; two uploads) | Chronological partitioning, explicit cost/drawdown penalties, component ablations | Daily US equities and semantic factors require point-in-time news/fundamental data. LLM knowledge cutoff and contamination require separate auditing; chronological price splits alone do not exclude text-model leakage. PPO not reproduced. |
| Yuan et al., AlphaCrafter (arXiv:2605.05580) | Separate hypothesis generation, regime screening and constrained execution; record rejected candidates | Daily cross-sectional universes differ from one intraday Bitcoin venue. The agent architecture is a research design candidate, not evidence of our system's alpha. No LLM calls added to the live price loop. |
| Yu et al., LSTM-augmented DQN (10.1038/s41598-026-49159-x) | Partial observability, sequence-state comparisons and reward accounting | Stock sequences and dual moving averages are not our order-flow ecology state. LSTM/DQN must beat simple history-based baselines on identical frozen environments. Not trained or deployed. |
| Zhang, Qwen3:4 Verification of PPO (10.54254/2753-8818/2026.33535) | Action-filter ablation and adverse-result reporting | Paper reports reduced returns after filtering despite technical feasibility. Agent filtering is not assumed beneficial; no filter activated. |
| Poudel & Paudel, Quantitative Trading Strategy, Backtesting, and Performance Analysis (10.3126/qjmss.v7i2.87782) | Cost/risk benchmarks and sensitivity reporting | NEPSE daily RSI/MA/Z-score rule strategy does not match the user's microstructure direction. Those indicators were not imported. |
| Xu et al., Position Management Model | Allocation, cost sensitivity, ARIMA/association-rule baseline ideas | Gold/BTC daily allocation and parameter optimization do not validate intraday maker fills. Low relative price-level error does not establish profitable return forecasts. |
| Gao, Applications of machine learning in quantitative trading | Taxonomy of supervised, recurrent and reinforcement methods | Overview, not a reproducible market-ecology model or standalone empirical validation. |
| Liu, Quantitative Finance and Information Technologies (10.11648/j.eco.20241304.11) | Background and system context | Comparative/regulatory discussion, not an implementable liquidity or pricing model. No current legal conclusions drawn. |

## Implemented next step

The new `src/simulation/adaptive_ecology.py` is an independent simple baseline,
not a reproduction of any uploaded deep-learning or agent model. It tests the
activity drift identified in the preceding calibration audit.

Training rates and state cutoffs use only 25 May 12 UTC. Four methods share the
same corrected observations and verified exposure:

1. Constant training quantity rate.
2. Frozen imbalance/depth conditional rate.
3. Exposure-time EWMA quantity rate.
4. Frozen conditional rate multiplied by the past-only EWMA/global-rate ratio.

The half-life is fixed at 30 verified-exposure seconds before this run; there is
no parameter sweep. For each quantity, after observing interval i:

`a = 1 - exp(-ln(2) * exposure_i / 30)`

`rate_next = (1-a) * rate_previous + a * quantity_i / exposure_i`

Interval i uses the rate available before its outcome is consumed. Episode
changes and discontinuities reset adaptation to the training rate. Hours start
independently. Adaptation time excludes gaps; it is not wall-clock decay or
fitted Hawkes excitation. Current outcome changes cannot change its current
prediction; tests check that boundary and frozen-model immutability.

Observed interval duration is known only at interval end. Expected BTC uses the
past-only rate times retrospective verified exposure. This is an exposure-based
rate diagnostic, not an executable prediction of the next interval's duration
or quantity. No live policy or Coinbase calibration was changed.

## Results and development decision

| Previously inspected later hour | Bid-add state-total error, frozen conditional | Adaptive conditional | Bid-add interval error, frozen conditional | Adaptive conditional |
|---|---:|---:|---:|---:|
| 25 May 18 UTC | 15.29% | 12.70% | 156.4% | 149.2% |
| 26 May 15 UTC | 27.12% | 23.47% | 102.8% | 108.1% |
| 26 May 21 UTC | 153.53% | 104.42% | 246.4% | 205.2% |

Errors are summed absolute BTC discrepancies divided by observed BTC. State-total
error aggregates within each of nine states before taking absolute differences;
interval error takes absolute differences for every update first. Aggregation
can hide event timing errors, so both are reported. Errors can exceed 100%.

In the difficult 26 May 21 recording, adaptive conditional ask-add state-total
error decreases from 260.39% to 169.68%; its bid-add error remains above 100%.
The simpler adaptive constant baseline has lower state-total bid-add error
(65.91%) than adaptive conditional (104.42%). There is no universal winner across
periods or metrics. The improvement does not qualify a trading policy or justify
adding complexity without comparisons.

**Decision: keep all four methods offline and unpromoted.** Next evaluate
observation-quality conditioning and event-count/quantity dispersion separately.
Predictive interval coverage needs an explicit probability model and untouched
venue-consistent contiguous recordings. Reusing these inspected hours cannot
supply independent final validation. Longer history and richer state can then
be compared with recurrent/actor-critic models on the same frozen environments.

## Reproduction

```bash
python -m src.simulation.adaptive_ecology --book-dir data/processed/replay_repaired --out docs/ADAPTIVE_ECOLOGY_RESULTS.json
python -m unittest discover -s tests -p 'test_simulation*.py'
```

Input SHA-256 hashes, episode reset counts and both error metrics are in the
result JSON. Validation: 65 tests passed. No paid services added.
