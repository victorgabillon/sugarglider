import { createLocalRegionData } from "../../src/sugarglider/web/static/local_region_data.js";
import { createLocalRegionStore, loadLocalRegionData } from "../../src/sugarglider/web/static/local_region_store.js";
import { createLocalRegionClient } from "../../src/sugarglider/web/static/local_region_client.js";
import { createPartitionedRegionData, decodeNatureDirectory, decodeNaturePartition } from "../../src/sugarglider/web/static/nature_partitions.js";
import { parseRegionalManifest, regionalBuildIdentity, sha256Bytes } from "../../src/sugarglider/web/static/regional_manifest.js";
import { selectCommittedRegion } from "../../src/sugarglider/web/static/regional_planning.js";
import { NATURE_PERFORMANCE_CASES, naturePerformanceFixture } from "./nature_performance_fixtures.js";
import { beginRegionalProfile, finishRegionalProfile, enableRegionalProfiling,
  recordWorkerProfile, regionalPerformanceSnapshot, regionalProfilingGeneration } from "../../src/sugarglider/web/static/regional_performance.js";

const assert = (value, message) => { if (!value) throw Error(message); };
const metrics = ["available", "method", "woodland", "open_natural", "agriculture", "water_crossing", "urban",
  "unknown_landcover", "park_or_protected", "near_water", "nature_score", "score_components", "warnings"];
const equal = (a, b, message) => assert(JSON.stringify(a) === JSON.stringify(b), message);
async function rejects(run, code) {
  try { await run(); } catch (error) { assert(!code || error.code === code, `${code}: ${error.stack}`); return; }
  throw Error(`Expected rejection: ${code}`);
}

