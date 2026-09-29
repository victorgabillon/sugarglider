import { initializeAppShell } from '../../src/sugarglider/web/static/app_shell.js';
import { createPolishRegionFixture } from './ui2_polish_fixture.js';
import { renderPwaStatus } from '../../src/sugarglider/web/static/pwa_view.js';
const assert=(ok,message)=>{if(!ok)throw Error(message)};
const until=async fn=>{for(let i=0;i<100;i++){if(fn())return;await new Promise(r=>setTimeout(r,10))}throw Error('operation did not settle')};
export async function runPolishHarness(){
 const cases=[], root=document.createElement('details');document.body.append(root);const f=await createPolishRegionFixture(root),e=f.elements;
 const check=(name,fn)=>{fn();cases.push(name)}, click=text=>{const b=[...e.list.querySelectorAll('button')].find(b=>b.textContent===text);assert(b&&!b.disabled,text);b.focus();b.click();return b}, settled=()=>until(()=>!e.refresh.disabled);
 try {
 check('available_no_implicit_download',()=>assert(f.calls.length===0&&e.list.querySelector('[data-region-state="Available"]'),'available'));
 check('identifiers_and_cleanup_disclosed',()=>assert(e.list.querySelector('.region-technical').textContent.includes('a'.repeat(64))&&!e.list.querySelector('.region-technical').open&&e.list.querySelector('.region-technical [data-mutation="remove"]'),'disclosure'));
 check('download_is_primary',()=>assert(e.list.querySelector('[data-region-action$=":install"]').classList.contains('primary'),'primary'));
 click('Download region');await until(()=>!e.cancel.classList.contains('hidden'));
 check('unknown_total_indeterminate',()=>assert(!e.progress.hasAttribute('value')&&e.status.textContent.includes('Downloading'),'indeterminate'));
 f.progress(12500000,25000000);
 check('real_component_progress_not_estimated',()=>assert(e.progress.value===12500000&&e.progress.max===25000000&&e.status.textContent.includes('12.5 MB of 25.0 MB'),'bytes'));
 check('busy_actions_locked_cancel_available',()=>assert(e.selector.disabled&&e.refresh.disabled&&!e.cancel.disabled&&e.list.getAttribute('aria-busy')==='true','busy'));
 f.finish();await settled();
 check('ready_only_after_verification',()=>assert(e.list.querySelector('[data-region-state="Ready"]')&&e.status.dataset.state==='regional_ready'&&e.progress.hidden,'ready'));
 check('rerender_restores_action_focus',()=>assert(document.activeElement?.dataset.regionAction?.endsWith(':install'),'focus'));
 check('install_call_contract_unchanged',()=>assert(JSON.stringify(f.calls[0])===JSON.stringify(['install','https://example.invalid/yvelines/manifest.json','yvelines-test','a'.repeat(64),25000000]),'call arguments'));
 e.list.querySelector('.region-technical').open=true;await f.screen.refresh();
 check('technical_disclosure_retained',()=>assert(e.list.querySelector('.region-technical').open,'open retained'));
 await f.update();check('update_available_distinct_from_ready',()=>assert(e.list.querySelector('[data-region-state="Update available"]')&&e.list.textContent.includes('installed region stays available'),'update'));
 click('Update region');await until(()=>!e.cancel.classList.contains('hidden'));e.cancel.click();
 check('cancel_waits_for_file_work',()=>assert(e.cancel.disabled&&e.status.dataset.state==='regional_cancelling','cancelling'));
 f.finish();await settled();check('cancel_keeps_installed_region_and_message',()=>assert(f.installedBuild()==='a'.repeat(64)&&e.status.dataset.state==='regional_install_cancelled','retained'));
 click('Update region');await until(()=>!e.cancel.classList.contains('hidden'));f.finish('regional_checksum_mismatch');await settled();
 check('integrity_failure_visible_and_old_build_retained',()=>assert(e.status.textContent.includes('integrity check')&&f.installedBuild()==='a'.repeat(64),'failure'));
 check('exact_error_code_in_disclosure',()=>assert(!e.diagnostics.hidden&&e.diagnosticCode.textContent==='regional_checksum_mismatch'&&!e.diagnostics.open,'code'));
 click('Update region');await until(()=>!e.cancel.classList.contains('hidden'));f.finish();await settled();
 check('successful_update_ready',()=>assert(f.installedBuild()==='b'.repeat(64)&&e.list.querySelector('[data-region-state="Ready"]'),'updated'));
 e.list.querySelector('.region-technical').open=true;click('Remove unused download');await settled();check('unused_cleanup_uses_exact_identity',()=>assert(f.calls.some(c=>JSON.stringify(c)===JSON.stringify(['discard','yvelines-test','a'.repeat(64)])),'discard id'));
 await f.failCatalog();check('catalog_error_does_not_hide_installed_region',()=>assert(e.status.dataset.state==='regional_catalog_unavailable'&&f.installedBuild()==='b'.repeat(64),'catalog'));
 }finally{root.remove()}
 const status=document.createElement('div');status.innerHTML='<section id="pwa-status-panel"><h2 id="pwa-network-status"></h2><p id="pwa-status-message"></p><button id="retry-connection"></button><button id="reload-pwa-update"></button></section><p id="app-status-summary"></p>';document.body.append(status);
 const state={networkStatus:'online',pwaSupported:true,pwaStatus:'ready',storagePersistenceStatus:'unknown',pwaUpdateAvailable:false};
 try{
 renderPwaStatus(state);check('healthy_status_readable_in_tools_without_band',()=>assert(status.querySelector('#pwa-status-panel').classList.contains('hidden')&&status.querySelector('#app-status-summary').textContent.includes('Online'),'healthy'));
 for(const [name,patch] of [['offline',{networkStatus:'offline'}],['storage_failure',{storagePersistenceStatus:'unavailable'}],['update',{pwaUpdateAvailable:true}],['saved_snapshot',{offlineSnapshotKind:'saved_route'}]]){renderPwaStatus({...state,...patch});check(name+'_notice_not_hidden',()=>assert(!status.querySelector('#pwa-status-panel').classList.contains('hidden'),'notice visible'))}
 }finally{status.remove()}
 await checkNestedControls(cases);
 return cases;
}

