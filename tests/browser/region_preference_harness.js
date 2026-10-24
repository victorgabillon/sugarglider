import { createRegionPreference } from '../../src/sugarglider/web/static/region_preference.js';
import { createRegionScreen } from '../../src/sugarglider/web/static/region_screen.js';
import { createVersionedRegionComponents } from '../../src/sugarglider/web/static/region_components.js';
import { createMemoryPwaStore } from '../../src/sugarglider/web/static/pwa_store.js';
import { selectCommittedRegion } from '../../src/sugarglider/web/static/regional_planning.js';
import { distribution } from './pr42_region_components_harness.js';

const key = 'planner-region-id';
const equal = (a, b, message) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw Error(`${message}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`); };
const wait = () => new Promise(resolve => setTimeout(resolve, 10));
async function until(check) { for (let i = 0; i < 500; i++) { if (await check()) return; await wait(); } throw Error('Preference UI did not settle'); }
function memory(value) {
  const values = new Map(value === undefined ? [] : [[key, value]]);
  return { durable: true, values, get: async (_, id) => values.get(id), put: async (_, id, v) => { values.set(id, v); }, remove: async (_, id) => { values.delete(id); } };
}

// Tiny synthetic web components are verified normally. Native component presence
// is acknowledged here; native file verification has independent JVM coverage.
export async function seedRegion(fixture, versions, id, label, { commit = true } = {}) {
  fixture = structuredClone(fixture); fixture.manifest.region_id = id;
  for (const [kind, component] of Object.entries(fixture.manifest.components)) component.component_id = `${id}-${kind}`;
  const current = await distribution(fixture, label);
  const ticket = await versions.stage(JSON.stringify(current.manifest));
  if (!commit) return current.manifest;
  const components = (manifest, directory) => createVersionedRegionComponents({ manifest, directory,
    pageLocation: { href: 'https://appassets.androidplatform.net/' },
    fetchResource: async url => {
      const bytes = current.files.get(new URL(url).pathname.slice(1));
      if (!bytes) throw Error('Unexpected synthetic download');
      return new Response(bytes, { headers: { 'Content-Length': String(bytes.byteLength) } });
    } });
  await versions.withStagedVersion(ticket, async ({ manifest, directory }) => {
    const scoped = await components(manifest, directory);
    await scoped.installMap('https://packs.example/manifest.json');
    await scoped.installIndexes('https://packs.example/manifest.json');
  });
  await versions.activate(ticket, { verifyComponent: async (kind, manifest, directory) => {
    const scoped = await components(manifest, directory);
    if (kind === 'map') return scoped.verifyMap();
    if (['pois', 'nature'].includes(kind)) await scoped.openIndexes();
    return true;
  } });
  return current.manifest;
}

