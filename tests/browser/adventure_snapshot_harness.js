// Explicitly synthetic model/native replies; actual planner, workers and IDB.
import { setup } from "./adventure_controller_harness.js";
import { createAdventureSnapshotRepository } from "../../src/sugarglider/web/static/adventure_snapshot.js";
import { openPwaStore, createMemoryPwaStore, PWA_STORES } from "../../src/sugarglider/web/static/pwa_store.js";
import { encodeAdventureSnapshot } from "../../src/sugarglider/web/static/adventure_snapshot_validation.js";
import { exportCanonicalCandidate } from "../../src/sugarglider/web/static/local_gpx_export.js";
const assert = (value, message) => { if (!value) throw Error(message); };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
export async function runAdventureSnapshotHarness() {
  const r = await setup(), cases = [];
  let store;
  try {
    const output = await r.controller.run(r.input);
    const selected = output.chosen.result.candidates.at(-1), id = selected.id;
    const encoded = await encodeAdventureSnapshot(output);
    assert(!encoded.payload.includes('user_request') && !encoded.payload.includes('oaiapp_'), 'No prompt or account metadata is retained');
    cases.push('exact_result_passes_shared_identity_arrival_assessment_validation');
    store = await openPwaStore(); assert(store.durable, 'Real browser IndexedDB');
    const repo = createAdventureSnapshotRepository(store, { lifecycleTarget: null });
    assert(await repo.save(output, id), 'Save durable latest result');
    const beforeGpx = await exportCanonicalCandidate(selected).blob.text();
    store.close(); store = await openPwaStore();
    const restarted = createAdventureSnapshotRepository(store, { lifecycleTarget: null });
    const beforeCalls = r.nativeCalls.length, beforeModels = r.calls.length;
    const restored = await restarted.read();
    assert(restored?.selected_id === id && same(restored.output, output), 'Exact request, both real round records, chosen result, stories and selection survive connection restart');
    assert(Object.isFrozen(restored.output.chosen.result.candidates[0].route.geometry[0]), 'Restored line immutable');
    assert(await exportCanonicalCandidate(restored.output.chosen.result.candidates.find(c => c.id === id)).blob.text() === beforeGpx, 'Restored selected GPX exact');
    assert(r.nativeCalls.length === beforeCalls && r.calls.length === beforeModels, 'Recovery cannot route or infer');
    cases.push('real_idb_restart_exact_selection_stories_source_and_gpx_without_native_work');
    await Promise.all(output.chosen.result.candidates.map(c => restarted.save(restored.output, c.id)));
    assert((await restarted.read()).selected_id === output.chosen.result.candidates.at(-1).id, 'Latest selection wins coalesced writes');
    cases.push('selection_writes_coalesce_to_latest');
    const original = await store.get(PWA_STORES.publicRuntime, 'latest-adventure');
    for (const change of [record => { record.payload += ' '; }, record => { record.selected_id = 'wrong'; },
      record => { record.payload = 'x'.repeat(16 * 1024 * 1024 + 1); }]) {
      const record = structuredClone(original); change(record);
      await store.put(PWA_STORES.publicRuntime, 'latest-adventure', record);
      assert(await restarted.read() === null, 'Invalid record unavailable');
      assert(await store.get(PWA_STORES.publicRuntime, 'latest-adventure') === undefined, 'Corrupt latest record removed');
    }
    cases.push('corruption_oversize_unknown_selection_unavailable');
    for (const change of [value => { value.access_token = 'synthetic-forbidden'; },
      value => { value.rounds[0].result.candidates[0].route.geometry[0][0] += .001; },
      value => { value.rounds[0].result.candidates[0].route.analysis.repetition.available = true; },
      value => { value.chosen.grounding.build_id = '0'.repeat(64); },
      value => { value.rounds[0].result.candidates[0].reached_stops.push({ id: 'invented' }); }]) {
      const value = structuredClone(output); change(value);
      assert(!await restarted.save(value, id), 'Forged canonical result cannot be saved');
    }
    cases.push('credentials_geometry_source_and_stop_corruption_rejected');
    let release, writes = 0;
    const delayed = { ...store, put: async (...args) => { writes++; await new Promise(resolve => { release = resolve; }); await store.put(...args); } };
    const delayedRepo = createAdventureSnapshotRepository(delayed, { lifecycleTarget: null });
    const saving = delayedRepo.save(output, id);
    while (!release) await new Promise(resolve => setTimeout(resolve, 10));
    const clearing = delayedRepo.clear();
    release(); await saving; await clearing;
    assert(writes === 1 && await delayedRepo.read() === null, 'Clear drains an already started put before removal');
    cases.push('clear_serializes_behind_inflight_put_no_resurrection');
    let worker;
    const pendingRepo = createAdventureSnapshotRepository(store, { lifecycleTarget: null, createWorker: () => {
      worker = { postMessage() {}, terminate() { this.terminated = true; } }; return worker;
    } });
    const pendingSave = pendingRepo.save(output, id);
    await Promise.resolve();
    await pendingRepo.clear();
    assert(!await pendingSave && worker.terminated && await pendingRepo.read() === null, 'Clear cancels worker and queued write');
    cases.push('clear_cancels_validation_worker_and_pending_write');
    const memory = createAdventureSnapshotRepository(createMemoryPwaStore(), { lifecycleTarget: null });
    assert(!await memory.save(output, id), 'Memory fallback cannot claim durable success');
    const failed = createAdventureSnapshotRepository({ durable: true, get: async () => { throw Error('synthetic failure'); }, put: async () => { throw Error('synthetic failure'); }, remove: async () => {} }, { lifecycleTarget: null });
    assert(await failed.read() === null && !await failed.save(output, id), 'Storage failure remains optional');
    cases.push('optional_storage_failure_preserves_valid_runtime_result');
    return cases;
  } finally { store?.close(); r.controller.cancel(); r.planner.invalidate(); }
}
