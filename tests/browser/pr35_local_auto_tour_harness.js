import {
  analyzeLocalLoopGeometry,
  createLocalAutoTourEngine,
  createLocalAutoTourExperiment,
  generateLocalAutoTourSkeletons,
  LOCAL_AUTO_TOUR_ROUTE_CALL_BUDGET,
  MARLY_LOCAL_AUTO_TOUR_FIXTURE,
  rankLocalAutoTourCandidates,
  validateLocalAutoTourRequest,
} from "../../src/sugarglider/web/static/local_auto_tour.js";
import {
  PUBLIC_LOCAL_ROUTE_PROFILES,
} from "../../src/sugarglider/web/static/local_routing.js";

export async function runPr35LocalAutoTourHarness() {
  const scenarios = [];
  strictRequestAndSixProfilesScenario();
  scenarios.push("strict_request_and_six_profiles");
  seededSkeletonScenario();
  scenarios.push("seeded_triangle_diamond_and_direction");
  await boundedAdaptationScenario();
  scenarios.push("bounded_adaptation_and_deterministic_identity");
  await hardValidationScenario();
  scenarios.push("snap_route_and_cross_pack_rejection");
  await geometryGoldenAndRankingScenario();
  scenarios.push("geometry_golden_and_structural_ranking");
  await diversityAndUnavailableMetricsScenario();
  scenarios.push("diversity_and_unavailable_metrics");
  await duplicateSingleFlightScenario();
  scenarios.push("duplicate_generation_is_single_flight");
  await staleExperimentScenario();
  scenarios.push("stale_generation_cannot_render");
  await noBackendFetchScenario();
  scenarios.push("no_fetch_or_graphhopper_fallback");
  return scenarios;
}

function strictRequestAndSixProfilesScenario() {
  for (const profile of PUBLIC_LOCAL_ROUTE_PROFILES) {
    equal(validateLocalAutoTourRequest({
      ...MARLY_LOCAL_AUTO_TOUR_FIXTURE,
      profile,
    }).profile, profile, `${profile} accepted without alias`);
  }
  rejects({ ...MARLY_LOCAL_AUTO_TOUR_FIXTURE, extra: true }, "invalid_request_fields");
  rejects({ ...MARLY_LOCAL_AUTO_TOUR_FIXTURE, candidate_count: 4 }, "invalid_candidate_count");
  rejects({ ...MARLY_LOCAL_AUTO_TOUR_FIXTURE, seed: -1 }, "invalid_seed");
  rejects({ ...MARLY_LOCAL_AUTO_TOUR_FIXTURE, target_distance_m: Infinity }, "invalid_target_distance");
  rejects({ ...MARLY_LOCAL_AUTO_TOUR_FIXTURE, tolerance_m: 7_000 }, "invalid_tolerance");
  rejects({ ...MARLY_LOCAL_AUTO_TOUR_FIXTURE, profile: "walking" }, "unsupported_profile");
  rejects({ ...MARLY_LOCAL_AUTO_TOUR_FIXTURE, direction_preference: "mixed" }, "invalid_direction_preference");
}

function seededSkeletonScenario() {
  const first = generateLocalAutoTourSkeletons(MARLY_LOCAL_AUTO_TOUR_FIXTURE);
  const repeated = generateLocalAutoTourSkeletons(MARLY_LOCAL_AUTO_TOUR_FIXTURE);
  const changed = generateLocalAutoTourSkeletons({ ...MARLY_LOCAL_AUTO_TOUR_FIXTURE, seed: 36 });
  equal(
    first.map((skeleton) => skeleton.skeleton_id),
    repeated.map((skeleton) => skeleton.skeleton_id),
    "same seed preserves skeleton ordering",
  );
  assert(first[0].skeleton_id !== changed[0].skeleton_id, "different seed changes ordering");
  assert(first.some((skeleton) => skeleton.family === "triangle"), "triangle family present");
  assert(first.some((skeleton) => skeleton.family === "asymmetric-triangle"), "asymmetric family present");
  assert(first.some((skeleton) => skeleton.family === "diamond"), "diamond family present");
  const clockwise = generateLocalAutoTourSkeletons({
    ...MARLY_LOCAL_AUTO_TOUR_FIXTURE,
    direction_preference: "clockwise",
  });
  assert(clockwise.every((skeleton) => skeleton.direction === "clockwise"), "clockwise order only");
  assert(clockwise.every((skeleton) => skeleton.points[0] === skeleton.points.at(-1)), "every skeleton closes at exact start");
}

