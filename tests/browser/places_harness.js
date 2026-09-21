import { createLocalRegionData, eligibleLocalPoi } from '../../src/sugarglider/web/static/local_region_data.js';
import { createLocalPlaceSearch } from '../../src/sugarglider/web/static/local_places.js';
import { createLocalRegionClient } from '../../src/sugarglider/web/static/local_region_client.js';
import { createRegionVersionStore } from '../../src/sugarglider/web/static/region_versions.js';
import { createVersionedRegionComponents } from '../../src/sugarglider/web/static/region_components.js';
import { parseRegionalManifest } from '../../src/sugarglider/web/static/regional_manifest.js';
import { createPlaceDetails, placePresentation, placeAddress } from '../../src/sugarglider/web/static/place_presentation.js';
import { initializeMap, renderPois, placeMapDiagnostics } from '../../src/sugarglider/web/static/map.js';
import { distribution } from './pr42_region_components_harness.js';

const assert = (condition, message) => { if (!condition) throw new Error(message); };
const equal = (a, b, message) => assert(JSON.stringify(a) === JSON.stringify(b), message);
const until = async (predicate) => {
  for (let i = 0; i < 200; i += 1) { if (predicate()) return; await new Promise((resolve) => setTimeout(resolve, 25)); }
  throw new Error('Timed out waiting for map state');
};
const rejects = async (run, code) => { try { await run(); } catch (error) {
  assert(!code || error.code === code || error.name === code, `Unexpected rejection ${error}`); return;
} throw new Error('Expected rejection'); };
function recount(document) {
  document.features.sort((a, b) => a.id < b.id ? -1 : 1);
  document.metadata.feature_count = document.features.length;
  for (const [key, field] of [['category_counts','category'],['access_counts','access_status'],['potability_counts','potability']]) {
    document.metadata[key] = {};
    for (const feature of document.features) document.metadata[key][feature[field]] = (document.metadata[key][feature[field]] ?? 0) + 1;
  }
}

