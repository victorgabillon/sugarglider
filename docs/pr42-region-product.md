# PR42 — region download product integration

This slice follows `1ac0a3c` / draft
[PR #50](https://github.com/victorgabillon/sugarglider/pull/50), whose five CI
checks passed. It remains a draft pending static distribution and required
consumer-region Fairphone acceptance. Earlier phone evidence remains identified
in [runtime bridge evidence](pr42-regional-runtime.md).

## Product behavior

The normal bundled planner receives one committed region context instead of
looking up development indexes by pack ID. Native capability validation runs
on the route worker, allowing a committed graph to remain independent of the
regional download worker. The capability is reused within that planning request;
each actual native route still validates its exact archive reference. The
configured sharing origin does not select the Android local planner. An
unavailable profile remains selected and visibly unavailable rather than being
silently replaced.

A shared coordinator serializes user mutations across pages with a Web Lock.
It captures one bounded, credential-free HTTPS manifest, stages map, native
routing and index components sequentially, then verifies all four before
activation. Failures retain inactive staging for explicit resume/removal.
Updates retain the old committed version until the final pointer switch.
Cancellation holds UI and file ownership until outstanding work drains;
uncertain native/commit outcomes retain staged data and an explicit error.

The screen exposes region selection, download/update, cancellation, verification,
unused-version cleanup and explicit whole-region removal. It gives a component
progress message, download size and installed version. A user can show the
selected region on the map without changing any planner points or routing.
The standard web map-pack UI remains separate; the bundled app uses this screen.

A read adapter exposes only the selected committed region to the existing shared
PMTiles/map runtime. It does not scan legacy packs, select another region by map
center or introduce a native map reader. Changing/removing a region refreshes the
map source, including reinstallation of the same immutable version. The catalog
read is capped at 16 KiB and ten seconds; regional manifests at 32 KiB and thirty
seconds. A foreground install has a thirty-minute cooperative deadline, with
bounded native drain retaining explicit uncertainty where necessary.

Whole-region cleanup first makes the web version unavailable while holding its
commit lock, then removes that region's native data and OPFS directory. Recovery
also works with damaged version metadata or an absent OPFS record. The native
bridge accepts only strict region/version identities for these scoped removals;
it does not fabricate a routing reference. Native read leases prevent removal
of in-use graphs. A bounded filesystem preflight rejects oversized/deep trees
before deletion, does not follow interior symlinks, and preserves other regions.
No legacy routing pack or saved snapshot is removed.

## Catalog and outstanding distribution gate

The bundled catalog records the measured Yvelines offering and component byte
total: **188,366,639 bytes**, plus its 2,229-byte top-level manifest. Its download
URL is currently null and the UI says that the download is unavailable. No
static HTTPS/CORS distribution has been published or claimed available.
Provider-neutral publication assets and the external hosting decision remain
required. The catalog is bundled with the app; Check regions rereads that catalog,
without claiming an independently hosted automatic catalog-update service.

## Host verification

These browser fixtures use real Chrome OPFS, shared PMTiles/index formats and
module workers where stated, but synthetic native acknowledgements/route
geometry. They are not physical/native routing acceptance.

- `make check`: 1,033 tests pass, 16 existing integration tests deselected; Ruff
  and strict mypy pass. Existing architecture assertions now require the bundled
  origin and committed-region planner wiring. No skip/xfail was introduced.
- `uv run python /tmp/sugarglider-pr42-product-all-browser.py`: twenty harnesses,
  361 scenarios. The thirteen new product cases exercise actual DOM controls,
  four-component activation, immutable update/resume, checksum failure,
  cancellation drain, selected map access, unused/whole-region removal,
  damaged metadata, orphaned native cleanup and writer/cleanup lock ordering.
  Existing component tests use a real index worker, including corruption after
  a cached parse. Python accepts 51 full canonical results, 30 submitted native
  fixtures and 16 diagnostic snapshots; 60 GPX exports match Python structurally.
- `uv run python /tmp/sugarglider-pr42-normal-ui.py`: the actual shared application
  page runs at the exact bundled origin in an ephemeral host Chrome profile.
  CDP fulfills packaged assets from source files and a tiny declared distribution;
  no TLS exception or application-server fallback is installed. The native adapter
  is explicitly synthetic. Download/activation, reload with distribution
  unavailable, Show region on map and all four normal Generate/export cases pass.
  Map sources equal the returned canonical geometry, traversal arrows retain the
  selected candidate, Python validates every candidate, and GPX equals Python
  output. Export makes no new native route call. Every planning/export case makes
  zero API requests. Forced uncovered routing fails explicitly; no uncaught error.

| Actual page case | Synthetic native calls | Candidates | GPX bytes |
| --- | ---: | ---: | ---: |
| Waypoint Route / hike | 1 | 1 | 562 |
| Waypoint Route / city bike | 1 | 1 | 573 |
| Auto Tour / hike | 7 | 2 | 646 |
| Auto Tour / city bike | 7 | 2 | 657 |

The thirteen-scenario harness uses a synthetic native store and a main-thread
index adapter for focused coordinator/DOM checks. The full application-page
check uses the actual index worker and publisher/export workers. Its synthetic
three/few-point geometry proves UI/canonical plumbing only, never graph validity.
The four page cases are additional checks, not included in the 361-case total.

## Android artifacts and physical gates

The bounded debug/release unit-test and lint run passes **195 tests per variant**,
zero failures/errors/skips. Both variants retain the shared production native
engine. All 101 allowlisted shared assets match source bytes in both packages (shell v40).
Debug lint has two existing warnings; release lint has one, with no errors.
The bounded final build completed successfully; logs are under
`/tmp/sugarglider-pr42-product-android-final.log`.

Fresh real-region download, installed/free storage, phone installation timing,
map, native routing/Auto Tour latency, restart, backend-isolated operation,
interruption/cancellation, removal and reinstall/update remain physical gates.
The Fairphone remains authorized. After package verification, `adb install -r`
successfully upgraded the debug app to this APK without clearing data. The phone
was locked: startup inspection through its WebView confirms the exact bundled
origin, visible/open regional panel, 188.4 MB offering marked Download unavailable,
no installed committed region, disabled Generate with an explicit regional-data
message, no error banner and no service-worker dependency. This is locked-device
startup evidence, not visible physical planning/install acceptance. The temporary
CDP forward was removed. No radio/hotspot state or existing user data was changed.

Final artifacts (outside Git; release bundle is unsigned):

- `/home/pompote/oldata/victor/sugarglider/android/app/build/outputs/apk/debug/app-debug.apk`: **151,696,861 bytes**, SHA-256
  `7c634034b20825a835d361cf8fb3a5be4fc0bfe11755b3866e9d4765c0e0fff2`.
- `/home/pompote/oldata/victor/sugarglider/android/app/build/outputs/bundle/release/app-release.aab`: **47,419,436 bytes**, SHA-256
  `4ab95d6456d20c937228b787d1d4a12e1183ef8aeb35bce52e4e753415c608b5`.

Both contain the unchanged ARM64 native library SHA-256
`e60d66dba922a17c53397e4a00ba4380a9ec87f8f203d3761fefe86bef9b2bbb`.
Artifact/source equality and test/lint totals were checked with
`uv run python /tmp/sugarglider-pr42-product-artifacts.py`.
