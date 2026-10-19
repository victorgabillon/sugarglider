# PR97: WebView Autofill traffic and offline privacy

Base: `45a31c8789e00476652c90f75a2e323f4e69ee51` (merged PR96).
This investigation preserves PR96's installer improvements and all routing,
terrain, elevation, regional identities, catalogs, signing and version settings.
Raw evidence stays in ignored `data/offline-regions/pr97-autofill/evidence/`.

Supported policies tested here do not eliminate the reproducible Autofill traffic.
Residual no-form traffic also remains intermittent and unattributed. No production
privacy fix is established: this PR adds isolated Debug diagnostics and regression
fixtures, while the normal Release APK remains byte-identical to PR96. Strict
whole-app privacy and public release remain **NO-GO**.

## Measurement contract

Physical experiments on 2026-10-18–19 UTC use independently verified audit namespaces,
Android API 36 and Google Android System WebView `155.0.8059.43` on Fairphone 6.
Existing production, Debug, research, staging and PR96 audit packages are
inventoried before testing and are not overwritten, uninstalled or cleared.
No phone-wide network, Autofill, certificate, provider or security setting changes.

Each form control starts with a fresh WebView data directory and app process.
An empty `about:blank` anchor allows metadata-only CDP netlog to start **before**
the test document or real planner is created. The controlled page remains visible
60 s; its Activity and WebView are then destroyed, followed by 15 s observation
with the anchor still alive so browser-process trace collection remains possible.
The anchor closes only after trace export. Native/empty/blank controls separately
reuse PR96's 60 s visible + 15 s destroyed control protocol without CDP.

One-second `TrafficStats` samples identify the actual UID/PID. Form-control results
separate setup, visible-page and post-destruction bytes. Any positive Tx or Rx
fails strict zero-network acceptance; measurement completion is not success.
The existing planner zero-byte assertion is unchanged. Device connectivity stays
available. UID counters are observations of app-attributed bytes in these windows,
not a complete device-wide capture or proof about every platform service UID.
Expected private regional HTTPS downloads are separate windows.

Every meminfo observation sums main and associated WebView process blocks from
one `dumpsys meminfo --package` invocation. Individual reads have small timing
skew, and roughly two-second sampling can miss short peaks. No forced device GC.
Netlog parameters are allowlisted before persistence: origins, event kinds,
counts, host metadata and dependencies; no headers, URL queries, TLS byte fields
or encrypted payloads. Socket metadata omits device-local addresses. A socket
listing permission warning limits what absence can prove.

## Controlled HTML

`tests/browser/pr97_autofill_controls.js` builds fixtures from the actual
`index.html` forms. Its browser regression checks exact source-form markup and
preserves names, types, labels and validation when only autocomplete attributes
change. Detached template contents and hidden-but-attached controls are distinct.
The real forms contain 7 profile controls, 1 location control, 28 route controls,
12 Places filters, 1 map-installer control and 2 controls in each outing form.
These are DOM counts, not a claim that Chromium classifies every control.

Experiments distinguish a single unowned input, one-field form, two-/three-field
causal pair, unowned fields, explicit `autocomplete="off"`, hidden forms,
detached forms, dynamic insertion, actual source-form subsets and full startup.
Control pages have no native bridge or external assets. Real-form subsets retain
relative brand-image markup; those local subresource requests receive the explicit
404 control response. They are form-classification controls rather than a complete
rendering of the application. Their WebView client
serves only the exact local test document and rejects all other document/resource
requests; this does not purport to intercept Chromium's internal services.

The direct-View experiment applies
`IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS` to the **actual WebView before
loading its document**. It is a test condition, not a production fix. PR96's failed
decor-view exclusion is not repeated and presented as a solution.

## Supported APIs and exact-version implementation

