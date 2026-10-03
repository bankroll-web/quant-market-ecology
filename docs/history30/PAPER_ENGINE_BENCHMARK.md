# Paper engine historical replay and extrapolation guard

A fixed expected-return ridge model trained on 459 first-half-hour Binance futures examples was replayed across 8,132 second-half/later-hour examples from eight previously inspected recordings. It is a development check, not untouched validation, and is not the venue-specific live model.

The unguarded regression produced extremely large predictions on a few later states (up to approximately 4,784 bps), while their observed one-second returns were small. Fourteen unguarded threshold crossings across four recordings yielded negative average quote-proxy net outcomes in every recording with entries. See [original unguarded diagnostics](PAPER_ENGINE_UNGUARDED.json). These are extrapolation failures, not detected market opportunities.

The live paper engine now stores training feature minima/maxima and rejects any input outside those bounds, or without available bounds, before showing BUY/SELL. Historical replay applies the same support mask to entry screening. This conservative box is an engineering guard, not a full joint-distribution detector; an input inside every marginal range can still be unusual. Forecast MSE in the report remains the unmasked diagnostic over all examples, so it exposes poor extrapolation rather than hiding it. The guard does not fix the model or demonstrate profitability.

[Guarded results](PAPER_ENGINE_BENCHMARK.json) and input hashes are reproducible with `python -m src.simulation.paper_engine_benchmark .`. Costs and execution use immediate bid/ask proxies plus assumed 6 bps roundtrip fees/slippage. No actual orders, size effects, funding, latency or independent qualification are represented.
