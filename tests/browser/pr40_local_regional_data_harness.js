import { parseRegionalManifest, regionalBuildIdentity, sha256Bytes, verifyRegionalBytes } from "../../src/sugarglider/web/static/regional_manifest.js";
import { createLocalRegionData, decodeRegionalIndex, eligibleLocalPoi } from "../../src/sugarglider/web/static/local_region_data.js";
import { createLocalRegionStore, loadLocalRegionData } from "../../src/sugarglider/web/static/local_region_store.js";
import { createLocalAutoTourEngine, validateLocalAutoTourRequest } from "../../src/sugarglider/web/static/local_auto_tour.js";
import { createLocalRegionClient } from "../../src/sugarglider/web/static/local_region_client.js";

export async function runPr40LocalRegionalDataHarness() {
  const fixture = await (await fetch("../fixtures/pr40_regional_data.json")).json();
  const scenarios = [];
  const manifest = await parseRegionalManifest(JSON.stringify(fixture.manifest));
  equal(manifest.build_id, fixture.manifest.build_id, "Python/JS canonical manifest identity");
  assert(Object.isFrozen(manifest.components.nature.files), "manifest immutable");
  scenarios.push("python_manifest_identity_and_immutability");

  for (const mutation of [
    (m) => { m.extra = true; }, (m) => { m.components.nature.files[0].path = "../secret"; },
    (m) => { m.components.pois.component_id = m.components.nature.component_id; },
    (m) => { m.bounds[0] = -1; }, (m) => { m.schema_version = 2; },
    (m) => { m.tools.poi_classifier = "old"; }, (m) => { m.source.sha256 = "invalid"; },
    (m) => { m.components.nature.files[0].byte_size = 2 ** 32; },
    (m) => { m.display_name = "changed without updating content identity"; },
  ]) {
    const changed = structuredClone(fixture.manifest); mutation(changed);
    await rejects(() => parseRegionalManifest(JSON.stringify(changed)));
  }
  scenarios.push("strict_manifest_paths_versions_coverage_and_identity");

  const data = createLocalRegionData(manifest, fixture);
  const original = JSON.stringify(fixture.route);
  const analysis = data.analyzeNature(fixture.route);
  assert(analysis.available, "nature analysis available");
  for (const key of ["woodland", "open_natural", "agriculture", "water_crossing", "urban", "unknown_landcover", "park_or_protected", "near_water"]) {
    close(analysis[key].distance_m, fixture.expected[key].distance_m, 1e-5, key);
  }
  close(analysis.nature_score, fixture.expected.nature_score, 1e-6, "shared nature score");
  equal(JSON.stringify(fixture.route), original, "analysis never mutates route");
  scenarios.push("python_nature_golden_holes_priority_multipolygons_overlays");

  const doubled = data.analyzeNature({ ...fixture.route, distance_m: fixture.route.distance_m * 2 });
  for (const key of ["woodland", "urban", "unknown_landcover", "near_water"]) close(doubled[key].distance_m, analysis[key].distance_m * 2, 1e-6, "authoritative distance normalization");
  const partition = ["woodland", "open_natural", "agriculture", "water_crossing", "urban", "unknown_landcover"].reduce((sum, key) => sum + analysis[key].distance_m, 0);
  close(partition, fixture.route.distance_m, 1e-7, "primary classes partition total");
  assert(analysis.warnings.includes("nature_index_route_partly_outside"), "outside bounds visible");
  scenarios.push("normalized_distance_partition_and_outside_unknown");

  const complexNature = structuredClone(fixture.nature);
  const circle = Array.from({ length: 2400 }, (_, index) => {
    const angle = index * 2 * Math.PI / 2400;
    return [.01 + .009 * Math.cos(angle), .01 + .009 * Math.sin(angle)];
  });
  circle.push([...circle[0]]);
  complexNature.features = [{ ...complexNature.features[0], geometry: { type: "Polygon", coordinates: [circle] } }];
  complexNature.metadata.feature_count = 1;
  complexNature.metadata.category_counts = { woodland: 1 };
  const boundedData = createLocalRegionData(manifest, { nature: complexNature });
  const bounded = boundedData.analyzeNature({ ...fixture.route,
    geometry: Array.from({ length: 5000 }, (_, index) => [.01 + (index % 2 ? .001 : -.001), .01]) });
  assert(!bounded.available && bounded.warnings[0] === "nature_analysis_budget_exhausted", "complex analysis fails explicitly at budget");
  equal(bounded.operation_count, bounded.operation_budget, "strict geometry operation budget");
  equal(bounded.unknown_landcover.distance_m, fixture.route.distance_m, "no partial score after budget rejection");
  scenarios.push("expensive_analysis_has_strict_public_budget_and_unknown_failure");

  const missing = createLocalRegionData(manifest).analyzeNature(fixture.route);
  assert(!missing.available && missing.nature_score === null && missing.unknown_landcover.distance_m === fixture.route.distance_m, "missing means unknown");
  const wrongPack = data.analyzeNature({ ...fixture.route, pack_id: "different" });
  assert(!wrongPack.available && wrongPack.warnings[0] === "nature_routing_pack_mismatch", "pack identity enforced");
  scenarios.push("missing_and_wrong_pack_evidence_stays_unknown");

  for (const mutation of [
    (d) => { d.pois.metadata.format_version = 1; },
    (d) => { d.nature.metadata.bounding_box[0] = -1; },
    (d) => { d.pois.features[0].approach_candidates[0].access = "restricted"; },
    (d) => { d.pois.features[0].id = "node/77"; },
    (d) => { d.nature.metadata.category_counts.woodland += 1; },
    (d) => { d.pois.metadata.approach_counts.exact_feature += 1; },
    (d) => { d.nature.features[0].geometry.coordinates[0].pop(); },
    (d) => { d.pois.features[0].coordinate.lat = Infinity; },
    (d) => { d.nature.features[0].geometry.coordinates[0] = [[0, 0], [.01, .015], [0, .02], [.02, 0], [.02, .02], [0, 0]]; },
    (d) => { d.nature.features[3].geometry.coordinates[1] = [[.015, .003], [.018, .003], [.018, .017], [.015, .017], [.015, .003]]; },
  ]) {
    const changed = structuredClone(fixture); mutation(changed);
    await rejects(() => createLocalRegionData(manifest, changed));
  }
  scenarios.push("strict_index_metadata_counts_identity_and_approaches");

  const query = data.queryPois({ center: { lat: .01, lon: .01 }, radius_m: 2000, requested_ids: ["node/1", "node/999"] });
  equal(query.requested.map((item) => item.feature?.id ?? null), ["node/1", null], "stable ID resolution");
  const reasons = Object.fromEntries(query.features.map((feature) => [feature.id, eligibleLocalPoi(feature, manifest.bounds)]));
  equal(reasons["node/1"], null, "scenic eligible");
  equal(reasons["node/2"], null, "verified water eligible");
  equal(reasons["node/3"], "poi_potability_unverified", "unknown is not drinking water");
  equal(reasons["node/4"], "poi_non_potable", "non-potable excluded");
  equal(reasons["node/5"], "poi_access_restricted", "private excluded");
  equal(data.queryPois({ center: { lat: .01, lon: .01 }, radius_m: 2000, limit: 1 }).features.length, 1, "bounded output");
  scenarios.push("local_poi_resolution_potability_access_and_query_bound");

  const download = await downloadable(fixture);
  const decoded = await decodeRegionalIndex(download.files.get("pois/index.json.gz"), download.manifest.components.pois.files[0]);
  equal(decoded, fixture.pois, "unchanged gzip document consumed");
  const damaged = download.files.get("nature/index.json.gz").slice(); damaged[10] ^= 1;
  await rejects(() => verifyRegionalBytes(damaged, download.manifest.components.nature.files[0]), "regional_checksum_mismatch");
  await rejects(() => verifyRegionalBytes(damaged.slice(1), download.manifest.components.nature.files[0]), "regional_size_mismatch");
  scenarios.push("gzip_read_size_and_sha256_verification");

  const memory = memoryStorage();
  const network = fakeDownloads(download);
  const store = createLocalRegionStore({ storage: memory.storage, locks: memory.locks, fetchResource: network.fetch, pageLocation: { href: "https://app.example/" } });
  await store.install("https://packs.example/manifest.json");
  const opened = await store.open("fixture");
  equal(opened.manifest.build_id, download.manifest.build_id, "installed identity");
  equal((await loadLocalRegionData(opened)).identity.poi_count, 5, "reopened local gzip data");
  equal((await store.list())[0].status, "installed", "restart discovery");
  assert(network.requests.every((request) => request.options.credentials === "omit" && request.options.redirect === "error" && request.options.cache === "no-store" && request.options.referrerPolicy === "no-referrer"), "credential-free uncached explicit download");
  scenarios.push("component_install_and_restart_without_duplicate_map_or_graph");

  const next = await downloadable(fixture, "Updated fixture");
  network.current = next;
  network.corrupt = "nature/index.json.gz";
  await rejects(() => store.install("https://packs.example/manifest.json"), "regional_checksum_mismatch");
  equal((await store.open("fixture")).manifest.build_id, download.manifest.build_id, "failed update preserves active");
  network.corrupt = null;
  scenarios.push("checksum_failure_preserves_previous_install");

  const abort = new AbortController();
  await rejects(() => store.install("https://packs.example/manifest.json", { signal: abort.signal,
    onProgress: ({ component }) => { if (component === "nature") abort.abort(); } }));
  equal((await store.open("fixture")).manifest.build_id, download.manifest.build_id, "cancel preserves active");
  scenarios.push("cancelled_update_preserves_previous_install");

  memory.failWrite = "active.json";
  await rejects(() => store.install("https://packs.example/manifest.json"));
  equal((await store.open("fixture")).manifest.build_id, download.manifest.build_id, "failed switch preserves active");
  memory.failWrite = null;
  memory.quota = 1;
  await rejects(() => store.install("https://packs.example/manifest.json"), "regional_insufficient_storage");
  memory.quota = 1e9;
  scenarios.push("activation_failure_and_insufficient_storage_are_explicit");

  await store.install("https://packs.example/manifest.json");
  equal((await store.open("fixture")).manifest.build_id, next.manifest.build_id, "validated update switches");
  await store.remove("fixture");
  equal(await store.list(), [], "explicit removal");
  await rejects(() => store.remove("../escape"), "invalid_region_id");
  scenarios.push("validated_update_and_explicit_removal");

  const request = { start: { lat: .01, lon: .01 }, target_distance_m: 2000, tolerance_m: 500, candidate_count: 3,
    seed: 40, profile: "hike", direction_preference: "any", preferences: { nature: "prefer", scenic: true, water: true, requested_poi_ids: ["node/1", "node/999"] } };
  const requests = [];
  const engine = createLocalAutoTourEngine({ route: async (input) => { requests.push(input); return reply(input); }, getRegionData: async () => data, now: () => 0 });
  const result = await engine.generate(request);
  assert(result.candidates.length > 0, "valid local loops retained");
  equal(result.candidates[0].candidate_id, result.no_poi_control_candidate_id, "no-POI control retained and recommended");
  assert(result.no_poi_control.selected_pois.length === 0, "control has no POI");
  assert(result.candidates.every((candidate) => candidate.nature_analysis.available), "real index enrichment");
  assert(result.route_call_count <= 24 && result.phase_route_calls.poi <= 6, "shared total and separate POI budget");
  equal(result.route_call_count, requests.length, "all native calls accounted");
  equal(result.cache.lookup_count, result.cache.hit_count + result.cache.miss_count, "cache lookup invariant");
  equal(result.cache.entry_count, result.cache.successful_entry_count + result.cache.failed_entry_count, "cache entry invariant");
  assert(result.poi_outcomes.some((outcome) => outcome.poi_id === "node/999" && outcome.reason === "poi_not_found"), "requested absent place explicitly dropped");
  equal(await engine.generate(request), result, "same graph/data/input yields identical complete result");
  scenarios.push("bounded_auto_tour_control_nature_poi_outcomes_and_determinism");

  for (const profile of ["hike", "trail_run", "city_bike", "gravel_bike", "mountain_bike", "road_bike"]) {
    const tour = await createLocalAutoTourEngine({ route: async (input) => { equal(input.profile, profile, "explicit selected profile"); return reply(input); },
      getRegionData: async () => data, routeCallBudget: 1, now: () => 0 }).generate({ ...request, profile });
    assert(tour.route_call_count <= 1 && tour.phase_route_calls.poi === 0, "POIs cannot expand exhausted budget");
    assert(tour.candidates.every((candidate) => candidate.profile === profile), "candidate profile identity");
  }
  scenarios.push("six_profiles_and_exhausted_budget_no_weakened_retry");

  await rejects(() => validateLocalAutoTourRequest({ ...request, preferences: { ...request.preferences, water: "yes" } }));
  const missingResult = await createLocalAutoTourEngine({ route: async (input) => reply(input), now: () => 0 }).generate(request);
  assert(missingResult.preference_status.nature === "unavailable" && missingResult.poi_outcomes.every((outcome) => outcome.status === "dropped"), "missing data truthful");
  scenarios.push("unsupported_preferences_and_missing_data_truth");

  let finish;
  let calls = 0;
  const active = createLocalAutoTourEngine({ route: (input) => { calls += 1; return new Promise((resolve) => { finish = () => resolve(reply(input)); }); }, now: () => 0 });
  const first = active.generate(request);
  active.invalidate();
  const second = active.generate(request);
  equal(calls, 1, "invalidation cannot start overlapping native call");
  assert(first === second, "native operation must drain before restart");
  finish();
  equal(await first, null, "stale generation discarded without correction");
  equal(calls, 1, "no stale correction or POI calls");
  scenarios.push("invalidation_drains_native_work_and_discards_stale_search");

  const messages = [];
  const worker = { postMessage: (message) => messages.push(message), terminate() { this.terminated = true; } };
  const client = createLocalRegionClient({ worker });
  const loading = client.load("fixture");
  worker.onmessage({ data: { id: messages[0].id, result: data.identity } });
  const session = await loading;
  const querying = session.queryPois({ center: request.start, radius_m: 1000 });
  equal(messages[1].value.build_id, data.identity.build_id, "analysis owns loaded version");
  worker.onmessage({ data: { id: messages[1].id, error: "regional_data_unavailable" } });
  await rejects(() => querying, "regional_data_unavailable");
  const outstanding = client.list();
  worker.onerror();
  await rejects(() => outstanding, "regional_worker_unavailable");
  await rejects(() => client.list(), "regional_worker_unavailable");
  assert(worker.terminated, "failed worker does not retain pending operations");
  scenarios.push("worker_version_ownership_and_failure_drains_pending_calls");

  const localNetwork = fakeDownloads(download);
  const realStore = createLocalRegionStore({ fetchResource: localNetwork.fetch });
  const realClient = createLocalRegionClient();
  try {
    await realStore.install("https://packs.example/manifest.json");
    const actualSession = await realClient.load("fixture");
    equal(actualSession.identity.build_id, download.manifest.build_id, "worker reopens actual OPFS version");
    const actualNature = await actualSession.analyzeNature(fixture.route);
    close(actualNature.nature_score, fixture.expected.nature_score, 1e-6, "worker computes independently");
    await realClient.remove("fixture");
    await rejects(() => actualSession.analyzeNature(fixture.route), "regional_data_unavailable");
  } finally {
    realClient.close();
    await realStore.remove("fixture").catch(() => {});
  }
  scenarios.push("real_opfs_module_worker_load_analysis_and_removal");

  return scenarios;
}

