# First observed Bitcoin six-field token trial

The six-field integer tokenizer is now connected to eight real displayed-book-change recordings. A compact causal transformer trained for five fixed epochs on 402 eligible first-half-hour examples and evaluated on 7,597 later eligible examples. These are previously examined development data, not untouched evidence. One test checks ordered quantiles and finite gradients.

The input contains eight valid receipt bundles per context. Type is book_change. Size is log gross displayed quantity change across both sides; time gap is log receipt interval. Side, price level and participant remain unknown/missing. We do not fabricate individual order types, tick offsets or trader identities. This is a state-bundle adapter, not a complete trade-message model. There are 129 possible field IDs; several fields are constant in this dataset.

Training-only size/gap bins use 21,821 earlier receipt transitions, with 32 quantile categories. Training contexts are retrospectively encoded using the initial frozen training codec. Later decisions use only that already-fitted codec. Contexts and targets must stay within one validity episode with inter-receipt gaps at most 250ms, non-crossed books and event timestamps no later than receipt. Outcomes are the first eligible receipt at/after one second, with up to 250ms sampling lag. Eight raw receipts cover variable wall-clock duration.

Outputs are five ordered return quantiles and a mean-absolute one-event log-return volatility proxy, measured within the future one-second target interval. This is not conventional realized variance. Numeric units are bps. Training target scales are fitted on fully resolved initial examples. No traded-flow output is trained because these inputs do not provide synchronized aggressor trades. No next-event head or multi-scale summary input is trained in this trial.

| Measure | Token model | Training-only baseline |
|---|---:|---:|
| Mean quantile pinball loss, bps | 0.072332 | 0.060277 |
| Volatility-proxy MSE, bps squared | 0.000299743 | 0.000299736 |

Lower is better: neither output improves on its baseline. The nominal 80% return interval covers 88.53% of outcomes. Coverage alone does not establish useful uncertainty; wider intervals can cover more while scoring poorly. Baselines are unconditional training return quantiles and mean training volatility. No checkpoint or threshold was selected by evaluation performance.

The model is a one-layer causal transformer, 32-wide embeddings summed over distinct field IDs, four attention heads and an eight-receipt position vocabulary. Seed 91, five epochs, batch up to 64, AdamW learning rate .001, gradient clipping 1. No pretrained ChatGPT/Kronos weights are used. It supplements rather than imports the uploaded five-field skeleton.

Saved artifacts: RESULTS.json, PREDICTIONS.csv, PREPROCESSING.json and WEIGHTS.npz (pickle-free loading). RESULTS pins source CSV SHA256 values. Source adapters and model are in src/simulation/bitcoin_event_token_trial.py. Source recordings are not duplicated into GitHub; use the existing pinned input recordings.

Counts are not independent samples; contexts overlap and sampled targets can overlap. No cost, latency-to-fill, queue, PnL, calibrated signal or live deployment is evaluated. Price quantiles are forecasts, not a validated profitable policy. Records already examined remain development data. This trial adds one neural fit, five training epochs with no checkpoint search, and two output baseline comparisons to the experiment history.

Next data requirement is synchronized trades and book states plus instrument tick metadata. That allows genuine aggressor-flow targets and level/side tokens; it does not grant participant identities. Further work includes baseline gradient boosting/n-grams on equal inputs, receipt/sequence provenance tests, saved-weight prediction reproduction, probability calibration, contiguous-day replication and realistic execution replay before promotion. Current model stays unqualified.

Run:

```sh
python -m src.simulation.bitcoin_event_token_trial /absolute/path/to/repository
python -m unittest discover -s tests -p test_simulation_bitcoin_event_token_trial.py
```
