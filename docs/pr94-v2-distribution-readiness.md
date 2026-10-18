# PR94: V2 elevation distribution staging

Base: main `cac2b415e7eb6db7a9129e6ff50068b3414c29eb`.
Source/host review: 16 October 2026. This is a private release-staging change,
not publication approval. See the [rights dossier](pr94-terrain-rights.md).

## Acceptance assessment

The source/host experiments dated 16 October remain historical evidence. The
18 October recovery and Fairphone measurements below use a **new immutable
private build**, not the lost original artifact. Neither the user's permission
to reconstruct/test nor this report is operator publication approval.

| Requested acceptance decision | Decision after physical acceptance |
| --- | --- |
| PR94 technical integration | **GO for merging the code after review:** native routing/elevation and private installation are validated; the unattributed session/startup bytes below remain a public-release gate. This is not a merge instruction or public-release approval; replacement graph identity and broader-device limitations remain explicit. |
| V2 installation engineering | **GO for the tested private five-component workflow:** normal HTTPS install, restart, exact bytes, cancellation, controlled failures and same-transaction recovery pass. Public hosting/catalog deployment remains gated. |
| Copernicus terrain quality for hiking | **NO-GO for a validated ground-terrain accuracy claim.** DSM canopy/building effects and the historical ~40% long-route IGN difference remain. The conversion/native format is suitable for private research. |
| Terrain redistribution approval | **NO-GO:** no actual operator publication approval exists; every real manifest remains `publication_allowed=false`. |
| Public Android release | **NO-GO:** exact-build approval, coordinated public V2 catalog and outstanding PR93 device/release gates remain. Normal Release still bundles unchanged V1 offerings and fails the explicit V2 release preflight. |

## Fairphone acceptance and artifact recovery: 18 October 2026

Starting PR94 head: `a6e71f00fa187e0c6850e987f0647fd1321e9cb6`.
ADB serial `014728cc` is the actual Fairphone 6, Android 16. Before any launch or
update, an independent read-only inventory verified installed APK certificates,
package metadata and readable private-file hashes. Staging had **zero private
files**, so there was no existing partial installation to overwrite. Production's
four splits were verified; production private data is inaccessible to `run-as`,
so it is not claimed to have been read or individually hashed.

Both original `/tmp/sugarglider-pr94-source` and `/tmp/sugarglider-pr94-data` were
missing. Searches found only historical Mapzen artifacts, which were preserved
and rejected as substitutes. The user explicitly authorized private reconstruction
and, after the different graph hash was explained, chose the simplest path of
testing the fresh identity with the difference recorded for a later decision.
No assumption of approval or byte equivalence was made.

The existing branch was recovered into ignored durable
`data/offline-regions/pr94-acceptance/source`; sibling `private` and `evidence`
hold all real data, TLS keys, APKs, raw logs, captures and screenshots outside Git.
All 11 originals (489,501,031 bytes) reproduced the pinned SHA-256 values:
14.71 s, maximum process RSS 49,448 KiB. A host reboot interrupted the first
conversion/build-check attempt; its partial output was retained separately.
The successful converter took 474.52 s / 207,388 KiB, with **all four compressed
HGT files byte-identical to 16 October**, including the hashes listed below.
Another 100 original-COG/manual-geoid controls and 14,404 seam comparisons pass;
maximum integer quantization error is 0.489426 m, not terrain accuracy.

The graph rebuild used the same pinned 3.9.1 image, unchanged PBF and verified
map/Places/Nature bytes. It took 523.32 s / maximum process RSS 2,676,276 KiB.
Its 99,481,600-byte graph has a different SHA-256; consequently the documented
region received a new identity. **The original graph was not reproduced.**

| Artifact | Immutable identity |
| --- | --- |
| Lost 16 October private build | `9799c1034b2e581ee1cf9cba522c4cf873c863280f8608506c15af0b4ba46efe` |
| Lost original graph | `7d85ebdeefbbabc1716a4ffd8a50b7e9bea0083741b26b4d4aee596474e8fd09` |
| Actually installed/tested 18 October build | `8df4d6d9c7cb18b5da524dd5ab38291ef77bff2004471a38cbc346dc74c46f6c` |
| Actually installed graph | `cb8bb5dc00e5981c366496515ecc5ae5354a35806bfc334283a3cb416933186c` |
| New regional manifest | `f5500e85efa7b528e72a898cd8abd51e18e5226e0afcb78c3901a6e2f7cf41bb` |
| New elevation manifest | `52f0720ddf5eee7e2b5c1ecec74ca45eb13f520c33757d82c48fd2b3f4caf322` |

