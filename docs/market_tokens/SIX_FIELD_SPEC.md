# Six-field tokenizer and reconstruction audit

Implemented: src/simulation/six_field_tokens.py; reproducible audit: src/simulation/token_reconstruction_audit.py. Six targeted tests passed.

Events emit exactly six separate integer IDs: type, side, signed relative tick level, log size, log receipt gap, estimated participant cluster. Each field has a disjoint ID range. There is no giant composite dictionary. For 32 size/time bins the event vocabulary has 129 IDs, including missing/out-of-range and unknown categories: 6 types + 3 sides + 33 levels + 35 size + 35 gap + 17 participants. Combinations are learned by a sequence model; they are not enumerated into millions of embedding entries.

Types include trade, limit, add, cancel plus book_change/unknown. These extra categories preserve honest semantics for current aggregated book data. Buy/sell require an upstream convention: aggressor side for trades, bid-to-buy/ask-to-sell for resting messages. Participant clusters have a fixed budget of 16 plus unknown; no participant clustering has been fitted.

Signed level uses 16 magnitude categories per sign plus missing. Exact integer tick categories are retained for 0 through 5; boundaries then widen through 7.5, 10.5, 14.5, 20.5 ticks and approximately logarithmic outer boundaries 32.5, 64.5, 128.5, 256.5, 512.5. Outer values saturate. Zero uses the nonnegative sign category; a negative sub-tick distance can use the negative zero-magnitude bucket. Thirty-two signed values cannot encode all 41 integer offsets from -20 through +20 exactly. This is an explicit precision tradeoff, not a claim that all near-touch offsets are lossless. Tick size is venue/instrument/time dependent and must come from metadata; the encoder accepts a precomputed distance from an already-available valid mid, never raw absolute price.

Size/time codecs use log1p(base quantity) and log1p(receipt-gap seconds). Each QuantileCodec fits on past observations only, optionally inside a rolling time window. Supplying a future record rejects the fit. Every fitted codec carries a cutoff timestamp; using it before that cutoff rejects encoding. Missing quantities/gaps remain missing, not zero. Coarse/fine dual tokens would change the six-field format and are deferred pending ablation. VQ-VAE is not implemented.

Rolling refits require explicit vocabulary versioning: identical numeric token IDs can change meaning after refitting. A sequence must not mix versions without recording version boundaries or re-encoding its context with one past-fitted codec. Decode maps each bin to its training median; under/over tokens reconstruct at training min/max and carry range flags. Reconstruction is approximate and does not recover exact market messages. Level reconstruction is not yet implemented; this audit measures quantile-codec numeric reconstruction.

SummaryTokenizer emits six summary IDs for volatility, spread, imbalance, funding, open-interest change and regime, with separate ID offsets. Completed period end, receipt and decision times are checked. This is a separate vocabulary namespace from event IDs and must get an explicit scale/type marker and disjoint global offsets in a neural input adapter. Missing fields receive missing IDs. The caller supplies completed second/minute summaries and fitted codecs; raw aggregation, funding/OI ingestion and a causal regime estimator are not implemented here. A regime ID supplied as a numeric feature is not evidence of a fitted market regime model.

## Actual daily-data audit

SIX_FIELD_AUDIT.json records 16/32/64 bin reconstruction and token-frequency divergence on the existing verified BTC daily features. Training bins freeze October 1, 2024. There are 607 evaluation trading dates in January 2025 through August 2026. This is daily development evidence, not an event size/time or participant-label audit. All periods were previously inspected.

| Bins | BTC return reconstruction MAE, bps | Two-state token model log loss | Base-rate log loss | Unseen context backoff |
|---|---:|---:|---:|---:|
| 16 | 22.107 | 2.22811 | 2.19722 | 8.73% |
| 32 | 12.447 | 2.22047 | 2.19722 | 53.71% |
| 64 | 6.549 | 2.20354 | 2.19722 | 84.84% |

Lower log loss is better. No variant beats the same-period base-rate prediction. The two-state model conditions on the previous/current BTC return tokens and predicts nine future return classes using smoothed training counts; unseen contexts fall back to the smoothed training prior. It is a simple n-gram-context classifier, not a message-generation simulator. No bin count is selected from these results. More bins preserve more numerical detail but make contexts sparser; the 64-bin model is largely a baseline backoff.

Frequency drift is measured with Jensen-Shannon divergence, with full histograms retained. BTC return divergence rises from 0.01272 at 16 bins to 0.03389 at 64 bins. This quantifies drift without declaring arbitrary stability thresholds. Errors are in the field's own units; daily volatility/illiquidity and quote-volume results are also saved.

The audit fits frozen bins rather than rolling them during evaluation. A rolling implementation must repeat strict past-only fitting and trace version changes. These three bin comparisons and the three conditional models are additional development trials. No profit, execution-cost or deflated-Sharpe claim is made.

## Build order and remaining work

Completed here: six-field schema, reconstructable quantile codec, rolling-fit API, summary availability checks, 16/32/64 daily reconstruction/frequency comparisons, unconditional baseline and simple two-state token comparison.

Next integration needs real ordered events, correct tick metadata, receipt timestamps and explicit sequence validity. Then test event size/gap reconstruction and frequencies, fit a next-event n-gram baseline, and train a small transformer against the same baseline and data. The earlier daily transformer is a separate completed experiment and has not been retrained on this event vocabulary.

Neural rollouts, stylized-fact validation, inferred participant training, cross-exchange clock audits and live promotion remain unimplemented. Match exchange event clocks while gating features by local receipt availability; never shift clocks to maximize predictive fit. Fat tails and volatility clustering are necessary diagnostics, not enough alone to approve fills or strategies. A new model must improve proper forecast scores and survive realistic cost/latency replay and fresh forward evaluation before signal promotion.

Run the daily audit with:

```sh
python -m src.simulation.token_reconstruction_audit /absolute/path/to/repository
python -m unittest discover -s tests -p test_simulation_six_field_tokens.py
```
