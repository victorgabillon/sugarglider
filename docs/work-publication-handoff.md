# Exact handoff for ChatGPT Work

The single block below is self-contained. No publication was performed by Codex.

```text
WORK_PUBLICATION_HANDOFF — Sugarglider V1 code 2

Work owns public hosting and Play Console operations; this handoff is for static regional files and the reviewed app privacy policy only. Do not upload anything to Google Play, merge application drafts/main, or create/rotate signing keys.

Publish the prepared bytes; do not rebuild them.
This rule covers the regional ZIP and all 11 extracted site files. Do not rerun map/routing/index builders, recompress the ZIP/gzip indexes, rewrite/minify JSON, change bounds/build IDs, or replace immutable files. Only the privacy template is intentionally editable for the publisher review below.

SOURCE OF TRUTH
Application repository: https://github.com/victorgabillon/sugarglider
Original static distribution tooling: branch feat/pr42-static-distribution; PR https://github.com/victorgabillon/sugarglider/pull/52; commit 9ed8dbe3cf757638af846882e7e0046443eda95c.
Use the prepared publication sources from local branch integration/v1-code2, commit 99ed28fd10781f5af880280bdea26a0075333b2c, which adds the reviewed-privacy copy step. This branch is local, not published to GitHub; do not substitute main or obsolete PR #42.
Integration checkout: /home/pompote/oldata/victor/sugarglider-v1-code2
Verified extracted site directory: /home/pompote/oldata/victor/sugarglider-v1-artifacts/work-publication-code2/site
Primary regional ZIP path: /home/pompote/oldata/victor/sugarglider-v1-artifacts/2026-09-12-05b77ba/sugarglider-regions-static.zip
Primary regional ZIP filename: sugarglider-regions-static.zip
Primary regional ZIP size: 188374659 bytes
Primary regional ZIP SHA-256: 40990c600c0b7bf934522daef1c92d7db44d0ab890077e1224084a6244476a9f
Region ID: yvelines-ouest-parisien
Region display name: Yvelines et ouest parisien
Build ID: 1bbf598d64f5d5cc987a60f9a4cb22318392d596ff88f3eb6b40cb70dceb4691
Bounds: [1.445097, 48.38, 2.25, 49.1] (rectangular coverage, not administrative boundaries or a connectivity guarantee).
Total seven regional files: 188368868 bytes. Catalog download_bytes: 188366639 (component files only; excludes the top-level manifest).
Catalog local path: /home/pompote/oldata/victor/sugarglider-v1-artifacts/work-publication-code2/site/catalog.json
Regional manifest local path: /home/pompote/oldata/victor/sugarglider-v1-artifacts/work-publication-code2/site/regions/yvelines-ouest-parisien/1bbf598d64f5d5cc987a60f9a4cb22318392d596ff88f3eb6b40cb70dceb4691/manifest.json
Map manifest local path: /home/pompote/oldata/victor/sugarglider-v1-artifacts/work-publication-code2/site/regions/yvelines-ouest-parisien/1bbf598d64f5d5cc987a60f9a4cb22318392d596ff88f3eb6b40cb70dceb4691/map/manifest.json
Routing manifest local path: /home/pompote/oldata/victor/sugarglider-v1-artifacts/work-publication-code2/site/regions/yvelines-ouest-parisien/1bbf598d64f5d5cc987a60f9a4cb22318392d596ff88f3eb6b40cb70dceb4691/routing/manifest.json

EXACT PUBLIC LAYOUT
Repository to create/use: victorgabillon/sugarglider-regions
Pages base: https://victorgabillon.github.io/sugarglider-regions/
Catalog: https://victorgabillon.github.io/sugarglider-regions/catalog.json
Region base R: https://victorgabillon.github.io/sugarglider-regions/regions/yvelines-ouest-parisien/1bbf598d64f5d5cc987a60f9a4cb22318392d596ff88f3eb6b40cb70dceb4691/
Region manifest: https://victorgabillon.github.io/sugarglider-regions/regions/yvelines-ouest-parisien/1bbf598d64f5d5cc987a60f9a4cb22318392d596ff88f3eb6b40cb70dceb4691/manifest.json
Privacy policy: https://victorgabillon.github.io/sugarglider-regions/privacy/
Release tag: yvelines-1bbf598d64f5d5cc987a60f9a4cb22318392d596ff88f3eb6b40cb70dceb4691
Release asset: https://github.com/victorgabillon/sugarglider-regions/releases/download/yvelines-1bbf598d64f5d5cc987a60f9a4cb22318392d596ff88f3eb6b40cb70dceb4691/sugarglider-regions-static.zip
GitHub Releases stores the complete large ZIP as a workflow input. GitHub Pages serves ALL extracted regional files, including the large PMTiles and routing archives, as well as catalog, attribution, landing page and privacy. Pages is not limited to the small files in this design. The Android client does not download individual Release assets and must never be given their redirecting URLs.

IMMUTABLE REGIONAL FILES (each local path = verified site directory + region path + relative path; each public URL = R + relative path)
Filename | bytes | SHA-256
manifest.json | 2229 | f99076f190d6f728c6b8924e619a5962eb0fd8214207112d7e26eb39d6ba4da8
map/basemap.pmtiles | 81571296 | 620dddfcb7e9c77995d91987299a5651ad1be4ef957154ab5c81ff414b60ff94
map/manifest.json | 631 | f1ddced633fae222133aac580172920c21f2e4a45f57b99a3d3ec1094aa5269c
nature/index.json.gz | 10634994 | abb0819a4f4b02d8ee844aa19de71c1760e0b63a1a9f7bd3410513d82dca7b90
pois/index.json.gz | 108248 | 03ed6ca8250e8f540a91b108fbfc989082161aa6f9231be17417ea51a660cb17
routing/manifest.json | 270 | 89961563df977a3eaf421c0192ddd8ec7513c6ee567f46e2c240fddd2299753d
routing/valhalla_tiles.tar | 96051200 | 94d83392f4261809ce830f916d01d24db14b7d0a30f1e9ded655078c37364b0f

OTHER EXACT SITE FILES (local/public paths relative to site/Pages base)
Filename | bytes | SHA-256
.nojekyll | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
README.txt | 1712 | 0889b5bfc5123e7625e6690332b9d1898c03f26401189b8821085b68226dc95d
catalog.json | 591 | e6cbaee32e9fe9760f4cd3d9b56d4cdab69235d06d4c5a7d6e22f26fa3e02688
index.html | 922 | 2ac325f08185bcef52b795f40bb48366e88e71f0f2c969c464c6cd3c63904cae
.nojekyll is a deployment flag; its lack of a public HTTP endpoint does not prevent runtime downloads.

PREPARED PUBLICATION SOURCES
Source directory, already arranged for the data repository: /home/pompote/oldata/victor/sugarglider-v1-artifacts/work-publication-code2/source
Small source-transfer ZIP: /home/pompote/oldata/victor/sugarglider-v1-artifacts/work-publication-code2/sugarglider-work-publication-source.zip
Source-transfer ZIP size: 20301 bytes
Source-transfer ZIP SHA-256: 6773bd83139df5ee30b6567602abc2f48c56ef56b5ff4114ec2468bb9b76a273
If this filesystem is unavailable to Work, obtain these two exact ZIP attachments from the user; do not recreate their contents. The large ZIP is the Release asset. Extract the small ZIP and commit its source files to the data repository, with the privacy edit described below.
Target path | unchanged source SHA-256 (privacy is its pre-review template hash)
.github/workflows/publish.yml | 80e6928bfc4d2808f30413d7b83f32a3704e26d694454588420524b1a47dfccc
unpack_distribution.py | 6200b06fe40c9bebfdd7c7577d1401a240b1e4cca88f134602f740138de55cc2
copy_public_privacy.py | 5263cadfd7dea3fd835812564e9ae515387a3b4be53988338578f0231fd96a3e
privacy/index.html | 7b82b997f06d1c156b6371be4ac2cb26f6a1d6126ad2617c05b1b257fc4d0e75
README.md | 7d8ae36cd68de9ee8d8c4ec8009b9deb1c386f989278d33cee69bde185bb9928
yvelines-publication.json | 2978bd7fc4f2118d7377fcbfe5f61bf34dc941f663fa0fd4306aeeea78b4d8cd

PUBLICATION PROCEDURE
1. Use the exact proposed public data repository and the prepared source layout above. Enable Pages with GitHub Actions as its source. Keep generated regional files out of Git history.
2. Upload only the unchanged primary ZIP as the Release asset named sugarglider-regions-static.zip on tag yvelines-1bbf598d64f5d5cc987a60f9a4cb22318392d596ff88f3eb6b40cb70dceb4691. Verify its uploaded size/hash against the values above.
3. Complete/review privacy/index.html as below. Commit the prepared workflow, both Python helpers, README, verification metadata and reviewed privacy source. Do not replace the pinned action revisions or weaken the archive verifier.
4. Manually dispatch the prepared workflow with release_tag=yvelines-1bbf598d64f5d5cc987a60f9a4cb22318392d596ff88f3eb6b40cb70dceb4691 and archive_sha256=40990c600c0b7bf934522daef1c92d7db44d0ab890077e1224084a6244476a9f. Its exact target is .github/workflows/publish.yml; its application source is deploy/regions/github-pages/publish.yml at the integration tooling commit above.
5. The workflow downloads the selected Release ZIP, verifies its complete hash, extracts only allowed regular files, copies the reviewed privacy HTML unchanged to privacy/index.html, and publishes the resulting complete site. It does not rebuild regional data. No push/release event automatically triggers it.
6. Verify actual HTTPS GET responses and streamed hashes below. A successful Actions run alone is insufficient. If Pages limits, CORS, MIME or redirect behavior prevent the contract, report the exact incompatibility; do not silently substitute another host/transport or rebuild data.
7. Every later Pages deployment replaces the entire site: retain the reviewed privacy page and all still-supported immutable versions. This prepared first package has one version; do not invent an update version.

ANDROID/BROWSER DOWNLOAD CONTRACT
- Exact canonical public HTTPS URLs, no userinfo, token/query/fragment, authentication, cookies, custom trust or redirects. Direct full GET must return 200 at the requested URL.
- Browser-downloaded catalog, top-level/map manifests, PMTiles and gzip indexes need Access-Control-Allow-Origin: * or https://appassets.androidplatform.net. Native routing downloads do not rely on CORS. Return observed headers for every file.
- Downloads using Accept-Encoding: identity must deliver the exact listed bytes. Routing responses reject non-identity Content-Encoding. The .json.gz files must remain gzip payloads, not HTTP-decompressed JSON; do not add Content-Encoding: gzip to those stored gzip bytes.
- Content-Length, when present, must equal the listed byte size. Record actual Content-Type: JSON should be application/json; PMTiles application/octet-stream or application/vnd.pmtiles; tar application/octet-stream or application/x-tar; gzip application/gzip or application/octet-stream; policy/landing text/html UTF-8; README text/plain.
- Installation uses full-file GETs; local PMTiles random reads use OPFS after installation. No server tile API, bulk raster cache or remote range-read fallback is involved.
- Preserve .nojekyll, README.txt and all map/OSM/ODbL/source attribution unchanged. Native bounds/profile validation, SHA-256 and byte limits stay authoritative.

PRIVACY POLICY HANDOFF
Canonical policy source: /home/pompote/oldata/victor/sugarglider-v1-code2/docs/pr44-privacy-data-safety.md (Privacy-policy source text section).
Prepared editable HTML: /home/pompote/oldata/victor/sugarglider-v1-code2/deploy/regions/github-pages/privacy/index.html; copied into the small source ZIP as privacy/index.html.
Desired public URL: https://victorgabillon.github.io/sugarglider-regions/privacy/
Public developer name is already Sugarglider. Fill {{PUBLIC_PUBLISHER_IDENTITY}}, {{PUBLIC_PRIVACY_CONTACT}}, {{POLICY_EFFECTIVE_DATE}}, and {{APPROVED_HOSTS_AND_ACTUAL_RETENTION}} with approved public facts. Name the actual static/social providers and operator settings; do not invent a social endpoint, contact or legal identity. Review the whole policy, then change data-policy-status="draft" to "approved". The workflow deliberately rejects unfinished placeholders, the draft marker and embedded active elements.
Keep these statements aligned with actual code/deployment: bundled Android planning and local GPX inspection stay local; sharing snapshots is explicit and links are unlisted; native outing location starts only after explicit disclosure/permissions and can continue screen-off through a foreground service with Stop, without automatic restart after process death/reboot; one current position plus bounded reconnection replay is not an activity history; default retention is routes 90 days, outings 30 days, position stale 120 s/expiry 3600 s, replay at most 900 s/1000 events, backups seven days with no live-position/replay rows; optional Remember/native storage retain only their bounded session/latest pending fix; no audited advertising/analytics integration; static providers receive request metadata; deletion/Stop/backup limitations remain truthful.
The app privacy-policy URL belongs in the app-specific Play privacy field and later Android build setting. It is distinct from public developer name/contact/website metadata; neither a developer homepage nor the tester invitation is a substitute. Do not copy private account/address/payment data, capabilities or signing material into this public repository or page. Do not upload a Play release as part of this handoff.

RETURN CONTRACT — SEND BACK TO CODEX
- Final catalog HTTPS URL.
- Final top-level regional manifest HTTPS URL.
- Full immutable HTTPS URLs for map/manifest.json, map/basemap.pmtiles, routing/manifest.json, routing/valhalla_tiles.tar, pois/index.json.gz and nature/index.json.gz.
- Final public app privacy-policy HTTPS URL and its reviewed effective publisher/contact/host settings.
- Uploaded regional ZIP observed filename, byte size and SHA-256.
- For each hosted catalog/manifest/component and privacy page: requested URL, final URL, GET status, observed entity byte size and SHA-256, Content-Type, Content-Length, Content-Encoding, Access-Control-Allow-Origin and every redirect encountered. Use Origin: https://appassets.androidplatform.net and Accept-Encoding: identity for the client-contract checks.
- Public repository, Release and Pages workflow run URLs, any hosting limitation/failure, and whether the verified bytes remained unchanged.
Publishing alone does not activate the app catalog: Codex will verify the return, embed the verified catalog/privacy URL, rebuild/revalidate and run the prepared physical acceptance. Do not mark those device gates passed.
```