TAR member metadata/order/offsets/sizes match the retained archive layout. The
original graph bytes are absent, so the cause of the difference is unresolved.
The actual [Valhalla 3.9.1 build-ID implementation](https://github.com/valhalla/valhalla/blob/3.9.1/src/mjolnir/util.cc#L405)
derives the tile-set ID from content hashes; it must not be dismissed as a random
nonce or timestamp. No graph-header editing, identity coercion or claim of exact
reconstruction was used. This limitation remains explicit for the user's later
artifact/reproducibility decision.

A fresh local CA/server chain and catalog were generated because the old private
keys were gone. Only staging and its test APK were updated **in place** after
independent ID/version/certificate/permission/asset/catalog/alignment audits.
No package was uninstalled or cleared. The cert is unchanged:
`e84155df3a2c7ea48723876b1fe8e0e602cb600f8374d6539b9fea9aa42cfbd7`.

| Initial installed item, before the startup fix | SHA-256 |
| --- | --- |
| `.v2staging`, code 8, `1.2.0-v2-staging`, 25,618,063 bytes | `74b3bcd740e4c26a67e5e4ac232624852a4ef202e3664b1489a744d9e0dd5a26` |
| `.v2staging.test`, 258,008 bytes | `6ded2bcda55086473aa3c2690555c807772797f66fdadf631b338cceee292c5e` |

Final startup-fixed staging APK: **25,665,884 bytes**, SHA-256
`4c9507cdfdc6f0d903602bfc7086be9bfd728aa7532b58781460aa2cf2278481`. It retains code 8, version `1.2.0-v2-staging`, the
unchanged certificate and native SO; its test APK is byte-identical to the hash
above. Only this audited staging APK was updated in place; all region bytes and
protected applications remain preserved.

### Actual HTTPS installation, restart and immutable-file checks

The server binds only `127.0.0.1:9443`, reached by a task-owned USB reverse tunnel.
No phone connectivity, trust store, USB authorization or system CA was changed.
Strict TLS 1.3 with explicit private CA/hostname verification, exact origin CORS,
identity encoding, no redirect/cookie/credentials and real 127-byte PMTiles ranges
pass. Default system trust correctly rejects the private CA. All 11 component
files (218,670,766 bytes) and the catalog/root manifest were fetched and matched;
actual APK/catalog preflight passes privately and public-mode preflight rejects.

The actual Regions UI discovered the bundled catalog. Cancelling the fresh map
download at 4.6 MB left an explicit incomplete state and **no active build**.
Normal Download resumed it and committed all five components; all five checkmarks
were Ready by the 30.91 s observation after resume. This is an observed upper bound
for download/verification/readiness, not a more precise installer timer.
Installation UID traffic, including cancelled bytes/TLS/startup, was
129,738 bytes TX / 225,518,036 bytes RX. It is intentionally separate from offline
routing traffic. All 11 installed component files were independently SHA-verified:
native graph/elevation via actual private files and map/Places/Nature via bounded
OPFS reads. The committed build and five-component Ready state survive process
restart. No raw regional files were pushed into Android storage.

| Installed component payload | SHA-256 |
| --- | --- |
| Map archive | `a5e2af1ac3785d370c84a5fc0c46e65ba764a2331d4d86b7e2c6b25de52bce3d` |
| Routing graph | `cb8bb5dc00e5981c366496515ecc5ae5354a35806bfc334283a3cb416933186c` |
| Places gzip | `1ace12b6869ae74f97a673ac9fe6f706cb17a6b7f29b35a9b0dbafd095ea4649` |
| Nature gzip | `abb0819a4f4b02d8ee844aa19de71c1760e0b63a1a9f7bd3410513d82dca7b90` |
| Four HGT gzip files | Exact four full hashes in the HGT table below |

### Actual normal Generate, native heights and interactive UI

All **24** normal Generate cases pass: six public profiles × open/loop × two runs.
Every repeat preserves the exact returned geometry, authoritative distance,
profile, candidate identity and elevation analysis. Each result binds the new
region/build and `0.6.4/valhalla-3.9.1`; no online routing fallback was available.
Distances and filtered totals equal the six-profile table below. Each case used
normal request-file import followed by the application's Generate button; neither
candidate geometry nor elevation results were injected.

A fresh long gravel loop contains **152.163 km / 2,048 samples**, with actual
74.33464 m spacing, complete EGM96 coverage, min/max 103.16/196.64 m.
Its raw D+/D− is **1,879.93/1,879.93 m**; unchanged `distance-box-v1` filtering
(radius 50 m, maximum gap 100 m) gives **1,402.06847/1,402.06847 m**.
It is a newly routed geometry, not the historical 151.917 km comparison line.
A normal 9.279 km Hike tour gives raw 248.68/248.68 m and filtered
182.53325/182.53325 m.

Across **26 actual captured profiles / 4,741 height samples**, all Python analysis
fields/fingerprints agree within `1e-7` numerical tolerance. Native-versus-decoded
HGT maximum error is 0.010000 m (native decimal precision); maximum original-COG
plus independently interpolated NGA-grid error is **0.491676 m**. The long route's
maximum is 0.474511 m. These check the same DEM and documented transformation,
not independent ground truth or a new hiking-quality endorsement.

Actual Android WebView touch/keyboard inspection moves the map marker to the
matching cumulative-distance coordinate. End inspection reaches the actual final
route coordinate. No additional `route_elevation` request occurs during graph
interaction. Before/after actual worker GPX exports are byte-identical and have
one track/one segment, no route, elevation or extensions. Normal Cancel during a
real native request leaves the route available with explicit cancelled status;
normal Retry restores only the current candidate/source. Raw screenshots and
route/GPX captures remain private.

### Sustained workload, disconnection and completed resumption

At **09:41:20 Europe/Paris** the host kernel recorded a physical USB disconnect.
The interrupted checkpoint remains intact: 99 selections, eight regenerations and
two Home/foreground cycles over 439.461 s. It is not counted as a completed run.
The user reconnected/unlocked the phone; its APKs and protected old data were
independently reverified before testing resumed. No USB/network/trust setting or
APK was changed during resumption.

A **fresh continuous run** completed **144 paced selections, 12 normal
regenerations and three Home/foreground cycles in 646.613 s**. Each checked result
retained its exact candidate/profile/region binding, one SVG/control, one map
archive and cleared inspection marker. Actual long-route generation and touch
were repeated afterward. Normal Clear removed the generation, chart/control and
map marker; test-owned GPX references were released before the 104.029 s idle window.
No forced phone GC was used. The two interrupted/completed traces are retained
separately; their peaks are not added or presented as one continuous run.

PSS is `dumpsys meminfo --package` for the actual staging package and **all
associated WebView processes from the same observation**, matching PR93's
definition. It does not exclusively attribute shared Android system services.
Collection is about 1.5 s plus command time; subsecond peaks can be missed.
First-use startup already opens an empty map. Native replies and chart observation
provide separate timings, not an invented isolated height/chart PSS peak.

| Physical phase | Median aggregate PSS, bytes | Observed peak, bytes | Main + associated WebView at that same peak |
| --- | ---: | ---: | --- |
| First startup/empty map/idle | 327,265,792 | 349,797,376 | 189,506,560 + 160,290,816 |
| Install/verification/readiness window | 599,928,832 | **1,096,246,272** | 199,291,904 + 896,954,368 |
| Restarted V2 region + map | 683,239,424 | 694,212,608 | 282,174,464 + 412,038,144 |
| Six-profile Generate/height/chart workload | 720,296,960 | 788,017,152 | 271,389,696 + 516,627,456 |
| Long route/chart/interaction window | 791,434,240 | 856,914,944 | 395,165,696 + 461,749,248 |
| Interrupted sustained workload | See 30 s windows below | 828,903,424 | 383,217,664 + 445,685,760 |

Interrupted-run first/last 30 s median aggregate PSS: **769,648,640 / 796,721,152 bytes**.
Two short background-window medians: 765,076,480 / 735,950,848 bytes. The interrupted trace cannot establish long-term
stability or exclude retention. The separate completed run and idle follow below. The installer peak is
larger than PR93's 989,039,616-byte route/region-return peak and must remain
visible. These are different workloads/artifacts/renderer states, not evidence
of a regression or a saving. No arbitrary memory ceiling or leak claim is made.
Observed staging private-storage peak during installation was **224,171,008
allocated bytes** (`du` across files/WebView/cache/no_backup, excludes APKs);
later route captures/cache reached 224,302,080. This is a sampled allocation peak,
not a sum of logical component sizes or proof that no short staging overlap exists.

Completed resumption, same simultaneous-process definition:

| Physical phase | Median aggregate PSS, bytes | Observed peak, bytes | Main + associated WebView at that same peak |
| --- | ---: | ---: | --- |
| Resumed first Generate/height/chart | 839,688,192 | 868,841,472 | 241,566,720 + 627,274,752 |
| Fresh continuous endurance | 768,146,432 | 868,753,408 | 298,126,336 + 570,627,072 |
| Final long route/chart/interaction | 833,047,552 | 930,572,288 | 407,236,608 + 523,335,680 |
| After Clear + idle, last 15 s | 776,938,496 | 776,940,544 | 404,678,656 + 372,261,888 |

Fresh-workload first/last 30 s medians: **816,737,280 /
751,558,656 bytes**. Post-clear idle was **104.029 s**.
These bounded observations and released chart/map state do not prove absence of
all leaks, quantify every worker/JNI/MapLibre allocation, or establish a memory
improvement against an unmatched PR93 workload. One warm actor, graph/DEM caches,
selected-region indexes and renderer pools remain expected after Clear. Current
mappings were checked and belonged only to the real selected Yvelines build,
including after controlled faults; none belonged to fault-region archives.
The initial 1,096,246,272-byte installer peak remains part of the acceptance data.

Controlled fault fixtures intentionally add retained private files for diagnosis;
their storage is not the normal Yvelines installation footprint. The initial
224,171,008-byte sampled installation peak above excludes those later fixtures.

Native reply timings captured before interruption include 37 actual route calls:
18–769 ms, median 35 ms (warm actor, different path/search lengths). Across the 26
captured profiles, native height is 4–177 ms, analysis 3–55 ms. The 2,048-sample
route specifically measures **149 ms native height / 55 ms analysis / 223 ms total**.
Nineteen passive reply-to-SVG MutationObserver intervals are 2.7–12.9 ms. These
include reply handling/validation/render scheduling and are **chart-ready upper
bounds**, not isolated construction CPU time. Test probes forward unmodified
messages and retain bounded metadata only; memory includes the test harness.

During the fresh continuous run the bounded passive timing buffer retained
111 native route observations (min/median/max
**14/32/110 ms**) and
33 reply-to-SVG upper bounds
(**2.90/3.70/8.30 ms**). The buffer is intentionally bounded;
it is not a count of all backend calls. Actual long-route replay timings are
retained in the captured result. Pure chart construction CPU and GPU paint time
are not inferred from MutationObserver intervals.

WebView network loads were blocked throughout the fresh normal Generate,
selection, long-route, GPX and cleanup workload without changing phone
connectivity. The full endurance/export window's strict UID assertion **failed** with
**5,401 TX / 8,211 RX bytes**. Its source is unattributed; it is not silently
excluded or labelled startup/chooser traffic. A separate diagnostic waited 20 s
for startup settling, then covered a complete packaged-page reload, actual tour
and long-route generation, chart/GPX serialization and a background/foreground
cycle: **0 TX / 0 RX**, with its strict instrumentation assertion passing.
That diagnostic's pre-ready startup window recorded **3,612 TX / 3,430 RX**.
The final fixed APK also passed its separate settled zero-TX/RX interval.
These establish offline route/page operation, not an all-session no-network
privacy claim. Attribution of the small observed transfers remains an explicit
public-release gate alongside the earlier PR93 startup-network finding. The fixed
APK pre-ready startup measured 15,861 TX / 20,171 RX; those bytes are also
unattributed. Installation/fault transfer traffic is measured separately: the original install was 129,738 TX /
225,518,036 RX; isolated fault/retry testing added 337,050 TX / 586,528,691 RX.
These are application-UID counters, not a claim that unrelated phone apps or
shared system services used no network.

### Native lifecycle, missing data and failure recovery

The actual 2,048-point long-route sample request passed cold/warm comparison and
20 identical repeats, the 2,048 budget and rejection of 2,049 points, invalid
coordinates, wrong component/build and empty input. All four installed tiles and
an integer seam returned independently checked heights. Two outer-tile positions
returned **null**, never zero. Original-COG/manual-NGA maxima were 0.474511 m for
the long route and 0.435757 m for tile/boundary controls; decoded-HGT maxima remain
0.01 m. Synthetic missing-file/void JNI probes remain null, malformed JSON is
rejected, and **17** on-device synthetic Kotlin analysis fixtures match their
reference fingerprints, including partial/unavailable coverage, long gaps, noisy
slopes, negative heights and irregular reversal. Synthetic coverage checks are
not represented as actual routed DEM voids; the real route captures are complete.

Cold native height: **473 ms**;
verification/actor/height wall time **2838 ms**; warm height
**164 ms**; 20 repeats **50–130 ms**, median **88 ms**.
Close/reopen returned a cold actor and identical heights. Explicit close changed
**five selected-build regional mappings to zero**, still zero after 15 s idle.
Main-process PSS was **219,048,960 bytes before close,
76,295,168 after close and
73,634,816 after idle**. These headless snapshots
are separate from aggregate WebView benchmarks. Native height/analysis/void
instrumentation each independently measured 0 UID TX/RX.

Controlled physical faults use the production browser coordinator/native client
and real TLS in fresh owned OPFS/native namespaces. They never overwrite the
successful real region, and failed stages have no committed active version:

| Controlled condition | Actual rejection |
| --- | --- |
| Expected immutable build differs | `regional_catalog_changed` |
| Simulated zero remaining index-storage estimate | `regional_insufficient_storage` |
| Archive checksum mismatch | `regional_checksum_mismatch` |
| Valid declared checksum but corrupt/short decoded HGT | `regional_elevation_invalid` |
| Cancellation after map bytes arrive | `regional_install_cancelled` |
| HTTPS stream interrupted after the server's first MiB | `map_pack_install_failed` |

The interrupted transaction was retried in **the same staged directory/build**
after normal server transfer was restored and committed only after all five
component verifications. Quota is an explicit estimate simulation on the physical
runtime, not actual phone-disk exhaustion. Fixture copies share graph bytes for
failure injection; they are **not a distinct-region graph-switch experiment**.
The real Yvelines build/pointer remained unchanged throughout. Failed fixture
state is retained privately for diagnosis.

The normal Android Export GPX button delivered byte-identical clean GPX bytes to
the native save bridge. The real Save-document chooser was cancelled; its native
reply was definitively `cancelled`, the research app returned to foreground and
no user document was created. Actual Android chart/map screenshots are private.

### Final preservation and integration limits

Final after-test checks pass against the original independent baseline:
production's four APK splits, old Debug, previous V2 research and its test APK
have unchanged bytes, paths, versions, install/update timestamps and certificates;
**220 Debug and 271 V2 research private files** are byte-identical. The staging
app/test still exactly match the audited APK hashes above. Production private data
is inaccessible to `run-as` and was not individually hashed. The selected new
native/OPFS component files and committed build were verified again. Previously
installed Mapzen Yvelines/Marly, retained host regions, source inputs and actual
private Copernicus bytes are preserved. No package or valuable region was cleared
or uninstalled; only owned test state was added.

**Confirmed startup defect fixed:** valid canonical imports could be rejected as
unknown activities while asynchronous regional verification was pending. The
packaged app now initializes the six immutable public profile identities before
accepting import events and preserves that catalog through configuration loading
and offline fallback. Availability remains false until native verification; no
routing, ranking, filtering or GPX semantics change. Six known profiles, invalid
aliases, draft preservation and missing-region gating are covered in both normal
and offline-config delayed-startup paths (16 real-app browser cases). On-device
delayed catalog delivery confirms early imports without injecting routing or
elevation results; normal native readiness and short/2,048-sample routes pass
after release of the same real request.

The sustained memory figures above were measured with staging APK `74b3bcd7…`,
before this startup-only fix. They are not relabelled as a fresh sustained run of
the final APK. The native library and installed regional bytes are identical;
the final APK received separate startup/route/elevation/touch/GPX/offline checks.
The focused instrumentation's mapping/idle/installation-counter assertions were physically
executed. All real DEM, personal captures, raw GPX, APKs, keys, logs and screenshots
remain outside Git. The original graph-byte mismatch remains unresolved and was
explicitly accepted only as a fresh private testing identity. Android reports
**4,096-byte pages** on this Fairphone: all APK/ELF 16 KiB packaging checks pass,
but this is not a physical 16 KiB-runtime validation or broad device guarantee.
Public V1 catalog/data, signing, Play and social remain unchanged. Broader PR93
release gates, ground-terrain quality and exact-build redistribution authorization
remain separate from the GO recommendation for reviewed code/private installation.

Private evidence integrity pins (not a claim that raw artifacts are committed):

| Evidence | SHA-256 |
| --- | --- |
| recovered-apk-audit.json | `1df3fa40032c6b37270ba51b25fe55200218f4de1481573e0772ceef301daac0` |
| host-https-final.json | `63a5bf836067b82c2597f708a60284c22dadb27c28f675fd4ab99a155cc2adf0` |
| installed-native-verified.json | `cacb7e085166eb76637bf507cb80471269934e77985475c193da6ce1e3f72b21` |
| installed-opfs-verified.json | `1035736a00af3394c5a799a42f636c6cdb9e55749a9033f2e72d39e208a24dc6` |
| profiles-summary.json | `39263743aa92c085a1504f37ddbd24c1d763ef81bf2f07d01d05d5dfc67acf67` |
| phone-comparison.json | `a990341bb719337d9f9cf1f6e5160e24ec1d5407e310bdd31c42f7207338cbd2` |
| long-interaction.json | `6931eb13bbf8e1bb2fc68b649fdb0a4a1aec6c5ee0cc55e59a7daa961ff09e48` |
| cancel-retry.json | `93f38272ca9b23e4b81619859aa79b6b0642d06ac8a3a1fc6454c0e3bfc1756c` |
| endurance-progress.json | `ff60f658c8b464b569013e31b5b13afcb5cc3f1ac03defc4a26e4b96ad9f53e5` |
| memory-summary-partial.json | `bb71d3c3230d49960669e2de67c971358335c01a26fb5e361119f59664fdcc3d` |
| device-before.json | `cb9cf621d5a6846065210ef9aa674915734018c33d72220437fe3a0a91306929` |
| preservation-after.json | `3c8dec531a57bdaad698d730e9c11234d967d6472584d6dcefd6ef670d1e05e4` |
| old-host-regions-verified.json | `1d4d4baf212d5fe44a0a09fc807996f7ba4d92832bfbb722f5a2425cea4e02bf` |


Completed resumption evidence:

| Evidence | SHA-256 |
| --- | --- |
| preservation-resumption.json | `4b72b9c96961cac164f120af55387e54d90ac85819693e8b5754e3059e146ed4` |
| height-result.json | `66940092ca7c76a62757cb0ddee765920d6d90adcdc0fdd7f3adcb654db3f825` |
| analysis-result.json | `5fd2c14ca2364bd5f594ee03f9a5d380d27e32c292ac2a6aa9305d2dbf027295` |
| void-result.json | `792af03eb70f40c47872eaca60693141d32bb542fbd8a90eb7dada7d3daeb5f5` |
| native-comparison.json | `2ba94a25644fa1aa58fee9c3be17a0cc42697f64baefe638ea610b9007271f06` |
| fault-results.json | `4736d7c110870bfe21cbdd81b984eaca516884e998277490796f5f50a48e10ed` |
| fault-verification.json | `83abccbd63fcebab52101e7dd24afa6f5f82aead1e6a2691171c2070e837e711` |
| endurance-resumed-final.json | `600ba0a03a847d5fd9b2914c7856d85f8cb2c31741d3941d6cd18eba456e509d` |
| memory-summary-resumed.json | `63f9958338b634d5f3fad5ddc85f05d64ad13a3f00529ac5dd7f881565697c3e` |
| planner-network-resumed.json | `f359b6891ed25f989381013fa4725a888441ce4aaf535d5f41248f912ca476eb` |
| final-ui-cleanup.json | `c1da7b34e3adc69ed5bd9d0f7a87324c59d432224277be5b3006b3289bad9159` |
| preservation-final.json | `9d952252728396d0d742b692b72386171f1f07742236ea966352242a99c44a9e` |
| offline-probe-network.json | `4e3051069c8a903f8faa81f98761469e8d0872c96afdee583b1001ef7df4647b` |
| recovered-apk-audit-fixed.json | `bc17d87edb18cdcf37f43a08a34ac74bb27b81e4f1fa68938b29d760ab21b815` |
| fixed-phone-startup.json | `b857399dfb18e82953d6c6a04a40c908fc9d1648d56d6477456e25cf72b935da` |
| fixed-phone-network.json | `a90f1681510aef1e00b21513839fce7a33dbf142347b999ac578d57121fb6678` |
| installed-native-fixed-verified.json | `4db02e63844606bf06adfd685766406b733e95ab2091115d02c14afc9eebfc71` |
| installed-opfs-fixed-verified.json | `1035736a00af3394c5a799a42f636c6cdb9e55749a9033f2e72d39e208a24dc6` |
| final-region-ready.json | `444a892657d173590fcfadd3de0cf96800ba76d0dd7e218b2f1bc8b3f788365e` |
| fixed-phone-interaction.json | `953b4b67ce1d6e39d6671cea4d816100c4e64bc860c90c02a442128e030a1381` |
| phone-comparison-resumed.json | `893a528f5f5a7bc2c22477d2e9d23f147c4c9d76f0eaa4e3dce082cca10920e3` |

## Implementation and confirmed integration changes

- Bounded, pinned, redirect-free source downloader and complete product/URL/hash
  verification. Eleven explicit files, at most 90 MB each; no implicit downloads.
- Deterministic COG node-grid to signed big-endian 3,601² Skadi conversion with
  mandatory EGM2008/EGM96 grids, north-to-south rows and no-data `−32768`.
  COGs removed east/south shared nodes: nine source COGs are necessary to produce
  four complete HGT tiles, including the external south/east halo. No clamping,
  extrapolation, zero filling or fabricated terrain. Missing sources fail.
- Fresh graph rebuild against the same derived HGT, with a graph/DEM/PBF/tool
  identity receipt. Reuse of unaffected verified map/Places/Nature bytes is
  explicit; the old elevation-enriched graph is never reused.
- Private documented and independently authorized V2 modes. Datum/status pairs
  are exactly historical `unresolved/unresolved` or documented `documented/EGM96`.
  Python, JavaScript and Android retain strict field, identity and size checks.
- **Confirmed metadata defect fixed:** route elevation replies previously always
  said “unresolved vertical datum.” The native actor now retains the reference
  from its verified, leased component before JNI creation; browser parsing accepts
  only the two known references. Analysis/scoring/geometry/GPX algorithms do not change.
- Exact-build approval request/copy/export/preflight. Neither a boolean edit nor an
  approval file merely found beside data authorizes publication. The operator must
  separately provide a trusted approval-record digest. The record binds canonical
  evidence, the proposed public build, reviewed terms acceptance and derived graph.
  This is an explicit operational trust boundary, not a claim of cryptographic
  signature or legal approval by the software. Synthetic test approvals are never
  actual operator records. Approved retained builds require separate future
  per-build authorization; this implementation rejects them rather than applying
  one approval to several versions.
- Static distribution notices keep DEM-enriched graph rights separate from ODbL
  database obligations; retained private versions do not inherit a newer DEM's
  licence or approval. Required Copernicus notices remain in the prepared artifact.
- Dedicated `.v2staging` Debug package, explicit external CA/catalog inputs and a
  localhost-only trust rule. Default Debug/Release need neither input and receive
  neither the CA nor staging catalog. No device/system certificate settings change.
  Gradle fingerprints certificate/catalog **bytes**, so same-path replacements
  cannot reuse stale generated resources. A real same-path catalog-change task
  experiment re-executed and copied the changed bytes; canonical inputs were restored.
- Normal Regions UI exposes exact-source terrain attribution. The active public
  catalog, versionCode/versionName, signing, production and historical regions are
  unchanged. No data or APK is committed.

## Measured source, transformation and build

The source ledger records product/release, original HTTPS locator, byte size,
SHA-256, acquisition time and observed Last-Modified/ETag/object version.
**489,501,031 bytes** were acquired: nine 2021-release COGs and two NGA grids.
Hashes pin observed HTTPS-authenticated bytes, not provider-signed checksums.
The implemented downloader was also run again against all eleven official
endpoints: **11.56 s**, peak RSS **48,104 KiB**, all pinned hashes reproduced.
The mutable mirror's 2021 release identity is documented; the original COG object
Last-Modified dates are May 2022, not fabricated terrain acquisition dates.

The initial artifact experiments used Python 3.13.5, NumPy 2.4.4, Rasterio 1.4.3 /
GDAL 3.9.3 and pyproj 3.7.2 / PROJ 9.5.1; gzip metadata is fixed to empty
filename/mtime zero. The optional build group retains main's unchanged NumPy
2.5.1 instead of downgrading the normal Python environment. Each conversion
record identifies its actual toolchain.
Full transformation records retain source hashes, pipeline, software versions,
void/range counters and all derived hashes outside Git.

| Measurement | Actual result |
| --- | --- |
| First four-tile conversion | 420.52 s, peak RSS 525,560 KiB |
| Repeat with explicit 32 MiB GDAL cache | 465.89 s, peak RSS 162,576 KiB |
| Full CLI, including generated source pins (NumPy 2.4.4) | 405.08 s, peak RSS 211,344 KiB; same HGT/record hashes |
| Locked NumPy 2.5.1 replay | 426.15 s, peak RSS 179,468 KiB; every compressed HGT byte identical |
| Reproducibility | Same-toolchain records identical; 2.5.1 record differs only in declared NumPy version |
| Independent boundary/source checks | 14,404 shared-seam samples identical; 100 original-COG/manual-geoid checks pass |
| Largest checked integer quantization error | 0.494683 m; theoretical bound 0.5 m, not terrain accuracy |
| Full regional rebuild/verification | 542.26 s, maximum process RSS 2,677,700 KiB, including OSM extraction |
| Valhalla builder container peak | 907,808,768 bytes; configured 3,072 MiB / 2 CPU build resource bound |
| Graph | 22 genuine 3.9.1 GPH tiles, embedded elevation flag independently verified |
| Regional components | 218,670,766 bytes; 218,674,036 including regional manifest |

The **16 October** private documented build was
`9799c1034b2e581ee1cf9cba522c4cf873c863280f8608506c15af0b4ba46efe`.
Graph SHA-256:
`7d85ebdeefbbabc1716a4ffd8a50b7e9bea0083741b26b4d4aee596474e8fd09`.
Its size is unchanged at 99,481,600 bytes, but its bytes differ from the old graph.
The selected PBF is unchanged, SHA-256
`2ac2b0d9c7ca8374af078a6f564c342a08a2634a110c1f18bae1cbd1cda5d849`.

| Component | Bytes |
| --- | ---: |
| Map | 81,570,965 |
| Routing including manifest | 99,481,878 |
| Places | 261,132 |
| Nature | 10,634,994 |
| Elevation including manifest | 26,721,797 |

All four decoded tiles have **zero void/invalid cells**. Their available integer
ranges are respectively 10–307, −1–209, −3–272 and 6–261 m. Real zero/negative
heights remain distinct from the missing-data sentinel.

Independent GNU `sha256sum` and full regional-format verification also passed for
the original inputs, final HGT, new region and both historical regions.

The previous private Yvelines build `850e2b…e23d3c6` (216,176,479 bytes) and Marly
`36e42e…e51d8e` are preserved. The new region adds approximately 2.50 MB / 1.16%,
without changing install/storage budgets. Conversion requires bounded raster/cache
memory and reserves enough free disk for the worst permitted four HGT outputs.
Keep roughly 0.49 GB source bytes, 0.027 GB converted terrain and 0.219 GB region;
site plus uncompressed publication ZIP duplicate the latter. OSM extraction and
optional independent IGN reference add temporary disk; no existing caches were
cleared to make room.

| HGT | Bytes | SHA-256 |
| --- | ---: | --- |
| N48E001 | 5,731,294 | `fac3ef52cbea26ca5736a597923562f79e36c0ef041e4ddde0f5e3d4f655de95` |
| N48E002 | 6,762,026 | `eea1345034e3110af7d2a0b9a706358be987182b3fb4b9e180a97e21e0f7ca7e` |
| N49E001 | 7,510,161 | `1b2b3dfd1a59691f81cf3f7a33043be9dc8c4f147d7f1a13ce9ec37141a18111` |
| N49E002 | 6,716,261 | `3c18a4d200ea418549ca097893338d52d47efd8eddb4b00edb2cf1cb7f457454` |

## Independent terrain comparison

Existing private **routed geometries** are reused unchanged for source comparison.
The PR89 policy remains `distance-box-v1`, radius 50 m, maximum gap 100 m. No
parameters were selected to reproduce a desired historical D+. Sampling is 50 m,
except the 151.917 km route's actual 2,048-sample budget (74.21446 m). All sources
had complete coverage on these five cases; unavailable samples remain null.

IGN reference: official D078 RGE ALTI 5 m edition `2020-07-30`, delivery
`2021-10-00009`, archive 90,690,133 bytes, provider MD5 checked and SHA-256
`cdd5637135c86a0779e4eed7b0398b6de1ec25e78e000b94fddc2ee00915ca38`.
Its Lambert-93 point grids were sampled locally; no private route was sent to an
online elevation service. IGN heights remain labelled **IGN69 normal heights**.
Cross-datum absolute altitude differences are not asserted. Raster comparisons
are not surveyed vertical validation; a datum gradient can also affect differences.
The flat/steep cases are exact contiguous routed subsections selected by independent
IGN elevation range, with original route distance normalized to their edge spans.

Values are metres, `raw D+/D− → filtered D+/D−`, rounded here only for presentation.

| Routed case | Historical Mapzen/Skadi | Copernicus EGM96 | IGN ground model, IGN69 |
| --- | --- | --- | --- |
| Marly woodland open, 2.655 km | 24.3 / 78.8 → 19.6 / 74.1 | 27.9 / 79.7 → 21.2 / 73.0 | 21.9 / 74.3 → 19.9 / 72.3 |
| Marly woodland loop, 6.451 km | 150.6 / 150.6 → 135.8 / 135.8 | 156.1 / 156.1 → 140.6 / 140.6 | 148.5 / 148.5 → 136.8 / 136.8 |
| Yvelines valley/hills loop, 151.917 km | 1,639.6 / 1,639.6 → 1,280.5 / 1,280.5 | 1,859.8 / 1,859.8 → 1,393.0 / 1,393.0 | 1,116.5 / 1,116.5 → 995.1 / 995.1 |
| Flat subsection, 3.414 km | 21.4 / 35.2 → 12.2 / 26.0 | 26.5 / 34.7 → 14.1 / 22.3 | 7.6 / 21.7 → 6.3 / 20.4 |
| Steeper subsection, 3.185 km | 95.8 / 23.0 → 86.4 / 13.6 | 126.7 / 52.9 → 103.7 / 30.0 | 90.5 / 14.6 → 87.1 / 11.2 |

| Copernicus filtered D+ | 25 m samples | 50 m | 100 m |
| --- | ---: | ---: | ---: |
| Woodland open | 21.74 | 21.22 | 21.00 |
| Woodland loop | 143.57 | 140.63 | 138.66 |
| Flat subsection | 14.82 | 14.12 | 12.63 |
| Steeper subsection | 107.58 | 103.74 | 94.94 |

The long loop gives 1,393.05 m at 74.21446 m and 1,311.35 m at 100 m. Denser
sampling would exceed the native budget; it is not silently used in production.
These differences show the combined effects of sampling, filtering and source
surface. The long-route Copernicus/IGN difference is about 40%; it must remain
visible in the source decision. Neither a 1 m grid nor a smooth chart proves metre
accuracy. Canopy, buildings, mixed source ages/infill, horizontal placement,
interpolation, geoid models and integer quantization remain uncertainty sources.
No independently surveyed route/control-point validation was provided or verified.

## Native host validation of the actual rebuilt graph

The pinned Valhalla **3.9.1 native Python actor**, with networking disabled and
read-only new regional files, routed all six numeric profile policies for both
open and loop requests. This checks the native core/graph; it is not an Android
WebView or Valhalla-Mobile packaging test. Sampled points came from the returned
native polylines and native total distances, with continuous leg boundaries.

| Profile | Open distance / D+ / D− | Loop distance / D+ / D− |
| --- | --- | --- |
| Trail run | 2.656 km / 21.19 m / 72.94 m | 6.564 km / 141.01 m / 141.01 m |
| Hike | 2.655 km / 21.22 m / 72.97 m | 6.432 km / 140.92 m / 140.92 m |
| City bike | 3.472 km / 28.78 m / 80.53 m | 7.399 km / 146.43 m / 146.43 m |
| Gravel bike | 3.472 km / 28.78 m / 80.53 m | 7.399 km / 146.43 m / 146.43 m |
| Mountain bike | 3.472 km / 28.78 m / 80.53 m | 7.399 km / 146.43 m / 146.43 m |
| Road bike | 3.472 km / 28.78 m / 80.53 m | 7.399 km / 146.43 m / 146.43 m |

A native map-matching diagnostic inspected **154 graph edges** with genuine
nonzero mean elevations and grades, independently of the tile header flag. Exact
edge-walk matching rejected the rounded polyline; the explicit map-match is an
attribute diagnostic, not an exact-route oracle or a route-generation fallback.
Native spatial probes also passed all four tiles, integer seams and neighboring
positions, with two missing outer-tile positions returning null.

Profile policies can legitimately return the same geometry. The above routes use
the new graph; they differ from the fixed historical geometries in the source
comparison. No route was chosen to preserve a historical ascent screenshot.
Native height sampling also passed the five comparison routes, including a real
2,048-sample route. Maximum decoded-HGT error was 0.010000 m (the native reply's
2-decimal precision); maximum original-COG/manual-geoid error was 0.487220 m,
within the quantization/interpolation bound. These are pipeline checks against
the **same DEM**, not independent terrain-accuracy evidence.

Host route latency: 16.97–33.63 ms warm, 208.33 ms for the first route. Five-route
native height calls took 1.13–200.06 ms; the long 2,048-sample call took 193.89 ms.
Host actor peak RSS was 145,152 KiB; regional file mappings went from five to zero
after actor destruction. Host RSS cannot be compared to phone aggregate PSS or
used to claim a phone memory improvement. Actual 18 October phone main/WebView measurements are reported separately above;
these host figures are not substituted for them.

## Private distribution and phone boundary

A real server binds **only 127.0.0.1:9443**. A dedicated USB reverse tunnel is the
planned phone path; no public host, account, Pages or DNS changes. Local CA and
server keys remain outside Git. The isolated Debug variant trusts that CA only
for `localhost`; other HTTPS uses system roots. Certificate/hostname verification
is enabled. An initially incomplete local test CA was rejected by strict TLS;
the fixture was corrected with CA key usage/constraints and passed strict OpenSSL
validation. No permissive verifier or device-wide trust workaround was used.

Actual HTTPX transport fetched all 11 component files and verified exact sizes,
SHA-256, no redirects/cookies/Content-Encoding, exact bundled-origin CORS and a real
127-byte PMTiles range. Total: **218,670,766 bytes**. This demonstrates host private
HTTPS, not public hosting acceptance or Android installation. The staging catalog
uses outer schema 1 with an exact **V2 regional manifest**, immutable build URL,
bounds and component byte total; its local manifest/component preflight passes.

The 16 October staging package is `io.github.victorgabillon.sugarglider.v2staging`, version code 8,
name `1.2.0-v2-staging`. It was verified against the installed research certificate
`e84155df3a2c7ea48723876b1fe8e0e602cb600f8374d6539b9fea9aa42cfbd7` before installation.
Only this previously absent package and its test APK were installed. Exact app ID,
permissions, certificate, bundled staging catalog/CA and absence of real regional
files were checked. Production, old Debug and `.v2debug` were not installed over,
cleared or uninstalled. Their APK/metadata and readable regional-file baselines
were captured before installation. Those 16 October raw baselines are now missing
with the temporary directory; the fresh 18 October preservation inventory is
recorded above, without claiming a comparison against unavailable files.

The 16 October phone installation was interrupted by disconnection. The actual
18 October reconstruction, replacement identity, in-place staging update, normal
HTTPS installation and new-source physical acceptance are reported above. Neither
historical Mapzen phone evidence nor synthetic fixtures substitute for those tests.

## Regression status and reproduction

The 18 October rerun after the instrumentation changes passes **1,405 / 16
deselected**, Ruff and strict mypy (186.56 s). Browser reruns pass all 48 harnesses /
918 scenarios, focused 22-case V2/release checks, controlled retention and real
four-viewport chart/map input. Android reruns pass **239 Debug + 234 Release**
tests, both lint/build variants and isolated staging/test/lint; all three APKs
pass ZIP/ELF 16 KiB alignment. All 134 shared assets are pinned; only staging
receives the explicit new CA/catalog, and its permission list is byte-identical
to the previously installed staging APK. Final committed-head reruns and CI are
linked from the PR94 delivery update. The final startup fix adds **16 actual-app
browser regression cases** to the existing 22-case focused V2/release suite
(**38 cases**). Its audited staging-only APK update and final physical checks are
recorded above; native library and all installed regional bytes are unchanged.


Historical 16 October `uv run --offline make check`: Ruff, strict mypy, **1,405 passed / 16
external-service tests deselected**, 179.01 s under main's retained NumPy version.
All **25 focused tests** pass, including deterministic synthetic HGT,
signed/no-data/orientation checks, known terms and exact approval, source
corruption, graph/DEM binding, per-file provenance, APK catalog binding and mocked
HTTPS failures. Unit tests use no network, real DEM, Docker or external services.
The real TLS/source/build/native experiments are recorded separately above.

Browser: **48 harnesses pass**, including source-matched attribution, both V2 wire
modes and explicit EGM96 replies. Existing cancellation/identity/storage/GPX suites
remain. Normal Android Debug/Release tests, lint and assembly passed; isolated
staging APK/test assembly and lint passed. Final normal
reruns pass **239 Debug + 234 Release tests**, both lint variants
and assembly (110 s), including the new datum tests. All **134** declared shared
assets match their sources; the staging variant has only its explicit catalog
override. Normal Release contains no private CA, terrain, research classes or
custom trust rule. All three APKs pass ZIP/ELF **16 KiB** alignment; the native
SO hash remains `09b6d312b19caa5410561b804213641f5f8a772d1b3db570cc17bac8a55fb878`.
Static 16 KiB packaging checks are separate from a physical 16 KiB-device claim.
The implementation head `05ea8cdc27e46fea0a8fcb3624620c23571e1551` passed all seven
push/PR CI runs. The delivered PR head is checked again after this report update.

Install optional build dependencies with `uv sync --frozen --group dem`. The normal
application runtime does not import or require the converter's Rasterio/PROJ tools.
Keep data outside Git and use fresh output directories:

```sh
uv run --group dem python -m sugarglider.offline_regions.terrain_pipeline acquire \
  --pins offline-regions/sources/copernicus-2021-yvelines.json --output /private/originals
uv run --group dem python -m sugarglider.offline_regions.terrain_pipeline convert \
  --pins offline-regions/sources/copernicus-2021-yvelines.json \
  --source /private/originals --output /private/skadi
uv run python -m sugarglider.offline_regions.terrain_pipeline rebuild \
  --previous-region /private/pr90-yvelines --pbf /private/ile-de-france-latest.osm.pbf \
  --elevation-pins /private/skadi/elevation-inputs.json --output /private/new-region
uv run --group dem python -m sugarglider.offline_regions.publication_cli request \
  --private-region /private/new-region --output /private/documented-region \
  --source-pins offline-regions/sources/copernicus-2021-yvelines.json \
  --originals /private/originals --transformation /private/skadi/transformation.json \
  --graph-build-record /private/new-region-graph-build.json \
  --evidence /private/unsigned-publication-request.json
```

The last command cannot create an operator approval or set publication true. Only
`approved-copy`, supplied a separately authorized record and trusted digest, can
create a new approved copy; it rechecks originals, transformation, graph and all
identities. This command was exercised only with synthetic test approvals, never
with actual research data. Do not infer authorization from this documentation.

Prepare the private catalog using `prepare_distribution` with the documented
region, `base_url="https://localhost:9443/"`, an explicit description and the
unsigned evidence path. This creates a fresh site/archive without deployment.
Create local certificates with `scripts/create_private_v2_test_ca.sh` into a fresh
external directory; serve with `scripts/serve_private_v2_https.py --root …
--certificate … --key …`. Both certificate and catalog Gradle properties are
required only for `assembleV2Staging`:

```sh
cd android
./gradlew -PsugargliderV2Staging \
  -PsugargliderV2StagingCA=/private/tls/ca.pem \
  -PsugargliderV2StagingCatalog=/private/site/catalog.json \
  assembleV2Staging assembleV2StagingAndroidTest
```

The explicit release gate is `python -m sugarglider.offline_regions.release_catalog
--apk ACTUAL_RELEASE_APK --catalog CATALOG --site SITE --base-url HTTPS_BASE
--evidence EVIDENCE --approval OPERATOR_RECORD --trusted-approval-sha256 TRUSTED_DIGEST`.
It checks the **actual APK catalog bytes** and the exact V2 region, then requires
publication authorization. `--private` validates staging only and never approves
release. Ordinary main CI performs tests/builds, not this authorized publication.

## Coordinated launch gates

1. Resolve/accept the documented source-quality and combined-database terms; obtain
   affirmative exact-build operator approval through an independently trusted record.
2. Prepare and verify the approved immutable copy, complete notices and byte-stable
   HTTPS artifacts. Keep the existing public V1 artifacts for the code-8 app.
3. Stage a V2 offering and rebuild the normal app with that coordinated catalog;
   pass the assembled-APK preflight. The outer catalog schema may remain 1.
4. Retain the measured phone acceptance and explicitly decide the replacement
   graph/reproducibility issue. Retain the PR93 startup-network attribution and
   broader device/16 KiB-runtime release limitations until separately verified.
5. Obtain separate deployment and Android release authorization. This PR authorizes
   neither public data publication, Google Play upload, signing/version changes,
   merge nor social activation.