export async function runRegionPreferenceHarness() {
  const cases = [], committed = id => ({ region_id: id, status: 'committed' });
  let rows = [committed('alpha'), committed('beta')];
  const versions = { list: async () => rows };
  for (const value of [null, false, 4, {}, [], { region_id: 'alpha' }, '../alpha', 'ALPHA', 'missing']) {
    const store = memory(value), preference = createRegionPreference(store);
    equal(await preference.restore(versions), null, 'Malformed/stale preference ignored');
    await until(() => !store.values.has(key));
  }
  cases.push('corrupt_and_missing_ids_ignored_and_cleared');
  const store = memory('beta'), preference = createRegionPreference(store);
  equal(await preference.restore(versions), 'beta', 'Valid choice restored among several regions');
  cases.push('multiple_regions_restore_exact_id_without_list_order_fallback');
  rows = [committed('alpha'), { region_id: 'beta', status: 'unavailable', code: 'regional_install_incomplete' }];
  equal(await preference.restore(versions), null, 'Unavailable metadata cannot restore a preference');
  rows = [committed('alpha'), { region_id: 'beta', status: 'not_installed' }];
  await preference.remember('beta');
  equal(await preference.restore(versions), null, 'Staged-only region cannot restore a preference');
  cases.push('unavailable_and_interrupted_first_install_never_restored');
  rows = [committed('beta')];
  await preference.remember('beta');
  equal(await preference.restore(versions), 'beta', 'Interrupted update retains committed region');
  rows = [committed('alpha')];
  equal(await preference.restore(versions), null, 'Removed preference never restored');
  equal(selectCommittedRegion(rows, null).region_id, 'alpha', 'Existing sole-region fallback remains');
  cases.push('deleted_choice_ignored_with_existing_sole_region_default');
  rows.push(committed('beta'));
  try { selectCommittedRegion(rows, null); throw Error('Missing explicit selection was accepted'); }
  catch (error) { equal(error.code, 'regional_selection_required', 'Multiple regions require explicit selection'); }
  cases.push('multiple_regions_without_preference_require_explicit_choice');

  let release;
  const slow = memory();
  const put = slow.put;
  slow.put = async (...args) => { if (args[2] === 'alpha') await new Promise(resolve => { release = resolve; }); return put(...args); };
  const ordered = createRegionPreference(slow);
  const first = ordered.remember('alpha'); await until(() => release);
  const second = ordered.remember('beta'), clear = ordered.remember(null), last = ordered.remember('gamma');
  release(); await Promise.all([first, second, clear, last]);
  equal([...slow.values.entries()], [[key, 'gamma']], 'Only latest ID retained');
  await ordered.remember(null); equal([...slow.values], [], 'Clear deletes preference');
  cases.push('rapid_switches_and_clear_serialize_pending_writes');
  let failWrite = true;
  const recovering = memory(), recoveryPut = recovering.put; recovering.put = async (...args) => { if (failWrite) throw Error('Unavailable'); return recoveryPut(...args); };
  const resilient = createRegionPreference(recovering);
  equal(await resilient.remember('alpha'), false, 'Write failure is harmless');
  failWrite = false; equal(await resilient.remember('beta'), true, 'Queue recovers after failed write');
  cases.push('failed_write_does_not_poison_later_selection');
  const broken = { durable: false, get: async () => { throw Error('Unavailable'); }, put: async () => { throw Error('Unavailable'); }, remove: async () => { throw Error('Unavailable'); } };
  const optional = createRegionPreference(broken);
  equal(await optional.restore(versions), null, 'Read failure is optional');
  equal(await optional.remember('alpha'), false, 'Write failure is optional');
  const fallback = createRegionPreference(createMemoryPwaStore());
  equal(await fallback.remember('alpha'), false, 'Optional memory fallback is not durable');
  equal(await fallback.restore(versions), 'alpha', 'Current-session memory remains usable');
  cases.push('optional_storage_failure_and_memory_fallback_preserve_session');
  const retained = memory('alpha');
  equal(await createRegionPreference(retained).restore({ list: async () => { throw Error('OPFS unavailable'); } }), null, 'Metadata failure cannot validate a hint');
  equal(retained.values.get(key), 'alpha', 'Temporary metadata failure does not destroy preference');
  cases.push('metadata_failure_leaves_authoritative_diagnostics_to_region_checks');

  // Exercise the production screen's actual event handlers, including operation
  // completion/failure boundaries. No routing or private data is involved.
  let selected = null, installing, installed, removeFailure = false;
  rows = [];
  const screenStore = memory(), screenPreference = createRegionPreference(screenStore);
  const manifest = id => ({ region_id: id, display_name: id, build_id: id.repeat(64).slice(0, 64) });
  const row = id => ({ ...committed(id), manifest: manifest(id), inactive_build_ids: [] });
  const product = {
    busy: () => false, cancel() {},
    install: async (_, { expectedRegionId: id }) => {
      await new Promise(resolve => { installing = resolve; });
      installed = row(id); rows = [...rows.filter(item => item.region_id !== id), installed]; return installed.manifest;
    },
    remove: async id => { if (removeFailure) throw Error('Removal failed'); rows = rows.filter(item => item.region_id !== id); },
  };
  const container = document.createElement('details');
  container.innerHTML = '<select></select><ul></ul><p></p><button data-refresh>Refresh</button><button data-cancel>Cancel</button>';
  document.body.append(container);
  const elements = { container, selector: container.querySelector('select'), list: container.querySelector('ul'), status: container.querySelector('p'), refresh: container.querySelector('[data-refresh]'), cancel: container.querySelector('[data-cancel]') };
  const screen = createRegionScreen({ elements, versions, product, selectedRegionId: () => selected,
    selectRegion: (id, { remember = true } = {}) => { selected = id; if (remember) void screenPreference.remember(id); },
    withRegion: async run => { const entry = selectCommittedRegion(rows, selected); return run({ capabilities: { enabled: true }, reference: entry.manifest }); },
    loadCatalog: async () => ['alpha', 'beta', 'gamma'].map(id => ({ ...manifest(id), description: 'Synthetic', download_bytes: 10, manifest_url: `https://packs.example/${id}/manifest.json` })),
    confirmRemoval: () => true, lifecycleTarget: null });
  const settled = () => until(() => !elements.refresh.disabled);
  async function choose(id) { elements.selector.value = id ?? ''; elements.selector.dispatchEvent(new Event('change')); await settled(); }
  async function click(id, action) {
    const control = elements.list.querySelector(`[data-region-action="${id}:${action}"]`);
    if (!control || control.disabled) throw Error(`Unavailable action ${id}:${action}`);
    control.click();
  }
  try {
    await screen.initialize();
    await click('alpha', 'install'); await until(() => installing);
    equal(screenStore.values.has(key), false, 'Starting install cannot select a region');
    installing(); await settled();
    equal(selected, 'alpha', 'First successful install selected');
    await until(() => screenStore.values.get(key) === 'alpha');
    cases.push('first_install_persisted_only_after_success');
    installing = null; await click('beta', 'install'); await until(() => installing); installing(); await settled();
    equal(selected, 'alpha', 'Additional install preserves selection');
    equal(screenStore.values.get(key), 'alpha', 'Additional install preserves preference');
    cases.push('additional_install_preserves_existing_choice');
    await choose('beta'); await until(() => screenStore.values.get(key) === 'beta');
    cases.push('screen_selection_persists_new_id');
    await choose(null); await until(() => !screenStore.values.has(key));
    equal(selected, null, 'Explicit multi-region deselection stays empty');
    cases.push('explicit_deselection_removes_preference');
    await choose('beta');
    removeFailure = true; await click('beta', 'remove'); await settled();
    equal(selected, 'beta', 'Failed removal retains selection');
    equal(screenStore.values.get(key), 'beta', 'Failed removal retains preference');
    removeFailure = false;
    await click('alpha', 'remove'); await settled();
    equal(screenStore.values.get(key), 'beta', 'Unrelated removal retains preference');
    cases.push('failed_and_unrelated_removal_preserve_choice');
    await choose(null); await until(() => !screenStore.values.has(key));
    equal(selected, 'beta', 'Sole-region default remains automatic');
    cases.push('sole_region_default_does_not_rewrite_explicit_clear');
    await choose('beta'); await until(() => screenStore.values.get(key) === 'beta');
    await click('beta', 'remove'); await settled();
    await until(() => !screenStore.values.has(key)); equal(selected, null, 'Selected removal clears state');
    cases.push('selected_region_removal_clears_memory_and_preference');
    rows = [row('alpha'), row('beta')]; await screen.refresh(); await choose('alpha');
    rows = [row('beta')]; await screen.refresh();
    await until(() => !screenStore.values.has(key)); equal(selected, 'beta', 'Missing selection reconciled by sole-region rule');
    cases.push('external_removal_reconciles_selection_without_persisting_fallback');
    screenStore.put = broken.put;
    rows.push(row('alpha')); await screen.refresh(); await choose('alpha');
    equal(selected, 'alpha', 'Write failure never blocks switching in current session');
    cases.push('screen_switch_survives_preference_write_failure');
  } finally { container.remove(); }
  return cases;
}
