# Liquidity-conditioned price response

Eight previously inspected Binance futures hours, using matching reconstructed books and trades. This is exploratory, not untouched evaluation. Definitions are frozen from the original first-hour study: high trade pressure >= 0.0010578000616062236; thin combined depth <= 364.226 BTC. Only freshness-qualified windows with audited forward labels enter. Targets are spaced by horizon plus 250 ms to cover the maximum inherited label-end lag.

Reinforcing means signed trade pressure and net displayed pressure share a sign; opposing means their signs differ. Net pressure includes several mechanisms and is not a cancellation or replenishment identification. Aligned forward return is positive for continuation in the trade-flow direction.

| Horizon | Display response | Depth | Observations | Mean aligned response, bps | 95% hour-cluster interval |
|---|---|---|---:|---:|---|
| 1 s | reinforcing | thin | 83 | 0.027 | [-0.181, 0.092] |
| 1 s | reinforcing | thick | 342 | 0.100 | [0.066, 0.170] |
| 1 s | opposing | thin | 47 | 0.006 | [0.000, 0.009] |
| 1 s | opposing | thick | 115 | -0.010 | [-0.028, 0.009] |
| 5 s | reinforcing | thin | 28 | -0.141 | [-2.046, 0.250] |
| 5 s | reinforcing | thick | 129 | 0.106 | [0.021, 0.207] |
| 5 s | opposing | thin | 12 | 0.442 | [-0.203, 2.037] |
| 5 s | opposing | thick | 49 | -0.246 | [-0.443, -0.046] |

These measurements suggest the relation of trade flow to displayed changes matters, but most effects are small and uncertain. Differences between group means have not been separately tested; group intervals are descriptive and uncorrected for multiple comparisons. Sparse thin-depth five-second groups cannot support dependable conclusions. No cost-aware entry rule or participant causal story is validated.

Later-hour results cover at most seven disconnected hours, not seven independent days. Cluster bootstrap resamples hours and recomputes observation-weighted means; hour dependence and regime coverage remain concerns. Midpoint response is not executable profit.

[Machine-readable results and input hashes](liquidity_conditioning.json). Run `python -m src.simulation.ecology_liquidity_conditioning .`. A targeted check verifies conservative target spacing; it does not validate profitability.
