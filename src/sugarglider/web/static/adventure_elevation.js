import { createRouteElevationClient, prepareRouteElevation } from "./route_elevation.js";
import { captureRegionalRoutingReference } from "./regional_routing_reference.js";
import { deepFreeze } from "./local_candidate_evaluator.js";
import { ELEVATION_SAMPLING_VERSION } from "./elevation_sampling.js";

// Completed adventure candidates use the existing native elevation protocol.
// No canonical route, geometry or GPX is changed. The caller retains its region
// lease until this sequential batch, including native cancellation, has drained.
export function createAdventureElevationSampler({ client = createRouteElevationClient(), prepare = prepareRouteElevation,
  operationId = () => crypto.randomUUID().replaceAll("-", "") } = {}) {
  const cache = new Map();
  let active = null;
  function clear() { cache.clear(); active?.abort.abort(); }
  async function measure(candidates, rawReference, signal) {
    if (active) throw Error("elevation_busy");
    if (!Array.isArray(candidates) || candidates.length > 5) throw Error("invalid_elevation_candidates");
    const reference = captureRegionalRoutingReference(rawReference);
    const abort = new AbortController(), owned = { abort };
    const cancelled = () => { if (abort.signal.aborted) throw new DOMException("Elevation cancelled.", "AbortError"); };
    const forwardAbort = () => abort.abort();
    signal?.addEventListener("abort", forwardAbort, { once: true });
    if (signal?.aborted) abort.abort();
    active = owned;
    const result = {};
    try {
      for (const candidate of candidates) {
        cancelled();
        const pinned = candidate.diagnostics?.details?.local_routing?.regional_version;
        if (!/^geometry:[a-f0-9]{64}$/.test(candidate.id) || pinned?.region_id !== reference.region_id
          || pinned?.build_id !== reference.build_id || pinned?.routing_pack_id !== reference.pack_id) throw Error("elevation_region_changed");
        const key = JSON.stringify([candidate.id, candidate.route.summary.distance_m, reference, ELEVATION_SAMPLING_VERSION]);
        if (cache.has(key)) { result[candidate.id] = cache.get(key); continue; }
        let operation = null, cancellation = null;
        const cancelNative = () => { if (operation) cancellation ??= Promise.resolve().then(() => client.cancel(operation)).catch(() => null); };
        abort.signal.addEventListener("abort", cancelNative, { once: true });
        try {
          const sampled = await prepare(candidate.route.geometry, candidate.route.summary.distance_m, abort.signal);
          cancelled();
          operation = operationId();
          const measured = await client.analyze({ elevation_version: 1, operation_id: operation, candidate_id: candidate.id,
            profile: candidate.routing_profile, distance_m: candidate.route.summary.distance_m, regional_reference: reference, ...sampled });
          cancelled();
          cache.set(key, measured);
          while (cache.size > 10) cache.delete(cache.keys().next().value);
          result[candidate.id] = measured;
        } catch { cancelled(); /* Missing/incomplete elevation never invalidates a routed line. */ }
        finally {
          abort.signal.removeEventListener("abort", cancelNative);
          if (cancellation) await cancellation;
        }
      }
      cancelled();
      return deepFreeze(result);
    } finally {
      signal?.removeEventListener("abort", forwardAbort);
      if (active === owned) active = null;
    }
  }
  return Object.freeze({ measure, clear });
}
