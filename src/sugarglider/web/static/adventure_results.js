import { safeAdventureLink } from "./adventure_proposal.js";
import { strongWoodlandPreference } from "./adventure_assessment.js";

const statuses = { reached: "Checked approach reached", dropped: "Not included in this route", unresolved_location: "Location unresolved",
  ambiguous_location: "Location is ambiguous", outside_coverage: "Outside the installed region", access_restricted: "Mapped access is restricted",
  identity_conflict: "The suggested identity conflicts with the mapped place",
  non_potable: "Mapped as non-potable; not included",
  no_mapped_approach: "No mapped approach found", researched_coordinate_unverified: "Online suggestion; location remains locally unverified",
  exact_anchor_satisfied_place_arrival_unverified: "Required route constraint met; landmark arrival unverified" };
const reasons = { omitted_for_distance: "The attempted detour exceeded the distance constraints.", route_infeasible: "The attempted route could not reach this place.",
  search_budget_exhausted: "The bounded search finished before this place could be included.", not_selected_for_this_candidate: "Another combination was retained for this route.",
  higher_priority_request_limit: "Higher-priority points used the available stop capacity." };
const percent = value => Number.isFinite(value) ? `${Math.round(value * 100)}%` : "Unknown";
const metres = value => Number.isFinite(value) ? `${Math.round(value)} m` : "Unknown";

