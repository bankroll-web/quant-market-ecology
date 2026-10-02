# Market Ecology: end goal and remaining development

Updated 3 October 2026, South Africa.

## End goal

A working research and decision engine that observes live markets, measures how trading pressure and liquidity interact, reproduces those interactions in a calibrated simulator, and evaluates systematic actions under uncertainty and execution costs. Its outputs should explain what the observations support, show data confidence and risk, and allow the system to choose no trade.

The engineering goal is a reliable, reproducible machine. Profitability is an empirical acceptance condition for a trading policy, not a promised consequence of assembling mathematical models. An explanatory model of an observed price reaction is not automatically a forecasting model or an execution strategy.

## Where the project stands

The live observer and synthetic ecology laboratory exist. Eight selected historical periods from a two-day archive now supply 8,300 audited one-second windows. We have measured liquidity reinforcement/opposition, conditional price distributions and frozen regression failures. Anonymous depth and trades do not establish actual retail/institution/market-maker identities or psychology; role-specific simulations must expose their assumptions.

The latest [response-model comparison](ROBUST_ECOLOGY_RESPONSE.md) addresses extreme initial-queue normalization. It compares three fixed alternatives with the original linear fit, training only on 25 May 00:00. The time-weighted depth alternative reduces all-window explanatory RMSE in each of the seven subsequent periods; freshness results and uncertainty are mixed. No model or policy is promoted into live trading.

## Remaining processes and acceptance conditions

| Stage | Work | Evidence required before moving on | Current position |
|---|---|---|---|
| 1. Reliable observations | Validate receipt/event clocks, sequence continuity, trade payloads, gaps, source hashes and capture coverage. Keep venue identity explicit. | Repeatable paired book/trade reconstruction; excluded gaps and missing data reported; sufficient contiguous coverage. | Audits implemented; existing selected archive inspected. New contiguous same-venue days still needed. |
| 2. Ecology response and calibration | Compare pressure, replenishment/opposition, changing depth, response tails and recovery. Specify bounded/nonlinear hypotheses before new evaluation. | Effects and calibration stability replicate beyond the two-day archive, including quiet/busy and thin/deep conditions. | Conditional mechanism measured; robust normalization candidates tested exploratorily. |
| 3. Calibrated event simulator | Model state-dependent event timing, quantities, depth transitions and response dynamics. Simulated makers have explicit inventory/quoting assumptions. | On frozen environments, reproduce distributions of spread, depth, activity bursts, imbalance, price reaction and recovery; compare interventions with uncertainty. | Synthetic lab exists; complete empirical simulator validation remains. |
| 4. Systematic policies and machine learning | Compare simple/tabular benchmarks first, then actor-critic/deep-set or other justified models on the same frozen environments. Train without future observations or repeated use of final periods. | Independent walk-forward results, calibration checks, sensitivity to seeds and regimes, and gains over simpler/no-trade alternatives. | Earlier policy experiments have not qualified. No validated profitable policy. |
| 5. Executable paper testing | Use actual venue fees/funding, spread, latency, queue/fill assumptions, slippage, inventory constraints and realistic missing-data behavior. Reconcile paper fills with observations. | Positive cost-adjusted performance with adequate effective samples, drawdown/tail-risk limits and robustness to plausible execution stress. | Paper-test framework exists; a qualifying policy remains to be established. |
| 6. Live shadow operation and controlled execution | Record live inputs and proposed actions; keep paper positions and risk controls visible. Stop on stale data or broken reconstruction. | Historical/live parity, stable shadow results, verified operational controls and explicit authorization before any real-money execution. | Live observation works; no qualified trained policy is enabled for real-money execution. |

These stages overlap in engineering, but evidence gates prevent a later dashboard or sophisticated learner from substituting for validation. A new hypothesis may return the project to earlier calibration work. A strategy that fails its gate stays a research result.

## Options, GEX and participant extensions

A coupled option/hedge module requires an option chain, a volatility surface and explicitly stated signed-position assumptions. Open interest alone does not reveal dealer inventory. Funding, basis and derivatives state need synchronized same-venue sources and their own observation audit. Macro bubbles and venue auctions remain separate branches until their data and mechanisms are validated; they should not be silently mixed into the intraday simulator.

## Immediate next input and next experiment

The highest-value input is additional **contiguous days of paired book and trade data from the same historical venue/product**, with source metadata and exchange update/trade identifiers. The live Coinbase feed requires separate venue calibration; it cannot be treated as independent replication of a Binance Futures coefficient.

For new data, freeze the observation rules and response candidates before inspection, reserve genuinely untouched final periods, and compare the original model, training-quantile clipping, asinh compression and time-weighted depth without adding candidates in response to final-test outcomes. Then validate the event environment against the measured joint distributions before training richer policies.

The project can continue engineering and exploratory research with the current archive. The archive cannot supply independent new-day validation by repeatedly splitting, bootstrapping or refitting the same observations.

Related: [main guide](MARKET_ECOLOGY_SIMULATION.md), [ecology price study](ECOLOGY_PRICE_MECHANICS.md), [additional-period replication](ECOLOGY_MECHANICS_REPLICATION.md), [response comparison](ROBUST_ECOLOGY_RESPONSE.md).
