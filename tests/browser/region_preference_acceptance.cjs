// The actual bundled app, real optional IndexedDB and verified synthetic OPFS
// web components. Only the native capabilities reply is a synthetic acknowledgement.
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const origin = 'https://appassets.androidplatform.net';
const root = path.resolve(__dirname, '../..');
const profiles = ['trail_run', 'hike', 'city_bike', 'gravel_bike', 'mountain_bike', 'road_bike'];

async function chooseAndRemember(page, regionId) {
  // A ready message precedes completion of the map refresh. Wait for controls,
  // then exercise the normal enabled selector instead of forcing a change.
  await page.waitForFunction(() => !document.querySelector('#planning-region').disabled
    && !document.querySelector('#regional-refresh').disabled);
  for (const selector of ['.header-tools', '#offline-regions']) {
    const details = page.locator(selector);
    if (!await details.evaluate(element => element.open)) await details.locator(':scope > summary').click();
  }
  await page.selectOption('#planning-region', regionId ?? '');
  await page.waitForFunction(id => document.querySelector('#planning-region').value === (id ?? '')
    && !document.querySelector('#planning-region').disabled
    && !document.querySelector('#regional-refresh').disabled, regionId);
  // In pinned Playwright 1.58, waitForFunction does not poll an async predicate:
  // its Promise is truthy even when it resolves false. Await each storage read
  // from Node and check the resolved value before allowing a reload.
  const deadline = Date.now() + 30_000;
  let stored;
  do {
    stored = await page.evaluate(async () => {
      const { store } = await (await import('/static/pwa_runtime.js')).pwaRuntime();
      return await store.get('public_runtime', 'planner-region-id') ?? null;
    });
    if (stored === regionId) return;
    await page.waitForTimeout(25);
  } while (Date.now() < deadline);
  assert.equal(stored, regionId, 'The selected region preference did not commit before reload');
}

