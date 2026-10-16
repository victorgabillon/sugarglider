// Explicit GC regression, separate from ordinary timing and physical PSS tests.
// Requires an existing Playwright/Chromium installation; never downloads tooling.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs/promises');
const http = require('node:http');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(__dirname, '../..');
  const server = http.createServer(async (request, response) => {
    try {
      const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
      const file = path.resolve(root, '.' + pathname);
      if (!file.startsWith(root + path.sep)) throw Error('Invalid path');
      const body = await fs.readFile(file);
      response.setHeader('Content-Type', /\.(?:m?js)$/.test(file) ? 'text/javascript'
        : file.endsWith('.html') ? 'text/html' : 'application/json');
      response.end(body);
    } catch { response.writeHead(404); response.end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true,
      ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}) });
    const page = await browser.newPage();
    const origin = `http://127.0.0.1:${server.address().port}`;
    await page.route('**/*', route => new URL(route.request().url()).origin === origin
      ? route.continue() : route.abort());
    await page.goto(origin + '/tests/browser/pr93_regional_retention_harness.html');
    await page.waitForFunction(() => document.querySelector('pre').dataset.status);
    assert.equal(await page.locator('pre').getAttribute('data-status'), 'passed');
    const before = await page.evaluate(() => window.createRegionalRetentionProbe());
    assert(before.nature_features > 0);
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('HeapProfiler.collectGarbage');
    await cdp.send('HeapProfiler.collectGarbage');
    const after = await page.evaluate(() => ({
      nature_retained: Boolean(window.retainedNature.deref()),
      names: window.retainedPlaces.searchPlaceNames('castle'),
    }));
    assert.equal(after.nature_retained, false, 'Name search must not retain the full Nature context');
    assert.deepEqual(after.names, before.expected);
    await page.goto(origin + '/tests/browser/pr93_map_retention_harness.html');
    await page.waitForFunction(() => ['passed', 'failed'].includes(document.querySelector('pre').dataset.status));
    assert.equal(await page.locator('pre').getAttribute('data-status'), 'passed', await page.locator('pre').textContent());
    console.log(JSON.stringify({ status: 'passed', nature_released: true, name_search_unchanged: true,
      retired_map_archives_released: true, no_unknown_source_network_fallback: true }));
  } finally {
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