export async function runPlacesHarness() {
  const cases = [], fixture = await (await fetch('../fixtures/pr40_regional_data.json')).json();
  const legacy = createLocalRegionData(fixture.manifest, structuredClone(fixture));
  const query = { bbox: { west:0, south:0, east:.02, north:.02 }, groups:['refreshment'], categories:['ice_cream'], limit:200 };
  equal(legacy.searchPois(query).returned_count, 0, 'Older regions truthfully have no ice cream');
  equal(legacy.identity.poi_classifier_version, '1', 'Old classifier identity survives');
  const ice = { ...structuredClone(fixture.pois.features[0]), id:'node/900', osm_id:900,
    coordinate:{lat:.01,lon:.01,name:null}, category:'ice_cream', group:'refreshment',
    scenic_confidence:'none', display_name:'Glacier <img src=x onerror=alert(1)>', approach_candidates:[],
    tags:[['addr:city','Versailles'],['addr:housenumber','3'],['addr:street','Rue des Deux Portes'],['opening_hours','Tu-Su 12:00-18:00']] };
  fixture.pois.features.push(ice);
  fixture.pois.metadata.classifier_version = fixture.pois.metadata.build_configuration.classifier_version = fixture.manifest.tools.poi_classifier = '2';
  recount(fixture.pois);
  const data = createLocalRegionData(fixture.manifest, structuredClone(fixture));
  equal(data.searchPois(query).features[0].id, ice.id, 'Primary-category filtering');
  equal(data.searchPois({ ...query, groups:[] }).returned_count, 0, 'Empty filter remains empty');
  equal(data.searchPois({ ...query, bbox:{west:.015,south:.015,east:.02,north:.02} }).returned_count, 0, 'Spatial envelope excludes out-of-view features');
  for (const bad of [{limit:501},{limit:0},{bbox:{west:2,south:0,east:1,north:.02}},{categories:['made_up']},{access:['public','public']}]) {
    await rejects(() => data.searchPois({...query,...bad}), 'invalid_local_place_query');
  }
  const radius = {center:{lat:.01,lon:.01},radius_m:2000,limit:64};
  equal(data.queryPois(radius).features, legacy.queryPois(radius).features, 'Ice cream cannot crowd Auto Tour shortlist');
  equal(eligibleLocalPoi(ice, fixture.manifest.bounds), 'poi_category_display_only', 'Requested ice cream cannot enter Auto Tour');
  equal(data.searchPois({...query,groups:['scenic','hydration'],categories:['castle','drinking_water','fountain','viewpoint']}).features,
    legacy.searchPois({...query,groups:['scenic','hydration'],categories:['castle','drinking_water','fountain','viewpoint']}).features, 'Existing category discovery preserved');
  cases.push('old_index_compatibility_explicit_category_spatial_filters_auto_tour_unchanged');
  const dense = structuredClone(fixture);
  for (let i = 901; i <= 930; i += 1) dense.pois.features.push({...structuredClone(ice), id:`node/${i}`,osm_id:i,
    access_status:i===930?'private':'public'});
  recount(dense.pois);
  const denseData = createLocalRegionData(dense.manifest,dense);
  const limited=denseData.searchPois({...query,limit:5});
  equal([limited.total_matching,limited.returned_count,limited.truncated],[30,5,true],'Bounded truthful count; private hidden');
  equal(limited,denseData.searchPois({...query,limit:5}),'Deterministic query order');
  assert(Object.isFrozen(limited.features[0]),'Search result immutable');
  equal(denseData.searchPois({...query,include_private:true,access:['private']}).features.map(f=>f.id),['node/930'],'Private requires explicit filter');
  const uncovered = structuredClone(fixture);
  uncovered.pois.features.push({...structuredClone(ice), id:'node/999',osm_id:999,coordinate:{lat:.03,lon:.03,name:null}});
  recount(uncovered.pois);
  equal(createLocalRegionData(uncovered.manifest,uncovered).searchPois({...query,bbox:{west:0,south:0,east:.04,north:.04}}).features.map(f=>f.id),
    [ice.id], 'Viewport discovery never exposes records outside installed coverage');
  cases.push('bounded_density_deterministic_sort_private_access_and_immutability');

  equal(placePresentation(ice).icon,'poi-ice-cream','Compact cone');
  equal(placePresentation({category:'drinking_water',potability:'verified'}).icon,'poi-water-verified','Blue water icon unchanged');
  equal(placePresentation({category:'fountain',potability:'unknown'}).icon,'poi-water-unknown','Unknown water distinct');
  equal(placePresentation({category:'fountain',potability:'non_potable'}).icon,'poi-water-nonpotable','Nonpotable water distinct');
  equal(placeAddress(ice),'3 Rue des Deux Portes, Versailles','Only mapped address fields');
  let centered=false;
  const details=createPlaceDetails(ice,{onCenter:()=>{centered=true;}});document.body.append(details);
  equal(details.querySelector('h3').textContent,ice.display_name,'Untrusted names are text');
  equal(details.querySelectorAll('img').length,1,'No markup injection');
  const button=details.querySelector('button');assert(button.getBoundingClientRect().height>=44,'Finger-sized action');button.click();assert(centered,'Center action works');
  assert(details.getBoundingClientRect().width<=innerWidth,'Details fit phone and desktop');
  assert(!details.textContent.includes('Auto Tour'),'No route preference invented');details.remove();
  cases.push('category_presentation_safe_metadata_responsive_details_and_real_action');

  const origin=await navigator.storage.getDirectory(), folder=`places-test-${crypto.randomUUID()}`;
  const root=await origin.getDirectoryHandle(folder,{create:true});
  const versions=createRegionVersionStore({storage:{getDirectory:async()=>root,estimate:async()=>({quota:1e9,usage:0})},locks:navigator.locks});
  const client=createLocalRegionClient();
  try {
    const download=await distribution(fixture,'Ice cream fixture');
    await parseRegionalManifest(JSON.stringify(download.manifest));
    const components=(manifest,directory)=>createVersionedRegionComponents({manifest,directory,
      fetchResource:async url=>{const bytes=download.files.get(new URL(url).pathname.slice(1));return new Response(bytes,{headers:{'Content-Length':String(bytes.byteLength)}});},pageLocation:location});
    const ticket=await versions.stage(JSON.stringify(download.manifest));
    await versions.withStagedVersion(ticket,async ({manifest,directory})=>{const scoped=await components(manifest,directory);await scoped.installMap(location.origin+'/manifest.json');await scoped.installIndexes(location.origin+'/manifest.json');});
    await versions.activate(ticket,{verifyComponent:async(kind,manifest,directory)=>{
      if(kind==='routing')return true;const scoped=await components(manifest,directory);if(kind==='map')return scoped.verifyMap();await scoped.openIndexes();return true;
    }});
    const search=createLocalPlaceSearch({versions,regionClient:client,selectedRegionId:()=>download.manifest.region_id});
    equal((await search(query)).features[0].id,ice.id,'Real worker queries committed OPFS index');
    const abort=new AbortController();abort.abort();await rejects(()=>search(query,abort.signal),'AbortError');
    await versions.deactivate(download.manifest.region_id,download.manifest.build_id);
    await rejects(()=>search(query));
    cases.push('version_two_manifest_real_opfs_worker_query_cancellation_and_removed_region');
  } finally {client.close();await origin.removeEntry(folder,{recursive:true});}

  let release; const deferred=new Promise(resolve=>{release=resolve;});let locked=false;
  const abort=new AbortController();
  const delayed=createLocalPlaceSearch({selectedRegionId:()=>fixture.manifest.region_id,
    versions:{withCommittedRegions:async run=>{locked=true;try{return await run([{status:'committed',region_id:fixture.manifest.region_id,manifest:fixture.manifest}]);}finally{locked=false;}},committedDirectory:async()=>({})},
    regionClient:{loadVersion:async()=>({identity:{build_id:fixture.manifest.build_id,region_id:fixture.manifest.region_id},searchPois:()=>deferred})}});
  const pending=delayed(query,abort.signal);await until(()=>locked);await new Promise(resolve=>setTimeout(resolve,0));
  abort.abort();release(data.searchPois(query));await rejects(()=>pending,'AbortError');assert(!locked,'Lease released after cancelled result');
  cases.push('late_response_cannot_escape_abort_or_hold_region_lease');

  let ready=false,selected=null,mapClicks=0;const features=[{...ice,display_name:'Glacier test'}];
  const choose=id=>{selected=id;renderPois(features,id,choose,{onDeselect:()=>choose(null)});};
  initializeMap({initial_center:[.01,.0085],initial_zoom:16,offline_mode:true,tile_attribution:'Test fixture'},
    {onReady:()=>{ready=true;choose(null);},onMapClick:()=>{mapClicks+=1;},onError:message=>{throw new Error(message);}});
  await until(()=>ready && placeMapDiagnostics().markerIds.includes(ice.id));
  const canvas=document.querySelector('.maplibregl-canvas'),rect=canvas.getBoundingClientRect();
  const point=placeMapDiagnostics().positions.find(feature=>feature.id===ice.id).point;
  for(const type of ['mousedown','mouseup','click'])canvas.dispatchEvent(new MouseEvent(type,{bubbles:true,clientX:rect.x+point[0],clientY:rect.y+point[1],button:0,buttons:type==='mousedown'?1:0}));
  await until(()=>selected===ice.id && document.querySelector('.place-details'));
  await until(()=>placeMapDiagnostics().selectedMarkerIds.includes(ice.id));
  const card=document.querySelector('.place-detail-popup').getBoundingClientRect();
  assert(card.top>=rect.top+11 && card.bottom<=rect.bottom-59 && card.left>=rect.left+11 && card.right<=rect.right-11,
    'Selection keeps the full card in the map and attribution clear');
  equal(mapClicks,0,'POI click does not become route point');
  document.querySelector('.place-detail-popup .maplibregl-popup-close-button').click();
  equal(selected,null,'Close deselects application state');equal(placeMapDiagnostics().popupId,null,'Close clears popup ownership');
  choose(ice.id);document.querySelector('.place-details').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
  equal(selected,null,'Escape deselects');assert(document.activeElement===canvas,'Dismiss returns focus to map');
  renderPois([],null,choose);equal(placeMapDiagnostics().selectedId,null,'Filter removal clears selected marker');
  cases.push('real_map_click_selected_exception_close_escape_focus_and_no_route_mutation');
  return cases;
}
