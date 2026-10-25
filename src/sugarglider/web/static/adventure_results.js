import { safeAdventureLink } from "./adventure_proposal.js";

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
    element("result-title").textContent = round.proposal.name;
    element("result-summary").textContent = `${round.result.candidates.length} checked route option${round.result.candidates.length === 1 ? "" : "s"}. ${output.refinement_improved ? "The extra suggestion round improved measured preferences." : output.refinement_error ? "The extra model request could not finish; the first valid routes were kept." : "The best available measured results were retained."}`;
    element("result-limitations").textContent = (round.result.candidates.length < round.request.candidate_count
      ? "The bounded search found fewer suitable options than requested. Additional suggestions did not yield distinct, feasible routes within the search limit. " : "") + "Stories are AI text with source labels. Mapped locations and route arrival do not establish current access or historical accuracy. Asphalt, exact retracing and technical difficulty remain unknown.";
    for (const button of candidatesRoot.querySelectorAll("[data-candidate-id]")) {
      button.querySelectorAll(".adventure-card-summary").forEach(node => node.remove());
      const assessment = round.assessment.assessments.find(value => value.candidate_id === button.dataset.candidateId);
      if (!assessment) continue;
      const summary = root.ownerDocument.createElement("span"); summary.className = "adventure-card-summary";
      summary.textContent = `Checked places: ${new Set(assessment.places.filter(place => place.status === "reached").map(place => place.canonical_id)).size} · Woodland ${percent(assessment.nature?.woodland)} · D+ ${metres(assessment.elevation?.ascent_m)} / D− ${metres(assessment.elevation?.descent_m)}`;
      button.append(summary);
    }
    if (displayed === output && selectedId === candidate?.id) return;
    displayed = output; selectedId = candidate?.id ?? null;
    stories.replaceChildren(); storyElements.clear();
    const assessment = round.assessment.assessments.find(value => value.candidate_id === candidate?.id);
    if (!assessment) return;
    const unavailable = assessment.wishes.filter(wish => wish.status === "unavailable");
    if (unavailable.length) paragraph(stories, `Preferences that remain unknown: ${unavailable.map(wish => wish.metric.replaceAll("_", " ")).join(", ")}.`);
    for (const place of round.grounding.places) {
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
        ? "AI story with a link cited during research. Its historical claims have not been independently verified."
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
        item.append(link, root.ownerDocument.createTextNode(source.retrieved ? " — cited during model research" : " — link supplied by AI; unverified")); list.append(item);
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
    paragraph(details, "Routes meeting your distance tolerance come first. The distance comparison route is retained and leads options in the same tolerance class because exact path repetition and backtracking are unavailable. Other options contain checked suggested places.");
  }
  function showPlace(id) {
    const article = storyElements.get(id); if (!article) return;
    stories.hidden = false; onShowStories(); article.focus({ preventScroll: true }); article.scrollIntoView({ block: "nearest" });
  }
  return Object.freeze({ render, showPlace });
}
