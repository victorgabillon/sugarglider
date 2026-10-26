// Full bundled application, real synthetic OPFS components/workers and normal
// native message framing. ChatGPT, routing and terrain replies are explicitly
// synthetic CI fixtures; no real account, geographic evidence or device install.
const fs = require('node:fs/promises'), path = require('node:path'), assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../..'), origin = 'https://appassets.androidplatform.net';
const profiles = ['trail_run', 'hike', 'city_bike', 'gravel_bike', 'mountain_bike', 'road_bike'];

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'],
    ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}) });
  try {
    for (const [width, height, locale] of [[372, 760, "fr-FR"], [390, 844, "en-GB"], [800, 372, "fr-FR"], [1280, 844, "en-GB"]]) {
      const context = await browser.newContext({ viewport: { width, height }, locale, serviceWorkers: 'block' });
      const errors = [], external = [], unexpected = [];
      try {
        await context.route('**/*', async route => {
          const url = new URL(route.request().url());
          if (url.origin !== origin) { external.push(url.href); return route.abort(); }
          if (url.pathname === '/seed.html') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>Synthetic adventure fixture</title><script src="/static/vendor/pmtiles-4.5.0/pmtiles.js"></script>' });
          if (url.pathname === '/static/offline_region_catalog.json') return route.fulfill({ json: { schema_version: 1, regions: [] } });
          const relative = url.pathname.startsWith('/tests/') || url.pathname.startsWith('/src/') ? url.pathname.slice(1)
            : 'src/sugarglider/web/static/' + (url.pathname === '/' ? 'index.html' : url.pathname === '/v1/ui/config' ? 'android_ui_config.json' : url.pathname.replace(/^\/static\//u, ''));
          const file = path.resolve(root, decodeURIComponent(relative));
          if (!file.startsWith(root + path.sep)) return route.abort();
          const types = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml' };
          try {
            let body = await fs.readFile(file);
            if (relative.endsWith('/pr36_offline_maps_harness.js')) body = Buffer.from(body.toString().replace(
              'attribution: "© OpenStreetMap contributors · Protomaps",',
              'attribution: packId.includes("second") ? "© OpenStreetMap contributors · ODbL · ESA WorldCover · Natural Earth · Protomaps · Synthetic pack B" : "© OpenStreetMap contributors · ODbL · ESA WorldCover (CC BY 4.0) · Natural Earth · Protomaps · Synthetic pack A",'));
            if (url.pathname === '/v1/ui/config') { const config = JSON.parse(body); config.initial_center = [.01, .01]; config.initial_zoom = 14; return route.fulfill({ json: config }); }
            return route.fulfill({ body, contentType: types[path.extname(file)] ?? 'application/octet-stream' });
          } catch { return route.fulfill({ status: 404, body: '' }); }
        });
        const page = await context.newPage(); page.setDefaultTimeout(15000); page.on('pageerror', error => errors.push(error.message));
        await page.goto(origin + '/seed.html');
        const fixture = await page.evaluate(async () => {
          const data = await (await fetch('/tests/fixtures/pr40_regional_data.json')).json();
          const { createRegionVersionStore } = await import('/static/region_versions.js');
          const { seedRegion } = await import('/tests/browser/region_preference_harness.js');
          const { syntheticAdventure } = await import('/tests/browser/adventure_proposal_harness.js');
          const { openPwaStore, PWA_STORES } = await import('/static/pwa_store.js');
          const manifest = await seedRegion(data, createRegionVersionStore(), 'adventure-fixture', 'Synthetic adventure region');
          await seedRegion(data, createRegionVersionStore(), 'second-fixture', 'Synthetic second region');
          const store = await openPwaStore();
          await store.put(PWA_STORES.trailProfile, 'current', { schema_version: 1, display_name: 'Synthetic reviewer', avatar_key: 'forest' });
          await store.put(PWA_STORES.publicRuntime, 'planner-region-id', manifest.region_id); store.close();
          const initial = structuredClone(syntheticAdventure);
          initial.intent = { ...initial.intent, topology: 'point_to_point', start: { name: 'Start', lat: .005, lon: .005 },
            end: { name: 'End', lat: .015, lon: .013 }, target_distance_m: 2200, tolerance_m: 700, order: 'fixed' };
          initial.wishes = [{ metric: 'interesting_stops', goal: 'maximize', value: null, importance: 'high' }];
          initial.places[0].location = { name: 'Fixture 1', lat: .01, lon: .005 };
          initial.places[0].osm_id = null; // Exercise name grounding through the real planning worker, without opening location search first.
          const revised = structuredClone(initial);
          revised.places.push({ ...structuredClone(initial.places[0]), id: 'water', osm_id: 'node/2', category: 'water', location: { name: 'Fixture 2', lat: .01, lon: .007 }, priority: 9 });
          revised.places.push({ ...structuredClone(initial.places[0]), id: 'private', osm_id: 'node/5', category: 'viewpoint', location: { name: 'Fixture 5', lat: .01, lon: .013 }, priority: 8 });
          const flat = (await (await fetch('/tests/fixtures/elevation/contract-v1.json')).json()).find(item => item.name === 'flat').expected;
          return { manifest, initial, revised, flat };
        });
        await context.addInitScript(({ profiles, fixture }) => {
          globalThis.adventureNativeCalls = []; globalThis.adventureSavedGpx = null; globalThis.adventureModelCount = 0; globalThis.failAdventureModel = false;
          let connected = false;
          const account = () => ({ accounts: connected ? [{ id: 'oaiapp_synthetic', label: 'Synthetic account', connected: true, plan_usage: true }] : [],
            selected_account: connected ? 'oaiapp_synthetic' : null, models: connected ? [{ id: 'synthetic-model', label: 'Synthetic available model' }] : [] });
          const distance = (a, b) => { const r = Math.PI / 180, h = Math.sin((b.lat-a.lat)*r/2)**2 + Math.cos(a.lat*r)*Math.cos(b.lat*r)*Math.sin((b.lon-a.lon)*r/2)**2; return 12742017.6*Math.asin(Math.sqrt(h)); };
          globalThis.sugargliderNative = { onmessage: null, postMessage(payload) {
            let request;
            if (payload instanceof ArrayBuffer) {
              const length = new DataView(payload).getUint32(0);
              request = JSON.parse(new TextDecoder().decode(new Uint8Array(payload, 4, length)));
              adventureSavedGpx = new TextDecoder().decode(new Uint8Array(payload, 4 + length));
            } else request = JSON.parse(payload);
            adventureNativeCalls.push(request); let reply;
            if (request.type === 'show_privacy') reply = { type: 'show_privacy_result', shown: true };
            else if (request.type === 'get_app_identity') reply = { type: 'app_identity_result', label: 'SG AI Test', revision: '88bdb8c', variant: 'v2Staging', version: '1.2.0-v2-staging' };
            else if (request.type === 'hello') reply = { type: 'hello_result', outing_slug: null, participant_id: null, active: false, state: 'stopped', last_published_at: null, pending_sample: false, stop_warning: null };
            else if (request.type === 'itinerary_dialog_state') reply = { type: 'itinerary_dialog_state_result', open: request.open };
            else if (request.type === 'get_local_route_capabilities') reply = { type: 'local_route_capabilities_result', enabled: true,
              engine: 'valhalla-mobile', engine_version: 'synthetic', installed_pack_count: 1, installed_pack_ids: [request.regional_reference.pack_id],
              supported_profile_ids: profiles, pack_capabilities: [{ pack_id: request.regional_reference.pack_id, access_modes: ['foot', 'bicycle'] }] };
            else if (request.type.startsWith('chatgpt_')) {
              if (request.type === 'chatgpt_sign_in') connected = true;
              if (request.type === 'chatgpt_sign_out') connected = false;
              if (request.type === 'chatgpt_infer') {
                adventureModelCount++;
                reply = { type: 'chatgpt_result', result: failAdventureModel ? null : {
                  text: JSON.stringify(adventureModelCount === 1 ? fixture.initial : fixture.revised), researched: true,
                  citations: [{ title: 'Synthetic citation', url: 'https://example.invalid/source' }], usage: { input_tokens: 30, output_tokens: 60, total_tokens: 90 }, elapsed_ms: 25 }, error: failAdventureModel ? 'usage_limit' : null };
              } else reply = { type: 'chatgpt_result', result: request.type === 'chatgpt_cancel' ? {} : account(), error: null };
            } else if (request.type.startsWith('adventure_speech_')) reply = { type: 'adventure_speech_result', mode: 'on_device',
              status: request.type.endsWith('_start') ? 'completed' : request.type.endsWith('_cancel') ? 'cancelled' : 'ready',
              text: request.type.endsWith('_start') ? 'Une aventure historique avec des lieux intéressants' : null };
            else if (request.type === 'local_route') {
              const p = request.points;
              const geometry = p.flatMap((point, i) => i ? [[(p[i-1].lon+point.lon)/2+.00001, (p[i-1].lat+point.lat)/2], [point.lon, point.lat]] : [[point.lon, point.lat]]);
              const metres = geometry.slice(1).reduce((sum, point, i) => sum + distance({ lon: geometry[i][0], lat: geometry[i][1] }, { lon: point[0], lat: point[1] }), 0);
              reply = { type: 'local_route_result', engine: 'valhalla-mobile', engine_version: 'synthetic', pack_id: request.regional_reference.pack_id,
                profile: request.profile, geometry, snapped_points: p, distance_m: metres, duration_s: metres / 2,
                measurements: { cold_start: false, engine_initialization_ms: 0, route_ms: 1, memory_before_initialization_bytes: 0, memory_after_initialization_bytes: 0, memory_after_route_bytes: 0 } };
            } else if (request.type === 'route_elevation') {
              const analysis = structuredClone(fixture.flat);
              Object.assign(analysis, { source_sha256: request.regional_reference.elevation.manifest.sha256, geometry_sha256: request.geometry_sha256,
                routing_profile: request.profile, route_distance_m: request.distance_m, height_reference: 'unresolved vertical datum; verified V2 elevation component manifest',
                available_sample_count: request.samples.length, analyzed_distance_m: request.distance_m,
                segments: [{ first_index: 0, last_index: request.samples.length - 1, distance_m: request.distance_m }],
                samples: request.samples.map((s, i) => ({ index: i, distance_m: s[0], height_m: 0, filtered_height_m: 0, segment_index: 0 })) });
              reply = { type: 'local_elevation_result', elevation_version: 1, operation_id: request.operation_id, candidate_id: request.candidate_id,
                regional_reference: request.regional_reference, sampling_interval_m: request.sampling_interval_m, sample_coordinates: request.samples.map(s => [s[2], s[1]]), analysis,
                measurements: { native_height_ms: 1, analysis_ms: 1, total_ms: 2, pss_bytes: 0, cold_start: false } };
            } else if (request.type === 'cancel_route_elevation') reply = { type: 'local_elevation_cancel_result', operation_id: request.operation_id, accepted: true };
            else if (request.type === 'save_gpx') reply = { type: 'save_gpx_result', status: 'saved' };
            else { globalThis.unexpectedAdventureNative = request.type; throw Error('Unexpected native operation: ' + request.type); }
            queueMicrotask(() => this.onmessage?.({ data: JSON.stringify({ schema_version: 1, request_id: request.request_id, ...reply }) }));
          } };
        }, { profiles, fixture });
        await page.goto(origin + '/');
        await page.evaluate(async () => { globalThis.adventureAppState = await import('/static/state.js'); });
        await page.waitForFunction(() => document.querySelector('#regional-status').dataset.state === 'regional_ready');
        const startupCalls = await page.evaluate(() => adventureNativeCalls.map(call => call.type));
        assert(!startupCalls.some(type => ['local_route', 'route_elevation', 'chatgpt_infer', 'adventure_speech_start'].includes(type)), 'Startup must not route, infer or listen');
        const screenshot = async name => {
          if (!process.env.MOBILE_EVIDENCE_DIR) return;
          await fs.mkdir(process.env.MOBILE_EVIDENCE_DIR, { recursive: true });
          await page.screenshot({ path: path.join(process.env.MOBILE_EVIDENCE_DIR, `${name}-${width}-${locale}.png`) });
        };
        let mapTapIndex = 0;
        const tapMap = async () => {
          const point = await page.locator('.maplibregl-canvas').evaluate((canvas, index) => {
            const bounds = canvas.getBoundingClientRect();
            const fractions = [.2, .8, .4, .6];
            const rotated = [...fractions.slice(index % 4), ...fractions.slice(0, index % 4)];
            for (const fx of rotated) for (const fy of [.25, .5, .75, .1]) {
              const x = bounds.width * fx, y = bounds.height * fy;
              if (document.elementFromPoint(bounds.left + x, bounds.top + y) === canvas) return { x, y };
            }
            return null;
          }, mapTapIndex++);
          assert(point, 'There is an unobstructed map target, including in landscape');
          await page.locator('.maplibregl-canvas').click({ position: point });
        };
        const unchanged = () => page.evaluate(() => JSON.stringify({ request: adventureAppState.state.request,
          result: adventureAppState.state.generationResult, source: adventureAppState.state.generationSourceRequest,
          selected: adventureAppState.state.selectedSignature, points: adventureAppState.currentAdventureContext() }));
        const checkLayout = async () => {
          await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
          const layout = await page.evaluate(() => {
            const rect = selector => document.querySelector(selector).getBoundingClientRect().toJSON();
            return { overflow: document.documentElement.scrollWidth > innerWidth, header: rect('.topbar'),
              ai: rect('#ask-chatgpt'), tools: rect('.header-tools > summary'),
              dock: rect('#route-dock'), credits: rect('.maplibregl-ctrl-attrib'), nav: rect('.workspace-navigation') };
          });
          assert(!layout.overflow, JSON.stringify(layout));
          assert(layout.ai.height >= 44 && layout.ai.right <= width && layout.ai.right <= layout.tools.left + 1, JSON.stringify(layout));
          assert(layout.dock.bottom <= layout.credits.top + 1 && layout.credits.bottom <= layout.nav.top + 1, JSON.stringify(layout));
          return layout;
        };
        assert(await page.locator('#ask-chatgpt').isVisible(), 'Ask ChatGPT is visible on startup without opening Plan');
        await page.waitForFunction(() => document.querySelector('.maplibregl-ctrl-attrib-inner').textContent.includes('Synthetic pack A'));
        const creditText = await page.locator('.maplibregl-ctrl-attrib-inner').textContent();
        for (const name of ['OpenStreetMap', 'ODbL', 'ESA WorldCover', 'Natural Earth', 'Protomaps', 'Synthetic pack A']) assert(creditText.includes(name), JSON.stringify({ name, creditText, width }));
        const osm = page.locator('.maplibregl-ctrl-attrib a[href="https://www.openstreetmap.org/copyright"]');
        assert(await osm.isVisible(), 'OSM licence link is available with the full active-pack credits');
        // Verify activation through a local interception, without requesting the provider.
        const links = [];
        await context.route('https://www.openstreetmap.org/copyright', route => { links.push(route.request().url()); return route.fulfill({ body: 'Synthetic attribution link target', contentType: 'text/html' }); });
        await screenshot('map-initial');
        if (width <= 640) {
          await page.waitForFunction(() => !document.querySelector('.maplibregl-ctrl-attrib').classList.contains('maplibregl-compact-show'));
          await checkLayout(); await screenshot('map-settled');
          const creditsButton = page.locator('.maplibregl-ctrl-attrib summary');
          await creditsButton.focus(); await page.keyboard.press('Enter');
          assert(await osm.isVisible(), 'Keyboard expands full licence credits');
          await page.waitForTimeout(5200);
          assert(await osm.isVisible(), 'Explicit keyboard expansion remains open');
          await checkLayout(); await screenshot('map-expanded');
        }
        const popup = page.waitForEvent('popup'); await osm.click(); const linked = await popup;
        await linked.waitForLoadState(); await linked.close(); assert.equal(links.length, 1);
        if (width <= 640) { await page.locator('.maplibregl-ctrl-attrib summary').click(); }
        const tools = page.locator('.header-tools');
        await tools.evaluate(node => { node.open = true; });
        await page.locator('#native-privacy').click();
        assert.equal(await page.evaluate(() => adventureNativeCalls.filter(call => call.type === 'show_privacy').length), 1);
        await tools.evaluate(node => { node.open = true; });
        await page.locator('.app-status-details > summary').click();
        await page.waitForFunction(() => document.querySelector('#app-build-identity').textContent.includes('SG AI Test · 88bdb8c · V2 Staging'));
        await tools.evaluate(node => { node.open = false; });
        // Switch actual verified OPFS regions, rather than replacing credit DOM.
        await page.locator('#planning-region').evaluate(node => {
          for (let parent = node.parentElement; parent; parent = parent.parentElement) if (parent.tagName === 'DETAILS') parent.open = true;
        });
        await page.locator('#planning-region').selectOption('second-fixture');
        await page.waitForFunction(() => document.querySelector('.maplibregl-ctrl-attrib-inner').textContent.includes('Synthetic pack B'));
        assert(!await page.locator('.maplibregl-ctrl-attrib-inner').textContent().then(text => text.includes('Synthetic pack A')), 'Previous pack credits do not remain associated with the new map');
        await tools.evaluate(node => { node.open = false; });
        assert(await osm.isVisible(), 'A new region reveals its complete credits again');
        await screenshot('map-pack-switch');
        await page.locator('#planning-region').evaluate(node => {
          for (let parent = node.parentElement; parent; parent = parent.parentElement) if (parent.tagName === 'DETAILS') parent.open = true;
        });
        await page.locator('#planning-region').selectOption('adventure-fixture');
        await page.waitForFunction(() => document.querySelector('.maplibregl-ctrl-attrib-inner').textContent.includes('Synthetic pack A'));
        await tools.evaluate(node => { node.open = false; });
        await page.evaluate(async () => { const { createRegionVersionStore } = await import('/static/region_versions.js'); await createRegionVersionStore().removeRegion('second-fixture'); });
        const original = await unchanged(), count = await page.evaluate(() => adventureNativeCalls.length);
        await page.locator('#ask-chatgpt').click();
        await page.waitForFunction(() => document.querySelector('#adventure-dialog').open && document.querySelector('#adventure-dialog').getAttribute('aria-busy') === 'false');
        await screenshot('dialog-disconnected');
        await page.locator('#adventure-text').fill('My editable adventure');
        await page.locator('#adventure-close').click();
        assert.equal(await unchanged(), original, 'Opening and cancelling from Map preserves the complete editable plan');
        assert(await page.locator('#ask-chatgpt').evaluate(node => node === document.activeElement), 'Cancel returns focus to the Map launcher');
        assert(!await page.evaluate(count => adventureNativeCalls.slice(count).some(call => ['chatgpt_infer', 'local_route', 'adventure_speech_start'].includes(call.type)), count));
        if (width === 372) {
          await page.evaluate(() => { document.documentElement.style.fontSize = '32px'; });
          await page.waitForFunction(() => !document.querySelector('.maplibregl-ctrl-attrib').classList.contains('maplibregl-compact-show'));
          await checkLayout(); await screenshot('map-large-text');
          await page.locator('.maplibregl-ctrl-attrib summary').click();
          await checkLayout();
          await page.keyboard.press('Tab');
          assert(await osm.evaluate(node => node === document.activeElement), 'Large-text credits retain keyboard access to the ODbL link');
          await screenshot('map-large-text-expanded');
          await page.locator('.maplibregl-ctrl-attrib summary').click();
          await page.locator('#ask-chatgpt').click();
          await screenshot('dialog-large-text');
          const overflow = await page.locator('#adventure-dialog').evaluate(node => node.scrollWidth > node.clientWidth + 1);
          assert(!overflow, 'Dialog has no horizontal overflow at 200% text size');
          assert(await page.locator('.adventure-body').evaluate(node => node.clientHeight >= 100), 'Large-text header leaves a usable scrolling editor');
          await page.locator('#adventure-text').scrollIntoViewIfNeeded();
          await screenshot('dialog-large-text-editor');
          await page.locator('#adventure-close').click();
          await page.evaluate(() => { document.documentElement.style.fontSize = ''; });
        }
        const initialContext = await page.evaluate(() => adventureAppState.currentAdventureContext());
        assert.equal(initialContext.start,null);assert.equal(initialContext.end,null);
        const initialPlanView = page.locator('[data-shell-view="plan"]');if(await initialPlanView.isVisible())await initialPlanView.click();
        await page.locator('#plan-with-ai').click();

        await page.locator('#adventure-connect').click();
        await page.waitForFunction(()=>document.querySelector('#adventure-model').value==='synthetic-model');
        await page.locator('#adventure-text').fill('Describe the endpoints, or choose them while planning');
        await page.waitForFunction(()=>!document.querySelector('#adventure-generate').disabled);
        assert((await page.locator('#adventure-start').textContent()).includes('from your description'),'Blank editor supports AI without serializing missing manual endpoints');
        await page.locator('#adventure-endpoints').evaluate(node => { node.open = true; });
        await page.locator('#adventure-choose-start').click();
        await page.waitForFunction(()=>adventureAppState.state.endpointSetMode==='start');
        await page.locator('#cancel-point-placement').click();
        await page.evaluate(()=>document.querySelector('#set-hard-start').click());
        await tapMap();
        assert(!await page.locator('#adventure-dialog').evaluate(node=>node.open),'Cancelled AI map placement cannot reopen during a later ordinary edit');
        await page.evaluate(()=>document.querySelector('#plan-with-ai').click());
        await page.waitForFunction(()=>document.querySelector('#adventure-dialog').open&&!document.querySelector('#adventure-choose-start').disabled);
        await page.locator('#adventure-endpoints').evaluate(node => { node.open = true; });
        await page.locator('#adventure-choose-start').click();
        await page.waitForFunction(()=>adventureAppState.state.endpointSetMode==='start');
        await tapMap();
        await page.waitForFunction(()=>document.querySelector('#adventure-dialog').open&&document.querySelector('#adventure-start').textContent.includes('Start:'));
        assert.equal(await page.locator('#adventure-text').inputValue(),'Describe the endpoints, or choose them while planning','Map selection resumes the same description');
        assert(await page.evaluate(()=>adventureAppState.currentAdventureContext().start!==null),'The ordinary map handler supplies the selected Start');
        assert.equal(await page.evaluate(()=>adventureModelCount),0,'Map selection does not infer automatically');
        await page.locator('#adventure-close').click();
        const request = { schema_version: 1, kind: 'waypoint_route', name: 'Synthetic manual route', topology: 'point_to_point',
          start: fixture.initial.intent.start, end: fixture.initial.intent.end, routing_profile: 'trail_run', candidate_count: 3, seed: 0,
          endpoint_snap_policy: { start: 'near', end: 'near' }, distance_objective: { target_m: 2200, tolerance_m: 700, maximum_m: null, priority: 'balanced' },
          preferences: { nature: 'off', path_selection: 'shortest', loop_geometry: 'off' }, waypoint_order: 'fixed', waypoints: [] };
        await page.evaluate(request => {
          const transfer = new DataTransfer(); transfer.items.add(new File([JSON.stringify(request)], 'synthetic-manual.json', { type: 'application/json' }));
          const input = document.querySelector('#request-file'); input.files = transfer.files; input.dispatchEvent(new Event('change', { bubbles: true }));
        }, request);
        await page.waitForFunction(() => !document.querySelector('#generate').disabled);
        const view = async name => { const button = page.locator(`[data-shell-view="${name}"]`); if (await button.isVisible()) await button.click(); };
        await view('plan'); await page.locator('#generate').click();
        await page.waitForFunction(() => adventureAppState.state.request.status === 'success');
        const manual = await page.evaluate(async () => { const { state, currentPlanRequest } = await import('/static/state.js'); return JSON.stringify({ request: currentPlanRequest(), result: state.generationResult, source: state.generationSourceRequest, selected: state.selectedSignature }); });
        assert(JSON.parse(manual).result.candidates.length && JSON.parse(manual).selected, 'The prior manual route must actually be generated and selected');
        await view('plan'); await page.locator('#plan-with-ai').click();
        await page.locator('#adventure-account-settings').evaluate(node => { node.open = true; });
        await page.locator('#adventure-connect').click();
        await page.waitForFunction(() => document.querySelector('#adventure-model').value === 'synthetic-model');
        await page.locator('#adventure-account-settings').evaluate(node => { node.open = false; });
        await screenshot('dialog-connected');
        const beforeSpeech = await page.locator('#adventure-text').inputValue();
        await page.locator('#adventure-speech-settings').evaluate(node => { node.open = true; });
        await page.locator('#adventure-language').selectOption('fr-FR');
        await page.locator('#adventure-microphone').click();
        await page.waitForFunction(before => document.querySelector('#adventure-text').value === before + '\nUne aventure historique avec des lieux intéressants', beforeSpeech);
        assert.equal(await page.evaluate(() => adventureNativeCalls.findLast(call => call.type === 'adventure_speech_start').mode), 'on_device');
        assert.equal(await page.evaluate(() => adventureNativeCalls.findLast(call => call.type === 'adventure_speech_start').language), 'fr-FR');
        assert.equal(await page.evaluate(() => adventureModelCount), 0, 'Speech alone must not infer');
        await page.locator('#adventure-text').fill('A synthetic 2.2 km historical route with interesting places');
        await page.locator('#adventure-generate').click();
        await page.waitForFunction(() => !document.querySelector('#adventure-dialog').open
          || document.querySelector('#adventure-dialog').getAttribute('aria-busy') === 'false' && document.querySelector('#adventure-error').textContent, null, { timeout: 30000 });
        const adventure = await page.evaluate(async () => { const { state } = await import('/static/state.js'); return { active: state.adventureDisplay,
          improved: state.adventureResult?.refinement_improved, grounding: state.adventureResult?.chosen.grounding, result: state.generationResult, source: state.generationSourceRequest,
          error: document.querySelector('#adventure-error').textContent }; });
        assert(adventure.active && adventure.improved, JSON.stringify(adventure));
        const modelContext=await page.evaluate(()=>JSON.parse(adventureNativeCalls.find(call=>call.type==='chatgpt_infer').input).planning_context);
        assert(modelContext.local_places.length>0&&modelContext.local_places.length<=24);
        assert(modelContext.local_places.some(place=>place.osm_id==='node/1'&&place.location.name==='Fixture 1'),'Actual installed OPFS landmarks are supplied to research through the normal Generate action');
        assert(!JSON.stringify(modelContext.local_places).includes('approach_candidates'),'Research never receives raw mapped approaches');

        assert(adventure.grounding.places.some(place => place.match_method === 'exact_local_name'),'Real worker grounds name-only suggestions without a prior location-picker session');
        assert(adventure.result.candidates.some(c => c.reached_stops.length === 2));
        await view('routes'); await page.locator('.candidate-select').last().click();
        await page.waitForFunction(() => document.querySelector('#adventure-storage-status').textContent.startsWith('Saved on this device'));
        const exactAdventure = await page.evaluate(() => JSON.stringify(adventureAppState.state.adventureResult));
        await page.locator('#adventure-stories-open').click();
        assert(await page.locator('#adventure-stories').isVisible());
        await page.locator('#download-gpx').click(); await page.waitForFunction(() => adventureSavedGpx !== null);
        const selected = await page.evaluate(async () => { const { selectedCandidate } = await import('/static/state.js'); const c = selectedCandidate();
          const doc = new DOMParser().parseFromString(adventureSavedGpx, 'application/xml'); return { id: c.id, track: [...doc.getElementsByTagName('trkpt')].map(p => [Number(p.getAttribute('lon')), Number(p.getAttribute('lat'))]), geometry: c.route.geometry, ways: doc.getElementsByTagName('wpt').length, reached: c.reached_stops.length, tracks: doc.getElementsByTagName('trk').length, segments: doc.getElementsByTagName('trkseg').length, extensions: doc.getElementsByTagName('extensions').length }; });
        const exactGpx = await page.evaluate(() => adventureSavedGpx);
        assert.equal(selected.tracks, 1); assert.equal(selected.segments, 1); assert.equal(selected.extensions, 0); assert.equal(selected.ways, selected.reached);
        assert.equal(selected.track.length, selected.geometry.length);
        selected.track.forEach((p, i) => p.forEach((value, j) => assert(Math.abs(value - selected.geometry[i][j]) < 1e-8)));
        await page.locator('#export-plan').evaluate(node => { for (let parent = node.parentElement; parent; parent = parent.parentElement) if (parent.tagName === 'DETAILS') parent.open = true; });
        const exportedRequest = page.waitForEvent('download'); await page.locator('#export-plan').click();
        const downloaded = await exportedRequest;
        assert.deepEqual(JSON.parse(await fs.readFile(await downloaded.path(), 'utf8')), adventure.source, 'Plan export follows the displayed adventure source');
        await page.locator('.header-tools').evaluate(node => { node.open = false; });
        await view('plan'); await page.locator('#plan-with-ai').click();
        await page.evaluate(() => { failAdventureModel = true; });
        await page.waitForFunction(() => !document.querySelector('#adventure-generate').disabled);
        await page.locator('#adventure-generate').click(); await page.waitForFunction(() => document.querySelector('#adventure-error').textContent.match(/usage limit|limite d’utilisation/u));
        assert.equal(await page.evaluate(async () => (await import('/static/state.js')).selectedCandidate().id), selected.id, 'Failed AI request must keep selected route');
        await page.locator('#adventure-close').click(); await view('routes'); await page.locator('#adventure-return-manual').click();
        const restored = await page.evaluate(async () => { const { state, currentPlanRequest } = await import('/static/state.js'); return JSON.stringify({ request: currentPlanRequest(), result: state.generationResult, source: state.generationSourceRequest, selected: state.selectedSignature }); });
        assert.equal(restored, manual, 'Returning to manual restores exact request/result/selection');
        await page.reload();
        await page.evaluate(async () => { globalThis.adventureAppState = await import('/static/state.js'); });
        await page.waitForFunction(() => !document.querySelector('#restore-adventure').hidden);
        assert.equal(await page.evaluate(() => adventureAppState.state.adventureDisplay), false, 'Startup preserves the editable planner until explicit Reopen');
        const forbiddenStartup = await page.evaluate(() => adventureNativeCalls.filter(c => ['chatgpt_infer','local_route','route_elevation','adventure_speech_start'].includes(c.type)));
        assert.deepEqual(forbiddenStartup, [], 'Restart does not infer, route, measure terrain or listen');
        await view('plan');
        await page.evaluate(() => {
          globalThis.actualAdventureWorker = globalThis.Worker;
          globalThis.Worker = function(...args) {
            const worker = new actualAdventureWorker(...args);
            if (String(args[0]).endsWith('/adventure_snapshot_worker.js')) Object.defineProperty(worker, 'onmessage', {
              set(handler) { worker.addEventListener('message', event => { globalThis.releaseAdventureRecovery = () => handler(event); }); }
            });
            return worker;
          };
        });
        await page.locator('#restore-adventure').click();
        await page.waitForFunction(() => typeof releaseAdventureRecovery === 'function');
        await page.locator('#target-distance').fill('21');
        await page.evaluate(() => { globalThis.Worker = actualAdventureWorker; releaseAdventureRecovery(); });
        await page.waitForFunction(() => document.querySelector('#adventure-recovery-status').textContent.includes('Your plan changed'));
        assert.equal(await page.evaluate(() => adventureAppState.state.adventureDisplay), false, 'A stale recovery cannot replace newly edited intent');
        assert.equal(await page.locator('#target-distance').inputValue(), '21', 'Recovery preserves the intervening edit');
        await view('plan'); await page.locator('#restore-adventure').click();
        await page.waitForFunction(() => adventureAppState.state.adventureDisplay).catch(async error => { throw Error(error.message + ' Recovery diagnostics: ' + JSON.stringify(await page.evaluate(() => ({ status: document.querySelector('#adventure-recovery-status').textContent, request: adventureAppState.state.request, region: document.querySelector('#planning-region').value }))) + ' Page errors: ' + JSON.stringify(errors)); });
        assert.equal(await page.evaluate(() => JSON.stringify(adventureAppState.state.adventureResult)), exactAdventure, 'Full exact AI output/stories/measurements recovered');
        assert.equal(await page.evaluate(() => adventureAppState.state.selectedSignature), selected.id, 'Last selected candidate recovered');
        await view('routes'); await page.locator('#download-gpx').click(); await page.waitForFunction(() => adventureSavedGpx !== null);
        assert.equal(await page.evaluate(() => adventureSavedGpx), exactGpx, 'Restart GPX exactly matches the previous native selected line');
        assert.deepEqual(await page.evaluate(() => adventureNativeCalls.filter(c => ['chatgpt_infer','local_route','route_elevation','adventure_speech_start'].includes(c.type))), [], 'Reopen/selection/export never reroutes or refetches terrain');
        await page.evaluate(async id => { const { createRegionVersionStore } = await import('/static/region_versions.js'); await createRegionVersionStore().removeRegion(id); }, fixture.manifest.region_id);
        await page.reload();
        await page.evaluate(async () => { globalThis.adventureAppState = await import('/static/state.js'); });
        await page.waitForFunction(() => !document.querySelector('#restore-adventure').hidden);
        await view('plan'); await page.locator('#restore-adventure').click();
        await page.waitForFunction(() => adventureAppState.state.adventureDisplay).catch(async error => { throw Error(error.message + ' Recovery diagnostics: ' + JSON.stringify(await page.evaluate(() => ({ status: document.querySelector('#adventure-recovery-status').textContent, request: adventureAppState.state.request, region: document.querySelector('#planning-region').value }))) + ' Page errors: ' + JSON.stringify(errors)); });
        assert.equal(await page.evaluate(() => adventureAppState.state.selectedSignature), selected.id, 'Missing source region does not destroy the immutable saved view');
        assert.equal(await page.locator('#planning-region').inputValue(), '', 'Recovery never silently selects a missing region');
        assert.notEqual(await page.locator('#regional-status').getAttribute('data-state'), 'regional_ready', 'Stored route never makes missing regional data ready');
        assert.deepEqual(await page.evaluate(() => adventureNativeCalls.filter(c => ['chatgpt_infer','local_route','route_elevation','adventure_speech_start'].includes(c.type))), [], 'Missing-region recovery has no native fallback');
        await view('routes'); await page.locator('.candidate-select').first().click();
        await page.evaluate(async () => { await (await import('/static/pwa_runtime.js')).clearSavedOfflineData(); });
        assert.equal(await page.evaluate(async () => { const { store } = await (await import('/static/pwa_runtime.js')).pwaRuntime(); return (await store.get('public_runtime','latest-adventure')) ?? null; }), null, 'Application clear drains queued adventure writes before clearing the store');
        assert.equal(await page.evaluate(() => adventureAppState.state.adventureDisplay), true, 'Clearing durable data preserves the displayed valid result');
        await view('routes'); await page.locator('#forget-adventure').click();
        await page.waitForFunction(() => document.querySelector('#adventure-storage-status').textContent.startsWith('Saved adventure forgotten'));
        await page.locator('.candidate-select').first().click();
        assert.equal(await page.evaluate(async () => { const { store } = await (await import('/static/pwa_runtime.js')).pwaRuntime(); return (await store.get('public_runtime','latest-adventure')) ?? null; }), null, 'Selecting after Forget must not resurrect the saved adventure');
        await view('map');
        await page.locator('#ask-chatgpt').click();
        await page.waitForFunction(() => !document.querySelector('#adventure-region-status').hidden);
        assert(await page.locator('#adventure-generate').isDisabled(), 'An unavailable region explains readiness and prevents Generate');
        assert.equal(await page.evaluate(() => adventureNativeCalls.filter(call => ['chatgpt_infer', 'local_route', 'adventure_speech_start'].includes(call.type)).length), 0);
        await screenshot('dialog-region-unavailable');
        await page.locator('#adventure-close').click();
        assert.deepEqual(errors, []); assert.deepEqual(external, []);
        console.log(JSON.stringify({ name: 'adventure_bundled_app', width, height, locale, status: 'passed', cases: ['startup_map_ai_cta_shared_lifecycle_privacy_build_identity','initial_settled_keyboard_credits_and_active_region_switch','french_portrait_landscape_large_text','region_unavailable_visible_without_automatic_request','bounded_local_landmark_context_before_research','name_grounding_without_prior_location_picker','optional_endpoints_and_cancelled_map_roundtrip','no_automatic_inference_route_or_microphone', 'manual_route_preserved', 'account_voice_text_native_pipeline', 'measured_revision_and_real_regional_workers', 'ordinary_selection_and_binary_gpx', 'failed_ai_request_keeps_selection', 'exact_return_to_manual', 'restart_exact_result_selection_and_gpx', 'explicit_recovery_without_model_routing_or_terrain', 'missing_source_region_stays_unavailable', 'forget_prevents_selection_resurrection', 'application_clear_drains_adventure_writes', 'stale_recovery_cannot_replace_new_user_edit'] }));
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
