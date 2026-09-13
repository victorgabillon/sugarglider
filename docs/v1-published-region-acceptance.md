# Published Yvelines acceptance

## Publication verified; previous hosting blocker superseded

Work published the prepared distribution at data-repository commit
`6b70b937ec11f37cea5c240e9bd76b098bbf50ae`, through
[workflow run 34746139123](https://github.com/victorgabillon/sugarglider-regions/actions/runs/34746139123).
The old September 12 observation that the public URLs return 404 is superseded.
No regional data was rebuilt, recompressed, repackaged or substituted by Codex.

Codex independently ran the prepared bounded public-file preflight:

```sh
uv run --offline python -m sugarglider.offline_regions.acceptance \
  --catalog-url 'https://victorgabillon.github.io/sugarglider-regions/catalog.json' \
  --privacy-url 'https://victorgabillon.github.io/sugarglider-regions/privacy/'
```

It completed in **9.445 seconds on the computer**, with direct HTTP 200, exact
byte sizes and SHA-256 hashes, matching Content-Length, no Content-Encoding, and
`Access-Control-Allow-Origin: *` for every checked object. No redirect or cookie
reuse was allowed. This is host verification, not a phone download measurement.
Detailed observations and generated requests are in
`/tmp/sugarglider-v1-final-acceptance-t9wvv1l4/`.

The region is `yvelines-ouest-parisien`, build
`1bbf598d64f5d5cc987a60f9a4cb22318392d596ff88f3eb6b40cb70dceb4691`.
Its seven regional files total **188,368,868 bytes**, of which **188,366,639 bytes**
are the six component files. All identities remain those in
`deploy/regions/github-pages/yvelines-publication.json`.

The [catalog](https://victorgabillon.github.io/sugarglider-regions/catalog.json)
is **591 bytes**, SHA-256
`e6cbaee32e9fe9760f4cd3d9b56d4cdab69235d06d4c5a7d6e22f26fa3e02688`.
Its exact verified bytes are now the bundled catalog. The shared application-shell
cache advances from v42 to v43 so browsers do not retain the unavailable offering.
The normal UI uses this bundled catalog snapshot and retrieves the advertised
manifest/components directly from Pages; it does not introduce a routing backend.

The approved [privacy page](https://victorgabillon.github.io/sugarglider-regions/privacy/)
is **4,827 bytes**, SHA-256
`8bcfb8ef06c81d048792e996aeeb609b6c3258ce9364ee1f6a89742e028fb729`.
It names public developer Sugarglider, publisher Victor Gabillon, the supplied
public email contact and effective date 13 September 2026. It explicitly says the
optional social service is not deployed/configured for this internal test, matching
the Android UI configuration. The Android build now defaults to this approved
public policy URL; its existing public environment override remains available.

## Explicit `.nojekyll` disposition

Codex confirmed `.nojekyll` returns HTTP 404. It remains present as the exact empty
file in the canonical prepared ZIP; no archive bytes were changed. The
[pinned upload-pages-artifact action](https://github.com/actions/upload-pages-artifact/blob/7b1f4a764d45c48632c6b24a0339c27f5614fb0b/action.yml)
does not accept `include-hidden-files` and explicitly excludes hidden files when
constructing its deployment tar. This explains Work's observed warning/omission.

This is **non-blocking for this deployment**: the custom workflow securely
extracts an already-built static site and deploys the artifact without a Jekyll
build step, and neither the Android nor browser download path consumes this flag.
GitHub documents this
[direct artifact workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
All application-consumed files passed the actual hosted-byte checks above.

Future workflow cleanup should remove the unsupported input and document the
intentional omission for artifact-based deployment. It does not require rebuilding
regional data or republishing this working deployment. The original publication
source bundle remains an immutable record of what Work used; Codex has neither
edited the public workflow nor requested another publication.

## Physical acceptance status

**NOT RUN against the published production region yet.** Initial `adb devices -l`
on September 13 returned an empty device list. The user has been asked to reconnect
and unlock the Fairphone without changing the hotspot or radios. All physical
scenarios in the [prepared checklist](v1-final-device-acceptance.md) remain open;
the public preflight is not a substitute for their evidence.

Only the separate debug package may be used for engineering installation. Preserve
the Play-installed main package and data. No `pm clear`, radio/hotspot change,
physical radio-off claim, signing, Play upload or merge to main is authorized.
After physical acceptance, identify the exact accepted tree and perform the final
full release checks against it. Until then this is a configured candidate, not a
frozen accepted release.

The original upload key and recovery file have been located in the user's private
ChatGPT Library, according to the supplied record. No replacement key is needed.
Do not access or transfer them during acceptance; local signing configuration is a
separate step after the acceptance and validation gates pass.

## Configured candidate validation while awaiting the phone

Application commit: `32f515a91f5259f1bf0d1f440a38ebb80f399641`.
Its committed tree is `4c951b6a548885f59091dd7d135ac770762bb19a`.
Branch/worktree remain `integration/v1-code2` at
`/home/pompote/oldata/victor/sugarglider-v1-code2`. Subsequent edits in this pass
record evidence in documentation only. This is **not** an accepted/frozen tree:
no Fairphone appeared during the pass, despite repeated enumeration.

| Validation | Observed result |
| --- | --- |
| `make check` | 1,099 passed / 16 existing integration deselections; Ruff and strict mypy pass; 51.25 s |
| Browser harnesses | All 27 pass, 480 cases; canonical model/GPX comparisons pass |
| Debug unit tests/lint/assembly | 196 tests, zero failures/errors/skips; two existing lint warnings; 3 min 9 s |
| Release unit tests/lint/assembly/bundle | 196 tests, zero failures/errors/skips; one existing lint warning; 3 min 25 s |
| Official bundletool 1.18.3 | `validate` passes; pinned tool digest verified |
| Shared packaged assets | All 103 source assets match both debug APK and release AAB |
| Privacy configuration | Approved URL confirmed in both generated BuildConfig variants |
| Native library | Sole ARM64 library matches source identity in both packages; all three ELF LOAD alignments are 16,384 bytes |
| Package alignment | Unsigned release APK passes `zipalign -c -P 16 4`; AAB configuration declares `PAGE_ALIGNMENT_16K` |
| Release boundaries | Package/code/name 2/1.0.0, min 26/target 36, exactly six expected permissions, no debug/cleartext/backup enablement, private location service |
| Real signing / device runtime | Not performed; AAB has no signing entries; binary alignment does not establish a 16 KiB runtime PASS |
| Git whitespace | `git diff --check` passes |

The existing full harness runner was copied to
`/tmp/sugarglider-v1-published-browser.py`, changing only evidence output prefixes,
and invoked with `uv run --offline python`. The native build commands used JDK 17,
SDK 36, offline Gradle, no configuration cache, one worker, a 1,400 MiB JVM heap,
and the existing 3 GiB / 200% CPU systemd scope limits. The release invocation
explicitly removed signing and privacy override environment variables so it used
no upload key and exercised the approved default policy URL.

Preserved artifacts and logs are outside Git under
`/home/pompote/oldata/victor/sugarglider-v1-artifacts/published-yvelines-2026-09-13/`:

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| `app-debug.apk` | 151693653 | `c2424aa5b85fc344ddd29443b9c6f7617fe580f27ded6e2e15cae0a75e51f50b` |
| `app-release.aab` (unsigned) | 47496488 | `f7aa862691544b414a921015e51e3f4658848be5639adba936bff052873cb5a6` |

All phone installation/activation, map, planning, POI/nature, deterministic-repeat,
GPX, lifecycle, outside-coverage, interruption/cancellation, removal/reinstall and
storage/timing rows remain **NOT RUN**. The first catalog advertises only one
prepared version; physical update preservation additionally needs an actual
different version and must not be inferred from Verify download. No phone storage
or latency values are available. These pre-acceptance automated checks do not
replace the required post-acceptance validation of the eventual accepted tree.

**Current blocker: Fairphone is not connected to ADB.** Publication/privacy hosting
is verified and no longer a blocker. The original checkout and main remain at
`ce4d8b70a16d7dda54203298033b4f0314ed5a61` and
`d129c22a808c0031c0bb09174ecbc5c22dfbda8d` respectively; the protected untracked
entries and stash `6abe302207f4336b04e3a050966c263c218393a1` remain untouched.
Nothing was pushed, publicly published, signed with the upload key, installed on
the phone or merged to main by Codex in this pass.