Android documents Autofill importance as a framework hint, including explicit
Autofill-request exceptions and changed ViewStructure behavior on Android 14+.
It is not a documented browser-process network firewall.
[View API](https://developer.android.com/reference/android/view/View#setImportantForAutofill(int)),
[AndroidX ViewCompat](https://developer.android.com/reference/androidx/core/view/ViewCompat#setImportantForAutofill(android.view.View,int)).

`WebSettings.setSaveFormData(false)` has no effect on Android 8+ and is not used
as a mitigation. Safe Browsing and TLS verification remain enabled.
[WebSettings API](https://developer.android.com/reference/android/webkit/WebSettings#setSaveFormData(boolean)).

The source tag matching the installed provider is available. In that tag,
`AndroidAutofillManager::ShouldParseForms()` returns true.
`ShouldBeQueried()` checks the query field-count threshold or password fields,
and `ShouldBeParsed()` checks scheme, field eligibility and search-form rules.
The matching `autofill_constants.h` sets `kMinRequiredFieldsForQuery = 1`;
`kMinRequiredFieldsForHeuristics = 3` is a different threshold. The server-query
path runs from `ParseFormsAsync()` after scheme/eligibility filtering.
An `autocomplete="off"` privacy veto is absent from these query rules. This
explains why a document-level hint cannot be assumed to prevent network queries;
physical intervention/removal/restoration tests remain necessary.
[Android manager at 155.0.8059.43](https://github.com/chromium/chromium/blob/155.0.8059.43/components/android_autofill/browser/android_autofill_manager.cc),
[Form qualifiers at 155.0.8059.43](https://github.com/chromium/chromium/blob/155.0.8059.43/components/autofill/core/browser/form_qualifiers.cc),
[query constants](https://github.com/chromium/chromium/blob/155.0.8059.43/components/autofill/core/common/autofill_constants.h),
[query call path](https://github.com/chromium/chromium/blob/155.0.8059.43/components/autofill/core/browser/autofill_manager.cc).

Current upstream main has since refactored these predicates into parsing
permissions; it must not be substituted for the installed tag without qualification.
Source interpretation identifies possible mechanisms, not encrypted request contents.

Android also documents the per-app `android.webkit.WebView.MetricsOptOut`
manifest entry. It controls usage-statistics collection, does not disable crash
reporting, and is not documented as an Autofill prediction switch. A separate
research-only app tests this hypothesis; its normal manifest is restored after building. Neither this
option nor an origin-only netlog can identify the contents of an encrypted request.
[WebView reporting privacy](https://developer.android.com/develop/ui/views/layout/webapps/webview-privacy).

## Completed controlled measurements

All byte values are exact per-UID deltas, with networking available. Each complete
window is 60 s visible plus 15 s after document destruction. No positive result is
reclassified as a pass. `Autofill` below means origin metadata identifies
`https://content-autofill.googleapis.com`, not that encrypted contents are known.
`Local origin only` means the trace did not identify the source of the UID bytes.

Runs a/b/c used the initial research build. Runs d/r/e and final functional tests
use final `.v2auditn1`, UID 10318, APK SHA-256
`ff2a6f20a9ee09436a398643e7128528c7fc139b6788f5b11d7f94ad0ac0c64d`.
Independent `.v2auditn2` (UID 10320) adds only research `MetricsOptOut=true`;
`.v2auditn3` (UID 10322) restores normal policy and starts with a never-used app UID.
The provider is API 36 / Google WebView `155.0.8059.43` throughout.

| Run / control | Tx bytes | Rx bytes | Destination metadata | Strict zero |
| --- | ---: | ---: | --- | --- |
| `a1-native` / native | 0 | 0 | not traced | PASS |
| `a2-webview` / webview | 0 | 0 | not traced | PASS |
| `a3-blank` / blank | 0 | 0 | not traced | PASS |
| `b1-native` / native | 0 | 0 | not traced | PASS |
| `b2-webview` / webview | 0 | 0 | not traced | PASS |
| `b3-blank` / blank | 0 | 0 | not traced | PASS |
| `b4-none` / none | 3584 | 2983 | local origin only | **FAIL** |
| `c1-form-three` / form-three | 7422 | 10903 | Autofill | **FAIL** |
| `c2-form-two` / form-two | 4326 | 7325 | Autofill | **FAIL** |
| `d1-form-three` / form-three | 7434 | 10611 | Autofill | **FAIL** |
| `d2-form-three-off` / form-three-off | 10329 | 16196 | Autofill | **FAIL** |
| `d3-form-three-exclude` / form-three:exclude | 3997 | 7548 | Autofill | **FAIL** |
| `d4-input` / input | 3743 | 7434 | Autofill | **FAIL** |
| `d5-form-one` / form-one | 7801 | 10242 | Autofill | **FAIL** |
| `d6-inputs-three` / inputs-three | 3768 | 7247 | Autofill | **FAIL** |
| `d7-form-three-detached` / form-three-detached | 0 | 0 | local origin only | PASS |
| `d8-form-three-dynamic` / form-three-dynamic | 4034 | 7650 | Autofill | **FAIL** |
| `d9-none-plain` / none@plain | 3935 | 3124 | not traced | **FAIL** |
| `d10-none-methods` / none@methods | 0 | 0 | local origin only | PASS |
| `d11-none-nojs` / none@nojs | 0 | 0 | local origin only | PASS |
| `d12-real-route` / real-route | 4214 | 7773 | Autofill | **FAIL** |
| `d13-real-profile` / real-profile | 8260 | 10311 | Autofill | **FAIL** |
| `d14-real-outings` / real-outings | 3864 | 7565 | not traced | **FAIL** |
| `r1-real-all-hidden` / real-all-hidden | 5329 | 8478 | Autofill | **FAIL** |
| `r2-real-all-detached` / real-all-detached | 0 | 0 | local origin only | PASS |
| `r3-real-all-off` / real-all-off | 4619 | 7843 | Autofill | **FAIL** |
| `r4-real-all` / real-all | 4306 | 7337 | Autofill | **FAIL** |
| `r5-planner` / planner | 9996 | 11502 | Autofill | **FAIL** |
| `m1-none-plain` / none@plain | 813 | 936 | not traced | **FAIL** |
| `m2-form-three` / form-three | 3994 | 7649 | Autofill | **FAIL** |
| `f1-none-plain-methods` / none@plain-methods | 0 | 0 | not traced | PASS |
| `f2-none-warm` / none@warm | 5186 | 6285 | local origin only | **FAIL** |
| `e1-numbers-two` / numbers-two | 12293 | 17501 | Autofill | **FAIL** |
| `e2-real-location` / real-location | 6626 | 13773 | Autofill | **FAIL** |

Across 34 completed control windows, 23 fail strict zero and 11 are silent. These
are different interventions, not a statistical estimate of a failure rate.

The ordinary single text input is sufficient in this experiment: no form wrapper,
native bridge, routing, focus or typing is needed. Two fields also trigger traffic;
the initial three-versus-two comparison is not a three-field threshold.

Neither explicit autocomplete-off nor direct importance 8 on the actual WebView
prevents Autofill requests. Hiding attached real forms also fails. Detached forms
are silent during these windows, but attaching the simple form after three seconds
restores Autofill traffic. Deferral postpones the trigger; it does not solve active
profile, routing, location or outing forms. Production semantic inputs and accessible
form behavior therefore remain unchanged. No supported production fix is established.

The numeric-only two-field control also contacts Autofill (12,293/17,501 bytes),
so removing the text field does not establish a numeric-input privacy solution.
The actual location form independently contacts Autofill (6,626/13,773 bytes)
without application scripts or geocoder calls. The actual route and profile
subsets independently contact Autofill. The outing
subset has positive counters but its trace export timed out; its destination is
not assigned by inference. All-real-forms and full-planner controls contact Autofill.
Full untouched planner r5 sends/receives 9,846/11,232 visible bytes and 150/270
additional bytes after page destruction while the blank anchor remains alive.

## Residual HTML traffic and attribution limits

Minimal documents contain no forms, scripts or external assets. Positive no-CDP
d9 (3,935/3,124) rules out CDP attachment as a necessary cause. Metrics-opt-out m1
also has positive bytes without CDP (813/936); m2 still contacts Autofill. This
setting is not a reliable elimination policy for either finding.

The first HTML document in the independent n3 UID is silent (f1), but a subsequent
fresh-WebView session with a reload after 25 s has 5,186/6,285 bytes (f2). Its trace
contains only the local origin. Initialization/warmth may affect timing, but these
few observations cannot isolate a specific browser service. They demonstrate
intermittence, not a cold-start guarantee or a quantified occurrence rate.

JavaScript-disabled d11 and enabled d10/f1 are all silent; this does not establish
JavaScript disabling as a fix. Two bounded method traces collect descriptors and
timing, without arguments. The silent d10 trace contains Safe Browsing lookup,
Google service connection, Autofill and cryptographic-key parsing methods. Their
presence in a **zero-byte run** cannot attribute another run's network traffic.
Local-socket and key-deserialization frames are not proof of IP egress or a TLS
request. Sample records are not invocation counts. Proprietary Google provider
classes also limit conclusions from the corresponding open-source Chromium tag.

Residual bytes remain unattributed. No claim is made about encrypted payloads,
user-data transfer, DNS, metrics, Safe Browsing or Android framework responsibility.
No security, provider, phone-wide Autofill or network setting was changed.

Incomplete a4/b5/c3 windows are retained and excluded from completed-pass counts.
The c3 foreground guard fired after page destruction; this alone is not evidence
of user activity. A private host guard correction tolerates transient empty focus
and stops checking page visibility after destruction, without changing the 75 s
counter window or zero-byte assertion. d14 has a complete failing counter window
but no completed trace export. An unnecessary heap-usage CDP roundtrip was removed
from subsequent metadata-only exports; no causal claim about the timeout is needed.
Early final-install drivers also failed before installation (input readiness and
an oversized IME diagnostic). They are preserved; the corrected driver waits for
owned foreground and retains only the IME-visible boolean. No failed measurement
has been erased or silently converted to a pass.

## Automated and packaging validation

`make check`: Ruff formatting/lint, strict mypy on 291 source files, and **1,440
passed, 16 deselected** normal non-integration pytest tests (110.77 s). Nine
existing rasterio/NumPy warnings remain. An initial restricted-runner hang was
retained and diagnosed separately; the complete normal run passed outside that
runner without exclusions or assertion changes.

Browser: all **50 harnesses / 935 cases** passed, including all 49 existing
harnesses and seven control-fixture contracts. Existing explicit-GC regional
retention and real elevation/chart interaction checks passed. Real application
inputs passed at widths 360, 390, 420 and 1280: profile persistence across reload,
accessible label lookup, focus, keyboard edits, touch, numeric validation and no
routing/height calls from preference editing. Browser acceptance uses synthetic
QA input and the actual application modules; it does not emulate platform
Autofill traffic. These checks do not constitute a spoken TalkBack assessment.
Two test-driver errors (autocomplete IDL reflection and `.mjs` response MIME)
were corrected; failed attempts remain in private evidence.

Android final normal variants: **240 Debug + 235 Release unit tests**, no failures,
errors or skips; Debug/Release lint and Debug/AndroidTest/Release assembly passed.
The isolated staging variant and its instrumentation also build and lint.
No normal Debug or Release APK was installed on the phone.

Normal Release retains application ID `io.github.victorgabillon.sugarglider`,
version code 8 / version 1.2.0 and its existing three permissions (Internet,
coarse and fine location). Its manifest and DEX contain no research Activity,
network-review instrumentation or method-sampling hooks. It contains no private
CA, HGT, regional PMTiles or routing graph. Bundled JavaScript matches the source.
The normal unsigned Release APK is byte-identical to the retained final PR96
Release artifact: SHA-256
`a9c61e76ab666d08fadc4c2f420743865c3337b84ff1a4ca1fc18edb9c6cf374`.
This is packaging preservation, not evidence of a privacy improvement.
Normal Debug, Release and the isolated research APK pass ZIP 16 KiB alignment;
every native ELF load segment has 16 KiB alignment and congruent offsets.
The Valhalla library remains SHA-256
`09b6d312b19caa5410561b804213641f5f8a772d1b3db570cc17bac8a55fb878`.

All three isolated app/test pairs are verified against the original Debug signing
certificate SHA-256
`e84155df3a2c7ea48723876b1fe8e0e602cb600f8374d6539b9fea9aa42cfbd7`
before installation; IDs, version 8, permissions, manifests, assets and native
identity are checked. No existing package is replaced to create n2/n3.

| Research app suffix | App APK SHA-256 |
| --- | --- |
| `.v2auditn1` | `ff2a6f20a9ee09436a398643e7128528c7fc139b6788f5b11d7f94ad0ac0c64d` |
| `.v2auditn2` | `add52c04eab108f55459a85ecd87a724d9899b36f8e745e49f12ab00fd6d291d` |
| `.v2auditn3` | `2404ef859df4c0a71535204d7931da18e308e774ff64e29143f4f84e271b9b33` |

## Reproducing a form measurement

Build a new private isolated suffix using the existing `sugargliderV2Staging`
workflow. Verify its ID, original Debug certificate, permissions, version,
bundled assets and native library before installing. Never reuse or clear an
existing user package. Generate the control documents using
`buildAutofillControls()` from the actual bundled HTML, as the browser harness does.

For a unique `research_id`, put `control.html`, `control-mode` (`html` or
`planner`), `view-policy` (`auto` or `exclude`) and optional `javascript-policy`
(`on` or `off`) into that isolated package's `cache/<research_id>/`. Invoke
`V2RegionInstrumentation` with `phase=autofill_control` and `fresh_webview=true`.
Wait for `preload-ready`, attach metadata-only tracing to the exact owned PID's
blank anchor if profiling, then create `preload-start`. After `preload-finished`,
export the allowlisted trace and create `preload-collected`. Pull
`control-result.json` and `uid-series.jsonl`. The result reads back the actual
WebView importance and JavaScript settings rather than inferring them from
command arguments. Nonzero counters produce an instrumentation failure even
though measurement artifacts are saved. `java_method_trace=true` optionally
samples method names/timing for 15 s with a 32 MiB buffer; it does not collect
argument values, headers, URLs or encrypted request bodies.

The original full planner strict zero-byte check is retained unchanged.
Native routing/elevation, expected private HTTPS installation and full WebView
privacy must be evaluated in separate windows. Do not subtract an attributed
request or ignore a small positive residual to manufacture a pass.

## Final Fairphone acceptance

The exact final n1 APK completes real profile-name and route-name Android keyboard
entry, numeric distance input, visible IME and accessible input labels. Focus is
assisted by the test driver after touch; this is not a spoken TalkBack evaluation.
Profile persistence also passes the four-viewport browser reload test. No system
accessibility setting is modified. Cold, normal-reopen and process-restart checks
retain both installed regions; region selection is made explicitly after restart.
Two early final-UI setups failed on a PID polling race and absent region selection;
these driver attempts remain recorded, with no successful routing result claimed.

| Real Generate | Routed metres | Samples | D+ / D− metres | Height / analysis ms |
| --- | ---: | ---: | ---: | ---: |
| hike | 2,655 | 55 | 18.70 / 72.43 | 114 / 5 |
| trail_run | 2,659 | 55 | 18.66 / 72.39 | 11 / 4 |
| city_bike | 3,472 | 71 | 27.32 / 81.05 | 13 / 5 |
| gravel_bike | 3,472 | 71 | 27.32 / 81.05 | 14 / 4 |
| mountain_bike | 3,472 | 71 | 27.32 / 81.05 | 10 / 5 |
| road_bike | 3,472 | 71 | 27.32 / 81.05 | 10 / 5 |
| Woodland loop | 7,942 | 160 | 135.26 / 135.26 | 23 / 8 |
| Long loop | 151,697 | 2,048 | 990.42 / 990.42 | 151 / 78 |

All listed profiles have complete coverage. The 151.697 km route exercises the
2,048-sample limit; its raw ascent/descent is 1,118.36/1,118.36 m versus filtered
990.42/990.42 m, with unchanged `distance-box-v1` parameters. These are regression
measurements, not an independent survey or validation of DEM absolute accuracy.

Actual trusted chart touch creates the corresponding map marker; keyboard controls
and map transition work. Interaction makes no additional height request and leaves
GPX bytes unchanged. Visible Cancel is nonfatal; Retry obtains elevation without
another routing request. The Auto Tour returns genuine distinct candidates;
60 selections over approximately one minute retain one elevation chart, one
control and one map archive, clear selection markers, and preserve canonical candidate and GPX bytes.
Four selected-region routes (Yvelines → Marly → Yvelines → Marly) use the matching
immutable region/build identity and no stale analysis-cache hit. Three 5 s
background/5 s foreground cycles retain the candidate, ready elevation and one
archive. Clear removes the candidate, chart and elevation marker, then receives a
90 s idle observation.

Actual native Save opens the Android document picker and saves a unique QA GPX.
The saved file equals the native bridge payload and canonical selected-candidate
export byte for byte (7,806 bytes). Parsing confirms exactly one track,
one segment, no route, elevation elements or extensions. The private GPX is not
committed. No generation or routing is performed to export it.

Independent host comparison covers 3,007 samples in 13 final captures, including
both genuine regional graphs. Every sampled height matches the verified private
HGT probe within 0.010001 m (largest observed difference 0.01000000 m), with null
availability preserved. Full native analysis equals Python analysis to 1e-7 for
numeric fields. Separate native routes, height, analysis, void and switch phases
all pass their strict
**0 Tx / 0 Rx** checks and show no regional graph/elevation mapping paths after
actor closure; active-actor removal is also blocked by the lease check.
Missing-height and source-identity checks remain unchanged.

### UI network results

The original strict planner assertion is retained. Its startup interval records
**0 Tx / 0 Rx**;
its settled full-workflow interval records **12,720 Tx /
13,152 Rx**. Nonzero counters are a privacy failure even
though all functional checks completed. Connectivity remained enabled and WebView
network loads were not blocked.

The page resource observer records 679 entries, without overflow:

- `https://appassets.androidplatform.net fetch`: 5
- `https://appassets.androidplatform.net img`: 13
- `https://appassets.androidplatform.net link`: 2
- `https://appassets.androidplatform.net other`: 101
- `https://appassets.androidplatform.net script`: 558

This observer covers page Resource Timing, not every worker, native operation or
browser-process service. Together with source review and native-only checks, it
supports the scoped application-path decision below; it cannot make whole-app
privacy pass or assign all UID bytes to the previously traced Autofill endpoint.

Per-phase UID deltas use one-second samples at host boundaries; timing has roughly
one-second uncertainty. Coincidence with Generate does not prove Generate caused
traffic. System picker/IME processes have separate UIDs and are not a whole-phone
capture. Expected installer HTTPS downloads are excluded from this UI window.

| Phase | Observed seconds | Tx / Rx bytes |
| --- | ---: | ---: |
| settled-empty-planner | 15.0 | 0 / 0 |
| generate-hike | 8.0 | 4,499 / 7,491 |
| generate-trail_run | 4.0 | 1,508 / 919 |
| generate-city_bike | 4.0 | 0 / 0 |
| generate-gravel_bike | 4.0 | 0 / 0 |
| generate-mountain_bike | 4.0 | 0 / 0 |
| generate-road_bike | 4.0 | 0 / 0 |
| woodland | 4.0 | 1,467 / 1,044 |
| long-2048 | 5.0 | 1,666 / 1,041 |
| touch-keyboard-map | 2.0 | 0 / 0 |
| cancel-retry | 5.0 | 0 / 0 |
| genuine-candidates | 6.0 | 1,241 / 959 |
| 60-selections | 73.0 | 2,339 / 1,698 |
| region-switches | 29.0 | 0 / 0 |
| background-0 | 6.0 | 0 / 0 |
| foreground-0 | 5.0 | 0 / 0 |
| background-1 | 5.0 | 0 / 0 |
| foreground-1 | 5.0 | 0 / 0 |
| background-2 | 6.0 | 0 / 0 |
| foreground-2 | 5.0 | 0 / 0 |
| actual-gpx-save | 8.0 | 0 / 0 |
| clear | 3.0 | 0 / 0 |
| post-clear-idle | 90.0 | 0 / 0 |

### Functional-workflow memory

This separate workflow has 171 valid aggregate observations and
sampled peak **1,302,102,016 bytes**. It includes the functional CDP driver
and page resource observer, without heap/CPU profiling. It is not interchangeable
with the installation comparison above.

| Phase | Median aggregate PSS | Peak PSS | Last PSS |
| --- | ---: | ---: | ---: |
| settled-empty-planner | 715,780,096 | 1,302,102,016 | 673,116,160 |
| generate-hike | 718,470,144 | 762,659,840 | 762,659,840 |
| long-2048 | 858,207,232 | 899,151,872 | 899,151,872 |
| 60-selections | 832,418,816 | 1,016,614,912 | 835,298,304 |
| region-switches | 861,639,680 | 1,275,083,776 | 1,275,083,776 |
| background-0 | 834,946,560 | 836,763,648 | 833,129,472 |
| foreground-0 | 537,349,120 | 543,586,304 | 471,464,960 |
| background-1 | 413,791,232 | 413,817,856 | 407,331,840 |
| foreground-1 | 456,008,704 | 459,125,760 | 454,910,976 |
| background-2 | 406,516,736 | 406,729,728 | 406,303,744 |
| foreground-2 | 454,870,016 | 459,404,288 | 454,870,016 |
| actual-gpx-save | 416,162,816 | 461,626,368 | 414,765,056 |
| clear | 479,144,448 | 480,123,904 | 478,164,992 |
| post-clear-idle | 462,652,416 | 478,894,080 | 462,793,728 |

For context, PR96 reported 688,075,776-byte selection median / 767,718,400-byte
selection peak and 892,019,712-byte switching peak; this run is higher in those
phases. PR96's separate activation peak was 1,213,277,184 bytes. These are not a
matched before/after experiment: driver diagnostics, prior form activity, workload
ordering and provider cache state differ. The table preserves the increase rather
than treating unchanged APK bytes as proof of identical memory usage. Its final
post-clear sample is lower than PR96's 617,961,472-byte sample, which likewise does
not establish a general improvement. The 15 s settled-planner label can include
late asynchronous regional/map activation after routing readiness.

These finite runs do not establish a leak or prove absence of all retention. The
bounded archive/chart assertions, native closure observations, browser retention
regressions and post-clear idle result provide the specific cleanup evidence.

### Existing installation preservation

Before/after inventory verifies unchanged bytes, sizes and signing certificates
for 14 pre-existing packages / 17 APKs,
plus 92 readable native
regional files and 110 OPFS
payload files. Production private storage is not readable with `run-as`, so its
sandbox cannot be independently hash-proven; it was not targeted for any write,
installation, clear or uninstall. Nine WebView metadata/log/database files differ
in older `.v2staging` and `.v2auditf1` packages (six and three respectively). Their
semantic database contents and the cause of those differences were not established;
the preservation claim is limited to the verified APKs and regional payloads, not
every private preference/database byte. All old packages remain installed. New audit apps/data remain
isolated. The owned HTTPS server and ADB reverse/forward mappings are removed after
testing; no device network/provider/security configuration is reset.

## Installation memory and preservation of PR96

The Yvelines run has 150 observations (148 valid main-process observations) over
284.1 s. Values below are aggregate main plus associated WebView **bytes**;
median, sampled peak and last observation have different meanings.

| Stage | Median PSS | Peak PSS | Last PSS |
| --- | ---: | ---: | ---: |
| Empty planner, 45 s | 360,587,264 | 363,266,048 | 343,387,136 |
| Map download | 389,514,240 | 414,098,432 | 414,098,432 |
| Native routing/elevation download | 365,227,008 | 366,830,592 | 366,830,592 |
| Places/Nature checking | 525,052,928 | 525,052,928 | 525,052,928 |
| Verification | 456,250,368 | 458,247,168 | 454,253,568 |
| Initial activation | 596,461,568 | 867,117,056 | 867,117,056 |
| After activation, 90 s | 557,707,264 | 710,605,824 | 557,446,144 |
| Normal reopen, 60 s | 596,555,776 | 725,434,368 | 559,566,848 |
| Process restart, 60 s | 593,135,616 | 715,738,112 | 555,780,096 |

The observed 867,117,056-byte installation/activation peak comprises 186,943,488
main-process and 680,173,568 associated-process bytes. It is 159,603,712 bytes
(22.6%) above PR96's 707,513,344-byte comparable installation peak, and below
its original 1,110,728,704-byte pre-fix peak. PR96's separate activation peak of
1,213,277,184 bytes remains a separate workload, not a proposed limit.

Both comparison runs are without heap/CPU profilers. This PR97 run additionally
performs actual Android input, retrieves an accessibility tree and uses the CDP
functional driver before installation; it also has a different fresh app UID and
provider state. Thus it does not reproduce an identical experimental condition.
The increase is real as an observation, but cannot be attributed causally to a
production code change: the normal Release APK and Valhalla library are byte-identical
to PR96. The run does **not** establish that the 707 MB result is reproduced or
that memory has no remaining optimization opportunities. It also does not establish
a leak. No arbitrary acceptance threshold or device-wide forced GC is used.

PR96's bounded installer worker, streamed Places/Nature validation and retired
map-archive ownership paths are unchanged. Existing explicit-GC retention tests
pass; the physical route-selection and cleanup measurements below complement them.
No unrelated memory redesign is made in PR97.

Yvelines (210,223,038 component bytes, 11 files) installs and becomes ready in
21.134 s; distinct Marly (25,722,739 bytes, 8 files) takes 8.187 s. Both have five
mandatory V2 components. Every file hash and size was independently reverified
before testing. Graph identities differ (`d47b022d…` versus `01a8eab9…`), as do
build identities (`a92396de…` versus `0d056336…`). Downloads use only the existing
app-scoped private HTTPS CA and normal installer, with the server bound to host
loopback. Installation counters include expected downloads and possibly concurrent
provider traffic; they are not zero-network acceptance windows.

## Options if supported policies fail

A failed policy experiment justifies keeping the privacy gate closed; it does
not prove every future provider or documented API will behave identically.
Do not replace semantic, accessible numeric/text controls with misleading input
types, or permanently remove profile, location or outing functionality to force
an empty-page result. Deferral must also be tested when a form becomes active.

| Option | Engineering cost and acceptance needed |
| --- | --- |
| Provider-level supported fix | Submit a minimal reproducible form case with provider/API versions and origin-only evidence; validate the eventual supported fix across cold/warm sessions and provider versions. No available fix or delivery date is established here. |
| Native Android presentation | Reuse the existing native routing/elevation and verified regions, but port map/chart presentation, forms, storage transitions and accessibility. Substantial UI work; measure every remaining SDK's traffic before claiming silence. |
| Separate offline UID and explicit downloader | An offline application without Internet authority would need a separate authorized HTTPS download component and narrowly scoped, verified regional handoff. This changes installation, storage, IPC and update design and requires a security review and new acceptance work. Removing the current permission alone would break regional downloads. |

None of these architectural changes is implemented in PR97. Unsupported Chromium
flags, private SafeMode switches, provider changes, system Autofill changes,
TLS exceptions and disabled Safe Browsing are excluded. Application WebView
resource interception and a network-blocked document are diagnostics, not a
firewall for all browser-process services.

## Independent final decisions

| Gate | Decision | Basis |
| --- | --- | --- |
| Application-controlled network paths | **GO for tested local paths** | Page-resource observations, source review and native zero-byte phases show local routing/elevation/map/chart/GPX behavior. This is scoped evidence, not a browser-service or whole-app firewall guarantee. Regional HTTPS downloads remain explicit expected traffic. |
| WebView/Chromium Autofill | **NO-GO** | Repeated minimal and real forms contact Autofill; autocomplete-off, actual-View exclusion, hiding and metrics opt-out fail. No supported production elimination policy is established on this provider. |
| Residual unexplained traffic | **NO-GO** | Multiple no-form sessions have positive bytes, including no-CDP and warm controls. Source remains unknown; silent adjacent runs do not override failures. |
| Offline routing/elevation functionality | **GO for tested workloads** | Six profiles, independent IGN samples/math, long/forest routes, touch, cancellation, candidates, regions, lifecycle, native closure and real GPX Save pass. This is local-execution evidence with connectivity preserved. |
| Technical code integration | **GO for research/tests/documentation review** | Automated and physical functional regressions pass; normal Release bytes are unchanged. No production privacy fix is claimed, and the observed higher installation peak and protocol differences remain explicit. Keep the PR draft for human review; no merge is performed. |
| Public release | **NO-GO** | Strict privacy fails. Existing coordinated V2 catalog/data/app and distribution approvals are not granted or changed by this investigation. |

No production HTML, routing, elevation, data, catalog, signing, permissions or version
change is made. No merge, release, Play update or regional publication is performed.
