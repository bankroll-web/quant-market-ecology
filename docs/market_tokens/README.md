# Market activity as a token sequence

This is a new research direction requested by the user, not a claim that prior strategies were profitable. Earlier regressions/trees do not test a dedicated autoregressive market language model.

## Research basis

- Chronos scales and quantizes numerical time series into tokens and trains transformer language-model architectures with a next-token objective: https://www.amazon.science/publications/chronos-learning-the-language-of-time-series . This supports the representation/method, not guaranteed financial profitability.
- Nagy et al., Generative AI for End-to-End Limit Order Book Modelling (2023), encode individual NASDAQ LOBSTER messages and process tokenized messages and states with a structured state-space model: https://arxiv.org/abs/2309.00638 . Our aggregated Binance displayed-book states cannot reproduce its order-ID/message data.
- LOB-Bench (ICML2025) evaluates generated order-book messages through distributional tests, spreads, depths, inter-arrival timing and price response: https://proceedings.mlr.press/v267/nagy25a.html . Realistic simulation and profitable execution are separate evaluation tasks.

## Implemented now

`src/simulation/market_tokens.py` creates a training-only typed tokenizer for eight measured state features: top-book imbalance, depth imbalance, log depth, spread, OFI/depth, bid/ask net displayed changes/depth and the most recent observed mid-price log change. The price change uses a valid preceding receipt only; recording gaps/episode changes reset that predecessor. These are observations of displayed liquidity, not known retail/institution/market-maker identities or identified cancellations.

Sixteen training-quantile bins per field plus explicit below/above-training-range tokens give147 token IDs, including reserved BOS/EOS/GAP IDs. Tokens preserve field identity. Repeated quantiles in constant fields may produce unused categories. Finite inputs are required. Numeric raw prices and target returns must be retained alongside tokens: quantization discards precision.

Contexts contain32 consecutive valid receipts, eight field tokens per receipt and BOS/EOS:258 tokens. They reset at episode changes, future-timestamp events, crossed books, nonpositive depth, reversed receipt timing or a gap above250ms. GAP is reserved; resets currently separate contexts rather than inserting it. Contexts overlap; their number is not an independent sample size. Exact receipt timestamps remain metadata, not a complete elapsed-time token vocabulary. Future target labels never enter input tokens.

Tokenizer boundaries are fitted only to valid raw observations before the same first-half-hour cutoff used in the previous book studies. ENCODER_AUDIT.json records the fitted cuts, train ranges, example contexts, range flags and source hashes. It is an encoding/continuity audit, not a forecast or trading result. All eight historical recordings were previously inspected.

No neural sequence predictor has been trained at this stage. The current runtime has no PyTorch installed. The encoder and checks run with the existing numerical research dependencies; no paid service or deployed signal change is involved.

## Next model experiment

1. Freeze a compact context vocabulary, add explicit elapsed-time/duration encoding and preserve numerical targets. Audit quantization error and tail-token frequency. Keep individual-message data distinct from aggregated-state data.
2. Establish a small next-token/count-based baseline, then a small causal transformer/state-space model trained to predict distributions of future price changes and liquidity states. A trainable financial model learns from recorded market sequences; tokens alone do not supply an edge. Check joint/conditional probabilities and calibration, not merely classification accuracy.
3. Separate simulator fidelity from trading utility. Check spread/depth/event-duration distributions, tail behavior and conditional price-response functions for generated paths. Do not identify synthetic participants as observed traders.
4. Compare price-history-only, ecology-state-only and combined sequence inputs at equal timestamps/horizons with regression/count baselines. Use identical cost/fill assumptions. Training/model selection remain chronological; heavily overlapping contexts need purging and episode boundaries. These already-seen recordings support development comparisons only.
5. Freeze the chosen recipe, then reserve new contiguous recordings and forward paper evaluation. Candidate BUY/SELL/WAIT decisions require supported states, calibrated uncertainty and estimated executable returns above costs. No promotion from token loss/perplexity or simulated realism alone.

This initial codec is not a Chronos or Nagy replication and is not yet a full market-event language model. It is a concrete foundation for testing the user's proposal.

## Reproduce

```bash
python -m src.simulation.market_tokens .
python -m unittest discover -s tests -p test_simulation_market_tokens.py
```

The tests verify field identity, explicit extreme-value tokens, discontinuity/episode resets and rejection of future-event contexts. They verify encoding behavior, not alpha.
