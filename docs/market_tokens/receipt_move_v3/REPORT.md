# Receipt-time token benchmark v3

Completed on five previously examined Binance BTCUSDT recordings. This is a development experiment, not untouched evaluation or a live trading qualification. The deployed Kraken learner is unchanged.

## What changed

* Decisions and 100 ms / 1 s / 10 s targets use book receipt time. Raw trades are reconstructed using the existing receipt-window adapter; current-receipt trade ties are deferred.
* Any observed midpoint move and ending-price change are separate. Half-tick midpoint changes are preserved; a move followed by reversal remains an any-move positive.
* Numeric and token models receive the same 35 features and four-event context (140 inputs). Tokens preserve missing/zero distinctions; other bins fit training hours only.
* Depth percentiles use strictly prior 256-row windows. Typical trade size uses the prior 200 intervals. Histories reset at episodes, gaps, invalid receipts and event/receipt delays over 250 ms.
* Both models use the supplied fixed gradient-boosting recipe: 150 trees, depth 4, minimum leaf 200, rate 0.05, L2 1.0, seed 0. No tuning or ablation selection on these evaluation hours.
* Bundle summaries cover 1, 10 and 60 seconds; partial history is missing, not extrapolated. These aggregate interval bundles by closing receipt, rather than exact individual trade timestamp summaries.

## Results

| Question | Horizon | Numeric AUC | Token AUC | Evaluation examples |
|---|---:|---:|---:|---:|
| Any observed move | 100 ms | 0.808 | 0.788 | 16,221 |
| Any observed move | 1000 ms | 0.639 | 0.593 | 11,805 |
| Any observed move | 10000 ms | 0.450 | 0.503 | 809 |
| Up, conditional on ending change | 100 ms | 0.710 | 0.707 | 193 |
| Up, conditional on ending change | 1000 ms | 0.900 | 0.881 | 985 |
| Up, conditional on ending change | 10000 ms | 0.453 | 0.392 | 278 |

The one-second conditional direction token model has 80.3% classification accuracy at probability threshold 0.5 and 32.3% lower log loss than the training-frequency baseline. Its occurrence model is worse than that baseline on log loss. This is not 80.3% accuracy on all trading opportunities: direction is evaluated only where an ending change occurred.

The 100 ms conditional direction experiment has only 193 evaluation examples. In the first three folds, the fixed minimum leaf size prevents splits and predictions remain the training prior. The last fold drives the learned-direction benefit. Pooled AUC should be read alongside FOLDS.json, not as a universal property.

The 10-second conditional direction model fails overall; token AUC is 0.392 and log loss is much worse than the prior. Only 278 changed-price examples remain after continuity checks, and one evaluation hour has no eligible 10-second examples. Do not promote this output.

## Costs and scope

COST_SCALE.json shows a perfect-future-direction diagnostic, not a trading backtest. It compares average absolute midpoint return with a declared 6 bp round-trip cost scenario inherited from the supplied script; actual venue fees are not verified here. It includes no executable bid/ask fills, latency, maker queues, inventory or slippage. No profit claim follows from AUC.

All five recordings were used in previous research. Train/test chronology is respected, but the four later hours are development evaluations, not newly untouched tests. Targets overlap despite strides of 3 (train) and 10 (evaluation). Counts are not independent effective sample sizes. Coverage filtering censors future feed interruptions and cannot establish all-condition performance.

220,923 of 258,917 state rows passed the new filters, producing 2,189 continuous segments. The run fitted 66 models (including separate endpoint and any-move questions); unsupported tasks were explicitly skipped. The trial count describes this run only, not the entire project research history.

## Reproduce

Install requirements-receipt-benchmark.txt, then run from repository root:

```
python -m unittest discover -s tests -p test_receipt_move_benchmark.py -v
python receipt_move_benchmark.py --repo . --upload /path/to/raw-trades --out docs/market_tokens/receipt_move_v3
```

The five raw trade Parquet files are external inputs. Their SHA-256 hashes and the adapter counts are in RESULTS.json. Frozen book tape paths are under data/frozen. Saved fold tokenizers and predictions permit inspection; classifier weights are not stored or promoted.

## Next qualification step

Freeze a predeclared candidate on a dedicated training period, score occurrence and conditional direction together on new contiguous data from one venue, and evaluate an executable cost/latency policy. Keep WAIT until that work establishes a qualified strategy.
