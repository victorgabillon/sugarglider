import { createLocalPlanningContext, LocalPlanningBudgetError } from "../../src/sugarglider/web/static/local_planning_context.js";
import { PUBLIC_PROFILE_METADATA } from "../../src/sugarglider/web/static/public_profile_metadata.js";
import { createLocalAutoTourEngine, MARLY_LOCAL_AUTO_TOUR_FIXTURE } from "../../src/sugarglider/web/static/local_auto_tour.js";

export const diagnosticSamples = [];

const points = (offset = 0) => [{lat:48,lon:2},{lat:48.01+offset,lon:2.01}];
const success = () => ({type:"local_route_result",geometry:[[2,48],[2.01,48.01]]});
function context(route, options = {}) {
  return createLocalPlanningContext({profile:"hike",route,totalLimit:3,phaseLimits:{control:3,poi:1},...options});
}
function assert(value, message) { if (!value) throw new Error(message); }
function equal(value, expected, message) { assert(JSON.stringify(value)===JSON.stringify(expected), `${message}: ${JSON.stringify(value)}`); }
async function rejected(promise, name) {
  let error;try {await promise;}catch(caught){error=caught;}
  assert(error?.name===name,`expected ${name}, got ${error}`);
  return error;
}
function accounting(ctx) {
  const snapshot=ctx.snapshot();
  diagnosticSamples.push(snapshot);
  const {budget,cache}=snapshot;
  equal(cache.lookup_count,cache.hit_count+cache.miss_count,"lookup invariant");
  equal(cache.entry_count,cache.successful_entry_count+cache.failed_entry_count,"entry invariant");
  equal(cache.backend_call_count,cache.miss_count,"backend invariant");
  equal(budget.total_used,cache.backend_call_count,"reservation matches actual call");
  equal(budget.total_remaining,budget.total_limit-budget.total_used,"remaining invariant");
  equal(Object.values(budget.phases).reduce((sum,phase)=>sum+phase.used,0),budget.total_used,"phase totals");
  return {budget,cache};
}

