import { createLocalRegionData, createLocalPlacesSession } from "../../src/sugarglider/web/static/local_region_data.js";
import { createLocalRegionStore } from "../../src/sugarglider/web/static/local_region_store.js";
import { createLocalRegionClient } from "../../src/sugarglider/web/static/local_region_client.js";
import { regionalBuildIdentity, sha256Bytes } from "../../src/sugarglider/web/static/regional_manifest.js";
import { scanNatureReference } from "./nature_scan_reference.js";
import { NATURE_PERFORMANCE_CASES, naturePerformanceFixture } from "./nature_performance_fixtures.js";

const assert = (value, message) => { if (!value) throw Error(message); };
const equal = (actual, expected, message) => assert(JSON.stringify(actual) === JSON.stringify(expected), message);
const primary = ["woodland", "open_natural", "agriculture", "water_crossing", "urban", "unknown_landcover"];

export async function runNaturePerformanceHarness() {
  const base = await (await fetch("../fixtures/pr40_regional_data.json")).json();
  const scenarios = [];
  for (const name of NATURE_PERFORMANCE_CASES) {
    const f = naturePerformanceFixture(base, name), data = createLocalRegionData(f.manifest, { nature: f.nature });
    const before = JSON.stringify(f.route), actual = data.analyzeNature(f.route);
    const reference = scanNatureReference(f.manifest, f.nature, f.route, data.identity);
    const fields = [...primary, "park_or_protected", "near_water", "nature_score", "score_components", "warnings"];
    assert(reference.available, `${name}: original reference completes within its unchanged budget`);
    const expected = Object.fromEntries(fields.map(key => [key, reference[key]]));
    assert(actual.available, `${name}: available`);
    equal(Object.fromEntries(Object.keys(expected).map(key => [key, actual[key]])), expected, `${name}: exact original full-scan golden`);
    equal(data.analyzeNature(f.route), actual, `${name}: deterministic operation count and output`);
    equal(JSON.stringify(f.route), before, `${name}: routed geometry unchanged`);
    assert(actual.operation_budget === 4_000_000 && actual.operation_count <= actual.operation_budget, `${name}: bounded`);
    assert(Math.abs(primary.reduce((total, key) => total + actual[key].distance_m, 0) - f.route.distance_m) < 1e-7, `${name}: partition`);
    scenarios.push(`full_scan_golden_${name}`);
  }

  const f = naturePerformanceFixture(base, "complex_water");
  const data = createLocalRegionData(f.manifest, { nature: f.nature });
  for (const geometry of [[], [[0, 0]], [[0, 0], [Infinity, 0]], [[0, 0], [0, NaN]],
    [[0, 0], [181, 0]], Array.from({ length: 20_001 }, () => [0, 0])]) {
    await rejects(() => data.analyzeNature({ ...f.route, geometry }), "invalid_routed_geometry");
  }
  const degenerate = data.analyzeNature({ ...f.route, geometry: [[.01, .01], [.01, .01]] });
  assert(!degenerate.available && degenerate.nature_score === null && degenerate.unknown_landcover.distance_m === f.route.distance_m, "zero-length route remains unknown");
  const malformed = naturePerformanceFixture(base, "complex_water");
  const ring = malformed.nature.features[0].geometry.coordinates[0];
  [ring[30], ring[1200]] = [ring[1200], ring[30]];
  await rejects(() => createLocalRegionData(malformed.manifest, { nature: malformed.nature }), "invalid_nature_polygon");
  scenarios.push("malformed_routes_and_indexed_polygon_topology_still_rejected");

  // Many overlapping polygons force meaningful work even after boundary pruning.
  // The public limit must stop the whole analysis, with no partial score.
  const stress = naturePerformanceFixture(base, "following_boundary");
  const template = stress.nature.features[0];
  stress.nature.features = Array.from({ length: 512 }, (_, index) => ({ ...structuredClone(template),
    feature_id: `way/${index + 1}`, osm_id: index + 1 }));
  stress.nature.features.sort((a, b) => a.feature_id < b.feature_id ? -1 : 1);
  stress.nature.metadata.feature_count = 512;
  stress.nature.metadata.category_counts = { woodland: 512, park_or_protected: 512 };
  stress.route.geometry = Array.from({ length: 20_000 }, (_, i) => [i % 2 ? .019 : .001, .01]);
  const bounded = createLocalRegionData(stress.manifest, { nature: stress.nature }).analyzeNature(stress.route);
  assert(!bounded.available && bounded.warnings[0] === "nature_analysis_budget_exhausted", "pathological work rejected");
  equal(bounded.operation_count, 4_000_000, "strict unchanged operation limit");
  assert(bounded.nature_score === null && bounded.unknown_landcover.distance_m === stress.route.distance_m
    && bounded.near_water === null && bounded.park_or_protected === null, "no invented partial result");
  scenarios.push("pathological_overlap_is_bounded_and_fails_closed");

  await workerLifecycle(base, scenarios);
  // The acceptance runner collects outside this stack, not during normal tests.
  window.createNatureIndexRetentionProbe = () => {
    const fixture = naturePerformanceFixture(base, "complex_water");
    const full = createLocalRegionData(fixture.manifest, { nature: fixture.nature, pois: structuredClone(base.pois) });
    window.retainedNatureIndexOwner = new WeakRef(full);
    window.retainedNatureIndexDocument = new WeakRef(fixture.nature);
    window.retainedNaturePlaces = createLocalPlacesSession(full);
    return full.searchPlaceNames("castle");
  };
  window.createNatureSourceReleaseProbe = () => {
    const fixture = naturePerformanceFixture(base, "complex_water");
    window.activeNatureAnalysis = createLocalRegionData(fixture.manifest, { nature: fixture.nature });
    window.activeNatureInput = new WeakRef(fixture.nature);
    window.activeNatureRoute = fixture.route;
    return window.activeNatureAnalysis.analyzeNature(fixture.route);
  };
  return scenarios;
}

