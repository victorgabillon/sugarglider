import { state, saveActivePoints, assignRouteEndpoint, currentPlanRequest, invalidateCandidates, isImmutableSnapshotDisplay } from '../../src/sugarglider/web/static/state.js';
import { addResolvedRouteLocation } from '../../src/sugarglider/web/static/route_point_acquisition.js';
import { changeMapTopology } from '../../src/sugarglider/web/static/automatic_intent.js';
import { clearPointUndo, undoPointEdit, redoPointEdit, pointUndoLabel, pointRedoLabel } from '../../src/sugarglider/web/static/route_edit_history.js';
import { resolvedPoiLocation } from '../../src/sugarglider/web/static/poi_route_location.js';
import { createPlaceDetails, createPassThroughAction } from '../../src/sugarglider/web/static/place_presentation.js';
import { initializeLocationSearchDialog } from '../../src/sugarglider/web/static/location_search_dialog.js';
import { initializeMap, renderPois, placeMapDiagnostics, mapPresentationDiagnostics } from '../../src/sugarglider/web/static/map.js';

const assert=(v,m)=>{if(!v)throw Error(m)}, same=(a,b,m)=>assert(JSON.stringify(a)===JSON.stringify(b),m);
const until=async p=>{for(let i=0;i<300;i++){if(p())return;await new Promise(r=>setTimeout(r,25))}throw Error('Timed out')};
const feature=(id,category='ice_cream',potability='not_applicable')=>({id,category,potability,display_name:'Named '+id,coordinate:{lat:.011+({water:1,scenic:-1,private:-2,nonpotable:-3}[id]??0)*.002,lon:.01},tags:[['opening_hours','Mo-Su 10:00-20:00']],access_status:'public',osm_id:123,osm_type:'node',warnings:[]});
const P=feature('ice'), A={name:'Start',lat:.009,lon:.01}, B={name:'Old End',lat:.01,lon:.009};

