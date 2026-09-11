# PR40 — Local Auto Tour and regional places/nature

Status: implementation and automated checks pass. Physical acceptance has not
passed; this milestone must not merge until it does. Production Android integration
remains PR41, and the normal regional catalog/download flow remains PR42.

## Regional data and storage

The shared web runtime reads the unchanged PR39 distribution manifest, POI gzip
JSON index v2/classifier 1 and nature gzip JSON index v1. There is no PBF parsing,
Overpass, hosted POI discovery, native GIS implementation or runtime data conversion.
The existing static files remain the distribution/storage representation.

The temporary debug panel installs just places and nature from an explicitly
entered regional manifest URL. It uses the existing map installer's HTTPS/private
debug-origin URL policy: no credentials, query strings, fragments or redirects;
downloads omit credentials/referrers and bypass caches. Fixed paths, exact byte
sizes, SHA-256, manifest content identity, source/bounds, component identities,
schema/toolchain versions and document structures are checked before activation.

Origin-private storage layout:

```text
sugarglider-region-components/<region_id>/
  active.json                         # {build_id}, written last
  <build_id>/
    manifest.json
    pois/index.json.gz
    nature/index.json.gz
```

The active pointer is switched only after both components have downloaded, passed
validation and closed their writes. Web Locks serialize cooperating tab/worker
mutations. Interrupted/staged versions cannot become active; cancellation and
failed updates preserve the previous active version. Removal is explicit. A corrupt
active version with the same build ID requires explicit removal and reinstall;
there is no overwrite of active bytes. Optional old-version cleanup cannot turn a
committed install into a failed result. Missing/failed OPFS remains explicit and
does not disable independent routing.

Maps stay solely in the PR36 shared OPFS random-read store. Routing archives stay
in Android private routing-pack storage. This places/nature store neither copies
nor downloads those larger components. PR42 can coordinate the existing independent
stores without changing the POI/nature representation.

One dedicated module worker owns decompression, validation, indexing and analysis;
the map thread receives bounded results. One loaded region is retained. Requests
carry its build ID, and a changed or failed worker cannot answer an older data
handle with a different index. Region data is selected only when exactly one
installed regional manifest matches the candidate's native routing-pack ID.

The manifest's expected routing archive hash is exposed as provenance. PR40's
existing PR34 native replies carry a pack ID, **not a cryptographic archive
identity**. Device acceptance must verify the installed routing bytes separately;
the production four-component installer/activation gate remains PR42 work.

## Bounds and evidence

- At most eight stored region entries; manifest 32 KiB; each compressed index
  32 MiB and expanded index 128 MiB; 250,000 features and two million nature
  positions. These are explicit local resource limits, not worldwide coverage.
- Immutable bounding-box trees are built once per loaded index. Runtime queries
  never scan/parse the source PBF. POI queries return at most 64 nearby features
  plus at most eight explicitly requested stable OSM IDs.
- POI categories, access, scenic confidence and potability remain distinct. Private,
  restricted, non-potable and unverified hydration features cannot enter ordinary
  tour proposals. Unknown potability never becomes verified drinking water.
- Meaningful approaches come from the stored bounded list. A routed snap must reach
  an approach within the code-controlled 15 m hydration / 25 m scenic tolerance.
  The semantic point is never used as proof of arrival. Every considered/requested
  feature has a reached candidate or one explicit dropped reason. Outcomes are
  attached separately to each candidate; a place visited only by an alternative
  is never reported reached by the recommended no-POI control.
- Imported name/coordinate resolution and user approach overrides are not added by
  this milestone. The debug requested-place input accepts stable OSM IDs only.
  There is no invented approximation when a strict approach fails.

## Nature measurement

Nature analysis uses the shared local equirectangular projection and the actual
Valhalla polyline. As in Python `project_geometry_edges`, raw haversine edge lengths
are normalized to the authoritative route distance before attribution. No route
vertex is added, removed, moved or replaced.

