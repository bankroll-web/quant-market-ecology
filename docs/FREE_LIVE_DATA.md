# Free live-data alternative

Coinbase Exchange BTC-USD spot is available with `--provider coinbase`.
The public subscription uses `level2_batch`, `matches` and `heartbeat` at
`wss://ws-feed.exchange.coinbase.com`; it needs no credentials or paid data plan.
Official channel documentation: https://docs.cdp.coinbase.com/exchange/websocket-feed/channels

The adapter preserves the full L2 snapshot and applies absolute sizes, deleting
zero-size levels. Snapshots have no engine timestamp and cannot qualify as fresh
until a timestamped update arrives. Backward timestamps, invalid levels, crossed
books, disconnects and detected trade-ID gaps invalidate the book and reconnect.
The subscription's historical `last_match` initializes the trade ID and is not
counted as a newly observed trade. Match side is the maker side; aggressor side
is inverted. Duplicate trade IDs are ignored.

There is no Coinbase book checksum or independently checked L2 sequence in this
channel. Ordered WebSocket delivery is not proof of uninterrupted exchange data.
The local update counter is not an exchange sequence ID. Batch timestamps belong
to the latest event in each 50 ms batch. Matches can be dropped; detected trade-ID
gaps reset the experiment. This is an inspection feed, not a qualified execution
feed or complete participant-level order history.

Historical Binance BTCUSDT futures research remains separate: no pooling with
Coinbase USD spot and no transfer of fitted coefficients without validation.
Kraken is retained as `--provider kraken` for rollback.

Hosting stays on the existing free Render service. Switching data provider does
not change Render's sleeping or ephemeral-storage limits. No paid resources are
created. Historical replay remains available without an exchange connection.

Local verification: 61 simulation tests passed. The workspace WebSocket probe
was blocked by its network proxy (HTTP 200 instead of a WebSocket upgrade);
production connectivity must be checked on Render before declaring the switch
successful. Do not treat fixture tests as live connectivity evidence.
