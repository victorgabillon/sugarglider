import { PWA_STORES } from "./pwa_store.js";
import { deepFreeze } from "./local_candidate_evaluator.js";

const KEY = "latest-adventure";

// One latest exact result in the existing optional store. No migration, history,
// model transcript, native authority or regional component copy is introduced.
export function createAdventureSnapshotRepository(store, {
  createWorker = () => new Worker(new URL("./adventure_snapshot_worker.js", import.meta.url), { type: "module" }),
  lifecycleTarget = globalThis,
} = {}) {
  let queue = Promise.resolve(), epoch = 0, latest = 0, active = null, cachedOutput = null, cachedEncoding = null;
  function cancel() {
    epoch++; latest++; cachedOutput = cachedEncoding = null;
    active?.finish(null);
  }
  function codec(type, value) {
    return new Promise(resolve => {
      let worker, timer;
      const owned = { finish(result) {
        if (active !== owned) return;
        active = null; clearTimeout(timer); worker?.terminate(); resolve(result);
      } };
      active = owned;
      try {
        worker = createWorker();
        worker.onmessage = ({ data }) => owned.finish(data?.type === "result" ? data.value : null);
        worker.onerror = worker.onmessageerror = () => owned.finish(null);
        timer = setTimeout(() => owned.finish(null), 60000);
        worker.postMessage({ type, value });
      } catch { owned.finish(null); }
    });
  }
  function save(output, selectedId) {
    const owned = epoch, revision = ++latest;
    queue = queue.then(async () => {
      if (owned !== epoch || revision !== latest) return false;
      try {
        if (!output.chosen.result.candidates.some(candidate => candidate.id === selectedId)) return false;
        if (cachedOutput !== output) {
          const encoded = await codec("encode", output);
          if (!encoded || owned !== epoch || revision !== latest) return false;
          cachedEncoding = encoded; cachedOutput = output;
        }
        if (owned !== epoch || revision !== latest) return false;
        await store.put(PWA_STORES.publicRuntime, KEY, { ...cachedEncoding, selected_id: selectedId });
        return owned === epoch && revision === latest && Boolean(store.durable);
      } catch { return false; }
    });
    return queue;
  }
  function read() {
    const owned = epoch;
    const result = queue.then(async () => {
      if (owned !== epoch) return null;
      try {
        const record = await store.get(PWA_STORES.publicRuntime, KEY);
        if (!record || owned !== epoch) return null;
        const decoded = await codec("decode", record);
        if (owned !== epoch) return null;
        if (!decoded) {
          await store.remove(PWA_STORES.publicRuntime, KEY); return null;
        }
        const output = deepFreeze(decoded.output);
        cachedOutput = output;
        cachedEncoding = { schema_version: record.schema_version, payload: record.payload, sha256: record.sha256 };
        return Object.freeze({ output, selected_id: decoded.selected_id });
      } catch { return null; }
    });
    queue = result.then(() => false, () => false);
    return result;
  }
  async function clear() {
    cancel();
    const remove = queue.then(async () => {
      try { await store.remove(PWA_STORES.publicRuntime, KEY); return true; } catch { return false; }
    });
    queue = remove;
    return remove;
  }
  lifecycleTarget?.addEventListener?.("pagehide", cancel);
  return Object.freeze({ durable: Boolean(store.durable), save, read, clear });
}
