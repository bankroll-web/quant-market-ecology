# Service-side live research training

This change removes the need to retrieve private recordings before a first Coinbase development fit. Each directly received feature bundle also enters a bounded in-memory research buffer, independent of the segmented raw archive. The collector schedules at most one background fit, checks readiness no more than once per minute, and keeps the observer loop responsive.

The buffer holds at most 20,000 feature bundles, not independent labeled examples. Disconnects mark separate generations; targets cannot cross them. The existing receipt freshness, target-window continuity and chronological split checks apply. The first-half resolved targets fit transforms and fixed ridge-logistic coefficients; the second half supplies development scores against the training base rate. At least 400 usable examples and ten training observations in each binary class are required before fitting. These are engineering thresholds, not qualification standards.

`ecology.json` includes `live_training`: collecting/insufficient-data/class-support/error or development-fit status, buffered bundles, training/evaluation counts when fitted, scores, and limitations. The dashboard displays this status and latest timestamped features even when simulations pause for feed-quality warnings. It never overrides the stale-feed warning or enables trading.

No observed service-side fit result is claimed before deployment and sufficient accepted data. Once active, the service can perform research fitting autonomously; this does not install a buy/sell policy. Signal remains WAIT and orders are disabled. Repeated fitting on a rolling buffer means prior evaluation observations may enter later training: these are repeated development comparisons, never an untouched accumulating holdout. New-day evaluation must be kept outside this process before qualification.

The free service's memory buffer and archive can disappear on restart. No paid service, disk, broker account or credential was added. numpy is added to the existing free observer image for the small regression. Only one fitting worker is used. The retained memory cap limits feature-history growth; the raw archive retains its separate existing policy.

## Alternative feeds checked

Coinbase Exchange already supplies public order-book and matches data, including batched L2. It is the active feed and preserves venue-specific continuity for this training path. Kraken public WebSocket L2 is another documented option, and this repository already has a Kraken observer; switching to it would require separate feature adaptation and venue-specific validation, not merging the two books or applying Coinbase coefficients unchanged.

Primary sources reviewed:
- https://help.coinbase.com/en/developer-platform/websocket-feeds/exchange
- https://docs-legacy.kraken.com/api/docs/websocket-v2/book/

Tests exercise background readiness, insufficient class support and a complete synthetic chronological fit. Synthetic results validate code behavior only. Real-data profitability, fees, latency, queue fills and paper trading remain unqualified.

## Delayed-feed recovery and alternate venue

An observed live page reported about 49 seconds of engine-to-receipt delay despite recent arrivals. The implementation now reconnects Coinbase when that lag exceeds ten seconds. After three consecutive delay failures, it switches the remaining run to the existing public Kraken spot observer. Kraken CRC32 top-ten verification is retained. Failure of that alternate feed is reported through its existing retry/status path; no provider quality is fabricated.

Coinbase depth calculations now reuse an exact Decimal cache when midpoint is unchanged, and the displayed top-100 copies use bounded heaps instead of sorting the full retained book. These reduce processing overhead without truncating the authoritative Coinbase book. They do not establish whether the observed delay was caused by processing, transport or clocks.

Kraken received-book features use its subscribed depth. Switching venues clears the rolling fitting buffer; pending fits from another venue are discarded. Offline fitting rejects mixed-venue examples. Raw recordings remain private. The two feeds are never combined as one book or one fitted model.