function reply(input) {
  return { type: "local_route_result", pack_id: "fixture-routing", profile: input.profile, distance_m: 2000, duration_s: 1000,
    geometry: input.points.map(({ lon, lat }) => [lon, lat]), snapped_points: input.points.map((point) => ({ ...point })), measurements: null };
}

async function downloadable(fixture, displayName = fixture.manifest.display_name) {
  const manifest = structuredClone(fixture.manifest);
  manifest.display_name = displayName;
  const files = new Map();
  for (const kind of ["pois", "nature"]) {
    const compressed = new Blob([JSON.stringify(fixture[kind])]).stream().pipeThrough(new CompressionStream("gzip"));
    const bytes = new Uint8Array(await new Response(compressed).arrayBuffer());
    const descriptor = manifest.components[kind].files[0];
    descriptor.byte_size = bytes.byteLength; descriptor.sha256 = await sha256Bytes(bytes);
    files.set(descriptor.path, bytes);
  }
  manifest.build_id = await regionalBuildIdentity(manifest);
  files.set("manifest.json", new TextEncoder().encode(JSON.stringify(manifest)));
  return { manifest, files };
}

function fakeDownloads(current) {
  const fake = { current, corrupt: null, requests: [] };
  fake.fetch = async (url, options) => {
    fake.requests.push({ url, options });
    options.signal?.throwIfAborted();
    const path = new URL(url).pathname.slice(1);
    let bytes = fake.current.files.get(path);
    assert(bytes, "no map, routing, hosted discovery or backend request");
    if (fake.corrupt === path) { bytes = bytes.slice(); bytes[10] ^= 1; }
    return new Response(bytes);
  };
  return fake;
}