async function boundedAdaptationScenario() {
  const requests = [];
  const route = async (input) => {
    requests.push(input);
    return routedReply(input, { distanceFactor: 1.25 });
  };
  const clock = sequenceClock();
  const engine = createLocalAutoTourEngine({ route, now: clock });
  const first = await engine.generate({ ...MARLY_LOCAL_AUTO_TOUR_FIXTURE, candidate_count: 1 });
  const second = await engine.generate({ ...MARLY_LOCAL_AUTO_TOUR_FIXTURE, candidate_count: 1 });
  assert(first.route_call_count <= LOCAL_AUTO_TOUR_ROUTE_CALL_BUDGET, "hard budget respected");
  assert(first.route_call_count >= 2, "distance correction reroutes at least once");
  assert(first.candidates.some((candidate) => candidate.construction.correction_step === 1), "bounded correction retained");
  equal(
    first.candidates.map((candidate) => [candidate.candidate_id, candidate.construction.skeleton_id]),
    second.candidates.map((candidate) => [candidate.candidate_id, candidate.construction.skeleton_id]),
    "identical request and graph replies preserve identities",
  );
  assert(requests.every((request) => request.points.length >= 4 && request.points.length <= 5), "only bounded ordered loop routes sent");
}

async function hardValidationScenario() {
  const badSnap = createLocalAutoTourEngine({
    route: async (input) => {
      const reply = routedReply(input);
      reply.snapped_points[1] = {
        lat: reply.snapped_points[1].lat + 0.02,
        lon: reply.snapped_points[1].lon,
      };
      return reply;
    },
    routeCallBudget: 2,
  });
  const snapResult = await badSnap.generate(MARLY_LOCAL_AUTO_TOUR_FIXTURE);
  equal(snapResult.candidates.length, 0, "absurd control snap rejected");
  equal(snapResult.rejected_attempt_counts.generated_control_snap_too_far, 2, "snap rejection counted");

  const noRoute = createLocalAutoTourEngine({
    route: async () => ({ type: "local_route_failure", code: "no_route" }),
    routeCallBudget: 3,
  });
  const noRouteResult = await noRoute.generate(MARLY_LOCAL_AUTO_TOUR_FIXTURE);
  equal(noRouteResult.route_call_count, 3, "route failure consumes only bounded attempts");
  equal(noRouteResult.rejected_attempt_counts.local_route_no_route, 3, "route failures diagnosed");

  const crossPack = createLocalAutoTourEngine({
    route: async () => ({
      type: "local_route_failure",
      code: "no_covering_routing_pack",
    }),
    routeCallBudget: 2,
  });
  const crossResult = await crossPack.generate(MARLY_LOCAL_AUTO_TOUR_FIXTURE);
  equal(crossResult.route_call_count, 2, "cross-pack failure remains bounded");
  equal(crossResult.rejected_attempt_counts.local_route_no_covering_routing_pack, 2, "cross-pack reason public");
}

async function geometryGoldenAndRankingScenario() {
  const response = await fetch("/tests/fixtures/pr35_local_loop_geometry_golden.json");
  const fixtures = await response.json();
  for (const fixture of fixtures) {
    const analysis = analyzeLocalLoopGeometry(fixture.geometry, fixture.route_distance_m);
    equal(analysis.closed, fixture.expected.closed, `${fixture.id} closure matches Python`);
    equal(
      analysis.sampled_self_crossing_count,
      fixture.expected.self_crossing_count,
      `${fixture.id} crossing matches Python golden`,
    );
    near(
      analysis.angular_monotonicity,
      fixture.expected.angular_monotonicity,
      1e-9,
      `${fixture.id} angular coherence matches Python golden`,
    );
    if (fixture.expected.compactness !== undefined) {
      near(
        analysis.signed_area_compactness,
        fixture.expected.compactness,
        1e-8,
        `${fixture.id} compactness matches non-crossing Python golden`,
      );
    }
    if (fixture.expected.outbound_return_proximity_share !== undefined) {
      near(
        analysis.sampled_outbound_return_proximity_share,
        fixture.expected.outbound_return_proximity_share,
        0.08,
        `${fixture.id} outbound/return proximity matches Python golden`,
      );
    }
  }
  const square = fixtures.find((fixture) => fixture.id === "square");
  const hairpin = fixtures.find((fixture) => fixture.id === "narrow_hairpin");
  const clean = rankingCandidate("clean", square, 900);
  const severe = rankingCandidate("severe", hairpin, 10);
  const ranked = rankLocalAutoTourCandidates([severe, clean], MARLY_LOCAL_AUTO_TOUR_FIXTURE);
  equal(ranked[0].candidate_id, "clean", "severe out-and-back loses before target error");
}

