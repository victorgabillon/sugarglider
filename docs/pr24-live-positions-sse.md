# PR24 authenticated live positions and durable SSE

## Product and privacy boundary

An outing participant may explicitly publish one current device position while
continuing to follow an independent immutable route. A live position belongs to the
participant identity, not to route geometry or a shared itinerary. The backend never
snaps it, calculates route progress, infers motion, changes a route, or calls
GraphHopper.

Anyone holding the unlisted outing slug can read current positions and subscribe to
events. This is unlisted sharing, not private access control or encryption.
Participant display names and temporarily retained coordinates may therefore be
visible to link holders. Publishing and stopping require the participant capability;
that token is sent only in `X-Sugarglider-Participant-Token` and never enters public
models, SSE data, logs, query parameters, or URLs.

PR24 is backend-only. Production JavaScript contains no browser geolocation,
`EventSource`, moving live markers, background API, or service worker. PR25 owns the
explicit browser sharing lifecycle.

## Public API

Publish an unsnapped current position:

```http
PUT /v2/outings/{slug}/participants/{participant_id}/position
X-Sugarglider-Participant-Token: <participant capability>
Content-Type: application/json

{
  "schema_version": 1,
  "sequence": 12,
  "coordinate": {"lat": 48.87, "lon": 2.10},
  "accuracy_m": 8,
  "altitude_m": 92,
  "speed_m_s": 1.4,
  "heading_deg": 180,
  "captured_at": "2026-07-28T12:00:00Z"
}
```

`DELETE` on the same path stops sharing and is idempotent after authorization.
`GET /v2/outings/{slug}/live` returns the authoritative current snapshot in immutable
participant join order. It needs no capability beyond the unlisted slug.
`GET /v2/outings/{slug}/events` opens the public unlisted SSE stream and accepts an
ASCII nonnegative `Last-Event-ID` header.

Wrong, missing, malformed, unknown, or expired participant capabilities uniformly
return `404 outing_not_found`. Timestamp policy failures use
`422 outing_position_invalid`; nonadvancing or conflicting payloads use
`409 outing_position_sequence_conflict`; malformed SSE cursors use
`400 outing_live_cursor_invalid`; safe storage failures use
`503 outing_storage_unavailable`.

## Sequence and timestamp semantics

Client sequence is the only update ordering key. With no current position, any
nonnegative sequence is accepted. A greater sequence replaces it. An equal sequence
with identical canonical client fields returns the existing server timestamp without
another event. A lower sequence, or equal sequence with different fields, conflicts.
Captured time never decides ordering.

The server supplies `received_at`, then derives `stale_at` and `expires_at`. Captured
time must be within the configured maximum age and future tolerance. By default a
position is stale after 120 seconds but remains visible until it expires after 3,600
seconds. Expiry removes current state and appends `position_cleared` with reason
`expired`.

## Durable current state and bounded replay

PR24 adds exactly two tables to the existing outing SQLite database:

- `outing_live_positions` stores one authoritative current row per participant;
- `outing_live_events` stores a bounded per-outing recovery window.

The additive `outings.live_event_cursor` column is migrated with
`INTEGER NOT NULL DEFAULT 0`. Event-producing transactions increment that durable
cursor under the same `BEGIN IMMEDIATE` lock and never allocate from retained event
rows. Age or count pruning can therefore remove every replay row without resetting
the cursor or reusing an event ID. Existing PR23 outing, participant, and copied-route
values remain unchanged.

Accepted state mutation and `position_updated` event append share one
`BEGIN IMMEDIATE` transaction. Clear, participant-left cleanup, event allocation, and
retention pruning are likewise atomic. Event IDs increase per outing. Age and count
limits bound the replay log; it is not a long-term activity history. Current state is
never rebuilt by replay, and there is no historical-track endpoint.

Current rows and recent events survive API restart. Startup purges expired outings,
expires old live rows with clear events, and removes globally old replay records.
Every successful live-backed participant leave atomically removes current state when
present, appends exactly one `participant_left` tombstone, and then deletes the
participant row. Outing deletion or expiry cascades participants, current positions,
and all events. Live reads and mutations actively delete an outing after its outing
TTL, even when its latest position has not yet reached position expiry.