function memoryStorage() {
  const memory = { failWrite: null, quota: 1e9 };
  const missing = () => new DOMException("missing", "NotFoundError");
  function directory() {
    const children = new Map();
    return { kind: "directory", entries: async function* () { yield* children.entries(); },
      async getDirectoryHandle(name, { create = false } = {}) {
        if (!children.has(name) && create) children.set(name, directory());
        const handle = children.get(name); if (!handle || handle.kind !== "directory") throw missing(); return handle;
      },
      async getFileHandle(name, { create = false } = {}) {
        if (!children.has(name) && create) {
          let committed = new Blob([]);
          children.set(name, { kind: "file", getFile: async () => committed,
            createWritable: async () => {
              let next;
              return { write: async (data) => { next = new Blob([data]); }, close: async () => {
                if (memory.failWrite === name) throw new Error("write failed"); committed = next;
              }, abort: async () => {} };
            } });
        }
        const handle = children.get(name); if (!handle || handle.kind !== "file") throw missing(); return handle;
      },
      async removeEntry(name) { if (!children.delete(name)) throw missing(); },
    };
  }
  const root = directory();
  memory.storage = { getDirectory: async () => root, estimate: async () => ({ usage: 0, quota: memory.quota }) };
  memory.locks = { request: async (name, action) => action() };
  return memory;
}

function assert(condition, label) { if (!condition) throw new Error(label); }
function equal(actual, expected, label) { assert(JSON.stringify(actual) === JSON.stringify(expected), `${label}: ${JSON.stringify(actual)} !== ${JSON.stringify(expected)}`); }
function close(actual, expected, tolerance, label) { assert(Math.abs(actual - expected) <= tolerance, `${label}: ${actual} != ${expected}`); }
async function rejects(action, code = null) {
  try { await action(); } catch (error) { if (code) equal(error.code, code, "failure code"); return; }
  throw new Error(`Expected rejection ${code ?? ""}`);
}
