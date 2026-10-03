# Market language: completed daily transformer experiment

We trained four compact neural sequence models on verified daily market states. This is an implemented and reproducible AI experiment, not a profitable signal or a deployed live model.

## What was built

Ten coins, 1,339 daily dates from January 2023 through August 2026, and 40 fields per date: return, quote volume, Parkinson volatility and Amihud illiquidity. Each field has 16 training-fitted quantile bins plus below/above-range categories. The vocabulary contains 720 typed IDs. A 16-day context enters a causal two-layer transformer with four attention heads and 141,657 parameters.

Three seeds learn next-day field categories through self-supervised pretraining, then fine-tune to nine future Bitcoin return categories. A matched seed trains directly without pretraining. Validation selects checkpoints and probability temperature; an ensemble averages the three pretrained forecasts. Logistic regression and a training-frequency prior use the same chronological boundaries. See [PROTOCOL.md](PROTOCOL.md) for the frozen recipe.

The training task improved: for seed 91 next-state training loss fell from 2.917 to 2.326. This measures fitting the training sequence; it does not establish held-out token-generation fidelity or tradability.

## Timing and results

There are 615 labeled training windows, 616 pretraining windows, 89 validation windows and 607 evaluation trading days, January 2025 through August 30, 2026. Training outcomes are available by October 1, 2024; validation observations start strictly later. Validation outcomes are available before the first evaluation trade. Execution waits a full daily bar after observing a completed feature day.

| Method | Return-class log loss, lower is better | Net return, 25 bps per side |
|---|---:|---:|
| Pretrained ensemble | 2.20524 | -18.29% |
| Direct transformer, no pretraining | 2.19864 | -19.87% |
| Last-frame logistic regression | 2.21172 | -21.27% |
| Training-frequency prior | 2.19776 | 0.00% |
| Hold Bitcoin | Not applicable | -17.40% |

Individual pretrained seeds returned -18.29%, -17.40% and -16.49%. They are reported together; the best seed is not selected as a strategy. Every neural path executed only two sides: a buy and the terminal sale. Forecasts never crossed the exit threshold. In plain terms, these models largely became buy-and-hold, rather than useful market-timing strategies. The simple class-frequency forecast had better log loss than every neural model. Continuous expected-return errors also exceeded the zero-return forecast error.

The ensemble is not profitable here and has not earned live promotion. Pretraining does not show a predictive improvement in this comparison. Its difference from the direct model includes ensemble averaging; the paired seed-91 comparison is the cleaner pretraining control.

## Reproducibility and development corrections

All four NPZ weight files load with pickle disabled and reproduce every saved forecast across all 607 days exactly in this runtime. RUN_AUDIT.json contains hashes and stage-boundary checks. Three targeted tests pass: causal attention, training-only tokenization, and finite gradients/probability normalization. These checks mean the software behaves as intended, not that a strategy is profitable.

Two implementation corrections were made and the entire unchanged recipe rerun: reset the fine-tuning random schedule for a matched pretraining control; exclude two validation observations at/before the training boundary. Earlier summaries are preserved in INITIAL_UNPAIRED_RANDOM_STREAM_RESULTS.json and INITIAL_PRE_VALIDATION_BOUNDARY_FIX_RESULTS.json. The final RESULTS.json and PREDICTIONS.csv are authoritative. Hyperparameters and trading thresholds were not optimized on evaluation profitability.

These historical periods have already been examined during development. They are not untouched evidence. Daily open fills use assumed fees and omit measured spread, slippage, impact and position sizing. Daily bars do not identify retail traders, institutions, dealer inventory or option hedging. This experiment does not extend the eight recorded hours of intraday book history into years of book data.

## Modern AI methods and the next experiment

Implemented: typed tokenization, causal attention, self-supervised pretraining, outcome fine-tuning, validation temperature calibration and a small ensemble. This model is trained from scratch; it is not ChatGPT or a pretrained financial foundation model.

Primary research references:
- [Chronos](https://www.amazon.science/publications/chronos-learning-the-language-of-time-series): quantized time-series tokens and pretrained sequence models.
- [PatchTST](https://arxiv.org/abs/2211.14730): patch-based time-series learning. Our grouped daily frames are not a faithful PatchTST implementation.
- [Decision Transformer](https://arxiv.org/abs/2106.01345): offline state/action/return sequence learning. Not implemented here.
- [Retrieval-augmented generation](https://arxiv.org/abs/2005.11401): external knowledge retrieval. Adapting this to training-only market episodes is a proposal, not a validated trading result.

The next defensible experiment is to measure held-out next-state fidelity, expand timestamped intraday trades/book observations across contiguous months, and compare a pretrained sequence model against equal-data controls on a newly frozen future period. Books supply hypotheses and mechanisms; observed market sequences supply training evidence. Offline policy learning comes after realistic fills, costs and inventory constraints are available. Adding model size or synthetic examples alone does not establish an edge.

## Run

Install requirements-token-training-cpu.txt in an isolated environment, obtain the checksum-pinned crossasset dataset using the existing data downloader, then run:

```sh
python -m src.simulation.daily_token_transformer /absolute/path/to/repository
python -m unittest discover -s tests -p test_simulation_daily_token_transformer.py
```

This command reruns training and replaces final result/weight files. CPU training uses two threads; this small run took approximately 33 seconds, excluding setup and data collection. It is not months of background compute or a large foundation-model training run.
