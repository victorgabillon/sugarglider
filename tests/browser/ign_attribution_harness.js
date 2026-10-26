// This existing fixture exercises explicit English output. French defaults and
// both-language state preservation are covered by localization_harness and the
// full bundled-app acceptance, with strict canonical and GPX comparisons.
import { setLanguage } from "../../src/sugarglider/web/static/i18n.js";
await setLanguage("en", { persist: false, document: null });
import {appendRegionSources, appendTerrainAttribution} from '../../src/sugarglider/web/static/terrain_attribution.js';
import {createRegionScreen} from '../../src/sugarglider/web/static/region_screen.js';
import {createRegionVersionStore} from '../../src/sugarglider/web/static/region_versions.js';
import {parseRegionalManifest, regionalBuildIdentity} from '../../src/sugarglider/web/static/regional_manifest.js';

const assert = (value, message) => { if (!value) throw Error(message); };
const equal = (a, b, message) => assert(JSON.stringify(a) === JSON.stringify(b), message);
const pause = () => new Promise(resolve => setTimeout(resolve, 0));
async function until(check) {
  for (let i = 0; i < 200; i++) { if (check()) return; await new Promise(resolve => setTimeout(resolve, 10)); }
  throw Error('Region screen did not settle');
}
async function validated(value) {
  const copy = structuredClone(value); copy.build_id = await regionalBuildIdentity(copy);
  return parseRegionalManifest(JSON.stringify(copy));
}

function regionElements(host) {
  const container = document.createElement('details'); container.open = true; container.className = 'offline-regions';
  // Fixed test markup; all manifest-derived text is rendered by the production screen.
  container.innerHTML = '<summary>Regions</summary><div class="offline-regions-body"><label>Region for this plan<select></select></label><p data-status role="status"></p><progress hidden></progress><p data-map role="status"></p><div class="button-row"><button data-refresh type="button" class="button secondary">Check regions</button><button data-cancel type="button" class="button secondary hidden">Cancel download</button></div><ul class="offline-region-list"></ul></div>';
  host.replaceChildren(container);
  return {container, selector:container.querySelector('select'), list:container.querySelector('ul'),
    status:container.querySelector('[data-status]'), progress:container.querySelector('progress'), mapStatus:container.querySelector('[data-map]'),
    refresh:container.querySelector('[data-refresh]'), cancel:container.querySelector('[data-cancel]')};
}

