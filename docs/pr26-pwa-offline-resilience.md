# PR26 installable PWA and explicit offline resilience

PR26 makes the browser application installable and gives users narrowly scoped,
explicit offline persistence. It does not change routing, saved-route or outing
backend models, live authorization, SSE replay, GPX serialization, or the PR25
foreground-only location boundary.

## Installation and local application shell

`/manifest.webmanifest` uses `/` for its ID, start URL, and scope. It contains no
slug, participant identity, query, fragment, capability, or share target. The
192×192 and 512×512 icons are deterministic Lanczos resizes of the canonical
1024×1024 `assets/brand/sugarglider-compact-icon.png`; no new artwork or text was
introduced.

The root `/service-worker.js` owns the versioned `sugarglider-shell-` cache family.
Installation pre-caches `/`, the first-party boot modules and stylesheet, the exact
local MapLibre GL JS 4.7.1 JavaScript/CSS distribution, and essential icons. The
worker does not call `skipWaiting` during installation. It waits until the page
offers **Reload to update**, then accepts one activation message. Activation removes
only older Sugarglider shell caches and claims clients.

Every lookup opens the active Sugarglider cache explicitly; the worker never uses a
global cache match that could return an unrelated origin cache entry. Requests with
authorization, cookie, participant, owner, join, or saved-route-owner headers are
ignored even under `/static/`. Module registration uses `updateViaCache: "none"` so
an imported cache-policy change is revalidated with the worker update. A failed
activation message returns to the retryable update-available state.

MapLibre came from the official `maplibre-gl@4.7.1` npm package with npm integrity
`sha512-lgL7XpIwsgICiL82ITplfS7IGwrB1OJIw/pCvprDp2dhmSSEBgmPzYRvwYYYvJGJD7fxUv1Tvpih4nZ6VrLuaA==`.
The tarball SHA-256 is
`7e8a778cff03abad64ae19674977058616e1cf7c3712cabd1c35461ae465f923`.
Individual installed hashes are recorded beside the files in
`static/vendor/maplibre-gl-4.7.1/README.md`.

## Cache allowlist and navigation fallback

Navigation is network-first. A valid HTTP response, including an error response, is
returned unchanged. The cached root shell is used only when `fetch` throws. Neither
`/r/{slug}` nor `/o/{slug}` navigation HTML is inserted into CacheStorage.

Only query-free same-origin `/static/` GET responses may be cached after install,
and only successful basic responses qualify. The worker ignores non-GET and
cross-origin requests and excludes `/v1/`, `/v2/`, OpenAPI/docs, the manifest, the
worker itself, GPX, live and event paths. API JSON, SSE, capabilities, positions,
unlisted resources, and OSM raster tiles are therefore outside the cache policy.
Cache writes are best effort: quota or transaction failure cannot replace an
otherwise successful basic network response.
Glyphs and nonessential artwork may be cached only when the page normally requests
their bounded static URL; tiles are never cached or prefetched.

## IndexedDB ownership and data classes

Only `pwa_store.js` opens the versioned `sugarglider-pwa` database. Its stores are:

- `public_runtime` for validated non-sensitive UI configuration;
- `offline_snapshots` for explicit public saved-route and outing copies;
- `participant_sessions` for one explicitly remembered participant capability;
- `position_outbox` for at most one latest normalized position per remembered
  participant.

Transactions resolve after completion and a conditional delete supports sample
identity. An in-memory fallback keeps the shell usable when IndexedDB is unavailable
but never claims that data is durable.
Opening and initialization are also optional: when opening or initial pruning fails,
the failed durable connection is closed and every repository is rebuilt over a new
in-memory store. Later optional reads and cleanup failures are caught without
preventing normal online or no-config offline-shell startup.

Snapshot pruning, deterministic oldest-copy eviction, and insertion share one
read-write transaction, so concurrent Saves cannot exceed eight records. The UI
discloses before Save that a ninth copy may replace the oldest. Remembering a new
participant for the same outing atomically removes the prior participant's outbox.
Outbox replacement compares captured time, queued time, and sample ID inside one
transaction, preventing a delayed older-tab write from replacing a newer sample.
That replacement reads the exact participant ID and token in the same cross-store
transaction and writes only while the session still matches. Forget reads and
removes the session and its exact outbox in one transaction, so a stale or abruptly
terminated tab cannot recreate an orphan coordinate record.

