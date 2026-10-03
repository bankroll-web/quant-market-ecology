# Uploaded D09 tokenizer: completed real-tape training experiment

The uploaded tokenizer_v1.py and ecology_arena.py were read and preserved as repository-root files. train_real.py was not among the attachments or local files, so a new compact trainer was implemented for the uploaded 12-field tokenizer. This run is not the five-field uploaded starter, the six-field prototype, or Kronos.

## Data verification and protocol

Ten D09/D09B CSVs were restored from the research branch. Every file matches its Git blob SHA and expected length (SOURCE_MANIFEST.json), and SHA256 hashes are recorded in RESULTS.json. The 1:1 episode/time join reproduced the uploaded tokenizer's no-dropped-row assertion.

Tokenizer bins fit only the first three recordings: May 25, 2026 at 04, 12 and 18 UTC, 136,600 event intervals. The later two are May 26 at 15 and 21 UTC, 122,317 intervals. These are five discontinuous recorded hours, not continuous coverage. All periods were already examined in development. Restoring the repository tapes allowed the reported tokenizer reconstruction figures to be reproduced.

The trainer uses 16 completed interval tokens per context and ten-event forward price/volatility/flow targets. It predicts the next interval's 12 token fields. Endpoint stride is ten events. Context+target must remain in one hour-scoped episode, have increasing event times and consecutive interval indices. This leaves 12,986 training contexts and 11,629 evaluation contexts. Contexts overlap; ten-event horizons vary in elapsed time. Flow targets with zero total traded quantity stay missing; 7,532 evaluation flow targets are usable.

A one-layer, 32-wide, four-head causal transformer has separate field embedding dictionaries, next-field classification heads, five ordered return quantiles and continuous signed-flow/volatility heads. Seed 91, five fixed epochs, AdamW .001, batches up to 128. Evaluation was not used for checkpoint selection. Future price targets use mid_t1 after the current interval and ten events later. Volatility is mean absolute log-return in the future window, not realized variance. Return/volatility scales fit only resolved training samples.

## Results

| Output | Transformer | Training-only baseline | Interpretation |
|---|---:|---:|---|
| Return pinball loss, bps | 0.038584 | 0.038267 | Transformer about 0.83% worse |
| Signed-flow MSE | 0.840258 | 0.834637 | Transformer about 0.67% worse |
| Volatility-proxy MSE, bps squared | 0.001129665 | 0.001173113 | Transformer about 3.70% better |

The nominal 80% price interval covers 87.42% of outcomes. Extra coverage alone does not imply useful forecasts. Volatility improvement is exploratory: one training seed, two already-examined later hours, no dependence-adjusted confidence interval, no cost-aware trading result.

Next-token comparisons use the same training/evaluation endpoints and targets for the unconditional prior, smoothed same-field bigram and transformer. The transformer scores better than the bigram on 6/12 fields: time gap, trade count, signed flow, bid reduction, mid move and spread flag. It scores worse on the other six, especially persistent order-book imbalance (0.8491 versus 0.5137 bits). Full scores are in RESULTS.json. These matched scores differ slightly from the uploaded tokenizer's all-adjacent-event bigram report because the trainer selects stride-ten, target-eligible windows.

Rare-move diagnostic: 248 next-event mid tokens are nonzero, versus 11,381 zero tokens. Conditional on an actual nonzero outcome, transformer log loss is 7.4115 bits versus bigram 7.9403. This retrospective conditional diagnostic does not prove the model can detect a move before it occurs; overall probability scores and calibrated event detection remain necessary. No class is selected for trading.

## Tokenizer findings and timing limits

The original reconstruction results were reproduced (TOKENIZER_OUTPUT.txt). More detail remains necessary around tail bins: inverse decoding clips to training bin means, so volume totals can be distorted despite high correlation. Signed net-sum recovery can also hide offsetting errors. PSI is reported as a descriptive distribution-shift measure; 0.1 is a heuristic, not a validated alarm threshold.

A critical live boundary remains unresolved: these frozen tapes identify exchange event intervals, but contain no receipt availability timestamps. Completed flow/liquidity/mid-change fields can be used after that interval completes, not at its start. This trial explicitly uses event-time development; it does not qualify a live observation pipeline. Historical training targets end before the first evaluation decision; the saved audit checks that chronological separation, but cannot supply missing receipt provenance.

Tick size 0.1 is inherited as an assumption. Mid-price changes can be half ticks; rounding can discard sub-tick detail. The concentration of rare larger moves is reproduced, but actual sweeps versus source resets/gap artifacts are not identified by this tokenizer. Avoid causal explanations of those jumps until raw sequence validity and price paths are reconciled. The absence of add/cancel/order identity labels means the fields describe aggregate displayed liquidity responses, not individual cancellation intentions.

## Arena reproduction and limitations

The unchanged uploaded arena was run with 60,000 evolution steps and 30,000 scoring steps on six fresh world seeds at 0.5 tick per fill. Token-driven evolved agents beat both baselines in 0/6 worlds; token-blind evolved agents also win 0/6. Average evolved PnL is 207.8 toy ticks with tokens and 370.5 without, versus tight-rule averages 513.4 and 612.3 respectively. These are reported toy units, not Bitcoin prices or realistic execution returns. The zero-fee run also reproduced the uploaded account: token-driven evolved agents win 5/6 worlds and token-blind agents 4/6, with mean evolved PnL 665.3 and 829.6 toy ticks respectively. Both fee runs are preserved as full output logs.

Informed agents deliberately see future latent prices; that is a simulator assumption, not training-data leakage into maker observations. However, two capital-accounting caveats limit interpretation: reusing a dead agent slot overwrites its remaining cash rather than archiving its estate, and final marking/liquidation at reference omits execution friction. Per-slot champion selection is not a complete conserved-capital lifetime return measure. Same seed across token modes does not ensure identical execution randomness, since endogenous fills and random choices differ. More fresh seeds do not remove simulator misspecification. No arena policy is promoted.

## Saved outputs and next decision

WEIGHTS.npz, PREPROCESSING.json, PREDICTIONS.csv.gz, RESULTS.json, rare-move diagnostics, input manifests and audit are saved. audit_d09_training.py loads weights with pickle disabled and reproduces return pinball score to numerical tolerance. Three tests cover fixed training bin edges, episode exclusion and finite multi-output gradients/ordered quantiles.

The real-data experiment now exists. No field is declared useful for strategies merely because one next-token score improved. Feature ablation belongs on separate development folds; untouched later periods must be reserved for confirmation. Next priority is receipt-time/source-sequence reconciliation and contiguous-day replication, followed by baseline/ablation comparisons. A small volatility improvement does not justify optimizing an agent against the toy world. Fees, tick size, slippage and queue assumptions must be specified from the actual venue before paper execution.

Run from the repository root:

```sh
python tokenizer_v1.py --repo . --train 3
python train_real.py --repo .
python audit_d09_training.py .
python -m unittest discover -s tests -p test_d09_token_training.py
```

Dependencies: NumPy, pandas and CPU PyTorch. These add one neural fit with five fixed epochs, twelve field baseline comparisons and three outcome comparisons to the already-existing development trial history. No project-wide effective trial count or deflated Sharpe statistic is asserted.
