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
| A. IGN technical readiness | Exact private payload, four HGT and seventeen original archives independently verified. Original derivation receipts/PBF remain missing; historical lineage is not newly re-proven. |
| B. Redistribution rights evidence | Official documents pinned; combined-graph interpretation and final notices require human review. |
| C. Exact-build authorization readiness | Synthetic complete path passes 45 tests. The real unsigned request remains blocked by missing preparation/conversion/graph receipts, prepared rasters and PBF. |
| D. Private V2 distribution engineering | Synthetic failure/restart contracts and the exact real private 210,223,038-byte HTTPS delivery pass. No fresh physical installation performed. |
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

## Final automated and transport results

Implementation commit `c11738ed8253c7d659de36bfdd1d30e52995db72` passed all
four GitHub workflows:

- [Python](https://github.com/victorgabillon/sugarglider/actions/runs/39405282421):
  Ruff format/lint, strict mypy over 299 files, **1,544 tests passed**, 16
  integration tests deliberately deselected, nine existing NumPy deprecation
  warnings. All 45 new IGN cases pass. The separate synthetic HTTPS acceptance
  also passes in CI.
- [Browser](https://github.com/victorgabillon/sugarglider/actions/runs/39405282294):
  retention/GC, elevation interactions, release/source/datum contracts and
  offline-product failures pass. Local Chromium also passes at 360, 390, 420
  and 1280 px, including the new exact synthetic IGN public identity vector.
- [Android](https://github.com/victorgabillon/sugarglider/actions/runs/39405282356):
  Debug/Release unit tests, lint, APK assembly, debug test-APK assembly and
  **Debug/Release APK + ELF 16 KiB checks pass**. The redundant local Android
  build was stopped after this complete CI result, and is not claimed as a
  completed local run. No physical APK installation was performed.
- [Existing social checks](https://github.com/victorgabillon/sugarglider/actions/runs/39405282337)
  pass; no deployment was requested.

The actual CI debug APK was downloaded from artifact `12257030512`, bound to
that exact commit, and independently inspected locally. Archive SHA-256:
`a19d5ac39b4c9a1b52383e18c86238d301a495c4daaa8a9f14362ef6b1aedf41`.
APK: 25,923,517 bytes, SHA-256
`3981e0abe9d72e81ecdddcbf8e8c4ecbbf384987225eeb63b767c412dab70864`.
Android SDK 36 `zipalign -c -P 16 4` passes; all three native ELF LOAD segments
have alignment `0x4000`. The APK's bundled catalog is byte-identical to the
preserved V1 catalog. No private regional/DEM bytes were added to the app.

Fresh private TLS results:

| Run | Result |
| --- | --- |
| Synthetic authorization format | 5 components / 4 HGT / 11 files / 122,693 bytes, exact streamed hashes and explicit CA passed. |
| Synthetic failures and restart | CORS OPTIONS, actual 206 ranges, interrupted response/retry, corruption and missing HGT rejection, wrong catalog ID rejection, restored bytes and fresh server actor all passed. |
| Recovered real private IGN | **11 files / 210,223,038 bytes**, all streamed hashes, explicit-CA TLS and actual PMTiles range passed. Public release preflight rejected missing authorization. |
| Existing published V1 | Original immutable manifest returned 200, schema 1, build `902f951bedd1de527629baa572358aec4c388359ce5435d472639dac61f9bc71`; all six component HEAD requests returned 200 with matching sizes using identity encoding. No V1 payload download/hash re-audit or modification is claimed. |
| Fairphone preservation | All 12 recovered regional files (including the regional manifest) were rehashed directly on the phone after recovery and still match the host copy. No install/update/clear, foreground launch, phone-wide certificate or connectivity change. |

Host evidence is retained durably in `/home/juno/sugarglider-pr101-evidence/`,
including raw licence snapshots, source retrievals, recovered private region,
post-recovery phone hashes, TLS receipts, V1 availability receipt and APK audit.
The local test CA/private key stays in that private directory; it is not a
production or phone-wide trust anchor. Both HTTPS servers and the temporary
DevTools forward have been stopped/removed.

The remaining technical prerequisite for a real authorization request is recovery
of the exact original preparation/conversion/graph-build records, prepared
input rasters and PBF, or a separately identified and independently verified
replacement private build if those records are lost. No source archive download
or green CI result supplies those historical records or the publisher's legal
interpretation and exact-build approval.

## Original IGN archive reacquisition

Following the owner's clarification that earlier work used another computer,
all **17 original official IGN archives** were reacquired into a fresh private
host directory. Every compressed byte size and SHA-256 independently matches
the preserved source ledger: **3,098,550,581 bytes** in total. Interrupted/slow
transfers were retried against the same official URLs and accepted only after
full SHA-256 verification; incomplete transfer bytes were never accepted as
sources. This does not rebuild, replace or authorize the recovered DEM/graph.
The original acquisition timestamps in the immutable ledger remain historical;
the separate new retrieval receipt records today's acquisition.

| Original archive | Verified bytes | Verified SHA-256 |
| --- | ---: | --- |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D002_2020-09-04.7z` | 333,567,478 | `7d2beca8d2d0de8b3e506900b5eb1636f80df9e929e07f683d853ce3b571ca91` |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D027_2022-12-21.7z` | 276,997,777 | `9895dd7d033332ad43d8e22fd65cc3069149907da0e14afa864de23aac9d1a50` |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D028_2019-12-16.7z` | 171,568,476 | `b6635e0b27b96b3ae430425d4e6b143005c6a0439cbaf075f3b4c773f371259f` |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D041_2019-12-16.7z` | 238,645,980 | `833071baff372ca02fe9f0276135fd65057b5b6aa64eb8e0ae0bf76a6b2bd01e` |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D045_2023-01-03.7z` | 369,285,331 | `f3128867a8d2384e0fe7cad4367958fb5c333773323fbbaf3fc781d479f7a33a` |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D060_2020-09-04.7z` | 226,246,156 | `436881d5dd7f963900f7a3f3e689e1833df620f89a9339aed0a39b52b0adbc26` |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D075_2020-07-30.7z` | 13,939,995 | `a159155985eae1c474fdefd49e29256063696285ffd0b4878f8d69754ee983c6` |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D076_2020-10-20.7z` | 238,578,862 | `86f051ab983d64399c443ec426ecc4a98c79b5257774fa73d4c00bf6a1aa5f19` |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D077_2021-03-03.7z` | 226,423,725 | `caf2c2f1fc1de554424eadc6597faf936716ee6cfb3dbe6f93b5880d87505dab` |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D078_2020-07-30.7z` | 90,690,133 | `cdd5637135c86a0779e4eed7b0398b6de1ec25e78e000b94fddc2ee00915ca38` |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D080_2019-07-09.7z` | 227,200,019 | `17e2d4b5b4adaafa980c1897612b0c859e7e0eae39426908c5fb8c42b8e480f7` |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D089_2023-01-03.7z` | 485,461,155 | `7a3659eb2a18bbb290182852e6014a490ae1089ef3899bbf37fa140396a2b3c9` |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D091_2021-03-03.7z` | 65,188,861 | `e63a8ae12fb825b76d0bedf826da1091d9d1b3b5e905e7f7d0d5f0c19b67c552` |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D092_2020-07-30.7z` | 19,125,413 | `868d9b52d4a2b46fec167c8dbda9f43d179d0165a87c369113463fda55f8c1f8` |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D093_2020-07-30.7z` | 23,291,756 | `0a0ea1bc80891b5952a8852ebbe5513d2e1293b375133028d06eabe798000c16` |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D094_2020-07-30.7z` | 23,784,381 | `6e8804cc8e2ac57737c1b2505d8cac7f9615895b9bf5cab2c03e85163394dfe6` |
| `RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D095_2020-07-30.7z` | 68,555,083 | `de662135a000ad91d8f67a3b003fe59c631ccb9099ab6f92cf67de1024fa5260` |

Reacquisition establishes these source identities. It supplies neither the lost
preparation/conversion/build receipts nor legal or operator approval.