async function diversityAndUnavailableMetricsScenario() {
  const fixed = fixedSquareAround(MARLY_LOCAL_AUTO_TOUR_FIXTURE.start, 1_000);
  const engine = createLocalAutoTourEngine({
    route: async (input) => routedReply(input, {
      geometry: fixed,
      distanceM: 4_000,
    }),
    routeCallBudget: 5,
  });
  const result = await engine.generate({
    ...MARLY_LOCAL_AUTO_TOUR_FIXTURE,
    target_distance_m: 4_000,
    tolerance_m: 1_000,
    candidate_count: 3,
  });
  equal(result.candidates.length, 1, "identical geometry is not fabricated as diverse");
  assert(result.rejected_attempt_counts.insufficient_geometry_diversity >= 1, "diversity rejection counted");
  equal(result.candidates[0].exact_edge_repetition, null, "exact repetition stays unavailable");
  equal(result.candidates[0].path_attributes, null, "path attributes stay unavailable");
  assert(result.warnings.includes("nature_analysis_unavailable"), "nature absence explicit");
}

async function duplicateSingleFlightScenario() {
  const pending = deferred();
  let calls = 0;
  let activeRoutes = 0;
  let maximumActiveRoutes = 0;
  const engine = createLocalAutoTourEngine({
    route: async (input) => {
      calls += 1;
      activeRoutes += 1;
      maximumActiveRoutes = Math.max(maximumActiveRoutes, activeRoutes);
      await pending.promise;
      activeRoutes -= 1;
      return routedReply(input);
    },
  });
  const first = engine.generate({ ...MARLY_LOCAL_AUTO_TOUR_FIXTURE, candidate_count: 1 });
  const duplicate = engine.generate({ ...MARLY_LOCAL_AUTO_TOUR_FIXTURE, candidate_count: 1 });
  assert(first === duplicate, "duplicate generation receives same in-flight promise");
  equal(calls, 1, "duplicate click starts no second native route");
  pending.resolve();
  await first;
  equal(maximumActiveRoutes, 1, "native route calls stay serialized");
}

async function staleExperimentScenario() {
  const pending = deferred();
  let rendered = 0;
  const result = syntheticResult();
  const fakeEngine = {
    generate: () => pending.promise,
    invalidate() {},
  };
  const rig = experimentRig(fakeEngine, () => { rendered += 1; });
  rig.experiment.bind();
  const operation = rig.experiment.requestMarlySmokeTest();
  rig.experiment.invalidate();
  pending.resolve(result);
  equal(await operation, null, "invalidated generation resolves without public result");
  equal(rendered, 0, "stale generation never renders");
  rig.fixture.remove();
}

async function noBackendFetchScenario() {
  const originalFetch = globalThis.fetch;
  let backendFetches = 0;
  globalThis.fetch = async () => {
    backendFetches += 1;
    throw new Error("local Auto Tour attempted a backend fetch");
  };
  try {
    const engine = createLocalAutoTourEngine({
      route: async (input) => routedReply(input),
    });
    const result = await engine.generate({ ...MARLY_LOCAL_AUTO_TOUR_FIXTURE, candidate_count: 1 });
    assert(result.candidates.length === 1, "graph-routed candidate produced without fetch");
    equal(backendFetches, 0, "no FastAPI or GraphHopper fetch attempted");
  } finally {
    globalThis.fetch = originalFetch;
  }
}

