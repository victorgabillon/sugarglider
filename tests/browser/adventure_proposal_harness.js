// Synthetic proposal/location records only. No model account, native geometry or regional data.
import { parseAdventureProposal, adventureWishCapabilities, ADVENTURE_SCHEMA, ADVENTURE_INSTRUCTIONS } from '../../src/sugarglider/web/static/adventure_proposal.js';
import { groundAdventurePlaces, resolveAdventureEndpoint, nearbyAdventurePlaceContext, ADVENTURE_CONTEXT_PLACE_LIMIT } from '../../src/sugarglider/web/static/adventure_grounding.js';
import { createAdventureModel } from '../../src/sugarglider/web/static/adventure_model.js';
import { state } from '../../src/sugarglider/web/static/state.js';
const assert = (ok, message) => { if (!ok) throw Error(message); };
export const syntheticAdventure = {
 format:'sugarglider_ai_adventure',version:1,name:'Synthetic forest adventure',interpretation:'A synthetic historical loop.',
 intent:{activity:'trail_run',topology:'loop',start:{name:'Synthetic Start',lat:.01,lon:.01},end:null,target_distance_m:10000,tolerance_m:1000,alternatives:3,order:'optimize'},
 wishes:[{metric:'woodland',goal:'maximize',value:null,importance:'high'},{metric:'historical_places',goal:'maximize',value:null,importance:'high'},{metric:'asphalt',goal:'minimize',value:null,importance:'medium'}],
 places:[{id:'castle',location:{name:'Synthetic Castle',lat:.02,lon:.02},osm_id:'node/1',wikidata_id:null,category:'historical',importance:'prefer',reason:'Synthetic historical interest',anecdote:'Synthetic test story, not factual history.',sources:[{title:'Synthetic source',url:'https://example.invalid/source'}],confidence:'located',access:'unknown',priority:8}],clarifications:[]
};
export async function runAdventureProposalHarness(){
 const before=JSON.stringify(state),cases=[];
 const parse=x=>parseAdventureProposal(JSON.stringify(x));
 const valid=parse(syntheticAdventure);assert(Object.isFrozen(valid.places[0]),'immutable proposals');cases.push('bounded-immutable-contract');
 const mutations={unknown:v=>v.geometry=[],loop_destination:v=>v.intent.end={...v.intent.start},string_coordinate:v=>v.places[0].location.lat='0.02',range:v=>v.places[0].location.lon=181,
  paired_null:v=>v.places[0].location.lat=null,missing:v=>delete v.intent,identity_array:v=>v.places[0].osm_id=['node/1'],
  malicious_link:v=>v.places[0].sources[0].url='javascript:alert(1)',html_story:v=>v.places[0].anecdote='<script>native()</script>',
  duplicate_places:v=>v.places.push(structuredClone(v.places[0])),duplicate_objective:v=>v.wishes.push(structuredClone(v.wishes[0])),
  fake_located:v=>{v.places[0].location.lat=null;v.places[0].location.lon=null},fractional_alternatives:v=>v.intent.alternatives=1.2,
  too_many:v=>v.places=Array.from({length:21},(_,i)=>({...v.places[0],id:'p'+i}))};
 for(const[name,change]of Object.entries(mutations)){const v=structuredClone(syntheticAdventure);change(v);let rejected=false;try{parse(v)}catch{rejected=true}assert(rejected,name);cases.push(name)}
 for(const raw of ['{broken',' '.repeat(65537),'{"deep":'+ '['.repeat(1000)+'0'+']'.repeat(1000)+'}']){let rejected=false;try{parseAdventureProposal(raw)}catch{rejected=true}assert(rejected,'invalid-json-bounds')}
 const unresolved=structuredClone(syntheticAdventure);unresolved.intent.start=null;unresolved.places[0].location.lat=null;unresolved.places[0].location.lon=null;unresolved.places[0].confidence='unresolved';
 assert(parse(unresolved).intent.start===null,'missing start stays missing');
 assert(adventureWishCapabilities(valid).every(w=>w.status==='unavailable'),'capabilities require runtime evidence');
 assert(adventureWishCapabilities(valid,{nature:true,places:true}).filter(w=>w.status==='optimization_preference').length===2,'real capabilities classified');
 assert(!ADVENTURE_INSTRUCTIONS.includes('API key')&&ADVENTURE_INSTRUCTIONS.includes('never geometry'),'central prompt boundary');
 assert(ADVENTURE_SCHEMA.properties.places.maxItems===20,'schema agrees on bound');
 const feature={id:'node/1',display_name:'Synthetic Castle',category:'castle',coordinate:{lat:.02,lon:.02},access_status:'unknown',potability:'not_applicable',approach_candidates:[{id:'entrance',coordinate:{lat:.0201,lon:.02},access:'public',semantic_distance_m:11,arrival_tolerance_m:25,kind:'mapped_entrance'}]};
 const identity={region_id:'synthetic',build_id:'synthetic-build',bounds:[0,0,.1,.1]};let queries=0;
 const session={identity,queryPois:async q=>{queries++;return{identity,requested:q.requested_ids.map(id=>({id,feature:id===feature.id?feature:null})),features:[feature]}},searchPlaceNames:async()=>({identity,results:[]})};
 const records=Array.from({length:64},(_,i)=>({...structuredClone(feature),id:'node/'+(100+i),display_name:'Synthetic landmark '+i,group:'scenic',tags:[['private_note','must not leave the index']]}));
 records[0].access_status='private';records[1].access_status='restricted';records[2].potability='non_potable';records[3].approach_candidates=[];records[4].coordinate={lat:2,lon:2};
 let contextQueries=0;
 const contextSession={...session,queryPois:async query=>{contextQueries++;assert(query.limit===64&&query.radius_m===30000&&query.requested_ids.length===0,'one bounded local shortlist query');return{identity,features:records}}};
 const localContext=await nearbyAdventurePlaceContext({session:contextSession,reference:identity,center:valid.intent.start});
 assert(localContext.length===ADVENTURE_CONTEXT_PLACE_LIMIT&&Object.isFrozen(localContext[0]),'bounded immutable public context');
 assert(localContext.every(row=>Number(row.osm_id.split('/')[1])>=105),'private restricted nonpotable uncovered and inaccessible records excluded');
 assert(!JSON.stringify(localContext).includes('private_note')&&!JSON.stringify(localContext).includes('approach_candidates'),'only compact public identity/location/category facts leave the index');
 assert((await nearbyAdventurePlaceContext({session:contextSession,reference:identity,center:null})).length===0&&contextQueries===1,'no default centre or index query when no endpoint is chosen');
 const contextAbort=new AbortController();contextAbort.abort();let contextCancelled=false;try{await nearbyAdventurePlaceContext({session:contextSession,reference:identity,center:valid.intent.start,signal:contextAbort.signal})}catch(e){contextCancelled=e.name==='AbortError'}assert(contextCancelled&&contextQueries===1,'cancelled context cannot query');
 let changedContext=false;try{await nearbyAdventurePlaceContext({session:{...contextSession,identity:{...identity,build_id:'changed'}},reference:identity,center:valid.intent.start})}catch{changedContext=true}assert(changedContext&&contextQueries===1,'context retains exact regional identity');
 cases.push('nearby_model_context_is_bounded_local_identity_checked_and_token_free');
 const options={session,reference:identity,start:valid.intent.start,citations:[{url:'https://example.invalid/source'}],researched:true};
 const endpoints={session,reference:identity};
 const proposed={name:'Synthetic endpoint',lat:.02,lon:.02};
 const exactSession={...session,searchPlaceNames:async()=>({identity,results:[{name:'Synthetic endpoint',lat:.0201,lon:.02}]})};
 const resolved=await resolveAdventureEndpoint(proposed,{...endpoints,session:exactSession});
 assert(resolved.evidence==='unique_exact_local_name'&&resolved.coordinate.lat===.0201&&resolved.proposed_coordinate.lat===.02,'resolved and proposed endpoint coordinates remain distinct');
 const ambiguousSession={...session,searchPlaceNames:async()=>({identity,results:[{name:proposed.name,lat:.02,lon:.02},{name:proposed.name,lat:.03,lon:.03}]})};
 assert(await resolveAdventureEndpoint(proposed,{...endpoints,session:ambiguousSession})===null,'model coordinates cannot resolve ambiguous local names');
 assert(await resolveAdventureEndpoint({...proposed,lat:1},endpoints)===null,'out-of-region endpoint rejected');
 assert(await resolveAdventureEndpoint({...proposed,lat:.09}, {...endpoints,session:exactSession})===null,'conflicting local identity rejected');
 assert(await resolveAdventureEndpoint({...proposed,lat:null,lon:null},endpoints)===null,'unlocated name never becomes a guessed coordinate');
 const zero=await resolveAdventureEndpoint({name:'Origin',lat:0,lon:0},endpoints);
 assert(zero.coordinate.lat===0&&zero.coordinate.lon===0&&zero.evidence==='model_coordinate_unverified','zero coordinates remain valid but visibly unverified');
 const endpointAbort=new AbortController();endpointAbort.abort();let endpointCancelled=false;
 try{await resolveAdventureEndpoint(proposed,{...endpoints,signal:endpointAbort.signal})}catch(e){endpointCancelled=e.name==='AbortError'}assert(endpointCancelled,'cancelled endpoint resolution cannot proceed');
 cases.push('shared_endpoint_resolution_requires_review_and_preserves_ambiguity_coverage_and_evidence');
 const grounded=await groundAdventurePlaces(valid,options);assert(grounded.places[0].status==='grounded','local id grounding');assert(grounded.places[0].access_status==='unknown','OSM is not access proof');
 const conflicting={...session,queryPois:async()=>({identity,requested:[{id:'node/1',feature:{...feature,category:'cafe'}}],features:[]})};assert((await groundAdventurePlaces(valid,{...options,session:conflicting})).places[0].status==='identity_conflict','wrong mapped category cannot become a visited historical place');cases.push('mapped_identity_category_conflict_stays_unresolved');
 const water=structuredClone(syntheticAdventure);water.places[0].category='water';
 for(const potability of ['verified','unknown','non_potable']){const waterSession={...session,queryPois:async()=>({identity,requested:[{id:'node/1',feature:{...feature,category:'fountain',potability}}],features:[]})};const result=(await groundAdventurePlaces(parse(water),{...options,session:waterSession})).places[0];assert(result.local_potability===potability&&result.status===(potability==='non_potable'?'non_potable':'grounded'),'water distinctions remain explicit');}cases.push('water_potability_remains_distinct_from_access_and_arrival');
 assert(grounded.places[0].proposed_coordinate.lat===.02&&grounded.places[0].routing_coordinate.lat===.0201,'proposed and approach distinct');
 assert(grounded.places[0].sources[0].retrieved,'actual citation evidence retained');cases.push('local-grounding-preserves-coordinate-access-and-provenance');
 const tracked=await groundAdventurePlaces(valid,{...options,citations:[{url:'https://example.invalid/source?utm_source=openai'}]});
 assert(tracked.places[0].sources[0].retrieved&&tracked.places[0].story_status==='source_linked_ai_text','known provider tracking does not hide real citation evidence');
 for(const url of ['https://example.invalid/source?id=different&utm_source=openai','https://example.invalid/other?utm_source=openai','https://example.invalid/source?utm_source=someone-else']){
  assert(!(await groundAdventurePlaces(valid,{...options,citations:[{url}]})).places[0].sources[0].retrieved,'meaningful source URL differences remain distinct');
 }
 cases.push('citation_evidence_ignores_only_known_provider_tracking');
 const unverified=await groundAdventurePlaces(valid,{...options,citations:[]});assert(!unverified.places[0].sources[0].retrieved,'invented citations not upgraded');
 const distant=structuredClone(syntheticAdventure);distant.places[0].location.lat=.09;assert((await groundAdventurePlaces(parse(distant),options)).places[0].status==='ambiguous_location','distant id not substituted');
 const outside=structuredClone(syntheticAdventure);outside.places[0].location.lat=1;const oldQueries=queries;assert((await groundAdventurePlaces(parse(outside),options)).places[0].status==='outside_coverage'&&queries===oldQueries,'outside stops not queried');
 const restricted={...session,queryPois:async q=>({identity,requested:[{id:'node/1',feature:{...feature,access_status:'private'}}],features:[]})};assert((await groundAdventurePlaces(valid,{...options,session:restricted})).places[0].status==='access_restricted','private excluded');
 const aborted=new AbortController();aborted.abort();let cancelled=false;try{await groundAdventurePlaces(valid,{...options,signal:aborted.signal})}catch(e){cancelled=e.name==='AbortError'}assert(cancelled,'cancelled grounding');
 cases.push('grounding-rejects-restrictions-outside-distant-and-cancelled');
 let nativeCalls=[];
 const transport={nativeAvailable:true,cancelOwner(){},request:async(type,fields,options)=>{nativeCalls.push({type,fields});return options.parseReply(JSON.stringify({schema_version:1,request_id:'test',type:'chatgpt_result',result:{accounts:[],selected_account:null,models:[]},error:null}))}};
 const model=createAdventureModel({transport,origin:'https://appassets.androidplatform.net'});await model.status();assert(nativeCalls[0].type==='chatgpt_status','native model adapter');
 let remoteRejected=false;try{await createAdventureModel({transport,origin:'https://untrusted.invalid'}).status()}catch(e){remoteRejected=e.code==='unavailable'}assert(remoteRejected,'untrusted origin rejected');
 assert(JSON.stringify(state)===before,'no invalid proposal or grounding result corrupts current plan');cases.push('native-provider-origin-and-plan-preservation');
 return cases;
}
