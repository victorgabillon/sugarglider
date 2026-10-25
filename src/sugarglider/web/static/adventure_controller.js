import { ADVENTURE_INSTRUCTIONS, ADVENTURE_SCHEMA, parseAdventureProposal, adventureWishCapabilities } from "./adventure_proposal.js";
import { groundAdventurePlaces, resolveAdventureEndpoint } from "./adventure_grounding.js";
import { AdventureIntentError, buildAdventureIntent } from "./adventure_intent.js";
import { assessAdventure, compactAdventureAssessment, compareAdventureAssessments, adventureMeasuredImprovement } from "./adventure_assessment.js";
import { deepFreeze } from "./local_candidate_evaluator.js";

// One visible product operation: one initial model request, at most one revision,
// one local planning session. A failed revision cannot erase a valid first pass.
export function createAdventureController({ model, planner, confirmProposal = null,
  measureElevations = null, onProgress = () => {}, lifecycleTarget = globalThis } = {}) {
  let generation = 0, active = null;
  function cancel() {
    generation++;
    if (active) { active.abort.abort(); model.cancel(); planner.invalidate(); }
  }
  function run({ prompt, modelId, context, research = false, structured = true, refine = true }, signal) {
    if (active) return Promise.reject(new AdventureIntentError("adventure_busy", "The previous adventure is still finishing."));
    if (typeof prompt !== "string" || prompt.trim().length < 3 || prompt.length > 8000
      || typeof modelId !== "string" || !modelId || !context?.reference) {
      return Promise.reject(new AdventureIntentError("adventure_context_required", "Choose an installed region and describe your adventure."));
    }
    if (signal?.aborted) return Promise.reject(cancelled());
    const input = deepFreeze(structuredClone(context)), abort = new AbortController(), owned = ++generation;
    const abortFromCaller = () => cancel();
    signal?.addEventListener("abort", abortFromCaller, { once: true });
    const current = () => {
      if (owned !== generation || abort.signal.aborted) throw cancelled();
    };
    const progress = stage => { current(); onProgress(stage); };
    const calls = [], rounds = [];
    async function infer(payload, phase) {
      current();
      if (calls.length >= 2) throw new Error("Adventure model budget exhausted.");
      const record = { phase, status: "started", usage: null, elapsed_ms: null, error: null };
      calls.push(record);
      try {
        const instructions = structured ? ADVENTURE_INSTRUCTIONS
          : `${ADVENTURE_INSTRUCTIONS}\nReturn one JSON object satisfying this schema. Local validation remains mandatory:\n${JSON.stringify(ADVENTURE_SCHEMA)}`;
        const response = await model.infer({ model: modelId, instructions,
          input: JSON.stringify(payload), research, output_schema: structured ? ADVENTURE_SCHEMA : null }, abort.signal);
        current();
        record.status = "completed"; record.usage = usage(response.usage);
        record.elapsed_ms = Number.isFinite(response.elapsed_ms) && response.elapsed_ms >= 0 ? response.elapsed_ms : null;
        return { proposal: parseAdventureProposal(response.text), response };
      } catch (error) {
        record.status = "failed"; record.error = errorCode(error, "invalid_response");
        throw error;
      }
    }
    const promise = (async () => {
      progress("understanding");
      const first = await infer({ user_request: prompt.trim(), planning_context: {
        start: input.start ?? null, end: input.end ?? null, start_is_fixed: Boolean(input.start), end_is_fixed: Boolean(input.end),
        activity: input.profile ?? input.suggested_profile ?? null, activity_is_fixed: Boolean(input.profile),
        exact_points: (input.hardWaypoints ?? []).map(({ id, name, coordinate }) => ({ id, name, coordinate })),
        region: { region_id: input.reference.region_id, bounds: input.reference.bounds },
        available: { offline_routing: true, mapped_nature: true, exact_repetition: false, native_surface: false, current_access: false } } }, "initial");
      let original = first.proposal;
      if (input.end && original.intent.topology === "loop") throw new AdventureIntentError("adventure_endpoint_review_required", "Your chosen End must be kept. Review it before changing this route to a loop.");
      if (input.profile && original.intent.activity !== input.profile) throw new AdventureIntentError("adventure_activity_review_required", "The proposed activity differs from your selected activity. Review it before routing.");
      const output = await planner.planAdventure(original.intent.activity, async session => {
        current();
        if (session.reference.build_id !== input.reference.build_id || session.reference.region_id !== input.reference.region_id
          || session.reference.pack_id !== input.reference.pack_id) throw cancelled();
        if (!session.data) throw new AdventureIntentError("adventure_places_unavailable", "The selected region's Places data is unavailable.");
        progress("checking_places");
        let startResolution = null, endResolution = null;
        if (!input.start) {
          startResolution = await resolveAdventureEndpoint(original.intent.start, { session: session.data, reference: session.reference, signal: abort.signal });
          current();
          if (!startResolution) throw new AdventureIntentError("adventure_start_required", "Where would you like to start? Describe a more precise place or choose Start on the map.");
          original = deepFreeze({ ...original, intent: { ...original.intent, start: startResolution.coordinate } });
        }
        if (!input.end && original.intent.topology === "point_to_point") {
          endResolution = await resolveAdventureEndpoint(original.intent.end, { session: session.data, reference: session.reference, signal: abort.signal });
          current();
          if (!endResolution) throw new AdventureIntentError("adventure_end_required", "The destination could not be resolved unambiguously in this region. Choose End on the map, then try again.");
          original = deepFreeze({ ...original, intent: { ...original.intent, end: endResolution.coordinate } });
        }
        if ((startResolution || endResolution) && !confirmProposal) throw new AdventureIntentError("adventure_endpoint_review_required", "Review the proposed Start and End before routing.");
        const start = input.start ?? startResolution.coordinate, end = input.end ?? endResolution?.coordinate ?? null;
        const grounded = await groundAdventurePlaces(original, { session: session.data, reference: session.reference,
          start, citations: first.response.citations, researched: first.response.researched, signal: abort.signal });
        current();
        let confirmation = { confirmedMandatoryIds: [] };
        const unsupportedHard = adventureWishCapabilities(original, { nature: true, places: true })
          .filter(wish => wish.importance === "hard" && wish.status === "unavailable");
        if (confirmProposal) {
          progress("reviewing");
          confirmation = await confirmProposal(deepFreeze({ proposal: original, grounding: grounded,
            context: { ...input, start, end }, unsupportedHard, startResolution, endResolution }), abort.signal);
          current();
          if (!confirmation) throw cancelled();
        }
        if (unsupportedHard.length && !confirmation.acceptUnknownHardPreferences) {
          throw new AdventureIntentError("adventure_unsupported_hard_preference", "Some required preferences cannot be verified. Review these limitations before routing.");
        }
        const options = { start, end, hardWaypoints: input.hardWaypoints ?? [],
          endpointSnapPolicy: input.endpointSnapPolicy, seed: input.seed ?? 0, confirmedMandatoryIds: confirmation.confirmedMandatoryIds ?? [] };
        const initialIntent = buildAdventureIntent(original, grounded, options);
        async function searchRound(proposal, grounding, intent) {
          progress("routing");
          const produced = await session.generate(intent.request, intent.targets);
          current();
          progress("comparing");
          let elevations = {};
          if (measureElevations && produced.result.candidates.length) {
            try { elevations = await measureElevations(produced.result.candidates, session.reference, abort.signal); }
            catch (error) { current(); /* Elevation remains unknown; valid routes survive. */ }
          }
          current();
          const assessment = assessAdventure({ proposal: { ...proposal, wishes: original.wishes }, grounding,
            request: produced.request, result: produced.result, bindings: intent.bindings, exclusions: intent.exclusions, elevations });
          const safeIds = new Set(assessment.assessments.filter(item => item.hard_route_constraints_satisfied).map(item => item.candidate_id));
          const result = { ...produced.result, candidates: produced.result.candidates.filter(candidate => safeIds.has(candidate.id)) };
          // Never promote an optional detour when its canonical control is lost.
          const controlId = result.search_diagnostics.details.local_planning.no_poi_control_candidate_id;
          if (!result.candidates.some(candidate => candidate.id === controlId)) result.candidates = [];
          const round = deepFreeze({ proposal, grounding, ...intent, result, assessment, elevations,
            endpoint_resolution: { start: startResolution, end: endResolution } });
          rounds.push(round);
          return round;
        }
        let chosen = await searchRound(original, grounded, initialIntent), refinementError = null, improved = false;
        if (refine) {
          progress("improving");
          try {
            const revision = await infer(revisionInput(original, chosen.assessment, options.confirmedMandatoryIds), "refinement");
            current();
            const mandatory = original.places.filter(place => place.importance === "mandatory");
            if (revision.proposal.places.some(place => place.importance === "mandatory" && !mandatory.some(old => old.id === place.id))) {
              throw new AdventureIntentError("adventure_hard_intent_changed", "The revision introduced an unconfirmed required place.");
            }
            const proposal = deepFreeze({ ...revision.proposal, wishes: original.wishes,
              places: [...mandatory, ...revision.proposal.places.filter(place => !mandatory.some(old => old.id === place.id))] });
            if (proposal.places.length > 20) throw new Error("The revised place set exceeds its limit.");
            progress("checking_places");
            const grounding = await groundAdventurePlaces(proposal, { session: session.data, reference: session.reference,
              start, citations: [...(first.response.citations ?? []), ...(revision.response.citations ?? [])],
              researched: first.response.researched || revision.response.researched, signal: abort.signal });
            current();
            const intent = buildAdventureIntent(proposal, grounding, { ...options,
              hardWaypoints: initialIntent.request.waypoints.filter(point => point.constraint_strength === "exact"), fixed: initialIntent.request });
            const revised = await searchRound(proposal, grounding, intent);
            const best = round => round.assessment.assessments.filter(item => round.result.candidates.some(candidate => candidate.id === item.candidate_id))
              .sort(compareAdventureAssessments)[0];
            const before = best(chosen), after = best(revised);
            improved = Boolean(after && (!before || adventureMeasuredImprovement(before, after)));
            if (improved) chosen = revised;
          } catch (error) {
            current();
            refinementError = errorCode(error, "invalid_revision");
          }
        }
        current();
        if (!chosen.result.candidates.length) throw new AdventureIntentError("adventure_no_candidates", "No valid route was found for these requirements and checked places. Your existing route is unchanged.");
        progress("ready");
        return deepFreeze({ selected_round: rounds.indexOf(chosen), rounds, chosen, refinement_improved: improved,
          refinement_error: refinementError, model_calls: calls, routing_diagnostics: session.diagnostics() });
      }, abort.signal);
      current();
      return output;
    })().finally(() => { signal?.removeEventListener("abort", abortFromCaller); if (active?.generation === owned) active = null; });
    active = { generation: owned, abort, promise };
    return promise;
  }
  lifecycleTarget?.addEventListener?.("pagehide", cancel);
  return Object.freeze({ run, cancel });
}