// Render actual application CSS: nested Tools controls must not inherit the
// dark topbar's white foreground on their light backgrounds.
async function checkNestedControls(cases) {
 const markup = new DOMParser().parseFromString(await (await fetch('../../src/sugarglider/web/static/index.html')).text(), 'text/html');
 markup.querySelectorAll('script, link[rel=manifest]').forEach(n => n.remove());
 markup.querySelectorAll('link[href]').forEach(n => { n.href = new URL(`../../src/sugarglider/web${n.getAttribute('href')}`, location.href).href; });
 const luminance = color => {
  const rgb = color.match(/[\d.]+/g).slice(0, 3).map(v => Number(v) / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
  return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
 };
 const contrast = (a, b) => { const x = luminance(a), y = luminance(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
 for (const [width, height, scale] of [[360,800,1],[390,844,1],[412,915,1],[1280,800,1],[1440,900,1],[390,420,1],[360,640,2]]) {
  const frame = document.createElement('iframe'); frame.title = 'Regions contrast and reachability'; frame.style.cssText = `width:${width}px;height:${height}px;border:0;display:block`;
  const loaded = new Promise(resolve => frame.addEventListener('load', resolve, {once:true})); frame.srcdoc = '<!doctype html>' + markup.documentElement.outerHTML; document.body.append(frame); await loaded;
  try {
   const doc = frame.contentDocument, win = frame.contentWindow;
   const shell = initializeAppShell({document:doc});
   shell.show('plan');
   doc.documentElement.style.fontSize = `${16*scale}px`; doc.querySelector('.header-tools').open = true;
   const root = doc.querySelector('#offline-regions'); root.classList.remove('hidden'); root.open = true;
   await createPolishRegionFixture(root);
   const secondary = root.querySelector('[data-refresh]'), primary = root.querySelector('.button.primary'), danger = root.querySelector('.button.danger');
   root.querySelector('.region-technical').open = true;
   for (const button of [secondary, primary, danger]) {
    button.scrollIntoView({block:'nearest'}); const css = win.getComputedStyle(button), rect = button.getBoundingClientRect(), panel = doc.querySelector('.header-tools-menu').getBoundingClientRect();
    assert(contrast(css.color, css.backgroundColor) >= 4.5, `${button.textContent} contrast at ${width}`);
    assert(rect.height >= 44 && rect.top >= panel.top-1 && rect.bottom <= panel.bottom+1, `reachable 44px ${button.textContent}`);
   }
   primary.focus(); assert(contrast(win.getComputedStyle(primary).outlineColor, win.getComputedStyle(root.querySelector('li')).backgroundColor) >= 3, 'focus outline contrast');
   secondary.disabled = true; const disabled = win.getComputedStyle(secondary); assert(contrast(disabled.color, disabled.backgroundColor) >= 4.5, 'readable disabled text');
   assert(doc.documentElement.scrollWidth <= width, 'no horizontal overflow');
   cases.push(`nested_controls_contrast_focus_targets_${width}_${height}_${scale}x`);
   doc.querySelector('.header-tools').open = false;
   const map = doc.querySelector('#map');
   map.innerHTML = '<div class="maplibregl-control-container"><div class="maplibregl-ctrl-top-left"><div class="maplibregl-ctrl maplibregl-ctrl-group"><button aria-label="Zoom in"></button><button aria-label="Zoom out"></button><button aria-label="Reset bearing"></button></div></div></div>';
   const bounds = map.getBoundingClientRect(), options = doc.querySelector('.map-tools'), menu = options.querySelector('summary').getBoundingClientRect();
   for (const button of map.querySelectorAll('button')) {
    const r = button.getBoundingClientRect(); assert(r.height >= 44 && r.width >= 44 && r.bottom <= bounds.bottom && r.right <= bounds.right, 'map navigation inside shallow map');
    assert(r.right <= menu.left || r.bottom <= menu.top || r.left >= menu.right || r.top >= menu.bottom, 'map controls do not overlap');
   }
   options.open = true; const legend = doc.querySelector('.legend'); legend.querySelector('summary').scrollIntoView({block:'nearest'}); legend.open = true;
   const item = legend.querySelector('.legend-items span:last-child'); item.scrollIntoView({block:'nearest'});
   const itemRect = item.getBoundingClientRect(), optionRect = options.getBoundingClientRect();
   assert(itemRect.top >= optionRect.top-1 && itemRect.bottom <= optionRect.bottom+1, 'full legend scrolls in Map options');
   cases.push(`shallow_map_controls_and_legend_${width}_${height}_${scale}x`);
   shell.destroy();
  } finally { frame.remove(); }
 }
}
