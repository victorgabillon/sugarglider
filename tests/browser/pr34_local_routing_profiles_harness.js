import {
  createLocalRoutingBridge,
  createLocalRoutingExperiment,
  MARLY_OFFLINE_SMOKE_TEST,
  MARLY_VIA_SMOKE_TEST,
  PUBLIC_LOCAL_ROUTE_PROFILES,
  parseLocalRoutingReply,
} from "../../src/sugarglider/web/static/local_routing.js";
import {
  createNativeBridgeTransport,
} from "../../src/sugarglider/web/static/native_bridge_transport.js";

const NONCE = "0123456789abcdef0123456789abcdef";

export async function runPr34LocalRoutingProfilesHarness() {
  const scenarios = [];
  strictCapabilitiesAndProfilesScenario();
  scenarios.push("strict_profile_and_pack_capabilities");
  await strictMultiPointWireScenario();
  scenarios.push("strict_v2_ordered_multi_point_wire");
  await viaProfileIdentityScenario();
  scenarios.push("via_route_preserves_public_profile");
  await incompatiblePackWithoutFetchScenario();
  scenarios.push("incompatible_pack_failure_without_fetch");
  return scenarios;
}

function strictCapabilitiesAndProfilesScenario() {
  const capabilities = capabilitiesReply();
  assert(parse(capabilities) !== null, "strict mixed pack capabilities accepted");

  const footOnly = capabilitiesReply({ includeBicycle: false });
  assert(parse(footOnly) !== null, "v1-equivalent foot-only capabilities accepted");
  equal(footOnly.supported_profile_ids, ["trail_run", "hike"], "foot-only profiles truthful");

  const mismatchedProfiles = structuredClone(capabilities);
  mismatchedProfiles.supported_profile_ids = ["hike"];
  equal(parse(mismatchedProfiles), null, "pack/profile capability mismatch rejected");
  const reversedModes = structuredClone(capabilities);
  reversedModes.pack_capabilities[0].access_modes.reverse();
  equal(parse(reversedModes), null, "non-canonical access modes rejected");

  for (const profile of PUBLIC_LOCAL_ROUTE_PROFILES) {
    assert(parse(routeReply(MARLY_OFFLINE_SMOKE_TEST.points, profile)) !== null, `${profile} accepted`);
  }
  const unknown = routeReply(MARLY_OFFLINE_SMOKE_TEST.points, "walking");
  equal(parse(unknown), null, "Android-only profile alias rejected");
}

async function strictMultiPointWireScenario() {
  const port = fakePort((request) => {
    if (request.type === "hello") return helloReply(request.request_id);
    if (request.type === "local_route") {
      return routeReply(request.points, request.profile, request.request_id);
    }
    return null;
  });
  const transport = createNativeBridgeTransport({
    port,
    pageNonce: NONCE,
    lifecycleTarget: null,
  });
  const bridge = createLocalRoutingBridge({ transport });
  const reply = await bridge.route({
    points: MARLY_VIA_SMOKE_TEST.points,
    profile: "gravel_bike",
  });
  equal(reply.profile, "gravel_bike", "route reply preserves selected public profile");
  const request = port.requests.find((value) => value.type === "local_route");
  equal(Object.keys(request).sort(), [
    "points", "profile", "request_id", "route_version", "schema_version", "type",
  ], "v2 request rejects legacy origin/destination shape");
  equal(request.route_version, 2, "local route version is explicit");
  equal(request.points, MARLY_VIA_SMOKE_TEST.points, "ordered via points preserved");
}

async function viaProfileIdentityScenario() {
  const observed = [];
  const rig = experimentRig({
    nativeAvailable: true,
    capabilities: async () => capabilitiesReply(),
    async route(input) {
      observed.push(input);
      return routeReply(input.points, input.profile);
    },
    invalidate() {},
  });
  await rig.experiment.bind();
  rig.profile.value = "mountain_bike";
  rig.profile.dispatchEvent(new Event("change"));
  const reply = await rig.experiment.requestViaSmokeTest();
  equal(observed[0].points, MARLY_VIA_SMOKE_TEST.points, "fixed three-point fixture used");
  equal(observed[0].profile, "mountain_bike", "selector public identity sent");
  equal(reply.snapped_points.length, 3, "all routed break points returned");
  assert(rig.status.includes("profile mountain_bike"), "result profile is visible");
  rig.fixture.remove();
}

