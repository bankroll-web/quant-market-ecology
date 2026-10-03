# River integration: first Bitcoin token replay

River online-ml/river (not the paid River AI LLM API) is now integrated. Version 0.26.1 was installed and used on the real receipt-token corpus. No paid service, API key, new data transfer or live deployment was used.

First recording: token-bin warmup only. Next two recordings: 10,748 incremental learning contexts. Final two: 11,608 evaluation contexts with model weights frozen. Labels enter the training queue only when target receipt is strictly before the next decision. Token IDs are represented categorically as latest-token indicators and context frequencies, never as ordinal numbers.

| Task | River MSE | Training-mean MSE | Relative error change |
|---|---:|---:|---:|
| return | 0.09987743 | 0.10002643 | -0.149% |
| flow | 1.82613901 | 0.84130765 | +117.060% |
| vol | 0.00121540 | 0.00117456 | +3.477% |

The return error difference is tiny and does not establish a trading edge. Flow and absolute-return-proxy forecasts are worse than their baselines. These are unconstrained linear regression outputs; flow may leave [-1,1] and the proxy may become negative. They are development comparators, not executable estimates. ADWIN flagged five shifts in return-error behaviour, processed in target receipt order; it did not reset or update the frozen models.

This first integration is three lightweight River linear models with fixed SGD settings, not a transformer replacement or a completed strategy. Its two-hour learning protocol and first-hour-only token bins differ from the previous transformer experiment; cross-run scores are not a fair model ranking. All recordings were already examined. No costs, latency or PnL were tested.

STATE.json saves numerical coefficients, intercepts and tokenizer state without pickle. AUDIT.json verifies restored predictions and source-code hash. Restoration touches River 0.26.1 internal VectorDict because its public weights property returns a copy; use the pinned version. This is an experimental checkpoint format, not a portable River-wide serialization guarantee.

Run from the repository root in an environment with river==0.26.1, numpy, pandas, pyarrow and zstandard:

```bash
python river_token_trial.py --repo . --upload raw
```

The hosted token dashboard remains the existing transformer replay. This new River result is saved separately and has not been deployed into the live feed.
