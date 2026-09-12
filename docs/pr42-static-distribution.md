# PR42 — static regional distribution preparation

Status: prepared locally; publication requires a hosting decision. The app's
bundled Yvelines download URL remains null. No repository, public release,
Pages site, paid resource, DNS record or account has been created by this slice.
The product UI is in dependent draft [PR #51](https://github.com/victorgabillon/sugarglider/pull/51),
which passes all five CI checks at `b568418`.

## Files, identity and publication

The existing PR39 validator checks the source components before packaging. The
preparer copies only the seven declared regional files to
`regions/<region-id>/<build-id>/`, verifies the copied region again, and writes
an attributed static landing page, README and compatible public catalog. It
produces a deterministic uncompressed ZIP and an external report of sizes/hashes.
It rejects an existing output, unsafe output paths, corrupt sources, insufficient
space and a site exceeding 950 MB. It never uploads, deploys or changes the app
catalog. Generated data, ZIPs and reports remain outside Git.

For the measured offering, run from the repository with Python 3.13 and `uv`:

```sh
uv run python -m sugarglider.offline_regions.distribution \
  --region-directory /absolute/path/to/yvelines-ouest-parisien \
  --output-directory /absolute/existing/parent/new-publication \
  --base-url https://victorgabillon.github.io/sugarglider-regions/ \
  --description 'Western Île-de-France, including the Yvelines and western Paris area. Coverage follows rectangular bounds, not administrative borders.'
```

That base URL is a concrete proposed destination, not an existing/approved host.
Any other conforming HTTPS static directory can use the same bytes after preparing
its catalog with the correct base URL. The ZIP is for publishing the static site;
the Android client still downloads its independent component files directly.

For an update, supply `--retain-directory /path/to/previous/region` to keep its
seven immutable files while advertising the new version. Both versions must have
the same region ID and different build IDs. The initial publisher supports one
advertised region and one previous version, with a combined 950 MB limit. Never
replace a published build's bytes or remove a still-supported version without
an explicit retirement decision. An installed version remains usable locally
when its distribution is unavailable.

The standalone verifier can be copied into an otherwise empty distribution
repository and run with Python 3.13, without installing Sugarglider:

```sh
python3 unpack_distribution.py \
  /path/to/sugarglider-regions-static.zip /new/site-directory REVIEWED_SHA256
```

It checks the expected digest before extraction; only strictly named regular,
uncompressed files are allowed. It rejects traversal, symlinks, duplicates,
missing attribution/catalog or incomplete version sets, and oversize content.
The digest must come from the locally reviewed publication report, not an
untrusted field downloaded alongside the ZIP.

## Proposed small-scale host

For initial public project distribution, a separate public repository
`victorgabillon/sugarglider-regions` would contain only deployment source. An
explicit Release asset would hold the reviewed ZIP; a manually dispatched
Actions workflow would verify it and publish the static directory to GitHub
Pages. The inactive template is under `deploy/regions/github-pages`. Creating
that repository, publishing its data release and enabling Pages are the concrete
USER_ACTION_REQUIRED hosting decision; they have not happened.

This keeps generated data out of application and distribution Git history, and
lets physical acceptance proceed without prematurely merging the dependent app
milestones. No application/routing server, new account, custom domain or paid
service is required by the proposed setup. An existing approved static object
host is also suitable if it meets the same HTTP contract.

Official limits checked on 2026-09-12: Pages permits public repositories on GitHub
Free, a site at most 1 GB, a ten-minute deployment and a soft 100 GB monthly
bandwidth limit; rate limits can still apply. At 188.4 MB, about 500 complete
installs would approach that bandwidth allowance, before retries or other reads.
This is an initial project distribution option, not unlimited production capacity.
Pages cannot host a site primarily facilitating commercial transactions or
commercial SaaS; that use or higher volume needs an appropriate static host.
[GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).

Release assets can each be under 2 GiB, with up to 1,000 assets and no stated
aggregate release-size/bandwidth limit. Releases serve here as the publication
archive store. Their redirecting, flat asset endpoints are not asserted compatible
with the app's strict component-directory/CORS transport.
[GitHub release limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

The template uses the documented Pages artifact/deployment workflow, with
preparation before deployment, a `github-pages` environment and Pages/OIDC write
permissions only for deployment. Action revisions are pinned to the verified
current major tags. No workflow in the application repository is activated.
[GitHub custom Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

## Required static HTTP contract

- Exact public HTTPS paths; no authentication, cookies, signed query strings,
  redirect chains, mutable `latest` paths or secret-bearing URLs.
- Successful downloads return 200 and the stored bytes. Set Content-Length to
  the exact file size when provided. Do not dynamically compress or transform
  files, especially the already gzip-compressed POI/nature indexes.
- Web components permit credential-free CORS GET from
  `https://appassets.androidplatform.net` (or public `*`). Expose Content-Length
  and Content-Encoding for diagnostics where the host supports it. The browser
  verifies actual sizes/hashes even when an optional header is not exposed.
- Serve JSON as JSON, PMTiles and routing tar as binary, and gzip indexes as
  `application/gzip` or binary, without `Content-Encoding: gzip`.
- Preserve the directory layout and attribution. Native archives are downloaded
  directly to native storage; maps/indexes go directly to shared web OPFS storage.
  No whole-region ZIP is downloaded by the app or copied across those stores.

After publication, independently verify all deployed bytes against the prepared
report and check CORS/redirect/encoding behavior from the actual bundled origin.
Only then replace the app catalog's null URL with the reviewed immutable manifest
URL, rebuild APK/AAB, and perform fresh Fairphone installation through Download.
Retain exact timing, storage, checksum, activation, map, native routing, Auto Tour,
restart, backend-isolated use, cancellation and removal/reinstall evidence.
Publication or a successful Actions job alone does not satisfy these gates.

## Data attribution

The landing page and README explicitly attribute OpenStreetMap contributors and
link the ODbL 1.0 for the distributed regional databases. The manifest preserves
source identity and build transformations; no unrecorded source date/URL or
completeness is invented. Existing map attribution remains visible in the app.
This follows the official requirement to credit OSM and identify the data license,
and the database guidance to include attribution/license information with the
distribution. [OpenStreetMap copyright](https://www.openstreetmap.org/copyright),
[OSMF attribution guidelines](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines).

## Validation

Unit fixtures use tiny local OSM geometry and synthetic map/routing containers,
with no Docker, network or external services. They check deterministic packaging,
exact copied and extracted bytes, immutable previous-version retention, HTML
escaping, attribution, complete hash reports, corrupt input/digest rejection,
existing output preservation and unsafe archive rejection before extraction.
Real Yvelines packaging/verification remains separately measured below; these
host checks do not claim physical routing or public HTTP acceptance.

Current validation: `make check` passes **1,049 tests / 16 existing integration
tests deselected**, Ruff and strict mypy pass (249 source files). No new skip or
xfail was introduced. The inactive workflow parses successfully; its sole manual
trigger, preparation dependency, read/write permission split and five full action
revision pins were checked. No remote workflow run or deployment is claimed.

The real Yvelines preparation at `/tmp/sugarglider-pr42-static-publication`
produces a **188,374,659-byte** ZIP, SHA-256
`40990c600c0b7bf934522daef1c92d7db44d0ab890077e1224084a6244476a9f`.
All seven regional files total 188,368,868 bytes. The standalone deployment
verifier successfully extracts the reviewed archive, and all eleven site files
match the prepared bytes. `report.json` records each file's size/hash. The real
source components and their copied regional directory both passed the complete
PR39 validator. No remote HTTP or physical acceptance is inferred from this.
