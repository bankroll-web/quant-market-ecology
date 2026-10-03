# Strategy research: first cost-aware comparison

> Replay integrity correction: the 25 May 18 UTC local tape used for these historical numbers was a truncated prefix. See [the correction and rebuilt analysis](OBSERVED_MARKET_MECHANICS.md#replay-integrity-correction). These numbers are preserved for provenance and must not be treated as a completed whole-hour evaluation.


The first experiment selects **no trading**. No model is qualified for live orders or investment decisions. The laboratory is working; profitable trading has not been established.

## Hypothesis and observation boundary

Hypothesis: completed aggressive flow plus the current observed book can forecast the next five-second price response strongly enough to exceed transaction costs. This is an association hypothesis, not a claim about institutional identity or causal dealer behavior.

A decision uses the completed one-second flow window and the exact post-update book at its ending receipt timestamp. Features are signed flow divided by current summed depth within 10 bps, current top imbalance, log total completed flow, completed-window return, current spread in bps and log depth. The decision book must have measured receipt minus event age between zero and 250 ms. Trade flow uses receipt order; no clock offsets are fitted. Old trades within a completed window remain observable, but this does not establish exchange-time causality.

Entry uses the first verified quote at least 100 ms after the decision. Exit uses the first quote at least five seconds after the decision, with at most 250 ms sampling delay at either endpoint. Both endpoints must belong to the decision's verified episode. Each attempted decision reserves its full horizon plus endpoint tolerance; later flow windows cannot overlap that interval. Future endpoint availability does not enter the feature vector. Missing entry/exit counts are reported separately.

These are **small-order quote-based paper proxies**. Longs buy at ask and exit at bid; shorts sell at bid and buy at ask. Neither order size nor executable depth, queue priority, impact or actual fill probability is established. Returns are normalized to entry-side quote notional. No real order is submitted.

## Frozen comparison

- Linear ridge regression: training-only mean/scale, unpenalized intercept, alpha=1.
- Nonlinear RBF kernel ridge: the same training transforms, alpha=1, gamma=1/6. This is supervised machine learning; no deep or reinforcement learning model is claimed.
- Flow-sign rule: trade in the direction of completed signed flow, abstain on zero.
- No-trade benchmark.

Assumed fees are 2 bps per side and extra slippage 0.5 bps per side, for 5 bps round trip in addition to observed spread. These are scenario assumptions, not verified account fees. Learned models trade only if absolute predicted midpoint response exceeds 5 bps. The threshold ignores spread as an additional gate, so it is an optimistic hurdle rather than a complete execution rule. Cost sensitivities subtract 0, 5 and 10 bps from the same quote-crossing returns; they do not refit signals.

Train: 25 May 2026 12 UTC. Validation/selection: 25 May 18 UTC. Later evaluation: 26 May 15 and 21 UTC. All hours have already been inspected in earlier research. This configuration is frozen for reproducibility, not a preregistered experiment or pristine final evaluation. No hyperparameter sweep is performed.

## Observed results

| UTC hour | Role | Resolved samples | Flow-sign trades | Flow-sign mean net bps/trade at assumed 5 bps costs | Ridge trades | Nonlinear trades |
|---|---|---:|---:|---:|---:|---:|
| 25 May 12 | Train | 172 | 159 | -4.930 | 0 | 0 |
| 25 May 18 | Validation | 65 | 50 | -4.890 | 0 | 0 |
| 26 May 15 | Previously inspected later evaluation | 104 | 104 | -4.599 | 0 | 0 |
| 26 May 21 | Previously inspected later evaluation | 229 | 202 | -4.916 | 0 | 0 |

Neither learned model produces predictions that clear the assumed cost threshold. Their zero-trade results are abstention, not evidence of profitable learning. Validation selects no trading; ties are resolved in favor of the first benchmark, no trading.

| UTC hour | Ridge RMSE bps | Nonlinear RMSE bps | Zero-forecast RMSE bps | Missing entry | Missing exit |
|---|---:|---:|---:|---:|---:|
| 25 May 12 | 0.6353 | 0.5914 | 0.7248 | 2 | 43 |
| 25 May 18 | 0.8347 | 0.4933 | 0.4908 | 0 | 16 |
| 26 May 15 | 2.8020 | 2.0123 | 2.0148 | 2 | 51 |
| 26 May 21 | 3.8428 | 0.7874 | 0.7861 | 5 | 53 |

Linear regression generalizes poorly. Nonlinear regression is close to a zero forecast on later samples, with no consistent improvement. This experiment rejects promotion of these candidates; it does not establish that all market strategies are unprofitable.

Scores are conditional on resolvable verified episodes. A trade opened before a missing exit might lose more than the resolved sample suggests; we cannot reconstruct that risk from these tapes. No portfolio Sharpe, significance, compounded return or independent sample-size claim is made. Summed bps and cumulative drawdown in the JSON are equal-unit opportunity diagnostics, not portfolio performance. Funding, margin, liquidation and position sizing are absent.

## Live data preparation

The Kraken observer now subscribes to public BTC/USD trade updates alongside checksum-verified book updates on the same connection. It captures raw trade messages with local receipt timestamps, without replaying historical trade snapshots as new arrivals. UI counters count received messages/events, not unique deduplicated trades or a certified complete tape. Trade IDs, duplicate checks and reconnect gaps must be audited during downstream preparation.

The live simulation still uses synthetic participant arrivals. Captured trade events do not silently replace those assumptions or activate historical models. Historical research uses Binance futures; live capture uses Kraken spot. Cross-venue or cross-product model transfer is not validated.

**Storage limitation:** the free Render instance's local recordings disappear on restart/redeployment. This capture is development instrumentation, not a durable research archive. Continuous calibration needs an authorized persistent archive before a full-day or multi-day research run can be claimed. The public static-server directory must never hold account keys or private trading data.

## Qualification gates and required data

1. Archive at least one complete paired book/trade day on one selected venue; audit timestamps, checksum/gap resets, trade IDs, feed coverage and usable decision times. Then collect additional contiguous training days and later untouched evaluation days across market conditions. A fixed day count alone does not establish adequacy.
2. Specify the actual product, order size, account fees, latency and permitted trading actions. Add funding and liquidation mechanics if futures are selected.
3. Calibrate event arrivals and replenishment from that venue's data; compare inventory-controlled makers with frozen tabular and later actor-critic policies on the same environments. L2 alone cannot certify FIFO fills or participant identity.
4. Keep parameter/model selection inside training/validation periods. Use purged chronological evaluation, day/block uncertainty estimates, cost/latency stress tests and a recorded experiment registry. Previously examined days remain development data.
5. Run a frozen qualified candidate in live paper mode, logging attempted orders, rejected/stale decisions, uncertain fills, inventory, net returns and losses. No-trade remains a benchmark. Promotion requires evidence after costs and explicit limits; it may never qualify.

Measured GEX requires an option chain, volatility surface and signed-position assumptions. Macro bubble and auction models remain separate; adding them without corresponding data would introduce unsupported behavior.

## Reproduce

```bash
python -m src.simulation.strategy_research --flow-dir data/processed/decision_response --book-dir data/processed/replay_states --out data/processed/strategy_research
python -m unittest discover -s tests -p 'test_simulation*.py'
```

Requires NumPy. Upstream tape preparation requires pyarrow and zstandard. The output includes input SHA-256 hashes, audit counts, model transforms/weights, predictions, RMSE and cost sensitivities. [Committed result snapshot](STRATEGY_RESEARCH_RESULTS.json). Related: [timing audit](TIMING_AND_OBSERVATION_AUDIT.md), [earlier regression](RESPONSE_REGRESSION.md), [live laboratory](LIVE_ECOLOGY_LAB.md).

## Extended quantitative study

The [horizon/regime analysis](REGIME_RESEARCH.md) compares 260 fixed candidate/configuration combinations, preserves unresolved-exit diagnostics and tests 5/10 bps cost assumptions. It also selects no trading; it does not promote a policy.