export async function runNaturePartitionsHarness() {
  const base = await (await fetch("../fixtures/pr40_regional_data.json")).json();
  const scenarios = [];
  for (const name of NATURE_PERFORMANCE_CASES) {
    const f = naturePerformanceFixture(base, name);
    const artifact = await partitionFixture(f);
    const directory = await decodeNatureDirectory(artifact.files.get("nature/partitions.json"), artifact.manifest);
    let reads = 0;
    const data = createPartitionedRegionData(artifact.manifest, null, directory, async descriptor => {
      reads++; return artifact.files.get(descriptor.path);
    });
    const before = JSON.stringify(f.route);
    const actual = await data.analyzeNature(f.route), expected = createLocalRegionData(f.manifest, { nature: f.nature }).analyzeNature(f.route);
    for (const key of metrics) equal(actual[key], expected[key], `${name}: ${key}`);
    assert(actual.operation_count <= 4_000_000 && actual.operation_budget === 4_000_000, `${name}: shared budget`);
    equal(await data.queryWoodlandPoints({ points: [{ lon: .01, lat: .01 }, { lon: .025, lat: .01 }] }).then(r => r.woodland),
      createLocalRegionData(f.manifest, { nature: f.nature }).queryWoodlandPoints({ points: [{ lon: .01, lat: .01 }, { lon: .025, lat: .01 }] }).woodland,
      `${name}: shared proposal guidance`);
    equal(JSON.stringify(f.route), before, `${name}: immutable geometry`);
    assert(reads > 0, `${name}: genuine bounded reads`);
    scenarios.push(`partitioned_monolithic_parity_${name}`);
  }
  const f = naturePerformanceFixture(base, "priority_overlays"), artifact = await partitionFixture(f);
  const manifest = await parseRegionalManifest(JSON.stringify(artifact.manifest));
  const directory = await decodeNatureDirectory(artifact.files.get("nature/partitions.json"), manifest);
  // One immutable session reuses preparation, but never trusts a cached tree
  // after its backing bytes change. Every failure discards the entire score.
  const one = naturePerformanceFixture(base, "holes"), oneArtifact = await partitionFixture(one);
  const oneDirectory = await decodeNatureDirectory(oneArtifact.files.get("nature/partitions.json"), oneArtifact.manifest);
  const oneData = createPartitionedRegionData(oneArtifact.manifest, null, oneDirectory,
    async descriptor => oneArtifact.files.get(descriptor.path));
  beginRegionalProfile(true);
  const firstAnalysis = await oneData.analyzeNature(one.route), cold = finishRegionalProfile();
  beginRegionalProfile(true);
  equal(await oneData.analyzeNature(one.route), firstAnalysis, "cached preparation preserves every metric and operation count");
  const warm = finishRegionalProfile();
  assert(cold.counters.prepared_partitions === 1 && warm.counters.cache_hits === 1
    && !warm.counters.prepared_partitions && warm.stages.hash_verification.calls === 1,
    "warm analysis skips preparation but checks exact immutable bytes");
  const originalByte = oneArtifact.files.get(oneDirectory.partitions[0].path)[10];
  oneArtifact.files.get(oneDirectory.partitions[0].path)[10] ^= 1;
  const cachedCorruption = await oneData.analyzeNature(one.route);
  assert(!cachedCorruption.available && cachedCorruption.nature_score === null
    && cachedCorruption.unknown_landcover.distance_m === one.route.distance_m, "corruption after a cache hit cannot return a stale score");
  oneArtifact.files.get(oneDirectory.partitions[0].path)[10] = originalByte;
  equal(await oneData.analyzeNature(one.route), firstAnalysis, "failed analysis cannot poison the following operation");
  scenarios.push("cached_partition_reverified_and_exact_after_failure");

  for (const cachePositions of [1_500_000, Math.max(...directory.partitions.map(part => part.position_count))]) {
    const bounded = createPartitionedRegionData(manifest, null, directory,
      async descriptor => artifact.files.get(descriptor.path), { cachePositions });
    beginRegionalProfile(true);
    const analyses = await Promise.all([bounded.analyzeNature(f.route), bounded.analyzeNature(f.route)]);
    const profile = finishRegionalProfile();
    equal(analyses[0], analyses[1], "concurrent callers retain deterministic interval arithmetic");
    assert(profile.counters.resident_partitions <= 4 && profile.counters.resident_positions <= cachePositions,
      "both count and geometry-position limits remain bounded");
    equal(analyses[0], await createPartitionedRegionData(manifest, null, directory,
      async descriptor => artifact.files.get(descriptor.path), { cachePartitions: 1 }).analyzeNature(f.route),
    "bounded LRU eviction never changes the global operation budget or result");
  }
  scenarios.push("bounded_cache_eviction_and_concurrent_result_equivalence");
  enableRegionalProfiling();
  const captureGeneration = regionalProfilingGeneration();
  recordWorkerProfile({ ...warm, user_description: "must not escape", token: "secret", stages: {
    ...warm.stages, coordinates: { calls: 1, wall_ms: 1 } } }, warm.received_ms, captureGeneration);
  for (let index = 0; index < 140; index++) recordWorkerProfile(warm, warm.received_ms, captureGeneration);
  const snapshot = regionalPerformanceSnapshot();
  assert(snapshot.records.length === 128 && snapshot.dropped === 13
    && !JSON.stringify(snapshot).includes("secret") && !JSON.stringify(snapshot).includes("coordinates")
    && !JSON.stringify(snapshot).includes("must not escape"), "profiling has fixed fields and bounded retention");
  enableRegionalProfiling(false);
  scenarios.push("performance_evidence_is_bounded_and_has_no_private_payloads");
  let submitted;
  const delayedWorker = { postMessage: message => { submitted = message; }, terminate() {} };
  const delayedClient = createLocalRegionClient({ worker: delayedWorker });
  try {
    enableRegionalProfiling();
    const previous = delayedClient.list();
    enableRegionalProfiling(false);
    enableRegionalProfiling();
    delayedWorker.onmessage({ data: { id: submitted.id, result: ["previous result"], profile: warm } });
    equal(await previous, ["previous result"], "capture changes never suppress actual operation results");
    assert(regionalPerformanceSnapshot().records.length === 0, "late previous capture cannot contaminate a new session");
    const current = delayedClient.list();
    delayedWorker.onmessage({ data: { id: submitted.id, result: ["current result"], profile: warm } });
    equal(await current, ["current result"], "current result delivery remains intact");
    assert(regionalPerformanceSnapshot().records.length === 1, "the current profiling generation remains observable");
  } finally { delayedClient.close(); enableRegionalProfiling(false); }
  scenarios.push("late_worker_profile_is_scoped_without_dropping_its_result");
  const corrupted = new Uint8Array(artifact.files.get(directory.partitions[0].path)); corrupted[10] ^= 1;
  const data = createPartitionedRegionData(manifest, null, directory, async descriptor => descriptor.path === directory.partitions[0].path ? corrupted : artifact.files.get(descriptor.path));
  const unavailable = await data.analyzeNature(f.route);
  assert(!unavailable.available && unavailable.nature_score === null && unavailable.unknown_landcover.distance_m === f.route.distance_m,
    "one corrupt partition leaves the entire analysis visibly unknown");
  scenarios.push("corrupt_partition_has_no_partial_score");
  const wrongBounds = structuredClone(directory.partitions[0]); wrongBounds.bounds[0] -= .001;
  await rejects(() => decodeNaturePartition(artifact.files.get(wrongBounds.path), manifest.components.nature.files[1], wrongBounds, directory, manifest));
  scenarios.push("false_pruning_bounds_rejected");
  const healthy = createPartitionedRegionData(manifest, null, directory, async descriptor => artifact.files.get(descriptor.path));
  const degenerate = await healthy.analyzeNature({ ...f.route, geometry: [[.01, .01], [.01, .01]] });
  assert(!degenerate.available && degenerate.warnings[0] === "nature_degenerate_geometry", "degenerate routed distance stays unknown");
  const stress = await healthy.analyzeNature({ ...f.route,
    geometry: Array.from({ length: 10_000 }, (_, index) => [index % 2 ? .019 : .001, .01]) });
  assert(!stress.available && stress.operation_count === 4_000_000 && stress.nature_score === null,
    "all partitions share one unchanged strict analysis budget");
  scenarios.push("global_analysis_budget_and_degenerate_geometry_remain_unknown");
  const oversized = new Uint8Array(await new Response(new Blob([" ".repeat(16 * 1024 * 1024 + 1)]).stream()
    .pipeThrough(new CompressionStream("gzip"))).arrayBuffer());
  const oversizedDescriptor = { byte_size: oversized.length, sha256: await sha256Bytes(oversized) };
  await rejects(() => decodeNaturePartition(oversized, oversizedDescriptor, directory.partitions[0], directory, manifest), "regional_index_too_large");
  scenarios.push("partition_decompression_stops_at_16_mib");

  const locks = { request: async (_name, action) => action() };
  let missing = null;
  const store = createLocalRegionStore({ locks, pageLocation: location, fetchResource: async url => {
    const path = new URL(url).pathname.replace("/fixture/", "");
    return path === missing ? new Response(null, { status: 404 }) : new Response(path === "manifest.json"
      ? JSON.stringify(manifest) : artifact.files.get(path));
  } });
  await store.install(`${location.origin}/fixture/manifest.json`);
  const opened = await store.open(manifest.region_id), installed = await loadLocalRegionData(opened);
  assert((await installed.analyzeNature(f.route)).available, "real OPFS partitioned install and query");
  enableRegionalProfiling();
  const client = createLocalRegionClient();
  try {
    const workerSession = await client.load(manifest.region_id);
    equal(await workerSession.analyzeNature(f.route), await installed.analyzeNature(f.route),
      "production worker/client profiling preserves canonical Nature output");
    const captured = regionalPerformanceSnapshot().records;
    assert(captured.some(record => record.stages?.nature_intersection?.calls > 0
      && Number.isFinite(record.queue_wait_ms) && Number.isFinite(record.delivery_ms)),
    "production transport captures worker queue, kernel and delivery timing");
  } finally { client.close(); enableRegionalProfiling(false); }
  scenarios.push("real_worker_profiling_and_opfs_result_equivalence");
  const next = structuredClone(manifest); next.display_name += " next"; next.build_id = await regionalBuildIdentity(next);
  const failing = createLocalRegionStore({ locks, pageLocation: location, fetchResource: async url => {
    const path = new URL(url).pathname.replace("/fixture/", "");
    return path === missing ? new Response(null, { status: 404 }) : new Response(path === "manifest.json"
      ? JSON.stringify(next) : artifact.files.get(path));
  } });
  missing = directory.partitions.at(-1).path;
  await rejects(() => failing.install(`${location.origin}/fixture/manifest.json`), "regional_download_failed");
  equal((await store.open(manifest.region_id)).manifest.build_id, manifest.build_id, "failed final shard preserves committed build");
  scenarios.push("real_opfs_commit_and_failed_update_preservation");

  const corruptUpdate = createLocalRegionStore({ locks, pageLocation: location, fetchResource: async url => {
    const path = new URL(url).pathname.replace("/fixture/", "");
    return new Response(path === "manifest.json" ? JSON.stringify(next)
      : path === directory.partitions[0].path ? corrupted : artifact.files.get(path));
  } });
  await rejects(() => corruptUpdate.install(`${location.origin}/fixture/manifest.json`), "regional_checksum_mismatch");
  equal((await store.open(manifest.region_id)).manifest.build_id, manifest.build_id, "corrupt update cannot replace the complete active build");
  const incomplete = structuredClone(manifest); incomplete.region_id = "incomplete-partition-test";
  incomplete.build_id = await regionalBuildIdentity(incomplete);
  const firstInstall = createLocalRegionStore({ locks, pageLocation: location, fetchResource: async url => {
    const path = new URL(url).pathname.replace("/fixture/", "");
    return path === directory.partitions.at(-1).path ? new Response(null, { status: 404 })
      : new Response(path === "manifest.json" ? JSON.stringify(incomplete) : artifact.files.get(path));
  } });
  await rejects(() => firstInstall.install(`${location.origin}/fixture/manifest.json`), "regional_download_failed");
  await rejects(() => firstInstall.open(incomplete.region_id));
  scenarios.push("corrupt_update_and_incomplete_first_install_never_activate");

  const row = (id, bounds) => ({ region_id: id, status: "committed", manifest: { bounds } });
  const rows = [row("lot", [0.9, 44.4, 1.3, 44.6]), row("marly", [2, 48.85, 2.2, 48.95]),
    row("idf", [1.445097, 48.11918, 3.560409, 49.24271])];
  for (const [name, lon, lat] of [["Paris", 2.3488, 48.853], ["Bastille", 2.36909, 48.85315],
    ["Fontainebleau", 2.6987, 48.403], ["Meaux", 2.8791, 48.96], ["Versailles", 2.1301, 48.8048]]) {
    equal(selectCommittedRegion(rows, "lot", { start: { lon, lat } }).region_id, "idf", `${name}: automatic complete-region selection`);
  }
  equal(selectCommittedRegion(rows, "lot", { start: { lon: 2.369, lat: 48.853 } }).region_id, "idf", "Paris selects complete IDF");
  equal(selectCommittedRegion(rows, "marly", { start: { lon: 2.1, lat: 48.87 } }).region_id, "marly", "covering preference preserved");
  equal(selectCommittedRegion(rows, "marly", { start: { lon: 2.1, lat: 48.87 }, end: { lon: 2.88, lat: 48.96 } }).region_id, "idf", "cross-boundary route chooses one continuous graph");
  equal(selectCommittedRegion(rows, "idf", { start: { lon: 1.137, lat: 44.504 } }).region_id, "lot", "Lot remains independent");
  await rejects(() => selectCommittedRegion(rows, "idf", { start: { lon: 2.1, lat: 48.87 }, end: { lon: 1.137, lat: 44.504 } }), "no_covering_routing_pack");
  equal(selectCommittedRegion(rows, "marly", { start: { lon: 2.1, lat: 48.87 }, waypoints: [{ coordinate: { lon: 1.137, lat: 44.504 }, constraint_strength: "approach" }] }).region_id,
    "marly", "an uncovered optional soft stop must not reject a covered plan");
  scenarios.push("automatic_coverage_preserves_preference_and_never_stitches_graphs");
  return scenarios;
}

