# PR25 foreground live outing map

PR25 adds the browser experience for PR24's authenticated current positions and
durable public SSE stream. It does not change the backend contract, participant
routes, persistence, authorization, event grammar, or replay policy.

## Product behavior

An outing page continues to render every participant's independent immutable route.
When live positions are configured, it also opens one public EventSource and renders
each current participant coordinate with an accuracy area. The coordinate is the
exact unsnapped value returned by PR24. It is never projected onto a route and is not
interpreted as progress, deviation, movement, speed, heading, or an ETA.

Fresh positions use full marker opacity and the text **Live**. Positions past their
server-provided `stale_at` use reduced opacity and the text **Stale**. Positions past
`expires_at` are omitted locally while backend cleanup is pending. Accuracy remains
visible in participant-card text. The browser recomputes these states from the
snapshot's server clock offset; the timer does not poll.

Clicking a marker or label selects the same participant card and emphasizes that
participant's route. Live updates do not fit or pan the map. Initial outing loading
may fit all immutable routes once.

## Public viewers and capabilities

Anyone with the unlisted public link can see currently shared positions, participant
display names, and planned routes. Public viewing opens EventSource without a query,
fragment, or capability and never asks for geolocation permission.

Owner, invitation, and participant capabilities are never written to HTML, map data,
public live state, history, logs, or browser storage. A participant capability exists
only in the current JavaScript in-memory receipt. Reloading therefore intentionally
returns the page to viewer-only mode.

After creating an outing, **Open public view** opens the capability-free link in a
new tab. **Open live outing in this tab** fetches the ordinary snapshot, derives the
creator participant receipt from the already in-memory owner receipt, and switches
the initialized SPA to outing display. The address is replaced with the
capability-free `/o/{slug}` public path and the history state is `null`; reloading
therefore opens viewer-only mode. It shows Start controls but does not request
permission or start sharing. An owner-only Delete action remains available in this
same-tab view without placing the owner capability in the DOM. A successful join
keeps only its participant receipt in memory, shows participant controls, and leaves
sharing stopped.

## Explicit Start lifecycle

Only a real click on **Start sharing** calls `watchPosition`, keeping the permission
request attached to that action. Loading, creating, joining, opening, reconnecting,
and opening the live panel never start the watch.

The watch requests high accuracy, accepts fixes up to ten seconds old, and uses a
30-second acquisition timeout. A fix is rejected unless latitude, longitude,
accuracy, and timestamp are finite and within backend bounds. Optional altitude,
speed, and heading become `null` when invalid; values are never clamped or invented.
The captured timestamp comes from the browser fix and is converted to UTC rather
than replaced with the current time.

The first valid fix publishes promptly. Later publications occur at most every five
seconds. There is one PUT in flight and one latest pending sample; a newer sample
replaces the pending one. No array of coordinates, breadcrumb, completed activity,
or historical track exists.

Client sequence orders updates. Each publication chooses a JavaScript safe integer
at least `max(Date.now(), lastAcceptedSequence + 1)`, seeded from the participant's
current public position. Captured time does not order backend updates. On one
sequence conflict, the browser fetches `/live`, advances above the participant's
authoritative sequence, and retries the latest sample once. Safe-integer exhaustion
stops sharing. Transient failures use one bounded in-memory retry timer capped at
approximately 30 seconds; no retry state survives reload.

## Stop, page exit, leave, and deletion

**Stop sharing** immediately invalidates the sampling generation, clears the local
watch, cancels timers, and discards the pending sample. If a PUT is already
dispatched, Stop waits for its definite HTTP outcome before sending authenticated
DELETE, with a bounded wait so the action cannot hang. A definite PUT outcome
followed by successful DELETE permits optimistic marker removal while EventSource
stays open.

A transport failure, abort, or timeout is uncertain because PR24 has no clear
tombstone that can reject a later-arriving PUT. Stop still attempts DELETE, but it
does not claim reliable success or optimistically remove the marker; the UI warns
that the last position may remain until expiry and keeps Stop available for retry.
Every asynchronous tracker operation owns a monotonic generation, so late fixes,
PUTs, conflict recovery, clears, timers, and finalizers from an invalidated session
cannot mutate a newer session.

When an actively sharing page receives `pagehide`, it performs the same local
shutdown and makes one best-effort same-origin DELETE with `fetch(..., {
keepalive: true })`. It does not block navigation and cannot promise delivery.
`sendBeacon` is unsuitable because the participant header is required. Pressing Stop
is the reliable action. Merely hiding the document does not stop sharing, although a
browser may suspend or throttle foreground JavaScript.

Participant Leave first aborts and stops the tracker without a separate live clear,
then uses the existing participant DELETE so PR24 atomically writes the
`participant_left` tombstone. Owner deletion also stops the tracker before deleting
the outing. `outing_closed` closes the stream, stops local tracking without another
mutation, clears live overlays, and disables live and membership controls.

## EventSource and recovery

Exactly one EventSource exists per active outing page. Named listeners handle
`snapshot`, `reset`, `position_updated`, `position_cleared`, and `outing_closed`.
Snapshot/reset replaces authoritative public current state. A contiguous update
upserts one participant; a clear removes one participant. Duplicate IDs are ignored.

Malformed payloads, mismatched SSE IDs, and event gaps never partially mutate public
state. The controller quarantines the old EventSource immediately, shows
**Reconnecting**, performs one single-flight `GET /live`, replaces state with that
authoritative snapshot, and creates a new capability-free stream without a cursor
parameter. Every source and recovery callback captures the outing slug and a
monotonic lifecycle epoch. An old callback or recovery resolving after
`outing_closed`, page exit, leave, deletion, or replacement cannot restore state or
open another stream. If the recovery snapshot request itself fails transiently, the
still-current session creates exactly one new capability-free stream instead of
remaining disconnected; `outing_not_found` closes the experience without
reconnecting. Native transient reconnection retains the last display without
creating a duplicate stream.

An update for a participant absent from the ordinary outing snapshot triggers one
single-flight ordinary outing refresh. A `participant_left` clear does the same so
the immutable route and card disappear. Invalidations arriving during a membership
GET mark it dirty and cause one serialized rerun, preventing a pre-leave response
from becoming the final view. Freshness and selection update existing participant
card nodes in place, preserving keyboard focus; only membership changes rebuild the
card structure. If a refresh proves that the in-memory participant has been removed,
the tracker shuts down and that stale participant receipt and its controls disappear;
an independent owner receipt remains available for owner deletion. These refreshes
do not regenerate, reroute, rerank, or automatically refit the map.

## Privacy and browser limitations

The live panel states that anyone with the unlisted link can see current sharing and
that nicknames may be appropriate. It also states that sharing is foreground-only,
that no historical track is retained, and that closing or suspending the tab can
leave the last position visible until server expiry.

PR25 deliberately has no service worker, install manifest, background location,
persistent queue, notification, wake lock, WebSocket, route matching, ETA,
rendezvous, or messaging behavior. Those concerns remain outside this change and
form part of the PR26 boundary.
