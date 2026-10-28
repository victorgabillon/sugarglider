# Île-de-France offline routing: prepared for device acceptance

Issue [#117](https://github.com/victorgabillon/sugarglider/issues/117) has a
continuous Valhalla 3.9.1 graph and verified private five-component products.
The original implementation at `b9810fb` started from `fefd23a` (main after
PR #116). Its source, private datasets, receipts and prepared APK remain
unchanged in `/home/pompote/sugarglider-idf-routing-2026-10-27/`.
The consolidated integration starts from `4991321`, including merged PRs #120
and #121, on a fresh branch in the normal checkout. See
[the consolidated validation record](issue117-consolidated-integration.md).

**This is host acceptance, not completed Fairphone acceptance.** No #117 APK or
Île-de-France routing data has been installed on the phone. The installed SG AI
Test `17caf0f` remains unchanged. Issue #117 remains open pending approval of
the newly consolidated artifacts and actual Android acceptance. No public
catalog, hosting, Play setting or IGN publication approval changed.

## Architecture decision

Use one logical Île-de-France region, one native graph and the existing version
lease. Places fits the existing bounded format; only Nature needs partitioning.
There is no graph stitching, geometric concatenation, online routing or rerouting
when a saved snapshot is opened. The six public profile identities are unchanged.

| Measured item | Separate complete regions (A) | Continuous graph with partitioned Nature (B) |
| --- | --- | --- |
| Actual complete product | Paris: 93,742,663 component bytes | Île-de-France: 630,996,885 component bytes |
| Native graph | Paris: 57,825,280 bytes | Full region: 329,625,600 bytes |
| Nature | Paris: 17,525 features; 2,080,323 compressed bytes | 190,606 features; 4,170,750 positions; 30,467,064 bytes including directory |
| Runtime geographical boundary | One selected graph; an overlap does not connect it to another graph | Nature file boundaries never cut the graph or polygons |
| Existing full-map reuse | A distinct Paris map adds 29,064,119 bytes | Exact existing full-map component is reused: 243,080,905 bytes |
| Native implementation | Multiple graph identities and handoff would require additional design | Existing native graph/elevation reference, unchanged native library |

The earlier four-rectangle clipping study measured 1,607,747 / 1,589,098 /
1,286,323 / 788,367 Nature positions. Their sum is 5,271,535, approximately
26.4% above the unsplit source because of overlaps. These are source-geometry
feasibility counts, **not four rebuilt complete products or measured package
sizes**. This task built the genuine Paris control and the full continuous
product; it did not fabricate sizes, connectivity, or phone timings for four
unbuilt products. A cannot substantiate all-region cross-boundary routing with
the existing one-graph runtime. B avoids that additional routing architecture.

The retained historical full graph was 3.6.3 and was not used as the routing
backend. Both new graphs were built with the pinned 3.9.1 image, networking
`none`, embedded verified IGN elevation, 3,072 MiB / two-CPU container limits
and the existing extraction/build/normalization scripts. Recorded container
memory peaks: Paris 789,704,704 bytes; full region 2,273,468,416 bytes.

## Bounded Nature format

The five-component manifest accepts either the unchanged legacy
`nature/index.json.gz`, or `nature/partitions.json` followed by at most 64
numbered gzip JSON files. Every file has an immutable size/hash descriptor in
the regional manifest. The small directory binds the full OSM SHA-256, source
identity, regional bounds, projection latitude, partition extents and counts.

The actual product has **12 partitions**, at most **481,495 positions** and
**15,593,336 expanded bytes** per partition. Implementation limits are 500,000
positions and 16 MiB expanded bytes per partition, with a 32 KiB directory.
The legacy **2,000,000-position / 128 MiB** limits remain unchanged. The old
132,550,175-byte expanded index is below 128 *binary* MiB; its 4,170,750 positions
are the decisive legacy-reader failure. Decimal MB and binary MiB must not be
conflated.

Whole OSM polygons belong to exactly one partition. No feature is clipped,
simplified, duplicated or transformed by partitioning. A deterministic spatial
bisection groups complete features; directory extents cover their entire
geometry, including features crossing geographical divisions. Two independent
partition builds produced byte-identical directory and compressed files.
The measured host builder took 128.21 seconds and peaked at 3,985,272 KiB RSS;
this build-time heap is not required on Android.

Installation checks every hash, source/bounds identity, feature inventory,
pruning bounds, category count, ring/hole and polygon topology before commit.
A missing, corrupted, oversized or duplicate partition cannot activate an update.
Runtime reads verified OPFS File snapshots and retains one projected partition.
Classes and water/park intervals are merged before precedence and scoring;
per-partition percentages are never averaged. Geometry and authoritative native
route distance remain unchanged. All partitions share the existing 4,000,000
analysis-operation budget and 2,000,000 proposal-guidance budget. At most 20,000
route vertices and 100,000 retained merged intervals are accepted. Exhaustion or
corruption yields visibly unknown analysis without a partial score.

The source is the retained 335,288,680-byte Geofabrik extract, SHA-256
`2ac2b0d9c7ca8374af078a6f564c342a08a2634a110c1f18bae1cbd1cda5d849`.
This is not a new October OSM snapshot. Administrative extract completeness is
not promised outside Île-de-France merely because a rectangular header covers it.
The full map retains archive SHA-256
`eeea1321da3641ebb867473114bcd3706cb0d9f0b6ab2692baaf51058230b7a9`.

## Native routing and geographical acceptance

A Linux native Actor from the pinned Valhalla image supplies every route and
height call with container networking disabled. The actual production browser
worker reads installed OPFS indexes while browser networking is disabled.
These are genuine native graph tests, not Android JNI or physical-device proof.

The campaign covers Bastille, Versailles, Fontainebleau, Meaux, northern and
southern Île-de-France, western/eastern edges and the proposed rectangular
boundaries. All six profiles pass at Bastille; Trail Run, Hike and City Bike
pass the remaining locations and long crossings. Selected examples:

| Native connection | Trail Run | Hike | City Bike |
| --- | ---: | ---: | ---: |
| Paris–Meaux | 42.211 km | 42.161 km | 48.954 km |
| Paris–Fontainebleau | 60.664 km | 60.951 km | 68.402 km |

An independent Shapely membership check on the returned lines proves actual
polygon intersections in **three** Nature partitions for Paris–Versailles and
**five** for each Paris–Meaux and Paris–Fontainebleau line. Crossing the earlier
rectangle divisions alone is not presented as evidence of crossing the new
feature partitions: the three short rectangle-boundary probes each touch only
one new partition. No unrelated native legs are joined; the Actor verifies
identical successive leg endpoints before assembling its returned trip.

The first Paris-only 25 km Trail Run search returns 24.344 / 24.696 / 25.120 km.
The full-region equivalent returns 24.939 / 24.873 / 25.201 km. Genuine loop
searches also pass at Fontainebleau and Meaux.

A separate 25 km historical test grounds eight places by stable local OSM ID:
Bastille ruins, Cluny baths, Conciergerie, Louvre, Palais Royal, Sainte-Chapelle,
Arènes de Lutèce and Place Vendôme. The unchanged bounded adventure search
returns 24.972 / 25.052 / 26.563 km. The first is the retained no-POI control;
the second reaches Bastille ruins; the third reaches five places within their
strict arrival tolerances. Other places have explicit drop reasons, including
search-budget exhaustion. There are no invented historical stories or hosted
place lookups. This is a 25 km objective with a 2.5 km tolerance, not a claim
that the five-place itinerary is exactly 25 km.

Coarse edge probes exposed native snaps up to 150.203 m at Start and 244.483 m
at End. Those raw diagnostic routes are not claimed as exact waypoint acceptance.
The normal canonical planner separately passes 12 boundary/long connections
with truthful Near adjustments and rejects all six deliberately unacceptable
endpoint cases: `endpoint_not_reached` for Exact and `endpoint_review_required`
for excessive Near displacement. No weakened retry is performed.

## Elevation, GPX and existing products

The full elevation component contains six verified Skadi tiles, derived with
the existing IGN RGE ALTI 5 m DTM pipeline. IGN69 normal heights remain IGN69;
the delivered lattice is one arc-second, not a claim of 5 m output resolution.
Original archive pins, prepared-grid hash, conversion receipt, tile hashes,
coverage/void counts and attribution remain in private manifests and receipts.
All manifests retain `publication_allowed=false`.

Across the initial **66 routed lines**, all **15,156** native height samples
agree with independent Python reads of the pinned HGT within 0.010001 m
(observed maximum 0.010000000000005116 m). That checks implementation/component
agreement, not surveyed elevation accuracy. Every line's primary Nature metrics,
including unknown, partition its native distance. GPX contains exactly one track
and segment, no route and no analysis extensions, and its trackpoints match the
already returned geometry. Historical-stop GPX additionally checks ordered,
truthfully reached waypoints and omits every dropped stop.

The existing Marly, Yvelines and Puy-l'Évêque products were mounted read-only for
36 additional native calls. All six profiles succeeded twice per region with
identical geometry and distance on repeated inputs. Full component verification
before and after preserved each original build identity and checksum. No old
regional directory, phone route, account or saved adventure was rewritten.

## Selection, map reuse and memory

Start selects one suitable committed complete region before routing. A covering
preference remains stable; otherwise deterministic area/ID ordering chooses one
region covering Start, End and exact intermediate constraints. Soft stops do
not cause an unexplained whole-plan rejection. A move updates verified readiness
without persisting an inferred preference; pending updates coalesce into a
serialized latest-request check. AI context preparation and its planning lease
use the same coverage rule. No graph retry or partition selection is hidden.
Map-only coverage remains explicitly separate in English and French.

An existing independent map is reused only after verifying both exact component
files against the complete manifest. The shared bounded PMTiles reader and File
snapshot integrity checks remain authoritative. Tests prove no second map
transfer or OPFS copy, and explicit failure on corruption. Removing the complete
region preserves the independent map.

Host-only measurements, with warmed host file caches:

| Measurement | Result |
| --- | ---: |
| Full Places/Nature OPFS install | 3.60–4.26 s |
| New worker open | 284–345 ms |
| Nine alternating Bastille/Fontainebleau/Paris–Meaux Nature analyses, including forced post-analysis GC | 0.94–2.08 s each |
| Worker heap after initial GC | 25,342,904 bytes |
| Worker heap after individual analyses and GC | approximately 43.6–49.4 MB |
| Sampled worker V8 peak, 124 samples requested at 100 ms | 368,769,116 bytes |
| Full native Actor peak RSS in initial routing campaign | 691,916 KiB |

The heap samples can miss shorter peaks and exclude native/browser allocations.
GC was an explicit measurement intervention. These figures establish bounded
retention in this host workload, not an Android PSS ceiling or minimum-device
specification. Fairphone aggregate PSS, cold launch, install headroom, offline
restart, foreground transitions and new-product switching remain pending.
The existing network/UID findings and release gates are unchanged; offline
routing evidence does not establish network silence.

## Artifacts and verification

| Product | Private build ID | Static ZIP bytes | ZIP SHA-256 |
| --- | --- | ---: | --- |
| Paris control | `a39261739b528a6496ccc34c3504c23422f4cba0a36dc7ac036a5e73b5d1fe25` | 93,751,664 | `7994abbb851f20a5ff99b77b6d80153d5c4fa88649034ad4b58216e465b70940` |
| Complete Île-de-France | `38fd6221da25e3e079002da3b147202700f263ba1567858419677d4543ac1a23` | 631,014,133 | `f4d8ee52bc9fb42c9244a207575ad31e5ed0368520c28972a8c9d8852c1dae60` |

Component payload sizes for Île-de-France: map 243,080,905; routing 329,625,879;
Places 1,183,288; Nature 30,467,064; elevation 26,639,749 bytes. Expected additional
phone payload with the exact existing map is **387,915,980 bytes**, plus small
manifests/installation records and the APK update. Installer temporary space and
actual phone capacity must be measured before transfer. Installing the Paris
control is unnecessary for full-region use and would add its distinct map.

Both ZIPs were separately hash-checked, securely unpacked with the existing
private verifier, and reverified component by component. Generated products,
GPX, source/DEM data, browser measurements and build logs are outside Git under
`outputs/` and `evidence/` in the isolated runtime directory.

Rebuild using the existing build entrypoint with `--partition-nature` for a
large region and explicit verified `--pbf` / `--elevation-sources`. Refuse an
existing output directory; never replace old builds. The independently usable
partition command is `python -m sugarglider.offline_regions.nature_partitions`.
The format and pipeline tests use only synthetic local fixtures. The new browser
harness compares 14 full-scan goldens and exercises real OPFS, corruption,
decompression limits, global budgets, failed-update preservation and selection.

Final source checks: `make check` passes Ruff, strict mypy over 306 files and
1,634 tests (16 service integrations deselected); all 63 browser harnesses pass.
Android Debug has 296 passing JVM tests and passing lint. The staging APK audit
is recorded in the accompanying private installation guide. That guide identifies the exact APK, catalog,
regional archive and installation commands. Physical installation and release
acceptance require a separate explicit authorization for those exact artifacts.
