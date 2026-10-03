# October 3 strategy-paper integration

## Result

Reviewed the ten supplied papers and implemented one interpretable ecology-tree adaptation. This is an offline development comparison, not a profitable-strategy certification. It is saved on the research branch; no live model or order behavior is changed.

The one-second experiment trained on 459 resolved observations from the first half of the May 25 00:00 recording, froze the model, and evaluated 8,132 later observations across eight previously inspected hourly recordings. Only 510 evaluation observations were inside all seven training feature ranges. No forecast cleared costs plus the entry buffer; zero BUY/SELL entries. The best training leaf's predicted net return was approximately -5.71 basis points (0.0571% loss), with six basis points of assumed fees/slippage already deducted. Tree return prediction beat the training-mean forecast in one of eight hours; it was worse in the other seven. No trading edge is established.

Longer-horizon trials use the same recorded-path continuity requirement and fixed minimum leaf size. Their explicit insufficient-data outcomes are in the 5S and 30S JSON files. A missing experiment is not a losing strategy. We did not relax time gates to manufacture labels.

## Paper-to-code register

Exact input filenames and SHA256 hashes are in SOURCES.json. Page references below mean printed pages or named sections; evidence belongs to the original paper, not to this laboratory.

| Source | Extracted method | Integration decision and evidence boundary |
|---|---|---|
| An_Evolutionary_Game_Model_of_Financial_Markets_wi.pdf | Momentum/contrarian/fundamentalist populations, excess-demand price response and payoff-driven replicator dynamics; section 2, pp959–961 | A synthetic mechanism experiment for the separate macro/bubble branch. Public order books do not reveal the three population shares. No empirical alpha inferred. Formula extraction has ambiguous symbols, requiring visual inspection before faithful implementation. |
| Bitcoin_and_Main_Altcoins_Causality_and_Trading_St.pdf | Daily BTC plus nine altcoins; 714-observation rolling LASSO, lags1–7 of returns/volume/volatility/illiquidity, forecast ensembles; pp19–22 | High-priority next data branch. Original strategy is long/flat, not symmetric shorting: enter above +0.25%, exit below -0.25%, costs0.25% per side. Requires synchronized multiasset daily histories and exact predictor definitions. Replace generic CV with chronological inner validation and explicitly label any adaptation. Granger prediction is not structural causation. No local replication performed yet. |
| TRADING_STRATEGIES_IN_THE_CRYPTOCURRENCY_MARKET_EV.pdf | Strategy review with an AI case, 5% stop and 10% take profit; pp56–57 | Narrative case provides monthly results but not sufficient dataset dates, architecture and executable training specification for independent reproduction. Register as under-specified; do not import its reported return as laboratory evidence. |
| Decision_Trees_for_Intuitive_Intraday_Trading_Stra.pdf | Equity indicator classifier, Gini, max depth4, shifted next return label; sectionsIII–IV | Implemented an adaptation: shallow multioutput regression tree using seven book/ecology features and long/short executable quote returns. Depth4 retained; min leaf40 is our fixed safeguard. Original technical indicators, equities and Gini classification were not replicated. Original interpolation and reported test-driven depth experimentation require separate timing/model-selection audit. |
| Developing_Actionable_Trading_Strategies.pdf | Optimize/enhance/discover/integrate strategies subject to real-market and organizational constraints; chapter193–215 | Adopted principle: the target includes spread crossing, costs and explicit short-access limitations. Conceptual development framework, not a standalone buy rule. |
| Gold_or_BTC_The_Best_Trading_Strategy.pdf | VMD/CEEMD forecasting ensemble, weekly gold/BTC/cash path optimization, Floyd and risk extension; section3.3 | Requires gold calendar and historical forecasts made before each week. The paper explicitly optimizes over forecast paths, so do not assert it necessarily uses actual future prices. Audit decomposition boundaries and forecast timestamp provenance before replication; actual future optimal route is only an oracle benchmark. |
| A_Market-Aware_Dynamic_Trading_Strategy_Based_on_U.pdf | Malaysian GAMUDA stock, GMM regimes, LSTM, DQN; four-year train/one-year frozen test walk-forward; section2.3.4 | Retain regime-aware training/evaluation architecture as a candidate. No DQN training on a tiny book sample and no transfer of the stock's performance to BTC. Need enough chronological market history, costs, state/action/reward specification and regime fit boundaries. |
| Measurement_of_Trading_Strategy_Based_on_Model.pdf | Gold/BTC price-vs-MA crossover, periods5/13/55 then period search and methodsA/B/C; section4 | Daily long/flat benchmark candidate. Selecting the best MA from full-period profit is development optimization, not untouched evidence. Original periods123/655 cannot be imported as optimal parameters. The lab needs longer daily history, warm-up, next-available-price execution and separate selection/test periods. |
| al-naymat2018.pdf | Pair selection via DTW/Euclidean similarity and dynamic control-chart monitoring; sections3–6 | Crossasset candidate. Paper's evaluation uses seeded synthetic prices; this does not establish convergence or net profit for actual BTC/ETH. Need synchronized prices, trained hedge ratio, two-leg costs, borrow/funding and convergence-loss exits. |
| Reinforcement_learning_for_optimization_of_energy_.pdf | Replay exogenous trajectories while modeling controllable inventory/storage; train2016–2018, validationQ4 2018, test2019; section5 | Useful environment-design pattern. Energy generation, weather and battery constraints do not constitute a cryptocurrency signal. Keep as methodological reference; no crypto edge or actor inference claimed. |

