# PR97: WebView Autofill traffic and offline privacy

Base: `45a31c8789e00476652c90f75a2e323f4e69ee51` (merged PR96).
This investigation preserves PR96's installer improvements and all routing,
terrain, elevation, regional identities, catalogs, signing and version settings.
Raw evidence stays in ignored `data/offline-regions/pr97-autofill/evidence/`.

## Measurement contract

Physical experiments use a new, independently verified `.v2auditn1` namespace,
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
available. Expected private regional HTTPS downloads are separate windows.

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
research-only manifest overlay is prepared to test this hypothesis. Neither this
option nor an origin-only netlog can identify the contents of an encrypted request.
[WebView reporting privacy](https://developer.android.com/develop/ui/views/layout/webapps/webview-privacy).

## Initial physical observations

All byte values below are exact UID deltas, **Tx / Rx**, with networking available.
Each row is an independent process and, for HTML controls, a fresh WebView data
namespace. The completed form rows use the verified research APK SHA-256
`ff2a6f20a9ee09436a398643e7128528c7fc139b6788f5b11d7f94ad0ac0c64d`.

| Control | Tx / Rx bytes | Metadata | Strict zero |
| --- | ---: | --- | --- |
| Native Activity, two completed sessions | 0 / 0 each | No WebView document | PASS |
| Empty WebView, two completed sessions | 0 / 0 each | No navigation | PASS |
| `about:blank`, two completed sessions | 0 / 0 each | No HTML form | PASS |
| No forms, scripts or external assets (`b4-none`) | 3,584 / 2,983 | Trace contained local appassets origin only | FAIL |
| Three-field form (`c1-form-three`) | 7,422 / 10,903 | `content-autofill.googleapis.com` | FAIL |
| Same form with third field removed (`c2-form-two`) | 4,326 / 7,325 | `content-autofill.googleapis.com` | FAIL |

The three-field and two-field pages required neither typing nor focus to produce
Autofill traffic. Removing the third field did **not** eliminate the request;
this experiment does not establish a three-field threshold or a privacy fix.
For these two sessions, all positive deltas occurred during the visible-page
window; setup and 15 s after page destruction were 0 / 0. Origin metadata
establishes destination, not encrypted payload contents or the number of useful
application-level transactions.

The no-form control is a separate unresolved observation. Its trace had three
netlog events (two CORS events and a preflight-necessity check), no external
origin, and no resolver host metadata. This is insufficient to attribute its
bytes to Autofill, metrics, DNS, Safe Browsing or CDP. Socket snapshots can miss
brief connections and have a netlink-permission limitation. Further independent
no-CDP, JavaScript-disabled and bounded Java method-sampling controls are needed.

Interrupted attempts (`a4`, `b5` and `c3`) are retained as incomplete, never
counted as zero-byte passes. The foreground guard stops when the phone is used
in another app. No screenshots or content from that other app are collected.

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
Normal Debug, Release and the isolated research APK pass ZIP 16 KiB alignment;
every native ELF load segment has 16 KiB alignment and congruent offsets.
The Valhalla library remains SHA-256
`09b6d312b19caa5410561b804213641f5f8a772d1b3db570cc17bac8a55fb878`.

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

## Acceptance still in progress

At this checkpoint the repeated supported-policy interventions, residual-traffic
controls, final installed-package functionality, installation memory comparison
and after-test preservation inventory are pending an unused Fairphone window.
The two completed form measurements fail strict privacy acceptance. No production
Autofill change or privacy guarantee is claimed. Host checks alone do not grant
physical acceptance or public release approval. The draft PR remains unready for
final integration review until these measurements and independent decisions are
recorded.
