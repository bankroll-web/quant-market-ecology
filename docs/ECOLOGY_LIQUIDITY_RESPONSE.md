# Training liquidity-response benchmark

The recorded-flow simulator still lacks opposing liquidity. This diagnostic measures the missing behavior in the frozen training recording before changing agent rules. It does not infer trader identities or deploy a new maker policy.

## What the recording shows

Of 210 high-pressure training windows, 148 show displayed changes reinforcing signed trades and 62 show changes opposing them: **29.5% oppose**. The current recorded-flow simulator has zero opposing windows across its three 120-step runs.

Quantities below are divided by combined bid/ask depth at window start. For net buying, bids are the support side and asks are the resistance side; for net selling, the mapping reverses. These labels describe relative book quantities, not intentions or proven price support.

| Training regime | Windows | Median support-side net change | Median resistance-side net change | Median gross displayed turnover |
|---|---:|---:|---:|---:|
| High pressure, reinforcing | 148 | +4.82% | −1.86% | 186.34% |
| High pressure, opposing | 62 | −1.16% | +4.05% | 164.63% |

Opposing windows have a median increase in the resistance-side displayed quantity and a median decrease on the support side. These separate medians do not add up to the median pressure. Signs of aligned pressure are part of the regime definition, so their separation is not independent evidence of a discovery.

Gross turnover sums bid additions, bid reductions, ask additions and ask reductions. Repeated quote changes can exceed initial depth many times. This is **not traded volume** or unique money entering the market. Same-window midpoint change has a zero median in both high-pressure groups; the quantiles are reported in JSON, without claims about subsequent returns.

## Integration boundary

The source CSV hash must match the frozen regime-study training hash. Only 25 May 2026 00:00 is permitted. Counts, trade pressure and displayed pressure reconcile with the accepted-window quantities. Full and fresh-receipt-only summaries are separate; each reports 10th, 50th and 90th percentiles.

Anonymous L2 reductions mix executions, cancellations and receipt aggregation. Feeding the full observed reduction as a cancellation alongside historical executions would double-count some removal. Moving near-touch bands and bundled updates also differ from synthetic per-method instrumentation. This benchmark therefore does not install observed gross changes directly as maker events.

Next development: reconstruct joint per-price trade and book-change events, state the ordering and residual-removal assumptions, and test an asymmetric displayed-liquidity environment. Distinguish replay of observed events from a generative agent model. Do not condition a pre-trade policy on the completed window's regime or price change.

## Reproduce

```python
from src.simulation.ecology_liquidity_response import build
build('data/processed/ecology_price_mechanics/2026-05-25_00_windows.csv',
      'docs/ECOLOGY_REGIME_DYNAMICS_RESULTS.json',
      'docs/ECOLOGY_LIQUIDITY_RESPONSE_RESULTS.json')
```

[Full results](ECOLOGY_LIQUIDITY_RESPONSE_RESULTS.json). Empirical training summaries have no uncertainty intervals or untouched validation. This is a simulator-development benchmark, not a profitable strategy.
