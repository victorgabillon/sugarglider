# PR43 — Small production social service

The production entry point is `python -m sugarglider.social_server serve`. It
starts SQLite-backed sharing, outings and latest-position services without
constructing a routing client, loading a regional index, or starting a routing
process. The development/reference `sugarglider.api.main:app` remains separate.

This milestone was prepared independently from main `15f3df3` while PR40 awaited
its required unlocked Fairphone acceptance. It does not enable Android release
planning or declare the V1 product ready. Those gates belong to PR41/42/44.

## Service boundary

| Surface | Production behavior |
| --- | --- |
| Saved routes | Existing immutable submitted-candidate validation, create/read/delete and stored-candidate GPX |
| Outings | Existing independent participant snapshots and owner/join/participant capability checks |
| Live positions | Existing authorized latest-position PUT/DELETE, current snapshot and durable bounded SSE replay |
| Shared browser pages | Packaged application shell, public configuration and static application assets |
| Profile metadata | All six public identities; server availability explicitly false with `server_planning_disabled` |
| Display projection | Existing `/v2/plans/visualization` classifies supplied geometry for shared-web highlighting, in a worker thread; no routing, nature lookup, geometry alteration or reranking |
| Planning/reversal | No endpoints, dependencies or network fallback; requests return 404 |
| Maps/region files | No tile server, pack download endpoint, PBF processing or regional index loading |
| Health/readiness | `/health` reports process liveness; `/ready` checks initialized services, retention health, existing SQLite tables/write locks and available disk |

Generating 100 routes on a device causes no routing computation in this service.
Sharing any of those routes is an explicit separate snapshot operation. Static
region downloads require a separately approved static host. The social container
has no egress network in the supplied deployment.

The small shared persistence and UI-configuration factories are also used by the
reference application. Its behavior and existing snapshot contracts remain tested.
SQLite access stays inside the repository adapters; the production maintenance
adapter owns readiness and backup SQL. Planning does not import saved routes or
outings. No public candidate schema changes were made.

## Provider-neutral deployment

`deploy/social/compose.yaml` runs one application process and Caddy for HTTPS.
There is no database server, routing service, map service or orchestration cluster.
Images are pinned by manifest digest; Python dependencies use `uv.lock`.
The positive Docker context allowlist excludes data, Android output and secrets.

The application runs as UID/GID 10001 with a read-only root filesystem, all Linux
capabilities removed, no privilege escalation, 128 PIDs, one CPU and a 512 MiB
memory limit. Caddy has a 128 MiB limit and only `NET_BIND_SERVICE`. The API has
no published port: only the HTTPS proxy on its private network can reach it.
Caddy additionally has a network for ports 80/443 and certificate issuance.
The application trusts forwarded client headers only because this private
deployment boundary excludes direct clients. Never publish its port or attach
untrusted containers to that network with `--trust-proxy` enabled.

Before deployment, the operator supplies an approved machine, domain, DNS and
firewall configuration. No host, account, domain, certificate issuance or paid
resource was provisioned by this milestone.

1. Put the reviewed checkout at `/srv/sugarglider` on a Linux machine with Docker
   Compose. Create `/etc/sugarglider/social.env`, readable only by the operator,
   from `deploy/social/.env.example`. Set the approved hostname and reviewed Git
   commit. Do not use the example domain or put capability tokens in this file.
2. Point the approved domain at that machine and allow TCP 80/443; UDP 443 is
   optional HTTP/3. Leave port 8000 closed. Verify persistent storage and backups.
3. Run the following from the checkout:

   ```sh
   docker compose --env-file /etc/sugarglider/social.env -f deploy/social/compose.yaml config --quiet
   docker compose --env-file /etc/sugarglider/social.env -f deploy/social/compose.yaml build social
   docker compose --env-file /etc/sugarglider/social.env -f deploy/social/compose.yaml up -d social https
   docker compose --env-file /etc/sugarglider/social.env -f deploy/social/compose.yaml ps
   ```

4. Check the approved HTTPS origin's `/health` and `/ready`. Save a synthetic
   candidate, create an outing, publish a synthetic current position, observe SSE,
   clear it and delete the synthetic data using the returned capabilities. Keep
   those capabilities in memory or a protected temporary file; never place them
   in URLs, command arguments, logs or committed fixtures.
5. Verify a backup and restore it into a separate empty test volume before
   admitting real users. Install the supplied systemd backup service/timer after
   reviewing their fixed checkout and environment-file paths:

   ```sh
   sudo install -m 0644 deploy/social/sugarglider-backup.service deploy/social/sugarglider-backup.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now sugarglider-backup.timer
   sudo systemctl start sugarglider-backup.service
   ```

For a process-local development check, set `SUGARGLIDER_SOCIAL_PUBLIC_ORIGIN` to
an exact HTTPS origin and `SUGARGLIDER_SOCIAL_DATA_DIRECTORY` to an absolute
temporary path, then run the entry point without `--trust-proxy`. It binds only
host loopback by default. The configured Host header remains required. This is
not a cleartext production deployment.

