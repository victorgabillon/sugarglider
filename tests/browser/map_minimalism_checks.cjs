// Called by the full bundled-app driver. All UI handlers and regional workers
// are real; its native routing/terrain and model responses remain synthetic.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises'), path = require('node:path');
exports.checkMinimalMobileMap = async ({ page, width, screenshot, checkLayout }) => {
  const measurements=[];
  async function measure(stage){measurements.push(await page.evaluate(stage=>{const map=document.querySelector('#map').getBoundingClientRect();const rect=s=>{const n=document.querySelector(s);if(!n?.getClientRects().length)return null;return n.getBoundingClientRect().toJSON();};const controls=['.topbar','#route-dock','.planner-location-control','.maplibregl-ctrl-attrib','.maplibregl-ctrl-group'].map(rect).filter(Boolean).map(r=>({left:Math.max(map.left,r.left),right:Math.min(map.right,r.right),top:Math.max(map.top,r.top),bottom:Math.min(map.bottom,r.bottom)})).filter(r=>r.right>r.left&&r.bottom>r.top);const xs=[...new Set(controls.flatMap(r=>[r.left,r.right]))].sort((a,b)=>a-b),ys=[...new Set(controls.flatMap(r=>[r.top,r.bottom]))].sort((a,b)=>a-b);let obstructed=0;for(let i=1;i<xs.length;i++)for(let j=1;j<ys.length;j++){const x=(xs[i-1]+xs[i])/2,y=(ys[j-1]+ys[j])/2;if(controls.some(r=>x>=r.left&&x<=r.right&&y>=r.top&&y<=r.bottom))obstructed+=(xs[i]-xs[i-1])*(ys[j]-ys[j-1]);}return{stage,viewport:{width:innerWidth,height:innerHeight},map:map.toJSON(),header:rect('.topbar'),dock:rect('#route-dock'),credits:rect('.maplibregl-ctrl-attrib'),gps:rect('.planner-location-control'),markers:[...document.querySelectorAll('#map .required-marker')].map(n=>({label:n.getAttribute('aria-label'),rect:n.getBoundingClientRect().toJSON()})),context:adventureAppState.currentAdventureContext(),obstructed_map_area_px:obstructed,unobstructed_map_area_px:map.width*map.height-obstructed};},stage));}
  const cases = [], mobile = width <= 840;
  if (!mobile) {
    assert(await page.locator('.brand').isVisible());
    assert(await page.locator('.maplibregl-ctrl-zoom-in').isVisible());
    return ['desktop_brand_and_pointer_navigation_preserved'];
  }
  const fingerprint = () => page.evaluate(() => {
    const { state } = adventureAppState;
    return JSON.stringify({ context: adventureAppState.currentAdventureContext(), points: state.points,
      endpoints: state.waypointEndpoints, tour: state.autoTour, options: state.options,
      result: state.generationResult, source: state.generationSourceRequest, selected: state.selectedSignature });
  });
  const request = () => page.evaluate(() => adventureAppState.currentPlanRequest());
  const openEditor = async () => {
    if (await page.locator('#route-editor-toggle').getAttribute('aria-expanded') !== 'true') await page.locator('#route-editor-toggle').click();
    assert(await page.locator('#route-editor-body').isVisible());
  };
  const closeEditor = async () => {
    if (await page.locator('#route-editor-toggle').getAttribute('aria-expanded') === 'true') await page.locator('#route-editor-close').click();
    assert(!await page.locator('#route-editor-body').isVisible());
  };
  const checkTools = async () => {
    const menu=await page.locator('.header-tools-menu').boundingBox(),map=await page.locator('#map').boundingBox();
    assert(menu.x>=0&&menu.x+menu.width<=width&&menu.y>=0&&menu.y+menu.height<=map.y+map.height,'Floating Tools stays within the map, including large text: '+JSON.stringify({menu,map}));
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&!scrollX),'Opening Map display does not horizontally scroll the page');
  };
  const view = async name => { await page.locator(`[data-shell-view="${name}"]`).click(); };
  const stationary = () => page.waitForFunction(async () => !(await import('/static/map.js')).mapPresentationDiagnostics().moving);
  const mapTap = async coordinate => {
    await stationary();
    const point = await page.evaluate(async coordinate => (await import('/static/map.js')).keepCoordinateVisible(coordinate), coordinate);
    const box = await page.locator('#map').boundingBox();
    const hit=await page.evaluate(([x,y])=>document.elementFromPoint(x,y)?.outerHTML.slice(0,240),[box.x+point.x,box.y+point.y]);assert(hit?.includes('maplibregl-canvas'),'Map tap targets uncovered canvas: '+JSON.stringify({coordinate,point,box,hit}));
    await page.touchscreen.tap(box.x+point.x,box.y+point.y);
    // These are separate placement taps, outside MapLibre's 500 ms double-tap
    // window. Evidence screenshots must not supply implicit synchronization.
    await page.waitForTimeout(550);await stationary();
  };
  assert(!await page.locator('.brand').isVisible(), 'Mobile Map has no permanent brand row');
  assert.equal(await page.locator('.maplibregl-ctrl-zoom-in').count(), 0, 'Touch mobile has no navigation tower');
  assert(!await page.locator('#route-editor-body').isVisible(), 'Default route editor is collapsed');
  assert.equal(await page.locator('.map-panel > .map-tools').count(), 0);
  assert.equal(await page.locator('.header-tools .map-tools').count(), 1, 'The existing settings live inside Tools');
  assert(!await page.locator('#planner-empty').isVisible(), 'Collapsed bar is the single first-use instruction');
  const layout = await checkLayout(); assert(layout.dock.height <= 80, 'Normal-text collapsed bar stays compact');
  await screenshot('minimal-empty');await measure('empty-collapsed');
  cases.push('minimal_header_collapsed_bar_single_instruction_touch_navigation');

  const untouched = await fingerprint();
  await page.locator('.header-tools > summary').click();
  await page.locator('.header-tools .map-tools > summary').click();
  await checkTools();
  if (width === 372) {
    // The real Fairphone WebView reports a 37 px top inset even though Android
    // already positions the WebView below its status bar.
    const insets = await page.context().newCDPSession(page);
    try {
      await insets.send('Emulation.setSafeAreaInsetsOverride', { insets: { top: 37, left: 0, right: 0, bottom: 0 } });
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      assert((await page.locator('.topbar').boundingBox()).y >= 37, 'The native safe-area inset is actually applied');
      await checkTools(); await screenshot('minimal-tools-native-insets');
      await page.evaluate(() => { document.documentElement.style.fontSize = '32px'; });
      await checkTools(); await screenshot('minimal-tools-native-insets-large-text');
    } finally {
      await page.evaluate(() => { document.documentElement.style.fontSize = ''; });
      await insets.send('Emulation.setSafeAreaInsetsOverride', { insets: { top: 0, left: 0, right: 0, bottom: 0 } });
      await insets.detach();
    }
    cases.push('tools_native_safe_area_and_large_text_clear_bottom_navigation');
  }
  await screenshot('minimal-tools-map-display');
  const count = await page.evaluate(() => adventureNativeCalls.length);
  assert(await page.locator('#show-nature').isDisabled(), 'Unavailable nature coloring stays explicitly disabled in the bundled planner');
  const direction = await page.locator('#show-direction').isChecked();
  await page.locator('#show-direction').setChecked(!direction); await page.locator('#show-direction').setChecked(direction);
  const camera = () => page.evaluate(async () => (await import('/static/map.js')).mapPresentationDiagnostics().camera);
  const zoom = (await camera()).zoom;
  await page.locator('#map-zoom-in').click(); await stationary(); assert((await camera()).zoom > zoom);
  await page.locator('#map-zoom-out').click(); await stationary();
  await page.locator('#map-reset-north').click(); await stationary(); assert.equal((await camera()).bearing,0);
  assert.equal(await fingerprint(), untouched, 'Display actions never change canonical planning state');
  assert(!await page.evaluate(n=>adventureNativeCalls.slice(n).some(c=>['local_route','chatgpt_infer','adventure_speech_start'].includes(c.type)),count));
  await page.locator('.header-tools > summary').click();
  cases.push('tools_settings_retained_accessible_zoom_north_no_planning_calls');

  const cdp = await page.context().newCDPSession(page);
  try {
    const box=await page.locator('#map').boundingBox(), cx=box.x+box.width*.5, cy=box.y+box.height*.4;
    const send=(type,points)=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:points.map(([id,x,y])=>({id,x,y,radiusX:2,radiusY:2,force:1}))});
    const prior=await camera();
    await send('touchStart',[[0,cx-35,cy],[1,cx+35,cy]]);
    for(let i=1;i<=8;i++){await send('touchMove',[[0,cx-35-i*5,cy-i*2],[1,cx+35+i*5,cy+i*2]]);await page.waitForTimeout(20);}
    await send('touchEnd',[]);await page.waitForTimeout(650);await stationary();
    assert((await camera()).zoom > prior.zoom+.1, 'Two-finger gesture actually zooms the map');
    assert.equal(await fingerprint(),untouched,'Pinch/rotation emits no point-add compatibility click');
    const panned=await camera();
    await send('touchStart',[[0,cx,cy]]);
    for(let i=1;i<=8;i++){await send('touchMove',[[0,cx+i*5,cy+i*2]]);await page.waitForTimeout(20);}
    await send('touchEnd',[]);await page.waitForTimeout(500);await stationary();
    assert.notDeepEqual((await camera()).center,panned.center,'One-finger gesture pans');
    assert.equal(await fingerprint(),untouched,'Pan does not add or move a route point');
  } finally { await cdp.detach(); }
  cases.push('real_browser_multitouch_pinch_rotation_pan_preserve_plan');

  await page.evaluate(async()=>{(await import('/static/map.js')).resetMapNorth();});await stationary();
  await page.evaluate(async()=>{(await import('/static/map.js')).fitCoordinates([[.003,.003],[.017,.017]],{maxZoom:15});});await page.waitForTimeout(650);await stationary();
  await mapTap([.006,.006]); assert(!await page.locator('#route-editor-body').isVisible()); await screenshot('minimal-start');
  // Keep placements clear of the tall existing pins, even at landscape's
  // lower fitted zoom. Selecting a marker is tested separately below.
  await mapTap([.018,.006]);assert.equal((await request()).waypoints.length,1,'First separate canvas tap adds the first stop');await mapTap([.002,.018]);
  assert.equal((await request()).waypoints.length,2);assert(!await page.locator('#route-editor-body').isVisible());
  await page.locator('.header-tools > summary').click();await page.locator('#map-fit-points').click();await page.locator('.header-tools > summary').click();await page.waitForTimeout(650);await stationary();await screenshot('minimal-two-stops');await measure('two-stops-collapsed');
  assert(await page.evaluate(()=>{const map=document.querySelector('#map').getBoundingClientRect();return [...document.querySelectorAll('#map .required-marker')].every(n=>{const r=n.getBoundingClientRect();return r.left>=map.left&&r.right<=map.right&&r.top>=map.top&&r.bottom<=map.bottom;});}),'Fit points exposes Start and both stop pins');
  const beforeSelection=await fingerprint();
  await page.locator('#map .required-marker[data-point-index="0"]').click();
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  assert(await page.locator('#route-editor-body').isVisible(),'Selecting a marker reveals its contextual editor');
  assert(await page.locator('[data-dock-action="move"]').isVisible());
  const actions = await page.evaluate(()=>{const body=document.querySelector('#route-editor-body').getBoundingClientRect(),move=document.querySelector('[data-dock-action="move"]').getBoundingClientRect(),heading=document.querySelector('.route-editor-heading').getBoundingClientRect();return {visible:move.top>=heading.bottom&&move.bottom<=body.bottom,body:body.toJSON(),move:move.toJSON(),heading:heading.toJSON(),scroll:document.querySelector('#route-editor-body').scrollTop};});
  await screenshot('minimal-selected-actions-check');
  assert(actions.visible,'Selected point actions are visible immediately, including short landscape sheets: '+JSON.stringify(actions));
  assert.equal(await fingerprint(),beforeSelection,'Selection does not edit canonical route');
  const clear=await page.evaluate(()=>{const pin=document.querySelector('#map .required-marker[data-point-index="0"]').getBoundingClientRect(),canvas=document.querySelector('#map').getBoundingClientRect();const obstacles=['.topbar','#route-dock','.planner-location-control','.maplibregl-ctrl-attrib'].map(s=>document.querySelector(s)).filter(n=>n?.getClientRects().length).map(n=>n.getBoundingClientRect());return {visible:pin.left>=canvas.left&&pin.right<=canvas.right&&pin.top>=canvas.top&&pin.bottom<=canvas.bottom&&obstacles.every(r=>!(pin.left<r.right&&pin.right>r.left&&pin.top<r.bottom&&pin.bottom>r.top)),pin:pin.toJSON(),canvas:canvas.toJSON(),obstacles:obstacles.map(r=>r.toJSON())};});
  assert(clear.visible,'Selected painted pin remains visible beside/above actual controls: '+JSON.stringify(clear));
  await screenshot('minimal-selected-stop-expanded');await measure('selected-expanded');
  if(width===372){
    const original=await fingerprint();await page.evaluate(()=>{document.documentElement.style.fontSize='32px';});
    await page.waitForTimeout(150);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Expanded editor fits at 200% text');
    assert((await page.locator('#route-editor-body').boundingBox()).height>=44,'Expanded editor retains usable scrolling space');
    await screenshot('minimal-editor-large-text');
    await page.locator('.header-tools > summary').click();await checkTools();await page.locator('#application-language').selectOption('en');await page.locator('.header-tools > summary').click();
    assert(await page.locator('#route-editor-body').isVisible(),'Language switch retains the expanded editor');await screenshot('minimal-editor-large-text-en');
    await page.locator('.header-tools > summary').click();await page.locator('#application-language').selectOption('fr');await page.locator('.header-tools > summary').click();
    await closeEditor();await checkLayout();await screenshot('minimal-route-large-text-collapsed');
    assert.equal(await fingerprint(),original,'Large text and dismissal preserve the full route');
    await page.evaluate(()=>{document.documentElement.style.fontSize='';});await openEditor();
    cases.push('selected_editor_and_collapsed_route_at_200_percent_text');
  }
  const selected=await fingerprint();await closeEditor();assert.equal(await fingerprint(),selected,'Dismiss preserves selection and route');
  await page.locator('#map .required-marker[data-point-index="0"]').focus();await page.keyboard.press('Enter');
  assert(await page.locator('#route-editor-body').isVisible(),'Keyboard marker activation reopens the editor');
  cases.push('map_taps_grammar_marker_context_dismiss_reselect_keyboard');

  const beforeMove=await request();
  await page.locator('[data-dock-action="move"]').click();await page.locator('[data-dock-action="move-map"]').click();await mapTap([.018,.002]);
  const moved=await request();assert.equal(moved.waypoints.length,2);assert.notDeepEqual(moved.waypoints[0].coordinate,beforeMove.waypoints[0].coordinate);
  await page.locator('#undo-point-edit').click();assert.deepEqual(await request(),beforeMove);await page.locator('#redo-point-edit').click();assert.deepEqual(await request(),moved);
  await page.locator('[data-dock-action="more"]').click();await page.locator('[data-dock-action="later"]').click();const reordered=await request();assert.deepEqual({...reordered.waypoints[1],id:moved.waypoints[0].id},moved.waypoints[0]);assert.equal(reordered.waypoints[1].id,'route-waypoint-2','Canonical positional IDs follow the existing visit order');
  await page.locator('[data-dock-action="more"]').click();await page.locator('[data-dock-action="remove"]').click();assert.equal((await request()).waypoints.length,1);
  await page.locator('#undo-point-edit').click();assert.deepEqual(await request(),reordered);await page.locator('#redo-point-edit').click();assert.equal((await request()).waypoints.length,1);await page.locator('#undo-point-edit').click();
  await page.locator('#dock-finish').selectOption('point_to_point');assert.equal((await request()).topology,'point_to_point');
  await page.locator('#dock-finish').selectOption('loop');assert.equal((await request()).topology,'loop');
  await page.locator('#dock-order').selectOption('optimize');assert.equal((await request()).waypoint_order,'optimize');
  await page.locator('#dock-order').selectOption('fixed');
  cases.push('move_delete_reorder_history_topology_order_same_authorities');

  await page.context().route('https://data.geopf.fr/geocodage/search**',route=>route.fulfill({json:{type:'FeatureCollection',features:[]}}));
  await page.locator('#dock-add').click();await page.locator('[data-dock-action="search-location"]').click();
  await page.locator('#location-search-query').fill('Fixture');await page.locator('#location-search-submit').click();
  await page.locator('#location-search-local button').first().waitFor();await page.locator('#location-search-local button').first().click();
  assert((await request()).waypoints.some(p=>/fixture/i.test(p.coordinate.name)),'Named local search uses the actual point acquisition handler');
  cases.push('local_search_adds_named_location_through_existing_handler');

  await closeEditor();await page.locator('#generate-map').click();
  await page.waitForFunction(()=>adventureAppState.state.request.status==='success');
  const routeCalls=await page.evaluate(()=>adventureNativeCalls.filter(c=>c.type==='local_route').length);assert(routeCalls>0);
  const candidateButtons=page.locator('#candidate-list .candidate-select');assert(await candidateButtons.count()>0);await candidateButtons.last().click();
  await view('map');await screenshot('minimal-generated-route');await checkLayout();
  const exact=await page.evaluate(async()=>{const{selectedCandidate}=await import('/static/state.js');return(await import('/static/local_gpx_export.js')).exportCanonicalCandidate(selectedCandidate()).blob.text();});
  await view('routes');await page.evaluate(()=>{globalThis.adventureSavedGpx=null;});await page.locator('#download-gpx').click();await page.waitForFunction(()=>adventureSavedGpx!==null);
  assert.equal(await page.evaluate(()=>adventureSavedGpx),exact,'UI GPX export serializes the exact selected candidate');
  assert.equal(await page.evaluate(()=>adventureNativeCalls.filter(c=>c.type==='local_route').length),routeCalls,'Selection/export never routes again');
  const generated=await fingerprint();for(const name of ['plan','routes','map'])await view(name);assert.equal(await fingerprint(),generated);
  await page.locator('#ask-chatgpt').click();assert(await page.locator('#adventure-dialog').evaluate(n=>n.open));await page.locator('#adventure-close').click();assert.equal(await fingerprint(),generated);
  cases.push('normal_synthetic_native_pipeline_candidate_inspection_exact_gpx_navigation_ai');

  await openEditor();let n=0;
  while(!await page.locator('#undo-point-edit').isDisabled()){await page.locator('#undo-point-edit').click();assert(++n<32);}
  await closeEditor();
  const context=await page.evaluate(()=>adventureAppState.currentAdventureContext());assert.equal(context.start,null);assert.equal(context.end,null);assert.equal(context.hardWaypoints.length,0);
  cases.push('undo_all_restores_empty_intent_without_test_state_injection');
  await page.evaluate(()=>{globalThis.adventureSavedGpx=null;});
  if(process.env.MOBILE_EVIDENCE_DIR){await fs.mkdir(process.env.MOBILE_EVIDENCE_DIR,{recursive:true});await fs.writeFile(path.join(process.env.MOBILE_EVIDENCE_DIR,`map-measurements-${width}.json`),JSON.stringify(measurements,null,2)+'\n');}
  return cases;
};
