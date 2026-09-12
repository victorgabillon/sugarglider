import { LocalGpxExportError, MAX_GPX_STOPS, MAX_GPX_VERTICES } from "./local_gpx_export.js";

export const MAX_GPX_OUTPUT_BYTES = 16 * 1024 * 1024;
const EXPORT_TIMEOUT_MS = 60_000;

export function createLocalGpxExporter({
  createWorker = () => new Worker(new URL("./local_gpx_worker.js", import.meta.url), { type: "module" }),
  lifecycleTarget = globalThis,
  schedule = globalThis.setTimeout.bind(globalThis),
  cancelScheduled = globalThis.clearTimeout.bind(globalThis),
} = {}) {
  let worker = null;
  let pending = null;
  let nextId = 0;
  let workerFailed = false;

  function prepare() {
    if (worker) return true;
    workerFailed = false;
    try {
      const created = createWorker();
      worker = created;
      created.onmessage = ({ data }) => {
        if (worker !== created || !pending || data?.id !== pending.id) return;
        if (data.type === "result" && data.blob instanceof Blob
          && data.blob.type === "application/gpx+xml" && data.blob.size > 0
          && data.blob.size <= MAX_GPX_OUTPUT_BYTES
          && typeof data.filename === "string" && data.filename.length <= 104
          && /^[^<>:"/\\|?*\x00-\x1F\x7F]+\.gpx$/u.test(data.filename)) {
          settle(null, { blob: data.blob, filename: data.filename });
        } else if (data.type === "error" && typeof data.code === "string") {
          settle(new LocalGpxExportError(data.code));
        } else {
          failWorker();
        }
      };
      created.onerror = created.onmessageerror = () => {
        if (worker === created) failWorker();
      };
      return true;
    } catch {
      workerFailed = true;
      return false;
    }
  }

  function exportCandidate(candidate) {
    if (pending) return Promise.reject(new LocalGpxExportError("export_busy"));
    let snapshot;
    try { snapshot = exportSnapshot(candidate); }
    catch (error) { return Promise.reject(error); }
    if (workerFailed || !prepare()) return Promise.reject(new LocalGpxExportError("export_worker_unavailable"));
    const id = ++nextId;
    return new Promise((resolve, reject) => {
      const timer = schedule(() => {
        if (pending?.id === id) failWorker("export_timed_out");
      }, EXPORT_TIMEOUT_MS);
      pending = { id, resolve, reject, timer };
      try { worker.postMessage({ type: "export", id, candidate: snapshot }); }
      catch { failWorker(); }
    });
  }

  function settle(error, result) {
    const operation = pending;
    if (!operation) return;
    pending = null;
    cancelScheduled(operation.timer);
    if (error) operation.reject(error); else operation.resolve(result);
  }

  function failWorker(code = "export_worker_unavailable") {
    workerFailed = true;
    stopWorker();
    settle(new LocalGpxExportError(typeof code === "string" ? code : "export_worker_unavailable"));
  }

  function stopWorker() {
    const previous = worker;
    worker = null;
    if (previous) {
      previous.onmessage = previous.onerror = previous.onmessageerror = null;
      previous.terminate();
    }
  }

  function invalidate() {
    stopWorker();
    workerFailed = false;
    settle(new DOMException("Export cancelled because the page was left.", "AbortError"));
  }

  lifecycleTarget?.addEventListener?.("pagehide", invalidate);
  return Object.freeze({ prepare, exportCandidate, invalidate });
}

function exportSnapshot(candidate) {
  const route = candidate?.route;
  if (!Array.isArray(route?.geometry) || route.geometry.length > MAX_GPX_VERTICES
    || !Array.isArray(candidate.reached_stops) || !Array.isArray(candidate.approximated_stops)
    || !Array.isArray(candidate.dropped_stops)
    || candidate.reached_stops.length + candidate.approximated_stops.length > MAX_GPX_STOPS) {
    throw new LocalGpxExportError("export_limit_exceeded");
  }
  const stop = (value) => value && ({
    id: value.id, name: value.name, category: value.category, route_progress: value.route_progress,
    route_to_approach_m: value.route_to_approach_m, distance_m: value.distance_m,
    normal_tolerance_m: value.normal_tolerance_m, configured_maximum_m: value.configured_maximum_m,
    resolved_approach: value.resolved_approach && {
      kind: value.resolved_approach.kind, arrival_tolerance_m: value.resolved_approach.arrival_tolerance_m,
      coordinate: { lat: value.resolved_approach.coordinate?.lat, lon: value.resolved_approach.coordinate?.lon },
    },
  });
  // Snapshot only the export field allowlist before asynchronous work starts.
  // Search/analysis/capability fields never cross into the export worker.
  try {
    return structuredClone({
      routing_profile: candidate.routing_profile,
      route: { name: route.name, routing_profile: route.routing_profile, geometry: route.geometry },
      reached_stops: candidate.reached_stops.map(stop),
      approximated_stops: candidate.approximated_stops.map(stop),
      dropped_stops: candidate.dropped_stops.map((value) => ({ id: value?.id })),
    });
  } catch { throw new LocalGpxExportError("invalid_export_geometry"); }
}