## Limits, origin policy and logs

Defaults are explicit in `SocialSettings` and independently configurable with
the `SUGARGLIDER_SOCIAL_` environment prefix. The reference `.env` is not read.

| Limit | Default |
| --- | --- |
| HTTP body | 12,000,000 bytes, also enforced while reading chunked bodies; compressed request bodies rejected |
| Serialized saved/participant snapshot | Existing 10,000,000-byte limit |
| Concurrent requests / body writes | 16 / 2; SSE uses its separate allowance |
| SSE streams | 64 globally, 8 per client address |
| Per-client token bucket | Capacity 240 requests, refill 240/minute |
| Create-route/create-outing bucket | Capacity 30, refill 30/hour, shared by both creation operations |
| Client bucket table | 4,096; idle entries expire after an hour; saturation rejects new identities instead of evicting recent limits |
| Body deadline / proxy header deadline | 30 seconds / 10 seconds |
| SQLite operation lock wait | Existing 5 seconds; readiness probe 1 second |
| Minimum free disk for readiness | 256,000,000 bytes |
| Proxy SSE connection lifetime | 30 minutes, then ordinary capability-free EventSource reconnect/replay |

Rate buckets use process-random keyed hashes of client addresses, remain only in
memory and reset on restart. Shared hotspot/NAT users share a bucket. These are
small-service resource bounds, not a distributed denial-of-service defense.
Failures return bounded generic errors and retry guidance without echoing inputs.

Only the exact configured browser origin is accepted; there is no cross-origin
CORS grant, wildcard or credentialed cross-origin mode. Requests without Origin
remain usable by the existing native HTTP client and must still pass capability
authorization. Cross-site browser mutations, duplicate Host headers, compressed
bodies and all query strings are rejected. Browser invitation authority remains
in an immediately scrubbed URL fragment, which never reaches HTTP.

The application logs only a generated request ID, fixed operation category,
fixed method, status and duration. It never logs a path, slug, query, IP, header,
body, exception text, capability or coordinate. General runtime messages are
reduced to a fixed event and level; full tracebacks are deliberately omitted.
Uvicorn access logging is disabled. Caddy access logging is absent and its
runtime log sink discards records because proxy errors can contain requests.
Docker log files are bounded to three 5 MB files per persistent service.
Use health/readiness, restart counts, memory, disk and safe application status
categories for monitoring. Do not turn on raw HTTP debug logging in production.

Caddy's [SSE handling](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#streaming)
flushes `text/event-stream` automatically. The configuration intentionally avoids
`flush_interval -1`, whose documented behavior retains an upstream after the
client disconnects. ASGI admission passes real disconnects through and releases
its counts in `finally`; existing broker subscriptions also close on disconnect.

## Persistence, retention and recovery

The named `social-data` volume contains `saved-routes.sqlite3` and
`outings.sqlite3`, including their SQLite WAL/SHM files. Keep it on local persistent
storage with reliable SQLite locks, never an ephemeral container layer or an
unverified network filesystem. Use one application worker for these published
rate/concurrency budgets. SQLite and durable cursors remain authoritative; the
process-local SSE broker is only a wakeup optimization.

Saved snapshots expire after 90 days and outings after 30 days; operators may
shorten these values. Live positions become stale after 120 seconds and expire
after 3,600 seconds. Replay retains at most 900 seconds and 1,000 events per
outing. A 60-second background cleanup offloads all SQLite work and removes
expired records even when nobody reads them. Access-time enforcement and startup
cleanup remain in place. Failed cleanup marks readiness unavailable until a
successful pass. Successful participant leave and outing deletion retain the
existing atomic tombstone/cascade behavior.

The backup command copies only allowlisted saved-route, outing and participant
tables. Each database is read in an explicit consistent transaction; the two
databases need no shared transaction because participant route snapshots are
independent copies. Expired snapshots are excluded. **Live-position and replay
tables are never copied**, even temporarily. Durable outing cursors are retained.
The verified pair and a size/SHA-256 manifest are staged in a private directory,
fsynced and renamed only when complete. Files are mode 0600, directories 0700.
The backup may contain private route snapshots and hashed capabilities; protect
it like the primary database.

```sh
docker compose --env-file /etc/sugarglider/social.env -f deploy/social/compose.yaml run --rm --no-deps backup
docker compose --env-file /etc/sugarglider/social.env -f deploy/social/compose.yaml run --rm --no-deps backup python -m sugarglider.social_server verify-backup /backups/EXACT_BACKUP_NAME
docker compose --env-file /etc/sugarglider/social.env -f deploy/social/compose.yaml run --rm --no-deps backup python -m sugarglider.social_server prune-backups /backups --retain-days 7
```

