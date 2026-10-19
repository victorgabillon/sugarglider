# PR98: offline-capability execution and acceptance

Review date: 19 October 2026. Base: main
`45a31c8789e00476652c90f75a2e323f4e69ee51`. PR97 remains an open,
unmerged draft at `d891d263888efc664409b56d12e70bacd8255dd7`.
Its code is neither merged nor cherry-picked here. Historical acceptance reports,
strict UID assertions and the published privacy page are unchanged.

## Independent decisions

| Assessment | Decision | Scope / remaining condition |
| --- | --- | --- |
| A — offline functionality | **GO within tested scope** | Fairphone 6; the two verified private IGN regions; normal app with region server unavailable and a separate research APK without Internet permission. Physical device disconnection was not tested. |
| B — first-party network controls | **GO within reviewed scope** | Local routing/elevation/GPX, explicit downloads and optional search, no routing-server fallback or automatic route/location publication; fixed local-only package policy preserved. Unknown platform flows are not waived. |
| C — platform network disclosure | **REVIEW REQUIRED** | Both substantive normal-app windows failed the unchanged strict UID diagnostic. Denial-window silence does not settle encrypted payloads or the normal provider's behavior. |
| Technical code integration | **GO for review** | Required functional/regression checks passed; strict UID failures are retained. Only resources change in the normal Android runtime. This remains a draft and no merge is performed or authorized here. |
| Public distribution | **NO-GO** | No IGN publication authorization; public V1-only catalog is incompatible; policy/Data Safety are unapproved drafts; version/signing/Play rollout needs publisher approval; lower-RAM and physical 16 KiB acceptance remain open. |

The complete coordinated release steps are in the
[product/release contract](pr98-offline-capable-product.md). Passing A does not
turn C into passing or authorize public distribution. The remaining operator
decisions include provider/payload/retention disclosure, final publisher/contact,
IGN and derived-data obligations, approved hosts/catalog, final policy/form
answers, device evidence and the future Play artifact/version/rollout.

## Changes under review

The approved [offline product contract](pr98-offline-capable-product.md) is now
in the README, repository instructions and actual native Privacy dialog. The
old dialog omitted both the explicitly submitted IGN address-search request and
measured WebView/platform traffic; it now explains those flows and their limits.
The published-policy button identifies the existing page as an earlier release.
The separate [policy draft](pr98-privacy-policy-draft.md) and
[Data Safety review](pr98-data-safety-review.md) require publisher approval.
No deployment template, public catalog, permissions, signing or version changes.

A typed, bounded metadata receipt validator produces separate offline,
first-party and strict UID results. Unit tests prove that nonzero UID bytes fail
the zero-byte diagnostic without automatically failing offline functionality;
a connected/available-server control cannot establish offline acceptance. The
validator checks consistency of supplied evidence, not whether tests were run.
Browser tests exercise real local planner/coordinator modules with synthetic
fixtures, denied JS networking and native stubs; physical execution below supplies
the native/data evidence. No old test is weakened.

## Host and packaged regression results

| Check | Measured result |
| --- | --- |
| Python 3.13.5, pinned uv environment; `make check` | Ruff format/lint passed; strict mypy passed on 294 source files; **1,480 passed, 16 integration tests deselected**, 95.94 s |
| Python warnings | Nine existing rasterio/NumPy warnings; no ignored new failure |
| Browser regression suite | **50 harnesses, 934 cases, zero failures**, including six new PR98 cases |
| Additional browser checks | Existing installer retention/explicit-GC checks, bundled startup/release checks and chart mouse/touch/keyboard/map lifecycle at 360, 390, 420 and 1280 px passed |
| Android normal variants | **240 Debug + 235 Release unit tests**, no failures/errors/skips; Debug/Release lint and assembly, Debug test APK assembly passed, 1 min 29 s |
| Normal Debug APK | SHA-256 `f50ef10397fc7431b8f2f2084c1e9f919fa2731df62c981528f55b3e4cddc8c8` |
| Normal unsigned Release APK | SHA-256 `c5be70ba4fef074e5931729fb1fc334c066922496feeddb1eabc9be718529da0` |
| Packaging | ZIP 16 KiB alignment passed; bundled ELF equals the verified 16 KiB-aligned library; runtime assets equal source; no private CA, DEM, region archives or research classes in Release |
| Release runtime invariance | Compared with PR97's main-based normal Release baseline, only `resources.arsc` differs; DEX, manifest, native library and runtime assets are byte-identical |

