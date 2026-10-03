# Live model readiness integration

The ecology endpoint now includes `model_status` and the live laboratory displays its signal and reasons. A frozen research model artifact is bundled with the dependency-light observer image. The implementation uses standard-library inference, with no numpy dependency in the live process.

The current signal is WAIT. The research artifact was fitted on Binance Futures BTCUSDT, while the active Coinbase spot feed is a different product. Exact receipt-bundle OFI and compatible feature lineage are also not supplied through the current live view. The model therefore does not emit a probability on that feed. It is not being retrained online.

If a future compatible adapter supplies all five ordered features with a fresh availability timestamp and a matching venue, the module can return an explicitly exploratory positive-return probability. It still emits WAIT because the artifact has no qualified cost-aware policy. Probability of a strictly positive one-second midpoint return is not a buy/sell recommendation and does not describe return magnitude or trading costs.

Unavailable feeds, future feature timestamps, stale features, wrong dimensions and nonfinite quantities suppress inference. Dashboard load failures clear the signal to WAIT. The current runtime never places orders. No trading thresholds are fabricated to transform an inconsistent development model into buy/sell signals.

Next: capture contiguous same-venue live data, build the exact bundle-feature adapter, fit and freeze a venue-specific model, evaluate chronological paper policies including costs, and then enable paper BUY/SELL/WAIT with documented decision rules. This change delivers live readiness visibility, not the finished live trading-policy system.
