# Cloud observer deployment preparation

## Corrected blocker

The observer now honors configured HTTP/HTTPS proxy settings via aiohttp `trust_env=True`. The previous DNS-only failure came from attempting a direct connection in this runtime. A public REST test through the configured proxy reached Binance and returned HTTP 451 with a restricted-location message. No order-book snapshot was received. This runtime therefore cannot validate the Binance live feed.

This is not resolved by an API key. Do not switch to an unofficial proxy or rewrite endpoints to evade the exchange restriction. A cloud deployment must be permitted by the provider and exchange; its actual feed access must be checked before calling the observer live.

## Prepared service

`Dockerfile.live-observer` packages the read-only collector/dashboard as a non-root process. It accepts the hosting platform's `PORT`, binds on `0.0.0.0` only when explicitly requested, and defaults to a 24-hour capture session in the container. Local command behavior still binds to loopback.

Build context: repository root. Dockerfile: `Dockerfile.live-observer`. Branch: `codex/market-ecology-simulation-v1`. The runtime dependencies are only aiohttp and the Python standard library; it does not install the historical Parquet/ML dependencies.

Example for a permitted cloud runner:

```bash
docker build -f Dockerfile.live-observer -t market-ecology-observer .
docker run --rm -p 10000:10000 market-ecology-observer
```

Container storage is ephemeral unless the provider mounts persistent storage at `/app/data/live`; captures can be lost on restarts. Without access controls the published dashboard exposes public market observations and replay records, not account credentials. Restrict access through the hosting provider if desired. There are no order submission or private-account calls.

No hosting service has been provisioned or billed. A connected hosting account is required before the agent can deploy. Render was discovered as an available deployment integration; its connection is pending user action. Location eligibility, pricing and public/private access must be checked against that account before provisioning.

## Live acceptance checks

1. Reach the public REST and WebSocket endpoints from the permitted runner.
2. Receive a real snapshot and bridge; observe advancing update IDs.
3. Keep current prices unavailable on gaps/stale events and validate reconnect/resnapshot with captured events.
4. Compare replayed states with the live capture and inspect the browser dashboard.

A successful HTTP server health check alone is not proof of a live exchange feed. Until the exchange checks pass, the status remains a prepared deployment, not a working live deployment.
