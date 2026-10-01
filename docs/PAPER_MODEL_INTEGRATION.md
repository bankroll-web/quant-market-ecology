# Paper-derived model research

This package opens a separate research track authorized on 2026-10-01.
It does not alter EXP-01, DBR, BTC_V3, or the Paper Engine V1 specification.
It is not a trained strategy or a reproduction of the papers' reported results.

## Source-to-implementation map

| Uploaded source | Candidate component | Current status / prerequisite |
|---|---|---|
| 056e459f9e6723607e93a931b6e0608e3343.pdf: Reinforcement Learning Approaches to Optimal Market Making | RL formulation, inventory-aware analytical benchmarks | Design reference; baseline and simulator required |
| MMarxiv4.pdf: Market Making under a Weakly Consistent Limit Order Book Model | Consistent book transitions, price-time priority, execution validation | Design reference; L2 does not reveal exact queue position |
| An_Impulse_Control_Approach_to_Market_Making_in_a_.pdf | Hawkes arrivals, intervention timing, PPO | Causal exponential intensity filter implemented; full LOB simulator, calibration and PPO pending |
| Multi-Level_Market_Making_with_Reinforcement_Learn.pdf | Multi-level order allocation, logistic-normal actions, deep-set encoder, reward shaping | Pending validated simulator and simple baselines |
| Online_Market_Making_and_the_Value_of_Observing_th.pdf | Online learning under action-dependent partial feedback | Pending observation-model audit; private trader valuations are not observed in our L2 data |
| Learning_Market_Making_with_Closing_Auctions.pdf | Auction-aware Deep Q-Learning | Deferred to an auction venue and auction data |
| main.pdf: Option Market Making with Hedging-Induced Market Impact | Cox option arrivals, quote/hedge control, underlying impact | Deferred to options quotes/trades and underlying/hedging data |
| 22642-ArticleText-61628-1-10-20220607.pdf | SADF/GSADF explosive-regime diagnostics | Separate macro research candidate; requires longer price history and calibrated critical values |
| PublishedArticleWJAETS-2025-0535.pdf | Liquidity and risk background | Reference only; no specific trained model implemented |
| The_hidden_role_of_market-making_in_the_rise_of_fa.pdf | Farmed salmon consumer-market formation | Excluded from financial modeling |

## Implemented foundation

`src/model_research/hawkes.py` implements a small, standard multivariate
exponential Hawkes filter inspired by the Hawkes paper. It is not its full
12-event simulator, impulse-control solution, or two-network PPO agent.

For target event i and source event j:

    lambda_i(t-) = mu_i + sum_j sum_{s<t,type(s)=j} alpha_ij exp(-beta(t-s))

Use seconds, baseline intensities in events/second, alpha in events/second,
and beta in inverse seconds. Outputs from `observe` exclude the current
event's excitation; subsequent queries include it. Parameters are supplied
explicitly, not fitted. A conservative maximum-row-sum stability bound is
enforced. Reset on every verified episode boundary and data gap; define and
report a warm-up period before evaluating empty-history initializations.

Tied event timestamps are rejected. Establish exchange sequence ordering or
develop an explicitly bucketed model before using tied records. Do not label
D07 removals as cancellations or feed aggregate L2 changes as known individual
order submissions. Initially use event types verified from trade records.

Run the analytical tests without extra dependencies:

    python tests/test_model_research_hawkes.py

## Integration gates

1. Finish the existing V1 latency, execution-reference, cost and outcome gates.
2. Audit the observed trade-event mapping and timestamp ties. Add an adapter
   from validated upstream data, with episode identity and causal timestamps.
3. Fit Poisson and Hawkes baselines on genuinely new training dates; evaluate
   held-out point-process likelihood, time-rescaling residuals and stability.
   Frozen May hours remain debugging/regression data, never training/tuning data.
4. Build a separate market-making environment with conservative L2 fill bounds,
   inventory accounting, fees, latency, partial fills, cancel latency and terminal
   inventory handling. Historical replay cannot model our endogenous impact;
   report that limitation and stress-test alternate execution assumptions.
5. Compare fixed quotes and an inventory-aware analytical benchmark before
   adding a simple RL action space. Freeze chronological train/validation/test
   dates, feature provenance and evaluation criteria before inspecting outcomes.
6. Add multi-level allocation and impulse control as separate ablations only
   after the simpler environment passes accounting and causality tests.

The Hawkes paper itself discusses unrealistic pump-and-dump behavior under
some exponential-kernel specifications. Intensity filtering alone does not
establish an arbitrage-consistent price/impact simulator. Simulator gains and
high reported Sharpe ratios are not evidence of deployable BTC profitability.

Report net simulated results, inventory exposure, turnover, fill sensitivity,
drawdowns and variation across independent dates. No live-order path is added.
