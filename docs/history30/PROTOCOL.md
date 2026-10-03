# Thirty-day trade-flow protocol

Frozen before archive extraction on 3 October 2026. Source: Binance USD-M BTCUSDT aggregate trades, 1–30 September 2026 UTC. This is a new trade-flow branch, not a replacement for L2 ecology validation.

Use nonoverlapping five-minute feature blocks. Predict the immediately following block's first-to-last trade return. Features: signed aggressor volume imbalance, current block return, log volume, log aggregate-trade count and high/low range. Fit standardized linear ridge with fixed penalty 0.1 on 1–20 September. Labels must end before the validation boundary. Select one excess-cost buffer from 0, 2, 5 bps on 21–25 September, or retain no-trade if every candidate loses. Freeze model and selection before computing 26–30 September results. Never retrain on test data in this run.

Compare MSE to zero and training-mean forecasts. Report a daily-block bootstrap interval for MSE difference, acknowledging only five test days. Base roundtrip assumed cost: 6 bps (2 bps per side fees plus 1 bp per side slippage). Report 2/6/12 bps sensitivity without reselecting the policy. Trade prints are execution proxies, not actual fills; no funding, L2, queue or receipt-latency validation. Thirty days does not guarantee profitability or independent long-run robustness.