export async function runPr41LocalPlanningHarness() {
  const scenarios=[];
  for (const [name, run] of [
    ["all_six_profiles_are_explicit_and_request_scoped", async () => {
      const observed=[];
      for (const profile of Object.keys(PUBLIC_PROFILE_METADATA)) {
        const ctx=context((input)=>{observed.push(input.profile);return success();},{profile});
        await ctx.requestRoute(points(),"control");await ctx.requestRoute(points(),"control");
        equal(accounting(ctx).cache.backend_call_count,1,"same request uses one call");
      }
      equal(observed,Object.keys(PUBLIC_PROFILE_METADATA),"no profile fallback or cross-profile cache");
    }],
    ["concurrent_identical_requests_share_one_immutable_result", async () => {
      let finish, calls=0, sent;
      const ctx=context((input)=>{calls+=1;sent=input;return new Promise((resolve)=>{finish=resolve;});});
      const input=points(), first=ctx.requestRoute(input,"control"), second=ctx.requestRoute(points(),"poi");
      assert(first===second,"one in-flight operation");equal(calls,1,"native call synchronous and unique");
      input[0].lat=1;equal(sent.points[0].lat,48,"outgoing points copied");
      assert(Object.isFrozen(sent.points) && Object.isFrozen(sent.points[0]),"request coordinates immutable");
      equal(accounting(ctx).cache.entry_count,0,"pending operation is not a completed cache entry");
      const raw=success();finish(raw);const result=await first;await second;
      raw.geometry[0][0]=3;equal(result.geometry[0][0],2,"backend mutation cannot change cached result");
      assert(Object.isFrozen(result.geometry[0]),"cached geometry deeply immutable");
      equal(accounting(ctx).cache.successful_entry_count,1,"one completed success");
    }],
    ["returned_failures_are_cached_without_routing_fallback", async () => {
      let calls=0;const ctx=context(()=>{calls+=1;return {type:"local_route_failure",code:"no_route"};});
      const first=await ctx.requestRoute(points(),"control"), second=await ctx.requestRoute(points(),"control");
      assert(first===second,"same immutable failure");equal(calls,1,"no retry");
      equal(accounting(ctx).cache.failed_entry_count,1,"one failed entry");
    }],
    ["transport_errors_are_cached_and_counted_once", async () => {
      let calls=0;const ctx=context(()=>{calls+=1;throw new Error("synthetic failure");});
      await rejected(ctx.requestRoute(points(),"control"),"Error");
      await rejected(ctx.requestRoute(points(),"control"),"Error");
      equal(calls,1,"cached thrown failure");equal(accounting(ctx).cache.failed_entry_count,1,"one failed entry");
    }],
    ["phase_and_total_limits_are_strict_and_rejections_are_separate", async () => {
      const ctx=context(()=>success());
      await ctx.requestRoute(points(),"control");await ctx.requestRoute(points(),"poi");
      await ctx.requestRoute(points(.01),"poi");
      const phaseError=await rejected(ctx.requestRoute(points(.02),"poi"),"LocalPlanningBudgetError");
      assert(phaseError instanceof LocalPlanningBudgetError && phaseError.phase==="poi","typed phase rejection");
      await ctx.requestRoute(points(.02),"control");
      await rejected(ctx.requestRoute(points(.03),"control"),"LocalPlanningBudgetError");
      await ctx.requestRoute(points(),"control");
      const {budget,cache}=accounting(ctx);
      equal(budget.total_used,3,"three actual calls");equal(budget.phases.poi.used,1,"POI limit enforced");
      equal(cache.pre_backend_rejection_count,2,"rejections outside cache misses");
      equal(cache.lookup_count,5,"only real lookups counted");assert(budget.global_exhausted,"total exhausted");
    }],
    ["invalid_requests_never_reserve_budget_or_invoke_native", async () => {
      let calls=0;const ctx=context(()=>{calls+=1;return success();});
      for (const input of [[],[...points(),{lat:NaN,lon:2}],[{lat:91,lon:2},{lat:48,lon:2}]]) {
        await rejected(ctx.requestRoute(input,"control"),"TypeError");
      }
      await rejected(ctx.requestRoute(points(),"unknown"),"TypeError");equal(calls,0,"invalid request cannot route");
      equal(accounting(ctx).budget.total_used,0,"no invalid reservation");
      for (const profile of ["constructor","walking","foot"]) {
        let error;try {context(()=>success(),{profile});}catch(caught){error=caught;}
        assert(error instanceof TypeError,"aliases and prototype keys rejected");
      }
    }],
    ["clone_errors_and_named_transport_errors_each_count_one_failure", async () => {
      for (const route of [()=>({...success(),invalid:()=>{}}),()=>{throw new DOMException("synthetic","DataCloneError");}]) {
        const ctx=context(route);
        await rejected(ctx.requestRoute(points(),"control"),"DataCloneError");
        await rejected(ctx.requestRoute(points(),"control"),"DataCloneError");
        equal(accounting(ctx).cache.failed_entry_count,1,"no double-counted failure");
      }
    }],
    ["separate_planning_requests_never_reuse_previous_graph_results", async () => {
      let calls=0;const route=()=>{calls+=1;return success();};
      const first=context(route), second=context(route);
      await first.requestRoute(points(),"control");await second.requestRoute(points(),"control");
      equal(calls,2,"one cache per request");accounting(first);accounting(second);
      const snapshot=first.snapshot();assert(Object.isFrozen(snapshot.budget.phases.control),"public diagnostics immutable");
    }],
    ["auto_tour_rejects_different_request_while_existing_call_drains", async () => {
      let finish,calls=0;
      const engine=createLocalAutoTourEngine({route:()=>{calls+=1;return new Promise((resolve)=>{finish=resolve;});},now:()=>0});
      const first=engine.generate(MARLY_LOCAL_AUTO_TOUR_FIXTURE);
      assert(first===engine.generate(MARLY_LOCAL_AUTO_TOUR_FIXTURE),"same request joins active search");
      let error;try {engine.generate({...MARLY_LOCAL_AUTO_TOUR_FIXTURE,seed:1});}catch(caught){error=caught;}
      equal(error?.code,"local_generation_busy","different request cannot receive old result");
      engine.invalidate();finish(null);equal(await first,null,"stale work discarded");equal(calls,1,"no extra backend call");
    }],
  ]) { await run();scenarios.push(name); }
  return scenarios;
}
