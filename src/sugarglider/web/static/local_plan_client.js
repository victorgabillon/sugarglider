import { deepFreeze } from "./local_candidate_evaluator.js";

// Geometry identity and deliberate-anchor projection stay off the UI thread.
// One pending publication is owned by this page; failure has no server fallback.
export function createLocalPlanPublisher({
  createWorker = () => new Worker(new URL("./local_plan_worker.js", import.meta.url), { type: "module" }),
  lifecycleTarget = globalThis,
  schedule = globalThis.setTimeout.bind(globalThis),
  cancelScheduled = globalThis.clearTimeout.bind(globalThis),
} = {}) {
  let worker = null, pending = null, sequence = 0;
  function prepare() {
    if (worker) return;
    const created = createWorker();
    worker = created;
    created.onmessage = ({ data }) => {
      if (worker !== created || !pending || data?.id !== pending.id) return;
      if (data.type === "result" && data.result?.schema_version === 1
        && data.result.routing_profile === pending.profile && data.result.kind === pending.kind
        && Array.isArray(data.result.candidates) && data.result.candidates.length <= 5) {
        settle(null, deepFreeze(data.result));
      } else fail(data.type === "error" && /^[a-z_]{1,80}$/.test(data.code) ? data.code : "local_publication_failed");
    };
    created.onerror = created.onmessageerror = () => { if (worker === created) fail("local_publication_worker_unavailable"); };
  }
  function publish(request, search) {
    if (pending) return Promise.reject(failure("local_publication_busy"));
    if (!Array.isArray(search?.candidates) || search.candidates.length > 5
      || search.candidates.some((draft) => !Array.isArray(draft.geometry) || draft.geometry.length > 200_000)) {
      return Promise.reject(failure("invalid_local_search_result"));
    }
    try { prepare(); } catch { return Promise.reject(failure("local_publication_worker_unavailable")); }
    const id = ++sequence;
    return new Promise((resolve, reject) => {
      pending = { id, resolve, reject, profile: request.routing_profile, kind: request.kind,
        timer: schedule(() => { if (pending?.id === id) fail("local_publication_timed_out"); }, 60_000) };
      // postMessage snapshots both inputs synchronously before this call returns.
      try { worker.postMessage({ type: "publish", id, request, search }); }
      catch { fail("local_publication_worker_unavailable"); }
    });
  }
  function settle(error, result) {
    const owned = pending;
    if (!owned) return;
    pending = null;
    cancelScheduled(owned.timer);
    if (error) owned.reject(error); else owned.resolve(result);
  }
  function stopWorker() {
    const previous = worker;
    worker = null;
    if (previous) { previous.onmessage = previous.onerror = previous.onmessageerror = null; previous.terminate(); }
  }
  function fail(code) { stopWorker(); settle(failure(code)); }
  function invalidate() {
    stopWorker();
    settle(new DOMException("Local publication cancelled.", "AbortError"));
  }
  lifecycleTarget?.addEventListener?.("pagehide", invalidate);
  return Object.freeze({ publish, invalidate });
}
function failure(code) { const error = new Error(code); error.code = code; return error; }