async function partitionFixture(fixture) {
  const manifest = structuredClone(fixture.manifest), files = new Map(), partitions = [];
  const groups = fixture.nature.features.length > 64 ? [fixture.nature.features.slice(0, 128), fixture.nature.features.slice(128)]
    : fixture.nature.features.map(feature => [feature]);
  const descriptors = [];
  for (const features of groups.filter(group => group.length)) {
    const index = partitions.length, path = `nature/part-${String(index).padStart(3, "0")}.json.gz`;
    const document = { metadata: { ...fixture.nature.metadata, feature_count: features.length, category_counts: {} }, features };
    const bounds = [Infinity, Infinity, -Infinity, -Infinity]; let positions = 0;
    for (const feature of features) {
      for (const key of [feature.primary_class, feature.park_or_protected ? "park_or_protected" : null]) {
        if (key !== null) document.metadata.category_counts[key] = (document.metadata.category_counts[key] ?? 0) + 1;
      }
      const polygons = feature.geometry.type === "Polygon" ? [feature.geometry.coordinates] : feature.geometry.coordinates;
      for (const polygon of polygons) for (const ring of polygon) for (const [lon, lat] of ring) {
        positions++; bounds[0] = Math.min(bounds[0], lon); bounds[1] = Math.min(bounds[1], lat);
        bounds[2] = Math.max(bounds[2], lon); bounds[3] = Math.max(bounds[3], lat);
      }
    }
    const bytes = new Uint8Array(await new Response(new Blob([JSON.stringify(document)]).stream().pipeThrough(new CompressionStream("gzip"))).arrayBuffer());
    files.set(path, bytes);
    descriptors.push({ path, format: "nature-index-v1-gzip-json", byte_size: bytes.byteLength, sha256: await sha256Bytes(bytes) });
    partitions.push({ path, bounds, feature_count: features.length, position_count: positions });
  }
  const directory = { schema_version: 1, source_sha256: manifest.source.sha256, source_basename: manifest.source.basename,
    source_size_bytes: manifest.source.byte_size, bounds: manifest.bounds, reference_latitude: fixture.nature.metadata.reference_latitude,
    feature_count: fixture.nature.features.length, position_count: partitions.reduce((sum, p) => sum + p.position_count, 0), partitions };
  const bytes = new TextEncoder().encode(JSON.stringify(directory)); files.set("nature/partitions.json", bytes);
  manifest.components.nature.files = [{ path: "nature/partitions.json", format: "nature-partitions-v1-json", byte_size: bytes.length, sha256: await sha256Bytes(bytes) }, ...descriptors];
  // The real store also requires the unchanged valid Places component.
  const base = await (await fetch("../fixtures/pr40_regional_data.json")).json();
  const pois = new Uint8Array(await new Response(new Blob([JSON.stringify(base.pois)]).stream().pipeThrough(new CompressionStream("gzip"))).arrayBuffer());
  files.set("pois/index.json.gz", pois);
  manifest.components.pois.files[0] = { ...manifest.components.pois.files[0], byte_size: pois.length, sha256: await sha256Bytes(pois) };
  manifest.build_id = await regionalBuildIdentity(manifest);
  return { manifest, files };
}