async function incompatiblePackWithoutFetchScenario() {
  const originalFetch = globalThis.fetch;
  let backendFetches = 0;
  globalThis.fetch = async () => {
    backendFetches += 1;
    throw new Error("incompatible local profile attempted backend access");
  };
  const rig = experimentRig({
    nativeAvailable: true,
    capabilities: async () => capabilitiesReply({ marlyBicycle: false }),
    async route(input) {
      equal(input.profile, "city_bike", "bicycle identity preserved to native boundary");
      return failureReply("no_compatible_routing_pack");
    },
    invalidate() {},
  });
  try {
    await rig.experiment.bind();
    rig.profile.value = "city_bike";
    rig.profile.dispatchEvent(new Event("change"));
    const reply = await rig.experiment.requestSmokeTest();
    equal(reply.code, "no_compatible_routing_pack", "typed compatibility failure preserved");
    assert(rig.status.includes("(no_compatible_routing_pack)"), "compatibility code visible");
    equal(backendFetches, 0, "compatibility failure makes no backend request");
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
    <button class="route" disabled aria-busy="false">Route</button>
    <button class="marly" disabled aria-busy="false">Marly</button>
    <button class="paris" disabled aria-busy="false">Paris</button>
    <button class="via" disabled aria-busy="false">Via</button>
    <button class="cross" disabled aria-busy="false">Cross</button>
    <p></p>
  `;
  document.body.append(fixture);
  const profile = fixture.querySelector("select");
  const experiment = createLocalRoutingExperiment({
    bridge,
    getPoints: () => MARLY_OFFLINE_SMOKE_TEST.points,
    renderRoute() {},
    clearRoute() {},
    elements: {
      container: fixture,
      profileSelect: profile,
      button: fixture.querySelector("button.route"),
      smokeButton: fixture.querySelector("button.marly"),
      parisSmokeButton: fixture.querySelector("button.paris"),
      viaSmokeButton: fixture.querySelector("button.via"),
      crossPackButton: fixture.querySelector("button.cross"),
      status: fixture.querySelector("p"),
    },
  });
  return {
    experiment,
    fixture,
    profile,
    get status() { return fixture.querySelector("p").textContent; },
  };
}

function capabilitiesReply({ includeBicycle = true, marlyBicycle = includeBicycle } = {}) {
  const marlyModes = marlyBicycle ? ["foot", "bicycle"] : ["foot"];
  const parisModes = includeBicycle ? ["foot", "bicycle"] : ["foot"];
  return {
    schema_version: 1,
    request_id: `web-${NONCE}-1`,
    type: "local_route_capabilities_result",
    enabled: true,
    engine: "valhalla-mobile",
    engine_version: "0.5.1/valhalla-3.6.3",
    installed_pack_count: 2,
    installed_pack_ids: ["marly-dev-v1", "paris-dev-v1"],
    supported_profile_ids: includeBicycle
      ? [...PUBLIC_LOCAL_ROUTE_PROFILES]
      : ["trail_run", "hike"],
    pack_capabilities: [
      { pack_id: "marly-dev-v1", access_modes: marlyModes },
      { pack_id: "paris-dev-v1", access_modes: parisModes },
    ],
  };
}

function routeReply(points, profile, requestId = `web-${NONCE}-2`) {
  const geometry = points.map(({ lon, lat }) => [lon, lat]);
  return {
    schema_version: 1,
    request_id: requestId,
    type: "local_route_result",
    profile,
    engine: "valhalla-mobile",
    engine_version: "0.5.1/valhalla-3.6.3",
    pack_id: "marly-dev-v1",
    distance_m: 3_980,
    duration_s: 2_820,
    geometry,
    snapped_points: geometry.map(([lon, lat]) => ({ lat, lon })),
    measurements: {
      cold_start: true,
      engine_initialization_ms: 1_000,
      route_ms: 100,
      memory_before_initialization_bytes: 1_000,
      memory_after_initialization_bytes: 2_000,
      memory_after_route_bytes: 2_100,
    },
  };
}

function failureReply(code) {
  return {
    schema_version: 1,
    request_id: `web-${NONCE}-3`,
    type: "local_route_failure",
    code,
  };
}

function helloReply(requestId) {
  return {
    schema_version: 1,
    request_id: requestId,
    type: "hello_result",
    outing_slug: null,
    participant_id: null,
    active: false,
    state: "stopped",
    last_published_at: null,
    pending_sample: false,
    stop_warning: null,
  };
}

function fakePort(responder) {
  return {
    onmessage: null,
    requests: [],
    postMessage(payload) {
      const request = JSON.parse(payload);
      this.requests.push(request);
      const reply = responder(request);
      if (reply) queueMicrotask(() => this.onmessage?.({ data: JSON.stringify(reply) }));
    },
  };
}

function parse(value) {
  return parseLocalRoutingReply(JSON.stringify(value));
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function equal(actual, expected, message) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${message}: ${JSON.stringify(actual)} !== ${JSON.stringify(expected)}`);
  }
}
