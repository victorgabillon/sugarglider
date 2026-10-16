# PR93: elevation stack integration and endurance review

Base: PR92, `313d0cb934a80291a4103f7ce08b26052c4f6b53`, on
`feature/interactive-elevation-pr92`. Review date: 16 October 2026.
Main reviewed: `6c0b022f48c110467c920fed6570f91daf6c4c75` (124 changed files
through PR92; most added lines are deterministic synthetic test vectors).

This review adds no elevation functionality or parameter changes. It fixes
confirmed regional-index and map-archive retention paths and strengthens Release CI. Private
terrain, regions, route captures, APKs and device logs remain outside Git.
The final research APK is installed and independently byte-verified. Marly was
installed through the normal private Regions workflow, and the packaged app passed
Yvelines → Marly → Yvelines after restart with WebView network loads blocked.
The physical native two-region endurance test passed. An uninterrupted final
foreground UI workload and background/foreground cleanup measurements remain in
progress; the earlier attempt stopped when another app became foreground.

## Confirmed defects and changes

1. The Places worker could retain a complete previous Nature analysis after a
   region change. `load_places_version` assigned the full analysis object to
   `placesData`. In addition, its name-search function shared a closure context
   with Nature analysis, so merely keeping that function retained Nature too.
   A controlled Chromium experiment with local synthetic data and explicit CDP
   garbage collection demonstrated this: Nature remained reachable while only
   name search was retained, then disappeared after that session was released.
   PR93 gives name search a separate context containing Places data/metadata only,
   and gives the worker a narrow immutable Places session. The same experiment
   now collects Nature while keeping identical working name search. This proves
   a retention fix, not an unbounded leak or a quantified device-memory saving.
   A separate controlled desktop run using the real Yvelines indexes (62,191
   Nature features / 4,415 Places) measured retained JavaScript heap after explicit
   collection: **180,020,560 bytes before / 5,058,964 bytes after**. The old module
   was explicitly served from PR92 and its selection verified. Releasing the
   name session then brought both processes to about 0.88 MB used JS heap. This
   isolates the old shared Nature context; it is not Fairphone PSS or a saving
   while full Nature analysis is still actively needed.
2. The shared PMTiles protocol retained every archive/version registered with
   `add()`. A regression using the actual pinned registry reproduced two retained
   archives after a single replacement. PR93 clears retired archives when replacing,
   detaching or losing coverage, and owns a map-removal listener. Only the active
   local archive may serve requests; retired/unknown keys fail before upstream
   can construct an implicit network FetchSource. Twenty-five synthetic version
   replacements now retain one registry entry, with zero after detach. Active
   header/tile reads and all existing overlays remain supported. This bounds
   retained archive/directory caches; it does not claim a measured GPU-memory saving.
3. Android CI previously linted Release without assembling its APK or checking its
   native alignment. CI now builds unsigned Release and checks both Debug and
   Release APK ZIP/ELF 16 KiB alignment. No upload signing credentials are required.

The focused controlled-GC and elevation input/map lifecycle regressions also run
in their own CI workflow with pinned Playwright 1.58.2, matching the locally tested
tooling. Synthetic screenshots remain in runner temporary storage.

Shell cache generation advances to v93; exact asset pins remain enforced.
The opt-in Android-test endurance phase requires two installed references with
*different graph hashes*, checks native mappings and active-file removal safety,
and records heap/PSS/closure. It does not install or delete regional files and
is absent from Release.

## Integration boundaries reviewed