Each routed edge is split at polygon boundaries. Polygon holes, multipolygons,
overlapping areas and the fixed urban → water → woodland → open-natural →
agriculture priority are respected. Uncovered or unclassified fractions remain
unknown. Primary metrics partition route distance; park/protected and near-water
are independent overlays. Near-water uses a 100 m geometric buffer with circular
end caps; the Python/Shapely approximation of circular buffers can differ slightly
on oblique boundary fixtures. Neither is a graph-edge or drinking-water claim.

Scores expose the existing nature weights and neutral base, with a null score
when analysis is unavailable. Four million counted analysis operations per
complete candidate bound spatial querying/intersection work. Exhaustion returns
explicit unavailable analysis and fully unknown primary distance, never a partial
score masquerading as complete. Index topology validation is separately bounded
at twenty million operations. No expensive nature analysis runs on temporary
insertion proposals or failed routes.

## Auto Tour search and recommendation

PR35's seeded, graph-routed control search runs first, preserving its 24-call
ceiling. One request-local cache counts successful and failed calls. A POI lane
can use at most six remaining calls, never increasing the 24-call total. It tries
at most two stored approaches per feature and routes a complete ordered sequence
through the selected approach. Every retained candidate remains profile- and
routing-pack-consistent. Native snaps must occur in returned geometry in order.

Optional nature preference ranks below tolerance and all existing loop-quality
keys. The best no-POI candidate is exposed both by ID and as an immutable control.
POI candidates cannot worsen the control's tolerance status, severe backtracking
indication, degeneracy, crossing count or sampled geometry-quality metrics.

The current Valhalla Mobile wrapper still supplies no exact edge IDs or exact
backtracking. Consequently **POI alternatives cannot be promoted over their
no-POI control**. That missing evidence is explicit; sampled geometric proximity
never populates exact repetition fields. Available POI alternatives may occupy
remaining requested portfolio slots, with meaningful approach/arrival details.
Dropped or unretained places are reported individually. Mapped water does not
guarantee present water quality or operation.

Diagnostics expose control/POI call usage, the effective remaining POI budget,
cache lookup/hit/miss/success/failure counts, region identity, preference status,
nature metrics, POI outcomes and the recommendation gate. Search invalidation
keeps an outstanding native call owned until it drains; a stale initial result
cannot start correction, enrichment or insertion work.

This remains the separate debug Auto Tour surface. Normal Generate, public
canonical planning objects and GPX export are not replaced here. No GPX extensions
or fabricated server `PlanResult` are introduced. The offline shell advances once
from v22 to v23 to include all six new shared modules and the changed UI/core.

## Evidence so far

- Real PR39 Marly manifest/content hashes and both index documents load locally:
  407 POIs and 6,734 nature features. The current host probe's topology validation
  and index construction took 769 ms; this is **not** phone latency evidence.
- Shared browser harness: 20 PR40 scenarios pass, including the Python-generated
  golden nature fixture, strict documents, checksums, install/update/cancel/remove,
  quota/switch failures, control retention, all six profiles, bounded calls,
  deterministic repeat, lifecycle failures, analysis-budget exhaustion and real
  OPFS/module-worker load, analysis and removal.
- Existing PR35: nine browser scenarios pass. Its geometric diversity fake now
  supplies the ordered snapped boundaries required by the strengthened validator.
- Existing PR38: 34 browser scenarios pass.
- Eleven new Python tests pass. The synthetic manifest and unchanged index models
  validate in Python, and nine nature metrics agree with independent Shapely
  analysis. Strict mypy passes across 229 source files.
- `make check`: **PASS**, 991 passed / 16 integration tests deselected, Ruff and
  strict mypy clean.
- `JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
  ANDROID_HOME=/home/pompote/Android/Sdk make android-check`: **PASS**; 136 Android
  unit tests, zero errors/failures/skips; Android lint passes. The initial SDK/JRE
  environment failures were corrected using the installed SDK and JDK 17.
- `uv run --offline --with websockets python /tmp/sugarglider-pr40-browser.py`:
  **187 scenarios across ten harnesses PASS** (PR26/27/32–38/40).
- Fairphone: USB authorized. Physical acceptance pending visible/unlocked app;
  hotspot/radios have not been changed. No device PASS is claimed.
