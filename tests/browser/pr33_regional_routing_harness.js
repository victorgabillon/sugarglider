import {
  createLocalRoutingExperiment,
  CROSS_PACK_FAILURE_TEST,
  MARLY_OFFLINE_SMOKE_TEST,
  PARIS_OFFLINE_SMOKE_TEST,
  parseLocalRoutingReply,
} from "../../src/sugarglider/web/static/local_routing.js";

const NONCE = "0123456789abcdef0123456789abcdef";

export async function runPr33RegionalRoutingHarness() {
  const scenarios = [];
  strictRegionalReplyParserScenario();
  scenarios.push("strict_regional_reply_parser");
  await regionalPackSwitchSequenceScenario();
  scenarios.push("regional_pack_switch_sequence");
  await crossRegionFailureWithoutFetchScenario();
  scenarios.push("cross_region_failure_without_fetch");
  return scenarios;
}

function strictRegionalReplyParserScenario() {
  const capabilities = capabilityReply();
  assert(
    parseLocalRoutingReply(JSON.stringify(capabilities)) !== null,
    "strict two-pack capabilities accepted",
  );
  const wrongCount = structuredClone(capabilities);
  wrongCount.installed_pack_count = 1;
  equal(parseLocalRoutingReply(JSON.stringify(wrongCount)), null, "count mismatch rejected");
  const unsorted = structuredClone(capabilities);
  unsorted.installed_pack_ids.reverse();
  equal(parseLocalRoutingReply(JSON.stringify(unsorted)), null, "unsorted pack IDs rejected");
  const extra = structuredClone(capabilities);
  extra.pack_path = "/private/path";
  equal(parseLocalRoutingReply(JSON.stringify(extra)), null, "filesystem field rejected");

  const route = routeReply(MARLY_OFFLINE_SMOKE_TEST, "marly-dev-v1", true);
  assert(parseLocalRoutingReply(JSON.stringify(route)) !== null, "selected pack accepted");
  delete route.pack_id;
  equal(parseLocalRoutingReply(JSON.stringify(route)), null, "missing selected pack rejected");
  assert(
    parseLocalRoutingReply(JSON.stringify(failureReply())) !== null,
    "explicit no-covering-pack failure accepted",
  );
}

async function regionalPackSwitchSequenceScenario() {
  let currentPack = null;
  const observed = [];
  const rig = experimentRig({
    nativeAvailable: true,
    capabilities: async () => capabilityReply(),
    async route(input) {
      const packId = input.points.at(-1).lon < 2.2
        ? "marly-dev-v1"
        : "paris-dev-v1";
      const coldStart = currentPack !== packId;
      currentPack = packId;
      observed.push({ packId, coldStart });
      return routeReply(input, packId, coldStart);
    },
    invalidate() {},
  });
  await rig.experiment.bind();
  assert(rig.status.includes("Installed regional packs (2)"), "pack count is visible");
  assert(rig.status.includes("marly-dev-v1 [foot+bicycle]"), "Marly modes are visible");
  assert(rig.status.includes("paris-dev-v1 [foot+bicycle]"), "Paris modes are visible");
  assert(rig.buttons.every((button) => !button.disabled), "regional actions enabled");

  await rig.experiment.requestSmokeTest();
  await rig.experiment.requestSmokeTest();
  await rig.experiment.requestParisSmokeTest();
  await rig.experiment.requestParisSmokeTest();
  await rig.experiment.requestSmokeTest();
  equal(observed, [
    { packId: "marly-dev-v1", coldStart: true },
    { packId: "marly-dev-v1", coldStart: false },
    { packId: "paris-dev-v1", coldStart: true },
    { packId: "paris-dev-v1", coldStart: false },
    { packId: "marly-dev-v1", coldStart: true },
  ], "A→A→B→B→A pack lifecycle is visible");
  equal(rig.rendered.length, 5, "every graph-derived regional result rendered");
  assert(rig.status.includes("pack marly-dev-v1"), "selected pack is reported");
  rig.fixture.remove();
}

