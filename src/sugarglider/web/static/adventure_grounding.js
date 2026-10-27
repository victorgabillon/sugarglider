// Bounded queries on the existing leased Places session; no index upload or URL fetch.
import { normalizeLocationText } from "./location_search.js";
import { haversineDistance } from "./local_plan_geometry.js";
import { deepFreeze } from "./local_candidate_evaluator.js";
import { safeAdventureLink } from "./adventure_proposal.js";
const position = point => [point.lon, point.lat];
const center = point => ({ lat: point.lat, lon: point.lon });
const distance = (a, b) => haversineDistance(position(a), position(b));
const covered = (point, bounds) => point?.lat !== null && Number.isFinite(point?.lat) && Number.isFinite(point?.lon)
  && point.lon >= bounds[0] && point.lat >= bounds[1] && point.lon <= bounds[2] && point.lat <= bounds[3];
const usable = feature => feature && !["private", "restricted"].includes(feature.access_status) && feature.potability !== "non_potable";
const categoryMatches = (suggestion, actual) => suggestion === "historical"
  ? ["castle", "ruins", "archaeological_site", "tourism_attraction"].includes(actual)
  : suggestion === "viewpoint" ? ["viewpoint", "observation_tower"].includes(actual)
    : suggestion === "water" ? ["drinking_water", "fountain", "water_tap"].includes(actual) : true;

