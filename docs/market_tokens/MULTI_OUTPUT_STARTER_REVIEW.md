# Uploaded multi-output market-language starter: audit and repairs

Source: Pasted text(20261003-130241).txt. Repaired development copy: src/simulation/market_lm_starter.py. This is a separate five-field model skeleton, not yet an integration with the six-field event vocabulary or a real-data training result.

The model learns next-event fields, ordered return quantiles for 10/50/200-event horizons, a future mean-absolute-return volatility proxy and signed traded flow. Summed field embeddings preserve separate field dictionaries. Causal attention blocks future context. The forward-looking targets are legitimate labels only when their complete horizons are resolved before training.

## Repaired

- Return scalers previously included R[:train_end], whose final h observations use mid prices after train_end. Each horizon now fits only R[:train_end-h]. Volatility scaling similarly excludes unresolved VOL_WIN targets.
- The evaluation unconditional quantile baseline previously used those unresolved training-tail labels. It now applies the same horizon-specific exclusion.
- Broadcast loss masks previously counted one horizon mask while summing five quantiles. The masked mean now counts the expanded mask, making quantile-loss weights interpretable.
- ModuleDict key "type" collides with nn.Module.type, preventing initialization. Internal keys now use field_ prefixes.
- Size and interarrival fields now use log1p before quantile fitting.
- The calibration helper now uses a finite-sample order statistic, rejects invalid data, returns infinity when the requested rank exceeds the sample size, and never narrows a band advertised as widening. This is not a coverage guarantee for dependent market sequences.
- Baseline tensors are moved to the evaluation device; empty evaluation slices reject explicitly.
- Raw lengths/finite values, positive mids and nonnegative sizes/gaps are checked.
- Unvalidated token rollout rejects explicitly rather than exposing the toy resting-count mask as a usable market simulator.
- Output wording no longer calls lower pinball loss a real trading edge. Synthetic results are explicitly marked synthetic.

## Checks completed

Four tests pass: modifying all mids/sizes after the train cutoff leaves training scalers, training tokens and fully resolved training targets unchanged; broadcast averaging returns the actual mean; conformal calibration selects the expected order statistic; a small synthetic forward/backward pass has finite loss and changing future context does not affect earlier predictions.

No full training, real-data forecasts, PnL or simulation validation was performed. These tests establish specific software properties, not broad validation.

## Remaining integration work

This input has five fields and no participant tag, missing/out-of-range IDs, summary-scale vocabulary, receipt timestamps, exchange clock alignment, validity episodes or gaps. It must be connected to the existing six-field encoder rather than pretending its synthetic data is observed Bitcoin data. Targets are event-count horizons, not constant wall-clock horizons. Sizes and side conventions must agree across source adapters.

Its synthetic generator deliberately inserts a weak flow/return relation; recovering that relation is not market evidence. No intraday training should use fabricated add/cancel labels from aggregated book decreases. Match next-event eligibility and full target availability to gap/episode validity before real-data training.

Current evaluation pools horizons and averages minibatch means, so the final short batch is over-weighted. Replace with per-horizon observation-weighted sums before publishing empirical performance. Include volatility/flow scores, interval widths, calibration by regime, effective sample/dependence analysis, simple n-gram and gradient-boosting baselines. No calibrated signal promotion is implemented.

The ordinal level smoothing is sensible only when level IDs preserve numeric order. It cannot be transferred unchanged to our signed magnitude vocabulary, where adjacent IDs may not mean adjacent price levels. Return quantiles are non-crossing by construction, but this alone does not establish accurate uncertainty.

Transformer cloned-layer initialization, bounded context checks, complete saved preprocessing/model artifacts and repeated-seed determinism remain further engineering work before training this skeleton. No pretrained weights are used. Split-conformal calibration must be held separate from model selection and final evaluation; time dependence requires explicit assumptions and suitable evaluation.

Token rollout is disabled until a proper book engine validates price/size, resting liquidity, conservation, fills and impact, and held-out tail/clustering/flow-memory comparisons pass. It currently has no mapping from generated event fields to resulting prices, so stylized_facts cannot validate its rollout returns.
