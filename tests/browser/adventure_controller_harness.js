// Synthetic completed model answers and native replies; normal regional data,
// local search, shared gateway, publication worker and GPX exporter are used.
import { createAdventureController } from "../../src/sugarglider/web/static/adventure_controller.js";
import { assessAdventure, compactAdventureAssessment, adventureMeasuredImprovement } from "../../src/sugarglider/web/static/adventure_assessment.js";
import { parseAdventureProposal } from "../../src/sugarglider/web/static/adventure_proposal.js";
import { validateLocalWaypointRouteRequest } from "../../src/sugarglider/web/static/local_waypoint_route.js";
import { buildAdventureIntent, requestedAdventureAlternatives } from "../../src/sugarglider/web/static/adventure_intent.js";
import { createLocalRegionData } from "../../src/sugarglider/web/static/local_region_data.js";
import { exportCanonicalCandidate } from "../../src/sugarglider/web/static/local_gpx_export.js";
import { syntheticAdventure } from "./adventure_proposal_harness.js";
import { rig } from "./adventure_routing_harness.js";
import { state } from "../../src/sugarglider/web/static/state.js";

const assert = (ok, message) => { if (!ok) throw Error(message); };
const equal = (a, b, message) => assert(JSON.stringify(a) === JSON.stringify(b), message);
const point = (lat, lon, name = null) => ({ lat, lon, name });
export const outputs = [];

export async function setup({ failure = null, mutateRevision = null, confirmProposal = null, change = undefined } = {}) {
  const r = await rig({ change });
  const f = await (await fetch("/tests/fixtures/pr40_regional_data.json")).json();
  const data = createLocalRegionData(f.manifest, { pois: f.pois, nature: f.nature });
  r.region.getRegionData = async () => data;
  const proposal = structuredClone(syntheticAdventure);
  proposal.intent = { ...proposal.intent, topology: "point_to_point", start: point(.005, .005, "Start"),
    end: point(.015, .013, "End"), target_distance_m: 2200, tolerance_m: 700, order: "fixed" };
  proposal.wishes = [{ metric: "interesting_stops", goal: "maximize", value: null, importance: "high" },
    { metric: "asphalt", goal: "avoid", value: null, importance: "low" }];
  proposal.places[0].location = { ...data.queryPois({ center: point(.01, .005), radius_m: 25, requested_ids: ["node/1"] }).requested[0].feature.coordinate, name: "Fixture 1" };
  const revision = structuredClone(proposal);
  revision.places.push({ ...structuredClone(proposal.places[0]), id: "water", osm_id: "node/2", category: "water",
    location: point(.01, .007, "Fixture 2"), priority: 9 });
  revision.places.push({ ...structuredClone(proposal.places[0]), id: "view", osm_id: "node/5", category: "viewpoint",
    location: point(.01, .013, "Fixture 5"), priority: 9 });
  const calls = [], stages = [];
  let pendingModel = null;
  const model = { cancel() {}, infer: async (input, signal) => {
    calls.push(input); const index = calls.length;
    if (index > 2) throw Error("Third model call forbidden.");
    if (failure === "pending" && index === 2) await new Promise(resolve => { pendingModel = resolve; });
    if (failure && failure !== "pending" && index === 2) { const e = Error("synthetic"); e.code = failure; throw e; }
    const value = structuredClone(index === 1 ? proposal : revision);
    if (index === 2) mutateRevision?.(value);
    return { text: JSON.stringify(value), elapsed_ms: 13, usage: { input_tokens: 20, output_tokens: 40, total_tokens: 60, access_token: "must-never-survive" },
      researched: true, citations: [{ url: "https://example.invalid/source", title: "Explicitly synthetic source" }] };
  } };
  const controller = createAdventureController({ model, planner: r.planner, confirmProposal, onProgress: stage => stages.push(stage), lifecycleTarget: null });
  const input = { prompt: "Synthetic test: a 2.2 km historical adventure with interesting stops.", modelId: "synthetic-model",
    context: { start: proposal.intent.start, end: proposal.intent.end, reference: r.region.reference }, research: true };
  return { ...r, model, nativeCalls: r.calls, controller, proposal, revision, calls, stages, input, finishModel: () => pendingModel?.(), modelPending: () => Boolean(pendingModel) };
}
async function rejected(promise, code) {
  const error = await promise.then(() => null, caught => caught);
  equal(typeof error?.code === "string" ? error.code : error?.name, code, `Expected ${code}, got ${error}`);
}