| Boundary | Evidence and retained behavior |
| --- | --- |
| Native actor and leases | One synchronized engine and one current actor. Replacement closes JNI before creating another actor; the actor retains its repository lease until closure. Request leases cover the whole native callback. Failed opens/initialization and idempotent closure have focused tests. Physical mappings and switching are checked separately below. |
| Immutable V2 install | Exactly five mandatory components, canonical build identity, streamed size/SHA-256 checks, bounded HGT decoding/coverage, full native tile headers, completion reference and atomic browser activation. Failed/cancelled staging cannot replace the old committed pointer. Existing unit/browser corruption and cancellation tests are retained. |
| Bridge | Exact configured appassets origin, current WebView, main frame, nonce/request ledger and operation ownership. No JavaScript interface, wildcard origin, new permission or authenticated redirect transport. Page invalidation cancels optional work and drops stale replies. |
| Elevation | Native nullable heights, distance-bound samples and unchanged PR89/PR91 algorithm/parameters. Missing data stays null; segments split at missing/unsupported spans; partial full-route totals stay unavailable. Synthetic complete/partial/void/reversal/numeric invariants remain distinct from DEM accuracy validation. |
| Presentation | Current candidate/generation/profile/geometry/region/component binding; bounded existing cache. One SVG/control and one style-independent marker, no hover rerouting/panning. Worker, observer, listeners, pending frame and marker cleanup are exercised. |
| GPX and planning | PR93 changes no route generation, ranking, canonical geometry, elevation analysis or GPX implementation. Export remains the returned canonical candidate, one track/segment, no elevation/extensions. |
| Packaging | Normal Debug and unsigned Release compile the same native runtime and shared web shell without requiring the research build flag. Research classes remain in Debug/androidTest source sets. APK inspection independently verifies assets, permissions, IDs, lack of private data and alignment. |

## Regression verification

- `uv run --offline make check`: Ruff, strict mypy, **1,380 passed / 16 deselected**;
  final run 192.34 s. Deselected service integration tests require external services.
- **47 browser harnesses / 912 scenarios passed**, including the new Places-session
  contract, existing bridge/security/GPX/planning/offline tests and real module-worker
  MapLibre security tests. The runner waits for terminal passed/failed status.
- `tests/browser/pr93_retention_acceptance.cjs`: controlled-GC regression passed;
  Nature released and name-search output unchanged.
- `tests/browser/pr92_elevation_acceptance.cjs`: actual mouse/keyboard/touch,
  scrolling and real MapLibre style/resize/remove passed at 360/390/420/1280 px.
- Existing bundled-origin Android itinerary handoff acceptance: **50 checks over
  five viewports**, zero external requests and no page errors. This is browser
  envelope simulation, not a physical Android Intent/IME claim.
- Android **238 Debug + 233 Release** tests, both lint variants, normal Debug and
  unsigned Release assembly, research main/test assembly and research lint passed.
  Normal Debug/Release were also rebuilt and tested without the research property.
  The final test-only native endurance instrumentation compiled successfully.

The standalone retention runner uses an existing Playwright/Chromium installation:

```sh
PLAYWRIGHT_MODULE=/path/to/playwright \
CHROMIUM_EXECUTABLE=/path/to/chromium \
node tests/browser/pr93_retention_acceptance.cjs
```

## Initial Fairphone whole-app baseline (PR92 APK)

The initial normal foreground Generate workload completed **144 paced candidate
selections and 12 regenerations over 554.606 s**. Seed changes repeated three
valid searches; each step waited for its current owned analysis. Exactly one
SVG/control remained, inspection markers cleared, canonical generation data
remained unchanged, and DOM counts alternated only with two/three candidate
cards (1,366 / 1,374 nodes). This is sustained single-region testing, not the
still-pending distinct-region acceptance.

The host sampled `dumpsys meminfo --package` for the research package and every
associated WebView process, approximately every 1.5 seconds plus collection time.
Aggregate values sum processes from the same observation. Main and renderer peaks
at different times are never added to invent a simultaneous peak. The associated
process view does not exclusively attribute shared Android system services.

| Initial phase | Median aggregate PSS | Observed peak aggregate PSS |
| --- | ---: | ---: |
| Startup/idle after installed Yvelines readiness | 577,759,232 bytes | 577,763,328 bytes |
| Map opened | 584,622,080 bytes | 588,212,224 bytes |
| Paced selection/regeneration workload | 666,500,608 bytes | 774,805,504 bytes |

