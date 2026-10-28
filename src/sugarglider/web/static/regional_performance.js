// Opt-in, bounded timing evidence. Never accepts arbitrary labels or payloads.
const stages = new Set(["partition_read", "hash_verification", "decompression", "json_parse",
  "partition_validation", "topology_projection", "spatial_index", "nature_intersection", "nature_scoring"]);
const counters = new Set(["partition_reads", "prepared_partitions", "cache_hits", "resident_partitions", "resident_positions"]);
const events = new Set(["native_route_complete", "refinement_model_started"]);
const limit = 128;
let enabled = false, active = null, dropped = 0, generation = 0;
const records = [];
export const regionalClock = () => performance.timeOrigin + performance.now();
const heap = () => performance.memory?.usedJSHeapSize ?? null;
const number = value => typeof value === "number" && Number.isFinite(value) && value >= 0;

export function enableRegionalProfiling(value = true) {
  generation++;
  enabled = value === true; records.length = 0; dropped = 0;
}
export const regionalProfilingEnabled = () => enabled;
export const regionalProfilingGeneration = () => enabled ? generation : null;
function retain(record) {
  if (records.length === limit) { records.shift(); dropped++; }
  records.push(record);
}
export const regionalPerformanceSnapshot = () => structuredClone({ schema_version: 1, dropped, records });
export function recordRegionalEvent(stage, wallMs = 0) {
  if (enabled && events.has(stage) && number(wallMs)) retain({ stage, at_ms: regionalClock(), wall_ms: wallMs });
}
export function beginRegionalProfile(capture, received = regionalClock()) {
  active = capture ? { received_ms: received, started_ms: regionalClock(), heap_start_bytes: heap(), stages: {}, counters: {} } : null;
}
export function finishRegionalProfile() {
  const result = active;
  active = null;
  return result ? { ...result, finished_ms: regionalClock(), heap_end_bytes: heap() } : null;
}
export function regionalCount(key, amount = 1, replace = false) {
  if (active && counters.has(key) && Number.isSafeInteger(amount) && amount >= 0) {
    active.counters[key] = replace ? amount : (active.counters[key] ?? 0) + amount;
  }
}
function elapsed(scope, stage, start) {
  if (!scope || !stages.has(stage)) return;
  const metric = scope.stages[stage] ??= { calls: 0, wall_ms: 0 };
  metric.calls++; metric.wall_ms += performance.now() - start;
}
export function regionalMeasure(stage, work) {
  const scope = active, start = scope ? performance.now() : 0;
  try { return work(); } finally { elapsed(scope, stage, start); }
}
export async function regionalMeasureAsync(stage, work) {
  const scope = active, start = scope ? performance.now() : 0;
  try { return await work(); } finally { elapsed(scope, stage, start); }
}
export function recordWorkerProfile(value, submitted, captureGeneration, received = regionalClock()) {
  if (!enabled || captureGeneration !== generation || !value
    || ![submitted, received, value.received_ms, value.started_ms, value.finished_ms].every(number)) return;
  const result = { submission_ms: Math.max(0, value.received_ms - submitted),
    queue_wait_ms: Math.max(0, value.started_ms - value.received_ms),
    worker_wall_ms: Math.max(0, value.finished_ms - value.started_ms),
    delivery_ms: Math.max(0, received - value.finished_ms),
    started_ms: value.started_ms, finished_ms: value.finished_ms, stages: {}, counters: {},
    heap_start_bytes: number(value.heap_start_bytes) ? value.heap_start_bytes : null,
    heap_end_bytes: number(value.heap_end_bytes) ? value.heap_end_bytes : null };
  for (const key of stages) {
    const metric = value.stages?.[key];
    if (Number.isSafeInteger(metric?.calls) && metric.calls >= 0 && number(metric.wall_ms)) {
      result.stages[key] = { calls: metric.calls, wall_ms: metric.wall_ms };
    }
  }
  for (const key of counters) {
    const count = value.counters?.[key];
    if (Number.isSafeInteger(count) && count >= 0) result.counters[key] = count;
  }
  retain(result);
}
