# Bitcoin token laboratory: visual interface

Open https://market-ecology-live-observer.onrender.com/tokens.html for the historical token-model laboratory. The existing live ecology page also links to it. This publishes saved research outputs; it does not connect the trained receipt-token model to the Coinbase live feed.

The page includes midpoint replay, a recording selector, playback controls, 16×12 token contexts, numerical values, decoded bucket centres, saved return quantiles, flow and volatility proxy forecasts, optional later-outcome reveal, full evaluation scores and per-field bigram comparisons. Recording dates and the historical/development status remain visible. No buy/sell rule or order execution is added.

683 contexts are selected systematically from the two evaluation recordings. Summary scores use all 11,608 examples. Future outcomes are not used to select charted contexts; the last context is included for navigation. Every exported context is checked against the saved model. The frontend moves through the exported contexts rather than reconstructing original event-speed playback. Times displayed are receipt timestamps in UTC, rounded down to milliseconds; full decision receipt nanoseconds are retained as strings in the embedded payload. This is different from the live counterfactual agent simulation.

The single file src/simulation/bitcoin_token_lab.html contains its dataset and scripts, so it can be downloaded and opened offline. Live-page links require an internet connection. Its dataset is derived from the original matching frozen tapes, uploaded raw trade files and receipt_trial/PREDICTIONS.csv.gz. The payload contains the predictions SHA256 and the experiment results/source hashes.

To regenerate after an independently approved new experiment:

```bash
python export_token_lab.py --repo . --upload raw
```

The exporter uses the trained bins without refitting them. The template is src/simulation/token_lab_template.html. Render serves the generated file as tokens.html beside the existing dashboards; no torch installation, paid instance, model retraining or capture-policy change is required on the web service.

Verification before publication: 683 exported contexts have 16 updates and 12 token fields; all exported targets are later than decisions; the actual dashboard output directory serves the page with HTTP 200 and identical content; the inline JavaScript passes node --check. Post-publication browser verification is recorded separately in the task handoff.
