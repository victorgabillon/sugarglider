// Bounded queries on the existing leased Places session; no index upload or URL fetch.
import { normalizeLocationText } from "./location_search.js";
import { haversineDistance } from "./local_plan_geometry.js";
import { deepFreeze } from "./local_candidate_evaluator.js";
import { safeAdventureLink } from "./adventure_proposal.js";
const position = point => [point.lon, point.lat];
const distance = (a, b) => haversineDistance(position(a), position(b));
const covered = (point, bounds) => point?.lat !== null && Number.isFinite(point?.lat) && Number.isFinite(point?.lon)
  && point.lon >= bounds[0] && point.lat >= bounds[1] && point.lon <= bounds[2] && point.lat <= bounds[3];
const usable = feature => feature && !["private", "restricted"].includes(feature.access_status) && feature.potability !== "non_potable";

export async function groundAdventurePlaces(proposal, { session, reference, start, citations = [], researched = false, signal } = {}) {
  const identity = session.identity;
  const current = response => {
    if (signal?.aborted) throw new DOMException("Adventure cancelled.", "AbortError");
    if (identity.build_id !== reference.build_id || identity.region_id !== reference.region_id
      || response && (response.identity.build_id !== reference.build_id || response.identity.region_id !== reference.region_id)) throw new Error("The selected region changed while checking places.");
  };
  current();
  const bounds = identity.bounds;
  const citationLinks = new Set(researched ? citations.map(item => safeAdventureLink(item.url)).filter(Boolean) : []);
  const results = [];
  for (const place of proposal.places) {
    current();
    const proposed = place.location.lat === null ? null : place.location;
    const base = { ...place, proposed_coordinate: proposed, semantic_coordinate: null, routing_coordinate: null,
      local_id: null, match_method: null, approach: null, access_status: "unknown", status: "unresolved_location",
      story_status: place.sources.some(source => citationLinks.has(source.url)) ? "source_linked_ai_text" : "unverified_ai_text",
      sources: place.sources.map(source => ({ ...source, retrieved: citationLinks.has(source.url) })) };
    if (proposed && !covered(proposed, bounds)) { results.push({ ...base, status: "outside_coverage" }); continue; }
    let feature = null, method = null, ambiguous = false;
    if (place.osm_id) {
      const reply = await session.queryPois({ center: proposed ?? start, radius_m: 25, limit: 1, requested_ids: [place.osm_id] }); current(reply);
      feature = reply.requested.find(row => row.id === place.osm_id)?.feature ?? null;
      if (feature) method = "osm_identity";
    }
    if (!feature && place.location.name.trim().length >= 3) {
      const named = await session.searchPlaceNames(place.location.name); current(named);
      const exact = named.results.filter(row => normalizeLocationText(row.name) === normalizeLocationText(place.location.name));
      if (exact.length > 1) ambiguous = true;
      if (exact.length === 1) {
        const reply = await session.queryPois({ center: exact[0], radius_m: 25, limit: 64, requested_ids: [] }); current(reply);
        const matches = reply.features.filter(item => normalizeLocationText(item.display_name) === normalizeLocationText(place.location.name)
          && distance(item.coordinate, exact[0]) < 1);
        if (matches.length === 1) { [feature] = matches; method = "exact_local_name"; }
        else if (matches.length > 1) ambiguous = true;
      }
    }
    if (!feature && !ambiguous && proposed) {
      const reply = await session.queryPois({ center: proposed, radius_m: 25, limit: 64, requested_ids: [] }); current(reply);
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
    if (!usable(feature)) { results.push({ ...base, local_id: feature.id, status: "access_restricted" }); continue; }
    const approaches = feature.approach_candidates.filter(approach => !["private", "restricted"].includes(approach.access)
      && covered(approach.coordinate, bounds) && distance(approach.coordinate, feature.coordinate) <= 1000)
      .sort((a, b) => a.semantic_distance_m - b.semantic_distance_m || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    const approach = approaches[0] ?? null;
    results.push({ ...base, local_id: feature.id, semantic_coordinate: feature.coordinate,
      routing_coordinate: approach?.coordinate ?? null, match_method: method, approach,
      access_status: feature.access_status, status: approach ? "grounded" : "no_mapped_approach" });
  }
  current();
  return deepFreeze({ region_id: reference.region_id, build_id: reference.build_id, places: results });
}
