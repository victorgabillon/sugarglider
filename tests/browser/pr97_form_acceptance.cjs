// Real application inputs and persistence. No route, height or region is forged.
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const origin = 'https://appassets.androidplatform.net';

async function runFormAcceptance(browser, root, width) {
  const language = width === 390 ? "en" : "fr";
  const context = await browser.newContext({ viewport: { width, height: 844 },
    isMobile: width < 500, hasTouch: width < 500 });
  const external = [], errors = [];
  try {
    await context.addInitScript(() => {
      globalThis.formNativeRequests = [];
      globalThis.sugargliderNative = { onmessage: null, postMessage(payload) {
        const request = JSON.parse(payload); formNativeRequests.push(request.type);
        if (request.type === 'set_ui_language') { queueMicrotask(() => this.onmessage?.({data:JSON.stringify({schema_version:1,request_id:request.request_id,type:'set_ui_language_result',language:request.language,selected:true})})); return; }
        if (request.type !== 'hello') throw Error('Input editing must not invoke native routing');
        queueMicrotask(() => this.onmessage?.({ data: JSON.stringify({ schema_version: 1,
          request_id: request.request_id, type: 'hello_result', outing_slug: null,
          participant_id: null, active: false, state: 'stopped', last_published_at: null,
          pending_sample: false, stop_warning: null }) }));
      } };
    });
    await context.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) { external.push(url.origin); return route.abort(); }
      if (url.pathname === '/static/offline_region_catalog.json') return route.fulfill({ json: { schema_version: 1, regions: [] } });
      const relative = url.pathname === '/' ? 'index.html' : url.pathname === '/v1/ui/config'
        ? 'android_ui_config.json' : url.pathname.replace(/^\/static\//u, '');
      const base = path.join(root, 'src/sugarglider/web/static'), file = path.resolve(base, relative);
      if (!file.startsWith(base + path.sep)) return route.abort();
      const mime = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json',
        '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png' };
      try { return route.fulfill({ body: await fs.readFile(file), contentType: mime[path.extname(file)] ?? 'application/octet-stream' }); }
      catch { return route.fulfill({ status: 404, body: '' }); }
    });
    const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
    await page.goto(origin + '/');
    await page.waitForFunction(() => document.querySelector('#trail-profile-dialog').open);
    if (language === 'en') await page.evaluate(async () => { const {setLanguage}=await import('/static/i18n.js'); await setLanguage('en'); });
    const name = page.getByRole('textbox', { name: language === 'fr' ? 'Comment vous appeler ?' : 'What should we call you?' });
    await name.waitFor(); await name.fill('PR97 keyboard QA');
    await name.press('End'); await name.press('Backspace'); await name.press('A');
    assert.equal(await name.inputValue(), 'PR97 keyboard QA');
    await page.getByRole('button', { name: language === 'fr' ? 'Continuer' : 'Continue', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('#trail-profile-dialog').open);
    await page.reload();
    await page.waitForFunction(language => document.querySelector('#regional-status').textContent.includes(language === 'fr' ? 'Téléchargez une région' : 'Download a region'), language);
    assert.equal(await page.locator('html').getAttribute('lang'), language, 'Language survives restart with the local profile');
    assert.equal(await page.locator('#trail-profile-dialog').evaluate(node => node.open), false);
    await page.locator('[data-shell-view="plan"]').click();
    await page.locator('#planning-preferences > summary').click();
    const routeName = page.getByRole('textbox', { name: language === 'fr' ? 'Nom du parcours' : 'Route name', exact: true });
    await routeName.fill('PR97 route input'); await routeName.press('Tab');
    assert.equal(await routeName.inputValue(), 'PR97 route input');
    const distance = page.getByRole('spinbutton', { name: 'Distance (km)', exact: true });
    await distance.fill('20'); await distance.press('ArrowUp'); await distance.press('Tab');
    assert.equal(await distance.inputValue(), '20.1');
    await distance.fill('0');
    assert.equal(await distance.evaluate(node => node.validity.rangeUnderflow), true);
    await distance.fill('20'); await distance.press('Tab');
    await routeName.focus(); assert.equal(await routeName.evaluate(node => document.activeElement === node), true);
    if (width < 500) { await routeName.tap(); assert.equal(await routeName.evaluate(node => document.activeElement === node), true); }
    assert.deepEqual(await page.evaluate(() => formNativeRequests.filter(type => ['local_route', 'route_elevation'].includes(type))), []);
    assert.deepEqual(external, []); assert.deepEqual(errors, []);
    return { width, language, profile_persisted: true, labels_keyboard_touch: true,
      numeric_constraints_preserved: true, no_route_or_height_calls: true };
  } finally { await context.close(); }
}
module.exports = { runFormAcceptance };