The standard suite intentionally excludes external-data/network integration tests;
they are not reported as 16 physical successes. Private real-data checks are
separately described below. No normal Debug/Release APK was installed over an
existing application. Static alignment is not physical 16 KiB runtime acceptance.

## Physical protocol and private inputs

Only the new owned package
`io.github.victorgabillon.sugarglider.v2auditp1` and its `.test` package are used.
Both were absent from the before inventory. Both APK variants retain the existing
Debug certificate SHA-256
`e84155df3a2c7ea48723876b1fe8e0e602cb600f8374d6539b9fea9aa42cfbd7`.
Their native library is unchanged:
`09b6d312b19caa5410561b804213641f5f8a772d1b3db570cc17bac8a55fb878`.
The test APK declares no permissions, so it cannot add Internet permission to the
denial experiment through instrumentation permission union.

| Private diagnostic artifact | SHA-256 / purpose |
| --- | --- |
| Research network-enabled app | `d6abb811b53a5b6ef5fc96b3ba5b5843b52f9eca27f4cdbe844755d385fabbbf`; normal Internet/location permissions, scoped private HTTPS installer |
| Research Internet-permission-denied app | `4f91aaddfe6b566ab29a9407b0c6ad81ff41d0378d48c2f2a9d12fe707acb438`; same owned ID/certificate/version/assets/native library, Internet permission removed only for this experiment |
| Common instrumentation APK | `d0e65467c115ff730eb55835bee021a4eaee130778c3a2192f9226ffca520dc4`; main's existing strict diagnostic, no PR97 infrastructure imported |

The private workflow serves only loopback HTTPS via an owned ADB reverse. It
installs both regions through the normal installer, then stops that owned server
and removes that reverse before offline acceptance. Phone-wide connectivity,
VPN, DNS, certificate settings and Autofill settings are not changed. Research
build edits are restored before packaging verification; no private CA/config or
diagnostic permission removal enters the normal build or Git.

All 19 component-file hashes/sizes were independently reverified against their
immutable manifests before installation:

| Region | Build identity | Routing graph SHA-256 | Files / bytes |
| --- | --- | --- | --- |
| IGN Yvelines | `a92396de46a6fed5fa1a49fc8c939c39bc6371424aa90c9b71f237878294c7fd` | `d47b022dc2036800bfa5eadc902a90d94de2cff8df32e6377ac9c0ff5fe9fb3d` | 11 / 210,223,038 |
| IGN Marly | `0d0563364bd255956c39edd97d27c2cf3cba225ec0775bdebbdde11f4a4cdc2d` | `01a8eab994555d6366fa77918e305bd06a20f69c955c0f657bfd9291674ddcf4` | 8 / 25,722,739 |

Each has five V2 components. Graph bytes genuinely differ. IGN69 and
`publication_allowed=false` are retained; installation is not public publication
authorization. The existing IGN publication rejection remains intact.


## Observed normal-app offline behavior

The region host was unavailable throughout planning: its listener was confirmed
closed and its owned ADB reverse removed. The phone retained a validated active
network. No research WebView blocking override was requested. This is **server
unavailability**, not a disconnected-device test.

Before installing either region, Generate was disabled, the download requirement
was explicit and native route calls remained zero. With installed data, a request
outside selected coverage returned `no_covering_routing_pack`, exactly one native
call, no candidate and no remote retry.

