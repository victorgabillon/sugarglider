// Local input convenience only. Canonical serialization owns all routing semantics.
import { WAYPOINT_PRODUCT_DEFAULTS, waypointPlanRequestSnapshot } from "./state.js";
import { PUBLIC_PROFILE_METADATA } from "./public_profile_metadata.js";

export const ITINERARY_MAX_BYTES = 65_536;
export const ITINERARY_NAME_LENGTH = 120;
export const ITINERARY_REASON_LENGTH = 400;
const topFields = ["format", "version", "name", "activity", "topology", "target_distance_km", "tolerance_km", "start", "end", "stops", "order"];
function requireValue(ok, message) { if (!ok) throw new Error(message); }
function fields(value, required, optional, label) {
  requireValue(value !== null && typeof value === "object" && !Array.isArray(value), `${label} must be an object.`);
  for (const key of required) requireValue(Object.hasOwn(value, key), `${label}.${key} is required.`);
  for (const key of Object.keys(value)) requireValue(required.includes(key) || optional.includes(key), `${label} contains an unknown field: ${key}.`);
}
function text(value, maximum, label) {
  requireValue(typeof value === "string" && value.trim().length > 0 && value.length <= maximum,
    `${label} must be nonempty text of at most ${maximum} characters.`);
  requireValue(!/[<>\u0000-\u001f\u007f]/u.test(value), `${label} must be plain text without HTML or control characters.`);
  return value.trim();
}
function number(value, minimum, maximum, label) {
  requireValue(typeof value === "number" && Number.isFinite(value) && value >= minimum && value <= maximum,
    `${label} must be a finite number from ${minimum} to ${maximum}.`);
  return value;
}
function location(value, label, stop = false) {
  fields(value, ["name", "lat", "lon"], stop ? ["reason"] : [], label);
  const point = { name: text(value.name, ITINERARY_NAME_LENGTH, `${label}.name`),
    lat: number(value.lat, -90, 90, `${label}.lat`), lon: number(value.lon, -180, 180, `${label}.lon`) };
  if (Object.hasOwn(value, "reason")) point.reason = text(value.reason, ITINERARY_REASON_LENGTH, `${label}.reason`);
  return point;
}
// Bound nesting before JSON.parse, ignoring braces inside strings. No recursive walk
// over untrusted input, prose extraction, repair, geocoding or remote dependencies.
function boundDepth(source) {
  let depth = 0, quoted = false, escaped = false;
  for (const character of source) {
    if (quoted) {
      if (escaped) escaped = false;
      else if (character === "\\") escaped = true;
      else if (character === '"') quoted = false;
    } else if (character === '"') quoted = true;
    else if (character === "{" || character === "[") {
      depth += 1; requireValue(depth <= 4, "Itinerary JSON is too deeply nested (maximum depth 4).");
    } else if (character === "}" || character === "]") depth -= 1;
  }
}
export function parseItineraryDraft(raw, { maximumStops = 30 } = {}) {
  requireValue(typeof raw === "string" && raw.length <= ITINERARY_MAX_BYTES
    && new TextEncoder().encode(raw).byteLength <= ITINERARY_MAX_BYTES,
    "Itinerary JSON must be at most 64 KiB.");
  let source = raw.trim();
  if (source.startsWith("```")) {
    const fence = /^```json\s*\r?\n([\s\S]*?)\r?\n```$/iu.exec(source);
    requireValue(Boolean(fence), "Use one surrounding JSON code fence, with no commentary outside it.");
    source = fence[1].trim();
  }
  requireValue(source.startsWith("{"), "Paste one JSON object, or one surrounding JSON code fence; remove any commentary.");
  boundDepth(source);
  let value;
  try { value = JSON.parse(source); }
  catch { throw new Error("Invalid JSON. Check commas, quotes and brackets; the itinerary was not changed."); }
  fields(value, topFields, [], "Itinerary");
  requireValue(value.format === "sugarglider_itinerary_draft", "format must be sugarglider_itinerary_draft.");
  requireValue(value.version === 1, "Only itinerary draft version 1 is supported.");
  requireValue(typeof value.activity === "string" && Object.hasOwn(PUBLIC_PROFILE_METADATA, value.activity), "activity must be an existing Sugarglider routing profile.");
  requireValue(["loop", "point_to_point"].includes(value.topology), "topology must be loop or point_to_point.");
  requireValue(["as_given", "optimize"].includes(value.order), "order must be as_given or optimize.");
  const start = location(value.start, "Start");
  let end = null;
  if (value.topology === "loop") requireValue(value.end === null, "A loop must have end: null.");
  else {
    end = location(value.end, "End");
    requireValue(start.lat !== end.lat || start.lon !== end.lon, "Start and End must have distinct coordinates.");
  }
  requireValue(Array.isArray(value.stops), "stops must be an array.");
  requireValue(Number.isSafeInteger(maximumStops) && maximumStops >= 0, "The application's stop limit is unavailable.");
  requireValue(value.stops.length <= maximumStops, `This itinerary supports at most ${maximumStops} stops; none were discarded.`);
  requireValue(value.topology !== "loop" || value.stops.length > 0, "A waypoint loop needs at least one stop.");
  const stops = value.stops.map((point, index) => location(point, `Stop ${index + 1}`, true));
  const coordinateKey = point => `${point.lat},${point.lon}`;
  const seen = new Set([coordinateKey(start), ...(end ? [coordinateKey(end)] : [])]);
  stops.forEach((point, index) => {
    requireValue(!seen.has(coordinateKey(point)), `Stop ${index + 1} duplicates another stop or endpoint.`);
    seen.add(coordinateKey(point));
  });
  return { format: value.format, version: 1, name: text(value.name, ITINERARY_NAME_LENGTH, "name"),
    activity: value.activity, topology: value.topology,
    target_distance_km: number(value.target_distance_km, 1, 200, "target_distance_km"),
    tolerance_km: number(value.tolerance_km, 0.1, 10, "tolerance_km"),
    start, end, stops, order: value.order };
}
export function itineraryDraftToCanonical(draft) {
  // Use the same fresh product defaults and serializer as the manual editor.
  // Whitelist coordinates; presentation reasons never enter this planner snapshot.
  const coordinate = ({ name, lat, lon }) => ({ name, lat, lon });
  return waypointPlanRequestSnapshot({
    planningMode: "waypoint_route", routingProfile: draft.activity,
    waypointEndpoints: { start: coordinate(draft.start), end: draft.end ? coordinate(draft.end) : null,
      routeTopology: draft.topology },
    options: { ...WAYPOINT_PRODUCT_DEFAULTS, name: draft.name,
      targetDistanceKm: draft.target_distance_km, toleranceKm: draft.tolerance_km,
      waypointOrder: draft.order === "as_given" ? "fixed" : "optimize" },
    points: draft.stops.map((point, index) => ({ ...coordinate(point),
      id: `itinerary-stop-${index + 1}`, constraintStrength: "exact" })),
  });
}
export function buildItineraryPrompt(settings = {}) {
  const defaults = WAYPOINT_PRODUCT_DEFAULTS;
  const coordinate = point => point ? { name: point.name?.trim() || "Chosen location", lat: point.lat, lon: point.lon } : null;
  const topology = settings.topology ?? "loop";
  const template = { format: "sugarglider_itinerary_draft", version: 1,
    name: "Name this itinerary", activity: settings.activity ?? "trail_run", topology,
    target_distance_km: settings.target_distance_km ?? defaults.targetDistanceKm,
    tolerance_km: settings.tolerance_km ?? defaults.toleranceKm,
    start: coordinate(settings.start), end: topology === "loop" ? null : coordinate(settings.end),
    stops: [{ name: "Place name", lat: null, lon: null, reason: "Short reason to visit" }], order: "optimize" };
  return `You are selecting interesting places for a route-planning application.
Choose scenic, cultural or tourist-friendly places near the supplied Start, appropriate for the activity and approximate distance. Do not invent road/path geometry: Sugarglider will route between the places.
Only include places whose coordinates you can identify confidently. Omit uncertain places. Do not claim verified opening times, current access or conditions.
Return ONLY one JSON object matching Sugarglider itinerary-draft version 1, without commentary. Give each stop a short plain-text reason. No HTML.
All fields in the template are required. Replace the example stop with real resolved places (name, numeric lat, numeric lon, optional reason). Names: 1–120 characters; reasons: 1–400 characters. Latitude: -90 to 90; longitude: -180 to 180. No unknown fields.
Allowed activities: ${Object.keys(PUBLIC_PROFILE_METADATA).join(", ")}.
Topology: loop (end must be null), or point_to_point (distinct resolved End required). Order: as_given or optimize. Target: 1–200 km; tolerance: 0.1–10 km. A loop needs at least one stop, at most 30.
${!settings.start ? "Start is missing: ask me for a named resolved Start before proposing an importable itinerary. Never guess my location." : "Preserve the supplied Start."}
${topology === "point_to_point" && !settings.end ? "End is missing: ask me for a named resolved End before proposing an importable itinerary." : ""}
Null coordinates in the template are placeholders, never valid locations. Return only resolved numeric coordinates when the inputs are complete.
Template:
${JSON.stringify(template, null, 2)}`;
}
