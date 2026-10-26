// This existing fixture exercises explicit English output. French defaults and
// both-language state preservation are covered by localization_harness and the
// full bundled-app acceptance, with strict canonical and GPX comparisons.
import { setLanguage } from "../../src/sugarglider/web/static/i18n.js";
await setLanguage("en", { persist: false, document: null });
import {projectElevationProfile,elevationPositionAtDistance} from '../../src/sugarglider/web/static/elevation_profile.js';
import {createElevationView} from '../../src/sugarglider/web/static/elevation_view.js';
import {createElevationMapMarker} from '../../src/sugarglider/web/static/elevation_map_marker.js';
import {createSelectedRouteElevation} from '../../src/sugarglider/web/static/route_elevation.js';
import {sampleElevationGeometry} from '../../src/sugarglider/web/static/elevation_sampling.js';
import {regionalRoutingReference} from '../../src/sugarglider/web/static/regional_routing_reference.js';

const assert=(value,message)=>{if(!value)throw Error(message);};
const close=(a,b)=>assert(Math.abs(a-b)<1e-7,`${a} != ${b}`);
const tick=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
async function until(check){for(let i=0;i<100;i++){if(check())return;await new Promise(r=>setTimeout(r,10));}throw Error('did not settle');}

export async function runElevationUiHarness(){
  const scenarios=[];
  const original=await(await fetch('../../src/sugarglider/web/static/index.html')).text();
  const markup=new DOMParser().parseFromString(original,'text/html').querySelector('#route-elevation');
  const fixture=document.getElementById('fixture');fixture.append(document.importNode(markup,true));
  const root=fixture.querySelector('#route-elevation');
  const contract=await(await fetch('../fixtures/elevation/contract-v1.json')).json();
  const runtime=await(await fetch('../fixtures/elevation/runtime-v1.json')).json();
  const analysis=(name,long=false)=>structuredClone((long?runtime:contract).find(c=>c.name===name).expected);
  const coords=a=>a.samples.map((s,i)=>[2+i/1000,48+i/2000]);
  const flat=analysis('flat'),negative=analysis('negative',true),missing=analysis('missing');
  const summit=analysis('summit'),longGap=analysis('long_gap',true),isolated=analysis('isolated',true),limit=analysis('limit_2048',true);
  for(const a of [flat,negative,summit,missing,isolated,longGap,limit]){
    const p=projectElevationProfile(a,coords(a),300);assert(p&&p.high>p.low&&Number.isFinite(p.y(a.samples.find(s=>s.filtered_height_m!==null).filtered_height_m)),'finite projection');
    close(p.x(0),p.left);close(p.x(a.route_distance_m),p.right);
  }
  scenarios.push('deterministic_flat_negative_short_long_axis_projection');
  assert(projectElevationProfile(analysis('all_missing',true),coords(analysis('all_missing',true)),300)===null,'all missing has no decorative chart');
  assert(projectElevationProfile(missing,coords(missing),300).paths.length===2,'missing split paths');
  assert(projectElevationProfile(longGap,coords(longGap),300).paths.length===2,'unsupported gap split paths');
  const dots=projectElevationProfile(isolated,coords(isolated),300);assert(dots.paths.length===0&&dots.points.length===2,'isolated points');
  scenarios.push('native_segments_never_connect_missing_or_unsupported_gaps');
  const c=[[2,48],[3,49],[2,48]];
  const selected=elevationPositionAtDistance(summit,c,25);close(selected.height_m,7.5);close(selected.coordinate[0],2.5);close(selected.coordinate[1],48.5);
  const repeated=elevationPositionAtDistance(summit,c,100);assert(repeated.distance_m===100&&repeated.coordinate===c[2],'repeated coordinate retains routed occurrence');
  for(const d of [75,100,125])assert(elevationPositionAtDistance(missing,coords(missing),d).height_m===null,'missing span');
  assert(elevationPositionAtDistance(longGap,coords(longGap),125).coordinate===null,'long gap no marker');
  assert(elevationPositionAtDistance(isolated,coords(isolated),50).height_m===3,'isolated exact point');
  assert(elevationPositionAtDistance(isolated,coords(isolated),51).height_m===null,'no interpolation from isolated point');
  close(elevationPositionAtDistance(negative,coords(negative),25).height_m,-25);
  assert(elevationPositionAtDistance(flat,coords(flat),25).height_m===0,'zero is available');
  scenarios.push('binary_distance_mapping_interpolates_only_supported_adjacent_samples');

  let current=null,currentCandidate=null,position=null,cancels=0,retries=0,shows=0;
  const view=createElevationView({root,isCurrent:(value,candidate)=>value===current&&candidate===currentCandidate&&Boolean(candidate),
    onPosition:p=>{position=p;},onCancel:()=>cancels++,onRetry:()=>retries++,onShowMap:()=>shows++});
  function display(a,status='ready',id='a'){
    currentCandidate={id,routing_profile:'hike',route:{routing_profile:'hike',summary:{distance_m:a.route_distance_m}}};
    current={status,candidate_id:id,result:status==='ready'?{analysis:a,sample_coordinates:coords(a)}:null};
    view.render(current,currentCandidate);return current;
  }
  const ign = structuredClone(summit);
  ign.height_reference = "IGN69 normal metres; IGN RGE ALTI 5 m; Licence Ouverte 2.0; verified V2 elevation component manifest";
  display(ign);
  assert(root.querySelector('[data-elevation-source]').textContent.includes('NGF-IGN69'),'IGN datum visible');
  assert(root.querySelector('[data-elevation-source] a').href==='https://www.data.gouv.fr/pages/legal/licences/etalab-2.0','IGN attribution and official license');
  assert(root.querySelector('[data-elevation-ascent]').textContent==='15 m','datum label never changes totals');
  scenarios.push('ign69_ground_model_credit_and_datum_without_recalculation');
  const partialIgn = structuredClone(missing); partialIgn.height_reference = ign.height_reference;
  display(partialIgn);
  assert(root.querySelector('[data-elevation-source]').textContent.includes('EPSG:5720') && root.querySelector('[data-elevation-coverage]').textContent === 'Partial coverage', 'partial coverage keeps actual IGN reference');
  for (const state of ['loading', 'unavailable', 'idle']) {
    display(ign);
    display(ign, state);
    assert(!root.querySelector('[data-elevation-source]').textContent && !root.querySelector('svg'), 'non-ready state clears old source text');
  }
  display(ign);
  current = {...current, status:'unavailable', diagnostic:'elevation_cancelled'}; view.render(current,currentCandidate);
  assert(!root.querySelector('[data-elevation-source]').textContent, 'cancelled analysis clears old IGN text');
  const noIgnHeights = analysis('all_missing',true); noIgnHeights.height_reference = ign.height_reference;
  display(noIgnHeights);
  assert(!root.querySelector('[data-elevation-source]').textContent, 'no coverage leaves no stale chart credit');
  scenarios.push('ign_partial_coverage_loading_cancellation_unavailable_idle_and_absent_coverage_sources');
  display(summit);
  assert(!root.querySelector('[data-elevation-source]').textContent.includes('IGN RGE'),'old source credit cleared on route change');
  assert(!root.hidden&&root.querySelector('[data-elevation-ascent]').textContent==='15 m','uses returned filtered D+');
  assert(root.querySelector('[data-elevation-altitude]').textContent==='0–30 m','raw observed range, no invented filtered range');
  assert(root.querySelectorAll('.elevation-profile-line').length===1,'one supported line');
  const p=projectElevationProfile(summit,coords(summit),root.querySelector('[data-elevation-chart]').clientWidth);
  assert(root.querySelector('.elevation-profile-line').getAttribute('d')===p.paths[0],'plots returned filtered values');
  scenarios.push('complete_summary_uses_native_totals_observed_range_and_filtered_path');
  display(missing);assert(root.querySelector('[data-elevation-ascent]').textContent==='Unavailable','partial total not zero');
  assert(root.querySelector('[data-elevation-observed]').textContent.includes('Measured segments only'),'observed labelled');
  assert(root.querySelectorAll('.elevation-profile-line').length===2,'partial visible gap');
  scenarios.push('partial_totals_unavailable_observed_values_explicit_and_gaps_visible');
  display(isolated);assert(root.querySelectorAll('.elevation-isolated-point').length===2&&root.querySelectorAll('.elevation-profile-line').length===0,'isolated points visible');
  scenarios.push('isolated_available_altitudes_remain_points');
  display(analysis('all_missing',true));assert(!root.querySelector('svg')&&root.querySelector('[data-elevation-ascent]').textContent==='Unavailable','unavailable chart hidden');
  root.querySelector('#retry-route-elevation').click();assert(retries===1,'explicit retry');
  scenarios.push('all_missing_has_no_graph_or_zero_totals_and_retry_action');
  display(summit,'loading');assert(!root.querySelector('svg')&&!root.querySelector('#cancel-route-elevation').hidden,'nonblocking loading');
  root.querySelector('#cancel-route-elevation').click();assert(cancels===1,'cancel retained');
  current={...current,status:'unavailable',diagnostic:'elevation_cancelled'};view.render(current,currentCandidate);
  assert(root.querySelector('#route-elevation-status').textContent.includes('cancelled')&&!root.querySelector('svg')&&position===null,'cancel clears');
  scenarios.push('loading_cancelled_unavailable_clear_graph_and_marker');

  display(summit);let control=root.querySelector('[role=slider]');control.focus();
  assert(position.height_m===0,'focus provides nonhover inspection');
  const renders=view.diagnostics().chart_renders;
  control.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,cancelable:true}));
  assert(position.distance_m===50&&position.height_m===15,'right sample');
  assert(control.getAttribute('aria-valuetext').includes('15.0 metres'),'accessible numeric value');
  assert(!root.querySelector('.elevation-cursor').hasAttribute('hidden'),'cursor visible');
  root.querySelector('#show-elevation-on-map').click();assert(shows===1,'deliberate map action');
  control.dispatchEvent(new KeyboardEvent('keydown',{key:'End',bubbles:true,cancelable:true}));assert(position.distance_m===100,'end');
  control.dispatchEvent(new KeyboardEvent('keydown',{key:'Home',bubbles:true,cancelable:true}));assert(position.distance_m===0,'home');
  control.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));assert(position===null,'escape clears');
  assert(view.diagnostics().chart_renders===renders,'inspection does not redraw chart');
  scenarios.push('keyboard_home_end_arrows_readout_cursor_and_explicit_map_action');
  display(missing);control=root.querySelector('[role=slider]');control.focus();
  for(let i=0;i<2;i++)control.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,cancelable:true}));
  assert(position===null&&root.querySelector('#elevation-position-readout').textContent.includes('Elevation unavailable here'),'gap clears marker');
  assert(root.querySelector('.elevation-cursor-point').hasAttribute('hidden'),'gap has no altitude dot');
  scenarios.push('keyboard_unknown_span_shows_unavailable_and_clears_marker');

  const old=current;display(summit,'loading','b');assert(!root.querySelector('svg')&&position===null,'B immediately clears A');
  view.render(old,currentCandidate);assert(root.hidden&&!root.querySelector('svg'),'late A cannot draw');
  display(summit,'ready','a');assert(!root.hidden,'back to A');
  current=null;currentCandidate=null;view.render(current,currentCandidate);assert(root.hidden&&!root.querySelector('svg'),'absent selected route');
  scenarios.push('candidate_switch_stale_or_absent_values_never_draw_old_profile');
  display(limit);assert(root.querySelectorAll('.elevation-profile-line').length===1,'2048 path');
  for(let i=0;i<20;i++){display(i%2?summit:limit);assert(root.querySelectorAll('[role=slider]').length===1,'single control');}
  display(limit);const longControl=root.querySelector('[role=slider]'),path=root.querySelector('.elevation-profile-line');
  longControl.focus();for(let i=0;i<50;i++)longControl.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,cancelable:true}));
  assert(root.querySelector('.elevation-profile-line')===path&&root.querySelectorAll('svg').length===1,'no path allocation on inspection');
  scenarios.push('2048_sample_profile_and_repeated_render_keep_one_control_and_stable_paths');
  for(const width of [360,390,420]){
    fixture.style.width=`${width-24}px`;await tick();
    const box=root.querySelector('svg').viewBox.baseVal;
    assert(box.width===root.querySelector('[data-elevation-chart]').clientWidth,'responsive projection');
    assert(root.scrollWidth<=fixture.clientWidth,'no section horizontal overflow');
  }
  scenarios.push('360_390_420_widths_resize_without_horizontal_overflow');
  assert(root.querySelector('svg title')&&root.querySelector('svg desc')&&longControl.getAttribute('aria-describedby'),'accessible title and description');
  assert(root.querySelector('#elevation-position-readout').getAttribute('aria-live')==='off','no dragging live announcements');
  assert(getComputedStyle(longControl).touchAction.includes('pan-y'),'vertical scrolling retained');
  scenarios.push('accessible_title_description_units_focus_and_vertical_touch_scrolling');

  const markerEvents=[];
  const fakeMap=()=>{const listeners=new Map();return {on:(event,handler)=>listeners.set(event,handler),off:event=>listeners.delete(event),
    getContainer:()=>fixture,remove:()=>listeners.get('remove')?.(),styleReload:()=>{},listeners};};
  const overlay=createElevationMapMarker({createMarker:element=>{markerEvents.push('create');assert(element.getAttribute('aria-hidden')==='true','noninteractive marker');return {
    setLngLat(c){markerEvents.push(['move',c]);return this;},addTo(){markerEvents.push('add');return this;},remove(){markerEvents.push('remove');}};}});
  const mapA=fakeMap(),mapB=fakeMap();overlay.attach(mapA);
  overlay.show(selected);overlay.show({...selected,distance_m:30});assert(markerEvents.filter(e=>e==='create').length===1,'one reusable marker');
  mapA.styleReload();assert(overlay.diagnostics().active,'style-independent DOM marker');
  overlay.show({coordinate:null,height_m:null});assert(!overlay.diagnostics().active,'unknown clears');
  overlay.show(selected);overlay.attach(mapB);assert(!overlay.diagnostics().active&&mapA.listeners.size===0,'replacement cleanup');
  overlay.show(selected);mapB.remove();assert(!overlay.diagnostics().active,'remove cleanup');overlay.destroy();
  scenarios.push('one_map_marker_style_reload_map_replacement_unknown_and_destroy_cleanup');

  const manifest=(await(await fetch('../fixtures/pr40_regional_data.json')).json()).manifest;
  const reference=await regionalRoutingReference(manifest),geometry=[[2,48],[2.001,48.001]];
  const makeCandidate=id=>({id:`geometry:${id.repeat(64)}`,route:{geometry,routing_profile:'hike',summary:{distance_m:100}},
    diagnostics:{details:{local_routing:{engine:'valhalla-mobile',regional_version:{region_id:manifest.region_id,build_id:manifest.build_id,routing_pack_id:reference.pack_id}}}}});
  const a=makeCandidate('a'),b=makeCandidate('b'),generation={candidates:[a,b]};let calls=0;
  const jobs=[];
  const coordinator=createSelectedRouteElevation({versions:{withCommittedRegions:async action=>action([{status:'committed',region_id:manifest.region_id,manifest}])},
    prepare:sampleElevationGeometry,client:{analyze:fields=>{calls++;return new Promise(resolve=>jobs.push({fields,resolve}));},cancel:async()=>{}},lifecycleTarget:null});
  const resolve=index=>{const {fields,resolve}=jobs[index],a=analysis('summit');a.source_sha256=reference.elevation.manifest.sha256;a.geometry_sha256=fields.geometry_sha256;
    resolve({candidate_id:fields.candidate_id,analysis:a,regional_reference:reference});};
  coordinator.sync(a,generation,manifest.region_id);await until(()=>jobs.length===1);resolve(0);await until(()=>coordinator.snapshot().status==='ready');
  const owned=coordinator.snapshot();assert(coordinator.owns(owned,a,generation,manifest.region_id),'current verified owner');
  a.route.routing_profile='trail_run';assert(!coordinator.owns(owned,a,generation,manifest.region_id),'profile mismatch rejected');a.route.routing_profile='hike';
  a.route.geometry=[...geometry];assert(!coordinator.owns(owned,a,generation,manifest.region_id),'geometry object mismatch rejected');a.route.geometry=geometry;
  assert(!coordinator.owns({...owned},a,generation,manifest.region_id),'copy not owned');
  assert(!coordinator.owns(owned,a,{candidates:[a]},manifest.region_id),'other generation not owned');
  assert(!coordinator.owns(owned,b,generation,manifest.region_id),'other candidate not owned');
  assert(!coordinator.owns(owned,a,generation,'other-region'),'other region not owned');
  coordinator.sync(b,generation,manifest.region_id);assert(!coordinator.owns(owned,a,generation,manifest.region_id),'old ownership immediately revoked');
  await until(()=>jobs.length===2);coordinator.cancel();assert(coordinator.retry(),'retry cancelled through same coordinator');resolve(1);
  await until(()=>jobs.length===3);resolve(2);await until(()=>coordinator.snapshot().status==='ready');
  coordinator.sync(a,generation,manifest.region_id);await until(()=>coordinator.snapshot().status==='ready');assert(calls===3&&coordinator.snapshot().cache_hit,'same existing cache');
  coordinator.sync(a,{candidates:[a]},manifest.region_id);assert(!coordinator.owns(owned,a,generation,manifest.region_id),'regeneration revokes');
  await until(()=>jobs.length===4);resolve(3);await until(()=>coordinator.snapshot().status==='ready');
  coordinator.regionChanged(reference);coordinator.regionChanged({...reference,elevation:{...reference.elevation,component_id:'replacement-elevation'}});
  assert(coordinator.snapshot().status==='idle','component replacement invalidates');
  scenarios.push('presentation_ownership_generation_geometry_profile_region_component_and_retry_share_pr91_coordinator');

  view.destroy();assert(position===null&&!root.querySelector('svg')&&root.hidden,'view destroy cleanup');
  scenarios.push('destroy_removes_chart_marker_listeners_observer_and_pending_frames');
  // Leave a synthetic fixture for actual Playwright mouse/touch/layout actions.
  let demo=null,demoCandidate=null;const positions=[];
  const demoView=createElevationView({root,isCurrent:(v,c)=>v===demo&&c===demoCandidate,onPosition:p=>positions.push(p)});
  demoCandidate={id:'demo',route:{summary:{distance_m:100}}};demo={status:'ready',candidate_id:'demo',result:{analysis:summit,sample_coordinates:c}};
  demoView.render(demo,demoCandidate);fixture.style.width='100%';
  window.elevationHarness={view:demoView,positions,root};
  return scenarios;
}