async function workerLifecycle(base, scenarios) {
  const first = naturePerformanceFixture(base, "complex_water");
  let download = await downloadable(base, first, "First synthetic indexed region");
  const store = createLocalRegionStore({ fetchResource: async url => {
    const path = new URL(url).pathname.slice(1), bytes = download.files.get(path);
    assert(bytes, "only synthetic index downloads");
    return new Response(bytes);
  } });
  let client = createLocalRegionClient();
  try {
    await store.install("https://packs.example/manifest.json");
    let session = await client.load("fixture");
    const initial = await session.analyzeNature(first.route);
    assert(initial.available, "actual worker boundary index available");
    const pending = session.analyzeNature(first.route);
    client.close();
    await rejects(() => pending, "regional_worker_unavailable");
    client = createLocalRegionClient();
    session = await client.load("fixture");
    equal(await session.analyzeNature(first.route), initial, "worker restart rebuilds same index and analysis");
    const second = naturePerformanceFixture(base, "holes");
    download = await downloadable(base, second, "Second synthetic indexed region");
    await store.install("https://packs.example/manifest.json");
    const switched = await client.load("fixture");
    assert(switched.identity.build_id !== session.identity.build_id, "worker owns switched identity");
    await rejects(() => session.analyzeNature(first.route), "regional_data_unavailable");
    const next = await switched.analyzeNature(second.route);
    assert(next.available, "switched region analyzed");
    equal(next.woodland, createLocalRegionData(second.manifest, { nature: second.nature }).analyzeNature(second.route).woodland,
      "switched region uses its own boundary data");
    await client.remove("fixture");
    await rejects(() => switched.analyzeNature(second.route), "regional_data_unavailable");
    scenarios.push("real_worker_analysis_close_cancellation_restart_switch_and_removal");
  } finally {
    client.close();
    await store.remove("fixture").catch(() => {});
  }
}

async function downloadable(base, fixture, displayName) {
  const manifest = structuredClone(base.manifest), files = new Map();
  manifest.display_name = displayName;
  for (const [kind, document] of [["nature", fixture.nature], ["pois", base.pois]]) {
    const bytes = new Uint8Array(await new Response(new Blob([JSON.stringify(document)]).stream()
      .pipeThrough(new CompressionStream("gzip"))).arrayBuffer());
    const descriptor = manifest.components[kind].files[0];
    descriptor.byte_size = bytes.length; descriptor.sha256 = await sha256Bytes(bytes);
    files.set(descriptor.path, bytes);
  }
  manifest.build_id = await regionalBuildIdentity(manifest);
  files.set("manifest.json", new TextEncoder().encode(JSON.stringify(manifest)));
  return { files };
}

async function rejects(action, code) {
  try { await action(); } catch (error) { assert(error.code === code, `expected ${code}, received ${error.code}`); return; }
  throw Error(`Expected rejection: ${code}`);
}
