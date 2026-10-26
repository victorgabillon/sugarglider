import {sampleElevationGeometry,elevationGeometryDigest} from '../../src/sugarglider/web/static/elevation_sampling.js';
import {createSelectedRouteElevation,createRouteElevationClient,parseRouteElevationReply,prepareRouteElevation} from '../../src/sugarglider/web/static/route_elevation.js';
import {regionalRoutingReference} from '../../src/sugarglider/web/static/regional_routing_reference.js';
import {createAdventureElevationSampler} from '../../src/sugarglider/web/static/adventure_elevation.js';
const assert=(v,m)=>{if(!v)throw Error(m);};const pause=()=>new Promise(r=>setTimeout(r,0));
async function until(check){for(let i=0;i<200;i++){if(check())return;await new Promise(r=>setTimeout(r,10));}throw Error('did not settle');}
async function rejected(action){assert(await action().then(()=>false,()=>true),'expected explicit rejection');}
export async function runElevationHarness(){
 const cases=[],geometry=[[2.08,48.88],[2.08,48.88],[2.09,48.89],[2.09,48.89]];
 const manifest=(await(await fetch('../fixtures/pr40_regional_data.json')).json()).manifest;
 const reference=await regionalRoutingReference(manifest);
 const vectors=await(await fetch('../fixtures/elevation/sampling-v1.json')).json();
 for(const v of vectors){const p=await sampleElevationGeometry(v.geometry,v.distance_m);assert(p.geometry_sha256===v.geometry_sha256,v.name+' digest');assert(p.samples.length===v.samples.length,v.name+' count');for(let i=0;i<p.samples.length;i++)for(let j=0;j<3;j++)assert(Math.abs(p.samples[i][j]-v.samples[i][j])<1e-7,v.name+' positions');}
 cases.push('python_binary_geometry_identity_and_pr88_sample_parity');
 for(const distance of [0.001,50,100,102350,102350.001,199999.9,200000]){const p=await sampleElevationGeometry(geometry,distance);assert(p.samples.length<=2048&&p.sampling_interval_m<=100,'budget');assert(p.samples[0][0]===0&&p.samples.at(-1)[0]===distance,'endpoints');for(let i=1;i<p.samples.length;i++)assert(p.samples[i][0]>p.samples[i-1][0]&&p.samples[i][0]-p.samples[i-1][0]<=100,'progress and gap');}
 cases.push('adaptive_200km_budget_below_100m_with_endpoints_and_repeated_vertices');
 for(const [g,d] of [[geometry,200001],[geometry,0],[[[0,0],[0,0]],100],[[[179,0],[-179,0]],100],[[[2,91],[2,90]],100],[Array(20001).fill([0,0]),100]])await rejected(()=>sampleElevationGeometry(g,d));
 cases.push('malformed_oversized_degenerate_and_dateline_inputs_explicit');
 const abort=new AbortController();abort.abort();await rejected(()=>prepareRouteElevation(geometry,100,abort.signal));
 const realWorker=await prepareRouteElevation(geometry,100,new AbortController().signal);assert(realWorker.samples.length===3,'real offthread sampling');
 cases.push('worker_sampling_and_preabort_termination');
 const golden=await(await fetch('../fixtures/elevation/contract-v1.json')).json();
 function reply(fields,name='summit'){
  const analysis=structuredClone(golden.find(g=>g.name===name).expected);analysis.source_sha256=reference.elevation.manifest.sha256;analysis.geometry_sha256=fields.geometry_sha256;analysis.height_reference='unresolved vertical datum; verified V2 elevation component manifest';analysis.routing_profile=fields.profile;
  return {schema_version:1,request_id:'web-'+ 'a'.repeat(32)+'-1',type:'local_elevation_result',elevation_version:1,operation_id:fields.operation_id,candidate_id:fields.candidate_id,regional_reference:structuredClone(reference),sampling_interval_m:50,sample_coordinates:fields.samples.map(s=>[s[2],s[1]]),analysis,measurements:{native_height_ms:1,analysis_ms:1,total_ms:2,pss_bytes:0,cold_start:false}};
 }
 const fields={elevation_version:1,operation_id:'e'.repeat(32),candidate_id:'geometry:'+'a'.repeat(64),profile:'hike',distance_m:100,regional_reference:reference,...await sampleElevationGeometry(geometry,100)};
 const documented=reply(fields);documented.analysis.height_reference="EGM96 orthometric metres; verified V2 elevation component manifest";
 assert(parseRouteElevationReply(JSON.stringify(documented))?.analysis.height_reference===documented.analysis.height_reference,'verified EGM96 reference accepted');
 documented.analysis.height_reference="IGN69 normal metres; IGN RGE ALTI 5 m; Licence Ouverte 2.0; verified V2 elevation component manifest";
 assert(parseRouteElevationReply(JSON.stringify(documented))?.analysis.height_reference===documented.analysis.height_reference,'verified IGN69 reference accepted without EGM96 relabel');
 cases.push('ign69_ground_model_reference_preserved');
 documented.analysis.height_reference="guessed datum";assert(parseRouteElevationReply(JSON.stringify(documented))===null,'unknown datum rejected');
 cases.push('documented_egm96_and_research_height_references_remain_explicit');
 assert(parseRouteElevationReply(JSON.stringify(reply(fields)))!==null,'valid reply');
 for(const change of [r=>r.analysis.total_ascent_m=-1,r=>r.analysis.samples[1].height_m=null,r=>r.analysis.segments[0].last_index=100,r=>r.regional_reference.elevation.component_id='../escape',r=>r.analysis.parameters.maximum_gap_m=500,r=>r.analysis.coverage='partial',r=>r.analysis.samples.push(r.analysis.samples[0])]){const r=reply(fields);change(r);assert(parseRouteElevationReply(JSON.stringify(r))===null,'bad reply rejected');}
 cases.push('strict_versioned_reply_null_coverage_parameters_and_segment_validation');
 const transport={request:async(type,input)=>reply(input)};
 const client=createRouteElevationClient({transport});assert(Object.isFrozen(await client.analyze(fields)),'immutable');
 const wrong=createRouteElevationClient({transport:{request:async(type,input)=>({...reply(input),candidate_id:'geometry:'+'f'.repeat(64)})}});await rejected(()=>wrong.analyze(fields));
 const partialFields={...fields,distance_m:200,...await sampleElevationGeometry(geometry,200)};
 const partial=reply(partialFields,'missing');assert(parseRouteElevationReply(JSON.stringify(partial))!==null&&partial.analysis.total_ascent_m===null,'partial totals remain null');
 cases.push('partial_coverage_keeps_only_observed_totals');
 cases.push('exact_candidate_region_geometry_and_sample_binding');
 const pending=[],states=[];let requests=0,cancels=0;
 const fake={analyze:async f=>{requests++;return new Promise(resolve=>pending.push({fields:f,resolve}));},cancel:async()=>{cancels++;}};
 const versions={withCommittedRegions:async action=>action([{region_id:manifest.region_id,status:'committed',manifest}])};
 const controller=createSelectedRouteElevation({versions,client:fake,prepare:async(g,d)=>sampleElevationGeometry(g,d),onChange:s=>states.push(s),lifecycleTarget:null,operationId:()=> 'e'.repeat(32)});
 const candidate=n=>({id:'geometry:'+n.repeat(64),route:{geometry,summary:{distance_m:100},routing_profile:'hike'},diagnostics:{details:{local_routing:{engine:'valhalla-mobile',regional_version:{region_id:manifest.region_id,build_id:manifest.build_id,routing_pack_id:reference.pack_id}}}}});
 const a=candidate('a'),b=candidate('b'),generation={};const before=JSON.stringify(a);
 controller.sync(a,generation,manifest.region_id);await until(()=>pending.length===1);
 controller.sync(b,generation,manifest.region_id);assert(controller.snapshot().candidate_id===b.id,'selection immediate');
 pending[0].resolve(reply(pending[0].fields));await until(()=>pending.length===2);assert(!states.some(s=>s.status==='ready'&&s.candidate_id===a.id),'old result never attached');
 pending[1].resolve(reply(pending[1].fields));await until(()=>controller.snapshot().status==='ready');assert(cancels===1,'native cancel sent');
 controller.sync(a,generation,manifest.region_id);await until(()=>pending.length===3);pending[2].resolve(reply(pending[2].fields));await until(()=>controller.snapshot().status==='ready');
 controller.sync(b,generation,manifest.region_id);await until(()=>controller.snapshot().status==='ready');assert(requests===3&&controller.snapshot().cache_hit,'completed exact key reused');
 controller.regionChanged(reference);controller.regionChanged({...reference,build_id:'f'.repeat(64)});assert(controller.snapshot().status==='idle','build replacement invalidates');
 assert(JSON.stringify(a)===before,'canonical candidate unchanged');cases.push('selection_stale_replies_drained_exact_cache_and_immutable_candidate');
 controller.sync(a,{},manifest.region_id);await until(()=>pending.length===4);controller.cancel();pending[3].resolve(reply(pending[3].fields));await pause();assert(controller.snapshot().status==='unavailable'&&controller.snapshot().diagnostic==='elevation_cancelled','explicit cancel stays unavailable');
 controller.sync(null,null,null);assert(controller.snapshot().status==='idle','editing invalidates');cases.push('regeneration_edit_and_explicit_cancel_cannot_republish_old_result');
 const events=new EventTarget();const life=createSelectedRouteElevation({versions,client:fake,prepare:async()=>realWorker,lifecycleTarget:events});life.sync(a,{},manifest.region_id);await until(()=>pending.length===5);events.dispatchEvent(new Event('pagehide'));pending[4].resolve(reply(pending[4].fields));await pause();assert(life.snapshot().status==='idle','page lifecycle');cases.push('pagehide_discards_inflight_results');
 const changed=createSelectedRouteElevation({versions,client:fake,prepare:async()=>realWorker,lifecycleTarget:null});changed.sync(a,{},'different-region');await until(()=>changed.snapshot().status==='unavailable');assert(requests===5,'region mismatch before native');cases.push('regional_build_and_selection_isolation');
 const batchCalls=[];
 const batchClient=createRouteElevationClient({transport:{request:async(type,input)=>{batchCalls.push(input);return reply(input);}}});
 let preparations=0;
 const sampler=createAdventureElevationSampler({client:batchClient,prepare:async(g,d,s)=>{preparations++;return prepareRouteElevation(g,d,s);},operationId:()=> 'e'.repeat(32)});
 const batchBefore=JSON.stringify([a,b]);
 const measured=await sampler.measure([a,b],reference,new AbortController().signal);
 assert(Object.keys(measured).length===2&&batchCalls.length===2,'bounded sequential native elevation batch');
 await sampler.measure([a,b],reference,new AbortController().signal);
 assert(batchCalls.length===2&&preparations===2,'one sampling and native analysis per retained identity across rounds');
 assert(JSON.stringify([a,b])===batchBefore,'batch elevation leaves canonical candidates unchanged');
 await rejected(()=>sampler.measure([{...a,diagnostics:{details:{local_routing:{regional_version:{region_id:'wrong'}}}}}],reference));
 assert(batchCalls.length===2,'region mismatch before native work');
 sampler.clear();cases.push('adventure_elevation_batch_reuses_strict_client_worker_and_source_bound_cache');
 let finishNative,finishCancel,cancelRequested=false,settled=false;
 const draining=createAdventureElevationSampler({prepare:async()=>realWorker,client:{analyze:()=>new Promise(resolve=>{finishNative=resolve;}),cancel:()=>{cancelRequested=true;return new Promise(resolve=>{finishCancel=resolve;});}},operationId:()=> 'e'.repeat(32)});
 const batchAbort=new AbortController();
 const batchOutcome=draining.measure([a],reference,batchAbort.signal).then(()=>{throw Error('cancelled result accepted');},()=>{settled=true;});
 await until(()=>Boolean(finishNative));batchAbort.abort();await until(()=>cancelRequested);
 await rejected(()=>draining.measure([b],reference));
 finishNative({});await pause();assert(!settled,'native cancel must drain too');finishCancel({});await batchOutcome;
 assert(settled,'cancelled batch settles only after native and cancel drain');draining.clear();cases.push('adventure_elevation_cancellation_drains_before_replacement');
 return cases;
}