export function createAdventureResults({ root, candidatesRoot, onManual, onShowMap, onShowStories = () => {} }) {
  const element = id => root.querySelector(`#adventure-${id}`), stories = element("stories");
  let displayed = null, selectedId = null;
  const storyElements = new Map();
  element("return-manual").addEventListener("click", onManual);
  element("stories-open").addEventListener("click", () => { stories.hidden = !stories.hidden; });
  function paragraph(parent, text, tag = "p") {
    const node = root.ownerDocument.createElement(tag); node.textContent = text; parent.append(node); return node;
  }
  function render(output, candidate) {
    root.hidden = !output;
    if (!output) { displayed = null; selectedId = null; stories.replaceChildren(); storyElements.clear(); return; }
    const round = output.chosen;
    const tradeoffs = adventureTradeoffLabels(round);
    element("result-title").textContent = round.proposal.name;
    const distinct = round.result.search_diagnostics.details.local_planning.adventure_search?.distinct_candidate_ids;
    const eligible = round.result.candidates.filter(candidate => candidate.diagnostics.within_tolerance && (!distinct || distinct.includes(candidate.id))).length;
    element("result-summary").textContent = `${round.result.candidates.length} checked route option${round.result.candidates.length === 1 ? "" : "s"}; ${eligible} geometrically distinct and within your distance tolerance (target: ${round.request.candidate_count}). ${output.refinement_improved ? "The extra suggestion round improved measured preferences." : output.refinement_error ? "The extra model request could not finish; the first valid routes were kept." : "The best available measured results were retained."}`;
    element("result-limitations").textContent = (eligible < round.request.candidate_count
      ? "The bounded search found fewer suitable options than requested. Additional suggestions did not yield distinct, feasible routes within the search limit. " : "") + forestAdventureLimitation(round) + "Stories are AI text with source labels. Mapped locations and route arrival do not establish current access or historical accuracy. Asphalt, exact retracing and technical difficulty remain unknown.";
    for (const button of candidatesRoot.querySelectorAll("[data-candidate-id]")) {
      button.querySelectorAll(".adventure-card-summary").forEach(node => node.remove());
      const assessment = round.assessment.assessments.find(value => value.candidate_id === button.dataset.candidateId);
      if (!assessment) continue;
      const summary = root.ownerDocument.createElement("span"); summary.className = "adventure-card-summary";
      const variant = (tradeoffs.has(button.dataset.candidateId) ? `${tradeoffs.get(button.dataset.candidateId)} · ` : "")
        + (distinct && !distinct.includes(button.dataset.candidateId) ? "Comparison variant · " : "");
      summary.textContent = `${variant}Checked places: ${new Set(assessment.places.filter(place => place.status === "reached").map(place => place.canonical_id)).size} · Woodland ${percent(assessment.nature?.woodland)} · Urban ${percent(assessment.nature?.urban)} · Unknown landcover ${percent(assessment.nature?.unknown_landcover)} · D+ ${metres(assessment.elevation?.ascent_m)} / D− ${metres(assessment.elevation?.descent_m)}`;
      button.append(summary);
    }
    if (displayed === output && selectedId === candidate?.id) return;
    displayed = output; selectedId = candidate?.id ?? null;
    stories.replaceChildren(); storyElements.clear();
    const assessment = round.assessment.assessments.find(value => value.candidate_id === candidate?.id);
    if (!assessment) return;
    const unavailable = assessment.wishes.filter(wish => wish.status === "unavailable");
    if (unavailable.length) paragraph(stories, `Preferences that remain unknown: ${unavailable.map(wish => wish.metric.replaceAll("_", " ")).join(", ")}.`);
    const reached = assessment.places.filter(place => place.status === "reached");
    const linked = reached.filter(place => round.grounding.places.some(record => record.id === place.id && record.anecdote && record.story_status === "source_linked_ai_text"));
    paragraph(stories, `${reached.length} reached places; ${linked.length} with source-linked AI anecdotes. No historical claim has been independently verified.`);
    const ordered = [...round.grounding.places].sort((a, b) => Number(reached.some(place => place.id === b.id)) - Number(reached.some(place => place.id === a.id)));
    for (const place of ordered) {
      const outcome = assessment.places.find(value => value.id === place.id);
      const article = root.ownerDocument.createElement("article"); article.className = "adventure-story"; article.tabIndex = -1;
      stories.append(article); storyElements.set(place.id, article);
      paragraph(article, place.local_name ?? place.location.name, "h3");
      if (place.local_name && place.local_name !== place.location.name) paragraph(article, `The AI called this place “${place.location.name}”. The local map names it “${place.local_name}”.`);
      paragraph(article, statuses[outcome?.status] ?? "Not included in this route", "strong");
      if (reasons[outcome?.reason]) paragraph(article, reasons[outcome.reason]);
      paragraph(article, place.reason);
      if (place.anecdote) paragraph(article, place.anecdote);
      paragraph(article, place.story_status === "source_linked_ai_text"
        ? "AI story linked to an observed research source. Its historical claims have not been independently verified."
        : "Unverified AI text. No matching source citation was available.");
      paragraph(article, place.access_status === "public" ? "Public access is mapped; opening and current conditions remain unverified."
        : place.access_status === "unknown" ? "Access is unknown. Check locally before visiting." : "Mapped access is restricted; this place is not selected.");
      if (["drinking_water", "fountain", "water_tap"].includes(place.local_category) || place.local_potability === "non_potable") {
        paragraph(article, place.local_potability === "verified" ? "Mapped as drinking water. Current quality and operation must be checked locally."
          : place.local_potability === "non_potable" ? "Mapped as non-potable. This is not a drinking-water stop."
          : "Potability is unknown. Mapped water does not establish drinking-water quality or operation.");
      }
      const list = root.ownerDocument.createElement("ul"); article.append(list);
      for (const source of place.sources) {
        const href = safeAdventureLink(source.url); if (!href) continue;
        const item = root.ownerDocument.createElement("li"), link = root.ownerDocument.createElement("a");
        link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer"; link.textContent = source.title;
        item.append(link, root.ownerDocument.createTextNode(source.retrieved ? source.provenance === "research_source" ? " — returned by hosted research; claim support unverified" : " — cited during model research; claim support unverified" : " — link supplied by AI; unverified")); list.append(item);
      }
      const coordinate = place.semantic_coordinate ?? place.proposed_coordinate;
      if (coordinate) {
        const button = root.ownerDocument.createElement("button"); button.type = "button"; button.className = "text-button";
        button.textContent = "Show this location on map"; button.addEventListener("click", () => onShowMap(coordinate)); article.append(button);
      }
    }
    const details = root.ownerDocument.createElement("details"); stories.append(details);
    paragraph(details, "Planning details", "summary");
    const elapsed = output.model_calls.reduce((total, call) => total + (call.elapsed_ms ?? 0), 0);
    paragraph(details, `ChatGPT requests: ${output.model_calls.length}. Measured response time: ${(elapsed / 1000).toFixed(1)} s. Offline route calls: ${output.routing_diagnostics.budget.total_used}/${output.routing_diagnostics.budget.total_limit}.`);
    if (output.timings) paragraph(details, `Total planning: ${(output.timings.total_ms / 1000).toFixed(1)} s · Local grounding: ${(output.timings.grounding_ms / 1000).toFixed(2)} s · Native routing: ${(output.timings.native_routing_ms / 1000).toFixed(2)} s · Nature: ${(output.timings.nature_ms / 1000).toFixed(2)} s · Elevation: ${(output.timings.elevation_ms / 1000).toFixed(2)} s.`);
    for (const call of output.model_calls) if (call.research_enabled !== undefined) paragraph(details, `${call.phase}: online research ${call.research_enabled ? "enabled" : "deferred or disabled"}; observed source URLs ${call.observed_source_count ?? "unknown"}. This is provenance, not independent claim verification.`);
    for (const call of output.model_calls) if (call.timings) paragraph(details, `${call.phase}: first response ${call.timings.response_headers_ms === null ? "unknown" : `${(call.timings.response_headers_ms / 1000).toFixed(1)} s`}; observed research span ${call.timings.research_span_ms === null ? "unknown" : `${(call.timings.research_span_ms / 1000).toFixed(1)} s`}.`);
    const search = round.result.search_diagnostics.details.local_planning.adventure_search;
    if (search) paragraph(details, `Search: ${search.evaluated_sequences} proposed sequences evaluated, ${search.validated_drafts} valid routed paths, ${search.diversity_omitted} similar lines omitted, ${search.within_tolerance_count}/${search.requested_count} returned within tolerance; ${search.distinct_route_count} geometry families and ${search.comparison_variant_count} retained comparison variants. Coordinate-segment sharing is a geometry proxy, not edge repetition or corridor equivalence. ${search.budget_finished ? "The local search budget finished." : "No more useful proposals remained."}`);
    paragraph(details, "Routes meeting your distance tolerance come first. The distance comparison route is retained and leads options in the same tolerance class because exact path repetition and backtracking are unavailable. Other options contain checked suggested places.");
    if (strongWoodlandPreference(round.proposal.wishes)) paragraph(details, "Your strong woodland preference guides exploration and selection using local mapped landcover. Among valid routes within tolerance, more mapped woodland can outweigh a modest loop-shape penalty; degenerate and severe out-and-back loops cannot earn preference from forest coverage. A useful landmark detour may remain as a comparison variant without counting as another distinct loop. Unknown landcover never counts as woodland.");
  }
  function showPlace(id) {
    const article = storyElements.get(id); if (!article) return;
    stories.hidden = false; onShowStories(); article.focus({ preventScroll: true }); article.scrollIntoView({ block: "nearest" });
  }
  return Object.freeze({ render, showPlace });
}

