# Observed ecology environment and frozen baseline

The project now has an executable, receipt-timed observation environment built from the audited L2 state tapes. `ObservedEnvironment.step()` returns the current observation and decision timestamp, without target labels. Historical paths remain fixed: agent actions cannot change them, and this module has no simulated queue fills or trading PnL.

## Information boundary

Observations include received midpoint, quotes, spread, imbalance, depth and changes in the last received bundle. They do not include the next window's liquidity classification, future return or future book state. Input event and availability timestamps pass `gate_inputs`. Labels live in a separate offline record. This is an interface separation, not a security barrier against code deliberately accessing internal evaluation records.

Targets use the first receipt at or after one second, accepting at most 250ms endpoint lag. Any sequence-episode boundary, receipt gap above 250ms or crossed/locked state inside the target interval excludes the example. Decisions are spaced at least one second apart. Sampling lag can still overlap targets; counts below are not independent sample sizes.

## Measured baseline

The first half of the 25 May 00 recording supplies 459 resolved labels. `gate_training` requires label availability no later than the fitting cutoff. The frozen probability of positive return is 11.11%; the empirical 80% interval is −0.350 to +0.137 basis points. Later labels cannot enter this fit.

| Recording | Evaluation examples | Frozen base-rate Brier | 50/50 Brier | 80% interval coverage | Zero-return fraction |
|---|---:|---:|---:|---:|---:|
| 2026-05-25_00 | 458 | 0.0633 | 0.2500 | 88.2% | 84.3% |
| 2026-05-25_04 | 547 | 0.0650 | 0.2500 | 91.6% | 89.9% |
| 2026-05-25_12 | 1120 | 0.0547 | 0.2500 | 91.4% | 90.0% |
| 2026-05-25_18 | 1151 | 0.0292 | 0.2500 | 96.0% | 95.0% |
| 2026-05-26_03 | 1215 | 0.0623 | 0.2500 | 88.1% | 83.9% |
| 2026-05-26_09 | 1153 | 0.0488 | 0.2500 | 91.7% | 89.4% |
| 2026-05-26_15 | 937 | 0.2016 | 0.2500 | 56.9% | 50.6% |
| 2026-05-26_21 | 1551 | 0.0560 | 0.2500 | 91.1% | 88.8% |

The first row evaluates only decisions strictly after the training cutoff. Other rows use the same frozen probability and interval. The baseline is constant: it uses none of the available book features. A score below the 50/50 reference chiefly reflects a low positive-return frequency, including unchanged prices counted as class 0. It is not a directional trading edge, market-making profit or a validated forecast model.

The busy 26 May 15 recording has only 56.9% interval coverage against nominal 80%. Most quieter periods exceed 80%. A single frozen interval is not calibrated uniformly across conditions. Width-sensitive Winkler losses are retained in [full results](OBSERVED_ECOLOGY_ENVIRONMENT_RESULTS.json). No independent uncertainty intervals were estimated for these comparisons.

## What comes next

Compare a fixed, regularized model using only available book features against this frozen base-rate baseline. Preserve fit-time transformations and resolved-label rules. Any feature or parameter chosen after these results is exploratory; all recordings have previously been inspected. New contiguous same-venue days are still required for untouched validation.

Policy evaluation needs an additional explicit execution model with queue uncertainty, latency, fees, inventory/cash accounting and adverse-selection markouts. This observation interface does not claim to supply those. It does not modify the live dashboard or deploy trading orders.

## Reproduce

```python
from src.simulation.observed_ecology_environment import benchmark
benchmark(ordered_state_csv_paths, 'docs/OBSERVED_ECOLOGY_ENVIRONMENT_RESULTS.json')
```

Pass the eight observed-change CSVs with 25 May 00 first; source hashes are in the JSON. Dependencies: numpy and the existing simulation package. Tests check that observations omit labels and are copied, resets reproduce the first decision, target gaps are rejected, and future event timestamps cannot enter observations.
