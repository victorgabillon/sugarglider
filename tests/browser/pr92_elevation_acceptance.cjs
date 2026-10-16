// Synthetic UI only. Real native Generate/device acceptance is recorded separately.
// PLAYWRIGHT_MODULE and CHROMIUM_EXECUTABLE may select an existing local install.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs'), path = require('node:path'), http = require('node:http');
const assert = require('node:assert/strict');
const root = process.cwd(), evidence = process.env.ELEVATION_EVIDENCE_DIR;
if (!evidence) throw Error('Set ELEVATION_EVIDENCE_DIR outside Git');
fs.mkdirSync(evidence, {recursive:true});
const types = {'.html':'text/html', '.js':'text/javascript', '.mjs':'text/javascript', '.css':'text/css', '.json':'application/json', '.png':'image/png'};
const server = http.createServer((request,response) => {
  let pathname;
  try { pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname); }
  catch { response.writeHead(400).end(); return; }
  const relative = pathname.startsWith('/static/') ? `src/sugarglider/web${pathname}` : pathname.slice(1);
  const file = path.resolve(root, relative);
  if (!file.startsWith(root + path.sep)) { response.writeHead(404).end(); return; }
  fs.readFile(file, (error, bytes) => {
    if (error) { response.writeHead(404).end(); return; }
    response.writeHead(200, {'Content-Type':types[path.extname(file)] || 'application/octet-stream'}).end(bytes);
  });
});

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({headless:true, args:['--enable-unsafe-swiftshader'], ...(process.env.CHROMIUM_EXECUTABLE ? {executablePath:process.env.CHROMIUM_EXECUTABLE} : {})});
  const reports = [];
  try {
    for (const width of [360,390,420,1280]) {
      const context = await browser.newContext({viewport:{width,height:844},isMobile:width<500,hasTouch:width<500,serviceWorkers:'block'});
      const page = await context.newPage(), errors = [], external = [];
      page.on('pageerror', error => errors.push(error.message));
      await context.route('**/*', route => {
        if (new URL(route.request().url()).origin === base) return route.continue();
        external.push(route.request().url()); return route.abort();
      });
      await page.goto(base + '/tests/browser/pr92_elevation_ui_harness.html');
      await page.waitForFunction(() => document.querySelector('#results').dataset.status);
      assert.equal(await page.locator('#results').getAttribute('data-status'), 'passed', await page.locator('#results').textContent());
      const control = page.locator('.elevation-profile-control');
      await control.scrollIntoViewIfNeeded();
      const geometry = await page.evaluate(async () => {
        const {projectElevationProfile} = await import('/static/elevation_profile.js');
        const svg = document.querySelector('.elevation-profile-control svg'), bounds = svg.getBoundingClientRect();
        const {left,right} = projectElevationProfile({route_distance_m:100,samples:[{distance_m:0,filtered_height_m:0,segment_index:0},{distance_m:100,filtered_height_m:0,segment_index:0}],segments:[{first_index:0,last_index:1}],parameters:{maximum_gap_m:100}},[[0,0],[1,1]],bounds.width);
        window.elevationPathBefore = document.querySelector('.elevation-profile-line');
        return {left:bounds.left+left,right:bounds.left+right,y:bounds.top+bounds.height/2,renders:window.elevationHarness.view.diagnostics().chart_renders};
      });
      const x = fraction => geometry.left+(geometry.right-geometry.left)*fraction;
      await page.mouse.move(x(.25), geometry.y);
      await page.waitForFunction(() => Math.abs(window.elevationHarness.view.diagnostics().position?.distance_m-25)<0.1);
      await control.focus(); await page.keyboard.press('Home'); await page.keyboard.press('ArrowRight');
      assert.equal(await page.evaluate(() => window.elevationHarness.view.diagnostics().position.distance_m),50);
      assert((await control.getAttribute('aria-valuetext')).includes('15.0 metres'));
      if (width < 500) {
        const session = await context.newCDPSession(page);
        await session.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:x(.1),y:geometry.y}]});
        for (const fraction of [.2,.4,.6,.8,.9]) {
          await session.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x(fraction),y:geometry.y}]});
          await page.waitForTimeout(20);
        }
        await session.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
        await page.waitForFunction(() => Math.abs(window.elevationHarness.view.diagnostics().position?.distance_m-90)<0.1);
        const before = await page.evaluate(() => scrollY);
        // Vertical touch remains browser scrolling, rather than a captured scrub.
        await session.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:x(.5),y:geometry.y}]});
        for (const delta of [15,35,60,90]) {
          await session.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x(.5),y:geometry.y-delta}]});
          await page.waitForTimeout(20);
        }
        await session.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
        await page.waitForTimeout(150);
        assert(await page.evaluate(() => scrollY)>before,'vertical chart gesture must scroll');
        await session.detach();
      }
      const state = await page.evaluate(() => ({diagnostics:window.elevationHarness.view.diagnostics(),
        stablePath:window.elevationPathBefore===document.querySelector('.elevation-profile-line'),
        overflow:document.documentElement.scrollWidth>innerWidth,
        sliderCount:document.querySelectorAll('[role=slider]').length}));
      assert(state.stablePath);assert.equal(state.sliderCount,1);assert(!state.overflow);
      assert.equal(state.diagnostics.chart_renders,geometry.renders);
      const mapLifecycle = await page.evaluate(async () => {
        const maplibre = await import('/static/vendor/maplibre-gl-6.4.1/maplibre-gl.mjs');
        const {createElevationMapMarker} = await import('/static/elevation_map_marker.js');
        const host = document.createElement('div'); host.style.cssText='width:300px;height:200px'; document.body.append(host);
        const style = color => ({version:8,sources:{},layers:[{id:'background',type:'background',paint:{'background-color':color}}]});
        const map = new maplibre.Map({container:host,center:[2,48],zoom:10,style:style('#fffaf0'),attributionControl:false});
        await new Promise(resolve => map.once('load',resolve));
        const marker = createElevationMapMarker({createMarker:element=>new maplibre.Marker({element,anchor:'center'})});
        marker.attach(map);marker.show({coordinate:[2,48],distance_m:50,height_m:15});
        const element=host.querySelector('.elevation-map-marker');
        const loaded = new Promise(resolve => map.once('style.load',resolve)); map.setStyle(style('#e7eee2')); await loaded;
        host.style.width='280px';map.resize();
        const stable=element===host.querySelector('.elevation-map-marker')&&element.isConnected&&marker.diagnostics().created===1;
        map.remove();const cleared=!marker.diagnostics().active&&!host.querySelector('.elevation-map-marker');
        marker.destroy();host.remove();return {stable_after_real_style_reload_and_resize:stable,cleared_after_real_map_remove:cleared};
      });
      assert(mapLifecycle.stable_after_real_style_reload_and_resize);assert(mapLifecycle.cleared_after_real_map_remove);
      assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
      await control.scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(evidence,`elevation-${width}.png`),fullPage:false});
      reports.push({width,checks:['projection/coverage/lifecycle harness','real mouse hover','keyboard sample navigation',
        ...(width<500?['real Chromium touch drag','vertical touch scrolling']:[]),'real MapLibre style reload/resize/remove','stable paths and no external requests'],state,mapLifecycle});
      await context.close();
    }
    fs.writeFileSync(path.join(evidence,'acceptance.json'),JSON.stringify(reports,null,2));
    console.log(JSON.stringify(reports));
  } finally { await browser.close(); await new Promise(resolve=>server.close(resolve)); }
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