// Describe measured differences only. These display labels never change public
// roles/ranks, route identity, source requests, selection, stories or GPX.
export function adventureTradeoffLabels(round) {
  const labels = new Map();
  if (!strongWoodlandPreference(round.proposal.wishes)) return labels;
  const eligible = new Set(round.result.candidates.filter(candidate => candidate.diagnostics.within_tolerance).map(candidate => candidate.id));
  const pool = round.assessment.assessments.filter(item => eligible.has(item.candidate_id)
    && !item.loop_geometry?.degenerate && !item.loop_geometry?.severe_out_and_back);
  const measured = pool.filter(item => Number.isFinite(item.nature?.woodland)).sort((a, b) => b.nature.woodland - a.nature.woodland
    || (a.candidate_id < b.candidate_id ? -1 : a.candidate_id > b.candidate_id ? 1 : 0));
  const forest = measured[0];
  if (!forest || measured.length < 2 || forest.nature.woodland - measured.at(-1).nature.woodland < 0.05) return labels;
  labels.set(forest.candidate_id, forest.nature.woodland >= 0.5 ? "Forest-focused" : "Most mapped woodland found");
  const visits = item => new Set(item.places.filter(place => place.status === "reached").map(place => place.canonical_id)).size;
  const historical = item => new Set(item.places.filter(place => place.status === "reached"
    && ["castle", "ruins", "archaeological_site"].includes(place.local_category)).map(place => place.canonical_id)).size;
  const highlights = [...pool].sort((a, b) => historical(b) - historical(a) || visits(b) - visits(a)
    || (a.candidate_id < b.candidate_id ? -1 : a.candidate_id > b.candidate_id ? 1 : 0))[0];
  if (highlights && (historical(highlights) > historical(forest) || visits(highlights) > visits(forest))) labels.set(highlights.candidate_id,
    historical(highlights) > historical(forest) ? "Historical highlights" : "More checked places");
  return labels;
}

export function forestAdventureLimitation(round) {
  const wish = round.proposal.wishes.find(wish => wish.metric === "woodland" && !["avoid", "minimize"].includes(wish.goal));
  if (!wish) return "";
  const eligible = new Set(round.result.candidates.filter(candidate => candidate.diagnostics.within_tolerance).map(candidate => candidate.id));
  const candidates = round.assessment.assessments.filter(item => eligible.has(item.candidate_id));
  const useful = candidates.filter(item => !item.loop_geometry?.degenerate && !item.loop_geometry?.severe_out_and_back);
  if (candidates.length && !useful.length) return "No reasonably shaped route within tolerance established the forest preference. Required places may force retracing. ";
  const values = useful.map(item => item.nature?.woodland).filter(Number.isFinite);
  if (!values.length) return "Woodland coverage remains unknown for routes within tolerance. The forest preference has not been established. ";
  const best = Math.max(...values) * 100, threshold = wish.value ?? 50;
  return best < threshold ? `No route within tolerance reached ${threshold}% mapped woodland${wish.value === null ? " (predominantly woodland)" : " as requested"}; the best found was ${best.toFixed(1)}%. Unknown landcover is not counted as forest. ` : "";
}
