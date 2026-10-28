// Normal bundled page, synthetic committed OPFS region and synthetic native leg boundaries.
// Nothing is installed on a device and no real regional data is used.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../..'),origin='https://appassets.androidplatform.net';
const profiles=['trail_run','hike','city_bike','gravel_bike','mountain_bike','road_bike'];
async function run(browser,touch){
 const context=await browser.newContext({viewport:touch?{width:372,height:709}:{width:1360,height:940},hasTouch:touch,isMobile:touch});
 const errors=[],requests=[];const cases=[];const french=touch;
 try{
  await context.addInitScript(({profiles})=>{
   globalThis.snapNativeCalls=[];globalThis.snapDistance=89.2;globalThis.snapHold=false;
   globalThis.sugargliderNative={onmessage:null,postMessage(payload){
    const input=JSON.parse(payload);snapNativeCalls.push(input);
    const deliver=reply=>queueMicrotask(()=>this.onmessage?.({data:JSON.stringify({schema_version:1,request_id:input.request_id,...reply})}));
    if(input.type.startsWith('calculation_'))deliver({type:'calculation_result',operation_id:input.operation_id??null,state:input.type==='calculation_begin'?'running':input.state??'idle',recovery:null});
    else if(input.type==='set_ui_language')deliver({type:'set_ui_language_result',language:input.language,selected:true});
    else if(input.type==='hello')deliver({type:'hello_result',outing_slug:null,participant_id:null,active:false,state:'stopped',last_published_at:null,pending_sample:false,stop_warning:null});
    else if(input.type==='get_local_route_capabilities')deliver({type:'local_route_capabilities_result',enabled:true,engine:'valhalla-mobile',engine_version:'synthetic',installed_pack_count:1,installed_pack_ids:[input.regional_reference.pack_id],supported_profile_ids:profiles,pack_capabilities:[{pack_id:input.regional_reference.pack_id,access_modes:['foot','bicycle']}]});
    else if(input.type==='local_route'){
     const reply=()=>import('/tests/browser/endpoint_snapping_harness.js').then(m=>deliver({...m.snappedReply(input,{start:snapDistance+(globalThis.snapVary&&input.points[1]?.lon>.01?10:0),pack:input.regional_reference.pack_id}),request_id:input.request_id}));
     if(snapHold)globalThis.releaseSnap=reply;else void reply();
    }else if(input.type==='route_elevation')deliver({type:'local_elevation_failure',operation_id:input.operation_id,code:'elevation_unavailable'});
    else if(input.type==='cancel_route_elevation')deliver({type:'local_elevation_cancel_result',operation_id:input.operation_id,accepted:true});
    else if(input.type==='itinerary_dialog_state')return;
    else throw Error('Unexpected native operation '+input.type);
   }};
  },{profiles});
  await context.route('**/*',async route=>{
   const url=new URL(route.request().url());requests.push(url.pathname);
   assert.equal(url.origin,origin,'no remote dependencies');
   if(url.pathname==='/seed.html')return route.fulfill({contentType:'text/html',body:'<!doctype html><script src="/static/vendor/pmtiles-4.5.0/pmtiles.js"></script>'});
   if(url.pathname==='/static/offline_region_catalog.json')return route.fulfill({json:{schema_version:1,regions:[]}});
   const file=path.resolve(root,url.pathname.startsWith('/tests/')||url.pathname.startsWith('/src/')?decodeURIComponent(url.pathname.slice(1)):'src/sugarglider/web/static/'+(url.pathname==='/'?'index.html':url.pathname==='/v1/ui/config'?'android_ui_config.json':decodeURIComponent(url.pathname.replace(/^\/static\//u,''))));
   assert(file.startsWith(root+path.sep));
   const types={'.js':'text/javascript','.mjs':'text/javascript','.html':'text/html','.css':'text/css','.json':'application/json','.png':'image/png','.svg':'image/svg+xml'};
   try{let body=await fs.readFile(file);return route.fulfill({body,contentType:types[path.extname(file)]||'application/octet-stream'});}catch(error){console.error(file,error.message);return route.fulfill({status:404,body:''});}
  });
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));page.on('console',m=>{if(m.type()==='error') console.error(m.text());});
  await page.goto(origin+'/seed.html');
  await page.evaluate(async french => {const {writeLanguagePreference}=await import('/static/pwa_store.js');await writeLanguagePreference(french?'fr':'en');},french);
  await page.evaluate(async()=>{
   const {seedRegion}=await import('/tests/browser/region_preference_harness.js');
   const {createRegionVersionStore}=await import('/static/region_versions.js');
   const {openPwaStore,PWA_STORES}=await import('/static/pwa_store.js');
   const fixture=await(await fetch('/tests/fixtures/pr40_regional_data.json')).json();
   const versions=createRegionVersionStore();await seedRegion(fixture,versions,'alpha','Synthetic alpha');await seedRegion(fixture,versions,'beta','Synthetic beta');
   const store=await openPwaStore();await store.put(PWA_STORES.publicRuntime,'planner-region-id','alpha');
   await store.put(PWA_STORES.trailProfile,'current',{schema_version:1,display_name:'Synthetic reviewer',avatar_key:'blue'});
  });
  await page.goto(origin+'/');
  await page.waitForFunction(()=>document.querySelector('#planning-region')?.value==='alpha'&&[...document.querySelector('#profile').options].filter(o=>!o.disabled).length===6);
  const app=await page.evaluate(()=>import('/static/state.js').then(({state})=>({profile:state.routingProfile})));assert(profiles.includes(app.profile));
  assert.equal(await page.evaluate(()=>snapNativeCalls.filter(c=>c.type==='local_route').length),0,'no startup routing');
  // Map click uses the actual automatic-intent and native planning UI.
  const mapTab=page.locator('[data-shell-view="map"]');if(await mapTab.isVisible())await mapTab.click();
  const canvas=page.locator('.maplibregl-canvas');
  await page.evaluate(async()=>{const {fitCoordinates}=await import('/static/map.js');fitCoordinates([[.002,.002],[.018,.018]]);});
  await page.waitForTimeout(600); // The declared 500 ms map camera transition.
  const box=await canvas.boundingBox();
  await canvas.click({position:{x:box.width*.4,y:box.height*.3}});
  if(!await page.locator('#dock-finish').isVisible())await page.locator('#route-editor-toggle').click();
  await page.locator('#dock-finish').selectOption('point_to_point');
  if(await page.locator('#route-editor-close').isVisible())await page.locator('#route-editor-close').click();
  await canvas.click({position:{x:box.width*.7,y:box.height*.45}});
  const request=await page.evaluate(async()=>{const {state,currentPlanRequest}=await import('/static/state.js');return {request:currentPlanRequest(),points:state.points.length};});
  assert.equal(request.request.endpoint_snap_policy.start,'near');assert.equal(request.request.endpoint_snap_policy.end,'near');
  if(await mapTab.isVisible())await mapTab.click();await page.click('#generate-map');
  await page.waitForFunction(french=>document.querySelector('#endpoint-adjustments-routes')?.textContent.includes(french?'Départ ajusté de 89 m':'Start adjusted by 89 m'),french);
  const snapshot=await page.evaluate(async()=>{const {state,selectedCandidate}=await import('/static/state.js');return {request:state.generationSourceRequest,candidate:selectedCandidate()};});
  assert(snapshot.candidate);assert.equal(snapshot.candidate.routing_profile,snapshot.request.routing_profile);
  await page.locator('#endpoint-adjustments-routes summary').click();
  const show=page.locator('#endpoint-adjustments-routes [data-adjustment-action="start-show"]');
  await show.focus();await page.keyboard.press('Enter');
  await page.waitForSelector('.endpoint-adjustment-marker.routed');
  assert.equal(await page.locator('.endpoint-adjustment-marker.requested').count(),1);
  assert.equal(await page.locator('.endpoint-adjustment-marker.routed').count(),1);
  assert.equal(await page.locator('.endpoint-adjustment-marker.routed').getAttribute('aria-label'),french?'Point calculé Départ, déplacement de 89 m':'Actual routed Start, 89 m displacement');
  const gpx=await page.evaluate(async()=>{const {selectedCandidate}=await import('/static/state.js');const {exportCanonicalCandidate}=await import('/static/local_gpx_export.js');return exportCanonicalCandidate(selectedCandidate()).blob.text();});
  assert(gpx.includes(`lat="${snapshot.candidate.route.geometry[0][1].toFixed(8)}"`));
  await page.waitForTimeout(600); // Finish the 500 ms Show adjustment camera transition.
  const mapEvidence=await page.evaluate(async()=>{const {mapPresentationDiagnostics}=await import('/static/map.js');return mapPresentationDiagnostics();});
  const connector=mapEvidence.sources['endpoint-adjustment-source'].data.features[0];
  assert.equal(connector.properties.label,'89 m');
  assert(mapEvidence.zoom>15,'Show adjustment separates nearby endpoint markers at street scale: '+mapEvidence.zoom);
  assert.equal(connector.geometry.coordinates.length,2);
  assert.deepEqual(connector.geometry.coordinates[1],snapshot.candidate.route.geometry[0]);
  assert.deepEqual(mapEvidence.layers.find(l=>l.id==='endpoint-adjustment-line').paint['line-dasharray'],[2,3]);
  if(process.env.ENDPOINT_EVIDENCE_DIR){await fs.mkdir(process.env.ENDPOINT_EVIDENCE_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.ENDPOINT_EVIDENCE_DIR,touch?'touch-warning.png':'keyboard-warning.png')});}
  assert(!gpx.includes('endpoint-adjustment'));cases.push('normal-map-intent-native-warning-keyboard-markers-gpx');
  // Actual policy control keeps strict choice and restores it through Undo.
  if(!await page.locator('[data-route-chip="start"]').isVisible())await page.locator('#route-editor-toggle').click();
  await page.click('[data-route-chip="start"]');
  await page.selectOption('[data-dock-action="snap-policy"]','exact');
  assert.equal(await page.locator('.endpoint-adjustment-marker').count(),0);
  if(await mapTab.isVisible())await mapTab.click();await page.click('#generate-map');await page.waitForFunction(french=>document.querySelector('#error-banner')?.textContent.includes(french?'limite stricte de rapprochement':'strict snap limit'),french);
  assert.equal(await page.evaluate(async()=>{const{state}=await import('/static/state.js');return state.generationResult.candidates.length;}),0);
  if(await mapTab.isVisible())await mapTab.click();
  if(!await page.locator('#undo-point-edit').isVisible())await page.locator('#route-editor-toggle').click();await page.click('#undo-point-edit');
  await page.evaluate(()=>{snapDistance=240;});if(await mapTab.isVisible())await mapTab.click();await page.click('#generate-map');
  await page.waitForFunction(french=>document.querySelector('#endpoint-adjustments-map')?.textContent.includes(french?'vérifier le rapprochement de 240 m':'review 240 m'),french);
  const before=await page.evaluate(async()=>{const{state}=await import('/static/state.js');return {lat:state.waypointEndpoints.start.lat,count:snapNativeCalls.filter(c=>c.type==='local_route').length};});
  await page.locator('#endpoint-adjustments-map [data-adjustment-action="start-show"]').click();
  await page.waitForTimeout(600); // Declared map transition must finish before testing occlusion.
  const visibility=await page.evaluate(()=>{
    const canvas=document.querySelector('.maplibregl-canvas').getBoundingClientRect();
    const dock=document.querySelector('#route-dock').getBoundingClientRect();
    return [...document.querySelectorAll('.endpoint-adjustment-marker')].map(marker=>{
      const r=marker.getBoundingClientRect();
      return {label:marker.getAttribute('aria-label'),rect:r.toJSON(),canvas:canvas.toJSON(),dock:dock.toJSON(),visible:r.left>canvas.left&&r.right<canvas.right&&r.top>canvas.top&&r.bottom<Math.min(canvas.bottom,dock.top)};
    });
  });
  assert.equal(visibility.length,2);assert(visibility.every(item=>item.visible),'Show adjustment must expose both markers above the dock: '+JSON.stringify(visibility));
  assert.equal(await page.evaluate(()=>document.activeElement?.tagName),'SUMMARY','collapsed disclosure keeps keyboard focus');
  const afterShow=await page.evaluate(async()=>{const{state}=await import('/static/state.js');return {lat:state.waypointEndpoints.start.lat,count:snapNativeCalls.filter(c=>c.type==='local_route').length};});
  assert.deepEqual(afterShow,before,'Show adjustment neither edits nor routes');
  if(process.env.ENDPOINT_EVIDENCE_DIR)await page.screenshot({path:path.join(process.env.ENDPOINT_EVIDENCE_DIR,touch?'touch-large-review.png':'keyboard-large-review.png')});
  if(!await page.locator('#endpoint-adjustments-map details').evaluate(e=>e.open))await page.locator('#endpoint-adjustments-map summary').click();
  const use=page.locator('#endpoint-adjustments-map [data-adjustment-action="start-use"]');
  if(touch)await use.tap();else {await use.focus();await page.keyboard.press('Enter');}
  const adopted=await page.evaluate(async()=>{const{state}=await import('/static/state.js');return {lat:state.waypointEndpoints.start.lat,result:state.generationResult,calls:snapNativeCalls.filter(c=>c.type==='local_route').length};});
  assert(adopted.lat!==before.lat);assert.equal(adopted.result,null);assert.equal(adopted.calls,before.count,'adoption never automatically routes');
  assert.equal(await page.locator('.endpoint-adjustment-marker').count(),0);
  if(!await page.locator('#undo-point-edit').isVisible())await page.locator('#route-editor-toggle').click();await page.click('#undo-point-edit');assert.equal(await page.evaluate(async()=>{const{state}=await import('/static/state.js');return state.waypointEndpoints.start.lat;}),before.lat);
  cases.push('strict-intent-large-displacement-explicit-adoption-invalidation-undo');
  // JSON restoration preserves exact intent, and each candidate owns its adjustment.
  const imported=structuredClone(snapshot.request);delete imported.endpoint_snap_policy;
  let importNumber=0;
  async function importRequest(value){const name=`synthetic-plan-${++importNumber}.json`;await page.setInputFiles('#request-file',{name,mimeType:'application/json',buffer:Buffer.from(JSON.stringify(value))});await page.waitForFunction(({name,french})=>document.querySelector('#request-status').textContent.includes(name+(french?' chargé.':' loaded.')),{name,french});}
  await importRequest(imported);
  assert.equal(await page.evaluate(async()=>{const {currentPlanRequest}=await import('/static/state.js');return currentPlanRequest().endpoint_snap_policy.start;}),'exact');
  imported.endpoint_snap_policy={start:'near',end:'near'};imported.candidate_count=3;imported.waypoint_order='optimize';
  imported.waypoints=[{id:'one',name:'One',coordinate:{lat:.009,lon:.006,name:'One'},constraint_strength:'exact',access_search_radius_m:500,maximum_best_effort_distance_m:null,approach_override:null},{id:'two',name:'Two',coordinate:{lat:.011,lon:.013,name:'Two'},constraint_strength:'exact',access_search_radius_m:500,maximum_best_effort_distance_m:null,approach_override:null}];
  await importRequest(imported);await page.evaluate(()=>{snapDistance=89.2;snapVary=true;});if(await mapTab.isVisible())await mapTab.click();await page.click('#generate-map');
  await page.waitForFunction(()=>document.querySelectorAll('.candidate-select').length===2);
  await page.locator('.candidate-select').nth(1).click();
  const chosen=await page.evaluate(async()=>{const{selectedCandidate}=await import('/static/state.js');return selectedCandidate().diagnostics.details.local_routing.endpoint_adjustments[0];});
  const marker=page.locator('.endpoint-adjustment-marker.routed');
  assert.equal(await marker.count(),1);assert((await marker.getAttribute('aria-label')).includes(`${Math.round(chosen.distance_m)} m`));
  const switchShow=page.locator('#endpoint-adjustments-routes summary');if(!await page.locator('#endpoint-adjustments-routes details').evaluate(e=>e.open))await switchShow.click();
  await page.locator('#endpoint-adjustments-routes [data-adjustment-action="start-show"]').click();
  for(const selector of ['.header-tools','#offline-regions']){const details=page.locator(selector);if(!await details.evaluate(e=>e.open))await details.locator(':scope > summary').click();}
  await page.selectOption('#planning-region','beta');
  await page.waitForFunction(()=>document.querySelector('#planning-region').value==='beta'&&!document.querySelector('#regional-refresh').disabled);
  assert.equal(await page.locator('.endpoint-adjustment-marker').count(),0,'region switch clears markers');
  assert(await page.locator('#endpoint-adjustments-map').evaluate(e=>e.hidden),'region switch clears disclosure');
  cases.push('imported-exact-intent-candidate-specific-markers-region-switch-cleanup');
  assert.deepEqual(errors,[]);assert(!requests.some(p=>/\/v1\/(plans|routes|generate)/.test(p)),'no server routing');
  return {name:touch?'touch':'keyboard',status:'passed',cases};
 }catch(error){const page=context.pages()[0];console.error(JSON.stringify(await page.evaluate(()=>({status:document.querySelector('#request-status')?.textContent,region:document.querySelector('#planning-region')?.value,profiles:[...document.querySelector('#profile')?.options??[]].map(o=>({value:o.value,disabled:o.disabled})),body:document.body.innerText.slice(-1500)}))));throw error;}finally{await context.close();}
}
(async()=>{const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});try{for(const touch of [false,true])console.log(JSON.stringify(await run(browser,touch)));}finally{await browser.close();}})().catch(error=>{console.error(error);process.exitCode=1});