// A small public-map context gives research stable names/identities, without
// uploading an index, routing geometry, approaches, tags or private features.
export const ADVENTURE_CONTEXT_PLACE_LIMIT = 24;
export async function nearbyAdventurePlaceContext({ session, reference, center, signal }) {
  if (!center || !covered(center, reference.bounds)) return [];
  const current = reply => {
    if (signal?.aborted) throw new DOMException("Adventure cancelled.", "AbortError");
    if (!session.identity || reply && !reply.identity
      || [session.identity, reply?.identity].filter(Boolean).some(identity => identity.region_id !== reference.region_id || identity.build_id !== reference.build_id)) {
      throw new Error("The selected region changed while checking nearby places.");
    }
  };
  current();
  const reply = await session.queryPois({ center: { lat: center.lat, lon: center.lon }, radius_m: 30_000, limit: 64, requested_ids: [] });
  current(reply);
  const priority = feature => ["castle", "ruins", "archaeological_site", "tourism_attraction"].includes(feature.category) ? 0 : feature.group === "scenic" ? 1 : 2;
  return deepFreeze(reply.features.filter(feature => usable(feature) && covered(feature.coordinate, reference.bounds)
    && feature.approach_candidates.some(approach => !["private", "restricted"].includes(approach.access) && covered(approach.coordinate, reference.bounds)
      && distance(approach.coordinate, feature.coordinate) <= 1000))
    .sort((a, b) => priority(a) - priority(b) || distance(center, a.coordinate) - distance(center, b.coordinate) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
    .slice(0, ADVENTURE_CONTEXT_PLACE_LIMIT).map(feature => ({ osm_id: feature.id,
      location: { name: feature.display_name.slice(0, 120), lat: feature.coordinate.lat, lon: feature.coordinate.lon },
      category: feature.category, access: feature.access_status, potability: feature.potability })));
}

// Both endpoints use this same review boundary. A model coordinate never
// disambiguates duplicate local names or becomes a verified place by itself.
export async function resolveAdventureEndpoint(location, { session, reference, signal, selected = null, fixed = null }) {
  if (signal?.aborted) throw new DOMException("Adventure cancelled.", "AbortError");
  if (session.identity.region_id !== reference.region_id || session.identity.build_id !== reference.build_id) throw new Error("The selected region changed while checking endpoints.");
  const result = (status, extra = {}) => {
    const value = { status, coordinate: null, proposed_coordinate: location, matches: [], ...extra };
    if (fixed && location && !value.coordinate && status === "unresolved"
      && normalizeLocationText(location.name) === normalizeLocationText(fixed.name ?? "")) {
      return deepFreeze({ ...value, status: "resolved", coordinate: fixed, evidence: "explicit_selection" });
    }
    if (fixed && location && (value.coordinate ? distance(fixed, value.coordinate) > 1
      : normalizeLocationText(location.name) !== normalizeLocationText(fixed.name ?? ""))) {
      return deepFreeze({ ...value, status: "conflict", described_status: status, fixed_coordinate: fixed });
    }
    return deepFreeze(value);
  };
  if (!location) return fixed ? result("resolved", { coordinate: fixed, evidence: "explicit_selection" }) : result("missing");
  // Selected results come only from an explicit local/IGN result button. Model
  // coordinates never disambiguate names or acquire geocoder provenance.
  if (selected) return result(covered(selected, reference.bounds) ? "resolved" : "outside_coverage", {
    coordinate: { name: selected.name, lat: selected.lat, lon: selected.lon },
    evidence: selected.source === "online" ? "selected_ign_result" : "selected_local_result" });
  let matches = [];
  if (location.name.trim().length >= 3) {
    const response = await session.searchPlaceNames(location.name);
    if (signal?.aborted) throw new DOMException("Adventure cancelled.", "AbortError");
    if (response.identity.region_id !== reference.region_id || response.identity.build_id !== reference.build_id) throw new Error("The selected region changed while checking endpoints.");
    matches = response.results.filter(row => normalizeLocationText(row.name) === normalizeLocationText(location.name));
  }
  if (matches.length > 1) return result("ambiguous", { matches });
  if (matches.length === 1) {
    const found = matches[0];
    if (location.lat !== null && distance(found, location) > 1000) return result("ambiguous", { matches });
    return result(covered(found, reference.bounds) ? "resolved" : "outside_coverage", {
      coordinate: { lat: found.lat, lon: found.lon, name: found.name }, evidence: "unique_exact_local_name" });
  }
  if (!Number.isFinite(location.lat) || !Number.isFinite(location.lon)) return result("unresolved");
  return result(covered(location, reference.bounds) ? "resolved" : "outside_coverage", {
    coordinate: { ...location }, evidence: "model_coordinate_unverified" });
}

export function adventureEndpointFailure(resolution, kind) {
  const messages = {
    missing: kind === "start" ? "Where would you like to start? Describe a starting place or choose Start on the map."
      : "Where would you like to finish? Describe a destination or choose End on the map.",
    unresolved: "The named place {place} was not found in the selected region. Search with IGN or review the place on the map.",
    ambiguous: "Several locations match {place}. Choose the intended place before routing.",
    outside_coverage: "{place} is outside the selected offline region. Choose or install a region covering this place before generating the route.",
    conflict: "The described place {place} conflicts with your selected {endpoint}. Your selected point is kept. Review the description or explicitly release that point before trying again.",
  };
  return { code: resolution.status === "missing" ? `adventure_${kind}_required` : `adventure_endpoint_${resolution.status}`,
    message: messages[resolution.status], parameters: { place: resolution.coordinate?.name || resolution.proposed_coordinate?.name || "", endpoint: kind }, resolution };
}

// The service appends this known tracking parameter to cited links. Keep every
// meaningful path/query distinction when matching proposal links to citations.
function citationIdentity(value) {
  const safe = safeAdventureLink(value);
  if (!safe) return null;
  const url = new URL(safe);
  const tracking = url.searchParams.getAll("utm_source");
  if (tracking.length === 1 && tracking[0] === "openai") url.searchParams.delete("utm_source");
  return url.href;
}

export async function groundAdventurePlaces(proposal, { session, reference, start, citations = [], researched = false, signal } = {}) {
  const identity = session.identity;
  const current = response => {
    if (signal?.aborted) throw new DOMException("Adventure cancelled.", "AbortError");
    if (identity.build_id !== reference.build_id || identity.region_id !== reference.region_id
      || response && (response.identity.build_id !== reference.build_id || response.identity.region_id !== reference.region_id)) throw new Error("The selected region changed while checking places.");
  };
  current();
  const bounds = identity.bounds;

  const results = [];
  for (const place of proposal.places) {
    current();
    const proposed = place.location.lat === null ? null : place.location;
    const base = { ...place, proposed_coordinate: proposed, semantic_coordinate: null, routing_coordinate: null,
      local_id: null, local_name: null, local_category: null, local_potability: null, match_method: null, approach: null, access_status: "unknown", status: "unresolved_location",
      ...adventureStoryEvidence(place, citations, researched) };
    if (proposed && !covered(proposed, bounds)) { results.push({ ...base, status: "outside_coverage" }); continue; }
    let feature = null, method = null, ambiguous = false;
    if (place.osm_id) {
      const reply = await session.queryPois({ center: center(proposed ?? start), radius_m: 25, limit: 1, requested_ids: [place.osm_id] }); current(reply);
      feature = reply.requested.find(row => row.id === place.osm_id)?.feature ?? null;
      if (feature) method = "osm_identity";
    }
    if (!feature && place.location.name.trim().length >= 3) {
      const named = await session.searchPlaceNames(place.location.name); current(named);
      const exact = named.results.filter(row => normalizeLocationText(row.name) === normalizeLocationText(place.location.name));
      if (exact.length > 1) ambiguous = true;
      if (exact.length === 1) {
        const reply = await session.queryPois({ center: center(exact[0]), radius_m: 25, limit: 64, requested_ids: [] }); current(reply);
        const matches = reply.features.filter(item => normalizeLocationText(item.display_name) === normalizeLocationText(place.location.name)
          && distance(item.coordinate, exact[0]) < 1);
        if (matches.length === 1) { [feature] = matches; method = "exact_local_name"; }
        else if (matches.length > 1) ambiguous = true;
      }
    }
    if (!feature && !ambiguous && proposed) {
      const reply = await session.queryPois({ center: center(proposed), radius_m: 25, limit: 64, requested_ids: [] }); current(reply);
      const terms = normalizeLocationText(place.location.name).split(/\s+/u).filter(term => term.length > 2);
      const matches = reply.features.filter(item => terms.length && terms.every(term => normalizeLocationText(item.display_name).includes(term)) && distance(item.coordinate, proposed) <= 25);
      if (matches.length === 1) { [feature] = matches; method = "name_and_proximity"; }
      else if (matches.length > 1) ambiguous = true;
    }
    if (feature && proposed && distance(feature.coordinate, proposed) > 1000) { feature = null; ambiguous = true; }
    if (ambiguous) { results.push({ ...base, status: "ambiguous_location" }); continue; }
    if (!feature) {
      results.push({ ...base, semantic_coordinate: proposed, routing_coordinate: proposed,
        status: proposed && place.confidence === "located" && base.story_status === "source_linked_ai_text" ? "researched_coordinate_unverified" : "unresolved_location" });
      continue;
    }
    if (!covered(feature.coordinate, bounds)) { results.push({ ...base, status: "outside_coverage" }); continue; }
    if (!usable(feature)) { results.push({ ...base, local_id: feature.id, access_status: feature.access_status,
      local_potability: feature.potability, status: feature.potability === "non_potable" ? "non_potable" : "access_restricted" }); continue; }
    if (!categoryMatches(place.category, feature.category)) {
      results.push({ ...base, local_id: feature.id, local_name: feature.display_name, local_category: feature.category,
        semantic_coordinate: feature.coordinate, status: "identity_conflict" }); continue;
    }
    const approaches = feature.approach_candidates.filter(approach => !["private", "restricted"].includes(approach.access)
      && covered(approach.coordinate, bounds) && distance(approach.coordinate, feature.coordinate) <= 1000)
      .sort((a, b) => a.semantic_distance_m - b.semantic_distance_m || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    const approach = approaches[0] ?? null;
    results.push({ ...base, local_id: feature.id, local_name: feature.display_name, local_category: feature.category,
      local_potability: feature.potability, semantic_coordinate: feature.coordinate,
      routing_coordinate: approach?.coordinate ?? null, match_method: method, approach,
      access_status: feature.access_status, status: approach ? "grounded" : "no_mapped_approach" });
  }
  current();
  return deepFreeze({ region_id: reference.region_id, build_id: reference.build_id, places: results });
}

export function adventureStoryEvidence(place, citations = [], researched = false) {
  const links = new Map();
  if (researched) for (const citation of citations) {
    const identity = citationIdentity(citation.url); if (!identity) continue;
    const evidence = citation.evidence === "research_source" ? "research_source" : "response_citation";
    if (!links.has(identity) || evidence === "response_citation") links.set(identity, evidence);
  }
  return { story_status: place.anecdote && place.sources.some(source => links.has(citationIdentity(source.url)))
    ? "source_linked_ai_text" : "unverified_ai_text",
    sources: place.sources.map(({ title, url }) => ({ title, url, retrieved: links.has(citationIdentity(url)),
      provenance: links.get(citationIdentity(url)) ?? "unverified" })) };
}