function routedReply(input, {
  distanceFactor = 1,
  distanceM = null,
  geometry = null,
} = {}) {
  const routedGeometry = geometry ?? input.points.map(({ lon, lat }) => [lon, lat]);
  return {
    type: "local_route_result",
    profile: input.profile,
    pack_id: "marly-dev-v1",
    distance_m: distanceM ?? geometryDistanceM(routedGeometry) * distanceFactor,
    duration_s: 3_600,
    geometry: routedGeometry.map((coordinate) => [...coordinate]),
    snapped_points: input.points.map(({ lat, lon }) => ({ lat, lon })),
    measurements: {
      cold_start: false,
      engine_initialization_ms: 0,
      route_ms: 50,
      memory_before_initialization_bytes: 1,
      memory_after_initialization_bytes: 1,
      memory_after_route_bytes: 1,
    },
  };
}

function rankingCandidate(id, fixture, targetErrorM) {
  return {
    candidate_id: id,
    within_tolerance: true,
    target_error_m: targetErrorM,
    geometry_metrics: analyzeLocalLoopGeometry(
      fixture.geometry,
      fixture.route_distance_m,
    ),
  };
}

function fixedSquareAround(start, sideM) {
  const latitudeDelta = sideM / 111_195.0802335329;
  const longitudeDelta = latitudeDelta / Math.cos(start.lat * Math.PI / 180);
  return [
    [start.lon, start.lat],
    [start.lon + longitudeDelta, start.lat],
    [start.lon + longitudeDelta, start.lat + latitudeDelta],
    [start.lon, start.lat + latitudeDelta],
    [start.lon, start.lat],
  ];
}

function geometryDistanceM(geometry) {
  let total = 0;
  for (let index = 1; index < geometry.length; index += 1) {
    total += haversine(geometry[index - 1], geometry[index]);
  }
  return total;
}

function haversine([leftLon, leftLat], [rightLon, rightLat]) {
  const radius = 6_371_008.8;
  const toRadians = (value) => value * Math.PI / 180;
  const deltaLatitude = toRadians(rightLat - leftLat);
  const deltaLongitude = toRadians(rightLon - leftLon);
  const value = Math.sin(deltaLatitude / 2) ** 2
    + Math.cos(toRadians(leftLat)) * Math.cos(toRadians(rightLat))
      * Math.sin(deltaLongitude / 2) ** 2;
  return 2 * radius * Math.atan2(Math.sqrt(value), Math.sqrt(Math.max(0, 1 - value)));
}

function experimentRig(engine, renderCandidates) {
  const fixture = document.createElement("section");
  fixture.innerHTML = `
    <button class="planner" aria-busy="false">Planner</button>
    <button class="smoke" aria-busy="false">Smoke</button>
    <input class="target" value="12">
    <input class="tolerance" value="2.5">
    <select class="count"><option value="2">2</option></select>
    <input class="seed" value="35">
    <select class="direction"><option value="any">Any</option></select>
    <p class="status"></p><ol></ol>
  `;
  document.body.append(fixture);
  const experiment = createLocalAutoTourExperiment({
    bridge: { route() {} },
    engine,
    getStart: () => MARLY_LOCAL_AUTO_TOUR_FIXTURE.start,
    renderCandidates,
    elements: {
      button: fixture.querySelector(".planner"),
      smokeButton: fixture.querySelector(".smoke"),
      targetDistanceInput: fixture.querySelector(".target"),
      toleranceInput: fixture.querySelector(".tolerance"),
      candidateCountSelect: fixture.querySelector(".count"),
      seedInput: fixture.querySelector(".seed"),
      directionSelect: fixture.querySelector(".direction"),
      status: fixture.querySelector(".status"),
      results: fixture.querySelector("ol"),
    },
  });
  return { experiment, fixture };
}

function syntheticResult() {
  return {
    candidates: [],
    route_call_count: 1,
    route_call_budget: 24,
    rejected_attempt_counts: {},
  };
}

function sequenceClock() {
  let value = 0;
  return () => value++;
}

function deferred() {
  let resolve;
  const promise = new Promise((settle) => { resolve = settle; });
  return { promise, resolve };
}

function rejects(value, code) {
  let observed = null;
  try {
    validateLocalAutoTourRequest(value);
  } catch (error) {
    observed = error.code;
  }
  equal(observed, code, `request rejected as ${code}`);
}

function near(actual, expected, tolerance, message) {
  if (Math.abs(actual - expected) > tolerance) {
    throw new Error(`${message}: ${actual} not within ${tolerance} of ${expected}`);
  }
}

function equal(actual, expected, message) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${message}: ${JSON.stringify(actual)} !== ${JSON.stringify(expected)}`);
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