async function startup(browser, scenario) {
  const context = await browser.newContext();
  const requests = [], errors = [];
  let releaseCatalog, catalogRequested;
  const gate = new Promise(resolve => { releaseCatalog = resolve; });
  const requested = new Promise(resolve => { catalogRequested = resolve; });
  let page, phase = 'setup';
  try {
    await context.addInitScript(({ profiles, scenario }) => {
      globalThis.preferenceEvents = [];
      globalThis.preferenceNative = [];
      const get = IDBObjectStore.prototype.get;
      IDBObjectStore.prototype.get = function(key) {
        if (key === 'planner-region-id' && scenario.storageUnavailable) throw Error('Optional preference read unavailable');
        const request = get.call(this, key);
        if (key === 'planner-region-id') request.addEventListener('success', () => preferenceEvents.push({ type: 'preference_read', region_id: request.result?.value }));
        return request;
      };
      const directory = FileSystemDirectoryHandle.prototype.getDirectoryHandle;
      FileSystemDirectoryHandle.prototype.getDirectoryHandle = function(name, options) {
        if (name === 'sugarglider-map-packs' && /^[a-f0-9]{64}$/u.test(this.name)) preferenceEvents.push({ type: 'map_open', build: this.name });
        return directory.call(this, name, options);
      };
      globalThis.sugargliderNative = { onmessage: null, postMessage(payload) {
        const request = JSON.parse(payload); preferenceNative.push(request);
        let reply;
        if (request.type === 'hello') reply = { type: 'hello_result', outing_slug: null, participant_id: null,
          active: false, state: 'stopped', last_published_at: null, pending_sample: false, stop_warning: null };
        else if (request.type === 'get_local_route_capabilities') {
          const id = request.regional_reference.pack_id;
          reply = { type: 'local_route_capabilities_result', enabled: !scenario.nativeUnavailable,
            engine: 'valhalla-mobile', engine_version: '3.9.1', installed_pack_count: 1,
            installed_pack_ids: [id], supported_profile_ids: profiles,
            pack_capabilities: [{ pack_id: id, access_modes: ['foot', 'bicycle'] }] };
        } else if (request.type === 'itinerary_dialog_state') return;
        else throw Error(`Unexpected automatic native operation: ${request.type}`);
        queueMicrotask(() => this.onmessage?.({ data: JSON.stringify({ schema_version: 1,
          request_id: request.request_id, ...reply }) }));
      } };
    }, { profiles, scenario });
    await context.route('**/*', async route => {
      const url = new URL(route.request().url());
      requests.push(url.pathname);
      if (url.origin !== origin) throw Error(`Startup attempted an external request: ${url.origin}`);
      if (url.pathname === '/seed.html') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>Synthetic region setup</title><script src="/static/vendor/pmtiles-4.5.0/pmtiles.js"></script>' });
      if (url.pathname === '/static/offline_region_catalog.json') {
        catalogRequested(); await gate;
        return route.fulfill({ json: { schema_version: 1, regions: [] } });
      }
      if (url.pathname === '/v1/ui/config' && scenario.offline) return route.abort();
      const relative = url.pathname.startsWith('/tests/') || url.pathname.startsWith('/src/')
        ? url.pathname.slice(1) : 'src/sugarglider/web/static/' + (url.pathname === '/' ? 'index.html'
          : url.pathname === '/v1/ui/config' ? 'android_ui_config.json' : url.pathname.replace(/^\/static\//u, ''));
      const file = path.resolve(root, relative);
      if (!file.startsWith(root + path.sep)) return route.abort();
      const mime = { '.js': 'text/javascript', '.mjs': 'text/javascript', '.html': 'text/html', '.json': 'application/json', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml' };
      try { return route.fulfill({ body: await fs.readFile(file), contentType: mime[path.extname(file)] ?? 'application/octet-stream' }); }
      catch { return route.fulfill({ status: 404, body: '' }); }
    });
    page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
    await page.goto(origin + '/seed.html');
    if (scenario.runHarness) {
      const cases = await page.evaluate(async () => (await import('/tests/browser/region_preference_harness.js')).runRegionPreferenceHarness());
      assert.deepEqual(errors, []);
      return { name: scenario.name, ...(scenario.repeat === undefined ? {} : { repeat: scenario.repeat }), status: 'passed', cases: cases.length };
    }
    const installed = await page.evaluate(async scenario => {
      const { seedRegion } = await import('/tests/browser/region_preference_harness.js');
      const { createRegionVersionStore } = await import('/static/region_versions.js');
      const { openPwaStore, PWA_STORES } = await import('/static/pwa_store.js');
      const fixture = await (await fetch('/tests/fixtures/pr40_regional_data.json')).json();
      const versions = createRegionVersionStore(), manifests = {};
      for (const id of scenario.regions) manifests[id] = await seedRegion(fixture, versions, id, id);
      if (scenario.update) manifests.beta = await seedRegion(fixture, versions, 'beta', 'Updated beta');
      if (scenario.interrupted) await seedRegion(fixture, versions, 'beta', 'Interrupted beta', { commit: false });
      if (scenario.deleted) await versions.removeRegion('beta');
      if (scenario.corruptMap) {
        const manifest = manifests.beta, directory = await versions.committedDirectory('beta', manifest.build_id);
        const pack = await (await directory.getDirectoryHandle('sugarglider-map-packs')).getDirectoryHandle(manifest.components.map.component_id);
        const file = await pack.getFileHandle('basemap.pmtiles');
        const writer = await file.createWritable(); await writer.write('corrupted'); await writer.close();
      }
      const store = await openPwaStore();
      await store.put(PWA_STORES.trailProfile, 'current', { schema_version: 1, display_name: 'Synthetic reviewer', avatar_key: 'blue' });
      if (Object.hasOwn(scenario, 'preference')) await store.put(PWA_STORES.publicRuntime, 'planner-region-id', scenario.preference);
      return manifests;
    }, scenario);
    requests.length = 0;
    if (scenario.offline) await context.setOffline(true);
    phase = 'initial startup';
    await page.goto(origin + '/', { waitUntil: 'domcontentloaded' });
    await requested;
    // Before catalog discovery/region-screen initialization, observe the *first*
    // regional map open. This catches restoring a preference too late in start().
    const early = await page.evaluate(async () => ({ events: preferenceEvents,
      snapshot: (await import('/static/offline_map.js')).offlineMapSnapshot() }));
    const opens = early.events.filter(event => event.type === 'map_open');
    if (scenario.expected) {
      assert.ok(opens.length > 0, `${scenario.name}: first scan did not open selected map`);
      assert.equal(opens[0].build, installed[scenario.expected].build_id, `${scenario.name}: wrong first map`);
      if (!scenario.storageUnavailable) {
        const readIndex = early.events.findIndex(event => event.type === 'preference_read');
        assert.ok(readIndex >= 0 && readIndex < early.events.findIndex(event => event.type === 'map_open'), 'Map checked before preference read finished');
      }
    } else assert.equal(opens.length, 0, 'Ambiguous choice opened an arbitrary map');
    releaseCatalog();
    await page.waitForFunction(() => !document.querySelector('#regional-refresh').disabled
      && !['', 'regional_checking'].includes(document.querySelector('#regional-status').dataset.state));
    const result = await page.evaluate(async () => ({
      selected: document.querySelector('#planning-region').value,
      status: document.querySelector('#regional-status').dataset.state,
      map: (await import('/static/offline_map.js')).offlineMapSnapshot(),
      candidate: (await import('/static/state.js')).selectedCandidate(),
      generation: (await import('/static/state.js')).state.generationResult,
      native: preferenceNative,
    }));
    assert.equal(result.selected, scenario.expected ?? '');
    assert.equal(result.status, scenario.failure ?? (scenario.expected ? 'regional_ready' : 'regional_selection_required'));
    if (scenario.expected && !scenario.corruptMap) assert.equal(result.map.packs[0].pack_id, installed[scenario.expected].components.map.component_id);
    assert.ok(result.native.every(request => ['hello', 'get_local_route_capabilities', 'itinerary_dialog_state'].includes(request.type)), `Restoration generated a route/download: ${JSON.stringify(result.native)}`);
    if (scenario.expected) assert.ok(result.native.filter(request => request.type === 'get_local_route_capabilities')
      .every(request => request.regional_reference.build_id === installed[scenario.expected].build_id));
    assert.equal(requests.some(url => /\.(pmtiles|gz|tar)$/u.test(url) || /\/v[12]\/.*(plan|route)/u.test(url)), false, 'Startup downloaded a region or generated a route');
    if (scenario.switchAndClear) {
      phase = 'select beta and commit';
      await chooseAndRemember(page, 'beta');
      phase = 'reload remembered beta';
      await page.reload();
      await page.waitForFunction(() => document.querySelector('#regional-status').dataset.state === 'regional_ready');
      assert.equal(await page.locator('#planning-region').inputValue(), 'beta');
      assert.equal(await page.evaluate(() => preferenceEvents.find(event => event.type === 'map_open').build), installed.beta.build_id);
      phase = 'clear selection and commit';
      await chooseAndRemember(page, null);
      phase = 'reload cleared selection';
      await page.reload();
      await page.waitForFunction(() => document.querySelector('#regional-status').dataset.state === 'regional_selection_required');
      assert.equal(await page.locator('#planning-region').inputValue(), '');
      assert.equal(await page.evaluate(() => preferenceEvents.filter(event => event.type === 'map_open').length), 0);
      assert.equal(await page.evaluate(() => preferenceNative.some(request => ['local_route', 'route_elevation', 'regional_routing_install'].includes(request.type))), false);
    }
    assert.equal(result.candidate, null, 'Startup restored a route candidate');
    assert.equal(result.generation, null, 'Startup generated a route');
    assert.deepEqual(errors, []);
    return { name: scenario.name, ...(scenario.repeat === undefined ? {} : { repeat: scenario.repeat }), status: 'passed', first_map_build_matches: Boolean(scenario.expected), offline: Boolean(scenario.offline) };
  } catch (error) {
    const diagnostic = await page?.evaluate(async () => {
      const { store } = await (await import('/static/pwa_runtime.js')).pwaRuntime();
      const { createRegionVersionStore } = await import('/static/region_versions.js');
      return { selected: document.querySelector('#planning-region')?.value,
        selector_disabled: document.querySelector('#planning-region')?.disabled,
        refresh_disabled: document.querySelector('#regional-refresh')?.disabled,
        status: document.querySelector('#regional-status')?.dataset.state,
        stored_region: await store.get('public_runtime', 'planner-region-id') ?? null,
        durable: store.durable,
        regions: (await createRegionVersionStore().list()).map(row => ({ id: row.region_id, status: row.status, code: row.code })),
        events: preferenceEvents.slice(-30),
        native_calls: preferenceNative.map(request => request.type),
        error: document.querySelector('#error-details')?.textContent };
    }).catch(cause => ({ diagnostic_error: cause.message }));
    console.error(JSON.stringify({ scenario: scenario.name, repeat: scenario.repeat, phase, diagnostic, errors }));
    throw error;
  } finally { releaseCatalog(); await context.close(); }
}

async function main() {
  const repeats = Number(process.env.REGION_PREFERENCE_RELOAD_REPEATS ?? 10);
  assert.ok(Number.isSafeInteger(repeats) && repeats >= 1 && repeats <= 50);
  const browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'],
    ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}) });
  try {
    // The focused screen harness and the real startup cases share the same
    // intercepted local origin; all regional artifacts are synthetic.
    for (const scenario of [
      { name: 'storage_and_screen_preferences', runHarness: true },
      { name: 'sole_region_restart', regions: ['alpha'], expected: 'alpha' },
      { name: 'multiple_region_restart_requires_choice', regions: ['alpha', 'beta'] },
      { name: 'previous_choice_first_map_before_catalog', regions: ['alpha', 'beta'], preference: 'beta', expected: 'beta' },
      { name: 'real_selection_and_clear_survive_reload', regions: ['alpha', 'beta'], preference: 'alpha', expected: 'alpha', switchAndClear: true },
      { name: 'invalid_id_ignored', regions: ['alpha', 'beta'], preference: '../beta' },
      { name: 'unexpected_value_ignored', regions: ['alpha', 'beta'], preference: { region_id: 'beta' } },
      { name: 'deleted_region_not_restored', regions: ['alpha', 'beta', 'gamma'], deleted: true, preference: 'beta' },
      { name: 'updated_build_same_region_id', regions: ['alpha', 'beta'], update: true, preference: 'beta', expected: 'beta' },
      { name: 'interrupted_update_uses_committed_build', regions: ['alpha', 'beta'], interrupted: true, preference: 'beta', expected: 'beta' },
      { name: 'optional_preference_storage_unavailable', regions: ['alpha'], storageUnavailable: true, expected: 'alpha' },
      { name: 'offline_restart_restores_map_without_download_or_route', regions: ['alpha', 'beta'], preference: 'beta', expected: 'beta', offline: true },
      { name: 'restored_hint_does_not_bypass_native_readiness', regions: ['alpha', 'beta'], preference: 'beta', expected: 'beta', nativeUnavailable: true, failure: 'regional_routing_unavailable' },
      { name: 'restored_hint_does_not_bypass_map_integrity', regions: ['alpha', 'beta'], preference: 'beta', expected: 'beta', corruptMap: true, failure: 'map_pack_invalid' },
    ]) {
      for (let repeat = 0; repeat < (scenario.switchAndClear ? repeats : 1); repeat++) {
        console.log(JSON.stringify(await startup(browser, { ...scenario, ...(scenario.switchAndClear ? { repeat } : {}) })));
      }
    }
  } finally { await browser.close(); }
}
module.exports = { startup };
if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
