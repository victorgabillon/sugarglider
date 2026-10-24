// Keyboard, offline and narrow-screen checks on production notice rendering.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../..');
const types = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json'};
const server = http.createServer((request,response) => {
  let file;
  try { file = path.resolve(root, '.' + decodeURIComponent(new URL(request.url, 'http://localhost').pathname)); }
  catch { response.writeHead(400).end(); return; }
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { response.writeHead(404).end(); return; }
  response.writeHead(200, {'Content-Type':types[path.extname(file)] || 'application/octet-stream'});
  fs.createReadStream(file).pipe(response);
});
(async () => {
  let browser; const reports=[];
  try {
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    const base=`http://127.0.0.1:${server.address().port}`;
    browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
    for (const width of [320,360,390,420,1280]) {
      const context=await browser.newContext({viewport:{width,height:844},serviceWorkers:'block'});
      const page=await context.newPage(), requests=[], errors=[], external=[];
      page.on('request',request=>requests.push(request.url())); page.on('pageerror',error=>errors.push(error.message));
      await context.route('**/*',route=>{ if(new URL(route.request().url()).origin===base)return route.continue(); external.push(route.request().url());return route.abort(); });
      await page.goto(`${base}/tests/browser/data_notices_harness.html`);
      await page.waitForFunction(()=>['passed','failed'].includes(document.querySelector('#result')?.dataset.status));
      const result=await page.locator('#result').evaluate(node=>({status:node.dataset.status,text:node.textContent}));
      assert.equal(result.status,'passed',result.text);
      await context.setOffline(true); const before=requests.length;
      const entry=page.locator('[data-source-information]').first(); await entry.focus(); await page.keyboard.press('Enter');
      const dialog=page.locator('#data-licences-dialog'); assert(await dialog.evaluate(node=>node.open));
      if(process.env.NOTICE_EVIDENCE_DIR){fs.mkdirSync(process.env.NOTICE_EVIDENCE_DIR,{recursive:true}); await page.screenshot({path:path.join(process.env.NOTICE_EVIDENCE_DIR,`dialog-${width}.png`)});}
      const full=dialog.locator('details').first(); await full.locator('summary').focus(); await page.keyboard.press('Space'); assert(await full.evaluate(node=>node.open));
      const layout=await dialog.evaluate(node=>({pageOverflow:document.documentElement.scrollWidth>innerWidth,dialogOverflow:node.scrollWidth>node.clientWidth,scrolls:node.scrollHeight>node.clientHeight,withinViewport:node.getBoundingClientRect().left>=0&&node.getBoundingClientRect().right<=innerWidth}));
      assert(!layout.pageOverflow&&!layout.dialogOverflow&&layout.scrolls&&layout.withinViewport,JSON.stringify(layout));
      await dialog.locator('details').last().scrollIntoViewIfNeeded();
      await page.keyboard.press('Escape'); await page.waitForFunction(()=>!document.querySelector('#data-licences-dialog').open);
      assert(await entry.evaluate(node=>document.activeElement===node),'Escape restores entry focus');
      assert.equal(requests.length,before); assert.deepEqual(errors,[]); assert.deepEqual(external,[]);
      if(process.env.NOTICE_EVIDENCE_DIR){fs.mkdirSync(process.env.NOTICE_EVIDENCE_DIR,{recursive:true}); await page.screenshot({path:path.join(process.env.NOTICE_EVIDENCE_DIR,`sources-${width}.png`),fullPage:true});}
      reports.push({width,harness_cases:JSON.parse(result.text),offline_requests:requests.length-before,layout,errors});
      await context.close();
    }
    if(process.env.NOTICE_EVIDENCE_DIR)fs.writeFileSync(path.join(process.env.NOTICE_EVIDENCE_DIR,'acceptance.json'),JSON.stringify(reports,null,2)+'\n');
    console.log(JSON.stringify(reports));
  } finally {await browser?.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
