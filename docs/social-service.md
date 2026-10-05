# Optional social service

Sugarglider separates planning from sharing. The reference app may expose persistence
alongside planning. The smaller `sugarglider.social_server` application only stores exact
route snapshots, independent outing membership/routes and latest live positions. It
constructs no GraphHopper client and loads no regional indexes.

## Deployment and enablement evidence

The repository contains a deployable factory, locked container, Compose/Caddy setup,
backup tooling and a CI smoke test. `.github/workflows/social.yml`, despite its name
**Social deployment**, validates configuration, builds the image, runs a network-disabled
factory smoke and validates the proxy. It has no public deployment step.

No live public social origin or successful host provisioning is established by these
checked-in sources. Do not claim a social deployment solely from green CI or the presence
of a production factory. The configured static regional download host is a different
service and contains no social API/database. Deployment requires independent operator
configuration and evidence.

The current bundled Android app disables saved-route sharing, outings and live
publication in both `android_ui_config.json` and `V1ReleasePolicy`. Shared browser/native
implementations remaining in source do not enable those capabilities. The browser
features below apply when a reference/social server actually advertises them.

## Saved routes and outings

`SavedRouteService` validates a submitted canonical request/candidate using the neutral
planning validator, then stores that exact immutable pair. Create returns an unlisted
`/r/{slug}` URL and one owner capability. Public read and stored-candidate GPX never
reroute, regenerate or rerank. Owner deletion uses its header capability; the public
model does not contain it.

An outing copies saved-route snapshots into independent participant records. Joining
uses a separate saved-route slug; each participant may have a different start, activity,
end, distance, topology and waypoint sequence. No shared itinerary is inferred. Copies
survive deletion of the original saved route. Participant GPX serializes only that
participant's stored candidate.

Snapshot display is read-only and carries no fabricated search budgets/cache facts.
**Use as a new plan** explicitly creates independent editable state without automatically
generating. An unlisted URL grants public viewing to anyone holding it; it is not an
account login or strong confidentiality boundary.

## Capabilities and current positions

| Authority | Used for | Where it belongs |
| --- | --- | --- |
| Saved-route owner | Delete that snapshot | Private receipt; request header, never public read models. |
| Outing owner | Manage/delete outing | Private memory-only receipt. |
| Invitation/join | Join outing | Immediately scrubbed URL fragment, then memory; never query string. |
| Participant | Own membership/position mutation | Memory by default; explicitly disclosed Remember may store only whitelisted participant fields. |
| Public unlisted slug | Public route/outing/live read and SSE | Capability-free URL; no owner/join/participant token in it. |

Services store capability hashes, not plaintext authority. Public models, map data,
SSE, logs and HTML must not contain capabilities. “Remember participant” is a browser
exception for participant authority only, not owner/invitation authority.

A participant position is an unsnapped current coordinate, not route progress. Client
sequence orders updates; captured time cannot overwrite newer state. Server timestamps
control stale and expired states separately. The current-position table is authoritative;
replay is strictly bounded and there is no historical-location API.

Live snapshot, cursor and retained replay bound come from one explicit SQLite read
transaction. Per-outing cursors remain monotonic even after pruning removes all events.
Participant leave atomically clears current position and appends one participant-left
tombstone. Outing deletion cascades its live state.

Async SSE handlers offload synchronous SQLite work. The process-local broker only wakes
readers; it carries no authoritative position payload. Recovery reads durable state and
checks the cursor instead of reconstructing current state from event history.

## Browser state and optional persistence

`outing_controller.js` owns page/slug epochs, membership refresh, reconnect and public
live display. `outing_tracking.js` owns explicit foreground sharing: one watcher/session
generation, one publication in flight and only the latest unsent sample. Start comes
from a participant click. Loading, joining, restoring or reconnecting does not start
geolocation/publication. Stop waits for a definite active PUT outcome before clearing;
an uncertain transport outcome retains the expiry warning and retry behavior.

`pwa_store.js` alone opens IndexedDB. Remembered sessions contain only participant
identity/authority and disclosed timestamps; restoration is passive. The durable outbox
contains one latest sample, no token, sequence or coordinate history, and requires an
explicit foreground Resume. Session replacement/forget and outbox mutations are atomic;
a stale tab cannot write coordinates for an authority that was removed.

Public snapshots are saved offline only by **Save for offline use**. They reject
capabilities, live positions/events/cursors and preserve exact immutable routes. The
service worker caches only the explicit application-shell allowlist: never APIs,
unlisted navigations, SSE, GPX, capabilities, coordinates or raster tiles. It never
accesses application IndexedDB. Cache/storage failure must not replace valid network
data or prevent shell startup. No background sync, background browser geolocation,
service-worker position publication or notification behavior exists in this PWA design.
Android skips that service worker; its disabled native tracking is a separate boundary.

## Running and operating the service

The explicit entry point is `uv run python -m sugarglider.social_server serve`.
`SocialSettings` uses `SUGARGLIDER_SOCIAL_` variables, one exact HTTPS public origin and
an absolute data directory, independent of the reference `.env`. The supplied Compose
stack runs one nonroot application worker behind the isolated HTTPS proxy. The app has
no published port/egress, and trusted proxy headers are appropriate only inside that
boundary. Exact-origin/Host checks, bounded bodies, admission and rate limits protect
the small service; they do not implement an account system.

Logs contain fixed operation categories, generated request ID, method/status/duration;
raw URL/slug/header/body/coordinate/capability logging is excluded. Health is liveness;
readiness also checks initialized persistence, retention health, SQLite write locks and
free disk. Do not enable raw HTTP debug logging to diagnose a production service.

Defaults: saved routes 90 days, outings 30 days, live stale 120 seconds, live expiry
3,600 seconds, replay at most 900 seconds / 1,000 events per outing. Access/startup checks
and periodic off-request cleanup enforce retention. Readiness becomes unavailable after
cleanup failure until a successful pass.

Backups copy only allowlisted immutable/membership tables under consistent reads;
current positions and replay events are excluded. Durable cursors are retained. Restore
must be checked in a separate empty test volume. The detailed
[deployment and backup runbook](pr43-social-production.md) and
[Compose configuration](../deploy/social/compose.yaml) describe operator actions, not
an already provisioned service. Hosting, deployment and permission changes require their
own explicit task.
