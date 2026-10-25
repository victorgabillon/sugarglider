import { createLocalPlanner } from '../../src/sugarglider/web/static/local_planner.js';
import { createLocalPlanPublisher } from '../../src/sugarglider/web/static/local_plan_client.js';
import { PUBLIC_PROFILE_METADATA } from '../../src/sugarglider/web/static/public_profile_metadata.js';
import { exportCanonicalCandidate } from '../../src/sugarglider/web/static/local_gpx_export.js';
import { endpointSnapPolicy, restoreEndpointSnapIntent } from '../../src/sugarglider/web/static/endpoint_snapping.js';
import { renderEndpointAdjustments } from '../../src/sugarglider/web/static/endpoint_adjustment_view.js';
import { replaceResolvedRouteLocation } from '../../src/sugarglider/web/static/route_point_acquisition.js';
import { regionalRoutingReference } from '../../src/sugarglider/web/static/regional_routing_reference.js';
import { state, currentPlanRequest, invalidateCandidates, assignRouteEndpoint } from '../../src/sugarglider/web/static/state.js';
import { clearPointUndo, undoPointEdit, redoPointEdit } from '../../src/sugarglider/web/static/route_edit_history.js';

const profiles = Object.keys(PUBLIC_PROFILE_METADATA);
const delta = metres => metres / 6371008.8 * 180 / Math.PI;
const assert = (value, message) => { if (!value) throw Error(message); };
const equal = (a, b, message) => assert(JSON.stringify(a) === JSON.stringify(b), `${message}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`);
export const samples = [];
export function snapRequest({ startPolicy = 'near', endPolicy = 'near', profile = 'trail_run', loop = false, auto = false } = {}) {
  return { schema_version: 1, kind: auto ? 'auto_tour' : 'waypoint_route', name: 'Synthetic snapping',
    topology: loop || auto ? 'loop' : 'point_to_point', start: {lat:0,lon:0,name:'Start'},
    end: loop || auto ? null : {lat:0,lon:.03,name:'End'}, routing_profile:profile,candidate_count:1,seed:0,
    endpoint_snap_policy:{start:startPolicy,end:endPolicy},
    distance_objective:{target_m:4000,tolerance_m:1000,maximum_m:null,priority:'flexible'},
    preferences:{nature:'off',path_selection:'shortest',loop_geometry:'off',
      ...(auto ? {scenic:'off',drinking_water:'off',direction:'any'} : {})},
    ...(auto ? {hard_waypoints:[],requested_stops:[],preferred_discovered_poi_ids:[],free_poi_spur_physical_m:200}
      : {waypoints:loop ? [{id:'interior',name:'Interior',coordinate:{lat:.01,lon:.02,name:'Interior'},constraint_strength:'exact',access_search_radius_m:500,maximum_best_effort_distance_m:null,approach_override:null}] : [],waypoint_order:'fixed'}) };
}
export function snappedReply(input, { start = 0, end = 0, interior = 0, pack = 'synthetic-pack' } = {}) {
  const points = structuredClone(input.points);
  points[0].lat += delta(start); points.at(-1).lat += delta(end);
  if (interior && points.length > 2) points[1].lat += delta(interior);
  const geometry = points.flatMap((p, i) => i ? [[(points[i-1].lon+p.lon)/2+.00001,(points[i-1].lat+p.lat)/2], [p.lon,p.lat]] : [[p.lon,p.lat]]);
  return {schema_version:1,request_id:'synthetic-native',type:'local_route_result',profile:input.profile,
    engine:'valhalla-mobile',engine_version:'synthetic',pack_id:pack,distance_m:4000,duration_s:1800,
    geometry,snapped_points:points,measurements:{cold_start:false,engine_initialization_ms:0,route_ms:1,
      memory_before_initialization_bytes:0,memory_after_initialization_bytes:0,memory_after_route_bytes:0}};
}
export async function runEndpointSnappingHarness() {
  const cases = [];
  const publisher = createLocalPlanPublisher({ lifecycleTarget:null });
  async function generate(request, options, transform = reply => reply) {
    let calls = 0;
    const planner = createLocalPlanner({publisher,lifecycleTarget:null,bridge:{
      capabilities:async()=>({enabled:true,installed_pack_count:1,supported_profile_ids:profiles}),
      route:async input=>{ calls++; return transform(snappedReply(input,options)); },
    }});
    const before = JSON.stringify(request);
    const result = await planner.generate(request);
    equal(JSON.stringify(request), before, 'request is unchanged');
    assert(calls <= (request.kind === 'auto_tour' ? 24 : 16), 'strict route budget');
    return result;
  }
  try {
    for (const profile of profiles) for (const endpoint of ['start','end']) for (const policy of ['near','exact']) {
      for (const distance of [0,24.9,25,25.1,89.2,149.9,150,150.1,5000]) {
        const request = snapRequest({profile,startPolicy:endpoint==='start'?policy:'near',endPolicy:endpoint==='end'?policy:'near'});
        const result = await generate(request,{[endpoint]:distance});
        const candidate = result.candidates[0], accepted = distance <= (policy==='near'?150:25);
        assert(Boolean(candidate)===accepted, `${profile} ${endpoint} ${policy} ${distance} publication`);
        if (candidate) {
          const adjustments=candidate.diagnostics.details.local_routing.endpoint_adjustments;
          const item=adjustments[endpoint==='start'?0:1];
          assert(Math.abs(item.distance_m-distance)<1e-6,'measured graph-derived displacement');
          equal(item.status,distance>25?'adjusted':'reached','truthful adjustment status');
          equal(candidate.compromises.filter(c=>c.code==='endpoint_adjusted').length,distance>25?1:0,'canonical persistent warning');
          const gpx=await exportCanonicalCandidate(candidate).blob.text();
          const doc=new DOMParser().parseFromString(gpx,'application/xml'), points=[...doc.getElementsByTagName('trkpt')];
          equal(points.length,candidate.route.geometry.length,'connector adds no GPX vertices');
          for (const index of [0,points.length-1]) {
            assert(Math.abs(Number(points[index].getAttribute('lat'))-candidate.route.geometry[index][1])<1e-8,'GPX routed endpoint');
          }
          equal(doc.getElementsByTagName('trk').length,1,'one track'); equal(doc.getElementsByTagName('trkseg').length,1,'one segment');
          assert(!doc.getElementsByTagName('rte').length&&!doc.getElementsByTagName('extensions').length,'clean GPX');
          if (endpoint==='start'&&distance===89.2&&policy==='near') samples.push({request,result});
        } else if (policy==='near') {
          const proposals=result.search_diagnostics.details.local_planning.endpoint_proposals;
          assert(proposals.length===1&&proposals[0].endpoint===endpoint,'large proposal remains outside successful routes');
        }
        cases.push(`${profile}/${endpoint}/${policy}/${distance}`);
      }
    }
    const mixed=await generate(snapRequest({endPolicy:'exact'}),{start:240,end:89.2});
    assert(!mixed.candidates.length&&!mixed.search_diagnostics.details.local_planning.endpoint_proposals.length,'strict failure cannot be hidden by another endpoint proposal');
    const both=await generate(snapRequest(),{start:89.2,end:149.9});
    equal(both.candidates[0].compromises.filter(c=>c.code==='endpoint_adjusted').length,2,'both endpoints warned');
    for (const auto of [false,true]) for (const profile of profiles) {
      const request=snapRequest({auto,loop:true,profile});
      for (const [start,end,accepted] of [[89.2,89.2,true],[149.9,149.9,true],[150,150,true],[89.2,0,false],[89.2,120,false],[150.1,150.1,false]]) {
        const result=await generate(request,{start,end});
        assert(Boolean(result.candidates.length)===accepted,`${auto?'Auto Tour':'Waypoint loop'} ${start}/${end} closure`);
        if (start===89.2&&end===0) assert(!result.search_diagnostics.details.local_planning.endpoint_proposals.length,'invalid closure cannot propose endpoint');
      }
      const exact=await generate({...request,endpoint_snap_policy:{start:'exact',end:'near'}},{start:89.2,end:89.2});
      assert(!exact.candidates.length,'loop return uses exact Start policy');
      cases.push(`${auto?'auto':'waypoint'}/${profile}/loop-outgoing-return-closure`);
    }
    for (const distance of [299.9,300,300.1]) {
      const result=await generate(snapRequest({loop:true}),{start:89.2,end:89.2,interior:distance});
      equal(Boolean(result.candidates.length),distance<=300,`interior remains 300 m: ${distance}`);
    }
    for (const mutate of [reply=>({...reply,snapped_points:[]}),reply=>({...reply,snapped_points:[{lat:NaN,lon:0},...reply.snapped_points.slice(1)]}),reply=>({...reply,snapped_points:undefined}),reply=>({...reply,profile:'wrong'}),reply=>({...reply,geometry:[[5,5],...reply.geometry.slice(1)]})]) {
      const result=await generate(snapRequest(),{start:89.2},mutate);
      assert(!result.candidates.length&&!result.search_diagnostics.details.local_planning.endpoint_proposals.length,'invalid native reply cannot authorize candidate or adoption');
    }
    const unavailable=await generate(snapRequest(),{},()=>({schema_version:1,request_id:'failure',type:'local_route_failure',code:'no_route'}));
    assert(!unavailable.candidates.length&&!unavailable.search_diagnostics.details.local_planning.endpoint_proposals.length,'no route has no guessed proposal');
    cases.push('invalid-native-no-route-interior-boundaries');
    const exact=snapRequest();delete exact.endpoint_snap_policy;
    const original=await generate(exact,{start:89.2});assert(!original.candidates.length,'missing policy preserves strict intent');
    restoreEndpointSnapIntent(exact,exact.start,exact.end);equal(exact.start.snapPolicy,'exact','restored old strict intent');
    for (const value of [null,{},'near',{start:'near',end:'bad'},{start:'near',end:'near',unknown:true}]) {
      let error;try {endpointSnapPolicy(value);}catch(e){error=e;}assert(error?.code==='invalid_endpoint_snap_policy','malformed policy rejected');
    }
    const first=samples[0], candidate=first.result.candidates[0], adjusted=candidate.diagnostics.details.local_routing.endpoint_adjustments.filter(i=>i.status==='adjusted');
    const root=document.createElement('section');document.body.append(root);let shown,moved,used;
    const callbacks={profileLabel:'Trail run',disabled:false,onShow:item=>shown=item,onMove:item=>moved=item,onUse:item=>used=item};
    renderEndpointAdjustments(root,adjusted,callbacks);
    assert(root.textContent.includes('Start adjusted by 89 m'),'accepted route gets persistent compact warning');
    root.querySelector('summary').click();
    root.querySelector('[data-adjustment-action="start-show"]').click();equal(shown,adjusted[0],'show adjustment');
    root.querySelector('[data-adjustment-action="start-move"]').click();equal(moved,adjusted[0],'move original endpoint');
    root.querySelector('[data-adjustment-action="start-use"]').click();equal(used,adjusted[0],'explicit use');
    renderEndpointAdjustments(root,[],callbacks);assert(root.hidden&&!root.childNodes.length,'candidate change removes stale disclosure');
    const proposal=(await generate(snapRequest(),{start:240})).search_diagnostics.details.local_planning.endpoint_proposals;
    renderEndpointAdjustments(root,proposal,callbacks);assert(root.textContent.includes('No route has been accepted')&&root.querySelector('details').open,'large proposal requires explicit review');
    // Real shared point edit mechanism, existing undo, canonical serialization, no generation.
    Object.assign(state,{planningMode:'waypoint_route',planningStrategy:'waypoint_route',points:[],waypointPoints:[],generationResult:first.result,generationSourceRequest:first.request,
      selectedSignature:candidate.id,request:{status:'success',id:1},waypointEndpoints:{start:{...first.request.start,snapPolicy:'near'},end:{...first.request.end,snapPolicy:'exact'},routeTopology:'point_to_point'}});
    clearPointUndo();
    const prior=state.waypointEndpoints.start.lat;
    assert(replaceResolvedRouteLocation({endpoint:'start'},proposal[0].routed_coordinate,{assignEndpoint:(kind,point)=>assignRouteEndpoint(state.waypointEndpoints,kind,point)}),'adoption through normal edit mechanism');
    invalidateCandidates(); assert(!state.generationResult,'adoption invalidates candidates');
    equal(currentPlanRequest().start.lat,proposal[0].routed_coordinate.lat,'updated canonical request');
    equal(currentPlanRequest().endpoint_snap_policy,{start:'near',end:'exact'},'both endpoint policies serialized');
    assert(undoPointEdit()&&state.waypointEndpoints.start.lat===prior,'undo adoption');assert(redoPointEdit(),'redo adoption');
    root.remove();cases.push('persistent-warning-large-proposal-normal-history-canonical-intent');
    // Current request lifecycle must discard even a valid accepted adjustment after cancellation/region switch.
    let finish; const planner=createLocalPlanner({publisher,lifecycleTarget:null,bridge:{capabilities:async()=>({enabled:true,installed_pack_count:1,supported_profile_ids:profiles}),route:input=>new Promise(resolve=>{finish=()=>resolve(snappedReply(input,{start:89.2}));})}});
    const controller=new AbortController(), pending=planner.generate(snapRequest(),controller.signal).then(()=>null,e=>e);
    while(!finish) await new Promise(resolve=>setTimeout(resolve,0));controller.abort();finish();assert((await pending).name==='AbortError','cancelled reply cannot publish');
    const fixture=await (await fetch('/tests/fixtures/pr40_regional_data.json')).json();
    const reference=await regionalRoutingReference(fixture.manifest);
    const mismatch=createLocalPlanner({publisher,lifecycleTarget:null,withRegion:async run=>run({bridge:{capabilities:async()=>({enabled:true,installed_pack_count:1,supported_profile_ids:profiles}),route:input=>snappedReply(input,{start:89.2,pack:'wrong-graph'})},reference})});
    const error=await mismatch.generate(snapRequest()).then(()=>null,e=>e);assert(error,'graph identity cannot publish');
    cases.push('cancelled-adjustment-and-graph-identity-rejection');
    return cases;
  } finally { publisher.invalidate(); }
}
