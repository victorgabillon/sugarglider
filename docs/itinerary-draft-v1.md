# Itinerary draft version 1

An external assistant chooses interesting named places; Sugarglider validates,
edits and routes between them. The assistant does not supply route geometry.
This provider-neutral input format converts to the existing canonical
`schema_version: 1`, `kind: waypoint_route` request. Canonical plan JSON remains
the long-term routing contract: Tools → Plan files and storage → Import plan JSON,
and canonical export, keep their existing behavior.

## Workflow and trust boundary

In Plan, choose **Import itinerary**. Paste JSON or choose a JSON file, then
**Review itinerary**. The preview shows Start, numbered stops, reasons, End for
an open route, order, distance and device capability information. Parsing,
previewing, Back and Cancel do not change the current plan or its results.
Only **Import itinerary** replaces the editable plan, clears placement and
Undo/Redo history, selects its first stop, fits the map and invalidates old
results. It does not generate a route. Review the coordinates, edit as needed,
then explicitly Generate.

Coordinates from an external source are unverified. Even confident suggestions
can be wrong; mapped places do not establish current opening, access, conditions,
or activity suitability. An exact unreachable point fails visibly; it is never
silently weakened, replaced or dropped.

Sugarglider contacts no assistant, opens no provider URL and needs no model key,
account, OAuth or billing integration. Inside the dialog, **Create prompt for an
assistant** builds text locally only after a click. Chosen Start coordinates and
route settings can appear in that text. Inspect/edit the visible textarea, then
explicitly **Copy prompt** and decide where to paste it. Creating a prompt does
not copy it or send it anywhere. A missing Start/End is disclosed as missing;
template null coordinates are placeholders, never valid imported locations.

## Exact input shape

All eleven top-level fields are required, with no unknown fields:

| Field | Contract |
| --- | --- |
| `format` | Exactly `sugarglider_itinerary_draft` |
| `version` | Number `1` |
| `name` | Plain text, 1–120 characters |
| `activity` | `hike`, `trail_run`, `city_bike`, `gravel_bike`, `mountain_bike`, `road_bike` |
| `topology` | `loop` or `point_to_point` |
| `target_distance_km` | Finite number, 1–200 |
| `tolerance_km` | Finite number, 0.1–10 |
| `start` | Required resolved location |
| `end` | `null` for loop; distinct resolved location for point-to-point |
| `stops` | Array of resolved stops, at most 30; loop requires at least one |
| `order` | `as_given` or `optimize` |

A resolved location has exactly `name`, `lat`, `lon`. Name is nonempty plain text
of at most 120 characters; latitude is a finite number in [-90, 90], longitude
in [-180, 180]. A stop has those same fields and optional `reason` (nonempty
plain text, at most 400 characters). Numeric strings, unresolved addresses,
HTML, control characters, unknown fields and repeated coordinates (including
endpoint/stop duplication) are rejected. Leading/trailing whitespace in text is
trimmed. Coordinate values are retained exactly.

The parser accepts a raw JSON object or exactly one surrounding Markdown
`json`/`JSON` code fence with line breaks. It rejects commentary outside the
object/fence and multiple nested fences. It does not scrape prose or repair JSON.
Input is bounded to 64 KiB of UTF-8, including fences, and nesting depth 4 before
JSON parsing. File size is checked before reading. Errors stay in the dialog and
are announced. Imported text is rendered with safe DOM/textContent operations.

See [the four-stop Versailles example](../examples/itinerary-drafts/versailles-tourist-loop.json).
Its locations come from the project's Yvelines context and local OSM-derived
index (the Trianon point is a mapped entrance). This is an illustrative suggestion,
not an assurance of access or a prevalidated continuous route.

## Deterministic canonical mapping

The profile is checked against the existing generated public profile metadata,
derived from the Python routing registry. Imported places become ordinary route
points; there is no assistant-specific routing kind.

Start/End keep their names and coordinates. Stop IDs are `itinerary-stop-1`,
`itinerary-stop-2`, etc. Each stop is `exact`, with access radius 500 m,
`maximum_best_effort_distance_m: null` and `approach_override: null`, as emitted
by the existing canonical serializer. `as_given` maps to `fixed`; `optimize` maps
to `optimize`. Distances convert km to metres.

Technical options come from the immutable **WAYPOINT_PRODUCT_DEFAULTS** in
`state.js`, also used by a fresh manual Waypoint Route, through
`waypointPlanRequestSnapshot()`. No active or inactive plan options leak into
conversion:

| Canonical option | Product default |
| --- | --- |
| `candidate_count` | 3 |
| `seed` | 0 |
| `distance_objective.priority` | `flexible` |
| `distance_objective.maximum_m` | `null` (no hard maximum) |
| `preferences.nature` | `off` |
| `preferences.path_selection` | `shortest` |
| `preferences.loop_geometry` | `off` (both topologies) |

Only name, profile, topology, target, tolerance, Start, End, stops and order are
overridden. Defaults are deterministic for a Sugarglider version. Flexible
distance is a soft objective, not a promise to achieve the target.

Reasons become in-memory `itineraryReason` presentation text shown in the detailed
Plan stop editor, never in the compact map ribbon. Moving/reordering retains the
reason; removal and Undo/Redo use the existing point history. Reasons never enter
canonical JSON, requests, ranking, route ordering, GPX or durable storage. A
canonical export/reimport therefore does not preserve reasons.

## Android capability limits

The canonical model/UI allow 30 interior stops. The current experimental local
Waypoint Route accepts at most 14 interior stops (16 points including closure or
End), exact constraints, shortest selection and nature/loop preferences off.
The preview uses the existing local validator and current profile/region
readiness. Excess local stops remain importable up to the canonical limit; a
capability warning explains why generation cannot use them. No point is dropped
and no planner or constraint is silently changed. Local exact interior fidelity
is 300 m; hard endpoint snapping/loop closure tolerance is 25 m. Local route
calls have a strict budget of 16 and maximum distance 200 km. Local Valhalla and
server GraphHopper behavior are explicitly not equivalent. Android routing
itself is unchanged by this input feature.

## Copyable assistant instruction

> Choose interesting scenic, cultural or tourist-friendly places near my supplied
> named Start for my activity and approximate distance. Do not invent route
> geometry. Include only confidently resolved numeric coordinates; omit uncertain
> places. Return only one JSON object shaped exactly like the version 1 example
> above, using `format: sugarglider_itinerary_draft`, with all required fields and
> no unknown fields. Use a short plain-text reason per stop. A loop has `end: null`;
> an open route needs a distinct resolved End. Ask for missing endpoint inputs.
> Do not claim current opening/access verification.

The local prompt helper includes the complete field template, enums, bounds and
chosen settings so it can be copied without including technical routing defaults.

## Coordinate acquisition

Address/place search resolves a location then feeds existing route-point
acquisition, just like map taps, GPS and this draft import; an address is not a
new route point type. Android Share and Open with use the same preview/confirmation
flow described below. Direct provider integration remains outside this format.

## Android Share and Open with

In the Android app, share plain text or a JSON document to Sugarglider, or use
Open with Sugarglider for a granted content:// JSON document. The same dialog
opens with the untrusted text at the input stage. Review itinerary and then
explicitly Import itinerary are required, just as with manual paste; nothing
imports, generates, contacts a provider or follows a shared URL automatically.
Native transport accepts at most 64 KiB UTF-8, reads temporary content grants once,
and stores no draft or URI durably. Cancel preserves the current plan/results.
The version 1 schema and coordinate authority are unchanged.
