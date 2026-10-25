// Synthetic proposal/location records only. No model account, native geometry or regional data.
import { parseAdventureProposal, adventureWishCapabilities, ADVENTURE_SCHEMA, ADVENTURE_INSTRUCTIONS } from '../../src/sugarglider/web/static/adventure_proposal.js';
import { groundAdventurePlaces } from '../../src/sugarglider/web/static/adventure_grounding.js';
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
 const mutations={unknown:v=>v.geometry=[],string_coordinate:v=>v.places[0].location.lat='0.02',range:v=>v.places[0].location.lon=181,
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
 const options={session,reference:identity,start:valid.intent.start,citations:[{url:'https://example.invalid/source'}],researched:true};
 const grounded=await groundAdventurePlaces(valid,options);assert(grounded.places[0].status==='grounded','local id grounding');assert(grounded.places[0].access_status==='unknown','OSM is not access proof');
 const conflicting={...session,queryPois:async()=>({identity,requested:[{id:'node/1',feature:{...feature,category:'cafe'}}],features:[]})};assert((await groundAdventurePlaces(valid,{...options,session:conflicting})).places[0].status==='identity_conflict','wrong mapped category cannot become a visited historical place');cases.push('mapped_identity_category_conflict_stays_unresolved');
 const water=structuredClone(syntheticAdventure);water.places[0].category='water';
 for(const potability of ['verified','unknown','non_potable']){const waterSession={...session,queryPois:async()=>({identity,requested:[{id:'node/1',feature:{...feature,category:'fountain',potability}}],features:[]})};const result=(await groundAdventurePlaces(parse(water),{...options,session:waterSession})).places[0];assert(result.local_potability===potability&&result.status===(potability==='non_potable'?'non_potable':'grounded'),'water distinctions remain explicit');}cases.push('water_potability_remains_distinct_from_access_and_arrival');
 assert(grounded.places[0].proposed_coordinate.lat===.02&&grounded.places[0].routing_coordinate.lat===.0201,'proposed and approach distinct');
 assert(grounded.places[0].sources[0].retrieved,'actual citation evidence retained');cases.push('local-grounding-preserves-coordinate-access-and-provenance');
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
