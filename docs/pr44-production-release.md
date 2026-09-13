# PR44 — production Android release hardening (in progress)

This preserves the original hardening-stage evidence. Later MapLibre/security and
publication findings supersede its historical blockers; use the
[current publication/acceptance record](v1-published-region-acceptance.md) and
[V1 ledger](v1-readiness.md) for the current state.

This integration follows product `b568418` / draft PR #51 and static publication
`9ed8dbe` / draft PR #52; both pass all five CI checks. It selectively integrates
the earlier PR44 preparation from `2ab30b8` without restoring disabled release
routing, development profile flags, obsolete server-origin startup or the old
string-only bridge. Production routing, protocol-v3 regional identity and binary
canonical GPX export remain the shared implementations.

No release readiness or physical completion is claimed here. The hosting question
for the reviewed 188.4 MB regional package is pending. Public privacy identity,
upload-key configuration, Play declarations and the remaining physical matrix
are still external/final acceptance gates.

## Current policy and device findings

Official guidance rechecked on 2026-09-12 requires API 36 for standard new apps
and updates from 2026-08-31. The app already compiles/targets 36 and supports
API 26+. [Google Play target API](https://developer.android.com/google/play/requirements/target-sdk).

Android 16 requires edge-to-edge handling and the supported predictive-back API.
The Activity uses OnBackInvokedDispatcher and now applies cutout, lateral,
navigation-bar and keyboard insets to the full planner. It retains the same
WebView for orientation/size/keyboard changes, invalidates its drawing and
reapplies insets without serializing capabilities, reloading or rerouting. Other
Activity/process recreation still resets unsaved page state truthfully. Physical
rotation, keyboard and lifecycle checks remain open.
[WebView configuration guidance](https://developer.android.com/develop/adaptive-apps/cookbook/webview-state).
[Android 16 behavior changes](https://developer.android.com/about/versions/16/behavior-changes-16).

The Fairphone has both the debug test app and an existing main package installed
by `com.android.vending`: version code 1 / name 0.1.0, last updated 2026-09-06.
That existing installation has not been replaced, cleared or uninstalled.
The proposed update uses code 2 / name 1.0.0; the publisher must confirm that code
2 is unused on all Play tracks and use the existing app’s upload-key setup.
No external signing configuration is present in the current build environment.

## Integrated safeguards

- External signing uses an explicitly supplied four-field properties file and
  keystore, both resolving outside the checkout. Missing configuration produces
  an unsigned bundle, without substituting the debug key. Partial/invalid
  configuration fails explicitly. Release debugging is explicitly disabled;
  WebView debugging follows BuildConfig.DEBUG. See
  [signing procedure](pr44-signing-and-bundle.md).
- Cloud backup and Android device transfer explicitly exclude all nine supported
  storage domains, alongside existing allowBackup/fullBackupContent false flags.
  Native participant data remains encrypted in no-backup storage. Cross-platform
  transfer has no iOS identity or transfer API configured. No OEM transfer test is
  inferred from XML inspection. [Android backup rules](https://developer.android.com/identity/data/autobackup).
- Renderer loss discards the dead page’s geolocation callback before invalidating
  its bridge, regional operation owner and GPX reply ownership. Only the affected
  WebView is removed/destroyed. Reopen requires an explicit current recovery action;
  stale recovery callbacks cannot replace a newer page. Pending GPX work receives
  a truthful check-the-file warning, not a success claim or an automatic retry.
- Native Privacy opens local details without navigating away from the planner.
  It is also available inside Start disclosure without dismissing or accepting
  that disclosure. The optional public HTTPS policy URL is separately validated
  at build time; no online policy link is fabricated while approval is pending.
  See the [privacy/Data Safety draft](pr44-privacy-data-safety.md).
- Native sharing retains its existing lifecycle. Recovery explains that active
  sharing continues and offers the existing Stop action. The native Start
  disclosure now says that precise coordinates are sent and recent updates are
  briefly retained for viewer reconnection. No historical activity-track claim,
  new permission, automatic Start or automatic Stop is introduced.

## Dependency review and remaining blocker

The resolved release includes 34 Maven components: AndroidX/Core/WebKit, Kotlin
and coroutines, the Valhalla wrapper/models, Moshi/Okio and generated OSRM models.
No advertising/analytics SDK appears in that inventory. An OSV query of those
exact coordinates returned no matching advisory on 2026-09-12. This does not cover
embedded native dependencies, the installed OS/WebView or unreported issues.
R8/resource shrinking remain disabled because the production JNI and reflected
Moshi models need separate keep-rule and device validation before that change.

The four directly vendored browser packages were also queried. **MapLibre GL JS
4.7.1 has the published critical GHSA-jrc7-96c5-q579 attribution sanitizer bypass.**
PMTiles 4.5.0, Protomaps basemaps 5.7.2 and noble-hashes 2.4.0 returned no matching
advisory. Updating MapLibre to the officially patched 6.4.1 and validating its
module/worker integration is an explicit release blocker being handled in a
separate follow-up; no current artifact is declared ready.
[Upstream advisory](https://github.com/maplibre/maplibre-gl-js/security/advisories/GHSA-jrc7-96c5-q579).

## Native integration validation

`make check` passes 1,052 tests / 16 existing integration tests deselected,
Ruff and strict mypy. The final combined native unit/lint/APK/AAB run passes in
4 min 33 s: 196 JUnit tests per variant with zero failures, errors or skips;
lint has two debug / one release existing warnings and no errors. Both artifacts
contain all 101 shell assets byte-identical to source and the same sole ARM64
native library, SHA-256
`e60d66dba922a17c53397e4a00ba4380a9ec87f8f203d3761fefe86bef9b2bbb`.

The native integration unsigned AAB is 47,423,654 bytes, SHA-256
`a6072bc17ab57191db88e96b6d7247fc56e5cd2573a2e196d5591f0361d8c451`,
retained outside Git at `/tmp/sugarglider-pr44-native-unsigned.aab`.
The debug APK is 151,812,979 bytes, SHA-256
`20d4bc53e8501a28179e04e334cf1ef2336d902434672d38d691be250b0a82eb`.
These still include MapLibre 4.7.1 and are **not release candidates**.

Three negative signing cases and a credential-bearing policy URL fail explicitly.
Before the final rotation/inset polish, a disposable two-day host-only certificate
successfully signed an AAB (47,436,306 bytes, SHA-256
`ad204aed8f36b299f0939652986922e2cdbb1786b631a05c993a2b71d6e8e7d3`).
`jarsigner` verifies it with the expected self-signed trust warning; official
bundletool 1.18.3 validates it and generates a universal APK. Both the direct
release APK and bundletool-delivered APK pass `apksigner verify` and
`zipalign -c -P 16 4`. The final unsigned bundle also passes bundletool validation;
the native ELF LOAD segments are at least 16 KiB aligned. None of this establishes
runtime acceptance on a 16 KiB device. No disposable artifact was installed or
uploaded; its key/properties/password files were removed and unsigned output
restored. No permanent signing key was generated or read.

Bundletool was obtained from the official Google release, 32,520,401 bytes with
release-advertised SHA-256
`a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29`.
Evidence is under `/tmp/sugarglider-pr44-final-{check,android}.log`,
`/tmp/sugarglider-pr44-native-*`, `/tmp/sugarglider-pr44-dependency-audit.*` and
the non-secret `/tmp/sugarglider-pr44-disposable-signing-vq8tzo8o/report.json`.
No new browser claim is made for these native-only changes; the preceding
product implementation passed 361 browser cases plus four real-page synthetic
adapter scenarios. The MapLibre follow-up requires those checks again.

The [store and physical matrix](pr44-store-acceptance.md) records current policy
dates, permission inventory, publisher material and explicit unpassed device rows.
Remaining work includes final artifact validation, the MapLibre security update,
public policy identity/URL, and physical release/region/lifecycle/permission/export
acceptance.
The required public hosting and publisher decisions do not authorize weakening
any of these checks.
