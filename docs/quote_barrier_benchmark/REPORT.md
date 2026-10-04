# Quote-side triple-barrier development benchmark

Status: completed, unqualified, no live promotion or orders.

## Fixed recipe and audit

Five frozen D09/D09B hours, 258,917 input rows; receipt continuity and event age audited using receipt_move_benchmark v3. Real post-event bid/ask quotes joined exactly by hour/receipt to mechanics-study files; midpoint match asserted for every used quote. No synthetic spreads or participant labels. Source hashes in RESULTS.json.

Primary settings fixed before this run: long-side quote proxy, 50 ms latency, one-second horizon, +1/-1 log-bps barriers, one-second minimum decision spacing. Ask entry and bid exit include spread; zero additional fees is a diagnostic assumption, not actual venue costs. First received quote after latency is the entry proxy, not a guarantee of a fill. Barrier monitoring begins on subsequent received quotes. Time exits use the last received quote at/before deadline, with later receipt coverage required.

4,206 observed labels: 44 profit barriers, 57 loss barriers, 4,105 time barriers. Censored: 1,591 missing deadline coverage and 107 missing entries. These censored examples are omitted, potentially selecting regimes with cleaner feeds. Continuous segments never bridge invalid rows, clock reversals, gaps or resets. Sampling restarts by segment; this is not a nonoverlapping trading policy.

The benchmark uses constant 1 bp barriers, not future volatility-scaled thresholds. Six label/split tests passed plus temporal and barrier assertions on every saved label.

## Models and validation

Four expanding-hour evaluations, 3,683 later-hour labels. All five recordings were previously examined: this is development evidence, not an untouched test. Past-only purged splits use feature-context start and exact label availability end. One-second post-test embargo is redundant here because future training is excluded.

Same 35 features and four-event context for numeric and tokens. Training-only 16-bin token edges saved for each fold. Tokens are ordinal bin features for gradient boosting, not a trained language model. Eight classifier fits: 80 iterations, 15 leaf nodes, minimum leaf 40, L2 2, no early stopping, seed 31. No search or retuning after results. Models predict profit/loss/time classes; no post-fit probability calibration. Baseline is Laplace-smoothed training class frequency.

| Model | Pooled multiclass log loss | Baseline |
|---|---:|---:|
| Numeric | 0.20193 | 0.15048 |
| Tokens | 0.19688 | 0.15048 |

Lower is better. Numeric loses by approximately 34.2%; tokens by 30.8%. Tokens slightly improve on numeric but do not earn an edge against the constant baseline. Rare barrier hits, discontinuous hours and a changing regime limit this comparison. The final hour improves modestly over its baseline for both models; that does not outweigh the overall failure.

Time label 0 does not mean zero return: labels.csv.gz preserves net quote-proxy return. These are outcome forecasts, not strategy P/L. No meta-labeling, calibrated sizing, fees/impact replay, real fills or profit qualification was performed. No BUY/SELL promotion.

## Reproduce

Use requirements-receipt-benchmark.txt, frozen data and the existing raw-trade Parquet files in ../upload plus mechanics-study quote files. From repository root:

```sh
python quote_barrier_benchmark.py
python -m unittest discover -s tests -p test_market_label_validation.py
```

Labels, predictions, source audit, bin definitions and summary are saved here. Next work must distinguish move occurrence from outcome direction and improve sample coverage on separate data; do not tune these inspected hours and call the same hours confirmation.
