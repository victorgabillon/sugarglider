# Complete V2 source notices and exact evidence

This change prepares proposed notices and technical gates. It grants no right to
publish a regional build. The retained genuine schema-2 IGN request remains
historical evidence for its original notice basis and is not regenerated here.

## Source assurance

The retained GeoPackage SHA-256 is
`46536607dd51665fd2a8b0f2912084a5d95680f4f0f9a31873248d85fcebc199`.
Its 27,358 feature attributes and normalized polygon geometries match Daylight's
published `low.shp` / `low.dbf` objects retrieved on 23 October 2026. Original
Yvelines logs record the Protomaps mirror download and subsequent cache reuse.
Protomaps' historical introduction, commit
`16777e4dfae36993d54e8bca2a14075af1fbda11`, explicitly identifies a mirror of
the dataset in Daylight's 11 October 2023 announcement, which names WorldCover
2020. This corroborates the documented 2020 lineage beyond a generic current
README. It does not recover the original ESA raster inventory, processing receipt
or a hash-bound historical cache-to-map consumption receipt. The notice states
this assurance limit and proposes the upstream 2020 credit for publisher review.
It does not assert independently verified WorldCover v100 raster inputs.

## One packaged inventory

`offline_regions/notice_registry.json` owns ancillary facts, fixed links, retained
support-input hashes, full data/software/font notices and database reading help.
`scripts/sync_data_notices.py` produces the browser module;
`scripts/sync_data_notices.py --check` verifies exact agreement without writing.
Tests compare full packaged vendor notices and the service-worker fingerprints.

Installed-region notices recognize the exact map descriptor, independently of
private/public regional identity. Unknown map payloads remain unknown. Existing
IGN/Copernicus terrain recognition and IGN's seventeen archive editions remain
separate. A source inventory does not confer publication authority. The general
source dialog explicitly describes its retained V2 scope and the existing public
V1 offer; it never fabricates a V2 download URL or infers a saved/imported route's
source. Map controls, selected-route/participant GPX export and the footer expose
the dialog. Opening it requires no fetch, routing, sampling or storage operation.
Official links activate only on user navigation. All notice DOM uses textContent.
GPX writers and output schemas are unchanged.

## Explicit new evidence version

Legacy IGN evidence **2** has basis **1**, with core IGN/OSM notices only. New
evidence **3** requires basis **2** and `supplementary_notices` schema **1**. Mixed
versions, extra/missing fields, duplicate JSON keys, unknown sources, incomplete
document lists, changed map identities and altered hashes fail closed. The
supplementary schema records:

- the exact code-owned registry's canonical SHA-256;
- the exact UTF-8 `SOURCE_NOTICES.txt` SHA-256;
- the exact map descriptor and ordered nine source IDs;
- thirteen ordered full notice-document identities (role, canonical UTF-8 bytes,
  SHA-256); and
- an explicit `lineage_review`, initially `pending`.

`propose_supplementary_notices()` returns only the pending inventory. It creates
no regional evidence, public identity or approval. The publisher must review the
documented assurance limit, layered rights, offer, GPX scope and final wording.
The accepted disposition is a publisher declaration, not a program-generated legal
opinion or a substitute for the independently pinned approval. A pending inventory
cannot pass approval. A new source/edition requires a reviewed registry revision.

After final notice review, a separate future `ign-request` operation may receive
`--supplementary-notices PATH` to construct a fresh schema-3 unsigned request.
It must reverify original records and use a new output path. The frozen request
must never be overwritten or reused as approval for this expanded basis. This
mission did not invoke that operation against real data.

Digest order: private manifest + original core records + supplementary inventory
→ canonical basis digest → public elevation metadata digest → regional build ID
→ evidence digest → independent human approval digest. The registry contains no
public ID or basis digest; `SOURCE_NOTICES.txt` contains its registry digest but
the registry contains no notice-file digest. There is no hash cycle. Changing
wording, links, source identity, document text or review disposition requires new
evidence and a newly computed public identity. Approval schema 1 remains exact:
an old evidence/build pin cannot authorize new schema-3 facts.

## Packaging and host boundary

Public schema-3 packaging adds exactly `SOURCE_NOTICES.txt` at the distribution
root, repeats its exact text in README and escaped HTML, and exposes every complete
component download. Unpack and catalog preflight verify the exact file, README and
HTML renderings against independently approved evidence. Missing, changed, oversized
or shadow-path notices fail before extraction. Legacy evidence cannot authorize
the new file or append expanded notices to its canonical README/index. Existing regional path/file budgets, confinement, checksums and
approval gates remain enforced; no generated database bytes change for a notice
update. The legacy copied `--private` verifier remains usable without the new
registry. Public v3 verification requires the pinned application package, registry
and Python dependencies; copying this one script alone is insufficient.

The separate hosting PR must preserve the exact V1 root catalog, privacy page and
all immutable V1 paths while assembling approved V2 files under `/v2/`. The current
host workflow replaces the entire Pages site from one archive and has no v3
approval inputs. This change does not update that workflow or dispatch deployment.

## Review dependency

The implementation is one commit above the verified local PR101+102 integration
tree `dedd6fb5e31496712e3e86c5e20b074df1622915`. Both existing PRs are unmerged
drafts on main. Keep this commit isolated until a suitable base containing both
changes exists; then apply it and review a clean draft diff. Do not merge either
draft or publish a PR containing their combined implementation accidentally.
