// All geography and native replies in this suite are explicitly synthetic.
// Production search, gateway, publication worker, Nature and GPX are exercised.
import { createLocalPlanner } from "../../src/sugarglider/web/static/local_planner.js";
import { createLocalRegionData } from "../../src/sugarglider/web/static/local_region_data.js";
import { exportCanonicalCandidate } from "../../src/sugarglider/web/static/local_gpx_export.js";
import { haversineDistance } from "../../src/sugarglider/web/static/local_plan_geometry.js";
import { PUBLIC_PROFILE_METADATA } from "../../src/sugarglider/web/static/public_profile_metadata.js";
import { syntheticRegionalReference } from "./regional_routing_fixture.js";

const profiles = Object.keys(PUBLIC_PROFILE_METADATA);
const assert = (value, message) => { if (!value) throw Error(message); };
const equal = (a, b, message) => assert(JSON.stringify(a) === JSON.stringify(b), `${message}: ${JSON.stringify(a)}`);
const point = (lat, lon, name = null) => ({ lat, lon, name });
const position = p => [p.lon, p.lat];
const samePoint = (a, b) => Math.abs(a.lat - b.lat) < 1e-10 && Math.abs(a.lon - b.lon) < 1e-10;
export const samples = [];

function fixture(loop = false, profile = "trail_run") {
  const target = (id, lat, lon, priority = 5) => ({ id, name: id, category: "castle", importance: "prefer", priority,
    status: "grounded", access_status: "unknown", semantic_coordinate: point(lat, lon),
    approach: { id: `${id}/entrance`, coordinate: point(lat, lon), kind: "mapped_entrance", source: "osm_entrance",
      access: "unknown", semantic_distance_m: 0, graph_snap_distance_m: null, arrival_tolerance_m: 25,
      name: null, osm_type: null, osm_id: null, provenance: "feature_geometry", warnings: [] } });
  const targets = [target("near-a", .006, .006, 9), target("near-b", .012, .008, 8),
    target("unreachable", .007, .007, 10), target("detour", .018, .019, 7), target("outside", .023, .023, 6)];
  const request = { schema_version: 1, kind: "waypoint_route", name: "Synthetic adventure", topology: loop ? "loop" : "point_to_point",
    start: point(.005, .005, "Start"), end: loop ? null : point(.015, .013, "End"), routing_profile: profile,
    candidate_count: 3, seed: 19, endpoint_snap_policy: { start: "near", end: "near" },
    distance_objective: { target_m: 2200, tolerance_m: 700, maximum_m: 3500, priority: "balanced" },
    preferences: { nature: "prefer", path_selection: "shortest", loop_geometry: loop ? "prefer" : "off" }, waypoint_order: "fixed",
    waypoints: targets.map(item => ({ id: item.id, name: item.name, coordinate: item.semantic_coordinate,
      constraint_strength: "approach", access_search_radius_m: 500, maximum_best_effort_distance_m: null,
      approach_override: item.approach.coordinate })) };
  return { request, targets };
}

function nativeReply(input, targets, change = () => {}) {
  const has = id => input.points.some(p => samePoint(p, targets.find(t => t.id === id)?.approach.coordinate ?? {}));
  if (has("unreachable")) return { schema_version: 1, request_id: "synthetic", type: "local_route_failure", code: "no_route" };
  const geometry = input.points.flatMap((p, i) => i ? [
    [(input.points[i-1].lon+p.lon)/2+.00001, (input.points[i-1].lat+p.lat)/2], position(p)] : [position(p)]);
  const distance = geometry.slice(1).reduce((sum, p, i) => sum + haversineDistance(geometry[i], p), 0);
  const reply = { schema_version: 1, request_id: "synthetic", type: "local_route_result", profile: input.profile,
    engine: "valhalla-mobile", engine_version: "synthetic", pack_id: "fixture-routing", geometry,
    distance_m: has("detour") ? 12_000 : distance, duration_s: distance / 2,
    snapped_points: input.points.map(p => ({ ...p })), measurements: { cold_start: false, engine_initialization_ms: 0,
      route_ms: 0, memory_before_initialization_bytes: 0, memory_after_initialization_bytes: 0, memory_after_route_bytes: 0 } };
  change(reply, input);
  return reply;
}

