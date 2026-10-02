# Where the ecology calibration fails

The nine-state model conditions on pre-update top imbalance and visible depth.
Rates, depth cutoffs and the 30-second shrinkage prior remain fitted solely on
25 May 2026 12 UTC. Later hours have already been inspected and are diagnostic
periods, not untouched final tests. Inputs are the corrected reconstruction tapes.

## Results in plain language

| Later recording (UTC) | Conditional count likelihood improvement | State-total quantity error: bid additions | Ask additions |
|---|---:|---:|---:|
| 25 May 18 | +1.26% | 15.29% | 31.31% |
| 26 May 15 | +4.22% | 27.12% | 22.08% |
| 26 May 21 | −2.94% | 153.53% | 260.39% |

Positive likelihood improvement means the conditional count model beats a
constant training-rate baseline on that diagnostic. It does not measure trading
accuracy or profitability. Quantity error sums absolute predicted-versus-observed
BTC differences across the nine state totals, divided by observed BTC. It is not
an interval forecast score; aggregation can hide timing errors.

For 26 May 21, even the constant model has large errors (about 107% for bid
additions and 178% for ask additions). Conditioning on imbalance and depth makes
those errors worse. Across all four addition/removal quantities, conditional
state-total errors range from 128.90% to 260.39%. The training activity scale
therefore fails to transfer reliably to this recording. These diagnostics do
not establish the cause: a changed activity regime, capture differences and
verified-episode censoring remain possible contributors.

## New audit output

`ECOLOGY_CALIBRATION_RESULTS.json` now reports each state's:

- Later-period verified exposure and interval count.
- Training exposure and shrinkage-prior weight, identifying weakly supported states.
- Observed BTC, conditional expected BTC, constant expected BTC and signed bias.
- Aggregate state-total quantity error against both baselines.

The diagnostics do not refit the model or tune it on later recordings. Input
hashes remain in the report. Unit tests verify quantity/exposure conservation
and that scoring does not change the frozen model.

## Development decision

Keep this model offline and unpromoted. Synthetic arrivals in the live
laboratory remain explicitly assumed. No maker identities, individual queue
fills, hidden liquidity, psychological states or measured dealer gamma are
inferred from these anonymous L2 observations.

Next research should distinguish observation-quality changes from activity
changes, then evaluate a causal adaptive activity-rate baseline against this
frozen baseline on contiguous, venue-consistent recordings. Adaptation must use
only completed past intervals, reset at gaps, and be scored on subsequent
intervals. Final performance needs fresh untouched periods; repeatedly improving
these inspected hours cannot supply that evidence. Historical Binance futures
and live Coinbase spot calibration must remain separate.

Reproduce:

```bash
python -m src.simulation.ecology_calibration --book-dir data/processed/replay_repaired --out docs/ECOLOGY_CALIBRATION_RESULTS.json
python -m unittest discover -s tests -p 'test_simulation*.py'
```

Validation: 62 simulation tests passed. No new trading strategy qualified.
