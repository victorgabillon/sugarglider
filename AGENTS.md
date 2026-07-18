# Repository instructions

- Use Python 3.13, `uv`, full annotations, and strict mypy typing.
- Format and lint with Ruff; run `make check` before completing work.
- Unit tests must not depend on Docker, the network, map data, or external services.
- Keep GraphHopper as an external process behind the typed routing adapter.
- Domain code must not import FastAPI.
- GPX export must contain one track and one segment, never a GPX route.
- GraphHopper's total route distance is authoritative; normalize geometry-edge
  distances to that total before calculating metrics.
- Route analysis must be deterministic, and missing path details must remain
  visibly unknown rather than being guessed.
- Fixed generation must preserve required-point order. Optimized-loop generation
  may reorder only non-start mandatory points, must retain original indices, and
  must never silently drop or replace a required point.
- Optimized-loop ordering must keep the first point fixed and use bounded,
  deterministic heuristics rather than exact exponential TSP.
- Generation must be deterministic for a fixed graph, seed, request, and settings;
  every search must enforce a strict full-route evaluation budget.
- Low-overlap generation must run after standard generation, preserve its exact
  routing-point sequence, and account alternative-leg requests in a separate strict
  cached budget.
- Alternative-leg assembly must compose only continuous GraphHopper geometry and
  snapped endpoints, and must keep a bounded deterministic beam with low-overlap,
  low-backtracking, progress, and all-primary-path representatives.
- Never use Euclidean or straight-line route fallback: all candidate and exported
  geometry must come from the routing backend.
- Target distance remains the primary generation objective; PR3's fixed score must
  keep tolerance status ahead of secondary route-quality metrics.
- Immediate backtracking and total repetition are distinct metrics; incomplete
  edge-ID coverage must remain visible, and dead-end POIs may force retracing.
- Low-overlap scoring uses exact repeated edge IDs. It does not infer overlap between
  nearby parallel corridors and does not promise a repetition-free route.
- A refined route may be recommended ahead of its standard source only when it
  lowers repetition without increasing immediate backtracking.
- GPX files contain no route-analysis extensions.
- Generated GPX remains exactly one track and one segment, never a GPX route.
- The browser frontend must use the backend visualization projection rather than
  duplicate repetition, backtracking, routing, or scoring semantics in JavaScript.
- Browser GPX inspection is local-only. Preserve track-segment breaks and never
  invent straight connections between separate segments.
- Selected-candidate GPX export must serialize the already returned `RouteResult`;
  it must not rerun generation or routing.
- Map attribution must remain visible. Do not bulk-download, prefetch, or cache map
  tiles, and do not add offline map behavior.
- Nature data must remain local and derived from the configured OSM PBF; never add a
  runtime Overpass or other hosted GIS dependency.
- Nature analysis must reuse normalized routed geometry edges and must never invent
  or modify route geometry.
- Woodland, open-natural, agriculture, water-crossing, urban, and unknown nature
  metrics must partition the authoritative route distance. Park/protected and
  near-water metrics remain independent overlays.
- Missing or uncovered nature data must remain visibly unknown, never guessed as
  urban or natural.
- Nature preference must never outrank target-distance tolerance or natural-loop
  validity, and PR5's repetition/backtracking promotion gate remains authoritative.
- Nature indexes are generated data and must never be committed. GPX output remains
  free of nature-analysis extensions.
- Loop geometry must use the shared local metric projection and normalized routed
  edges; GraphHopper distance remains authoritative for shares and compactness.
- Loop-geometry metrics and penalties must remain explainable and separate from
  PR3 `CandidateScore.total`; missing analysis remains visibly unknown.
- Loop-geometry preference defaults off and must preserve PR8 proposal ordering,
  GraphHopper accounting, route-evaluation counts, signatures, and recommendation.
- Prefer must complete that exact legacy control lane under the unchanged base
  budget before using its separate bounded geometry-exploration allowance.
- Balanced optional points must be sampled only from one GraphHopper round-trip
  proposal geometry cached by the control lane. Never add a proposal call for the
  balanced lane; account its derived sequences and complete evaluations separately.
- Temporary low-overlap beam states must never run Shapely loop-geometry or nature
  analysis. Only complete routed candidates may receive those enrichments.
- Loop geometry ranks below tolerance, outside-distance pressure, immediate
  backtracking, and repetition; it ranks before nature and cannot bypass the PR5
  natural-improvement gate.
- `assets/brand` is the canonical editable artwork source. Runtime files under
  `src/sugarglider/web/static/brand` must remain byte-identical synchronized copies.
- Never recolor, rotate, stretch, tightly crop, or hand-edit divergent copies of
  Sugarglider artwork, and never add a remote brand-image dependency.
- The Sugarglider map pin is for required POIs and the route start only. Generated
  optional points and imported GPX waypoints must keep distinct marker languages.
- Required marker names come from request JSON and remain attached through editing,
  reordering, optimized-order display, dragging, copying, and candidate inspection.
- Required marker numbers represent current visit order. DOM markers must remain
  draggable and keyboard focusable, with the painted pin tip aligned to coordinates.
- Required-point text labels must remain a collision-aware MapLibre symbol layer;
  do not replace them with permanently overlapping HTML labels.
- Frontend required-point selection must stay synchronized across marker, label,
  popup, and POI editor without changing coordinates or invalidating routes by
  selection alone.
- Never commit generated GPX files or browser validation screenshots.
- Popularity signals remain future work.
- Never commit PBF map data, GraphHopper caches, secrets, or generated GPX files.
