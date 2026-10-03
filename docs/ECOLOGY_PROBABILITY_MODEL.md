# Fixed regularized book-feature probability model

A ridge-logistic model now predicts whether the next approximately one-second midpoint return is strictly positive. Zero returns are class 0. It is trained on the same 459 resolved first-half 25 May 00 labels as the frozen baseline. Source hashes must match the baseline; fit transforms and coefficients use no later labels.

Five features: top imbalance, combined-depth imbalance, log depth, spread in basis points, and the last received bundle's best-quote OFI divided by current combined depth. No completed future-window features enter the observations. Standardization uses training means and standard deviations. Ridge penalty is fixed at 0.1 on coefficients, with unpenalized intercept; Newton iterations stop at a preset tolerance. No parameter search was performed.

| Recording | Model Brier | Baseline Brier | Difference (negative improves) |
|---|---:|---:|---:|
| 2026-05-25_00 | 0.0594 | 0.0633 | -0.0039 |
| 2026-05-25_04 | 0.0609 | 0.0650 | -0.0041 |
| 2026-05-25_12 | 0.0598 | 0.0547 | +0.0051 |
| 2026-05-25_18 | 0.0764 | 0.0292 | +0.0471 |
| 2026-05-26_03 | 0.0585 | 0.0623 | -0.0038 |
| 2026-05-26_09 | 0.0421 | 0.0488 | -0.0067 |
| 2026-05-26_15 | 0.2109 | 0.2016 | +0.0093 |
| 2026-05-26_21 | 0.0534 | 0.0560 | -0.0025 |

Five of eight comparisons improve in point-estimate Brier loss; three worsen. Among the seven later hours, four improve and three worsen. The model is not consistently superior. The 25 May 18 deterioration is substantial. No significance test or independent confidence interval was calculated; sample counts are not independent counts because target endpoint lag can overlap outcomes.

This is an exploratory development comparison on previously inspected recordings, not untouched validation. Low positive-return frequency can dominate these binary scores. Better probability scoring does not establish profitable trades after spreads, latency and fees. The 80% return intervals remain the unchanged baseline intervals; this model does not fix interval calibration.

The code, training transforms, weights and all comparison scores are in [results](ECOLOGY_PROBABILITY_MODEL_RESULTS.json). Tests verify constant-feature predictions match the base rate, probability responds to a synthetic signal, and evaluation does not refit stored transforms. No live strategy is deployed.

Next: distinguish the probability that price moves at all from its direction conditional on moving, and compare regime-sensitive uncertainty with the same frozen baselines. Any new model choice following these results remains exploratory. Preserve new contiguous recordings for validation before selecting policies.

Reproduce with `ecology_probability_model.benchmark(ordered_state_csv_paths, baseline_json_path, output_json_path)`, passing the original training hour first. Requires numpy and the existing simulation package.