## Executable tree protocol

`src/simulation/ecology_tree_research.py` fits `DecisionTreeRegressor(max_depth=4, min_samples_leaf=40, random_state=91)` with two targets:

- Long: 10,000 × (exit bid / entry ask − 1) − 6 basis points.
- Short: 10,000 × (entry bid − exit ask) / entry bid − 6 basis points.

Features: top-book imbalance, ten-basis-point depth imbalance, log depth, spread in basis points, best-quote OFI/depth, and bid/ask net displayed additions/depth. These represent displayed liquidity, not known institutions/retail/dealers. A displayed reduction is not a measured cancellation.

Select the larger predicted net return only when above two basis points and all features are within training min/max. Otherwise WAIT. A short is hypothetical; no broker orders are sent. Training labels must resolve before the cutoff. Tree leaf means and rules, per-hour errors, data hashes and range rejection counts are saved in JSON. No parameter search was run on later observations.

One-second labels use the first receipt at or after the horizon, maximum250ms lag and no inter-receipt gap above250ms or episode crossing. Target sampling can overlap. The offline loader does not reproduce every live engine/freshness condition. Immediate top-quote proxies omit size, execution latency, borrow and funding. Results cannot be claimed as portfolio returns or independent sample statistics.

## What comes next

The useful next data acquisition is synchronized daily BTC/altcoin histories for a frozen rolling-LASSO/long-flat benchmark, plus longer contiguous bid/ask recording periods for the ecology strategy. These answer different questions and remain separate datasets. Previously inspected August/September tapes are development data; a newly reserved period is needed before a new candidate is called validated. Specify and freeze candidate rules, costs, horizon, inner selection and rejection criteria before opening that evaluation period. Compare price-only, ecology-only and combined predictors to test whether ecology adds information.

No additional books are needed to proceed with that work. The current missing inputs are market data coverage and timestamps, not a promise that more model complexity produces profit.

## Reproduce

Use Python3.12, numpy and scikit-learn1.8.0 (offline research dependency only). From repository root:

```bash
OPENBLAS_NUM_THREADS=1 python -m src.simulation.ecology_tree_research . 1
OPENBLAS_NUM_THREADS=1 python -m src.simulation.ecology_tree_research . 5
OPENBLAS_NUM_THREADS=1 python -m src.simulation.ecology_tree_research . 30
python -m unittest discover -s tests -p test_simulation_ecology_tree_research.py
```

Requires the eight observed-change CSVs under `data/processed/mechanics_study_states` and `data/processed/mechanics_replication_states`, generated by the existing historical replay pipeline. Their exact hashes are recorded in the one-second result. Sources: supplied PDFs; scikit-learn's primary API documentation https://scikit-learn.org/stable/modules/generated/sklearn.tree.DecisionTreeRegressor.html. Three software checks cover planted directional net edge, WAIT without an edge, out-of-range rejection and quote/cost arithmetic. They do not certify profitability.