async function rig({ loop = false, profile = "trail_run", change, handler, dataAvailable = true } = {}) {
  const fixtureData = await (await fetch("/tests/fixtures/pr40_regional_data.json")).json();
  const f = fixture(loop, profile), source = createLocalRegionData(fixtureData.manifest, { nature: fixtureData.nature });
  const reference = { ...structuredClone(syntheticRegionalReference), region_id: fixtureData.manifest.region_id,
    build_id: fixtureData.manifest.build_id, pack_id: "fixture-routing", bounds: [.0, .0, .02, .02] };
  reference.elevation.tiles[0].path = "skadi/N00/N00E000.hgt.gz";
  let lease = false, analyses = 0;
  const calls = [], analyzed = [];
  const region = { reference, capabilities: { enabled: true, installed_pack_count: 1, supported_profile_ids: profiles },
    bridge: { route: async input => { assert(lease, "native routing under lease"); calls.push(input);
      return handler ? handler(input, f.targets) : nativeReply(input, f.targets, change); } },
    getRegionData: async () => dataAvailable ? { ...source, analyzeNature: draft => {
      analyses++; analyzed.push(draft.candidate_id); return source.analyzeNature(draft); } } : null };
  const planner = createLocalPlanner({ lifecycleTarget: null, withRegion: async run => {
    assert(!lease, "one lease"); lease = true; try { return await run(region); } finally { lease = false; } } });
  return { ...f, planner, calls, region, get lease() { return lease; }, get analyses() { return analyses; }, analyzed };
}

async function rejected(promise, code) {
  const error = await promise.then(() => null, caught => caught);
  equal(typeof error?.code === "string" ? error.code : error?.name, code, `expected ${code}`);
}
function accounting(snapshot, calls) {
  const { cache: c, budget: b } = snapshot;
  equal(c.lookup_count, c.hit_count + c.miss_count, "lookup invariant");
  equal(c.entry_count, c.successful_entry_count + c.failed_entry_count, "entry invariant");
  equal(c.backend_call_count, c.miss_count, "miss invariant");
  equal(c.backend_call_count, calls.length, "native facts authoritative");
  assert(b.total_used <= 16 && b.phases.initial.used <= 8 && b.phases.refinement.used <= 8, "strict phases and total");
}

