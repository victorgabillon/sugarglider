// Synthetic geometry and real module-worker lifecycle. Never uses regional map data.
const fs = require('node:fs'), path = require('node:path'), http = require('node:http');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../..');
const server = http.createServer((request, response) => {
  let pathname;
  try { pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname); }
  catch { response.writeHead(400).end(); return; }
  const file = path.resolve(root, `.${pathname}`);
  if (!file.startsWith(`${root}${path.sep}`) || !['/tests/', '/src/sugarglider/web/static/'].some(prefix => pathname.startsWith(prefix))) {
    response.writeHead(403).end(); return;
  }
  if (!fs.existsSync(file) || !fs.statSync(file).isFile()) { response.writeHead(404).end(); return; }
  const types = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json' };
  response.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(response);
});
(async () => {
  let browser;
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const base = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({ headless: true,
      ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}) });
    const context = await browser.newContext();
    const forbidden = [];
    await context.route('**/*', route => {
      if (new URL(route.request().url()).origin === base) return route.continue();
      forbidden.push(new URL(route.request().url()).origin); return route.abort();
    });
    const page = await context.newPage();
    await page.goto(`${base}/tests/browser/nature_performance_harness.html`);
    await page.waitForFunction(() => ['passed', 'failed'].includes(document.querySelector('pre')?.dataset.status), { timeout: 30_000 });
    const result = await page.locator('pre').evaluate(node => ({ status: node.dataset.status, text: node.textContent }));
    if (result.status !== 'passed' || forbidden.length) throw Error(JSON.stringify({ result, forbidden }));
    const expected = await page.evaluate(() => window.createNatureIndexRetentionProbe());
    const cdp = await context.newCDPSession(page);
    await cdp.send('HeapProfiler.collectGarbage');
    await cdp.send('HeapProfiler.collectGarbage');
    const retained = await page.evaluate(() => ({ owner: Boolean(window.retainedNatureIndexOwner.deref()),
      nature: Boolean(window.retainedNatureIndexDocument.deref()), names: window.retainedNaturePlaces.searchPlaceNames('castle') }));
    if (retained.owner || retained.nature || JSON.stringify(retained.names) !== JSON.stringify(expected)) throw Error('Retired regional nature index retained');
    const analysis = await page.evaluate(() => window.createNatureSourceReleaseProbe());
    await cdp.send('HeapProfiler.collectGarbage');
    const sourceRelease = await page.evaluate(() => ({ retained: Boolean(window.activeNatureInput.deref()),
      analysis: window.activeNatureAnalysis.analyzeNature(window.activeNatureRoute) }));
    if (sourceRelease.retained || JSON.stringify(sourceRelease.analysis) !== JSON.stringify(analysis)) throw Error('Active analysis retained source geometry or changed after release');
    console.log(JSON.stringify({ source_geometry_released_while_analysis_active: true }));
    console.log(JSON.stringify({ nature_index_released: true, name_search_unchanged: true, name: 'offline_nature_performance', cases: JSON.parse(result.text), status: 'passed' }));
  } finally {
    await browser?.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
