# Live paper research signal panel

The live venue-specific trainer now fits an expected one-second midpoint-return model alongside its directional probability model. Standardized ridge regression uses fixed penalty 0.1, training-only scaling and the existing chronological label-availability split. This remains repeated development fitting, not independent validation.

The PAPER RESEARCH panel can show BUY, SELL or WAIT. BUY/SELL mean hypothetical directional exposure for a one-second research horizon, not an instruction to place an order. SELL is hypothetical short exposure, not a statement that a spot account supports shorting. No orders are enabled; the main qualified trading signal remains WAIT.

Required gates: matching venue/symbol, research-usable feed, feature receipt and engine ages each <=250 ms and nonnegative, model labels no older than ten minutes, development MSE below a zero-return baseline, and at least 20 development candidates with positive mean after assumed costs. Those gates are engineering screening choices, not statistical qualification. Current expected movement must exceed an assumed 6 bps roundtrip cost plus 2 bps buffer in either direction. Fees/slippage are assumptions, not account-specific execution costs. Midpoint targets omit executable spread, impact, funding and fills.

When any gate fails, the panel shows WAIT with reasons. Binary direction probability is not converted directly into a trade; the panel uses an explicit expected-return estimate. Historical reversal candidates that failed costs are not promoted into this panel.

The next step is to freeze a candidate model for prospective paper evaluation with executable quotes and independent observations. This panel has no paper portfolio, completed-trade ledger or actual execution yet. It does not establish profitability.

## Frozen prospective outcome ledger

The service freezes the first fitted return-model report and evaluates it for ten minutes. The visible paper candidate uses that same frozen model; training may continue separately but cannot alter this evaluation. After the window, the candidate returns to WAIT for review. The ledger does not auto-select or promote a replacement model. Venue mismatch blocks resolution and entries.

Each fresh decision records an expected one-second midpoint move. The first eligible published observation at least one second later, with a feature receipt at or after that horizon, resolves it; observations later than 1.25 seconds invalidate the trial. Feed quality failures also invalidate pending observations, and rejected counts are reported. Decisions are at least 1.25 seconds apart. Forecast MSE is compared with zero-return MSE on resolved observations, conditional on data surviving the freshness filters. Rejection rates can create selection effects.

BUY proxies enter at the displayed ask and exit at the later bid; SELL proxies enter at the bid and exit at the later ask. Deduct 6 bps assumed fee/slippage cost after quote spread, with no actual orders, queue model, inventory or size-dependent execution. SELL does not establish spot borrow availability. Sum of per-entry bps is not an account return. No portfolio drawdown or profitability qualification is supplied. Only twenty latest outcomes plus bounded summary counters are retained; all state is lost on restart. This is a prospective diagnostic ledger, not completed market validation.