async function crossRegionFailureWithoutFetchScenario() {
  let backendFetches = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    backendFetches += 1;
    throw new Error("regional smoke test attempted backend access");
  };
  const rig = experimentRig({
    nativeAvailable: true,
    capabilities: async () => capabilityReply(),
    async route(input) {
      equal(input, CROSS_PACK_FAILURE_TEST, "fixed cross-region fixture used");
      return failureReply();
    },
    invalidate() {},
  });
  try {
    await rig.experiment.bind();
    const reply = await rig.experiment.requestCrossPackTest();
    equal(reply.code, "no_covering_routing_pack", "regional coverage failure preserved");
    assert(rig.status.includes("(no_covering_routing_pack)"), "failure code visible");
    equal(backendFetches, 0, "regional failure makes no backend request");
    equal(rig.clears, 1, "failed regional request clears prior local geometry");
  } finally {
    globalThis.fetch = originalFetch;
    rig.fixture.remove();
  }
}

function experimentRig(bridge) {
  const fixture = document.createElement("section");
  fixture.className = "hidden";
  fixture.innerHTML = `
    <select><option value="trail_run">Trail</option><option value="hike" selected>Hike</option><option value="city_bike">City</option><option value="gravel_bike">Gravel</option><option value="mountain_bike">MTB</option><option value="road_bike">Road</option></select>
    <button class="route" type="button" disabled aria-busy="false">Route</button>
    <button class="marly" type="button" disabled aria-busy="false">Marly</button>
    <button class="paris" type="button" disabled aria-busy="false">Paris</button>
    <button class="via" type="button" disabled aria-busy="false">Via</button>
    <button class="cross" type="button" disabled aria-busy="false">Cross</button>
    <p></p>
  `;
  document.body.append(fixture);
  const rendered = [];
  let clears = 0;
  const experiment = createLocalRoutingExperiment({
    bridge,
    getPoints: () => {
      throw new Error("fixed regional test read planner points");
    },
    renderRoute: (geometry) => rendered.push(geometry),
    clearRoute: () => { clears += 1; },
    elements: {
      container: fixture,
      button: fixture.querySelector("button.route"),
      smokeButton: fixture.querySelector("button.marly"),
      parisSmokeButton: fixture.querySelector("button.paris"),
      viaSmokeButton: fixture.querySelector("button.via"),
      crossPackButton: fixture.querySelector("button.cross"),
      profileSelect: fixture.querySelector("select"),
      status: fixture.querySelector("p"),
    },
  });
  return {
    experiment,
    fixture,
    rendered,
    buttons: [...fixture.querySelectorAll("button")],
    get status() { return fixture.querySelector("p").textContent; },
    get clears() { return clears; },
  };
}

function capabilityReply() {
  return {
    schema_version: 1,
    request_id: `web-${NONCE}-1`,
    type: "local_route_capabilities_result",
    enabled: true,
    engine: "valhalla-mobile",
    engine_version: "0.5.1/valhalla-3.6.3",
    installed_pack_count: 2,
    installed_pack_ids: ["marly-dev-v1", "paris-dev-v1"],
    supported_profile_ids: [
      "trail_run", "hike", "city_bike", "gravel_bike", "mountain_bike", "road_bike",
    ],
    pack_capabilities: [
      { pack_id: "marly-dev-v1", access_modes: ["foot", "bicycle"] },
      { pack_id: "paris-dev-v1", access_modes: ["foot", "bicycle"] },
    ],
  };
}

function routeReply(input, packId, coldStart) {
  const origin = input.points[0];
  const destination = input.points.at(-1);
  const geometry = [
    [origin.lon, origin.lat],
    [
      (origin.lon + destination.lon) / 2,
      (origin.lat + destination.lat) / 2,
    ],
    [destination.lon, destination.lat],
  ];
  return {
    schema_version: 1,
    request_id: `web-${NONCE}-2`,
    type: "local_route_result",
    profile: "hike",
    engine: "valhalla-mobile",
    engine_version: "0.5.1/valhalla-3.6.3",
    pack_id: packId,
    distance_m: 3_980,
    duration_s: 2_820,
    geometry,
    snapped_points: [
      { lat: geometry[0][1], lon: geometry[0][0] },
      { lat: geometry.at(-1)[1], lon: geometry.at(-1)[0] },
    ],
    measurements: {
      cold_start: coldStart,
      engine_initialization_ms: coldStart ? 1_000 : 0,
      route_ms: coldStart ? 900 : 50,
      memory_before_initialization_bytes: 1_000,
      memory_after_initialization_bytes: 2_000,
      memory_after_route_bytes: 2_100,
    },
  };
}

function failureReply() {
  return {
    schema_version: 1,
    request_id: `web-${NONCE}-3`,
    type: "local_route_failure",
    code: "no_covering_routing_pack",
  };
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function equal(actual, expected, message) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${message}: ${JSON.stringify(actual)} !== ${JSON.stringify(expected)}`);
  }
}
