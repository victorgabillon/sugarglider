import { evaluateLocalCandidateDraft, LocalCandidateEvaluationError, deepFreeze } from "../../src/sugarglider/web/static/local_candidate_evaluator.js";
import { canonicalFixed } from "../../src/sugarglider/web/static/canonical_numbers.js";
import { publishLocalPlan, buildLocalPortfolio } from "../../src/sugarglider/web/static/local_plan_publisher.js";
import { createLocalPlanPublisher } from "../../src/sugarglider/web/static/local_plan_client.js";
import { createLocalPlanningContext } from "../../src/sugarglider/web/static/local_planning_context.js";

export const publishedSamples = [];
export const publishedPlans = [];
function assert(value,message) { if (!value) throw new Error(message); }
function same(actual, expected, path="value") {
  if (typeof actual==="number" && typeof expected==="number") {
    assert(Math.abs(actual-expected)<=Math.max(1e-10,Math.abs(expected)*1e-12),`${path}: ${actual} != ${expected}`);return;
  }
  if (actual && expected && typeof actual==="object" && typeof expected==="object") {
    assert(JSON.stringify(Object.keys(actual).sort())===JSON.stringify(Object.keys(expected).sort()),`${path}: keys differ`);
    for (const key of Object.keys(expected)) same(actual[key],expected[key],`${path}.${key}`);
  } else assert(actual===expected,`${path}: ${actual} != ${expected}`);
}
async function fails(request,draft,code) {
  let error;try {await evaluateLocalCandidateDraft(request,draft);}catch(caught){error=caught;}
  assert(error instanceof LocalCandidateEvaluationError && error.code===code,`expected ${code}, got ${error}`);
}
export async function runPr41LocalCandidatesHarness() {
  const fixture=await(await fetch('/tests/fixtures/pr41_local_candidates.json')).json(), scenarios=[];
  for (const test of fixture.cases) {
    const request=deepFreeze(test.request), draft=deepFreeze(test.native_draft);
    const before=JSON.stringify({request,draft});
    const candidate=await evaluateLocalCandidateDraft(request,draft);
    assert(!Object.hasOwn(candidate,'rank') && !Object.hasOwn(candidate,'roles'),'evaluator does not rank');
    assert(candidate.id===test.expected.signature,`${test.id}: exact Python signature`);
    same(candidate.traversal,test.expected.traversal,`${test.id}.traversal`);
    const expected=structuredClone(test.expected.analysis);expected.spurs.warnings=['spur_analysis_unavailable'];
    same(candidate.route.analysis,expected,`${test.id}.analysis`);
    assert(JSON.stringify(candidate.route.geometry)===JSON.stringify(draft.geometry),'native line unchanged');
    assert(candidate.route.analysis.repetition.available===false,'repetition remains unknown');
    assert(candidate.route.analysis.backtrack_edge_id_coverage.share===0,'backtracking coverage remains zero');
    assert(candidate.route.analysis.unknown_surface.distance_m===draft.distance_m,'unknown surface owns authoritative total');
    assert(JSON.stringify({request,draft})===before,'source request and draft unchanged');
    assert(Object.isFrozen(candidate.route.geometry[0]),'immutable final routed geometry');
    const search=fixtureSearch(request,[draft]);
    const result=await publishLocalPlan(request,search);
    assert(result.candidates.length===1 && result.candidates[0].id===candidate.id,'shared publication retains candidate');
    assert(result.candidates[0].roles.join(',')==='harmonious,distance_focused','unknown repetition cannot earn a smooth role');
    assert(JSON.stringify(result.search_diagnostics.cache)===JSON.stringify(search.search_diagnostics.cache),'publication preserves gateway cache facts');
    publishedPlans.push({request,result});
    publishedSamples.push({request,candidate:result.candidates[0]});
    scenarios.push(`canonical_${test.id}`);
  }
  const source=fixture.cases[0], request=source.request;
  await fails(request,{...source.native_draft,profile:'road_bike'},'local_candidate_identity_mismatch');
  scenarios.push('profile_mismatch_rejected');
  const wrongStart=structuredClone(source.native_draft);wrongStart.geometry[0][0]+=1;
  await fails(request,wrongStart,'local_hard_endpoint_not_reached');scenarios.push('hard_endpoint_fidelity');
  const missing=structuredClone(request);missing.waypoints[0].coordinate.lon+=1;
  await fails(missing,source.native_draft,'local_exact_waypoint_not_reached');scenarios.push('exact_point_fidelity');
  const strict=structuredClone(request);strict.distance_objective={target_m:10000,tolerance_m:100,maximum_m:10100,priority:'strict'};
  await fails(strict,source.native_draft,'strict_distance_tolerance_missed');scenarios.push('strict_tolerance_stays_hard');
  const balanced=structuredClone(request);balanced.distance_objective={...balanced.distance_objective,maximum_m:2600,priority:'balanced'};
  await fails(balanced,source.native_draft,'maximum_distance_exceeded');scenarios.push('balanced_maximum_stays_hard');
  assert(canonicalFixed(-0,6)==='-0.000000','canonical negative zero');
  assert(canonicalFixed(0.0078125,6)==='0.007812','Python six-decimal ties to even');
  assert(canonicalFixed(0.0078125,8)==='0.00781250','GPX formatting preserved');
  scenarios.push('canonical_decimal_identity_and_gpx_formatting');
  const worker=createLocalPlanPublisher({lifecycleTarget:null});
  const workerResult=await worker.publish(request,fixtureSearch(request,[source.native_draft]));
  same(workerResult,publishedPlans[0].result,'actual_worker_publication');
  assert(Object.isFrozen(workerResult.candidates[0].route.geometry[0]),'worker results deeply immutable');
  worker.invalidate();scenarios.push('actual_module_worker_canonical_publication');
  const deduplicated=await publishLocalPlan(request,fixtureSearch(request,[source.native_draft,source.native_draft]));
  assert(deduplicated.candidates.length===1,'canonical geometry deduplication');
  const rejected=await publishLocalPlan(request,fixtureSearch(request,[wrongStart]));
  assert(rejected.candidates.length===0 && rejected.search_diagnostics.details.local_planning.rejected_publications[0].code==='local_hard_endpoint_not_reached','failed publication remains explicit');
  scenarios.push('portfolio_deduplication_and_final_hard_constraint_rejection');
  let rankedError=false;try{buildLocalPortfolio(publishedPlans[0].result.candidates,{limit:2});}catch{rankedError=true;}
  assert(rankedError,'portfolio accepts only unranked evaluator output');scenarios.push('one_owner_of_public_roles_and_rank');
  const fakeWorkers=[];let timeout;
  const fake=createLocalPlanPublisher({lifecycleTarget:null,createWorker:()=>{const w={postMessage(value){this.input=value;},terminate(){this.stopped=true;}};fakeWorkers.push(w);return w;},schedule:callback=>{timeout=callback;return 1;},cancelScheduled:()=>{}});
  const operation=fake.publish(request,fixtureSearch(request,[source.native_draft]));
  const outcome=operation.then(()=>null,error=>error);
  const busy=await fake.publish(request,fixtureSearch(request,[])).then(()=>null,error=>error.code);
  assert(busy==='local_publication_busy','only one bounded worker operation');
  const oldHandler=fakeWorkers[0].onmessage;
  fake.invalidate();assert((await outcome).name==='AbortError' && fakeWorkers[0].stopped,'page invalidation cancels worker');
  const next=fake.publish(request,fixtureSearch(request,[source.native_draft]));
  const nextOutcome=next.then(()=>null,error=>error);
  oldHandler({data:{id:fakeWorkers[0].input.id,type:'result',result:workerResult}});
  timeout();assert((await nextOutcome).code==='local_publication_timed_out','stale reply cannot settle a later operation');
  assert(fakeWorkers[1].stopped,'timeout terminates work');scenarios.push('publication_single_flight_lifecycle_and_timeout');
  return scenarios;
}

function fixtureSearch(request,candidates) {
  const context=createLocalPlanningContext({profile:request.routing_profile,route:()=>{throw new Error('publication must not route');},totalLimit:16,phaseLimits:{waypoint:16}});
  return {type:'local_waypoint_route_result',profile:request.routing_profile,pack_id:candidates[0]?.pack_id??null,candidates,
    search_diagnostics:context.snapshot(),warnings:[],rejected_attempt_counts:{}};
}