The 30-second beginning/end workload medians were 729,074,688 / 698,015,744 bytes.
No monotonic growth appeared in this run; that does not prove leak freedom.
The main-page JS estimate stayed 31.2 MB, but excludes worker/native/GPU memory
and cannot establish regional-worker heap size. Owned native mappings after
single-region endurance still contained only the one Yvelines graph plus its
four HGT files. Unused compressed mappings can have zero resident PSS.

This baseline predates both final resource fixes and is not a controlled claim
of whole-app memory improvement over PR92's earlier 865,814,528-byte peak. A long
151.917 km / 2,048-sample route also completed with the exact reference native
totals, but its foreground check detected another app; that attempt is excluded
from foreground interaction/latency acceptance. Post-idle/background intervals
are not silently treated as comparable foreground baselines. The later monitor
records an explicit foreground Boolean.

### Final-APK foreground routing and elevation

The normal packaged page was restarted after installation, removing the temporary
USB catalog adapter. Both installed regions remained available; with two regions,
explicit selection is correctly required. Yvelines → Marly → Yvelines each became
ready with all five components and completed normal Generate. Every switch cleared
the previous analysis; all three results were fresh (`cache_hit=false`) and bound
to their selected build, graph and elevation manifest. The short route is identical
within the overlapping graph coverage and uses the same verified N48E002 source;
this is expected and is not evidence that the complete graphs are identical.

| Physical normal Generate case | Distance | Native samples | D+ / D− | Height / analysis / total |
| --- | ---: | ---: | ---: | ---: |
| Yvelines, first Hike | 9.243 km | 186 | 172.6175 / 172.6175 m | 135 / 13 / 168 ms |
| Marly, Hike | 9.243 km | 186 | 172.6175 / 172.6175 m | 95 / 11 / 129 ms |
| Yvelines, returned Hike | 9.243 km | 186 | 172.6175 / 172.6175 m | 92 / 12 / 123 ms |
| Yvelines, long Gravel loop | 151.917 km | 2,048 | 1,280.455150 / 1,280.455150 m | 147 / 77 / 246 ms |

These are actual Valhalla routes and nullable native samples, not injected profiles.
All four complete analyses match unchanged Python on every field (numeric tolerance
1e-7); geometry/source/profile digests match. Independently resampled coordinates
and distances match, and bilinear HGT checks differ by at most 0.01 m (allowance
0.010001 m for native rounding). This validates implementation/source consistency,
not physical survey accuracy or the unresolved datum.

The long route uses 74.21446018563752 m sampling to respect the 2,048 cap. Raw
observed D+/D− are 1,639.74 m; unchanged `distance-box-v1`, 50 m radius / 100 m
maximum gap, gives the totals above. Its SVG rendered in 7.3 ms; sampled touch
readout delays were at most 7.6 ms. Actual touch in both regions and on the long
route preserved candidate/generation identity, the same SVG path, byte-identical
GPX (one track/segment, no extensions/elevation) and zero native requests while
inspecting. Keyboard sample navigation and vertical touch scrolling also passed.

The offline planner interval recorded **0 transmitted / 0 received research-UID
bytes**, including startup, with WebView network loads explicitly blocked. Private
USB installation happened in an earlier, separate session. A notification-shade
interval is excluded from foreground memory statistics. The paced UI workload
paused when Chrome became foreground and is not counted as completed endurance.
A fresh uninterrupted run and explicit background/foreground/cleanup baselines
remain pending.

## Native resource attribution (physical, no WebView)

The fixed research APK separately passed all six profiles × open/loop (12 native
routes), real-height repeat/budget/wrong-identity checks and all 17 portable
analysis fixtures. Each phase used only already-installed Yvelines files and
recorded zero research-UID transmit/receive bytes. These are physical native
checks, distinct from the normal foreground Generate/UI workload.

