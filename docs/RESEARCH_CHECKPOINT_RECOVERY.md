# Prepared research checkpoint recovery

Status: implemented and unit checked, not provisioned or activated. The free observer was seen waking on 3 October at approximately 10:30 UTC; its new display had 34 accepted examples and no completed prospective evaluation. Previous progress cannot be recovered from the currently observed process. Do not claim uninterrupted training or completed paper outcomes.

Optional `ECOLOGY_CHECKPOINT_DATABASE_URL` stores bounded audited labels (maximum 20,000), fit reports, and frozen evaluation counters in one JSONB row. It uses TLS, one background writer, a 60-second checkpoint cadence and a five-second connection timeout. Credentials are environment-only; error reports expose exception class, not connection strings. Raw capture files are not persisted by this patch.

Restart restores audited labels but clears raw feature buffers. It invalidates pending paper outcomes and closes any restored frozen evaluation; outages cannot create continuous forecasts or trades. Venue changes still reset venue-specific learning. Stale-model checks and WAIT status remain in effect. Data collected since the last successful checkpoint can be lost. Database outages are reported and collection continues in ephemeral mode.

Tests cover audited-label recovery, invalidating a pending outcome across restart, rejecting invalid label timing before mutation, and rejecting nonfinite checkpoint values. A live database write/read integration test remains required after provisioning.

Activation plan: select the user's confirmed Render workspace, create a Free Postgres instance in Frankfurt if an appropriate free instance is not already available, configure its external TLS connection URL for the existing free web service, deploy the prepared code, and verify checkpoint status plus read-only database state. Do not put credentials into GitHub or public dashboard output. Do not use a paid plan automatically.

Free Render web services sleep after 15 minutes without inbound traffic and lose local changes on sleep/restart. A database preserves checkpoints; it does not make the collector run while asleep. Free Render Postgres expires after 30 days and is temporary recovery storage. Export/migrate before expiry; no production durability guarantee or automatic paid upgrade.

Official limitations: https://render.com/docs/free
