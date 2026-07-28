# PR23 shared outings

## Product scenario and boundary

An outing is an unlisted container for people going out together while following
independent plans. Victor may contribute a long `trail_run` loop while another
participant contributes a shorter `city_bike` point-to-point route. The service
does not assume shared geometry, starts, destinations, profiles, distances,
topology, waypoints, direction, or departure plan.

PR23 deliberately contains no live position, geolocation, tracking, SSE,
WebSockets, polling, ETA, rendezvous, messaging, navigation, route changes, user
accounts, or invitation delivery. PR24 owns the future live-position boundary.

## Domain and copied-route semantics

Each schema-version-1 outing has a title, UTC creation and expiration times,
capacity, and participants in immutable join order. Each participant owns:

- an opaque public participant ID;
- a bounded display name;
- a UTC join time;
- an `OutingPlannedRoute` containing one canonical `PlanRequest` and the exact
  selected `PlanCandidate`.

The API resolves a PR22 saved-route slug only during create or join. It passes the
exact request and candidate to the outing service, which runs neutral submitted
candidate validation and copies their canonical JSON into the separate outing
database. It stores neither the saved-route slug nor a foreign key. Deleting,
expiring, disabling, or moving the source saved-route database cannot remove or
change the outing copy. Reads reconstruct and validate persisted JSON again.
Nothing regenerates, reroutes, reranks, or reanalyzes a copied route.

## API

Create from an existing saved route:

```http
POST /v2/outings
Content-Type: application/json

{
  "schema_version": 1,
  "title": "Forest and gravel day",
  "participant_display_name": "Victor",
  "saved_route_slug": "abcdefghijklmnopqrstuv"
}
```

The `201` response contains the public snapshot plus one-time owner, join, and
initial-participant tokens. `Location` identifies `/v2/outings/{slug}` and
`Cache-Control` is `no-store`.

Public reads:

```http
GET /v2/outings/{slug}
GET /o/{slug}
GET /v2/outings/{slug}/participants/{participant_id}/gpx
```

The JSON and page use private/no-store, no-index, and no-referrer headers. Public
models contain no capabilities or storage details. The GPX serializes the stored
participant candidate directly as one track and one segment with no GPX route.

Join with a separately saved route:

```http
POST /v2/outings/{slug}/participants
X-Sugarglider-Outing-Join-Token: <join capability>
Content-Type: application/json

{
  "schema_version": 1,
  "display_name": "Gravel friend",
  "saved_route_slug": "zyxwvutsrqponmlkjihgfe"
}
```

The response returns the updated outing, public participant ID, and one-time
participant capability. Leaving and owner deletion use:

```http
DELETE /v2/outings/{slug}/participants/{participant_id}
X-Sugarglider-Participant-Token: <participant capability>

DELETE /v2/outings/{slug}
X-Sugarglider-Outing-Owner-Token: <owner capability>
```

Unknown, expired, malformed, missing, or incorrect capabilities all use the same
safe `404 outing_not_found`. A full outing is disclosed as `409 outing_full` only
after valid join authorization. Other stable errors are
`outing_candidate_invalid`, `outing_route_too_large`, and
`outing_storage_unavailable`.

## Capabilities and links

The service generates independent owner, join, and participant capabilities and
persists only SHA-256 bytes. Authorization uses `hmac.compare_digest`.
Capabilities never enter logs, public GET models, GPX, HTML, SQL plaintext,
cookies, localStorage, sessionStorage, IndexedDB, or query parameters.

The ordinary link is `/o/{slug}`. An invitation is
`/o/{slug}#invite={join_token}`. URL fragments do not reach the server. The
browser captures the token into memory and immediately calls
`history.replaceState` to remove the fragment. Public and invitation links are
visibly distinguished, and sharing/copying occurs only after an explicit click.

## Persistence and configuration

The standard-library SQLite adapter uses one short-lived connection per operation
with WAL, a 5,000 ms busy timeout, and foreign keys enabled. It creates exactly:

- `outings`: internal ID, schema version, public slug, owner/join token hashes,
  title, UTC timestamps, and capacity;
- `outing_participants`: internal and public IDs, outing foreign key,
  participant-token hash, display name, exact request/candidate JSON, join time,
  and join order.

Creating the outing and initial participant is one transaction. Joining uses
`BEGIN IMMEDIATE`, so capacity checking and insertion are atomic under concurrent
requests. Deleting an outing cascades participants.

Configuration defaults:

- `SUGARGLIDER_OUTING_DATABASE_PATH=/data/outings/outings.sqlite3`
- `SUGARGLIDER_OUTING_TTL_DAYS=30` (1–365)
- `SUGARGLIDER_OUTING_MAX_PARTICIPANTS=8` (2–20)
- `SUGARGLIDER_OUTING_MAX_ROUTE_SNAPSHOT_BYTES=10000000`

A null database path disables only outings. Initialization failure installs an
unavailable outing service after one safe warning; planning, routing, saved
routes, GPX, health, readiness, nature, and POIs remain operational.

## Browser flow and privacy

After saving a route, “Create outing” asks for a title and display name. The
creation receipt keeps owner, join, and participant capabilities in memory and
offers separate open, copy, share, delete, and dismiss actions. Nothing is copied
or shared automatically.

Opening `/o/{slug}` fetches only UI map configuration and the outing snapshot.
It does not fetch routing profiles, POIs, saved routes, planning, route
visualization, or GraphHopper. Every exact stored geometry is rendered separately
with a deterministic palette. Selection emphasizes one participant and displays
its stored metrics and traversal without hiding or mutating the others and
without fabricating a `PlanResult` or search diagnostics.

Anyone holding the public link can see participant display names and planned
routes. The outing is unlisted, not private, encrypted, or access-controlled.
Participants should use nicknames when appropriate. PR23 collects no live
position.

## Manual acceptance

Generate and save a long hiking/trail-running route and create an outing. Confirm
the invitation capability is in a fragment and is scrubbed on open. In another
planner tab, generate and save a shorter cycling route, then join with its link.
Verify both exact request/candidate pairs, distinct profiles, lengths, and
geometries through the API and simultaneous map display. Confirm outing load
causes no planning or GraphHopper request, each GPX contains only its participant
route, source saved-route deletion does not affect either copy, and the outing
survives API restart. Then leave as the second participant, delete as owner, and
verify `404`. Repeat at desktop and exactly 390×844 and inspect severe console
events. Delete temporary capability files and generated acceptance artifacts.