In that native-only height phase, loading all four real HGT tiles reached
219,520,000 bytes main-process PSS immediately before actor close and
76,430,336 bytes immediately afterward. Native-only routing measured
119,204,864 → 97,666,048 bytes across closure. These are snapshots of separate
process phases, not aggregate app benchmarks or a memory threshold. Cold height
sampling took 156 ms (2,450 ms including pack verification/initialization), warm
20 ms; the 2,048-point native API budget fixture took 145 ms. No elevation values
were injected into real planner results.

The inspected owned configurations use `global_synchronized_cache=false`,
`use_lru_mem_cache=false`, `use_simple_mem_cache=false`, a 1,000,000,000-byte soft
graph-cache setting and no shortcut-cache override. The
[3.9.1 GraphReader implementation](https://github.com/valhalla/valhalla/blob/3.9.1/src/baldr/graphreader.cc)
therefore selects its actor-owned flat tile cache rather than the optional
process-global synchronized cache. A configured maximum is not an eager 1 GB
allocation or a hard whole-app memory bound. This review does not tune it to an
arbitrary new limit.

[Skadi 3.9.1](https://github.com/valhalla/valhalla/blob/3.9.1/src/skadi/sample.cc)
maps compressed tile bytes and allocates 25,934,402 decoded bytes for each used
HGT tile. Its native unpacked cache threshold is 50; Yvelines supplies four tiles
and Marly one. Native actor destruction releases its sampler and graph resources;
allocator/system retention may make immediate PSS differ from live allocation.
Physical mapping checks below test actual closure across distinct regions.
Eight small owned configuration JSONs remained from earlier hard-stopped
processes; these are cache files, not live native mappings or installed regional
data. Normal closure removes its own configuration. They were not deleted.

### Sustained native two-region endurance

The final APK completed **40 operations over 748.483 s**, with a fixed Y/M/M/Y
sequence, 15 s steady intervals, **20 actual region switches / 21 cold actor
starts**, warm repeats, explicit closure, four 30 s idle intervals, a cold Yvelines
reopen and final closure. Every operation routes, samples native heights twice,
checks selected-component coverage and attempts leased removal, which returns
BUSY before mutation. There is no region deletion. Identical graph hashes are
rejected before the test; the installed graphs differ.

Yvelines supplies N48E001 at the public diagnostic point (48.5, 1.5); Marly does
not. All iterations returned available/null respectively, never a cached height
from the other region. Repeated public-point heights agreed within each region.
Only the selected build's graph and compressed DEM mappings existed: five paths
for Yvelines, two for Marly, and **zero after every explicit close**. Threads stayed
at **14** throughout. Reopening reproduced Yvelines heights. Research UID traffic
was **0 / 0 bytes**. A separate Marly native suite also passed all six profiles ×
open/loop, so both real graphs have physical six-profile routing coverage.

| Native-only stage | Main-process PSS | Native allocated heap |
| --- | ---: | ---: |
| Initial closed | 47,859,712 bytes | 7,072,160 bytes |
| Yvelines steady median (20 samples) | 164,230,144 bytes | 217,842,944 bytes |
| Marly steady median (20 samples) | 129,029,120 bytes | 191,903,584 bytes |
| Immediately after close | 80,489,472 bytes | 13,967,088 bytes |
| After 120 s closed idle | 79,594,496 bytes | 13,966,304 bytes |
| Reopened then finally closed | 79,156,224 bytes | 14,133,856 bytes |

The observed native-only PSS peak was 173,630,464 bytes. First/last same-region
steady PSS were 170,408,960 / 164,342,784 bytes (Yvelines) and 135,170,048 /
129,039,360 bytes (Marly). No continuing growth or accumulated native mappings
appeared in this workload; this is not proof of leak freedom for every route or
region. Residual PSS/heap after closure includes loaded code, Java results and
allocator state; it is not evidence that the actor survives.

The first height/coverage calls added 51,957,648 native allocated bytes in Yvelines
and 25,987,552 in Marly, consistent with decoding two versus one 25,934,402-byte
HGT grids plus small allocations. Native allocation counts are not resident PSS.
The whole-app trace separately includes every associated WebView process; none is
present in this headless native test. The Fairphone has 7,579,252 KiB physical RAM,
Android API 36 and 4 KiB pages. 16 KiB support is structurally checked in APK/ELF,
not claimed as exercised on a physical 16 KiB device.

## Distribution evidence and launch gates

The bundled catalog currently names Yvelines build
`902f951bedd1de527629baa572358aec4c388359ce5435d472639dac61f9bc71`.
A read-only request on 16 October confirmed that its actual regional manifest is
schema **1** with only map/routing/places/nature. Catalog schema 1 is the catalog
format, not proof of regional V2 compatibility. The new app deliberately rejects
V1 and preserves old files; releasing it against this catalog would leave new
installations without a compatible regional download. The catalog was not changed.

A coordinated V2 launch must:

1. Resolve rights/attribution and vertical-reference evidence for every terrain
   source and derivative, including DEM-enriched routing archives. Record an
   explicit approved publication policy rather than bypassing current false flags.
2. Build/independently verify every offered V2 region with the pinned 3.9.1 engine,
   all five mandatory components, exact bounds and immutable content identities.
3. Validate a private staging HTTPS distribution end to end, including sizes,
   byte hashes, nonredirecting/range-compatible transport and storage/restart/failure.
4. Coordinate the app's bundled catalog and hosted immutable artifacts. Keep V1
   artifacts/catalog available to the existing app until a separately approved
   migration/retirement policy exists. Never silently reinterpret V1 as V2.
5. Verify the final Release artifact, version/update policy, attribution/privacy
   presentation, supported-device memory behavior and ordinary install/export
   behavior. The present version remains 8 / 1.2.0; it is a review build, not an
   incremented or signed Play release.
6. Publish only after explicit authorization. No PR merge, signing change, public
   artifact, catalog update, social enablement or Play deployment occurred here.

### Four DEM tiles: evidence versus unresolved questions

The exact private source pins and hashes are in [PR90](pr90-v2-offline-regions.md).
PR93 rechecked object headers for N48E001/N48E002/N49E001/N49E002. Their lengths
and April 2016 Last-Modified dates still match the acquisitions; the HEAD responses
provide no per-tile imagery-source metadata. Hashes prove the acquired bytes,
not which upstream pixels, licenses or datum conversions produced them.

The [AWS registry](https://registry.opendata.aws/terrain-tiles/) identifies the
bucket and links to provider attribution, rather than granting a single blanket
license. Provider [source documentation](https://github.com/tilezen/joerd/blob/master/docs/data-sources.md)
describes mosaics of several datasets and a footprints database. PR93 privately
retrieved that public metadata (8,706,136 compressed bytes, SHA-256
`1882c61652283929aad1564734d1eb01575116f5936e9836ccd140c6d852d8b1`).
Geographic overlap finds SRTM, EU-DEM, GMTED and ETOPO1 candidate source footprints
around these tiles. Overlap, especially boundary-touching footprints, is not
proof of actual contribution, priority or the historical 2016 build recipe.

Provider [Skadi format documentation](https://github.com/tilezen/joerd/blob/master/docs/formats.md#skadi)
states WGS84 horizontal coordinates and metre heights referenced to WGS84/EGM96.
That is documented provider intent; it is stronger evidence than assuming a datum
from the HGT extension, but does not independently establish the processing of
these exact historical objects. The application/manifest's unresolved datum label
is intentionally retained pending that verification.

Provider [attribution guidance](https://github.com/tilezen/joerd/blob/master/docs/attribution.md)
requires source-specific investigation and identifies credits for EU-DEM,
SRTM/GMTED and ETOPO1. Before redistribution, establish the historical contributing
sources and their applicable terms, transformations/datum handling, derivative
routing-graph obligations and final in-app/download notices. Public access to
S3 and a software license for Joerd are not terrain redistribution approval.
No rights approval is inferred by this review.


## Distinct Marly artifact — built, installed and verified

The normal V2 builder used the same explicitly pinned local Île-de-France PBF
and verified private DEM pins. A fresh Python verification process repeated the
full validation; an additional streaming pass independently checked every file
size/SHA-256. No existing Yvelines artifact was modified.

| Property | Marly | Existing Yvelines |
| --- | --- | --- |
| Native graph bytes | 12,339,200 | 99,481,600 |
| Native graph tiles | 5 | 22 |
| Required DEM tiles | N48E002 | N48E001/N48E002/N49E001/N49E002 |
| Complete artifact bytes | 30,857,941 | 216,176,479 |

Marly build: `36e42e17b5c1752c0df98970fa23573fbb0ac091b0aae3bb9eccab360be51d8e`.
Graph SHA-256: `a53667f9246f92d6a9b8be4f6a60afe0ded32bf101aca8c3851e7db65f3fea32`.
Elevation manifest SHA-256:
`9974f492dd8cd6e3bc0a116840946b62eda901429706e83f71f79b72cdb0fb10`.
These are genuinely different graph bytes, bounds and immutable identities, not
two paths to one graph. The single HGT tile is correctly shared source data with
Yvelines; its region-specific manifest/component identity differs. All five
mandatory components are present. The artifact remains private and unpublished.

The normal private Debug workflow installed Marly without reinstalling/removing
Yvelines. Loopback-only hosting and USB forwarding supplied the existing temporary
Debug source adapter; manifest/component/hash verification, workers, native
installation and atomic activation remained the production implementation. This
is private Debug transport acceptance, not public HTTPS distribution acceptance.
The adapter was removed by restarting the packaged page before offline testing.
Both regions survived restart and became ready; physical normal Generate and
native mappings confirmed Yvelines → Marly → Yvelines. Native graph mappings never
coexisted across region identities. The sustained headless test above additionally
checked selected DEM coverage, closure/recreation and active leases.

## Current acceptance decisions

- **Code integration: NO-GO pending required physical acceptance.** The confirmed
  resource fixes, full automated regression and packaging checks pass, but the
  final uninterrupted foreground/endurance and background/cleanup review must finish before changing this decision.
- **Public distribution: NO-GO.** Incompatible public V1 regional offerings and
  unresolved historical DEM provenance/rights remain independent blockers even
  if code acceptance subsequently passes. Device/RAM/API coverage and a coordinated
  approved V2 catalog/artifact/app launch remain release gates.

Production and older Debug have not been installed over or cleared; all commands
that write APKs target only the verified isolated research IDs/certificate. No
region removal, signing change, connectivity setting, public artifact, Play or
social release was performed. A hash comparison after Marly installation confirmed unchanged production/older
Debug APK paths, hashes, versions and install timestamps; all 83 older Debug
private files and all nine original native regional files were unchanged. Five
Marly native files were added. The comparison also passed after native endurance with the same counts and hashes.


## Final tested artifact

The final isolated main APK including both fixes is SHA-256
`e635d160574ade24e710924118cf6ebf7a7f2fe074d5fcf9af2f915dee97c02a`.
Its actually installed bytes independently match; test APK is
`f27d025e5e04cbd78beaa29e832af91eb7bef8455144dc7f9d37afed3acf25ba`.
Both use the unchanged research certificate
`e84155df3a2c7ea48723876b1fe8e0e602cb600f8374d6539b9fea9aa42cfbd7`.
The package is `io.github.victorgabillon.sugarglider.v2debug` / `.test`, version
8 / `1.2.0-v2-research`. Normal Debug/Release packaging and all 133 shared assets
passed independent inspection. Neither normal package was installed on the phone.

Private evidence includes the raw aggregate trace and an initial-baseline plot/CSV,
full test logs, independent artifact/source reports, before/after controlled-GC
results and immutable APK metadata. No screenshot, route snapshot, generated GPX,
DEM, PBF, graph or region archive is committed. The additional legacy manual
browser acceptance drivers that require a running external GraphHopper service,
private reference plan/baseline servers or live IGN are separate from the 47
self-contained harnesses above and are not claimed as executed here.