export async function run() {
  const cases = [];
  const fixture = await (await fetch('../fixtures/ign_terrain_attribution.json')).json();
  const copernicus = await (await fetch('../fixtures/pr94_terrain_attribution.json')).json();
  const privateManifest = await parseRegionalManifest(JSON.stringify(fixture.manifest));
  const publicValue = structuredClone(privateManifest); publicValue.publication_allowed = true;
  publicValue.components.elevation.files[0] = fixture.proposed_public_elevation_descriptor;
  const publicManifest = await validated(publicValue);
  assert(privateManifest.build_id !== publicManifest.build_id, 'private and proposed-public metadata have distinct identities');
  assert(!('derivation' in privateManifest.components.elevation), 'top-level descriptors have no full derivation');
  const terrain = document.createElement('div');
  for (const manifest of [privateManifest, publicManifest]) {
    terrain.replaceChildren(); appendRegionSources(terrain, manifest);
    for (const text of ['IGN — RGE ALTI® 5 m', 'ground-elevation model', 'NGF-IGN69', 'EPSG:5720', 'one-arcsecond HGT',
      'integer metres', 'does not retain the original 5 m resolution', 'Valhalla routing graph', 'Licence Ouverte 2.0', 'not the terrain acquisition date', 'do not imply endorsement']) {
      assert(terrain.textContent.includes(text), `source fact: ${text}`);
    }
    assert(terrain.querySelectorAll('.terrain-editions li').length === 17, 'all source editions available locally');
    assert(!terrain.textContent.includes('EGM96') && !terrain.textContent.includes('Copernicus'), 'IGN never mislabeled');
    assert(terrain.querySelector('summary').textContent === 'Data sources and licences', 'discoverable title');
    assert(!terrain.querySelector('[data-source-disclosure=editions]').open, 'editions initially collapsed');
  }
  cases.push('real_v2_descriptor_shape_exact_ign_payloads_private_and_public_metadata');
  const cop = {components:{elevation:{files:[{}, ...copernicus.derived_sha256.map(sha256 => ({sha256}))]}}};
  terrain.replaceChildren(); appendRegionSources(terrain, cop);
  assert(terrain.textContent.includes(copernicus.attribution) && terrain.textContent.includes(copernicus.disclaimer), 'Copernicus notices unchanged');
  assert(terrain.querySelector('a').href === copernicus.license_url, 'Copernicus license unchanged');
  cases.push('historical_copernicus_credit_disclaimer_and_license_preserved');
  const malformed = [null, {}, {components:{elevation:{files:'not an array'}}}, {components:{elevation:{files:[null, null, null, null, null]}}}];
  for (const key of ['sha256', 'path', 'byte_size', 'format']) {
    const copy = structuredClone(privateManifest); copy.components.elevation.files[1][key] = key === 'byte_size' ? 7 : 'unsupported'; malformed.push(copy);
  }
  for (const change of [files => files.pop(), files => files.reverse(), files => files.push(files[1]), files => { files[0] = null; }]) {
    const copy = structuredClone(privateManifest); change(copy.components.elevation.files); malformed.push(copy);
  }
  for (const manifest of malformed) {
    terrain.replaceChildren(); appendRegionSources(terrain, manifest);
    assert(terrain.textContent.includes('unavailable or unsupported') && !terrain.querySelector('a'), 'malformed source stays neutral');
    assert(!terrain.textContent.includes('IGN') && !terrain.textContent.includes('Copernicus'), 'no invented provenance');
    assert(!appendTerrainAttribution(document.createElement('div'), manifest), 'standalone recognition fails closed');
  }
  const otherGraph = structuredClone(privateManifest); otherGraph.components.routing.files[1].sha256 = '0'.repeat(64);
  terrain.replaceChildren(); appendRegionSources(terrain, otherGraph);
  assert(terrain.textContent.includes('identifies the elevation HGT only') && !terrain.textContent.includes('incorporated into'), 'HGT identity never credits an unrelated graph');
  cases.push('unknown_malformed_reordered_truncated_and_modified_payloads_fail_closed');
  cases.push('graph_credit_requires_exact_separate_routing_archive_identity');

  const hostile = structuredClone(privateManifest);
  hostile.source.source_url = 'javascript:alert(1)'; hostile.source.product = '<img src=x onerror=alert(1)> IGN';
  hostile.components.elevation.derivation = {license_url:'javascript:alert(1)', sources:{files:[{filename:'<script>alert(1)</script>'}]}};
  hostile.components.elevation.files[1].source_url = 'https://attacker.invalid/';
  terrain.replaceChildren(); appendRegionSources(terrain, hostile);
  assert(!terrain.querySelector('script,img') && !terrain.textContent.includes('alert(1)'), 'manifest source text never inserted');
  for (const a of terrain.querySelectorAll('a')) {
    assert(new URL(a.href).hostname === 'www.data.gouv.fr' && a.target === '_blank' && a.rel === 'noopener noreferrer', 'only code-owned deliberate official links');
  }
  hostile.components.elevation.files[1].sha256 = '<svg onload=alert(1)>';
  terrain.replaceChildren(); appendRegionSources(terrain, hostile);
  assert(!terrain.querySelector('a,svg,script,img') && !terrain.textContent.includes('IGN'), 'hostile unsupported source remains neutral');
  cases.push('hostile_html_source_fields_and_unsafe_urls_cannot_create_notices_or_links');

  // Real OPFS stores only fixture metadata. Activation acknowledgements are synthetic;
  // component checksum/install gates are covered by the existing regional harnesses.
  const origin = await navigator.storage.getDirectory(), directoryName = `ign-notices-${crypto.randomUUID()}`;
  const directory = await origin.getDirectoryHandle(directoryName, {create:true});
  const storage = {getDirectory:async () => directory};
  let selected = privateManifest.region_id, rowsCalls = 0, routingCalls = 0;
  const mutations = [];
  const product = {busy:() => false, cancel:() => {}, install:async () => mutations.push('install'),
    remove:async () => mutations.push('remove'), discardUpdate:async () => mutations.push('discard')};
  const host = document.getElementById('fixture');
  let elements = regionElements(host);
  const makeScreen = versions => createRegionScreen({elements, versions:{list:async () => { rowsCalls++; return versions.list(); }}, product,
    selectedRegionId:() => selected, selectRegion:id => { selected = id; }, loadCatalog:async () => [],
    withRegion:async () => { routingCalls++; return {capabilities:{}, reference:{build_id:(await versions.read(selected)).build_id}}; },
    lifecycleTarget:null});
  try {
    let versions = createRegionVersionStore({storage});
    const ticket = await versions.stage(JSON.stringify(privateManifest));
    await versions.activate(ticket, {verifyComponent:async () => true});
    const unsupportedValue = structuredClone(privateManifest); unsupportedValue.region_id = 'other-region'; unsupportedValue.display_name = '<img src=x onerror=alert(1)> Other region';
    unsupportedValue.components.elevation.files[1].sha256 = '0'.repeat(64);
    const unsupported = await validated(unsupportedValue);
    await versions.activate(await versions.stage(JSON.stringify(unsupported)), {verifyComponent:async () => true});
    let screen = makeScreen(versions); await screen.initialize();
    let cards = elements.list.querySelectorAll('li.offline-region-card');
    assert(cards.length === 2 && !elements.list.querySelector('img'), 'region names escaped and independent installed cards');
    const ignCard = () => [...elements.list.children].find(card => card.querySelector('strong').textContent === privateManifest.display_name);
    const source = () => ignCard().querySelector('.region-sources');
    const sourceSummary = () => source().querySelector('summary');
    assert(source().textContent.includes('NGF-IGN69') && !document.querySelector('[data-elevation-chart]'), 'installed facts available without a route or chart');
    const originalFetch = globalThis.fetch; const originalManifest = JSON.stringify(await versions.list());
    const before = [rowsCalls, routingCalls, mutations.length]; let fetches = 0;
    globalThis.fetch = () => { fetches++; throw Error('Offline'); };
    try {
      source().open = true; source().querySelector('[data-source-disclosure=editions]').open = true;
      sourceSummary().focus(); await pause();
      equal([rowsCalls, routingCalls, mutations.length], before, 'opening source details has no reads, routing or mutation');
      assert(fetches === 0, 'opening source details never fetches');
      await screen.refresh();
      assert(source().open && source().querySelector('[data-source-disclosure=editions]').open, 'refresh preserves both disclosure states');
      assert(document.activeElement === sourceSummary(), 'refresh restores source summary focus');
      const official = source().querySelector('a'); official.focus(); await screen.refresh();
      assert(document.activeElement === source().querySelector('a'), 'refresh restores source link focus');
      elements.selector.value = unsupported.region_id; elements.selector.dispatchEvent(new Event('change'));
      await until(() => elements.list.getAttribute('aria-busy') === 'false');
      assert(selected === unsupported.region_id, 'selection still works');
      assert(source().textContent.includes('NGF-IGN69'), 'IGN credit remains on its own region card');
      const other = [...elements.list.children].find(card => card !== ignCard());
      assert(other.querySelector('.region-sources').textContent.includes('unsupported') && !other.querySelector('.region-sources a'), 'other region never inherits selected IGN credit');
      versions = createRegionVersionStore({storage}); elements = regionElements(host);
      screen = makeScreen(versions); await screen.initialize();
      assert(source().textContent.includes('Source archive editions (17)'), 'restart reads existing installed descriptors offline');
      equal(JSON.stringify(await versions.list()), originalManifest, 'source views and selection do not mutate stored data');
      assert(fetches === 0 && mutations.length === 0, 'all source lifecycle checks offline with no product mutations');
    } finally { globalThis.fetch = originalFetch; }
    cases.push('real_opfs_metadata_restart_refresh_region_switch_without_route_or_network');
    cases.push('native_details_preserve_open_state_summary_and_license_link_focus');
    cases.push('source_disclosure_zero_reads_downloads_routing_sampling_or_mutations');
    // Leave the real region screen visible for Playwright keyboard/layout acceptance.
    window.ignAttributionHarness = {screen, elements, manifest:privateManifest};
  } finally { await origin.removeEntry(directoryName, {recursive:true}); }
  return cases;
}
