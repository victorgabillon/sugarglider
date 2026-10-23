// Real Chromium keyboard, offline and layout acceptance; no regional data or device.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../..');
const evidence = process.env.ATTRIBUTION_EVIDENCE_DIR;
const types = {'.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json'};
const server = http.createServer((request, response) => {
  let pathname;
  try { pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname); }
  catch { response.writeHead(400).end(); return; }
  const file = path.resolve(root, `.${pathname}`);
  if (!file.startsWith(root + path.sep) || !['/tests/', '/src/sugarglider/web/static/'].some(prefix => pathname.startsWith(prefix))) {
    response.writeHead(403).end(); return;
  }
  if (!fs.existsSync(file) || !fs.statSync(file).isFile()) { response.writeHead(404).end(); return; }
  response.writeHead(200, {'Content-Type':types[path.extname(file)] || 'application/octet-stream'});
  fs.createReadStream(file).pipe(response);
});
(async () => {
  let browser;
  const reports = [];
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const base = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({headless:true,
      ...(process.env.CHROMIUM_EXECUTABLE ? {executablePath:process.env.CHROMIUM_EXECUTABLE} : {})});
    for (const width of [320, 360, 390, 420, 1280]) {
      const context = await browser.newContext({viewport:{width,height:844}, isMobile:width < 500, hasTouch:width < 500, serviceWorkers:'block'});
      const page = await context.newPage(), requests = [], external = [], errors = [];
      page.on('request', request => requests.push(request.url()));
      page.on('pageerror', error => errors.push(error.message));
      await context.route('**/*', route => {
        if (new URL(route.request().url()).origin === base) return route.continue();
        external.push(route.request().url()); return route.abort();
      });
      await page.goto(`${base}/tests/browser/ign_attribution_harness.html`);
      await page.waitForFunction(() => ['passed','failed'].includes(document.querySelector('#result')?.dataset.status));
      const result = await page.locator('#result').evaluate(node => ({status:node.dataset.status, text:node.textContent}));
      assert.equal(result.status, 'passed', result.text);
      await context.setOffline(true);
      const before = requests.length;
      const sources = page.locator('.region-sources').filter({hasText:'NGF-IGN69'});
      const summary = sources.locator(':scope > summary');
      if (evidence) {
        fs.mkdirSync(evidence, {recursive:true});
        await page.screenshot({path:path.join(evidence, `sources-collapsed-${width}.png`), fullPage:true});
      }
      await summary.focus(); await page.keyboard.press('Enter');
      assert.equal(await sources.evaluate(node => node.open), true, 'Enter opens source facts offline');
      const editions = sources.locator('[data-source-disclosure=editions]');
      await editions.locator('summary').focus(); await page.keyboard.press('Space');
      assert.equal(await editions.evaluate(node => node.open), true, 'Space opens source editions');
      assert.equal(await editions.locator('li').count(), 17);
      const layout = await sources.evaluate(node => ({overflow:document.documentElement.scrollWidth > innerWidth,
        clipped:node.scrollWidth > node.clientWidth, filenames:[...node.querySelectorAll('.terrain-editions code')].every(code => code.getBoundingClientRect().right <= innerWidth),
        focusVisible:getComputedStyle(document.activeElement).outlineStyle !== 'none'}));
      assert(!layout.overflow && !layout.clipped && layout.filenames && layout.focusVisible, JSON.stringify(layout));
      const firstLink = sources.locator('a').first(); await firstLink.focus();
      assert.equal(await firstLink.getAttribute('target'), '_blank');
      assert.equal(await firstLink.getAttribute('rel'), 'noopener noreferrer');
      await sources.locator('.terrain-editions li').last().scrollIntoViewIfNeeded();
      assert.equal(requests.length, before, 'disclosure, keyboard and scrolling never request data');
      assert.deepEqual(external, []); assert.deepEqual(errors, []);
      if (evidence) {
        fs.mkdirSync(evidence, {recursive:true});
        await summary.scrollIntoViewIfNeeded();
        await page.screenshot({path:path.join(evidence, `sources-${width}.png`), fullPage:true});
      }
      reports.push({width,status:'passed',harness_cases:JSON.parse(result.text),layout,offline_requests:requests.length-before,page_errors:errors});
      await context.close();
    }
    if (evidence) fs.writeFileSync(path.join(evidence, 'acceptance.json'), JSON.stringify(reports,null,2) + '\n');
    console.log(JSON.stringify(reports));
  } finally {
    await browser?.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
