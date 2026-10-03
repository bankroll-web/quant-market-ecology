# First chronological price-response regression

This experimental module estimates the next one-second midpoint return from observed aggressive flow and starting liquidity. It does not submit orders or change simulated participant behavior. Options pricing remains a future component; Black–76, Heston and Bates have not been added by this change.

## Fixed experiment

- Train separately on the all-message and fresh-250-ms samples from 25 May 2026, 12 UTC. Evaluate unchanged on 25 May 18 UTC and 26 May 15/21 UTC. These hours were already inspected in earlier diagnostics: they are chronologically held out from this fit, not a pristine independent research sample.
- Target: `forward_1s_return_bps`, measured from the end of the flow window inside the same verified book episode. No 1-BTC cutoff is used; zero and small flows remain.
- Features: signed aggressive BTC divided by initial summed bid/ask depth within 10 bps, initial top-of-book imbalance, and `log(1 + total aggressive BTC)`. Initial book observations join by exact receipt timestamp and episode.
- Standardize using training means and population standard deviations only. Zero-variance features use scale one. Fit an unpenalized intercept and ridge slopes with fixed penalty alpha=1; no hyperparameter search or test-hour refitting.
- After retaining a row, skip starts before its flow end plus 1.25 seconds. This conservatively separates the next feature window from the preceding one-second label and its permitted 250-ms endpoint tolerance. It does not make rows statistically independent.
- Compare root mean squared error (RMSE) with a zero-return forecast and a constant training-mean forecast. Lower RMSE is better.

For standardized feature vector z, solve `beta = (Z.T Z + I)^(-1) Z.T (y - mean(y))`; prediction is `mean(y) + z beta`. Implemented with a linear solve, not an explicit matrix inverse.

## Results

| Sample | UTC hour | Role | Rows | Model RMSE bps | Zero RMSE bps | Training-mean RMSE bps | Improvement vs zero |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| all_messages | 2026-05-25 12 | training | 463 | 0.3270 | 0.3577 | 0.3574 | +8.58% |
| all_messages | 2026-05-25 18 | held_out | 497 | 0.1879 | 0.1758 | 0.1767 | -6.88% |
| all_messages | 2026-05-26 15 | held_out | 407 | 1.1019 | 1.0996 | 1.0994 | -0.21% |
| all_messages | 2026-05-26 21 | held_out | 608 | 0.3157 | 0.3006 | 0.3007 | -5.02% |
| fresh_250ms | 2026-05-25 12 | training | 307 | 0.1641 | 0.1699 | 0.1699 | +3.44% |
| fresh_250ms | 2026-05-25 18 | held_out | 330 | 0.1361 | 0.1383 | 0.1383 | +1.55% |
| fresh_250ms | 2026-05-26 15 | held_out | 109 | 0.3607 | 0.3678 | 0.3678 | +1.94% |
| fresh_250ms | 2026-05-26 21 | held_out | 395 | 0.2168 | 0.2164 | 0.2164 | -0.20% |

**Decision:** all-message forecasts lost to zero on all three later hours. The freshness-filtered model improved slightly on two and lost on one. Do not promote this model into trading or maker behavior. Training error improvement is not validation.

## Interpretation limits

The freshness filter examines the full future book path used by the label. Its sample membership is known retrospectively, so fresh-sample scores are a data-quality sensitivity diagnostic, not a deployable forecast policy. Receipt/exchange clock alignment remains unresolved. Observed book pre-update states are timestamped at message receipt; they are approximate observation times rather than exact exchange-state availability.

Four selected hours over two days cannot establish robustness. No significance, confidence interval, causal-impact, executable-profit or cross-venue claim is made. Spread, slippage, fees and execution latency are absent from these midpoint-return scores. Results are conditional on valid book episodes and complete horizons. Adjacent retained observations can still be dependent.

## Reproduce

Requires NumPy plus the upstream flow CSVs and observed-change tapes. Raw-data preparation also requires pyarrow and zstandard. Run from the repository root:

```bash
python -m src.simulation.response_regression --flow-dir data/processed/flow_response_v2 --changes-dir data/processed/replay_states --out data/processed/regression_baseline
python -m unittest discover -s tests -p 'test_simulation*.py'
```

If the change tapes are stored under `book_changes_new`, pass that folder instead. Output `report.json` stores training transforms, coefficients, sample definitions and SHA-256 input hashes; `predictions.csv` stores row-level fitted/predicted and observed returns. This committed [result snapshot](RESPONSE_REGRESSION_RESULTS.json) preserves the current run. The [visual report](RESPONSE_REGRESSION_CHART.html) shows later-hour errors without requiring JavaScript.

## Next development

Audit exchange-time/receipt-time alignment and book/trade delays, then obtain additional contiguous days. Any revised features, selection rules or penalty need a new independent evaluation period. Keep the current baseline frozen for comparison.

Related: [flow timing study](REAL_FLOW_PRICE_RESPONSE.md), [historical replay](HISTORICAL_MARKET_REPLAY.md), [simulation laboratory](MARKET_ECOLOGY_SIMULATION.md).
