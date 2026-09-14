# Fairphone production-region acceptance — 13 September 2026

**PRODUCTION_REGION_ACCEPTANCE_PASS.** This supersedes the missing-device and
awaiting-publication blockers in earlier reports. It does not authorize a main
merge, signing, a public deployment or a Play upload.

## Accepted application and evidence

Application commit `11c64958aeb8359931e82a6365ee8e65525b12ec`, tree
`8f22e53a35e69d4140e38d5ec43bfeded72a6d82`, on local `integration/v1-code2`.
Engineering APK: 154,131,426 bytes, SHA-256
`68da2617508d87c259c79f3d451cd25edad1cf24a285166f6c5d3bd5e65bf0f6`.
All 105 declared assets match the repository exactly. The final documentation
freeze is recorded separately in the validation receipt; it changes no application
bytes from this physically accepted commit.

Fairphone 6, Android 16 / API 36, WebView 151.0.7922.199. Engineering acceptance
uses only `io.github.victorgabillon.sugarglider.debug`. The Play-installed main
package remains code 1 / name 0.1.0. No location sharing, radio changes, `pm clear`,
uninstallation, Play-package upgrade or upload-key access was used.

Detailed JSON, drivers, screenshots and exported public-coordinate GPX evidence
are outside Git in:
`../sugarglider-v1-artifacts/fairphone-acceptance-2026-09-13/`.
The record contains failed first attempts as well as the successful reruns.

## Exact regional data

The published catalog is retrieved on the phone through credential-free CORS.
It is the exact bundled 591-byte catalog, SHA-256
`e6cbaee32e9fe9760f4cd3d9b56d4cdab69235d06d4c5a7d6e22f26fa3e02688`.
Region `yvelines-ouest-parisien`, build
`1bbf598d64f5d5cc987a60f9a4cb22318392d596ff88f3eb6b40cb70dceb4691`,
uses the [published immutable objects](v1-published-region-acceptance.md).
All six stored component files were independently size/hash checked on the phone,
both after the first installation and after reinstallation. No regional file or
publication was changed.

The Pages `.nojekyll` omission is non-blocking for the deployed custom artifact
workflow. It is not requested by the application. The previously documented
future workflow correction remains separate from acceptance.

## Physical matrix

| Scenario | Result and evidence |
| --- | --- |
| Public catalog and complete download | PASS; real normal Download region UI, no injected regional data; `download-after-http-decoding-fix.json` |
| Atomic activation | PASS; Generate/region selection remained unavailable until all four components verified; failed/cancelled/interrupted versions had no active pointer |
| Stored identities and checksums | PASS; `stored-regional-hashes.json`, `reinstalled-regional-hashes.json` |
| Offline PMTiles map | PASS; visible map and attribution, shared OPFS random reads; `offline-map-first-render.json` and lifecycle screenshots |
| All six Waypoint Route profiles | PASS; hike, trail_run, city_bike, gravel_bike, mountain_bike, road_bike; `final-tree-planning.json` |
| Hiking and cycling Auto Tour | PASS; two candidates each; hiking control 14,378 m, cycling control 14,397 m against 12,000 ± 2,500 m requests |
| Local POI/nature consumption | PASS; actual 2,153-POI / 62,191-nature-feature indexes; bounded six-call POI phases; explicit approach/access/potability/quality/budget drops; available nature partitions and unknown values remain truthful |
| Deterministic repeat | PASS; exact entire canonical candidates equal; search timing excluded; `final-tree-deterministic-repeat.json` |
| Canonical map/export geometry | PASS; every candidate passes Python neutral submitted-candidate validation; selected MapLibre source coordinates equal returned geometry |
| GPX Save and Cancel | PASS; actual Android picker; unchanged selected candidate, zero native route calls; saved 34,085-byte GPX equals Python serialization, one track/segment, no route/extensions; `final-tree-gpx-*.json` |
| Background/resume | PASS; same process and unchanged candidate; `background-resume-with-candidate.json` |
| Process restart and retained map | PASS; changed process, installed region reopened, local map and artwork visible, external downloads/API blocked; `lifecycle.json` |
| Outside coverage | PASS; explicit `no_covering_routing_pack`, no candidates, one accounted native request, no automatic retry or external route call; `outside-coverage.json` |
| Backend isolation | PASS; API/download blocking and main/worker network observation during planning; no external routing requests, no USB reverse or local routing server; this is not radio-off evidence |
| Cancellation | PASS at 1.0 MB map progress; incomplete inactive region and disabled Generate; `download-recovery.json` |
| Process interruption | PASS after 11.9 MB native routing progress; inactive after restart; explicit Remove followed by fresh download succeeds |
| Removal and reinstallation | PASS through normal UI; all components reverified, then a local Auto Tour passes with the same geometry; `post-reinstall-planning.json` |
| Update/failed update on device | NOT APPLICABLE to this single published immutable version; no substituted version/data. Automated staged-update, cancellation, checksum-failure and active-version-preservation cases remain part of final validation |