export async function run(){
 const initial=structuredClone(state), cases=[], roots=[];
 const reset=()=>{Object.assign(state,structuredClone(initial));state.config={max_required_points:30};state.routingProfile='trail_run';clearPointUndo()};
 const endpoints=()=>state.planningMode==='auto_tour'?state.autoTour:state.waypointEndpoints;
 const assign=(kind,p)=>{saveActivePoints();assignRouteEndpoint(endpoints(),kind,p);if(state.planningMode==='auto_tour'&&kind==='start')state.points=[p,...state.autoTour.hardPoints].filter(Boolean)};
 const request=()=>endpoints().start?currentPlanRequest():null;
 const add=p=>addResolvedRouteLocation(p,{assignEndpoint:assign});
 const canPassThrough=f=>!isImmutableSnapshotDisplay()&&!['running','reversing'].includes(state.request.status)&&resolvedPoiLocation(f)!==null;
 const onPassThrough=f=>{if(!canPassThrough(f))return false;const changed=add(resolvedPoiLocation(f));if(changed)invalidateCandidates();return changed};
 const action=f=>createPassThroughAction(f,{canPassThrough,onPassThrough});
 const setup=scenario=>{reset();if(scenario.startsWith('open'))changeMapTopology('point_to_point');if(scenario!=='start')add(A);if(scenario==='open_extension')add(B)};
 try{
  same(resolvedPoiLocation(P),{name:P.display_name,...P.coordinate},'Only name and coordinate');cases.push('metadata_whitelist_and_useful_name');
  for(const access of ['public','unknown'])assert(resolvedPoiLocation({...P,access_status:access}),'Allowed access');cases.push('public_and_unknown_access_allowed');
  for(const access of ['private','restricted','no',undefined])assert(!resolvedPoiLocation({...P,access_status:access}),'No route-add for access '+access);cases.push('private_restricted_invalid_access_hidden');
  assert(!resolvedPoiLocation({...P,potability:'non_potable'}),'Nonpotable hidden');cases.push('nonpotable_prominent_action_hidden');
  for(const coordinate of [{lat:91,lon:0},{lat:0,lon:181},{lat:NaN,lon:1},{lat:'1',lon:2},{lat:1,lon:Infinity},null])assert(!resolvedPoiLocation({...P,coordinate}),'Invalid coordinate');cases.push('finite_numeric_coordinate_ranges_enforced');
  for(const name of ['', ' ', 'x'.repeat(201), 'bad\nname', null])assert(!resolvedPoiLocation({...P,display_name:name}),'Invalid name');cases.push('bounded_nonempty_plain_text_name');
  reset();const button=action(P);assert(button.type==='button'&&button.textContent==='Pass through here'&&!button.hidden,'Semantic action');document.body.append(button);roots.push(button);button.focus();assert(document.activeElement===button,'Focusable');cases.push('explicit_real_button_keyboard_focus');
  for(const status of ['running','reversing']){state.request.status=status;assert(action(P).hidden,'Disabled editing '+status);const before=request();button.click();same(request(),before,'Stale action guarded')};cases.push('running_reversing_hidden_and_stale_action_guarded');
  reset();state.savedRouteSnapshotDisplay=true;state.savedRouteSnapshot={};assert(action(P).hidden,'Saved immutable');cases.push('saved_snapshot_action_hidden');
  reset();state.outingDisplay=true;state.outingSnapshot={};assert(action(P).hidden,'Outing immutable');cases.push('outing_view_action_hidden');
  const html=await(await fetch('../../src/sugarglider/web/static/index.html')).text();window.poiCanonicalEvidence=[];
  for(const scenario of ['start','loop_stop','open_end','open_extension']){
   setup(scenario);add(resolvedPoiLocation(P));const direct=request();
   setup(scenario);action(P).click();const poi=request();
   setup(scenario);const root=new DOMParser().parseFromString(html,'text/html').querySelector('#location-search-dialog');document.body.append(root);roots.push(root);
   const dialog=initializeLocationSearchDialog({root,config:()=>({available:false}),canEdit:()=>true,
    search:async(_,options)=>{const local=[{...resolvedPoiLocation(P),source:'local',secondaryLabel:'Mapped place'}];options.onLocal({results:local,message:'Mapped places'});return {local,remote:[],remoteMessage:'Unavailable'}},onSelect:(_,location)=>add(location)});
   dialog.open();root.querySelector('input').value='Named ice';root.querySelector('form').requestSubmit();await until(()=>root.querySelector('#location-search-local button'));root.querySelector('#location-search-local button').click();const search=request();
   same(poi,direct,'POI equals direct '+scenario);same(search,direct,'Search equals direct '+scenario);assert(!JSON.stringify(poi).includes('osm_id')&&!JSON.stringify(poi).includes('ice_cream'),'No metadata');window.poiCanonicalEvidence.push({scenario,direct,poi,search,equal:true});cases.push('canonical_search_poi_direct_'+scenario);root.remove();
   const after=request();assert(undoPointEdit(),'Undo');assert(redoPointEdit(),'Redo');same(request(),after,'Exact restored');cases.push('undo_redo_'+scenario);
  }
  setup('open_extension');const before=request(),oldEnd=structuredClone(endpoints().end);action(P).click();assert(endpoints().end.name===P.display_name,'Named new End');same(state.points.at(-1),oldEnd,'Demoted old End identity');assert(undoPointEdit(),'Undo extension');same(request(),before,'Exact old End restored');cases.push('open_extension_preserves_old_end_exactly');
  add(A);assert(!redoPointEdit(),'New edit clears redo');cases.push('new_edit_clears_redo');
  reset();const twice=action(P);twice.click();twice.dispatchEvent(new MouseEvent('click'));assert(endpoints().start.name===P.display_name&&!state.autoTour.hardPoints.length,'One acquisition');assert(undoPointEdit()&&!undoPointEdit(),'One history entry');cases.push('rapid_double_activation_one_edit');
  reset();state.generationResult={candidates:[]};state.generationSourceRequest=request();action(P).click();assert(!state.generationResult&&!state.generationSourceRequest&&state.request.status!=='running','No auto Generate');cases.push('candidate_invalidation_without_generation');
  reset();const rich=createPlaceDetails(P,{onCenter:()=>{},canPassThrough,onPassThrough});assert(rich.querySelector('.place-pass-through')&&rich.querySelector('.place-center')&&rich.querySelector('img').src.endsWith('sugarglider-ice-cream-pin.png'),'Artwork and both actions');cases.push('rich_ice_cream_artwork_center_and_pass_action');
  let ready=false,selected=null,placements=0,preferCalls=0;const features=[P,feature('water','drinking_water','verified'),feature('scenic','viewpoint'),{...feature('private'),access_status:'private'},{...feature('nonpotable','drinking_water','non_potable')}];
  const choose=id=>{selected=id;renderPois(features,id,choose,{onDeselect:()=>choose(null),canPassThrough,onPassThrough:f=>{const changed=onPassThrough(f);if(changed)choose(null);return changed},onPrefer:()=>preferCalls++})};
  initializeMap({initial_center:[.01,.011],initial_zoom:15,offline_mode:true},{onReady:()=>{ready=true;choose(null)},onMapClick:()=>placements++,onError:m=>{throw Error(m)}});await until(()=>ready&&['ice','water'].every(id=>placeMapDiagnostics().priorityMarkerIds.includes(id)));
  for(const id of ['ice','water','scenic']){
   reset();state.addPointMode=true;const before={request:request(),undo:pointUndoLabel(),redo:pointRedoLabel(),placement:state.addPointMode};choose(id);
   same({request:request(),undo:pointUndoLabel(),redo:pointRedoLabel(),placement:state.addPointMode},before,'Inspect preserves full intent/history/placement');assert(!placements,'No map placement');cases.push(id+'_inspect_only_and_action_present');
   const pass=document.querySelector('.maplibregl-popup .place-pass-through');assert(pass&&!pass.hidden,'Available');assert(Boolean(document.querySelector('.popup-prefer'))===(id!=='ice'),'Prefer separate');pass.click();assert(!selected&&!document.querySelector('.maplibregl-popup'),'Closes selected POI');cases.push(id+'_explicit_action_normal_selection_transition');
  }
  reset();choose('water');const openPopup=document.querySelector('.maplibregl-popup');state.request.status='running';choose('water');assert(document.querySelector('.place-pass-through').hidden&&document.querySelector('.maplibregl-popup')===openPopup,'Live availability no popup replacement');cases.push('existing_popup_updates_editability_without_recreation');
  reset();choose('water');document.querySelector('.popup-prefer').click();assert(preferCalls===1&&!endpoints().start,'Prefer not pass-through');cases.push('prefer_remains_distinct_soft_callback');
  for(const id of ['private','nonpotable']){choose(id);assert(document.querySelector('.place-pass-through').hidden,'Hidden in display '+id)}cases.push('unsafe_displayable_pois_have_no_route_add');
  choose('ice');const popup=document.querySelector('.maplibregl-popup'),canvas=document.querySelector('canvas');await until(()=>{const bounds=popup.getBoundingClientRect(),viewport=canvas.getBoundingClientRect();return bounds.top>=viewport.top+10&&bounds.bottom<=viewport.bottom-58});popup.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));assert(!selected&&document.activeElement===canvas,'Escape and map focus');cases.push('priority_clamping_escape_and_focus_retained');
  choose('ice');const zoom=mapPresentationDiagnostics().zoom,point=placeMapDiagnostics().positions.find(f=>f.id==='ice').point,r=canvas.getBoundingClientRect();canvas.dispatchEvent(new MouseEvent('dblclick',{bubbles:true,clientX:r.x+point[0],clientY:r.y+point[1],button:0}));await until(()=>mapPresentationDiagnostics().zoom>zoom+.8);assert(!endpoints().start&&!placements,'Doubletap zoom no acquisition');cases.push('native_map_doubletap_zoom_inspection_unchanged');
 }finally{for(const root of roots)root.remove();Object.assign(state,initial);clearPointUndo()}
 return cases;
}
