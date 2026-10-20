# IGN V2 distribution readiness — private review

Base: `224752a40fad24fe5b8bb8c5c2c8454c64dfbb9d`. Review date: 2026-10-20.
This change prepares an authorization mechanism and private staging. It grants
no real publication authority. No real region has been marked public, no public
catalog has been replaced, and no Play operation, version increment, signing
change or production installation is part of this work.

## Rights dossier

The official [IGN RGE ALTI dataset](https://www.data.gouv.fr/datasets/rge-alti-r)
identifies IGN as publisher and `lov2` as its licence. It covers the 1 m and 5 m
ground models, describes normal ground heights, heterogeneous inputs and an end
to updates in 2024. A current catalogue modification date is not a source-cell
acquisition date. The delivery names and dates of the seventeen pinned archives
must remain visible; this review does not treat successful acquisition as a grant.

The [French Licence Ouverte 2.0](https://www.etalab.gouv.fr/wp-content/uploads/2017/04/ETALAB-Licence-Ouverte-v2.0.pdf)
permits copying, adaptation, combination and redistribution, including commercial
reuse. Its conditions include identifying the source/grantor and the reused
information's last update, avoiding misleading source/date claims or implied
endorsement, and respecting applicable personal-data rules. The licence describes
the allocation of responsibility and absence of general data-quality guarantees.
These are confirmed terms of the reviewed document, not confirmation that this
particular graph or notice meets every condition. The operator must decide how
archive editions and available source metadata satisfy the date requirement.

The [ODbL 1.0 legal text](https://opendatacommons.org/licenses/odbl/odbl-10.txt)
permits database reuse subject to conditions. Sections 4.2–4.4 govern notices,
public output and derivative-database terms; 4.6 requires a machine-readable
offer of the entire derivative database or the complete alterations/method,
including additional contents, free online. Sections 4.7–4.8 constrain additional
restrictions and preserve recipients' rights. ODbL does not itself clear separate
rights in IGN contents or software. The conservative release proposal is to
offer the complete generated map, routing, POI and nature databases as the exact
regional files under ODbL, with IGN contents identified under Licence Ouverte.
Merely pointing to build code or an upstream PBF would not establish that the
offer contains every alteration and added content.

The [OSMF attribution guidelines](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines)
explain expected map/database/routing-engine credits and accessible licence
information. Proposed staging notices identify OpenStreetMap contributors,
link ODbL and IGN terms, identify terrain changes and IGN69, and offer the entire
derived databases at immutable manifest paths. The existing in-app map and
terrain credits remain necessary; a host README alone does not establish that
every screen meets the guidelines. Review final mobile/desktop placement and
downstream exported metadata before approving the real release.

The [OSMF collective-database guideline](https://osmfoundation.org/wiki/Licence/Community_Guidelines/Collective_Database_Guideline_Guideline)
discusses independence of combined data and includes routing-related examples.
**Human interpretation remains required:** a Valhalla graph with elevation and
grade values attached to OSM edges cannot simply be assumed to be independent
layers. Determine whether that combined graph is a derivative database, whether
the complete graph offer satisfies the applicable source obligation, and whether
its IGN contents and proposed downstream terms are compatible. The separate raw
HGT component does not resolve the graph's status. No code path supplies this
legal conclusion on the publisher's behalf.

The exact downloaded snapshots are recorded in
[`ign-v2-evidence.json`](../offline-regions/legal/ign-v2-evidence.json): five official
documents, original URLs, byte sizes, SHA-256 and retrieval time. Raw snapshots
are retained privately under the host evidence directory, not regional Git data.
The Etalab URL currently redirects to the official data.gouv PDF resource:
`https://static.data.gouv.fr/resources/licence-ouverte-2-0/20260909-072646/etalab-licence-ouverte-v2.0.pdf`.
That PDF is 237,693 bytes, SHA-256
`df600a2fd08b887716612ac57fffbbe10c9e678961064c72214cebb89c90cbb6`.
ODbL's 25,278-byte plain text is
`607680718977f6f6c9607972afd98f208573f19251315ed1362a8589b51beaf5`.
Snapshots establish which bytes are being reviewed. A matching digest is not a
legal opinion; HTML or catalogue changes require a fresh reviewed snapshot.

## Exact-build approval contract

`ign_publication.py` adds a strict source-specific evidence schema, preserving
the original Copernicus schema. The IGN basis includes the **complete private
regional manifest**, all five component descriptors, exact OSM identity/tools,
all pinned original archives, IGN69 derivation, preparation and conversion
digests, graph-build receipt, five legal-document descriptors and complete
notices with source editions. Four exact HGT identities are mandatory.

`ign-request` rehashes originals, preserved decoded ASCII and prepared rasters,
the preparation index, conversion receipt, graph-build receipt, PBF, legal
documents and all regional bytes. It checks the source/IGN69/algorithm/HGT/graph
relationships. It performs no acquisition, DEM conversion or graph rebuild.
Its only output is unsigned evidence; the real region stays byte-identical and
private. Missing retained evidence fails closed.

The public elevation metadata requires an additional
`publication_basis_sha256`. The basis digest is computed **before** the proposed
public manifest, avoiding a circular hash. In-memory preview changes only the
two publication flags, the elevation metadata descriptor and regional build ID;
it preserves IGN69 and all five payloads. An independent human approval then
binds the canonical evidence digest, which includes that proposed public ID.

The operator supplies the approval JSON and its SHA-256 through an independent
trusted channel. Finding a neighbouring approval file does not trust it. The
approval identifies the human, timezone-qualified time, exact-build/DEM-enriched
graph scope and explicit acceptance. Request generation never creates it.
Approved-copy verifies both records and retained originals before creating a
fresh output; failed copies are removed. Package preparation, public archive
unpacking and release-catalog preflight each require that approval and verify
the IGN elevation basis. Copernicus evidence cannot relabel or authorize IGN69.

Android validates the extra IGN publication field only on structurally public
IGN components, preserves the IGN69 height reference, and rechecks installed
payload hashes. JavaScript retains its strict five-component immutable regional
manifest contract. Reader compatibility is not publisher authorization: the
offline reader has no independent human trust channel. Export gates own that
decision. A publication flag or basis hash by itself grants no authority.

All successful authorization fixtures identify themselves as **synthetic only**.
They contain zero-height HGT, toy databases and synthetic licence bytes; they
test engineering bindings, not legal sufficiency or real-data authorization.

## Compatible hosting and rollback

Keep the existing public V1 catalog, URLs and files indefinitely accessible to
existing apps. This PR pins the bundled V1 catalog's exact bytes in a regression:
`009a3ebcdd5d8774b04f58320eca0f92a58adab55ef521fe675d9aa7332ba48c`.
No normal-production catalog replacement is included.

Use a distinct `/v2/` namespace and catalog. Public IGN preparation and export
reject a base without that segment. Example **layout only**, not a deployed URL:

```text
https://REGION_HOST/v2/catalog.json
https://REGION_HOST/v2/regions/REGION_ID/BUILD_ID/manifest.json
https://REGION_HOST/v2/regions/REGION_ID/BUILD_ID/map/...
https://REGION_HOST/v2/regions/REGION_ID/BUILD_ID/routing/...
https://REGION_HOST/v2/regions/REGION_ID/BUILD_ID/pois/...
https://REGION_HOST/v2/regions/REGION_ID/BUILD_ID/nature/...
https://REGION_HOST/v2/regions/REGION_ID/BUILD_ID/elevation/...
```

Before any separately authorized deployment, verify all five components locally
and over HTTPS. Preserve exact bytes and sizes; prohibit redirects, cookies,
credentials and Content-Encoding transformations, including for `.gz` files.
Serve an explicit CORS origin `https://appassets.androidplatform.net`, permit
Range preflight and expose length/range headers; PMTiles ranges must return
206 with the exact Content-Range and original bytes. Keep a stable TLS chain.
Immutable build paths must never be overwritten. Uploading files, switching a
catalog and shipping a coordinated app are separate future operator actions.

Private staging uses the existing loopback-only HTTPS server and test-CA
scripts. When the original host CA is unavailable, create a fresh short-lived
host-only fixture CA; do not add it to global or phone-wide trust. Synthetic
public-format fixtures and real private-format verification are separate runs.
Do not install an APK over any retained Fairphone package with an unverified
signing identity. The staging/debug trust exception must never enter production.

For updates, stage the entire exact build, verify each descriptor and native
copy, then atomically switch the active build. Incomplete, corrupted, cancelled
or wrong-ID installs must leave the previous active version intact. Restart
must reopen and verify committed bytes rather than trust readiness markers.
Retain the previous working V2 build and the existing V1 distribution. Rollback
changes only the V2 catalog/active pointer to a retained compatible build; it
does not mutate immutable payloads, delete regional data, downgrade an unknown
app database or redirect an old V1 URL into V2.

## Reproduction

With retained inputs and reviewed notices, the following creates **unsigned
evidence only**. Every path is private and absolute; substitute actual retained
paths rather than creating replacement receipts under historical hashes.

```sh
uv sync --frozen --group dem
uv run python -m sugarglider.offline_regions.publication_cli ign-request \
  --private-region "$PRIVATE_REGION" --originals "$IGN_ORIGINALS" \
  --prepared "$IGN_PREPARED" --transformation "$IGN_CONVERSION" \
  --graph-build-record "$GRAPH_RECEIPT" --osm-pbf "$OSM_PBF" \
  --legal-directory "$LEGAL_SNAPSHOTS" \
  --legal-evidence offline-regions/legal/ign-v2-evidence.json \
  --notices "$REVIEWED_NOTICES" --evidence "$FRESH_UNSIGNED_REQUEST"
```

There is deliberately no real approval example or ready-to-run real public-copy
command in this handoff. The operator must first review the proposed ID and
notices and supply their own detached approval and independent digest.

Run the synthetic HTTPS acceptance separately from network-free unit tests:

```sh
uv run python tests/unit/pr101_private_https_acceptance.py \
  --output "$FRESH_PRIVATE_ACCEPTANCE_DIRECTORY"
```

It creates its own synthetic fixtures and three-day local CA, binds only
127.0.0.1, checks streamed hashes, CORS, ranges, interruption/retry, corruption,
missing HGT, incorrect catalog identity, recovery and a new server actor after
restart. It stops both servers and never installs a certificate or app.

## Verification and remaining decisions

See the final audit section below for evidence available on this host and final
automated results. Historical PR95/PR98 results, newly recovered byte audits,
fresh synthetic authorization and physical installation are distinct evidence.

| Conclusion | Release gate |
| --- | --- |
| A. IGN technical readiness | Verify recovered exact private bytes and record any missing original derivation inputs separately. |
| B. Redistribution rights evidence | Official documents pinned; combined-graph interpretation and final notices require human review. |
| C. Exact-build authorization readiness | Synthetic complete path tested; actual unsigned request requires every retained source and build record. |
| D. Private V2 distribution engineering | Loopback HTTPS and installation contracts tested; real-data transport results reported separately. |
| E. Public distribution authorization | **Absent.** No real human approval, approved real artifact or deployment. |
| F. Google Play readiness | **Not granted.** Technical APK checks do not settle policy, Data Safety, signing, distribution authority or the retained nonzero UID findings. |

The publisher must decide the graph/database interpretation, adequacy of the
machine-readable offer, source-date wording and final notices; review the exact
unsigned request and proposed identity; provide independently pinned human
approval; and separately authorize hosting/catalog/app release. Existing PR95
strict zero-byte network failures remain failures; offline functionality and
local native zero-traffic results do not erase them.

## Recovered private artifact audit

The host did not retain PR95's original data directory. The connected Fairphone
6 still retained the exact private region in
`io.github.victorgabillon.sugarglider.v2staging`. A read-only `run-as` copy
recovered its regional manifest/map/indices from the Chromium OPFS backing
files and its routing/elevation files from the native store. Only regional
payloads were copied; no route/session data was recovered. No app was launched,
stopped, installed, updated or cleared. A temporary local DevTools forward was
removed after the background WebView did not answer; recovery used file reads.

`verify_region` independently validates the complete recovered copy, all eleven
component files, the PMTiles and Valhalla structures, POI/Nature metadata and
all four decoded HGT payloads. The result is exactly
`a92396de46a6fed5fa1a49fc8c939c39bc6371424aa90c9b71f237878294c7fd`,
**210,223,038 component bytes**, documented **IGN69**, and publication remains
**false**. This is a recovered byte-identical copy, not a DEM or graph rebuild.

| Component file | Bytes | Verified SHA-256 |
| --- | ---: | --- |
| `elevation/manifest.json` | 9,389 | `67fff11e1f8ae2b09792962e28d93ae96aeef2883d3a52635a89fed64f36d969` |
| `elevation/skadi/N48/N48E001.hgt.gz` | 3,597,713 | `a7d55ab92559ace1c64069bdf7669717e2ddd8acfbc9c8b041a770d0461688d3` |
| `elevation/skadi/N48/N48E002.hgt.gz` | 4,248,630 | `d47f7dc9e0947cacd975be249fb73c8c7212f98b9cdb384d9044da87f81ca5e0` |
| `elevation/skadi/N49/N49E001.hgt.gz` | 5,527,281 | `d79a01593f51fa01589242892505b90e3a13479405c864373462d2b094bd7611` |
| `elevation/skadi/N49/N49E002.hgt.gz` | 4,891,056 | `7955eec7df9675fdf2d897d6f581379c87940365353a2505c420ee6565415cb3` |
| `map/manifest.json` | 631 | `ee0f29b2f831afdc60db4a45e50abbf412e6b4e803e4a9347d70821dbd4e63b3` |
| `map/basemap.pmtiles` | 81,570,334 | `a5e2af1ac3785d370c84a5fc0c46e65ba764a2331d4d86b7e2c6b25de52bce3d` |
| `nature/index.json.gz` | 10,634,994 | `abb0819a4f4b02d8ee844aa19de71c1760e0b63a1a9f7bd3410513d82dca7b90` |
| `pois/index.json.gz` | 261,132 | `1ace12b6869ae74f97a673ac9fe6f706cb17a6b7f29b35a9b0dbafd095ea4649` |
| `routing/manifest.json` | 278 | `3d87397c8f997cdb1a4622cd3e3ad52eb3481ff777723da7031ca14e2f71927a` |
| `routing/valhalla_tiles.tar` | 99,481,600 | `d47b022dc2036800bfa5eadc902a90d94de2cff8df32e6377ac9c0ff5fe9fb3d` |

The preserved source identity is `ile-de-france-latest.osm.pbf`, 335,288,680
bytes, SHA-256
`2ac2b0d9c7ca8374af078a6f564c342a08a2634a110c1f18bae1cbd1cda5d849`.
The region records no source URL. The exact PBF itself is not recovered; a
current latest download is not a substitute for that historical hash.

The recovered IGN derivation exactly matches the seventeen-archive committed
ledger, whose SHA-256 is
`7c5ead1c0b224ac88106c35785a36f2c7ce8105cf95f5adce592d54245d8f1b9`.
It binds preparation index
`78a77421a09cf4d97a3b522abcf55c47e371cea814b1ba8f233b27beb36138b7`
and conversion record
`fcf7187c3c3916403fc5cc8e83c65fec33b5ef74d60baa75ede061deda9a71a9`.
Those two original records/prepared grids and the original graph-build receipt
were not present on this host or in the installed region. Their digests are
**recorded references, not newly verified record bytes**. The original computer
may still retain them. Regenerating a receipt cannot establish its historical
identity; a necessary future regeneration must be independently verified and
assigned its actual new identity, preserving this original private build.

Consequently this run does not manufacture a real unsigned authorization
request, proposed public build ID or approval. Recover those exact original
inputs/receipts, or explicitly prepare and verify a new private build with a
new identity, before running the real IGN request path. The strict gate
demonstrates this missing-evidence condition instead of bypassing it.
