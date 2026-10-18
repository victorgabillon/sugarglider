// Actual bundled application with only the catalog response delayed. No map data,
// routing results, DEM, network service or planner-state injection is used.
const fs = require('node:fs/promises');
const path = require('node:path');
const origin = 'https://appassets.androidplatform.net';
const profiles = ['trail_run', 'hike', 'city_bike', 'gravel_bike', 'mountain_bike', 'road_bike'];

async function runBundledStartupRegression(browser, root, { offlineConfig = false } = {}) {
  const context = await browser.newContext();
  let releaseCatalog;
  let catalogRequested;
  const catalogGate = new Promise(resolve => { releaseCatalog = resolve; });
  const requested = new Promise(resolve => { catalogRequested = resolve; });
  const cases = [];
  try {
    await context.addInitScript(() => {
      globalThis.startupNativeRequests = [];
      globalThis.sugargliderNative = {
        onmessage: null,
        postMessage(payload) {
          const request = JSON.parse(payload);
          startupNativeRequests.push(request.type);
          if (request.type !== 'hello') throw Error(`Unexpected startup native request: ${request.type}`);
          queueMicrotask(() => this.onmessage?.({ data: JSON.stringify({ schema_version: 1,
            request_id: request.request_id, type: 'hello_result', outing_slug: null,
            participant_id: null, active: false, state: 'stopped', last_published_at: null,
            pending_sample: false, stop_warning: null }) }));
        },
      };
    });
    await context.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) return route.abort();
      if (url.pathname === '/static/offline_region_catalog.json') {
        catalogRequested();
        await catalogGate;
        return route.fulfill({ json: { schema_version: 1, regions: [] } });
      }
      if (url.pathname === '/v1/ui/config' && offlineConfig) return route.abort();
      const relative = url.pathname === '/' ? 'index.html'
        : url.pathname === '/v1/ui/config' ? 'android_ui_config.json'
        : url.pathname === '/manifest.webmanifest' ? 'manifest.webmanifest'
        : url.pathname.replace(/^\/static\//u, '');
      const base = path.join(root, 'src/sugarglider/web/static');
      const file = path.resolve(base, relative);
      if (!file.startsWith(`${base}${path.sep}`)) return route.abort();
      const types = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
        '.json': 'application/json', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png' };
      try { return await route.fulfill({ body: await fs.readFile(file), contentType: types[path.extname(file)] ?? 'application/octet-stream' }); }
      catch { return route.fulfill({ status: 404, body: '' }); }
    });
    const page = await context.newPage();
    await page.goto(`${origin}/`, { waitUntil: 'domcontentloaded' });
    await requested;
    const baseRequest = { schema_version: 1, kind: 'waypoint_route', name: 'Startup import',
      topology: 'point_to_point', start: { lat: 48.871281, lon: 2.095997 },
      end: { lat: 48.889384, lon: 2.099125 }, candidate_count: 1, seed: 0,
      distance_objective: { target_m: 4000, tolerance_m: 1000, maximum_m: null, priority: 'flexible' },
      preferences: { nature: 'off', path_selection: 'shortest', loop_geometry: 'off' },
      waypoints: [], waypoint_order: 'fixed' };
    for (const profile of profiles) {
      await page.evaluate(request => {
        const transfer = new DataTransfer();
        transfer.items.add(new File([JSON.stringify(request)], 'startup.json', { type: 'application/json' }));
        const input = document.querySelector('#request-file');
        input.files = transfer.files;
        input.dispatchEvent(new Event('change', { bubbles: true }));
      }, { ...baseRequest, routing_profile: profile });
      await page.waitForFunction(async expected => {
        const { state } = await import('/static/state.js');
        if (document.querySelector('#error-details').textContent.includes('unknown routing profile')) throw Error('Known profile rejected while regional verification is pending');
        return state.planningMode === 'waypoint_route' && state.routingProfile === expected && state.waypointEndpoints.start?.lat === 48.871281;
      }, profile, { timeout: 1500 }).catch(async error => {
        const diagnostic = await page.evaluate(async () => { const { state } = await import('/static/state.js'); return { catalog: state.routingProfileCatalog, mode: state.planningMode, profile: state.routingProfile, error: document.querySelector('#error-details').textContent }; });
        throw Error(`${profile}: ${error.message}; ${JSON.stringify(diagnostic)}`);
      });
      const snapshot = await page.evaluate(async () => {
        const { state, currentPlanRequest } = await import('/static/state.js');
        return { request: currentPlanRequest(), disabled: document.querySelector('#generate').disabled,
          available: state.routingProfileCatalog.profiles.some(row => row.available),
          native: startupNativeRequests.filter(type => ['local_route', 'route_elevation'].includes(type)) };
      });
      if (snapshot.request.routing_profile !== profile || !snapshot.disabled || snapshot.available || snapshot.native.length) {
        throw Error(`Import bypassed verification or changed profile: ${JSON.stringify(snapshot)}`);
      }
      cases.push(`pending_region_import_${profile}`);
    }
    const before = await page.evaluate(async () => JSON.stringify((await import('/static/state.js')).currentPlanRequest()));
    await page.evaluate(request => {
      const transfer = new DataTransfer(); transfer.items.add(new File([JSON.stringify(request)], 'unknown.json'));
      const input = document.querySelector('#request-file'); input.files = transfer.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }, { ...baseRequest, routing_profile: 'walking' });
    await page.waitForFunction(() => document.querySelector('#error-details').textContent.includes('unknown routing profile'));
    const after = await page.evaluate(async () => JSON.stringify((await import('/static/state.js')).currentPlanRequest()));
    if (before !== after) throw Error('Unknown profile changed the imported request');
    cases.push('unknown_alias_rejected_without_draft_mutation');
    releaseCatalog();
    await page.waitForFunction(() => document.querySelector('#regional-status').textContent.includes('Download a region'));
    const stateAfter = await page.evaluate(async () => {
      const { state } = await import('/static/state.js');
      return { profile: state.routingProfile, available: state.routingProfileCatalog.profiles.some(row => row.available),
        disabled: document.querySelector('#generate').disabled };
    });
    if (stateAfter.profile !== profiles.at(-1) || stateAfter.available || !stateAfter.disabled) throw Error('Missing region enabled routing or replaced imported identity');
    cases.push('missing_region_stays_unavailable_preserves_imported_profile');
    return cases;
  } finally { releaseCatalog(); await context.close(); }
}
module.exports = { runBundledStartupRegression };
if (require.main === module) {
  const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
  (async () => {
    const browser = await chromium.launch({ headless: true,
      ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}) });
    try { for (const offlineConfig of [false, true]) { const cases = await runBundledStartupRegression(browser, path.resolve(__dirname, '../..'), { offlineConfig }); console.log(JSON.stringify({ name: 'bundled_startup_import', offlineConfig, status: 'passed', cases })); } }
    finally { await browser.close(); }
  })().catch(error => { console.error(error); process.exitCode = 1; });
}
