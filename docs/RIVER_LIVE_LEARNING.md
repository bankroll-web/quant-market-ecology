# Live Bitcoin token learning

Open `/river.html` on the existing market ecology observer. River runs on the server; no laptop installation is needed. The historical transformer laboratory remains at `/tokens.html`.

## What runs

This deployment starts separate fresh Coinbase BTC-USD and Kraken BTC/USD River 0.26.1 linear regression models. Only the active venue learns; coefficients, metrics and checkpoints remain separate. It does not import Binance-trained coefficients or bin edges. Twelve small categorical fields describe each validated book update: receipt time gap, observed trade count, signed aggressor flow, bid/ask liquidity adds/removals near the midpoint, relative midpoint change, top imbalance, depth imbalance, depth and spread. Fixed 8-bucket edges are declared in `river_live.py` before the live run. The vocabulary is 96 field-specific symbols; it is not a composite vocabulary. Input features combine the latest tokens and normalized counts over 16 book updates. No absolute price is an input feature. No participant identity is claimed.

The 30-second return target is computed from midpoint prices at decision receipt and first accepted book receipt at/after the deadline, with a maximum two-second target delay. Decisions occur no more than once per second. Predictions are bounded to ±100 bp by a fixed research guard. The model scores its stored prediction against the later outcome **before** learning from that outcome. SGD uses constant rate 0.005, L2 0.0001 and gradient clipping 10. The comparison forecasts are zero return and the mean of already observed targets at the decision time.

Only verified new Coinbase match messages enter trade tokens; historical subscription seeds, duplicates and gaps do not become new examples. Coinbase's maker side is inverted to obtain aggressor side. Book observations must meet the existing 250 ms event/receipt research cutoff. Missing trade subscription, a receipt gap over two seconds, reversed receipt time, disconnect, stale feed or venue change discards pending labels and context. Kraken fallback trains its own model from its checksum-validated subscribed depth (100 levels per side) and valid, deduplicated trade updates. It does not train the Coinbase model. Coinbase L2 has no independent sequence/checksum validation; the page must not imply one.

## How to interpret the page

* **Learned outcomes** should increase after 16 valid updates and approximately 30 seconds of continuous research-quality data. Repeated pauses can extend this indefinitely.
* **Skill vs no change** is `1 - model_squared_error / zero_forecast_squared_error`. Positive values indicate a better forecast under that loss, not a profitable strategy. Compare the prior-mean baseline too.
* **Flow and later price response** groups decisions into six fixed anonymous-flow/liquidity states. Means are descriptive, not causal. Ties use the bid-withdrawal state. Overlapping outcomes are correlated, so outcome counts cannot be treated as independent trials or used to claim conventional significance.
* **WAIT** remains the trading status. This module has no order endpoint, execution model, fee model, paper profit qualification or authorized real-money trading.

The first hours establish whether data and learning work. Investigating repeatability requires independent periods and multiple market conditions. Freeze a candidate model before testing on new periods, then include venue fees, slippage and latency. The current adaptive prequential scores are not an untouched holdout. No fixed number of hours, days or tokens guarantees profitability.

## Hosting and checkpoints

`--seconds 0` removes the previous 24-hour collector deadline and means run until stopped. This does not prevent the hosting provider from stopping the process.

The existing Render free service can sleep after 15 minutes without inbound traffic and has ephemeral local storage. Continuous learning happens only while the service is awake and the active venue feed passes quality gates. No paid plan, persistent disk or artificial keep-alive traffic was added. Local model checkpoints are written atomically every ten seconds and restored when present; pending outcomes and context are always discarded on restore. The public **Download learning checkpoint** link exports coefficients, counters and response aggregates. It is a manual backup, not durable automated storage. Truly unattended 24/7 learning requires an always-on host and durable storage, subject to the user's budget approval.

## Validation

Three targeted tests cover delayed scoring before learning, trade/timing/venue gates and checkpoint prediction equivalence. Sixteen existing Coinbase, Kraken and observer tests also pass. These verify software behavior, not trading profitability. Run with the live requirements installed:

```
python -m unittest discover -s tests -p test_river_live.py -v
python -m unittest discover -s tests -p 'test_simulation_*observer.py' -v
```

The live laboratory is in the **online research and monitoring stage**. Profitable trading qualification remains a separate unresolved stage.