Public configuration is whitelisted field by field. Public snapshots are written
only after **Save for offline use**. They are limited to eight bounded records,
validate slugs, timezone-aware timestamps, participant uniqueness, and every route
geometry coordinate, and recursively reject capability/token keys, live positions,
SSE events, and cursors. Expired or malformed records are deleted. Existing explicit
copies may be refreshed after a successful ordinary public GET; merely opening an
unlisted link never creates a copy.

An offline route or outing uses its exact immutable stored request and candidate. It
does not regenerate, route, rerank, visualize through the API, or fabricate search
diagnostics. Outing offline views contain no live positions and create no
EventSource. Mutations and GPX downloads are disabled. MapLibre renders stored
geometry over a labelled neutral background because raster basemap tiles are not
available offline.

## Remembered participant risk and Forget

**Remember this participant on this device** is an explicit action. The UI explains
that anyone with access to the browser profile may act as that participant, that
this is not account authentication, and that site-data clearing or **Forget**
removes it. Remembering stores exactly schema version, outing slug, participant ID,
participant token, outing expiry, remembered time, and last-used time. It never
stores owner or invitation authority and never starts geolocation or publication.

Restore verifies expiry and current outing membership, then reconstructs only the
existing in-memory participant receipt. Controls can reappear, but sharing remains
stopped. Participant removal, outing closure, expiry, **Forget**, or **Clear saved
offline data** removes the session and outbox while leaving any independent owner
receipt in memory.

Restoration itself is pure with respect to application state. Outing load and
reconnect operations recheck their slug and page epoch after every asynchronous
session/outbox read before installing the receipt, selecting a participant,
initializing the map, or opening the live stream.

`navigator.storage.persist()` is requested only from an explicit Save or Remember
action. A false response is normal: the copy remains available but the UI explains
that the browser may evict it under storage pressure. Browsers can still remove
site data, so offline storage is resilience rather than backup.

## Latest-only foreground outbox

The position outbox is not a queue or track. Its exact record has one opaque sample
ID, participant identity without its token, captured and queued timestamps, one
normalized coordinate and sensor accuracy fields, and a resume-required flag. It
contains no sequence, history array, route data, server time, derived motion,
progress, ETA, or previous coordinate. A fresh fix transactionally replaces the
prior record.

For a remembered active participant, persistence completes before its foreground
PUT begins. Sequence remains generated at send time by the PR25 tracker. A successful
PUT conditionally deletes only the matching sample ID, so a late success cannot
erase a newer fix. Stop and Forget invalidate pending operations and delete the
record. A retained record is never sent by page load, restoration, installation, or
the worker. **Start/Resume** is required, and a restored sample older than 15 seconds
is deleted without inventing a timestamp. Captured time must not follow queued time,
and future records are invalid and removed rather than remaining perpetually fresh.

A validated public resource response remains authoritative when optional IndexedDB
refresh fails. Resource, configuration, and persistence outcomes are classified
separately: definite resource not-found wins over a simultaneous configuration
transport failure, while storage failures affect only storage status. Ordinary
online route and outing pages rerender controls on disconnection and retry their
public endpoint on an online hint; a successful outing retry owns exactly one live
stream and never restarts foreground tracking.

Online events are retry hints, not proof of connectivity. Outbox publication from
such a hint requires a visible document, an active tracker generation, and a
remembered participant. The service worker has no session/outbox dependency and no
Background Sync, periodic sync, push, notification, geolocation, or position request.
There is no background geolocation: closing the page leaves no document capable of
publishing.

## Update, clearing, and roadmap boundary

Worker updates remain waiting until explicit activation. The update action refuses
to interrupt active tracking or a participant/outing mutation, and one guarded
controller change reloads once. Update state is not persisted.

Authenticated position publication or sequence recovery returning definitive
`outing_not_found` stops that tracker generation and removes the remembered session
and outbox. Durable identity cleanup still runs if concurrent Stop invalidates the
publishing generation; only stale in-memory UI mutation is suppressed. Forget always
removes local authority; when Stop or its clear request is
uncertain, the UI preserves the warning that the last public position may remain
until server expiry.

**Clear saved offline data** removes explicit public snapshots, remembered
participant sessions, and outbox records. It need not unregister the service worker
or delete its non-sensitive application shell cache.

PR27 may explore a native Android/background execution boundary. PR26 deliberately
adds no native wrapper, service-worker publication, background location,
notification, wake lock, or durable coordinate history.
