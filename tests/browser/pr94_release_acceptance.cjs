// Real Chromium/OPFS coverage. No DEM, private artifact or external service.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { runBundledStartupRegression } = require('./pr94_startup_acceptance.cjs');
const root = path.resolve(__dirname, '../..');
const server = http.createServer((request, response) => {
  let pathname;
  try { pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname); }
  catch { response.writeHead(400).end(); return; }
  const file = path.resolve(root, `.${pathname}`);
  if (!file.startsWith(`${root}${path.sep}`)
      || !['/tests/', '/src/sugarglider/web/static/'].some(prefix => pathname.startsWith(prefix))) {
    response.writeHead(403).end(); return;
  }
  const mime = { '.js': 'text/javascript', '.json': 'application/json', '.html': 'text/html' };
  if (!fs.existsSync(file) || !fs.statSync(file).isFile()) { response.writeHead(404).end(); return; }
  response.writeHead(200, { 'Content-Type': mime[path.extname(file)] || 'application/octet-stream' });
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
    await context.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
    for (const name of ['pr40_local_regional_data', 'pr90_v2_regions', 'pr91_route_elevation',
      'pr94_release', 'pr96_installation_memory']) {
      const page = await context.newPage();
      await page.goto(`${base}/tests/browser/${name}_harness.html`);
      await page.waitForFunction(() => ['passed', 'failed'].includes(document.querySelector('pre')?.dataset.status), { timeout: 30_000 });
      const result = await page.locator('pre').evaluate(node => ({ status: node.dataset.status, text: node.textContent }));
      if (result.status !== 'passed') throw Error(`${name}: ${result.text}`);
      console.log(JSON.stringify({ name, cases: JSON.parse(result.text).length, status: 'passed' }));
      await page.close();
    }
    for (const offlineConfig of [false, true]) {
      const startupCases = await runBundledStartupRegression(browser, root, { offlineConfig });
      console.log(JSON.stringify({ name: 'bundled_startup_import', offlineConfig, cases: startupCases.length, status: 'passed' }));
    }
  } finally {
    await browser?.close();
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
