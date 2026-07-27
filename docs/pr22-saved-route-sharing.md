# PR22 — immutable saved-route snapshots and unlisted sharing

Saved routes preserve one canonical source request and one selected
`PlanCandidate`. Loading, sharing, exporting, and deleting a saved route never
regenerates, reroutes, or reranks it.

## Persistence

The application service depends on the typed `SavedRouteRepository` protocol. The
production adapter uses Python's standard-library `sqlite3` module with one
short-lived connection per operation, WAL journaling, a 5,000 ms busy timeout, bound
SQL parameters, and explicit write transactions.

The database contains one application table, `saved_routes`, with an internal ID,
schema version, opaque public slug, SHA-256 owner-token hash, compact canonical source
request and candidate JSON, and UTC creation and expiry timestamps. Public slugs and
expiry timestamps are indexed. The schema is initialized idempotently at startup and
expired records are purged.

The raw owner token is returned only by creation. It is retained only in the creator
page's in-memory state and is never placed in storage, URLs, browser storage, shared
HTML, GPX, or GET responses. Unknown, expired, and unauthorized deletion requests all
produce the same safe not-found response.

## Configuration

- `SUGARGLIDER_SAVED_ROUTE_DATABASE_PATH`, default
  `/data/saved-routes/saved-routes.sqlite3`; an explicit null path disables only saved
  routes.
- `SUGARGLIDER_SAVED_ROUTE_TTL_DAYS`, default 90 and bounded from 1 through 365.
- `SUGARGLIDER_SAVED_ROUTE_MAX_SNAPSHOT_BYTES`, default 10,000,000 and bounded from
  100,000 through 50,000,000.

Expected SQLite startup failures install an unavailable saved-route service without
preventing health, routing, or planning startup.

## HTTP workflow

Create a snapshot by posting the exact canonical request and selected candidate:

```http
POST /v2/saved-routes
Content-Type: application/json

{
  "schema_version": 1,
  "source_request": { "...": "canonical PlanRequest" },
  "candidate": { "...": "published PlanCandidate" }
}
```

The `201 Created` response contains the public slug, relative `share_path` and
`gpx_path`, expiry timestamp, exact snapshot, and an `owner_token`. The token is a
one-time creation receipt capability: retain it only in memory and send it in
`X-Saved-Route-Owner-Token` to delete the snapshot. Public GET responses, GPX,
shared URLs, HTML, logs, and browser storage never contain it.

```http
GET /v2/saved-routes/{slug}
GET /v2/saved-routes/{slug}/gpx
GET /r/{slug}
DELETE /v2/saved-routes/{slug}
X-Saved-Route-Owner-Token: creation-response-token
```

Unknown, expired, missing-token, malformed-token, and incorrect-token deletion
requests share the same safe `404` response. Expired records are purged at startup
and lazily on access. Corrupt or no-longer-valid persisted models fail closed with a
safe storage error.

## Snapshot display and forking

Opening `/r/{slug}` loads only the immutable request and candidate. It does not load
current routing-profile availability, call GraphHopper, plan, rerank, or fabricate
search budgets and cache diagnostics. GPX is produced directly from the stored
candidate.

Snapshot controls and map mutation are locked until the user chooses **Use as a new
plan**. That explicit action fetches the current routing-profile catalogue and POI
status, copies the canonical request into independent editable planner state, and
does not generate automatically. The original snapshot and share link remain
unchanged. A later save creates a new snapshot.

Saving and sharing are separate actions. A successful save displays its unlisted
link; the user may then copy it or explicitly invoke the browser share sheet. Share
cancellation does not invalidate or report failure for the completed save.

## Privacy, availability, and limitations

Unlisted slugs are access capabilities rather than authentication. Anyone with the
link can view or download the snapshot. Deletion requires the separate owner token,
which cannot be recovered after the creator page session ends. Snapshots expire
after the configured TTL and are not collaborative mutable documents.

Setting `saved_route_database_path` to null disables only saved-route endpoints and
UI actions. Expected SQLite initialization failures install an unavailable service;
health, readiness, planning, reversal, and ordinary GPX remain independent.

Manual acceptance covers exact create/GET equality, direct stored GPX, read-only
desktop and 390 px snapshot display, zero generation during load, explicit editable
forking, API restart persistence, deletion, and unaffected ordinary generation and
reversal.
