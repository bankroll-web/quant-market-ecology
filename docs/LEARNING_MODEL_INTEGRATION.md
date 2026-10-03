# Paper integration and machine-learning fitting standard

**Status:** executable research modules, with a trained synthetic policy. No live-data training, exchange execution or reliable Bitcoin trading advantage has been established. Existing real-data regression and historical replay remain separate.

## What was built

- `learning_book.py`: an order-level FIFO engine with integer ticks/lots, partial fills, post-only checks, cancellation, explicit self-trade prevention and cash/fee accounting. The original pro-rata ecology experiment remains available.
- `clustered_flow.py`: a two-type exponential Hawkes arrival generator using Ogata thinning. Positive stationary kernels are required. Parameters are assumed, not fitted to Bitcoin.
- `learning_market_maker.py`: finite-episode tabular Q-learning with bounded multi-level quoting, inventory skew, keep/pause/hedge actions, an exported policy, and evaluation on disjoint simulation seeds.
- `test_simulation_learning.py`: queue priority, conservation, direction, fees, capacity, liquidation and policy compatibility tests.

## Mapping the supplied PDFs

| Paper | Principle | Implementation boundary |
| --- | --- | --- |
| Multi-Level Market Making with Reinforcement Learning (2026) | FIFO/partial fills, multi-level actions, wealth-change reward and terminal liquidation | Implemented simplified two-level discrete quoting and tabular Q-learning; no actor-critic, logistic-normal allocation or deep-set encoder. |
| Market Making under a Weakly Consistent Limit Order Book Model (2020) | Order-type direction consistency and price-time priority | FIFO matching and event-local direction/volume tests; not the full marked-point-process/HJB-QVI model. |
| An Impulse Control Approach to Market Making in a Hawkes LOB Market (2025) | Clustered mutually exciting arrivals and discrete interventions | Two-type exponential Hawkes trade arrivals, hold/cancel/requote/hedge actions; no fitted ten-type LOB, PPO, self-imitation or HJB-QVI solver. |
| Reinforcement Learning Approaches to Optimal Market Making (2021) | Inventory-aware learning and benchmarking | Used for the state/action/reward and baseline design; survey performance claims are not transferred to Bitcoin. |
| Option market making with hedging-induced market impact (2026) | Option inventory/hedge feedback, permanent versus transient impact and manipulation checks | Future coupled options module; current hypothetical gamma experiment remains separate. Options quotes, contract terms, hedge timing and signed-position assumptions are required. |
| Learning Market Making with Closing Auctions (2026) | Explicit terminal liquidity event and inventory management | Executable terminal liquidation is adopted, not a closing auction. This continuous Bitcoin sandbox has no auction mechanism; an auction would need a venue-specific extension. |
| Online Market Making and the Value of Observing the Order Book (2026) | Action-dependent feedback and value of book observations | Retained as a future observation/partial-feedback experiment. No-trade observations do not identify private trader valuations in our aggregate data; no regret theorem is claimed. |
| Foreign Exchange Volatility and the Bubble Formation in Financial Markets: Evidence From The COVID-19 Pandemic (2022) | SADF/GSADF right-tailed explosiveness tests on long daily series | Deferred to a separate macro/regime diagnostic requiring long contiguous data and appropriate critical values; not a short-horizon price or RL engine. |
| Market making and liquidity provision: The role of market makers in financial markets (2025) | General inventory, liquidity and operational-risk overview | Background context, not a specific fitted algorithm or empirical Bitcoin calibration source. |
| The hidden role of market-making in the rise of farmed salmon (2025) | Consumer demand and marketing in salmon markets | Excluded from financial matching/learning implementation: market-making has a different meaning here. |

The source filename, SHA-256 and PDF reference-page numbers are preserved in [the paper manifest](LEARNING_PAPER_MANIFEST.json). This is a principles-based implementation and targeted methods review, not a claim to reproduce every paper or verify its empirical results. No PDF text or author code is bundled.

## Mathematics and units

For buy/sell type i, the simulated intensity is `lambda_i(t) = mu + sum_j sum_{u in events_j, u<t} alpha_ij exp(-beta*(t-u))`. Here mu=1.2 events/second/type, beta=1.5/second, diagonal alpha=0.5/second and off-diagonal alpha=0.1/second. The kernel integral matrix has spectral radius `(0.5+0.1)/1.5=0.4`, below one. Burst stress sets mu=2.4 and diagonal alpha=0.8 (radius=0.6). Events start with zero excitation, not from a stationary prehistory.

Prices use $0.10 integer ticks and quantities 0.01 BTC integer lots. These are scenario units, not a verified venue contract specification. Maker fees are zero in training, taker fees 0.5 bps; the fee stress sets maker fees to 1 bp. There are no rebates. Maximum signed inventory is 20 lots = 0.20 BTC. Outstanding bid/ask capacity is counted before posting so resting orders cannot breach this bound under either fill direction.

Inventory q is measured in lots. Wealth at the exogenous reference p is `W = cash + q * 0.01 * p * 0.10`. The one-second reward is `W_next - W_previous - 0.0002*q_before_terminal_liquidation^2` in USDT. Terminal inventory is sold/bought through the book with taker fees. Undiscounted accumulated reward equals final cash less accumulated inventory penalties. This adopts the wealth-change/terminal-accounting principle of Cheridito and Weiss, section 3.3 (PDF pages 5-6); our quadratic penalty changes the objective from their absolute-inventory penalty. No invariant-optimal-policy claim is made.