export async function runAdventureControllerHarness() {
  const cases = [], beforeState = JSON.stringify(state);
  for (const unresolved of [false,true]) {
    const r=await setup();
    try {
      r.proposal.intent.topology='loop';r.proposal.intent.end=null;r.input.context.end=null;
      if(unresolved){r.proposal.places[0].location={name:'Unknown synthetic landmark',lat:null,lon:null};r.proposal.places[0].osm_id=null;r.proposal.places[0].confidence='uncertain';}
      else r.proposal.places=[];
      const output=await r.controller.run({...r.input,refine:false});
      assert(output.chosen.result.candidates.length>0&&output.routing_diagnostics.budget.total_used<=8,'bounded native control survives when no suggested stop can be located');
      assert(output.chosen.result.candidates.every(c=>c.reached_stops.length===0),'a control route cannot invent landmark visits');
      if(unresolved)assert(output.chosen.assessment.assessments.every(a=>a.places[0].status==='unresolved_location'),'unresolved place remains visibly unresolved on control routes');
      let manualRejected=false;try{validateLocalWaypointRouteRequest({...output.chosen.request,preferences:{nature:"off",path_selection:"shortest",loop_geometry:"off"}})}catch(e){manualRejected=e.code==='loop_requires_waypoint'}assert(manualRejected,'ordinary manual waypoint loops still require an explicit point');
      cases.push(unresolved?'unresolved_suggestions_keep_routed_control_without_fabricated_visits':'adventure_loop_without_suggestions_uses_bounded_native_control');
    } finally {r.controller.cancel();r.planner.invalidate();}
  }
  {
    const r=await setup();
    try {
      const place={osm_id:'node/1',location:{name:'Fixture 1',lat:.01,lon:.005},category:'castle',access:'unknown',potability:'not_applicable'};
      r.input.context.localPlaces=Array.from({length:40},()=>structuredClone(place));
      await r.controller.run({...r.input,refine:false});
      const sent=JSON.parse(r.calls[0].input).planning_context.local_places;
      assert(sent.length===24&&sent[0].osm_id==='node/1'&&sent[0].location.lat===.01,'the model receives the bounded local geographic facts before proposing stops');
      cases.push('bounded_mapped_landmarks_reach_initial_inference');
    } finally {r.controller.cancel();r.planner.invalidate();}
  }
  {
    const r = await setup();
    try {
      await r.controller.run({ ...r.input, structured: false, refine: false });
      assert(r.calls.length === 1 && r.calls[0].output_schema === null, 'explicit text mode omits unsupported Structured Outputs');
      const marker = 'Local validation remains mandatory:\n';
      const schema = JSON.parse(r.calls[0].instructions.split(marker)[1]);
      assert(schema.properties.format.enum[0] === 'sugarglider_ai_adventure'
        && schema.properties.places.maxItems === 20 && schema.additionalProperties === false,
      'text mode still supplies the complete bounded proposal contract');
      cases.push('text_mode_includes_exact_contract_without_provider_structured_output');
    } finally { r.controller.cancel(); r.planner.invalidate(); }
  }
  for (const id of ['__proto__', 'constructor']) {
    const r = await setup();
    try {
      r.proposal.places[0].id = id;
      const output = await r.controller.run({ ...r.input, refine: false });
      const candidate = output.chosen.result.candidates.find(c => c.reached_stops.length);
      const assessment = output.chosen.assessment.assessments.find(a => a.candidate_id === candidate.id);
      assert(candidate.reached_stops[0].id === `adventure/${id}` && assessment.places[0].canonical_id === `adventure/${id}`, 'model IDs remain data rather than object prototype properties');
    } finally { r.controller.cancel(); r.planner.invalidate(); }
  }
  cases.push('model_ids_cannot_address_javascript_prototypes');
  {
    const r = await setup();
    try {
      r.proposal.places[0].location.name = 'AI historical nickname';
      const output = await r.controller.run({ ...r.input, refine: false });
      const candidate = output.chosen.result.candidates.find(c => c.reached_stops.length);
      assert(candidate.reached_stops[0].name === 'Fixture 1' && output.chosen.grounding.places[0].location.name === 'AI historical nickname', 'new AI stops use the matched map name while preserving the suggestion');
      const doc = new DOMParser().parseFromString(await exportCanonicalCandidate(candidate).blob.text(), 'application/xml');
      assert([...doc.getElementsByTagName('wpt')].every(point => point.textContent.includes('Fixture 1')), 'GPX does not claim an unverified AI place name');
      cases.push('mapped_names_authoritative_for_new_ai_waypoints_and_gpx');
    } finally { r.controller.cancel(); r.planner.invalidate(); }
  }
  {
    const r = await setup();
    try {
      const output = await r.controller.run(r.input);
      equal(r.calls.length, 2, "one initial plus one revision");
      assert(output.refinement_improved && output.selected_round === 1 && output.rounds.length === 2,
        `measured improvement chooses revised portfolio: ${JSON.stringify({ error: output.refinement_error,
          rounds: output.rounds.map(round => ({ candidates: round.result.candidates.map(c => c.id),
            assessments: round.assessment.assessments.map(a => ({ id: a.candidate_id, valid: a.hard_route_constraints_satisfied,
              within: a.within_distance_tolerance, loss: a.measured_preference_loss, error: a.target_error_m })) })) })}`);
      assert(output.chosen.result.candidates.some(c => c.reached_stops.length === 2), "actual checked subset uses revised places");
      assert(output.chosen.result.candidates.some(c => c.reached_stops.length === 0), "canonical comparison route retained");
      assert(output.chosen.result.candidates[0].diagnostics.within_tolerance, "distance tolerance takes priority over the outside-tolerance comparison");
      assert(!r.calls[0].research && r.calls[1].research && r.calls.every(call => call.output_schema && call.instructions.includes("never geometry")), "geographical pass defers research without weakening the proposal contract");
      assert(output.model_calls[0].research_enabled===false&&output.model_calls[1].research_enabled===true,"observed research policy is public in model diagnostics");
      assert(r.calls[0].instructions.includes("Set every anecdote to null"),"the first geographical pass must not generate historical stories");
      const researched=JSON.parse(r.calls[1].input).reached_place_research;
      assert(researched.length>0&&researched.every(place=>place.osm_id&&place.name)&&!JSON.stringify(researched).includes('"lat"'),"final research is grounded in checked reached identities without route coordinates");
      const sent = JSON.parse(r.calls[1].input).measurements;
      const encoded = JSON.stringify(sent);
      assert(!encoded.includes('"geometry"') && !encoded.includes('"lat"') && !encoded.includes('"lon"'), "revision summary has no raw line or coordinates");
      assert(output.routing_diagnostics.budget.total_used <= 16 && output.routing_diagnostics.cache.backend_call_count === r.nativeCalls.length, "shared bounded route accounting");
      assert(output.model_calls.every(call => !Object.hasOwn(call.usage, "access_token") && call.elapsed_ms === 13), "only measured whitelisted usage retained");
      const assessed = output.chosen.assessment.assessments;
      assert(assessed.every(a => a.wishes.find(w => w.metric === "asphalt").status === "unavailable"
        && a.wishes.find(w => w.metric === "asphalt").met === null), "unknown surfaces are never claimed avoided");
      assert(assessed.some(a => a.places.some(p => p.local_category === "castle" && p.status === "reached")), "local OSM category rather than AI historical label");
      assert(assessed.every(a => a.places.every(p => p.story_status === "source_linked_ai_text")), "linked source does not become independently verified history");
      assert(assessed.every(a => a.places.find(p => p.id === "view").status === "access_restricted"), "private mapped viewpoint stays omitted");
      const candidate = output.chosen.result.candidates.find(c => c.reached_stops.length === 2);
      const doc = new DOMParser().parseFromString(await exportCanonicalCandidate(candidate).blob.text(), "application/xml");
      equal(doc.getElementsByTagName("trkpt").length, candidate.route.geometry.length, "end-to-end selected GPX uses routed line");
      equal(doc.getElementsByTagName("wpt").length, 2, "checked approaches only");
      assert(!doc.documentElement.textContent.includes("Synthetic test story"), "stories stay out of GPX");
      for (const stage of ["understanding", "checking_places", "routing", "comparing", "improving", "ready"]) assert(r.stages.includes(stage), `stage ${stage}`);
      outputs.push(output); cases.push("proposal_grounding_two_round_search_measured_improvement_and_gpx");
    } finally { r.controller.cancel(); r.planner.invalidate(); }
  }
  for (const failure of ["deadline", "network_timeout", "usage_limit", "auth_expired", "network", "unsupported", "invalid_response"]) {
    const r = await setup({ failure });
    try {
      const output = await r.controller.run(r.input);
      assert(output.rounds.length === 1 && output.chosen.result.candidates.length && output.refinement_error === failure, "valid first candidates survive second-call failure");
      assert(r.calls.length === 2 && !output.refinement_improved, "no hidden retry or falsely improved route");
      assert(output.chosen.grounding.places.every(place=>place.anecdote===null&&place.sources.length===0),"failed final research cannot turn the geography-only pass into ungrounded history");
    } finally { r.controller.cancel(); r.planner.invalidate(); }
    cases.push(`revision_${failure}_retains_first_valid_candidates`);
  }
  for (const mutation of [v => { v.intent.target_distance_m += 1000; }, v => { v.places[1].importance = "mandatory"; },
    v => { v.places[1].sources[0].url = "javascript:alert(1)"; }, v => { v.intent.start.lat += .001; }]) {
    const r = await setup({ mutateRevision: mutation });
    try {
      const output = await r.controller.run(r.input);
      assert(output.selected_round === 0 && output.rounds.length === 1 && output.refinement_error,
        `untrusted revision cannot change hard intent or unsafe stories: ${JSON.stringify({ mutation: String(mutation), selected: output.selected_round, rounds: output.rounds.length, error: output.refinement_error })}`);
    } finally { r.controller.cancel(); r.planner.invalidate(); }
  }
  cases.push("changed_intent_unconfirmed_mandatory_and_unsafe_revision_rejected");
  {
    const r = await setup();
    try {
      await rejected(r.controller.run({ ...r.input, context: { ...r.input.context, reference: null } }), "adventure_context_required");
      equal(r.calls.length, 0, "missing region never starts a model request");
      r.proposal.wishes[1].importance = "hard";
      await rejected(r.controller.run(r.input), "adventure_unsupported_hard_preference");
      equal(r.nativeCalls.length, 0, "unsupported hard wish requires review before routing");
      cases.push("missing_region_and_unsupported_hard_wish_require_review");
    } finally { r.controller.cancel(); r.planner.invalidate(); }
  }
  for (const kinds of [["start"], ["end"], ["start", "end"]]) {
    let reviewed = false;
    const r = await setup({ confirmProposal: async review => {
      assert(r.nativeCalls.length === 0, 'inferred endpoints cannot route before review');
      for (const kind of kinds) {
        assert(review[`${kind}Resolution`].evidence === 'model_coordinate_unverified', 'model coordinate is not relabelled as locally verified');
        assert(['lat','lon','name'].every(key => review.context[kind][key] === r.proposal.intent[kind][key]), 'review displays the actual proposed coordinate');
      }
      reviewed = true; return { confirmedMandatoryIds: [] };
    } });
    try {
      const context = { ...r.input.context };
      for (const kind of kinds) context[kind] = null;
      const output = await r.controller.run({ ...r.input, context, refine: false });
      assert(reviewed && output.chosen.result.candidates.length > 0, 'reviewed inferred endpoints produce actual routed candidates');
      const sent = JSON.parse(r.calls[0].input).planning_context;
      for (const kind of kinds) {
        assert(sent[kind] === null && sent[`${kind}_is_fixed`] === false, 'missing endpoints are sent honestly without GPS or centre fallback');
        assert(['lat','lon','name'].every(key => output.chosen.request[kind][key] === r.proposal.intent[kind][key]), 'canonical request preserves the reviewed endpoint');
      }
      assert(output.routing_diagnostics.budget.total_used <= 8 && r.calls.length === 1, 'endpoint resolution adds no model or routing calls');
      cases.push(`inferred_${kinds.join('_and_')}_requires_review_before_routing`);
    } finally { r.controller.cancel(); r.planner.invalidate(); }
  }
  {
    const r = await setup({ confirmProposal: async () => { throw Error('Unresolved endpoint must not reach review'); } });
    try {
      r.proposal.intent.start = null;
      await rejected(r.controller.run({ ...r.input, context: { ...r.input.context, start: null }, refine: false }), 'adventure_start_required');
      assert(r.calls.length === 1 && r.nativeCalls.length === 0, 'missing area asks for clarification before any route call');
      cases.push('missing_start_description_does_not_invent_a_location');
    } finally { r.controller.cancel(); r.planner.invalidate(); }
  }
  {
    let checked = false;
    const r = await setup({ confirmProposal: async ({ startResolution }) => {
      checked = true; assert(startResolution.evidence === 'unique_exact_local_name', 'named Start is resolved in the installed index');
      assert(r.nativeCalls.length === 0, 'named Start reviewed before routing');return { confirmedMandatoryIds: [] };
    } });
    try {
      r.proposal.intent.start = { name: 'Fixture 2', lat: null, lon: null };
      const output = await r.controller.run({ ...r.input, context: { ...r.input.context, start: null }, refine: false });
      assert(checked && output.chosen.request.start.name === 'Fixture 2', 'resolved Start is canonical');
      outputs.push(output);cases.push('named_start_resolved_with_original_proposal_retained');
    } finally { r.controller.cancel(); r.planner.invalidate(); }
  }
  {
    const r = await setup({ confirmProposal: async () => ({ confirmedMandatoryIds: [] }) });
    try {
      r.proposal.intent.topology = 'loop';r.proposal.intent.end = null;
      const output = await r.controller.run({ ...r.input, context: { ...r.input.context, start: null, end: null }, refine: false });
      assert(output.chosen.request.topology === 'loop' && output.chosen.request.end === null && output.chosen.endpoint_resolution.end === null,
        'inferred loop Start never invents a separate End');
      cases.push('inferred_loop_returns_to_reviewed_start');
    } finally { r.controller.cancel(); r.planner.invalidate(); }
  }
  {
    const r = await setup();
    try {
      r.proposal.places[0].importance = "mandatory";
      await rejected(r.controller.run({ ...r.input, refine: false }), "adventure_mandatory_confirmation_required");
      equal(r.calls.length, 1, "no automatic approval or extra model call");
      cases.push("model_cannot_confer_mandatory_authority");
    } finally { r.controller.cancel(); r.planner.invalidate(); }
  }
  {
    const r = await setup({ confirmProposal: async ({ proposal }) => ({ confirmedMandatoryIds: [proposal.places[0].id] }),
      change: (reply, input) => {
        const index = input.points.findIndex(p => Math.abs(p.lon - .005) < 1e-10 && Math.abs(p.lat - .01) < 1e-10);
        if (index >= 0) { reply.snapped_points[index].lon += .001; reply.geometry[index * 2] = [reply.snapped_points[index].lon, reply.snapped_points[index].lat]; }
      } });
    try {
      r.proposal.places[0].importance = "mandatory";
      await rejected(r.controller.run({ ...r.input, refine: false }), "adventure_no_candidates");
      cases.push("exact_anchor_tolerance_cannot_fabricate_landmark_visit");
    } finally { r.controller.cancel(); r.planner.invalidate(); }
  }
  {
    const r = await setup({ failure: "pending" }), abort = new AbortController();
    const promise = r.controller.run(r.input, abort.signal), result = rejected(promise, "AbortError");
    while (!r.modelPending()) await new Promise(resolve => setTimeout(resolve, 0));
    abort.abort(); r.finishModel(); await result;
    equal(r.calls.length, 2, "cancel during revision cannot restart model or route work");
    cases.push("cancelled_revision_never_commits_first_or_stale_results"); r.planner.invalidate();
  }
  {
    const r = await setup();
    try {
      const stale = structuredClone(r.input); stale.context.reference.build_id = "f".repeat(64);
      await rejected(r.controller.run(stale), "AbortError");
      assert(!r.stages.includes("routing"), "region changed during inference cannot route");
      cases.push("changed_region_rejected_after_model_before_routing");
    } finally { r.controller.cancel(); r.planner.invalidate(); }
  }
  {
    const output = outputs[0], round = output.chosen, candidate = round.result.candidates[1];
    const elevation = { candidate_id: candidate.id, regional_reference: { region_id: round.grounding.region_id, build_id: round.grounding.build_id,
      pack_id: candidate.diagnostics.details.local_routing.pack_id }, analysis: { routing_profile: candidate.routing_profile,
      route_distance_m: candidate.route.summary.distance_m, coverage: "partial", total_ascent_m: null, total_descent_m: null,
      observed_ascent_m: 37, observed_descent_m: 32 } };
    const proposal = { ...round.proposal, wishes: [{ metric: "elevation_gain", goal: "target", value: 500, importance: "high" }] };
    const analyze = value => assessAdventure({ ...round, proposal, elevations: { [candidate.id]: value } }).assessments.find(a => a.candidate_id === candidate.id);
    assert(analyze(elevation).wishes[0].status === "unavailable", "partial elevation cannot claim complete ascent");
    const complete = structuredClone(elevation); complete.analysis.coverage = "complete"; complete.analysis.total_ascent_m = 510;
    assert(analyze(complete).wishes[0].measured_value === 510 && analyze(complete).wishes[0].status === "measured_not_directly_optimized", "complete matched elevation is comparison only");
    complete.candidate_id = "wrong"; assert(analyze(complete).wishes[0].status === "unavailable", "wrong binding cannot supply elevation");
    complete.candidate_id = candidate.id;
    const measured = analyze(complete), unknown = analyze(elevation);
    assert(!adventureMeasuredImprovement(measured, unknown), "missing elevation is not rewarded as zero target error");
    const first = round.assessment.assessments[0], same = { ...first, candidate_id: "another-id" };
    assert(!adventureMeasuredImprovement(first, same), "different ID alone is not an improvement");
    const compact = compactAdventureAssessment(round.assessment);
    assert(JSON.stringify(compact).length < 16000, "measurement summary bounded and compact");
    cases.push("partial_misbound_elevation_unknown_and_no_false_id_improvement");
  }
  {
    const prior = structuredClone(outputs[0].chosen.assessment.assessments[0]);
    prior.loop_geometry = { geometry_penalty: 1 };
    const revised = structuredClone(prior);
    revised.loop_geometry.geometry_penalty = 2;
    for (const wish of revised.wishes) if (wish.loss !== null) wish.loss -= 10;
    assert(!adventureMeasuredImprovement(prior, revised), "better wishes cannot conceal worse measured loop shape");
    revised.loop_geometry.geometry_penalty = 1;
    assert(adventureMeasuredImprovement(prior, revised), "preferences can improve equally shaped valid routes");
    revised.within_distance_tolerance = false; revised.loop_geometry.geometry_penalty = 0;
    assert(!adventureMeasuredImprovement(prior, revised), "loop shape cannot outrank distance eligibility");
    prior.within_distance_tolerance = false; prior.target_error_m = 100; revised.target_error_m = 200;
    assert(!adventureMeasuredImprovement(prior, revised), "outside-distance error precedes measured shape and wishes");
    cases.push("distance_then_measured_loop_shape_before_soft_wishes");
  }
  {
    for (const [prompt, expected] of [["Propose-moi deux parcours différents",2],["three distinct loops",3],["trois lieux historiques",3],
      ["Une boucle de 35 km",1],["Deux parcours, finalement trois itinéraires",3],["2 routes",2],["Je veux courir en forêt",3]]) {
      equal(requestedAdventureAlternatives(prompt),expected,"explicit route count survives natural-language interpretation");
    }
    const r=await setup();
    try {
      r.proposal.intent.alternatives=5;
      const output=await r.controller.run({...r.input,prompt:"Propose-moi deux parcours différents",refine:false});
      assert(output.chosen.request.candidate_count===2&&output.chosen.proposal.intent.alternatives===2,"model cannot change an explicit count");
      assert(JSON.parse(r.calls[0].input).planning_context.requested_alternatives===2,"count is supplied before model interpretation");
      assert(output.timings.total_ms>=0&&output.timings.grounding_ms>=0&&output.model_calls[0].timings.request_bytes===null,"sanitized observable timings, unavailable values remain null");
      cases.push("french_english_count_default_and_model_override");
    } finally {r.controller.cancel();r.planner.invalidate();}
  }
  {
    const r=await setup();
    try {
      r.proposal.intent.target_distance_m=1600;
      const output=await r.controller.run({...r.input,prompt:"Propose-moi deux parcours"});
      assert(r.calls.length===1&&output.chosen.result.candidates.length===2,`satisfactory source-linked route set avoids a second call: ${JSON.stringify({calls:r.calls.length, assessments:output.rounds[0].assessment.assessments.map(a=>({within:a.within_distance_tolerance, distance:a.distance_m,hard:a.hard_route_constraints_satisfied})),stories:output.rounds[0].grounding.places.map(p=>[p.anecdote,p.story_status])})}`);
      cases.push("satisfactory_routes_skip_optional_model_call");
    } finally {r.controller.cancel();r.planner.invalidate();}
  }
  for (const invalid of [false,true]) {
    const r=await setup();
    try {
      r.proposal.places[0].anecdote=null;
      const infer=r.model.infer;
      r.model.infer=async (input,signal)=>{
        if(!r.calls.length)return infer(input,signal);
        r.calls.push(input);
        assert(input.output_schema.properties.stories&&!JSON.stringify(JSON.parse(input.input)).includes('"lat"'),"story call supplies only reached identities and no route geometry/coordinates");
        return {text:JSON.stringify({stories:[{id:r.proposal.places[0].id,osm_id:invalid?"node/999":"node/1",anecdote:"Synthetic reached-place story.",sources:[{title:"Synthetic source",url:"https://example.invalid/source"}]}]}),
          researched:true,citations:[{url:"https://example.invalid/source"}],elapsed_ms:5,usage:{input_tokens:10,output_tokens:10,total_tokens:20}};
      };
      r.proposal.intent.target_distance_m=1600;
      const output=await r.controller.run({...r.input,prompt:"Propose-moi deux parcours"});
      assert(r.calls.length===2&&output.model_calls[1].phase==="stories"&&output.rounds.length===1&&output.routing_diagnostics.budget.total_used<=8,"story enrichment cannot reroute or create another routing round");
      if(invalid)assert(output.refinement_error&&output.chosen.grounding.places[0].anecdote===null,"wrong story identity leaves first result intact");
      else assert(output.chosen.grounding.places[0].anecdote==="Synthetic reached-place story."&&output.chosen.grounding.places[0].story_status==="source_linked_ai_text","reached identity retains honest citation provenance");
      const candidate=output.chosen.result.candidates.find(c=>c.reached_stops.length);
      assert(!(await exportCanonicalCandidate(candidate).blob.text()).includes("Synthetic reached-place story"),"researched text never enters GPX");
      if(!invalid){
        const {encodeAdventureSnapshot,decodeAdventureSnapshot}=await import("../../src/sugarglider/web/static/adventure_snapshot_validation.js");
        const encoded=await encodeAdventureSnapshot(output);
        const recovered=await decodeAdventureSnapshot({...encoded,selected_id:candidate.id});
        equal(recovered.output,output,"story research and whitelisted timings recover exactly without rerouting");
      }
      outputs.push(output);cases.push(invalid?"story_identity_change_rejected_without_losing_routes":"second_call_researches_reached_places_without_rerouting");
    } finally {r.controller.cancel();r.planner.invalidate();}
  }
  {
    const r=await setup();
    try {
      r.revision.places=[{...structuredClone(r.proposal.places[0]),anecdote:"Synthetic source-linked story from the rejected route revision."}];
      const output=await r.controller.run(r.input);
      assert(output.selected_round===0&&!output.refinement_improved&&output.rounds.length===2,"equal routed strategies do not falsely improve route quality");
      assert(output.chosen.grounding.places[0].anecdote==="Synthetic source-linked story from the rejected route revision."&&output.chosen.grounding.places[0].story_status==="source_linked_ai_text","verified citation provenance for the same reached identity survives a non-improving routing round");
      const candidate=output.chosen.result.candidates.find(c=>c.reached_stops.length);
      assert(!(await exportCanonicalCandidate(candidate).blob.text()).includes("rejected route revision"),"retained research never alters GPX");
      const {encodeAdventureSnapshot}=await import("../../src/sugarglider/web/static/adventure_snapshot_validation.js");await encodeAdventureSnapshot(output);
      cases.push("reached_story_research_survives_rejected_route_strategy_without_rerouting_first_result");
    } finally {r.controller.cancel();r.planner.invalidate();}
  }
  equal(JSON.stringify(state), beforeState, "controller never corrupts selected/manual plan");
  return cases;
}
