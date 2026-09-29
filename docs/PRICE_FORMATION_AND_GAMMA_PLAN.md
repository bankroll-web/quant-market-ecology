# Price formation and the next agent layers

This is a research design, not a calibrated price forecast. The current paired experiment has a reconstructed-sample scale for the starting book, two assumed liquidity providers, random takers, and a scheduled aggressive buy. The new size sweep in `src/simulation/impact_sweep.py` changes only the buy size and whether maker B withdraws; the background random stream stays fixed.

## Event sequence and equations

At each simulated second: (1) makers reduce displayed quotes; (2) maker B may withdraw; (3) background takers execute; (4) the scheduled aggressive buy consumes asks from lowest price upward; (5) makers replenish except at the shock second; (6) record best quotes, depth, midpoint and inventories. At a price level, makers share a fill pro rata. This is a discrete price-priority mechanism, not an exchange-accurate queue model.

With best bid `b_t`, best ask `a_t`, midpoint `m_t=(b_t+a_t)/2`, and aggressive buy size `Q`, execution matches available asks `A_i` in ascending price until `Q` is filled. The average execution price is `VWAP=sum_i p_i q_i / sum_i q_i`. We report:

- Immediate midpoint move: `10,000 * (m_after/m_before - 1)` bps.
- Execution slippage: `10,000 * (VWAP/a_before - 1)` bps.
- Extra move under withdrawal: `move_withdrawal(Q) - move_normal(Q)` bps, using each scenario's own pre-buy midpoint. This is the effect of the combined withdrawal-and-buy intervention in this synthetic setup; it does not identify a real-world withdrawal coefficient.

The size sweep compares `Q = 5, 10, 20, 40, 60, 80 BTC`. Larger orders can deplete the finite displayed book in this simplified design; do not extrapolate a fitted impact curve. A separate empirical impact study should measure conditional response `E[10^4 log(m_(t+h)/m_t) | Q, signed flow, depth, regime, valid book]`, with controls for contemporaneous news and selection, and report uncertainty across independent days. Impact papers motivate concave and transient alternatives, but their parameters cannot be imported without validation. See [Donier et al., latent order-book impact](https://arxiv.org/abs/1412.0141).

## Agent ecology: proposed modules and what can be observed

| Module | Simulated decision | Public data constraint |
| --- | --- | --- |
| Liquidity providers | Post, move, reduce quotes conditional on inventory, spread, imbalance and risk | Visible depth changes mix execution, cancellation and modification; provider identity is hidden. |
| Small takers (retail *scenario*) | Many small buy/sell orders, time-varying participation | Size alone cannot prove a trader is retail. |
| Large takers (institutional *scenario*) | Split a target quantity into a sequence of child orders; condition on participation and impact | Public trades do not reveal parent orders or institutional identity. |
| Arbitrage / cross-venue actors | Respond to basis and cross-venue price differences with latency and cost | Needs synchronized spot, futures and venue quotes. |
| Futures leverage and liquidations | State-dependent forced flow and inventory constraints | Needs funding, open interest, basis and liquidation feed, with coverage checks. |
| Options dealer hedging | Rebalance delta exposure as underlying price and Greeks change | Dealer net position and hedge venue are not publicly identified; simulate explicit sign/coverage scenarios. |

Proposed mathematical sequence: a valid event-time book and trades → background flow and conditional spread/depth state → heterogeneous agent policies → queue/fill and latency → paired interventions → held-out distributional checks for spread, depth, signed response and recovery. Add modules one at a time and compare against a simple baseline. The earlier nine-state book-change intensity model performed worse than the constant benchmark on holdout, so it must not drive maker agents.

## Options gamma / GEX layer

Gamma is the local derivative of option delta with respect to underlying price, `Gamma_i = d Delta_i / dS`. For an option contract with open interest `OI_i`, multiplier `u_i` underlying units per contract, and *assumed* dealer signed position `z_i` (+1 long, -1 short), define scenario dealer gamma in underlying units per $1 move:

`G_dealer(S,t;z) = sum_i z_i * OI_i * u_i * Gamma_i(S,t)`.

For a small underlying move `dS`, the dealer delta change is approximately `G_dealer*dS` underlying units, and the hedge order is `dH ≈ -G_dealer*dS`, before vanna/charm, position changes and hedge delay. A long-gamma scenario tends to hedge against a move; a short-gamma scenario tends to hedge with it. The sign `z_i` cannot be inferred from open interest alone. Report **positive, negative and neutral positioning scenarios** and their assumed hedge fractions; do not label one as the actual dealer book. Recompute Greeks as price, time and implied volatility move. A commonly plotted `OI*Gamma*S²*0.01` measure expresses notional gamma per 1% move under a chosen unit convention; document the multiplier, currency, contract type and sign each time.

GEX influences the model through *hypothesized hedge orders*, not by directly shifting a price variable. Route those orders through the same book as other taker flow; optional quote responses and cross-venue transmission need explicit latency. This separates a Greek exposure estimate from realized price impact.

Binance Options documents contract units and expiries via exchange info, per-contract open interest by expiry, and mark Greeks including gamma. Those are candidate inputs, subject to coverage and time alignment. A historical intraday backfill at the exact futures dates is needed before estimating past GEX. Options activity on other venues may be material; exchange-specific OI is not global market gamma. Source: [Binance Options market data](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-options/api/rest-api/market-data).

## Data request and research gates

1. **Next matching futures data:** BTCUSDT depth plus trades for 2026-05-25 01, 02 and 03 UTC, then multiple contiguous independent days. Preserve raw timestamps, update IDs and invalid-book flags.
2. **For GEX:** historical option chain by contract (strike, call/put, expiry, multiplier), time-stamped open interest, mark IV/Greeks or option quotes to recompute Greeks, underlying/index price, and option trades if available. State the venue and historical coverage; a current snapshot cannot reconstruct the May experiment.
3. **For derivatives ecology:** time-stamped futures OI, funding, basis, liquidation observations and synchronized spot/futures books. Distinguish public proxies from actual participant identity.
4. **Validation:** estimate event size/timing and impact on training days, compare with constant/simple models on untouched days, then test recovery, latency, fees, queue/fills and sensitivity to assumed dealer sign. A visually interesting curve is not validation.

Run the new picture with:

```bash
python -m src.simulation.impact_sweep --config configs/simulation_v1_demo.json --out data/processed/impact_sweep
```

Open `data/processed/impact_sweep/impact_sweep.html`. The CSV contains the numeric output. This uses Python standard library and no API key.