Q-learning uses `Q(s,a) += 0.2*(reward + max_a Q(next_s,a) - Q(s,a))`; terminal continuation is zero and discount is one. Training exploration falls from 0.8 to a floor of 0.1. Unvisited/all-tied states choose pause. State bins use inventory, previous signed flow, session progress, and observed spread. Coarse bins omit queue positions, excitation and detailed history, so the learner has an approximate/partially observed state, not a proven sufficient Markov state.

## Experiment protocol

Train on seeds 0-199, each 120 synthetic seconds. Freeze the table. Evaluate 30 disjoint seeds 10000-10029 for base, burst, partial rival withdrawal, reference-price jump and 1-bp maker-fee stress. For every scenario/seed, all policies receive the same exogenous event tape. Endogenous fills and wealth differ. Compare learned, fixed-medium quotes, inventory-skew quotes and no-quotes. No tuning or refitting uses evaluation outcomes.

This is simulation-seed generalization only. Historical hours already inspected by the project are not a fresh real-market test. Evaluation never mutates the table; loading and re-evaluating the exported policy reproduced every score exactly.

## Results

| Scenario | Learned mean reward USDT | Fixed medium | Inventory skew | No quotes |
| --- | ---: | ---: | ---: | ---: |
| base | -0.2377 | -2.2145 | +0.1292 | +0.0000 |
| burst | +1.0606 | -0.0096 | +1.6249 | +0.0000 |
| withdrawal | -0.3714 | -1.9464 | -0.1420 | +0.0000 |
| jump | -0.1391 | -1.9705 | +0.2577 | +0.0000 |
| fees_1bps | -25.2859 | -32.1034 | -36.6306 | +0.0000 |

**Decision: do not promote the learned policy.** It improves over fixed-medium quoting in these scenarios but loses to the inventory-skew baseline in four of five. It loses to no-quotes in four of five. The fee stress substantially reduces results. A working training loop is not evidence of a robust strategy.

[Full per-seed results and source hashes](LEARNING_V1_RESULTS.json) and [visual report](LEARNING_V1_REPORT.html). Report cash separately from the reward because risk penalties are an objective, not a cash expense.

## Simulator limitations

Rival quotes refresh every decision second. Each side has four levels with three lots each (more distant levels during withdrawal). Withdrawal is a widened/thinner near-touch rival book, not complete liquidity removal. Agent quotes use two levels, two lots per level, and three width choices. Requoting loses FIFO priority; keep preserves surviving orders. Actions take effect immediately, with no exchange/cancellation latency. Quotes that would cross are moved to the nearest post-only price.

The quote anchor is exogenous: each second it moves by the sign of net synthetic flow plus a noise tick; jump stress adds 100 ticks once. Agent order flow does not affect that anchor. Matching prices obey event-local direction rules, but this is not the fully endogenous ten-type Hawkes LOB from Jain et al. Marking uses the independent reference, so the learner cannot improve its reward merely by moving its own displayed midpoint.

Terminal rival liquidity is artificially replenished to 50 lots per level before actual liquidation. This prevents unfilled residuals under the assumed cap but can understate real stressed exit costs. There is no margin, funding, borrow constraint, multi-venue routing, participant identification, long-horizon regime fitting, options book or live data feed.

## Fitting standard for subsequent development

1. Validate sequence reconstruction, clock alignment, message ages and observation availability before fitting real-data features. Keep future-path quality filters out of deployable sample selection; they can remain retrospective sensitivity diagnostics.
2. Separate fit, model-selection and untouched later-day evaluation periods; purge overlapping feature/label paths. Fit transforms and arrival parameters only on training data. Preserve raw/derived/source hashes, parameters and environment assumptions.
3. Fit event rates, size distributions and state dependence before replacing assumed Hawkes/rival behavior. Aggregate trade prints do not necessarily identify distinct market orders. Level-2 data does not reveal historical participant identity or exact order-level queue positions.
4. Require spread, depth, impact/recovery and fill distributions to match independent observations before interpreting simulated policy returns. Do not insert hypothetical fills into historical data and call them observed fills.
5. Keep zero/no-trade, simple inventory policies and the frozen real-data ridge model as benchmarks. Include fees, slippage, delay, withdrawals and jump scenarios; preserve failed experiments.
6. Gate policy deployment on independent-period performance and calibrated execution/risk behavior. Live observation and shadow decisions come before exchange order submission.

## Run or reload

Requires Python and NumPy. From the repository root:

```bash
python -m src.simulation.learning_market_maker --out data/processed/learning_v1
python -m src.simulation.learning_market_maker --policy configs/learning_v1_policy.json --out data/processed/learning_v1_reload
python -m unittest discover -s tests -p 'test_simulation*.py'
```

Outputs: `policy.json`, `report.json`, and `trace.csv`. The first fitted table is committed as `configs/learning_v1_policy.json`. The compatibility-checked policy can be loaded without another fit. CPU execution is sufficient for this small table; no GPU is required. Raw replay tests also require pyarrow and zstandard.

## Next integration

First audit the real-data timing and observation boundary, then calibrate a richer event environment on additional contiguous days. After that, compare tabular policies with actor-critic/deep-set approaches on the same frozen environments and untouched evaluation periods. The coupled option/hedge module requires an option chain, volatility surface and explicitly stated signed-position assumptions. The macro bubble and venue-auction branches remain separate.

Related: [real-data regression](RESPONSE_REGRESSION.md), [historical replay](HISTORICAL_MARKET_REPLAY.md), [main laboratory guide](MARKET_ECOLOGY_SIMULATION.md).
