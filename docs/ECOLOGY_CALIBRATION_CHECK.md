# Simulator calibration check: observed ecology versus the demo

Completed 3 October 2026. The existing demonstration is substantially quieter than the selected recorded market. This comparison adds quantitative calibration diagnostics; it does not fit new agent parameters or qualify the simulator.

## Instrumentation and comparability

An optional ObservedBook records executed buy/sell quantities and per-side displayed additions/reductions after each cancellation, execution and replenishment method call. Quantity changes use each method's pre-action midpoint and the same 10-basis-point near-touch band as the historical diagnostic. Initial near-touch depth normalizes the pressure. It records actual filled quantities, including hedge executions when enabled, rather than requested quantities or trade counts.

The original simulation behaviour is preserved by default. A test compares all original fields and shock outputs with and without instrumentation for an identical seeded run. The empirical replay and frozen research coefficients remain unchanged.

The comparison runs seeds 7, 19 and 43 under normal and maker-withdrawal scenarios. Each contains 300 synthetic seconds with a forced buy at second 120; withdrawal is also intentional. The first 120 seconds are reported separately. Normal and withdrawal pre-intervention paths share identical flow and mechanics and must not be counted as independent replications.

Real received update bundles and simulator method calls have different aggregation/timing. Executions themselves reduce opposite-side displayed liquidity and can mechanically reinforce pressure; the reinforcement label is not proof of discretionary maker behaviour. Real unknown deeper book coverage and filtered segments limit equivalence.

## Main comparison

Across the three unique normal pre-intervention samples, **1 of 360 windows (0.28%)** cross the original frozen high-pressure cutoff. No high-pressure/opposing-liquidity windows appear in these samples. The measured training period has 210 of 897 high-pressure windows (23.41%). Across the eight observed recordings, high-pressure frequencies range from about 7.6% to 65.8%.

| Seed | Pre-intervention windows | High/reinforcing | High/opposing | Lower-pressure | Occupancy distance from training |
|---|---:|---:|---:|---:|---:|
| 7 | 120 | 0 | 0 | 118 | 0.281 |
| 19 | 120 | 0 | 0 | 115 | 0.256 |
| 43 | 120 | 1 | 0 | 118 | 0.281 |

Occupancy total variation is half the sum of absolute differences in empirical state proportions: 0 means matching proportions and 1 means disjoint distributions. Transition-row distances use the same measure when both samples contain outgoing transitions for that state; unsupported comparisons are null. Observed run-median differences are also reported, with censoring and coverage limitations retained. No equivalence threshold or automatic pass/fail rule has been validated.

The sample is small and the source archive is selected. This does not establish the real population frequency of bursts. It does demonstrate that the fixed demo is not reproducing those observed regime frequencies under these seeds and its existing assumed background flow.

## Full intervention runs

All normal and withdrawal runs are included separately in [ECOLOGY_CALIBRATION_CHECK_RESULTS.json](ECOLOGY_CALIBRATION_CHECK_RESULTS.json), with per-regime counts, transition counts, censored observed runs and comparisons to each historical period. The forced shock and maker pause are stress interventions; their full-run frequencies must not be interpreted as natural market calibration. No synthetic observations are mixed into empirical training data.

## Concrete calibration target

The assumed constant background trade count, capped exponential size distribution and largely symmetric maker routines fail to generate enough of the recorded pressure/liquidity diversity. The next environment experiment needs measured event-size and timing distributions, burst dependence and asymmetric state-dependent liquidity changes. Those choices should be specified before evaluating a replacement on new contiguous same-venue days.

Increasing an arbitrary shock or fitting until these selected frequencies match would not establish realistic market ecology. A candidate environment must jointly reproduce depth, spread, activity, reaction and recovery distributions, as well as these regime diagnostics. Participant identity and option inventory remain assumptions unless suitable additional sources are provided.

## Reproduction

```bash
python -m src.simulation.ecology_calibration_check --config configs/simulation_v1_demo.json --reference docs/ECOLOGY_REGIME_DYNAMICS_RESULTS.json --out data/processed/ecology_calibration_check
python tools/report_ecology_calibration_check.py --source data/processed/ecology_calibration_check/report.json --reference docs/ECOLOGY_REGIME_DYNAMICS_RESULTS.json --out docs/ECOLOGY_CALIBRATION_CHECK.md
python -m unittest discover -s tests -p 'test_simulation*.py'
```

The reference hashes and configuration hash are saved in the results. Tests verify simulation parity, filled-quantity/side instrumentation and identical-summary distances. This diagnostic does not change the live observer's default simulation or enable trading. [Development roadmap](MARKET_ECOLOGY_ROADMAP.md).

