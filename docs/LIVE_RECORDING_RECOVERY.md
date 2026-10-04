# Live learning recording and recovery

Added private segmented forecast/outcome journals, using the existing CaptureArchive writer. Each decision records receipt timestamp, forecast, baseline, tokens and observed token values; each matured outcome records the frozen forecast, actual return and outcome receipt. No orders. A new dashboard status reports journal recording failures separately. Partial files are flushed; completed 8 MiB segments have checksum manifests. Files remain ephemeral on free hosting and are not exposed through the public dashboard. This is not a durable cloud archive.

Added an explicit saved Kraken seed checkpoint fallback when the local checkpoint is absent. Local checkpoints take precedence. Seed restores weights, intercept and accumulated scores only through its backup point; it does not recover newer observations, raw tapes, pending labels or context. It is pinned to the existing model/venue version. Forecast logic, bins, horizons and training parameters unchanged. New sessions continue cumulative scores, so reported skill includes pre-backup scores.

The bundled backup was downloaded from the running laboratory before deployment. Initial inspection showed 1,492 learned outcomes and -25.62% skill relative to no-change; a newer backup was taken before release. Actual backup counters are in src/simulation/river_kraken_seed.json. These are outcomes, not independent samples. Improvement or profitability is not established.

Raw-message recording already existed privately in CaptureArchive; the new journal fills the gap in full forecast/outcome history (the prior UI retained only the latest 100). No retroactive forecast history can be recreated from a weights checkpoint alone.

Seven River tests and eight existing live-observer tests passed, including seed fallback/local precedence and real journal decision/outcome writes. Free service can sleep; loss since the saved seed remains possible. Scheduled durable backups or paid storage have not been provisioned. No artificial keepalive.
