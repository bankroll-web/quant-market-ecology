# Bitcoin token laboratory: receipt-window upgrade

The timing repair is implemented and the compact model has been retrained. Trade tokens now describe information received between book updates, rather than the retrospectively complete exchange-time interval. This is a working development pipeline and saved inference adapter. It is not a deployed live feed or a profitable trading policy.

## What changed

For successive book receipts B(previous) and B(current), count and sum trades with receipt timestamps in [B(previous), B(current)). Trades arriving exactly at the current receipt are deferred to the next window. A delayed trade is incorporated when received, without revising earlier tokens. This avoids needing an oracle to know when an exchange-time trade set is complete.

The dt token uses elapsed receipt time. Liquidity-add/remove, deeper liquidity, midpoint change, pre-update imbalance and spread retain the frozen book feature definitions. Twelve field tokens remain separate; no composite vocabulary or inferred participant identity was introduced. This is a new vocabulary policy, receipt_window_v1: old saved bin edges/weights must not be substituted.

Decision time is the closing book receipt with zero processing latency for this diagnostic. The return anchor is that observed book's midpoint. The ten subsequent book updates must have strictly increasing receipts and event timestamps, one episode and consecutive interval indices. Missing predecessors, episode starts, timestamp reversals/ties and gaps invalidate samples. All features in each accepted context have already arrived. This adapter inherits frozen book reconstruction; it does not independently certify the underlying raw book stream.

Bin edges and numeric normalization are fitted only on the first three hours; invalid receipt rows do not fit the bins. The same one-layer transformer, 32-dimensional representation, four heads, seed 91, five epochs and training loss are retained. The corrected vocabulary yields 17,802 parameters. No evaluation checkpoint selection or larger pretrained model was used. The serialization rerun retained the same seed/configuration and predictions; it was not a parameter-search trial.

## Measured results

Training: 12,953 contexts from May 25 04, 12 and 18 UTC. Evaluation: 11,608 contexts from May 26 15 and 21 UTC. These five hours were already examined previously; this is development evaluation, not untouched confirmation. Training targets finish before the first evaluation decision. Contexts contain 16 updates; targets cover ten updates. Evaluation target delay has median 269.66ms and minimum 2.34ms, which emphasizes that this diagnostic horizon is not a realistic execution allowance.

| Forecast task; lower error is better | Transformer | Training-only baseline | Difference |
|---|---:|---:|---:|
| Return distribution, pinball loss in bps | 0.03877077 | 0.03824225 | 1.38% worse |
| Signed flow ratio, mean squared error | 0.84061510 | 0.83985998 | 0.09% worse |
| Mean absolute book-return proxy, mean squared error | 0.00110349 | 0.00117278 | 5.91% lower |

The volatility proxy error is lower in both evaluation recordings (6.20% and 3.18%). This is a limited descriptive improvement, not a significance claim or demonstrated trading advantage. Flow performance differs by hour: worse in the 15 UTC recording, better in the 21 UTC recording. Return distribution error is worse in both. The predicted 80% return interval covers 84.69% of observations. The transformer beats the same-endpoint smoothed bigram on seven of twelve field prediction scores. The bigram remains substantially better for the slowly moving order-book imbalance token.

These scores must not be presented as gains versus the old event-time experiment: input semantics, labels and eligible examples changed. Compare against each run's own training-only baseline. No PnL, fees, slippage, inventory or queue result was measured here.

## Delivered components

- `receipt_tokens.py`: receipt-window aggregation and causal context/label construction.
- `train_receipt.py`: fixed-budget training, baseline scoring, per-hour diagnostics and artifact saving.
- `receipt_predict.py`: loads frozen bins and numerical weights, forecasts from exactly 16 already observed valid rows; never calls fit. Returns quantile returns, flow, the absolute-return proxy and WAIT.
- `audit_receipt_model.py`: verifies training code/artifact hashes and loaded inference against saved forecasts in both evaluation hours.
- `tests/test_receipt_tokens.py`: verifies late arrivals, receipt ties, future-data perturbation, invalid receipts and decision-price anchoring. The four new tests pass; the two previous receipt tests and three existing token-model tests also pass.

Saved weights reproduce all 11,608 stored forecasts exactly in the training reload check. The independently loaded tokenizer/model reproduces checked forecasts from both hours within 2.03e-8 absolute difference and rejects invalid contexts. Artifact and code hashes are recorded. `EXAMPLE_FORECAST.json` is a historical replay example, not a current Bitcoin signal.

## Run from the repository root

Use an environment with numpy, pandas, torch, pyarrow and zstandard. The recorded runtime versions are in INFERENCE_AUDIT.json. Keep the five matching raw trade files in a directory such as raw/; the ten D09/D09B CSV files remain in data/frozen/. Commands expect BTCUSDT_trades_2026-05-25_04.parquet, _12.parquet, _18.parquet, and the May 26 _15.parquet and _21.parquet files.

```bash
python train_receipt.py --repo . --upload raw
python receipt_predict.py --repo . --upload raw
python audit_receipt_model.py --repo . --upload raw
python -m unittest discover -s tests -p 'test*receipt*.py' -v
```

The inference CLI demonstrates historical replay. For integration, construct observed feature rows using the receipt policy and pass the last 16 valid rows to `ReceiptPredictor(checkpoint_directory).predict(context)`. It does not subscribe to an exchange or send orders. Connecting a feed requires the same valid book reconstruction, receipt stamps, gap handling and buffering of current-receipt ties.

## Next implementation direction

Keep this receipt policy as the input boundary. Next add fixed-clock, trailing summaries and half-tick-preserving relative-price tokens, then compare against this saved development baseline. Reserve additional contiguous recordings for subsequent confirmation before inspecting their outcomes. Execution-latency replay and costs must precede any profitable-policy claim. Raw-file spillover completeness and duplicate messages still need independent source verification. The existing live deployment was not changed by this experiment.
