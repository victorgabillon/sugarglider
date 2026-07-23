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
- POI indexes must remain local, deterministic derivatives of the configured OSM
  PBF; runtime code must query the startup-loaded STRtree and never parse the PBF or
  call a hosted discovery service.
- Scenic, verified-water, unknown-potability, and explicitly non-potable classes
  must remain distinct. Private and non-potable features are indexed but hidden by
  default, and mapped water never implies current quality or operation.
- POI discovery is display-only. Selection and filters must never mutate mandatory
  points, generation, ranking, route analysis, route geometry, or GPX output.
- Generated POI indexes under `data/pois` must never be committed.
- Auto Tour must retain and expose its best no-POI control; POI reward must never
  override target-tolerance, backtracking, repetition, loop-geometry, crossing, or
  hard-point gates.
- Auto Tour skeletons and exported lines must use only GraphHopper-routed geometry;
  ellipse and POI coordinates are proposals, never straight-line route fallback.
- Auto Tour POIs must come only from the startup-loaded local index. Private and
  non-potable features are excluded from normal tour search, and only verified
  drinking water uses the blue mascot water pin.
- Auto Tour isochrone, round-trip, skeleton, POI, repair, alternative-leg, and total
  budgets must remain strict, deterministic, cached, and public in diagnostics.
- Temporary insertion and low-overlap beam states must use structural analysis only;
  expensive nature and loop-geometry enrichment belongs only on complete candidates.
- Auto Tour GPX export remains a clean single track/segment with no POI, nature,
  route-analysis, or Auto Tour extensions. Selected approaches are standard ordered
  GPX waypoints; dropped POIs are never exported.
- A selected POI must have a meaningful approach and the final routed geometry must
  reach it within the server-controlled strict arrival tolerance. Semantic-centroid
  proximity is never proof of arrival; every other considered POI is dropped with
  one explicit reason.
- POI index format 2 stores at most eight deterministic meaningful approaches per
  feature. Private, access=no, restricted, and locked approaches are excluded;
  missing or old indexes must fail safely without disabling routing or health.
- Imported requested places resolve by stable OSM ID, then exact normalized name,
  then a strict 25 m graph target. User approach overrides must remain within the
  server-controlled 1,000 m semantic bound and normal snap validation.
- POI excursion analysis must keep raw repetition visible. The default first 200 m
  of total repeated distance per excursion is penalty-free; excess `x` has penalty
  `x + x² / 400`, and a shared excursion is charged only once.
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
- Runtime planning must not contain compatibility adapters or import the removed
  `generation` and `tours` packages.
- Every planning request owns exactly one planning search context. Only its cached
  routing gateway may reserve typed route-call budget or call the routing backend.
- Cache diagnostics must satisfy lookup = hit + miss, entry = successful + failed,
  and backend call = miss; pre-backend budget rejection is counted separately.
- Mode searches produce shared immutable candidate drafts. Shared evaluation creates
  unranked public candidates, and the shared portfolio alone assigns roles and ranks.
- Auto Tour temporary controls, beams, insertions, approaches, and repairs use
  structural analysis only. Retained routed paths receive expensive final enrichment
  exactly once through the shared candidate evaluator.
- Auto Tour algorithm diagnostics must never reconstruct route calls or cache facts;
  phase usage and cache snapshots from the request context are authoritative.
- Public routing profiles are exactly `hike`, `trail_run`, `city_bike`, `gravel_bike`,
  `mountain_bike`, and `road_bike`; do not accept aliases or expose backend profile
  names through public models.
- The immutable routing-profile registry is the sole owner of public/backend mapping,
  activity kind, path details, snap preventions, capabilities, and public labels.
- Every production planning and POI-approach route call must pass the selected public
  profile explicitly. Route caches, candidate signatures, results, and GPX metadata
  must preserve profile identity and must never fall back to hike.
- Packaged readiness requires all six GraphHopper profiles. Profile/config/model/version
  changes must invalidate the graph cache through the import fingerprint.
- Activity-specific analysis and scoring must respect path-detail coverage. Missing
  surface, access, network, smoothness, or technicality data remains visibly unknown.
- Routing profiles are preferences over mapped OSM data, never safety, legality,
  opening, current-condition, or rideability guarantees. Elevation remains disabled.
- Start, end, and explicitly exact waypoints remain hard constraints. Approach and
  best-effort constraints must use the shared profile-aware resolver and may not cause
  an unexplained total-plan rejection.
- Public stop outcomes are reached, approximated, or dropped. An approximation must
  preserve semantic and routed coordinates, report the actual remaining distance,
  and must never be labeled reached.
- Flexible and balanced distance tolerance is soft; only an explicit balanced
  maximum is hard. Strict tolerance and its required explicit maximum remain hard.
- Every successful compromise must be immutable, deterministic, profile-aware, and
  visible in the canonical result and browser. Exact failure must never trigger an
  automatic weakened retry.
- Reached and approximated GPX waypoints use their validated routed coordinates with
  truthful names. Dropped stops are omitted; the GPX remains one track and segment.
- Every published candidate carries centrally built traversal direction and ordered
  deliberate anchors. Incidental discovered POIs and private reversal shape hints must
  never become traversal anchors.
- Route reversal must reroute through the shared cached gateway and typed reverse
  budget. Never reverse returned geometry in the browser or call the raw backend from
  direction modules.
- Reversal preserves exact constraints, profile, and canonical intent while resolving
  soft stops and rebuilding analysis, scoring, compromises, roles, ranks, and GPX order.
  Reversing twice need not reproduce byte-identical geometry.
- Spur-closure refinement must use the shared request context and typed repair budget,
  preserve exact and deliberate anchors, reject inbound-corridor reuse by routed edge
  identity, reconstruct a complete routed path, retain originals, and fail nonfatally.
