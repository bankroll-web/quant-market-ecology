# Market Ecology simulation: user manual

## What you can use today

The draft project lives in [pull request #1](https://github.com/bankroll-web/quant-market-ecology/pull/1), branch `codex/market-ecology-simulation-v1`. The observer is an offline, five-minute **simulation**, not a connection to today's market. It compares normal liquidity with a case in which maker B withdraws for 60 seconds around an 80 BTC aggressive buy at second 120. It does not submit exchange orders or require API keys.

For the quickest look, open the ready-made observer HTML supplied in our conversation. Download the HTML and double-click it. It is self-contained and runs in your browser with no server. The repository commands below regenerate it.

## Download and run (Windows PowerShell)

1. Open the [draft pull request](https://github.com/bankroll-web/quant-market-ecology/pull/1). Select the branch `codex/market-ecology-simulation-v1` in the repository's branch selector, then **Code → Download ZIP**. Extract the ZIP. Do not use the `master` ZIP yet: this work is still a draft pull request.
2. Install Python 3.13 if needed. Open PowerShell in the extracted repository folder, the folder containing `src` and `configs`. On Windows you can type `cd ` and drag that folder into the PowerShell window, then press Enter.
3. Run these lines one at a time:

```powershell
py -3.13 -m src.simulation.ecology --config configs/simulation_v1_demo.json --out data/processed/simulation_v1
py -3.13 -m src.simulation.observer --csv data/processed/simulation_v1/simulated_ecology.csv --out data/processed/simulation_v1/observer.html
start data/processed/simulation_v1/observer.html
```

If `py -3.13` is unavailable but `python --version` reports Python 3.13, replace `py -3.13` with `python`. This demo and observer use the Python standard library. To check the simulation tests, run `py -3.13 -m unittest discover -s tests -p test_simulation_ecology.py`.

The commands write `simulated_ecology.csv`, `simulation_report.json`, and `observer.html` under `data/processed/simulation_v1`. These are generated outputs. A cloud VM can run the same commands from the repository root; your laptop does not need to stay on.

## Read the observer

Select **Spread**, **Ask depth**, **Bid depth**, **Midprice**, or either maker's inventory. Move the time slider second by second. Blue shows both makers; orange shows maker B's withdrawal. The dashed line at 120 marks the scheduled buy. The panels show best bid/ask, depth, background buy/sell trade counts, each maker's posting and displayed removal, inventory, and the scheduled buy quantity.

Compare the same second in both panels to isolate the withdrawal scenario under shared background random draws. Posted/removed quantities are simulated agent actions. Inventory is signed BTC held by each simulated maker. Depth is displayed BTC in the model's 770-level band; it is not the entire exchange book. Mark-to-mid in the report excludes fees, hedging and risk and is not realized trading profit.

## Change a scenario

Copy `configs/simulation_v1_demo.json` to a new filename and edit its JSON values. Pass the new filename to `--config` and a new folder to `--out`; then rerun the observer with that folder's CSV. Keep the original config so comparisons remain reproducible. The scenario parameters, including taker arrival, posting/removal, shock and withdrawal, are assumptions unless specifically identified in the technical notes as sample-derived scales.

## Current evidence and limits

The book reconstruction diagnostic matches frozen D06 audit counts on two uploaded BTCUSDT hours (2026-05-25 00 and 04 UTC). The observed nine-state book-change count model failed its 04 UTC holdout against a constant-rate baseline (negative log likelihood per exposure second 935.11 versus 908.65, lower is better). It is **not** connected to the agents. A displayed level reduction does not reveal whether an order was canceled, executed or modified, and the public feed does not identify individual market makers.

The simulation is useful now for studying causal *model mechanisms* and viewing intraday-like events second by second. It is not a validated forecast, a complete intraday market replay, or a profitable trading strategy. The full frozen regression suite was not run locally because the full large data corpus was not present; the isolated simulation tests passed.

## Can it run with live data?

**Yes as a next development stage; the current code cannot do it yet.** First build a read-only collector and live observer. Use Binance USD-M BTCUSDT public diff-depth WebSocket and aggregate-trade WebSocket. No trading credentials are needed for those public feeds. A live view would show observed order book and trades; the simulator could then run hypothetical maker actions against snapshots of that observed state. No exchange orders should be inferred from the simulation output.

Implementation sequence:

1. Connect to `wss://fstream.binance.com/public/ws/btcusdt@depth@100ms` and buffer depth deltas. Fetch `https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=1000`, bridge snapshot/update IDs under the current Binance rules, apply absolute quantities (zero removes a level), and resynchronize after a sequence gap.
2. Connect separately to `wss://fstream.binance.com/market/ws/btcusdt@aggTrade`. Preserve exchange event and trade timestamps, IDs, prices, sizes, and buyer-maker flag; also record local receipt time. Treat aggregate trades as aggregated fills, not individual private orders.
3. Persist raw messages and periodic book snapshots to replayable files. Mark the book invalid during reconnect or resync; exclude invalid spans from features and displays. Monitor gaps, message delay, dropped data and disk growth.
4. Compute incremental best quotes, spread, depth, order-book imbalance, signed aggregate flow and displayed changes only while synchronized. Feed a read-only live dashboard; compare the pipeline's recorded replay with its online output.
5. Calibrate and validate candidate agent rules on multiple contiguous days and independent holdouts. Add a separate paper-only execution loop with realistic latency, queue/fill, fees, inventory and risk controls if the research survives. Trading API integration would be a later explicit decision.

The exchange currently separates public depth and market trade WebSocket paths. Verify connection and sequencing rules against its live documentation at implementation time: [local book synchronization](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly), [public depth stream](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/public), [aggregate trade stream](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market). Historical D06 replay rules remain frozen; a new live adapter needs its own fixtures and audit tests.

## Research still needed

Priority one is multiple contiguous days of matching depth and trade data, starting with 2026-05-25 01, 02 and 03 UTC to fill the current 00–04 gap. Then measure event timing and sizes, handle executions when interpreting depth reductions, and check held-out spread, depth, impact and recovery distributions. Add regime changes and a better queue/latency/fill model before calling it a serious market-making study. Cross-market derivatives and participant ecology can follow with their own data and tests. Public data permits behavioral hypotheses, not participant identity.

For the next implementation step, provide the missing matching depth/trade hours or access to a cloud host that can reach Binance public endpoints. A GitHub link is already available; no repository link or API key is needed for this manual.
