# Empirical trade-flow integration

This offline diagnostic replaces assumed independent, small background trades with recorded training-hour bursts. Maker rules remain fixed. It does not change the live dashboard or install a trading strategy.

## Results

Each run contains 120 synthetic steps, before any forced shock or maker withdrawal.

| Seed | Assumed high-pressure windows | Recorded-flow high-pressure windows | Assumed occupancy distance | Recorded-flow occupancy distance |
|---|---:|---:|---:|---:|
| 7 | 0 | 35 | 0.281 | 0.127 |
| 19 | 0 | 30 | 0.256 | 0.085 |
| 43 | 1 | 22 | 0.281 | 0.069 |

Across seeds, high-pressure frequency rises from 1/360 (0.28%) to 87/360 (24.17%). Training recording: 210/897 (23.41%). Distance is total variation over five regime frequencies: lower means closer proportions, not validated equivalence.

Every empirical synthetic high-pressure window reinforces signed trading pressure. Opposing liquidity is still absent. Executions mechanically remove opposite-side quotes, so reinforcement alone does not show that maker behavior is realistic. Next: measure training-only asymmetric displayed additions/reductions and compare a richer maker environment without tuning against later recordings.

## Boundary and reproduction

Only the 897 accepted windows from 25 May 2026 00:00 feed the driver. Raw trades reconcile exactly with window counts, net quantities and absolute quantities. Trades retain tape order for equal receipt timestamps and are never clipped. Random starts extend up to 10 windows, ending at any gap or episode boundary. Ten is a fixed exploratory choice, not an optimized setting. Source windows, durations and block identities are recorded in the JSON.

Each recorded 1–1.25 second window maps to one synthetic second. This compresses the clock and omits intra-window arrival times. Artificial block joins enter descriptive synthetic transition statistics; they cannot establish natural persistence. The diagnostic uses original cancellation and replenishment rules before second 120, with no forced intervention. A parity test checks that the runner preserves original prices under identical flow.

Run from repository root with numpy and pyarrow installed:

```python
from src.simulation.empirical_ecology_flow import check
check('configs/simulation_v1_demo.json',
      'docs/ECOLOGY_REGIME_DYNAMICS_RESULTS.json',
      'data/processed/ecology_price_mechanics/2026-05-25_00_windows.csv',
      '/path/to/BTCUSDT_trades_2026-05-25_00.parquet',
      'docs/EMPIRICAL_ECOLOGY_FLOW_RESULTS.json')
```

No later-period fitting occurs. All eight comparison hours were inspected previously; none provides untouched validation. This is a simulator development result, not evidence of profitability or a causal counterfactual. Full results and input hashes: [JSON](EMPIRICAL_ECOLOGY_FLOW_RESULTS.json).
