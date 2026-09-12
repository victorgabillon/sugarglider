import { MAX_ROUTE_POINTS } from "./local_routing.js";
import { PUBLIC_PROFILE_METADATA } from "./public_profile_metadata.js";

export class LocalPlanningBudgetError extends Error {
  constructor(phase) {
    super("The local route request budget is exhausted.");
    this.name = "LocalPlanningBudgetError";
    this.code = "local_route_budget_exhausted";
    this.phase = phase;
  }
}

// One instance belongs to one planning request. Only this gateway invokes the
// injected native routing adapter or reserves route-call budget.
export function createLocalPlanningContext({ profile, route, totalLimit, phaseLimits }) {
  if (!Object.hasOwn(PUBLIC_PROFILE_METADATA, profile) || typeof route !== "function"
    || !Number.isSafeInteger(totalLimit) || totalLimit < 1 || totalLimit > 24
    || !phaseLimits || Array.isArray(phaseLimits) || !Object.keys(phaseLimits).length
    || Object.entries(phaseLimits).some(([phase, limit]) => !/^[a-z_]{1,32}$/.test(phase)
      || !Number.isSafeInteger(limit) || limit < 0 || limit > totalLimit)) {
    throw new TypeError("Invalid local planning context.");
  }
  const limits = Object.freeze({ ...phaseLimits });
  const phaseUsage = Object.fromEntries(Object.keys(limits).map((phase) => [phase, 0]));
  const entries = new Map();
  let used = 0, lookups = 0, hits = 0, misses = 0, successful = 0, failed = 0, rejected = 0;

  function requestRoute(points, phase) {
    if (!Object.hasOwn(limits, phase) || !Array.isArray(points) || points.length < 2 || points.length > MAX_ROUTE_POINTS
      || points.some((point) => !point || !Number.isFinite(point.lat) || Math.abs(point.lat) > 90
        || !Number.isFinite(point.lon) || Math.abs(point.lon) > 180)) {
      return Promise.reject(new TypeError("Invalid local route request."));
    }
    const coordinates = Object.freeze(points.map(({ lat, lon }) => Object.freeze({ lat, lon })));
    const key = JSON.stringify([profile, coordinates]);
    const existing = entries.get(key);
    if (existing) {
      lookups += 1;
      hits += 1;
      return existing;
    }
    if (used >= totalLimit || phaseUsage[phase] >= limits[phase]) {
      rejected += 1;
      return Promise.reject(new LocalPlanningBudgetError(phase));
    }
    // Reserve and install the promise before invoking user/native code, so an
    // identical concurrent request joins the same bounded operation.
    used += 1;
    phaseUsage[phase] += 1;
    lookups += 1;
    misses += 1;
    let resolvePending, rejectPending;
    const pending = new Promise((resolve, reject) => { resolvePending = resolve; rejectPending = reject; });
    entries.set(key, pending);
    const completeFailure = (error) => { failed += 1; rejectPending(error); };
    const complete = (reply) => {
      let immutable;
      try { immutable = deepFreeze(structuredClone(reply)); }
      catch (error) { completeFailure(error); return; }
      if (immutable?.type === "local_route_result") successful += 1;
      else failed += 1;
      resolvePending(immutable);
    };
    try { Promise.resolve(route({ profile, points: coordinates })).then(complete, completeFailure); }
    catch (error) { completeFailure(error); }
    return pending;
  }

  function snapshot() {
    return deepFreeze({
      budget: {
        phases: Object.fromEntries(Object.entries(limits).map(([phase, limit]) => [phase, {
          used: phaseUsage[phase], limit, remaining: limit - phaseUsage[phase],
          exhausted: phaseUsage[phase] >= limit,
        }])),
        total_used: used, total_limit: totalLimit, total_remaining: totalLimit - used,
        global_exhausted: used >= totalLimit,
      },
      cache: {
        lookup_count: lookups, hit_count: hits, miss_count: misses,
        entry_count: successful + failed, successful_entry_count: successful,
        failed_entry_count: failed, backend_call_count: misses,
        pre_backend_rejection_count: rejected,
      },
      warnings: [], details: {},
    });
  }
  return Object.freeze({ requestRoute, snapshot, get totalUsed() { return used; } });
}

function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  Object.values(value).forEach(deepFreeze);
  return Object.freeze(value);
}