## SSE grammar and recovery

A new stream registers with the process-local broker before its first database read.
Without `Last-Event-ID`, it emits:

```text
retry: 5000
id: <snapshot cursor>
event: snapshot
data: <compact OutingLiveSnapshot JSON>
```

A retained cursor replays every later `position_updated` or `position_cleared` event
in ID order. A cursor older than the retained window or ahead of current state emits
`reset` with the current snapshot and cursor. An empty retained table while the
durable cursor is ahead of the client is an exhausted replay window and also requires
a reset; a client already at the durable cursor remains current. Periodic comments
use exactly `: keep-alive` and carry no event ID. When an outing disappears, the
stream emits `outing_closed` when possible and closes.

Snapshot positions, durable cursor, and oldest retained event ID are loaded in one
explicit deferred SQLite read transaction. Snapshot/reset frame IDs and internal
stream cursors always represent that same read snapshot, so an overlapping update is
either included in the snapshot or delivered as the following durable event.
Because retention can advance between that atomic state read and the separate replay
query, every returned replay is checked for contiguous event IDs beginning
immediately after the client cursor and extending through the represented durable
cursor. A missing beginning or internal gap is discarded without partial delivery;
the stream loads a fresh atomic state and emits one reset from that exact snapshot.

The in-process broker stores no payload and uses one coalescing `asyncio.Event` per
subscriber. It reduces local latency but is not durable truth. Every wake and
keepalive timeout queries SQLite, so another API process's commits are eventually
delivered. All synchronous SQLite work is dispatched through the application
threadpool rather than run on the event loop.

PR24 owns this backend protocol, persistence, authorization, freshness, and replay
grammar. The capability-free public EventSource client, explicit foreground browser
geolocation, latest-only publication controller, and unsnapped live map overlays are
implemented by PR25 without changing these endpoints. See
[`pr25-foreground-live-map.md`](pr25-foreground-live-map.md).

## Configuration

Defaults and bounds are:

- `SUGARGLIDER_OUTING_LIVE_STALE_AFTER_SECONDS=120` (15–3,600)
- `SUGARGLIDER_OUTING_LIVE_EXPIRE_AFTER_SECONDS=3600` (60–86,400)
- `SUGARGLIDER_OUTING_LIVE_MAX_UPDATE_AGE_SECONDS=600` (30–86,400)
- `SUGARGLIDER_OUTING_LIVE_FUTURE_TOLERANCE_SECONDS=30` (0–600)
- `SUGARGLIDER_OUTING_LIVE_EVENT_RETENTION_SECONDS=900` (60–86,400)
- `SUGARGLIDER_OUTING_LIVE_MAX_EVENTS_PER_OUTING=1000` (10–100,000)
- `SUGARGLIDER_OUTING_LIVE_SSE_KEEPALIVE_SECONDS=15` (5–60)

Stale must precede expiry, and keepalive must be shorter than event retention. Live
data uses `SUGARGLIDER_OUTING_DATABASE_PATH`; no new database or volume is created.
A shared database initialization failure coherently disables ordinary outing and
live endpoints while planning, routing, saved routes, GPX, nature, and POIs remain
available.

## Manual acceptance

Use two participants with unrelated routes and keep capabilities in a restrictive
temporary script rather than shell history. Open SSE and verify the initial snapshot,
one event for an accepted update, no event for an identical retry, increasing event
IDs, `409` for an older sequence, independent participant state, normal `/live`
reads, reconnect replay, stale-cursor reset, stop and participant-left clear events,
restart persistence, stale/expiry timing, keepalive comments, and stream closure after
outing deletion. Confirm there are no planning, visualization, saved-route, or
GraphHopper calls and no capability in SSE data. Stop Compose before deleting only
disposable outing SQLite/WAL/SHM acceptance files; preserve `data/outings/.gitkeep`
and unrelated saved-route data.
