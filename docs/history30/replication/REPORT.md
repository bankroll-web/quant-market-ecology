# Quantitative research workflow applied to the ecology candidate

## Result: do not promote the reversal strategy

Applied the frozen September strong-flow/high-activity condition to **35,676,321 August aggregate trades**. The archive checksum matched its published value, aggregate IDs had zero gaps, and the five-minute grid was contiguous. Thresholds and directions were not refitted on August. Together the two archives contain 71,712,950 aggregate trades across 61 calendar days.

| Holding time | Hypothetical entries | Gross mean bps | Net mean at 6 bps cost | 95% stationary-day bootstrap interval for net mean |
|---|---:|---:|---:|---|
| 5 min | 274 | 2.41 | -3.59 | [-4.89, -2.41] |
| 15 min | 100 | 2.17 | -3.83 | [-8.02, 0.10] |
| 30 min | 46 | -0.53 | -6.53 | [-12.14, 0.13] |

The five-minute reversal relationship repeats weakly before costs, but assumed execution costs exceed its average benefit. The fifteen-minute result is also negative after costs. The thirty-minute reversal did not repeat even before costs. These frozen conditions do not justify promotion. At a hypothetical 2 bps roundtrip cost, five- and fifteen-minute point estimates become slightly positive (0.41 and 0.17 bps), but that is not verified execution pricing or statistical proof of profit. Their uncertainty intervals shifted to that cost include zero.

## What a quantitative researcher does, and what was implemented

1. **Mechanism and measurement.** Specify a falsifiable statement: extreme signed trade flow during high activity is followed by a reversal. Do not invent participant identities or label trade imbalance as book-event OFI.

2. **Freeze the experiment.** Lock thresholds, trade direction and three holding periods before evaluating another period. August is an earlier-period replication, not a forward deployment simulation. See [protocol](PROTOCOL.md).

3. **Audit the inputs and timing.** Verify published archive hashes, monotonic IDs/timestamps and contiguous buckets. Use only completed feature blocks. Fixed-clock subsampling prevents holding-interval overlap, though dependence can remain.

4. **Estimate economically relevant outcomes.** Report gross and cost-adjusted returns per candidate entry. Keep decisions fixed under cost sensitivity. Do not equate direction accuracy with profit or additive trade bps with an account return. Actual bid/ask, funding, fills and latency are missing, so results are proxy scores.

5. **Account for dependence.** Implement the stationary bootstrap over whole-day return sums and counts: 5,000 draws, geometric blocks averaging three days, fixed seed 91. This preserves neighbouring days more often than independent resampling. Report intervals and approximate one-sided centered-bootstrap tests. Stationarity and the small month sample constrain validity.

6. **Account for multiple hypotheses.** Apply Holm adjustment to the three frozen horizon tests. All adjusted p-values are 1.0 here: none supports positive net mean. This correction does not erase the selection effects from the broader earlier research history.

7. **Reject or replicate.** Reject promotion of this candidate under the base assumptions. Do not retune August and call it new validation. The next research branch needs a separately registered mechanism and new observations; a later period is required for genuine forward testing.

## Sources and scope

Politis and Romano: stationary bootstrap for dependent data, primary institutional source: https://statistics.stanford.edu/technical-reports/stationary-bootstrap

Bailey, Borwein, Lopez de Prado and Zhu: probability of backtest overfitting, primary paper listing: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253. This motivates controlling search and separating periods; this implementation does not calculate their PBO statistic.

Holm correction is implemented directly as ordered p-values multiplied by remaining hypothesis count, with monotone cumulative maximum and clipping at one. This is not White's Reality Check or Hansen's SPA; those require a defined candidate family and different inference. More mathematical tools are not automatically stronger evidence.

## Reproduce

```bash
python -m src.simulation.download_historical_month data/raw/history30 2026-08
python -m src.simulation.ecology_reversal_replication data/raw/history30/BTCUSDT-aggTrades-2026-08.zip docs/history30
python -m unittest tests.test_simulation_reversal_replication tests.test_simulation_conditional_response tests.test_simulation_historical_month
```

Archive SHA-256: `0f154421a06dc63f31fc98769c71c621685be67522cc3a595b44ddb004db1c66`. [Machine-readable results](results.json). The monthly aggregation module requires NumPy and pandas. No raw archive or generated large CSV is committed. Eight targeted software checks passed; these verify implementation behaviour, not an edge.