The supplied daily timer performs backup and seven-day pruning. Pruning deletes
only verified completed directories with the command's exact generated naming
format; unrelated files and symlinks are ignored. Invalid backups stop pruning
with an explicit failure. A killed backup can leave a hidden `.partial` directory;
inspect and remove that incomplete copy explicitly, without touching live data.
Monitor backup failures and disk use. Copy verified backups to encrypted off-host
storage using the operator's chosen credentials, applying the same seven-day
retention there. A volume on the same machine alone is not disaster recovery.

Restore procedure:

1. Verify the exact backup with `verify-backup`. Preserve the existing live volume
   for investigation; never overwrite it while either application is running.
2. Stop the application and proxy. Provision a new empty private volume owned by
   UID/GID 10001 and copy only the two verified `.sqlite3` files into it, mode 0600.
   Do not mix in an old WAL/SHM file or restore a `.partial` directory.
3. Point an isolated test deployment at the new volume, then start the reviewed
   image. Startup removes expired snapshots and initializes normal WAL operation.
4. Confirm readiness, exact saved and participant GPX, and empty live positions.
   Reconnected clients receive a reset when retained replay is absent. Sharing
   resumes only through the existing explicit client activation flow.
5. Switch the production volume only after the operator accepts the recovery
   point and verifies synthetic end-to-end operations.

Daily backups imply up to roughly one day of snapshot loss. A restore can
resurrect a snapshot or membership deleted after that backup; the operator must
reconcile known deletions before reopening the service. Backups never restore
location history. No automated destructive database migration or restore is
included. Retention is logical deletion, not a promise of immediate forensic
erasure from SQLite pages, device media or operator-controlled older copies.

For upgrades, take and verify a backup, build the new reviewed revision, and
recreate the application container. Graceful shutdown is bounded to 20 seconds
inside Compose's 30-second grace period; SSE reconnects use durable state. Retain
the previous reviewed image for rollback. PR43 changes no persisted schema.

## Evidence and remaining gates

Initial automated evidence on the independent PR43 branch:

- `make check`: 1,010 tests passed, 16 existing integration tests deselected;
  Ruff and strict mypy passed over 239 source files. A subsequent focused run
  including backup retention passed all 31 new social tests. Final totals are
  recorded below after the final checks.
- `docker build -f apps/social/Dockerfile -t sugarglider-social:pr43-local-check .`:
  PASS. The image contains the application and locked Python runtime, no graph,
  regional artifacts or Java/native routing engine.
- `docker compose -f deploy/social/compose.yaml config --quiet`: PASS with
  explicit example validation variables. `caddy validate`: PASS on the pinned
  Caddy image with networking disabled.
- Temporary HTTPS acceptance driver
  `/tmp/sugarglider-pr43-container-acceptance.py`: PASS through an ephemeral local
  Caddy CA trusted only by that test's curl process. Exact production proxy
  directives were used with `tls internal` for the test certificate. The app
  network was internal and contained no routing or regional service. It proved
  save/outing/current-position/SSE/GPX, process restart, exact snapshot restoration,
  rejected planning/origin/query requests, backup verification and private logs.
  Test containers, networks and synthetic data volumes were removed afterward.
- That synthetic run performed 100 sequential HTTPS reads in 2.589 seconds and
  measured 63.09 MiB application / 15.92 MiB proxy memory after the workload.
  These small-fixture host measurements are not a throughput or capacity guarantee
  for 10 MB snapshots, many concurrent users or a production hosting provider.
- Stored GPX SHA-256 from the synthetic fixture:
  `61c3fd52084b4c1a7033afd3ba9729304ae105f124c1bfc7361371e9cc0a2da2`;
  exactly one track and one segment. No generated GPX or capabilities committed.

Final verification after the backup-retention addition:

- `make check`: **1,011 passed, 16 existing integration tests deselected**; Ruff
  and strict mypy passed (239 source files). All 31 new social tests pass.
- Shared-web Chrome harnesses: **94 scenarios PASS** (PR25: 14, PR26: 63, PR27: 17).
- Rebuilt container and repeated HTTPS acceptance: **PASS**; 100 sequential reads
  in 2.692 seconds, application 62.71 MiB and proxy 15.21 MiB. Report:
  `/tmp/sugarglider-pr43-acceptance-nukh9069/report.json`. The earlier small-fixture
  measurements above remain valid evidence from the preceding run.
- CI now builds the production image, boots its factory as UID 10001 with
  networking disabled, checks health/readiness and absent routing endpoints, and
  validates the pinned proxy configuration. Local equivalent smoke passed.
- `git diff --check`: PASS. No Android source, browser module, real data or
  protected worktree/stash content was changed by this branch.

Expected cost drivers are the small persistent machine, retained snapshot disk,
encrypted backups and outbound shared-snapshot/SSE traffic. Device route search
and static regional downloads do not consume this application's routing CPU.
There is no provider price estimate or paid plan selection in this milestone.

**USER_ACTION_REQUIRED for live acceptance:** approve an existing or new hosting
destination, domain/DNS authority and encrypted off-host backup destination.
Provisioning, certificate issuance against the real domain and public smoke
tests remain pending. No claim of public deployment, Android physical acceptance,
Play readiness or approved hosting has been made.
