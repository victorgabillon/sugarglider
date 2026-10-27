// Synthetic component/failure tests only; real offline execution needs phone evidence.
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
  const types = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml' };
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
    const forbidden = [];
    for (const name of ['pr91_route_elevation', 'localization', 'adventure_pin_context', 'adventure_ui']) {
    const context = await browser.newContext();
    await context.route('**/*', route => {
      if (new URL(route.request().url()).origin === base) return route.continue();
      forbidden.push(new URL(route.request().url()).origin); return route.abort();
    });
      const page = await context.newPage();
      await page.goto(`${base}/tests/browser/${name}_harness.html`);
      await page.waitForFunction(() => ['passed', 'failed'].includes(document.querySelector('pre')?.dataset.status), { timeout: 60_000 });
      const result = await page.locator('pre').evaluate(node => ({ status: node.dataset.status, text: node.textContent }));
      if (result.status !== 'passed' || forbidden.length) throw Error(JSON.stringify({ result, forbidden }));
      console.log(JSON.stringify({ name, cases: JSON.parse(result.text), status: 'passed' }));
      await context.close();
    }
  } finally {
    await browser?.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
