# Île-de-France map coverage — 27 October 2026

A complete Île-de-France **map-only** PMTiles pack is available for private
installation. It does not add native routing coverage. Puy-l'Évêque delivery is
independent; see [the Lot report](puy-leveque-offline-coverage.md).

The intact archive was found in the retained PR42 measurement output and copied
into the new isolated runtime directory. Its existing identity, template and
Protomaps 4.14.1 builder are unchanged; a redundant build was unnecessary.
Current strict Python and actual shared browser readers both accept it.

| Item | Verified value |
| --- | --- |
| Pack ID | `ile-de-france-map-v1` |
| Bounds | `[1.445097, 48.11918, 3.560409, 49.24271]` |
| OSM input | 335,288,680 bytes, SHA-256 `2ac2b0d9c7ca8374af078a6f564c342a08a2634a110c1f18bae1cbd1cda5d849` |
| PMTiles | **243,080,284 bytes**, zooms 0–15, v3/MVT |
| PMTiles SHA-256 | `eeea1321da3641ebb867473114bcd3706cb0d9f0b6ab2692baaf51058230b7a9` |
| Build ID | `protomaps-3ea8293a2813-pbf-2ac2b0d9c7ca8374-pmtiles-eeea1321da3641eb` |
| Historical build | 1,252.505 seconds under 3,072 MiB / 2 CPU container limits |
| New build peak | Not measured: this task reused verified bytes |

The input is the existing Geofabrik extract, not a new October snapshot. Its
administrative footprint covers Île-de-France; the rectangular header does not
establish OSM feature completeness outside that footprint. See the
[provider's source page](https://download.geofabrik.de/europe/france/ile-de-france.html)
and the [historical measurements](pr42-production-region-measurement.md).

A clean, isolated desktop Chrome origin installed the genuine full pack plus
unchanged Marly/Yvelines maps into **real OPFS**, using the existing
`MapPackStore`, PMTiles runtime and shared `OpfsPmtilesSource`. No third-party
request was permitted. MapLibre rendered actual water/road layers, with visible
OpenStreetMap attribution, at Bastille, Versailles, Marly, Fontainebleau and Meaux.
No map rendering errors occurred. No application GUI code changed.

| Current desktop-host measurement | Result |
| --- | ---: |
| Full-map install, warmed host file cache | 742 ms |
| Archive opening, repeat run | 2.2 ms (initial run 3.4 ms) |
| Five pans at zoom 13, initial run | 311–327 ms to idle |
| Direct tile probes | All 15 probes at zooms 8/12/15 return real tiles |
| Full-map random reads including pans | 38 reads / 2,502,294 bytes |
| Shared per-read upper bound | Unchanged 32 MiB |
| JS heap before explicit collection, initial run | 333,298,286 bytes, includes transient installation allocations |
| JS heap after explicit collection with map active, repeat | 6,949,272 bytes; backing storage 4,177,100 bytes |
| Combined OPFS usage, all three packs | 336,225,724 bytes including manifests/storage overhead |

These figures are desktop evidence, not Android timing, PSS, memory ceilings or
minimum-device specifications. This task did not transfer/install anything onto
the Fairphone. Android's existing map path uses the same web OPFS random reader;
actual full-pack Android reads, opening, pan latency and aggregate PSS still
require the separately authorized installation. Whole-archive installation and
validation are distinct from bounded runtime random reads.

Coexistence is deterministic: the smallest covering pack wins. Marly remains
selected at its covered center (and at the tested Versailles coordinate on its
southern bound); Île-de-France supplies Bastille, Fontainebleau and Meaux. A
covering Yvelines area outside Marly similarly outranks Île-de-France by area.
Only one map source is active; regions are never stitched. Existing installed
copies were not modified: the test installed copies into a fresh desktop origin.

The private site contains the map at
`https://localhost:9444/maps/ile-de-france-map-v1/manifest.json`. After the authorized
staging APK/CA update and USB tunnel, install that URL through the existing
**Tools → Offline maps → Pack manifest URL** form. The Regions catalog still
contains complete five-component products only. The staging catalog does not
pretend the full map is a routing product. The full map adds 243,080,284 archive
bytes plus its small manifest/OPFS metadata. Attribution remains visible.

Full native routing is still blocked by the unchanged Nature reader:
**4,170,750 positions** versus the **2,000,000** limit, in a 132,550,175-byte
expanded index (190,606 features). The historic actual reader rejects it with
`regional_index_too_large`. No limit was raised. An attempted central longitudinal
partition also measured **2,365,194 positions** and was rejected as a proposal.

Clipping the retained full Nature geometries to practical rectangles gives this
bounded proposal. These are **measured feasibility counts**, not newly built,
validated five-component products; a real source rebuild can change them.

| Proposed complete coverage | Bounds W/S/E/N | Measured Nature positions |
| --- | --- | ---: |
| West, wider north/south envelope | `[1.445097, 48.11918, 2.25, 49.24271]` | 1,607,747 |
| Paris / central north | `[2.15, 48.70, 2.75, 49.24271]` | 1,589,098 |
| Central south / Essonne | `[2.15, 48.11918, 2.75, 48.80]` | 1,286,323 |
| Eastern Île-de-France | `[2.65, 48.11918, 3.560409, 49.24271]` | 788,367 |

The union covers the administrative region's selection envelope with deliberate
boundary overlap. The installed Yvelines product remains untouched; the wider
west envelope is a future candidate, not a replacement operation. Every future
complete product must independently pass all format, byte, topology, operation,
Places, elevation, native graph and device limits. Routing still uses one selected
region. Crossing its boundary must fail explicitly; cross-region graph stitching
is a separate engineering milestone.

The smallest next routing task is the **existing Paris spec**
`[2.25, 48.80, 2.42, 48.92]`, with approximately **268,943 Nature positions** under
the same clipping measurement. Build its five genuine components and required
verified elevation halo, resolve **Place de la Bastille** from its local index,
and run the unchanged selected-profile 25 km planner with grounded historical
places, actual native geometry, measured distance and clean GPX. Confirm that
any desired historical stop lies inside this small rectangle; extend to the
measured central-north product if needed. The full Île-de-France map alone does
not pass that routing acceptance.

Private receipts and large files live under
`/home/pompote/sugarglider-coverage-2026-10-27/`; none are committed. No public
hosting, production catalog, Play configuration or installed region changed.
