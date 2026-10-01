# Read-only live depth observer

## Status

The BTCUSDT USD-M Futures depth adapter, local dashboard, event capture and fixture replay are implemented. Thirty isolated simulation tests pass. The captured-event fixture recovers after a disconnect and shows a gap in the chart history. Dashboard JavaScript passes `node --check`; actual browser rendering and an exchange-connected session have not been verified.

A bounded eight-second live attempt from this cloud runtime failed with `Cannot connect to host fstream.binance.com:443 ... Temporary failure in name resolution`. No live exchange message or snapshot was received. A subsequent fix enabled the configured network proxy; the REST endpoint then returned HTTP 451 (restricted location). The current blocker is exchange access from this runtime, not a missing API key or proof of an exchange outage. See [cloud deployment preparation](LIVE_CLOUD_DEPLOYMENT.md). Do not label the fixture as live data. [Standalone fixture demonstration](LIVE_OBSERVER_DEMO.html).

## Behavior

- Opens the public depth WebSocket before requesting the 1000-level REST snapshot, buffering at most 5000 messages.
- Uses the documented USD-M Futures inclusive snapshot bridge `U <= lastUpdateId <= u`. Afterwards, each advancing message must have `pu == previous u`. Duplicate/stale advancing IDs never refresh health. These live rules do not change the frozen historical reconstruction.
- Applies absolute level quantities using Decimal prices/quantities. Zero deletes a level; deleting an absent level is allowed. Invalid, empty or crossed books are cleared.
- Clears prices on sequence gaps/disconnects, reconnects and requests a new snapshot; buffered overflow also triggers a reset.
- Publishes post-update best quotes, midpoint, spread, top imbalance, displayed depth within 10 bps and ten nearest levels. Invalid/stale/clock-warning states expose no current price features.
- The exploratory freshness threshold is 250 ms for both message receipt-minus-event age and time since last advancing receipt. Negative ages suppress features. Timestamp differences include clock offset; this is not a latency measurement or synchronized exchange clock.
- Atomic state publication prevents the dashboard from reading partially written JSON. If a live state file stops updating, the dashboard clears current values after two seconds. Plot lines break at unavailable states.
- Writes snapshot, depth and disconnect records to `capture.jsonl`; an offline replay reuses the same state engine. The dashboard is served on loopback only; cloud browser access requires the runner's normal port forwarding.

This version observes the order book only. It does not yet ingest trade/funding streams, identify participant roles, run the learned policy on live data, or submit orders. The visible book excludes liquidity not in the exchange snapshot/updates; displayed depth is not a full-market liquidity measure. No authentication, private account endpoint or order endpoint is used.

## Start in a network-capable cloud runner

From the repository root on `codex/market-ecology-simulation-v1`:

```bash
python -m pip install -r requirements-live-observer.txt
python -m src.simulation.live_observer --out data/processed/live_observer --seconds 3600 --serve
```

View `http://127.0.0.1:8765` through that runner's forwarded port while the command runs. Data capture ends at the requested duration and the server closes. Ctrl-C stops the command. The timeout is approximate because an in-flight network operation may finish after the requested deadline.

## Offline demonstration

```bash
python -m src.simulation.live_observer --out data/processed/live_demo --replay configs/live_observer_fixture.jsonl
python -m http.server 8765 --bind 127.0.0.1 --directory data/processed/live_demo
```

The fixture is fabricated for software testing. It is not recorded Bitcoin market data or an alpha result. The standalone demonstration embeds its final replay state and requires no server. The normal replay dashboard reads the generated `state.json`; replay data is labeled by mode and is not subject to live wall-clock expiry.

## Required next validation

Run an exchange-connected observation session in a cloud runtime permitted to reach the public REST and WebSocket hosts. Check a real initial bridge, sustained sequence continuity, age distributions, forced disconnect/resnapshot, queue overflow and replay agreement. Then add a separately synchronized public trade stream and integrate those observations with the historical timing report. Only after independent-day calibration should learning policies consume the feed in shadow mode.

No additional historical data is needed to run this depth observer. Real-market simulator calibration still needs complete paired days and provider timestamp/sequence documentation.

## Official protocol references

Verified against Binance documentation retrieved 2 October 2026:

- [USD-M local-book synchronization](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly)
- [Public depth stream documentation](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/public)
- [Market-data REST documentation](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)

The current documented public-stream URL includes `/public/stream`; do not substitute an older path without rechecking the exchange's migration notice.
