# Coinbase training pipeline

The live Coinbase feature adapter deployment was confirmed live before this change. This addition supplies an offline venue-specific fitting pipeline and live feature-capture counters. This offline entry point does not enable BUY/SELL orders. A subsequent [service-side research path](LIVE_RESEARCH_TRAINING.md) now also fits directly received features in the background, without reading private segments.

`coinbase_training.dataset` reads only completed capture segments with verified byte hashes and record counts. Feature inputs must be Coinbase Exchange BTC-USD. Targets span approximately one second, at most 250ms endpoint lag. Session changes, update-counter resets, receipt gaps above 250ms and receipt/event age outside 0–250ms reject an interval. Decisions are separated by at least one second; endpoint lag can still overlap targets. Hash verification establishes stored-byte integrity, not exchange feed completeness.

The trainer fits the existing fixed ridge-logistic model and transforms on resolved labels in the first half of the capture timeline, then compares against a constant training base rate on the later half. It reports Brier/interval scoring. No later outcome enters training. Fewer than 400 usable examples produces an explicit insufficient-data report instead of a fitted artifact. This is an engineering floor, not statistical validation. New-day holdout testing and cost-aware paper execution remain required.

Run with numpy installed:

```bash
python -m src.simulation.coinbase_training /private/capture/*.manifest.json --out coinbase_training_report.json
```

The source recordings are private service files. This implementation has not retrieved or trained on the deployed service's recordings; only a synthetic test capture was used to verify manifest handling and the insufficient-data boundary. No real Coinbase training result is claimed. Training requires completed recording segments to be available to the offline runner.

The live `training_capture` field reports feature bundle count for the current connection, and resets on invalidation. It does not pretend bundles are independent labeled examples. The dashboard displays this distinction. Free-service recordings are ephemeral and may disappear on deployment or restart. Do not infer sufficient training data from the counter.

Future paper policies need return magnitude, fees, latency, inventory and execution assumptions; probability alone is insufficient. The model artifact remains unqualified and is never automatically installed into live trading.
