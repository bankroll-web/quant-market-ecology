# Robust expected-return model comparison

Exploratory follow-up to the regression extrapolation failure. Same 459 first-half-hour training examples and 8,132 previously inspected evaluation examples. This method was chosen after examining the original failures, so it is not independent validation. No live model replacement or strategy promotion.

## Method

Transform the OFI/depth feature with inverse hyperbolic sine, center features using training medians, scale by training interquartile ranges, and clip normalized values to ±5. Fit Huber residual loss with fixed training-derived delta (1.345 × 1.4826 × target median absolute deviation, floor 0.01 bps) plus ridge penalty 0.1. Iteratively reweighted least squares performs at most 100 updates. Zero feature IQR uses scale 1.

This is our fixed-scale Huber/ridge implementation, not scikit-learn HuberRegressor, which jointly estimates a scale. The official documentation explains Huber loss and its lower influence on outliers: https://scikit-learn.org/stable/modules/linear_model.html#huber-regression

## Results

| Recording | Examples | Feature-clipped rows | Robust MSE | Zero-return MSE |
|---|---:|---:|---:|---:|
| 2026-05-25_00 | 458 | 165 | 0.135316 | 0.135664 |
| 2026-05-25_04 | 547 | 149 | 0.039334 | 0.039529 |
| 2026-05-25_12 | 1120 | 420 | 0.075734 | 0.075988 |
| 2026-05-25_18 | 1151 | 1151 | 0.024681 | 0.024796 |
| 2026-05-26_15 | 937 | 920 | 1.000269 | 1.001497 |
| 2026-05-26_21 | 1551 | 1551 | 0.068343 | 0.068605 |
| 2026-05-26_03 | 1215 | 1215 | 0.113767 | 0.114088 |
| 2026-05-26_09 | 1153 | 1153 | 0.052183 | 0.052378 |

The robust model no longer generated extreme forecasts; the largest absolute estimate was about **0.008 bps**. It slightly beat the zero-return MSE baseline in all eight development comparisons, but predictions are almost zero and the improvements are small. This is closer to a stable near-zero forecast than a useful trading edge. Every recording had **zero 8 bps threshold crossings**.

Large fractions of later-hour features required clipping, sometimes all rows. Numerical stability does not make those inputs statistically supported. Clipped states would still require rejection or independent validation before trading; clipping must not be used to bypass the live training-support guard. Target labels may overlap by up to 250 ms, and comparisons have no dependence-aware significance test or multiple-search correction.

Three targeted checks passed: a planted relationship positive control, a constant-feature extreme-target case, and extreme-feature reporting with finite predictions. These demonstrate implementation behaviour, not market profitability.

Run `python -m src.simulation.robust_paper_benchmark .` and `python -m unittest tests.test_simulation_robust_paper`. [Machine-readable model and results](ROBUST_PAPER_BENCHMARK.json).