export async function runAdventureRoutingHarness() {
  const cases = [];
  for (const loop of [false, true]) for (const profile of profiles) {
    const r = await rig({ loop, profile });
    try {
      const inputBefore = JSON.stringify(r.request);
      const output = await r.planner.planAdventure(profile, session => session.generate(r.request, r.targets));
      const { candidates, search_diagnostics: diagnostics } = output.result;
      assert(candidates.length >= 2, `${loop}/${profile}: real subset alternatives from native fixture`);
      assert(!candidates[0].reached_stops.length, "control remains first without exact repetition evidence");
      assert(candidates.some(c => c.reached_stops.length), "interesting optional places actually selected");
      assert(candidates.every(c => c.dropped_stops.length + c.reached_stops.length === r.targets.length), "every optional outcome explicit");
      assert(candidates.every(c => c.dropped_stops.some(p => p.id === "unreachable") && c.dropped_stops.some(p => p.id === "detour")
        && c.dropped_stops.some(p => p.id === "outside")), "unreachable/detour/outside never reported reached");
      assert(candidates.every(c => c.traversal.anchors.length === c.reached_stops.length + (loop ? 1 : 2)), "shape controls are not traversal anchors");
      equal(r.analyses, candidates.length, "only retained complete candidates enriched once");
      equal(new Set(r.analyzed).size, r.analyses, "no duplicate enrichment");
      for (const c of candidates) {
        const n = c.route.analysis.nature;
        assert(n?.available && Math.abs(["woodland", "open_natural", "agriculture", "water_crossing", "urban", "unknown_landcover"]
          .reduce((sum, key) => sum + n[key].distance_m, 0) - c.route.summary.distance_m) < 1e-6, "Nature partitions native total");
        const doc = new DOMParser().parseFromString(await exportCanonicalCandidate(c).blob.text(), "application/xml");
        assert(doc.getElementsByTagName("trk").length === 1 && doc.getElementsByTagName("trkseg").length === 1
          && !doc.getElementsByTagName("rte").length && !doc.getElementsByTagName("extensions").length, "clean canonical GPX");
        const trk = [...doc.getElementsByTagName("trkpt")];
        equal(trk.length, c.route.geometry.length, "GPX vertex count");
        for (let i = 0; i < trk.length; i++) assert(Math.abs(Number(trk[i].getAttribute("lon")) - c.route.geometry[i][0]) < 1e-8
          && Math.abs(Number(trk[i].getAttribute("lat")) - c.route.geometry[i][1]) < 1e-8, "GPX equals native line");
        equal(doc.getElementsByTagName("wpt").length, c.reached_stops.length, "only reached optional waypoints");
      }
      equal(JSON.stringify(r.request), inputBefore, "input untouched");
      assert(!r.lease && r.calls.every(c => c.profile === profile), "lease released and no profile fallback");
      accounting(diagnostics, r.calls);
      samples.push(output);
      cases.push(`${loop ? "loop" : "open"}/${profile}/subset_nature_canonical_gpx`);
    } finally { r.planner.invalidate(); }
  }
  {
    const r = await rig();
    try {
      const h = (id, lat, lon) => ({ id, name: id, coordinate: point(lat, lon), constraint_strength: "exact",
        access_search_radius_m: 500, maximum_best_effort_distance_m: null, approach_override: null });
      r.request.waypoints.splice(1, 0, h("hard-a", .011, .011));
      r.request.waypoints.splice(3, 0, h("hard-b", .008, .008));
      await r.planner.planAdventure("trail_run", async session => {
        const first = await session.generate(r.request, r.targets), second = await session.generate(r.request, r.targets);
        for (const result of [first.result, second.result]) for (const c of result.candidates) {
          const visits = c.diagnostics.details.required_waypoint_order;
          equal(visits.map(p => p.original_index), [1, 3], "hard original indices/order preserved");
        }
        accounting(session.diagnostics(), r.calls);
        assert(session.diagnostics().cache.hit_count > 0, "revision reuses control and routes");
        equal(new Set(r.analyzed).size, r.analyses, "cached retained routes are not enriched again");
        await rejected(session.generate(r.request, r.targets), "adventure_refinement_limit");
      });
      cases.push("two_rounds_one_context_cache_hard_order_and_refinement_limit");
    } finally { r.planner.invalidate(); }
  }
  {
    const r = await rig();
    try {
      await r.planner.planAdventure("trail_run", async session => {
        await session.generate(r.request, r.targets);
        const changed = structuredClone(r.request); changed.start.lon += .001;
        await rejected(session.generate(changed, r.targets), "adventure_hard_intent_changed");
      });
      equal(r.calls.length <= 8, true, "changed intent cannot reserve extra calls");
      cases.push("refinement_cannot_change_confirmed_intent");
    } finally { r.planner.invalidate(); }
  }
  for (const mutation of [reply => { reply.profile = "road_bike"; }, reply => { reply.pack_id = "wrong-pack"; },
    reply => { reply.snapped_points.reverse(); }, reply => { reply.geometry.reverse(); }]) {
    const r = await rig({ change: mutation });
    try {
      const output = await r.planner.planAdventure("trail_run", s => s.generate(r.request, r.targets));
      assert(!output.result.candidates.length, "malformed native identity/order never published");
    } finally { r.planner.invalidate(); }
  }
  cases.push("native_pack_profile_and_order_corruption_rejected");
  {
    const r = await rig({ change: (reply, input) => {
      const index = input.points.findIndex(p => samePoint(p, point(.006, .006)));
      if (index < 0) return;
      const p = reply.snapped_points[index]; p.lat += .0001;
      reply.geometry[index * 2] = position(p);
    } });
    try {
      r.targets[0].approach.arrival_tolerance_m = 5;
      const output = await r.planner.planAdventure("trail_run", s => s.generate(r.request, r.targets));
      assert(output.result.candidates.every(c => !c.reached_stops.some(p => p.id === "near-a")), "stricter mapped approach is authoritative");
      cases.push("mapped_arrival_threshold_not_semantic_proximity");
    } finally { r.planner.invalidate(); }
  }
  {
    const r = await rig();
    try {
      const hard = { id: "outside-hard", name: "Keep exact", coordinate: point(.03, .03), constraint_strength: "exact" };
      r.request.waypoints.push(hard);
      await rejected(r.planner.planAdventure("trail_run", s => s.generate(r.request, r.targets)), "no_covering_routing_pack");
      equal(r.calls.length, 0, "outside mandatory point rejects before native work");
      cases.push("outside_mandatory_never_dropped_or_relocated");
    } finally { r.planner.invalidate(); }
  }
  {
    const r = await rig();
    try {
      const template = structuredClone(r.targets[0]);
      for (let i = 0; i < 15; i++) {
        const t = structuredClone(template); t.id = `many-${i}`; t.name = t.id;
        t.semantic_coordinate.lon += .00001 * (i + 1); t.approach.coordinate = t.semantic_coordinate;
        t.approach.id = `${t.id}/entrance`; r.targets.push(t);
        r.request.waypoints.push({ ...structuredClone(r.request.waypoints[0]), id: t.id, name: t.name,
          coordinate: t.semantic_coordinate, approach_override: t.approach.coordinate });
      }
      const output = await r.planner.planAdventure("trail_run", s => s.generate(r.request, r.targets));
      assert(r.calls.length <= 8 && r.calls.every(c => c.points.length <= 16), "many optional suggestions remain bounded");
      assert(output.result.candidates.every(c => c.reached_stops.length + c.dropped_stops.length === 20), "no lost optional outcome");
      cases.push("twenty_places_bounded_subset_and_explicit_outcomes");
    } finally { r.planner.invalidate(); }
  }
  {
    const r = await rig({ handler: async () => ({ schema_version: 1, request_id: "synthetic", type: "local_route_failure", code: "no_route" }) });
    try {
      const output = await r.planner.planAdventure("trail_run", s => s.generate(r.request, r.targets));
      assert(!output.result.candidates.length && r.calls.length <= 8, "all unreachable is honest failure");
      cases.push("all_unreachable_no_fallback");
    } finally { r.planner.invalidate(); }
  }
  {
    const r = await rig({ dataAvailable: false });
    try {
      const output = await r.planner.planAdventure("trail_run", s => s.generate(r.request, r.targets));
      assert(output.result.candidates.length && output.result.candidates.every(c => c.route.analysis.nature === null), "missing Nature remains unknown");
      cases.push("missing_nature_remains_unknown");
    } finally { r.planner.invalidate(); }
  }
  {
    let finish;
    const r = await rig({ handler: (input, targets) => new Promise(resolve => { finish = () => resolve(nativeReply(input, targets)); }) });
    const abort = new AbortController();
    const pending = r.planner.planAdventure("trail_run", s => s.generate(r.request, r.targets), abort.signal);
    while (!finish) await new Promise(resolve => setTimeout(resolve, 0));
    const outcome = rejected(pending, "AbortError"); abort.abort();
    assert(r.lease, "lease retained while native drains");
    await rejected(r.planner.planAdventure("trail_run", () => null), "local_generation_busy");
    finish(); await outcome;
    assert(!r.lease && r.calls.length === 1, "cancel drains without additional calls");
    r.planner.invalidate(); cases.push("cancellation_owns_lease_through_native_drain");
  }
  return cases;
}
