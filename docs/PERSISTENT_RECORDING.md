# Verifiable market recordings

Raw book and trade messages now use private 8 MiB JSONL segments under
`CAPTURE_ARCHIVE_DIR` (Docker default `/app/storage/capture`). The directory must
be outside the HTTP dashboard directory. Each process has a unique session ID;
restarts cannot append to an earlier unfinished segment.

Completed segments have an atomic manifest containing SHA-256, byte count,
record count and first/last receipt timestamps. The segment and manifest are
flushed and fsynced before publication. `verify_segment` checks hashes, counts
and complete lines before returning records. A manifest proves byte integrity,
not exchange completeness, timing quality or contiguous coverage.

Abrupt termination can leave `.partial` files or finalized files without
manifests. These are excluded from verified research; no automatic repair,
promotion or deletion occurs. Connection gaps remain gaps. Closed segments are
preserved across restarts only when this path is actually on persistent storage.

`state.json` and `ecology.json` contain archive health, current-session counts
and errors. A write error stops recording for the session and is visible in the
health output; the observer can continue showing the live book. Recording also
stops before opening a new segment when less than 64 MiB remains. There is no
automatic disk growth or deletion. Monitor storage and export recordings before
capacity is exhausted. A full disk can also prevent dashboard publication.

## Prepared Render configuration — not activated

Existing service: `market-ecology-live-observer`,
`srv-davf3spsrm7s73bososg`, Frankfurt, Docker, single instance.

Keep the existing service/repository/branch and change only:

- Compute: Free → Starter (512 MiB).
- Attach a 10 GB persistent disk named `market-recordings` at `/app/storage`.
- Environment: `CAPTURE_ARCHIVE_DIR=/app/storage/capture` (already default in Docker).

Published baseline pricing checked 2026-10-02: $7/month compute plus
$2.50/month disk = $9.50/month, before taxes or any other metered charges.
Sources: https://render.com/pricing and https://render.com/docs/disks.
Disk-backed deploys briefly stop the single instance; they are not zero downtime.
Docker creates the mount directory with observer ownership; verify write access
on the actual mounted disk and confirm archive health after activation.

Acceptance: a completed segment must pass verification before and after an
actual service restart. An in-process test or configured environment variable
is not proof that cloud persistence works. Previous ephemeral data is not
recovered by attaching a new disk. Continuous-day coverage is still required
before new calibration or strategy evaluation.