| Public profile, open-route fixture | Routed m | Height samples | D+ m | D− m |
| --- | ---: | ---: | ---: | ---: |
| hike | 2,655 | 55 | 18.7000 | 72.4300 |
| trail_run | 2,659 | 55 | 18.6625 | 72.3925 |
| city_bike | 3,472 | 71 | 27.3175 | 81.0475 |
| gravel_bike | 3,472 | 71 | 27.3175 | 81.0475 |
| mountain_bike | 3,472 | 71 | 27.3175 | 81.0475 |
| road_bike | 3,472 | 71 | 27.3175 | 81.0475 |

The woodland loop measured 7,942 m, 160 samples and D+/D− 135.2625 m each.
The long gravel loop measured 151,697 m, the maximum 2,048 samples and
D+/D− 990.4214595 m each. Its recorded native height/analysis/total times were
186/76/285 ms. These are fixture results, not expected terrain truth or an accuracy
claim about the IGN source.

Actual chart touch, keyboard positioning and “show on map” preserved canonical
GPX and caused no additional height request. Visible elevation Cancel was
nonfatal; Retry completed without rerouting. Auto Tour with Nature preference
produced two genuine candidates. Sixty one-second candidate selections retained
one chart and one map archive and unchanged canonical GPX. Four selections
Yvelines → Marly → Yvelines → Marly used each correct immutable reference without
an elevation cache hit. Equal heights on shared DEM coverage are expected;
the independently verified graph bytes differ.

Local name search returned five “marly” matches from the installed 4,415-feature
Places index. Nature analysis used 62,191 features, had zero route-distance
partition residual, and kept 21.3391% of this Auto Tour visibly unknown. Its zero
woodland share is not replaced with a guess. The local map read 1,421,742 bytes
through 15 bounded reads; one archive and 64 regional layers were present. An
actual Android screenshot and rendered local-label diagnostics verified the
basemap, route and visible attribution on the actual display. DevTools captures omitted the WebGL basemap even after
rendered-label queries succeeded; Android compositor screenshots showed it. Neither
file reads nor a DevTools capture alone was treated as visual proof.

Three five-second background/foreground cycles retained the candidate, ready
analysis and one map archive. Actual Android Save wrote a local Downloads QA GPX:
canonical output = native bridge payload = saved bytes, SHA-256
`85e6ecd1a879de8ffd53a5469cb0ee60cd4d5f2a0588cccd76e2a63b42ef8b6d`.
It contains one track, one segment, no route, no elevation elements and no analysis
extensions. Clear removed the selected candidate/result, chart and map position;
a 60-second post-clear idle window was measured.

The normal campaign spans `normal-2` and its `normal-3` continuation. A first setup
attempt stopped at Android's uppercase button text; a later driver attempted a
full POI query on a Places-only worker. Both original errors/logs are retained.
The driver was corrected to match native labels case-insensitively and use the
supported Places name search. Already passed six-profile/chart/Cancel tests were
not silently rerun to erase the first UID failure. No product routing or worker
code was changed for either driver correction.

## Original strict network diagnostics

| Window | Startup Tx / Rx bytes | Settled Tx / Rx bytes | Original settled zero-byte diagnostic |
| --- | ---: | ---: | --- |
| `normal-2`: six profiles, forest/long routes, chart/Cancel, Auto Tour; stopped at the driver POI error | 0 / 0 | **12,240 / 12,765** | **FAILED** |
| `normal-3`: normal-app continuation, Places/map, 60 selections, regions, lifecycle, Save, cleanup/idle | **4,111 / 3,021** | **7,217 / 12,978** | **FAILED** |

The initial setup-aborted `normal-1` had zero counters; it is not reported as a
completed functional or privacy control. No nonzero value is subtracted,
relabelled as passing, or attributed to a particular payload. PR98's UID counters
do not identify the initiator/recipient or establish whether personal information
is present. PR97's confirmed Autofill endpoint and unexplained minimal-page traffic
remain separate evidence; they are not used to label every byte above as Autofill.
Page resource observations cannot cover all workers/native/platform services.
The [draft disclosure review](pr98-data-safety-review.md) therefore remains required.

