// Shared UI acquisition for the legacy real-service acceptance drivers. The
// compact/default disclosure is covered by the full bundled-app acceptance.
exports.revealMapEditor = async page => {
  const toggle=page.locator('#route-editor-toggle');
  if(await toggle.isVisible() && await toggle.getAttribute('aria-expanded')==='false')await toggle.click();
};
exports.zoomFromUi = async (page,direction,count=1) => {
  const native=page.locator(direction>0?'.maplibregl-ctrl-zoom-in':'.maplibregl-ctrl-zoom-out');
  if(await native.isVisible()){for(let i=0;i<count;i++)await native.click();return;}
  const tools=page.locator('.header-tools'),display=page.locator('.map-tools');
  const toolsOpen=await tools.evaluate(n=>n.open),displayOpen=await display.evaluate(n=>n.open);
  if(!toolsOpen)await tools.locator(':scope > summary').click();
  if(!displayOpen)await display.locator(':scope > summary').click();
  for(let i=0;i<count;i++)await page.locator(direction>0?'#map-zoom-in':'#map-zoom-out').click();
  if(!displayOpen)await display.locator(':scope > summary').click();
  if(!toolsOpen)await tools.locator(':scope > summary').click();
};