These fixtures found no POI insertion that passed the existing arrival/quality
constraints; the UI retains explicit drops and the no-POI control. Missing exact
edge repetition/backtracking and unavailable candidate nature analysis remain
unknown. Acceptance does not claim routing-server parity or POI promotion.

## Measurements

- Complete public install through ready UI: **25.947 s**; reinstallation **25.723 s**.
- Four components: **188,366,639 bytes**, plus the 2,229-byte regional manifest.
- Measured app-directory growth: **192,808,960 bytes**. Sampled combined
  files/WebView/no-backup peak: **326,959,104 bytes**, including existing debug data.
  Samples are not an exact operating-system allocation high-water mark.
- Device free storage at first successful download start: **175,880,462,336 bytes**;
  after readiness: **175,679,709,184 bytes**. Other device activity can affect this.
- Final-tree Waypoint Route: **3.144–5.981 s**, one native route call each.
- Final-tree Auto Tour: **6.367–6.894 s**, 12 hiking / 14 cycling calls within the
  24-call total bound and six-call POI bound. After process interruption/removal/
  reinstallation the hiking tour took **9.142 s**, with the same routed geometry.
- Cold process launch through region readiness and visible map: **13.406 s**.

## Demonstrated blockers fixed

`48c9441` corrects the map installer's HTTP header assumption. GitHub Pages
compresses the PMTiles transfer for browsers: Content-Length was 81,510,429 while
Fetch returned the original 81,571,296 archive bytes, and CORS hid Content-Encoding.
The installer now bounds and checks actual decoded archive bytes, exact SHA-256
and PMTiles structure. Truncation, oversize, corruption and cancellation still
fail without activation. Regression fails before the fix and passes afterward.

`11c6495` includes the two existing lazy HTML illustrations omitted from the Android
allowlist. Artwork remains unchanged and synchronized; the new test checks every
HTML image is bundled. Both missing files caused the regression to fail before the
fix. The repaired empty-map illustration was observed on the Fairphone.

## Final release gate and remaining user actions

The accepted application is ready to freeze for `1.0.0` / code 2. Full validation
must run after this documentation freeze: `make check`, all browser harnesses,
both native test/lint variants, APK/AAB builds, exact packaged assets/native binary,
bundletool and release/security/alignment checks. The resulting exact freeze
commit/tree, logs, unsigned bundle hash and validation outcome are recorded in
`../sugarglider-v1-artifacts/fairphone-acceptance-2026-09-13/final-validation.json`.
The earlier 1,100-test/47-affected-browser-case checks are pre-freeze evidence.

After the receipt is green, configure the existing permanent upload key outside
Git using `SUGARGLIDER_ANDROID_SIGNING_PROPERTIES=/absolute/private/signing.properties`
with exactly `storeFile`, `storePassword`, `keyAlias`, `keyPassword`. The user need
supply only the private configuration path; never paste secrets into chat. No new
key or signing identity is needed. The approved privacy URL is already configured.

Explicit main integration approval, confirmation that code 2 is available in Play,
signing with the existing key, Internal testing delivery and a Play-installed
update/smoke test remain separate gates. Optional social hosting/operator/backup
settings are needed only if that currently disabled service is later deployed.