Explicit download windows also had positive UID totals: Yvelines 116,390 Tx /
210,746,769 Rx bytes; Marly 33,932 Tx / 25,801,426 Rx bytes. These totals include
transport overhead and any concurrent UID traffic, not just component payloads.
Counter gaps outside those named windows are retained as unattributed: 13,683 /
34,530 bytes before the Marly installer; 52 / 52 before the first setup run; and
72 / 0 before `normal-3`. Reopen/restart/setup happened in those intervals, but
the data does not identify which service caused their bytes. The private ledger
checks monotonic cumulative accounting instead of dropping between-window deltas.

## Research app without Internet permission

The owned research APK update retained its UID and all 30 native-region/OPFS
payload files byte-for-byte. No pre-existing package was updated. The full
`denied-1` workflow passed cold/warm startup, explicit outside-coverage rejection,
all six profiles, open/loop/Auto Tour planning, 2,048-sample native elevation,
chart touch/keyboard/map interaction, Cancel/Retry, local Places/Nature, 60
candidate selections, four region selections, three background cycles, Android
Save, Clear and 60-second idle. GPX output matched the normal campaign's SHA-256.

This run required actual rendered local labels before accepting the map: ten
labels, one archive, 36 bounded reads / 2,975,852 bytes and 64 local layers.
Android compositor screenshots visually confirmed it. Explicit online address
search reported “Online search could not complete. Try again or choose on the
map.” No remote result or planner mutation occurred; local name-search results
had already succeeded independently. The denied IGN fetch is an explicit failed
action, not a successful transmission or hidden planning dependency.

Startup and settled app UID deltas were both **0 Tx / 0 Rx bytes** in this denial
window. The unchanged original strict assertion passed **for this control only**.
The metadata receipt CLI returned `passed_within_scope` for A/B,
`research_app_without_internet_permission` as its scope, `review_required` for
platform disclosure and `not_authorized` for public release. The WebView setting
is recorded as unknown: no separate blocking override was requested or measured.
The test APK has no Internet permission to union into this target process.

Five additional native phases passed: six-profile routes, 2,048-point heights,
analysis, unavailable/void semantics and distinct-region switching. Every phase
recorded zero app UID traffic and an empty regional mapping list after closure.
A subsequent cold `MainActivity` launch, **without instrumentation**, read the
previously installed region and generated the hike route with native IGN analysis
while Internet permission remained absent. This establishes more than an
instrumentation-only smoke test, but is still a research-APK control.

An additional 72 Tx / 0 Rx counter gap before the denial run is retained as
unattributed. The monotonic ledger from the first installer through the end of the
denial workflow totals 187,769 Tx / 236,611,541 Rx bytes, including explicit
installs, setup gaps, startup and settled windows. It is not a packet attribution
or a claim that no subsequent process can ever communicate.

The phone remained connected; no Airplane Mode, VPN, DNS, system certificate,
Autofill or other phone-wide setting was changed. Actual physical device
disconnection was **not tested**. The normal network-enabled APK's server-unavailable
results, research permission denial and hypothetical separate WebView blocking
must not be conflated. Zero bytes under denial do not fix or approve the connected
normal app's platform behavior.

## Aggregate memory observations

PSS is sampled with `dumpsys meminfo --package`, summing the main process and all
associated processes reported together. Rows retain per-process figures; peaks
are maxima of simultaneous totals, not sums of separately timed process maxima.
Polling is approximately two seconds including ADB overhead and can miss shorter
peaks. DevTools, instrumentation, screenshots and workflow ordering are part of
this protocol. Values below are **bytes**, not a universal memory ceiling.

