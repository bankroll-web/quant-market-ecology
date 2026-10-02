# Short-history price-response ablation

Hypothesis: two earlier completed contiguous flow windows add useful predictive
information beyond current completed flow, imbalance, spread, depth and return.
This is the required simple history-state comparison before considering recurrent
policies motivated by the supplied LSTM/DQN paper. It is not that paper's model.

Training: 25 May 12 UTC only, ridge penalty fixed at 1. Validation: 25 May 18 UTC.
Later diagnostic periods: 26 May 15 and 21 UTC. All periods were already inspected;
there is no untouched final test. No hyperparameter search or horizon selection
was performed in this experiment.

The history features use only two preceding completed flow windows in the same
verified episode, with no discontinuity between windows. Missing history is
zero-filled with explicit availability flags. Supplied forward-return columns
are ignored. Prior signed flow is normalized by currently observed depth; past
volume uses log1p and past returns are in basis points. All centering, scaling
and fitted coefficients use the training period only.

Snapshot and history models use identical decisions, scheduled 100 ms entry,
five-second exit and 250 ms endpoint tolerance. Longs cross the entry ask and
exit bid; shorts use the opposite quotes. Assumed round-trip fees/slippage are
5 bps, with 0 and 10 bps sensitivities. Current spread adds a conservative signal
gate. Decisions reserve non-overlapping information/trade intervals, including
unresolved exits. No order-size, queue-fill, impact, funding or liquidation model
is established. Net sums are equal-unit bps diagnostics, not portfolio returns.

| Period | Zero forecast RMSE (bps) | Current-state ridge | History ridge |
|---|---:|---:|---:|
| Training: 25 May 12 | 0.725 | 0.635 | 0.628 |
| Validation: 25 May 18 | 0.431 | 0.849 | 0.999 |
| Later: 26 May 15 | 2.015 | 2.802 | 3.264 |
| Later: 26 May 21 | 0.786 | 3.843 | 5.021 |

Small training improvement fails to generalize. Both fitted models are worse
than predicting no midpoint change on every later period. The additional history
makes those errors worse rather than improving the baseline.

At 5 bps costs, validation triggers no trades for either model. The predeclared
selection rule therefore selects `no_trade`: at least five resolved validation
trades and positive net sum under hypothetical 50 bps loss per missing exit are
required to qualify even for further research selection.

On the last diagnostic hour, the history model triggers 115 resolved trades:
−554.47 summed net bps, plus 22 opened decisions with unobserved exits.
Hypothetical 50 bps-per-missing-exit stress gives −1654.47 bps. Those stresses
are sensitivity assumptions, not measured losses or guaranteed worst cases.
The selected no-trade policy takes none of those trades. No live policy changed.

**Decision: reject this short-history strategy.** Do not interpret ridge weights,
small training improvement or the presence of historical context as established
alpha. A larger recurrent network must justify its extra complexity against
these identical baseline and data boundaries. Next diagnosis is whether features
and activity distributions shift, and whether price responses can be evaluated
with enough contiguous venue-consistent data and realistic execution costs.
Additional strategies require logged hypotheses and fresh final evaluation
periods; repeatedly reusing these hours cannot establish profitable robustness.

`HISTORY_STRATEGY_RESULTS.json` contains every policy, cost sensitivity, regression
score, missing endpoint audit and input hash. `HISTORY_STRATEGY_MODELS.json`
contains frozen training transforms and weights. Results are reproducible with:

```bash
python -m src.simulation.history_strategy --flow-dir data/processed/decision_repaired --book-dir data/processed/replay_repaired --out data/processed/history_strategy
python -m unittest discover -s tests -p 'test_simulation*.py'
```

68 simulation tests pass. New checks cover future/current-outcome exclusion from
lagged state, exact depth normalization, availability flags, gap/episode resets
and unordered-window rejection. No paid services or live trading added.
