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