function cancelled() { return new DOMException("Adventure cancelled.", "AbortError"); }
function errorCode(error, fallback) {
  return typeof error?.code === "string" && /^[a-z_]{1,80}$/.test(error.code) ? error.code : fallback;
}
function revisionInput(proposal, assessment, mandatoryIds) {
  const measurements = structuredClone(compactAdventureAssessment(assessment));
  measurements.candidates = measurements.candidates.slice(0, 3);
  const payload = { original_strategy: { name: proposal.name, intent: proposal.intent, wishes: proposal.wishes,
    places: proposal.places.map(({ id, location, osm_id, wikidata_id, category, importance, priority }) =>
      ({ id, location, osm_id, wikidata_id, category, importance, priority })) },
    confirmed_mandatory_ids: mandatoryIds, measurements,
    omitted_measurement_count: assessment.assessments.length - measurements.candidates.length,
    instruction: "Revise optional places only. Keep the original wishes and confirmed requirements. This is the final model call." };
  // Stay below the native input boundary even for maximum-length place IDs.
  // Whole candidate summaries are omitted; JSON and individual facts are intact.
  while (new TextEncoder().encode(JSON.stringify(payload)).byteLength > 32000 && measurements.candidates.length > 1) {
    measurements.candidates.pop(); payload.omitted_measurement_count++;
  }
  if (new TextEncoder().encode(JSON.stringify(payload)).byteLength > 32000) throw new Error("The bounded refinement summary is too large.");
  return payload;
}
function usage(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return Object.fromEntries(["input_tokens", "output_tokens", "total_tokens"].filter(key => Number.isSafeInteger(value[key]) && value[key] >= 0)
    .map(key => [key, value[key]]));
}
