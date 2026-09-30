// Safe presentation fixture: real screen/controller, simulated native/download outcomes.
// Never downloads or publishes a region. Product/storage integrity has separate PR42 tests.
import { createRegionScreen } from '../../src/sugarglider/web/static/region_screen.js';
export async function createPolishRegionFixture(container, { manifest, screenFactory = createRegionScreen } = {}) {
  const original = manifest ?? { region_id: 'yvelines-test', display_name: 'Yvelines', build_id: 'a'.repeat(64), bounds: { west: 1.5, south: 48.6, east: 2.3, north: 49 } };
  let rows = [], selected = null, offeringBuild = original.build_id, busy = false, pending = null, cancelRequested = false, readyError = null, catalogError = false;
  const calls = [];
  container.innerHTML = '<summary>Regions</summary><div class="offline-regions-body"><label>Region for this plan<select></select></label><p data-status role="status"></p><progress hidden></progress><details data-diagnostics hidden><summary>Technical details</summary><code></code></details><p data-map role="status"></p><div class="button-row"><button data-refresh type="button" class="button secondary">Check regions</button><button data-cancel type="button" class="button secondary hidden">Cancel download</button></div><ul class="offline-region-list"></ul></div>';
  container.classList.add('offline-regions');
  const elements = { container, selector: container.querySelector('select'), list: container.querySelector('ul'), status: container.querySelector('[data-status]'), progress: container.querySelector('progress'), diagnostics: container.querySelector('[data-diagnostics]'), diagnosticCode: container.querySelector('code'), mapStatus: container.querySelector('[data-map]'), refresh: container.querySelector('[data-refresh]'), cancel: container.querySelector('[data-cancel]') };
  const error = code => Object.assign(Error(code), { code });
  const product = { busy: () => busy,
    install: async (url, options) => { calls.push(['install', url, options.expectedRegionId, options.expectedBuildId, options.expectedDownloadBytes]); busy = true; cancelRequested = false;
      options.onProgress({ component: 'checking', received_bytes: 0 });
      try { await new Promise((resolve, reject) => { pending = { resolve, reject, progress: options.onProgress }; });
        const manifest = { ...original, build_id: offeringBuild }; rows = [{ region_id: original.region_id, status: 'committed', manifest, inactive_build_ids: rows.length ? [rows[0].manifest.build_id] : [] }]; return manifest;
      } finally { busy = false; pending = null; }
    },
    cancel: () => { cancelRequested = true; calls.push(['cancel']); },
    remove: async id => { calls.push(['remove', id]); rows = []; },
    discardUpdate: async (id, build) => { calls.push(['discard', id, build]); rows[0].inactive_build_ids = rows[0].inactive_build_ids.filter(x => x !== build); },
  };
  const screen = screenFactory({ elements, versions: { list: async () => structuredClone(rows) }, product,
    selectedRegionId: () => selected, selectRegion: id => { selected = id; },
    withRegion: async () => { if (readyError) throw error(readyError); return { capabilities: { enabled: true }, reference: { build_id: rows[0].manifest.build_id } }; },
    loadCatalog: async () => { if (catalogError) throw error('regional_catalog_unavailable'); return [{ region_id: original.region_id, display_name: original.display_name, description: 'Yvelines and western Paris area', build_id: offeringBuild, download_bytes: 25000000, manifest_url: 'https://example.invalid/yvelines/manifest.json' }]; },
    confirmRemoval: () => true, lifecycleTarget: null,
  });
  await screen.initialize();
  return { screen, elements, calls,
    progress: (received, total) => pending.progress({ component: 'map', received_bytes: received, total_bytes: total }),
    finish: code => { if (cancelRequested) pending.reject(Object.assign(Error('cancelled'), { name: 'AbortError' })); else if (code) pending.reject(error(code)); else pending.resolve(); },
    update: async () => { offeringBuild = 'b'.repeat(64); await screen.refresh({ catalogToo: true }); },
    installed: async () => { selected = original.region_id; rows = [{ region_id: original.region_id, status: 'committed', manifest: original, inactive_build_ids: [] }]; await screen.refresh(); },
    failCheck: async code => { readyError = code; await screen.refresh(); },
    failCatalog: async () => { catalogError = true; await screen.refresh({ catalogToo: true }); },
    installedBuild: () => rows[0]?.manifest.build_id,
  };
}