| Window / phase | Valid samples | Median aggregate PSS | Sampled peak aggregate PSS |
| --- | ---: | ---: | ---: |
| Yvelines installation campaign, including reopen/restart | 149 | — | 836,132,864 |
| Empty first-start idle within Yvelines campaign | 25 | 376,375,296 | 377,440,256 |
| Marly installation campaign | 15 | — | 786,008,064 |
| Normal core workflow, stopped at driver error | 57 | — | 986,057,728 |
| Normal continuation, settled empty planner | 8 | 704,626,688 | 725,645,312 |
| Normal continuation, 60 selections | 37 | 765,833,216 | 857,059,328 |
| Normal continuation, region switching | 16 | 804,977,664 | 861,263,872 |
| Normal continuation, post-clear idle | 31 | 481,331,200 | 487,732,224 |
| Full denial workflow | 162 | — | 1,089,226,752 |
| Denial long 2,048-sample route | 2 | 850,437,120 | 878,701,568 |
| Denial 60 selections | 37 | 871,189,504 | 1,089,226,752 |
| Denial region switching | 16 | 799,838,208 | 912,523,264 |
| Denial post-clear idle | 30 | 512,256,000 | 531,508,224 |

At the full denial peak, main PSS was 419,821,568 bytes and associated PSS
669,405,184 bytes. Its final post-idle total was 512,256,000 bytes; the normal
continuation ended idle at 481,319,936 bytes. These workload-specific observations
neither establish a leak nor a universal safe limit, and the different campaigns
are not a controlled causal memory comparison. PR96's worker/streaming changes
are unchanged. PR97's approximately 867 MB installation and 1.30 GB UI observations
remain valid under its own protocol. Additional lower-RAM-device workloads,
storage-headroom measurements and **physical 16 KiB-page-size** acceptance remain
release requirements. This Fairphone uses API 36, Google WebView 155.0.8059.43 and
4,096-byte pages; static alignment does not close the 16 KiB runtime gate.

## Real-data cross-check and retained evidence

Across 28 route captures from both APK controls and the direct launch, 6,254 native
height samples agreed with an independent Python HGT read of the verified IGN
bytes within **0.010001 m** (observed maximum 0.010000000000019327 m). Full native
analysis objects matched the Python algorithm with numeric tolerance **1e-7**.
This validates sampling/component identity and implementation agreement using the
same source DEM; it is not an independent surveyed elevation profile, nor proof
of centimetre DEM accuracy. Missing-height semantics were separately exercised by
the native void phase and automated failure tests.

Raw APKs, input manifests/HGT, synthetic QA route snapshots, GPX, screenshots,
provider/package metadata, UID series, PSS rows and driver failures are retained
privately under `data/offline-regions/pr98-offline-contract/evidence/` and the
existing private PR95 inputs. They are outside Git. No personal route or generated
screenshot/GPX is published with this report. The public report retains only
necessary aggregate measurements and immutable identities. PR97 and PR98 changed
paths are disjoint; this is a compatibility check, not a merge of PR97.

## Preservation and cleanup

The before/after inventory enumerated **22 pre-existing packages and 25 APKs**,
including production's four splits, older Debug/research/staging applications and
their tests. Every APK size/hash and signing certificate is unchanged. All
**5,160 readable private-file entries** have identical paths/hashes, with no
mutable metadata difference in this run. This includes **109 native regional
files and 139 OPFS payload files**. Production's private sandbox was unreadable
(`run-as` exit 1), so its private contents cannot be hash-proved; its APKs/certificate
were verified and no update, clear, uninstall or launch was issued for it.

Exactly two packages were added: the new `v2auditp1` application and its test APK.
After the denial experiment, only this owned application was restored to its
original verified network-enabled APK. Its UID and 30 native/OPFS payload files
remained unchanged. Both installed private regions remain present. The owned
HTTPS listener, ADB reverse and temporary forwards are closed; no forward remains.
The user's original worktree/branch and its pre-existing untracked files are
untouched. Phone connectivity and global settings, signing, normal app IDs,
version configuration and all older installations are preserved.

No PR was merged, public region/policy/catalog deployed, IGN gate bypassed,
production APK replaced or Google Play declaration/upload/release performed.
