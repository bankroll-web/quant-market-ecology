# October 3 research integration

Ten supplied PDFs were reviewed for scope, methods and transfer to Market Ecology. This review uses the attached versions; publication status, claimed results, proofs and external code have not been independently verified. Source fingerprints and page counts: [manifest](OCTOBER_3_PAPER_SOURCES.json). No paper's reported performance is a result of our system.

## Decisions for each paper

| Supplied paper | Relevant contribution | Integration decision and boundary |
|---|---|---|
| FinBench: Time-Gated Calibration and Uncertainty Benchmarking for Agentic Financial Forecasting | Availability-constrained forecasting, Brier probability loss and Winkler interval score; reported pilot is only 33 forecasts | Implement reusable time and scoring checks now. Its small pilot does not establish robust superiority or profitability. |
| Cryptocurrency Volatility and Tail Risk: ARMA-GARCH-X | Asset-specific volatility and VaR/ES evaluation; compares many specifications and reports heterogeneous gains | Keep a separate risk-model experiment using longer contiguous return history and release-timed covariates. The present selected hours are insufficient for faithful reproduction. Do not search thousands of variants against the same evaluation sample. |
| Confidence and Competence in Investor Cognition | Cross-sectional distinction between self-assessment and measured competence | Use as motivation for comparing confidence with measured performance. Do not turn U.S. survey associations into order-book participant parameters. Its “high-frequency” trading measure is not exchange HFT. |
| S-band Antenna Angles Data Calibration using Spacecraft Tracking | Batch least squares and designed observation coverage for instrument calibration | General measurement analogy only. Spacecraft dynamics and antenna error coefficients have no direct market interpretation. No financial model imported. |
| Optimal Quoting under Adverse Selection and Price Reading | Inventory-aware quoting with client tiers, size-dependent arrivals, informed flow and information revealed by quote skew | Candidate separate OTC model. Adapt inventory and adverse-selection hypotheses only after defining the exchange queue/fill model. Anonymous BTC L2 does not reveal client tiers, dealer inventory or quote-reading intent. |
| Dynamic Slippage Control and Rejection Feedback in Spot FX Market Making | Joint quote/slippage control, latency price moves and rejection-feedback effects on client intensity | OTC last-look branch only. A resting Binance limit order cannot reject a matched trade after observing an adverse move. Transfer latency sensitivity and execution-cost measurement, not the rejection privilege. |
| Competition in Dealer Markets with Internalisation and Externalisation | Inventory-driven quote skew, active hedging, competition and transient impact in a dealer game | Separate multi-dealer experiment with explicit inventory, cash and hedging costs. Do not interpret public trade signs as known internaliser/externaliser identities or copy its Nash equilibrium into an L2 exchange. |
| 2608.16155v1: REFLEX | Quotes change the flow later used to retrain the policy; proposes stability margins in a structural OTC model | Add policy-induced distribution-shift and retraining-stability experiments later. The paper's structural modulus is not a universal stability certificate for our simulator or live BTC. |
| SSRN-id4119858: Dynamics of Market Making Algorithms in Dealer Markets | Intensity-control dealer game; decentralized actor/critic learning can produce spreads above competitive benchmarks in its model | Future frozen-environment multi-agent experiment, comparing non-learning baselines, inventories, spreads and client costs. Do not label real-market collusion from a simulated spread increase. |
| Temporal Obfuscation Testing for LLM Structural Reasoning | Remove dates/tickers and use negative controls; paper distinguishes pattern detection from economic alpha | Use as a future LLM robustness test. Obfuscation alone cannot exclude memorization or prove causal reasoning. Its open-interest sign convention is an assumption, not observed dealer positioning. GEX requires an option chain, volatility surface, contract units and explicit signed positions. |

## Implemented in this change

`src/simulation/forecast_evaluation.py` provides three evaluation components:

- `gate_inputs`: every input records event time and availability time; both must be no later than the decision time. This prevents a release delivered late from appearing available at its earlier event timestamp.
- `gate_training`: target endpoints and label availability must be resolved before training. It prevents using a future-completed outcome merely because its row starts earlier.
- `score`: Brier loss for strictly positive return and Winkler interval loss at a chosen miscoverage (default 20%, or an 80% interval), with empirical coverage. Return and interval units must match. `skill` compares aggregate loss with a baseline and returns missing when baseline loss is zero.

The formulas are standard proper-scoring rules used by FinBench:

\[
 B=\frac1N\sum_i(p_i-\mathbf1\{r_i>0\})^2,
\quad W_i=(U_i-L_i)+\frac2\alpha(L_i-r_i)_++\frac2\alpha(r_i-U_i)_+.
\]

A zero return belongs to class 0; in a discrete-price market this convention must be reported. Brier loss combines calibration and discrimination; a low score alone is not proof of calibration. Prediction interval coverage also needs width-sensitive scoring. Neither metric estimates trading profit.

These are callable checks, not an assertion that every existing pipeline is now guarded. Input lineage, fitted-transform cutoffs, model/pretraining contamination, clock uncertainty, chronological splits, target-overlap purging and frozen evaluation periods still need explicit integration. Unit tests verify late-release rejection, unresolved-label rejection, scoring arithmetic, zero returns and invalid values. No ML policy was trained in this change, no external paper result reproduced, and the live dashboard is unchanged.

## Next executable integration

Continue the empirical liquidity-path environment using authoritative price-level L2 updates and receipt clocks. Keep trades as annotations so reductions are not applied twice. A policy must observe only the current and past state. Completed-window liquidity-response labels stay analysis targets. Frozen benchmark paths can then compare inventory-aware quoting against fixed-quote and no-trade baselines with latency, fees, queue uncertainty and adverse-selection markouts explicitly stated.

A generative maker model is a separate task: historical replay cannot tell us how other participants would respond to a newly introduced policy. Additional contiguous same-venue days remain necessary for new validation. More papers do not replace this data requirement.
