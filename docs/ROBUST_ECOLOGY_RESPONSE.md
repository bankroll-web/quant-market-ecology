# Robust ecology response: fixed exploratory comparison

Completed 3 October 2026. The known initial-queue extrapolation failure motivated three response normalizations. This experiment compares them with the original fit without removing extreme windows or refitting on evaluation periods. It concerns **contemporaneous explanation**, not future prediction or profitable execution.

## Fixed design and mathematics

The specification is [configs/ecology_response_comparison_v1.json](../configs/ecology_response_comparison_v1.json). It was written after inspecting earlier failures and before running this comparison. Every period has already been inspected; this is an exploratory comparison, not independent validation or a pre-registered discovery on untouched data.

All models train only on the 897 accepted 25 May 00:00 windows, using one transformed feature, train-only centering/scaling, an intercept and ridge alpha=1. The original fit is reproduced numerically against its frozen saved coefficients. No grid search, outcome-based exclusion or model promotion occurs.

Let E be the window's summed best-quote OFI and Q0 its initial average bid/ask best-quote queue. Original pressure is x=E/Q0. Alternatives are:

* **Training-quantile clipping:** clip x to its training 1st and 99th percentiles, then fit the same ridge form. This bounds the input but can discard meaningful extreme distinctions.
* **Asinh compression:** transform x to asinh(x/s), where s is the training pressure standard deviation. This softens extremes while retaining sign; it is not bounded.
* **Window-average depth:** replace Q0 with the received-state, time-weighted average best-quote queue during the observed window. Each received state is held until the next received update. The endpoint state receives zero duration weight.

$$\bar Q=\frac{\sum_{k=i}^{j-1}(t_{k+1}-t_k)(q^B_k+q^A_k)/2}{t_j-t_i},\qquad x_{avg}=E/\bar Q.$$

This average uses within-window observations. It is unavailable at the window's beginning and must not be described as a beginning-of-window forecast feature. It does not recover hidden liquidity, matching-engine event order or identified maker inventory.

## Results: all accepted windows

RMSE is in midpoint basis points. Lower values mean smaller explanatory errors. These are not executable returns. The first row is training; the remaining rows are previously inspected chronological comparison periods.

| Period, UTC | Original linear | Quantile clip | Asinh | Window-average depth |
|---|---:|---:|---:|---:|
| 2026-05-25_00 | 0.2315 | 0.2256 | 0.2265 | 0.2182 |
| 2026-05-25_04 | 0.1293 | 0.1292 | 0.1244 | 0.1147 |
| 2026-05-25_12 | 0.1812 | 0.1680 | 0.1658 | 0.1583 |
| 2026-05-25_18 | 0.0909 | 0.0891 | 0.0855 | 0.0873 |
| 2026-05-26_03 | 1.2607 | 0.2013 | 0.2053 | 0.1653 |
| 2026-05-26_09 | 0.1489 | 0.1188 | 0.1192 | 0.1179 |
| 2026-05-26_15 | 1.5265 | 0.7009 | 0.6878 | 0.6487 |
| 2026-05-26_21 | 0.1820 | 0.1594 | 0.1561 | 0.1453 |

The time-weighted depth alternative improves all-window RMSE in all seven subsequent periods. It is not the lowest-error alternative in every period: asinh is lower at 25 May 18:00. The large 03:00 and 15:00 extrapolation failures are greatly reduced. A repeated improvement in this inspected archive still cannot certify new-day robustness.

## Paired uncertainty and fresh-message sensitivity

The paired difference is original MSE minus time-weighted-depth MSE in squared basis points. Positive means the alternative has lower error. Exploratory 95% intervals use 1,000 one-minute block bootstrap draws on paired window losses; they are not multiple-comparison adjusted and do not describe across-day uncertainty.

| Period | Paired MSE improvement [95% interval] | Fresh original RMSE | Fresh time-weighted-depth RMSE |
|---|---|---:|---:|
| 2026-05-25_00 | 0.00600 [-0.00467, 0.01807] | 0.1916 | 0.1792 |
| 2026-05-25_04 | 0.00355 [-0.00087, 0.00997] | 0.1052 | 0.1049 |
| 2026-05-25_12 | 0.00778 [-0.00032, 0.02019] | 0.1019 | 0.0957 |
| 2026-05-25_18 | 0.00063 [-0.00012, 0.00164] | 0.0661 | 0.0665 |
| 2026-05-26_03 | 1.56204 [0.00542, 4.47862] | 1.3044 | 0.1309 |
| 2026-05-26_09 | 0.00827 [-0.00157, 0.02545] | 0.0904 | 0.0911 |
| 2026-05-26_15 | 1.90930 [0.31616, 4.76819] | 0.4207 | 0.4056 |
| 2026-05-26_21 | 0.01202 [0.00475, 0.02080] | 0.1161 | 0.0929 |

Among the seven comparison periods, only three paired intervals exclude zero on the positive side: 26 May 03:00, 15:00 and 21:00. Under the freshness subset, time-weighted depth is slightly worse at 25 May 18:00 and 26 May 09:00. The improvement is therefore not uniform across subsets or established in every period with uncertainty taken into account.

## Interpretation for the machinery

A tiny starting queue is an unstable denominator for a whole window of evolving flow and displayed liquidity. Averaging observed depth reduces that particular failure in this archive. However, depth and quote changes are endogenous, and the alternative is a same-window statistic. It is a candidate calibration diagnostic, not a standalone price generator, causal impact estimate or trading policy.

The original OFI statistic includes price-changing quotes. An explanatory R² can be high partly because quote formation and the response share information. Better contemporaneous fit does not prove tradable continuation, net profitability, actor identification or a complete simulator. The original observation exclusions and frozen replication remain unchanged.

## Evidence and reproduction

Complete thresholds, coefficients, RMSE/R², maximum fitted moves, error concentration, paired intervals and input hashes: [ROBUST_ECOLOGY_RESPONSE_RESULTS.json](ROBUST_ECOLOGY_RESPONSE_RESULTS.json). The new comparison is separate from the frozen original study. Proposed acceptance stages and data requirements: [MARKET_ECOLOGY_ROADMAP.md](MARKET_ECOLOGY_ROADMAP.md).

```bash
python -m src.simulation.robust_ecology_response --baseline docs/price_mechanics/summary.json --spec configs/ecology_response_comparison_v1.json --base-windows data/processed/ecology_price_mechanics --replication-windows data/processed/mechanics_replication --base-states data/processed/mechanics_study_states --replication-states data/processed/mechanics_replication_states --out data/processed/robust_ecology_response
python tools/report_robust_ecology_response.py --source data/processed/robust_ecology_response/report.json --destination docs/ROBUST_ECOLOGY_RESPONSE.md
python -m unittest discover -s tests -p 'test_simulation*.py'
```

Reconstruct the source tapes and accepted windows using the two preceding study guides first. Dependencies: numpy, pyarrow and zstandard. Tests check time weighting, endpoint exclusion, episode boundaries, clipping versus soft compression, and evaluation without model mutation. The original model must reproduce the frozen baseline before scoring alternatives.

