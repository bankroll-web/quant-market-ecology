# Fixed daily crossasset LASSO protocol — 2026-10-03

Written before inspecting crossasset backtest outcomes. This adapts Santos/Sebastião/Silva's Bitcoin/altcoin paper, not a replication of its Yahoo/marketwide USD series or its headline returns.

Data: checksum-verified Binance spot UTC daily klines, 2023-01-01 through 2026-08-31 inclusive. Fixed paper universe BTC, ETH, DOGE, BNB, XRP, ADA, LTC, TRX, LINK, ETC against USDT. Require identical contiguous dates, no interpolation and valid positive prices/quote volumes. Normalize official millisecond/pre2025 and microsecond/post2025 timestamps to nanoseconds. Bars cannot be observed before close. USDT quote volume is not consolidated USD volume.

Two fixed models: BTC-only and all ten coins. Four variables per coin: close-to-close log return (basis points), log quote volume, Parkinson daily variance log(high/low)^2/(4 log2), Amihud abs(log return)/quote volume ×1e8. Include current completed daily value and six preceding lags. These are market-state proxies, not identified dealer/retail positions. No Granger causal claim.

At completed feature day i, observation is available at opening of day i+1. Execute at opening of day i+2 (one full daily bar of processing delay); target is BTC open i+3/open i+2 log return. Training may use only rows j with target open j+3 at or before observation time i+1 (j<=i-2). Each fit uses the latest714 resolved rows. No overlapping daily target intervals.

Fit training-only StandardScaler and Lasso on return in basis points. Pick alpha from0.1,1,5 with five expanding chronological TimeSeriesSplit folds and gap2 on the FIRST714 resolved rows only, minimizing mean squared forecast error. Freeze that alpha and all trading rules for all subsequent fits. Convergence warnings must be recorded. Each rolling fit uses already resolved history; this is a frozen recipe, not frozen weights.

Long/flat state machine: forecast above+25bps enters/stays long; below-25bps exits/stays cash; otherwise keep prior position. Start cash. Charge25bps per executed side (paper benchmark), with fixed5/10bps side-cost sensitivities that do NOT alter signals. Equity holds from execution open to following open and deducts turnover costs. Liquidate at the final available target open and charge a sell fee. Buy-and-hold pays the same entry/exit costs on matching dates; cash baseline unchanged.

Report development execution dates2025-01-01–2025-06-30 separately from execution dates2025-07-01–2026-08-30. The latter is a chronological evaluation of a new recipe; some project research already inspected2026 market periods, so it is not wholly untouched project-level evidence. Never optimize rules after looking at it and still call it held out. The final rolling fit may learn earlier resolved evaluation labels as specified before testing. Independently initialize cash and liquidate at each segment boundary; no portfolio state transfer.

Metrics: cumulative net return, maximum drawdown, daily risk-adjusted performance, turnover count, exposure, forecast MSE vs zero/training-mean, per-year summaries. Compare crossasset vs BTC-only forecast errors with paired stationary bootstrap (geometric blocks mean7 days,5000 resamples,seed91). Any multiple hypothesis claim needs adjustment; no selecting best sensitivity as a certified outcome.

Constraints: all prices are idealized daily opens, not actual bid/ask fills; latency after open, spread, market impact, order size and stablecoin risk remain unmodeled beyond the fee assumption. Fixed ten-coin universe excludes other/delisted tokens. Two fitted approaches and selected alpha are disclosed. No live deployment, no orders, no profitability qualification based on a single historical result.
