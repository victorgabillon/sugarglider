import {
  createLocalRoutingBridge,
  createLocalRoutingExperiment,
  MARLY_OFFLINE_SMOKE_TEST,
  parseLocalRoutingReply,
} from "../../src/sugarglider/web/static/local_routing.js";
import {
  createNativeBridgeTransport,
} from "../../src/sugarglider/web/static/native_bridge_transport.js";
import {
  createNativeTrackingBridge,
} from "../../src/sugarglider/web/static/outing_native_bridge.js";

const NONCE = "0123456789abcdef0123456789abcdef";
const ORIGIN = "https://example.test";
const SLUG = "native_outing_slug_12345";
const PARTICIPANT = "native_participant_12345";

export async function runPr32LocalRoutingHarness() {
  const scenarios = [];
  await unavailableScenario();
  scenarios.push("native_local_routing_unavailable");
  await handshakeDiagnosticScenario();
  scenarios.push("native_handshake_unavailable_is_diagnostic");
  await sharedTransportScenario("outing-first");
  scenarios.push("shared_transport_outing_first");
  await sharedTransportScenario("local-first");
  scenarios.push("shared_transport_local_first");
  await unsolicitedTrackingWhileLocalRoutingScenario();
  scenarios.push("unsolicited_tracking_while_local_routing");
  await validRouteScenario();
  scenarios.push("valid_local_route_zero_backend_fetches");
  await marlySmokeTestScenario();
  scenarios.push("marly_smoke_test_fixed_offline_cold_warm");
  await noRouteScenario();
  scenarios.push("no_route_is_explicit");
  malformedReplyScenario();
  scenarios.push("malformed_native_reply_rejected");
  await stalePageReplyScenario();
  scenarios.push("stale_page_reply_ignored");
  await currentRequestRenderingScenario();
  scenarios.push("geometry_rendered_only_for_current_request");
  return scenarios;
}

async function sharedTransportScenario(clientOrder) {
  const port = sharedPort();
  let randomCalls = 0;
  const cryptoObject = {
    getRandomValues(bytes) {
      randomCalls += 1;
      bytes.fill(0x2a);
      return bytes;
    },
  };
  const transport = createNativeBridgeTransport({
    port,
    cryptoObject,
    lifecycleTarget: null,
  });
  const outing = createNativeTrackingBridge({ transport, origin: ORIGIN });
  const local = createLocalRoutingBridge({ transport });
  const clients = clientOrder === "outing-first"
    ? [outing, local]
    : [local, outing];
  equal(await clients[0].initialize(), true, `${clientOrder} first client trusts Hello`);
  equal(await clients[1].initialize(), true, `${clientOrder} second client reuses Hello`);

  equal(randomCalls, 1, `${clientOrder} creates one page nonce`);
  equal(port.onmessageAssignments, 1, `${clientOrder} has one onmessage owner`);
  equal(
    port.requests.filter((value) => value.type === "hello").length,
    1,
    `${clientOrder} posts one Hello`,
  );

  const trackingEvents = [];
  outing.subscribe((event) => trackingEvents.push(event));
  const initialEventCount = trackingEvents.length;
  let outingSettled = false;
  let localSettled = false;
  const outingRequest = outing.getStatus().then((reply) => {
    outingSettled = true;
    return reply;
  });
  const localRequest = local.capabilities().then((reply) => {
    localSettled = true;
    return reply;
  });
  await wait(0);

  const outingMessage = port.requests.find((value) => value.type === "get_status");
  const localMessage = port.requests.find(
    (value) => value.type === "get_local_route_capabilities",
  );
  assert(outingMessage && localMessage, `${clientOrder} posts both client requests`);
  port.reply(capabilityReply(outingMessage.request_id, true, true));
  port.reply(trackingReply(localMessage.request_id));
  port.reply(trackingReply(`web-${"2a".repeat(16)}-999`));
  await wait(0);
  assert(!outingSettled, `${clientOrder} local reply cannot resolve outing request`);
  assert(!localSettled, `${clientOrder} outing reply cannot resolve local request`);
  equal(
    trackingEvents.length,
    initialEventCount,
    `${clientOrder} unknown web request is ignored`,
  );

  port.reply(trackingReply(outingMessage.request_id));
  port.reply(capabilityReply(localMessage.request_id, true, true));
  const [status, capabilities] = await Promise.all([outingRequest, localRequest]);
  equal(status.state, "stopped", `${clientOrder} outing receives its own reply`);
  equal(capabilities.installed_pack_count, 1, `${clientOrder} local receives its own reply`);
  const requestIds = port.requests.map((value) => value.request_id);
  equal(
    new Set(requestIds).size,
    requestIds.length,
    `${clientOrder} request IDs are globally unique`,
  );
  assert(
    requestIds.every((requestId) => requestId.startsWith(`web-${"2a".repeat(16)}-`)),
    `${clientOrder} requests share one nonce`,
  );
}

async function unsolicitedTrackingWhileLocalRoutingScenario() {
  const port = sharedPort();
  const transport = createNativeBridgeTransport({
    port,
    pageNonce: NONCE,
    lifecycleTarget: null,
  });
  const outing = createNativeTrackingBridge({ transport, origin: ORIGIN });
  const local = createLocalRoutingBridge({ transport });
  const events = [];
  outing.subscribe((event) => events.push(event));
  await Promise.all([outing.initialize(), local.initialize()]);
  events.length = 0;

  let routeSettled = false;
  const routing = local.route(routeInput()).then((reply) => {
    routeSettled = true;
    return reply;
  });
  await wait(0);
  const routeMessage = port.requests.find((value) => value.type === "local_route");
  assert(routeMessage, "local route is pending while native broadcasts arrive");
  port.reply(trackingReply(`native-${NONCE}-1`, true));
  port.reply(terminalFailureReply(`native-${NONCE}-2`));
  await wait(0);

  assert(!routeSettled, "tracking broadcast does not resolve local route");
  equal(events.length, 2, "status and terminal failure both reach outing subscriber");
  equal(events[0].kind, "status", "tracking status is dispatched safely");
  equal(
    events[1].kind,
    "permanent_failure",
    "terminal failure is dispatched safely",
  );
  port.reply(routeReply(routeMessage.request_id));
  equal((await routing).type, "local_route_result", "local route remains correlated");
}

async function marlySmokeTestScenario() {
  let routeCount = 0;
  const port = fakePort((request) => {
    if (request.type === "hello") return helloReply(request.request_id);
    if (request.type === "get_local_route_capabilities") {
      return capabilityReply(request.request_id, true, true);
    }
    if (request.type === "local_route") {
      routeCount += 1;
      return routeReply(request.request_id, routeCount === 1);
    }
    return null;
  });
  let plannerStateReads = 0;
  const rig = experimentRig(
    localBridgeFor(port),
    () => {
      plannerStateReads += 1;
      return [{ lat: -30, lon: -40 }, { lat: -50, lon: -60 }];
    },
  );
  const originalFetch = globalThis.fetch;
  let backendFetches = 0;
  globalThis.fetch = async () => {
    backendFetches += 1;
    throw new Error("Marly smoke test attempted backend access");
  };
  try {
    await rig.experiment.bind();
    await rig.experiment.requestSmokeTest();
    assert(rig.status.includes("Cold local Valhalla experiment"), "cold result labeled");
    assert(rig.status.includes("4 vertices"), "vertex count shown");
    assert(rig.status.includes("0.5.1/valhalla-3.6.3"), "engine version shown");
    assert(rig.status.includes("PSS before initialization"), "PSS metrics shown");
    await rig.experiment.requestSmokeTest();
    assert(rig.status.includes("Warm local Valhalla experiment"), "warm result labeled");
    equal(plannerStateReads, 0, "smoke test ignores normal planner state");
    equal(backendFetches, 0, "smoke test makes no fetch");
    const requests = port.requests.filter((value) => value.type === "local_route");
    equal(requests.length, 2, "same smoke action can run twice");
    for (const request of requests) {
      equal(request.origin, MARLY_OFFLINE_SMOKE_TEST.origin, "fixed Marly origin");
      equal(
        request.destination,
        MARLY_OFFLINE_SMOKE_TEST.destination,
        "fixed Saint-Germain destination",
      );
      equal(request.profile, "hike", "fixed public profile");
    }
    equal(rig.rendered.length, 2, "cold and warm graph geometry rendered");
  } finally {
    globalThis.fetch = originalFetch;
    rig.fixture.remove();
  }
}

async function unavailableScenario() {
  const bridge = localBridgeFor(null);
  equal(await bridge.capabilities(), null, "ordinary browser has no native route");
}

async function handshakeDiagnosticScenario() {
  const silentPort = fakePort(() => null);
  const bridge = localBridgeFor(silentPort, {
    schedule: (callback) => {
      queueMicrotask(callback);
      return 1;
    },
    cancelScheduled() {},
  });
  const rig = experimentRig(bridge);
  await rig.experiment.bind();
  assert(!rig.fixture.classList.contains("hidden"), "native timeout is visible");
  equal(rig.status, "Native routing handshake unavailable.", "diagnostic is explicit");
  assert(rig.buttons.every((button) => button.disabled), "diagnostic actions disabled");
  rig.fixture.remove();

  const releaseRig = experimentRig({
    nativeAvailable: true,
    capabilities: async () => ({ enabled: false }),
    invalidate() {},
  });
  await releaseRig.experiment.bind();
  assert(releaseRig.fixture.classList.contains("hidden"), "disabled release stays hidden");
  releaseRig.fixture.remove();

  const noPackRig = experimentRig({
    nativeAvailable: true,
    capabilities: async () => ({
      enabled: true,
      installed_pack_count: 0,
      installed_pack_ids: [],
    }),
    invalidate() {},
  });
  await noPackRig.experiment.bind();
  assert(!noPackRig.fixture.classList.contains("hidden"), "empty registry is visible");
  equal(
    noPackRig.status,
    "No valid regional routing packs are installed.",
    "empty registry diagnostic is explicit",
  );
  assert(noPackRig.buttons.every((button) => button.disabled), "empty registry disables actions");
  noPackRig.fixture.remove();
}

async function validRouteScenario() {
  const port = fakePort((request) => {
    if (request.type === "hello") return helloReply(request.request_id);
    if (request.type === "get_local_route_capabilities") {
      return capabilityReply(request.request_id, true, true);
    }
    if (request.type === "local_route") return routeReply(request.request_id);
    return null;
  });
  const bridge = localBridgeFor(port);
  const capabilities = await bridge.capabilities();
  assert(capabilities.enabled && capabilities.installed_pack_count === 1, "debug pack ready");

  const originalFetch = globalThis.fetch;
  let backendFetches = 0;
  globalThis.fetch = async () => {
    backendFetches += 1;
    throw new Error("Local route attempted backend access");
  };
  try {
    const reply = await bridge.route({
      origin: { lat: 48.8715, lon: 2.0965 },
      destination: { lat: 48.8983, lon: 2.0969 },
      profile: "hike",
    });
    equal(reply.geometry.length, 4, "graph geometry preserved");
    equal(backendFetches, 0, "bridge route makes no fetch");
    const request = port.requests.find((value) => value.type === "local_route");
    equal(Object.keys(request).sort(), [
      "destination", "origin", "profile", "request_id", "schema_version", "type",
    ], "local request has strict non-secret fields");
    assert(!JSON.stringify(request).includes("participant"), "no outing authority");
  } finally {
    globalThis.fetch = originalFetch;
  }
}

async function noRouteScenario() {
  const reply = parseLocalRoutingReply(JSON.stringify({
    schema_version: 1,
    request_id: `web-${NONCE}-3`,
    type: "local_route_failure",
    code: "no_route",
  }));
  equal(reply.code, "no_route", "no route remains distinct");
  const rig = experimentRig({
    capabilities: async () => ({
      enabled: true,
      installed_pack_count: 1,
      installed_pack_ids: ["marly-dev-v1"],
    }),
    route: async () => reply,
    invalidate() {},
  });
  await rig.experiment.bind();
  await rig.experiment.requestSmokeTest();
  assert(rig.status.includes("(no_route)"), "native failure code remains visible");
  rig.fixture.remove();
}

function malformedReplyScenario() {
  const reply = routeReply(`web-${NONCE}-3`);
  reply.geometry = [[2.0965, 48.8715]];
  equal(parseLocalRoutingReply(JSON.stringify(reply)), null, "one-point shape rejected");
  const unexpected = routeReply(`web-${NONCE}-3`);
  unexpected.participant_token = "forbidden";
  equal(parseLocalRoutingReply(JSON.stringify(unexpected)), null, "extra secret rejected");
}

async function stalePageReplyScenario() {
  const port = fakePort((request) => (
    request.type === "hello" ? helloReply(request.request_id) : null
  ));
  const bridge = localBridgeFor(port);
  await bridge.initialize();
  const first = bridge.route(routeInput());
  await wait(0);
  const second = bridge.route(routeInput());
  await wait(0);
  const requests = port.requests.filter((value) => value.type === "local_route");
  port.reply(routeReply(requests[0].request_id));
  port.reply(routeReply(requests[1].request_id));
  equal(await first, null, "superseded request reply ignored");
  assert((await second)?.type === "local_route_result", "current reply accepted");

  const third = bridge.route(routeInput());
  await wait(0);
  bridge.invalidate();
  equal(await third, null, "navigation invalidation resolves pending request as stale");
}

async function currentRequestRenderingScenario() {
  const pending = [];
  const bridge = {
    capabilities: async () => ({
      enabled: true,
      installed_pack_count: 1,
      installed_pack_ids: ["marly-dev-v1"],
    }),
    route: () => new Promise((resolve) => pending.push(resolve)),
    invalidate() {},
  };
  const rig = experimentRig(bridge, () => {
    throw new Error("smoke request read normal planner points");
  });
  await rig.experiment.bind();
  const first = rig.experiment.requestSmokeTest();
  const second = rig.experiment.requestSmokeTest();
  pending[0](routeReply(`web-${NONCE}-2`));
  await first;
  equal(rig.rendered.length, 0, "superseded geometry not rendered");
  pending[1](routeReply(`web-${NONCE}-3`));
  await second;
  equal(rig.rendered.length, 1, "only current geometry rendered");
  equal(rig.rendered[0].length, 4, "complete graph line rendered");
  rig.fixture.remove();
}

function experimentRig(bridge, getPoints = () => [
  { lat: 48.8715, lon: 2.0965 },
  { lat: 48.8983, lon: 2.0969 },
]) {
  const fixture = document.createElement("section");
  fixture.className = "hidden";
  fixture.innerHTML = `
    <button type="button" disabled aria-busy="false">Route</button>
    <button class="smoke" type="button" disabled aria-busy="false">Smoke</button>
    <button class="paris" type="button" disabled aria-busy="false">Paris</button>
    <button class="cross" type="button" disabled aria-busy="false">Cross</button>
    <p></p>
  `;
  document.body.append(fixture);
  const rendered = [];
  let clears = 0;
  const experiment = createLocalRoutingExperiment({
    bridge,
    getPoints,
    renderRoute: (geometry) => rendered.push(geometry),
    clearRoute: () => { clears += 1; },
    elements: {
      container: fixture,
      button: fixture.querySelector("button:not(.smoke)"),
      smokeButton: fixture.querySelector("button.smoke"),
      parisSmokeButton: fixture.querySelector("button.paris"),
      crossPackButton: fixture.querySelector("button.cross"),
      status: fixture.querySelector("p"),
    },
  });
  return {
    experiment,
    fixture,
    rendered,
    buttons: [...fixture.querySelectorAll("button")],
    get clears() { return clears; },
    get status() { return fixture.querySelector("p").textContent; },
  };
}

function fakePort(responder) {
  const port = {
    onmessage: null,
    requests: [],
    postMessage(payload) {
      const request = JSON.parse(payload);
      this.requests.push(request);
      const reply = responder(request);
      if (reply) queueMicrotask(() => this.reply(reply));
    },
    reply(value) {
      this.onmessage?.({ data: JSON.stringify(value) });
    },
  };
  return port;
}

function sharedPort() {
  let messageHandler = null;
  let onmessageAssignments = 0;
  const port = {
    requests: [],
    postMessage(payload) {
      const request = JSON.parse(payload);
      this.requests.push(request);
      if (request.type === "hello") {
        queueMicrotask(() => this.reply(helloReply(request.request_id)));
      }
    },
    reply(value) {
      messageHandler?.({ data: JSON.stringify(value) });
    },
    get onmessageAssignments() {
      return onmessageAssignments;
    },
  };
  Object.defineProperty(port, "onmessage", {
    configurable: false,
    enumerable: true,
    get() {
      return messageHandler;
    },
    set(callback) {
      onmessageAssignments += 1;
      messageHandler = callback;
    },
  });
  return port;
}

function localBridgeFor(port, transportOptions = {}) {
  const transport = createNativeBridgeTransport({
    port,
    pageNonce: NONCE,
    lifecycleTarget: null,
    ...transportOptions,
  });
  return createLocalRoutingBridge({ transport });
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

function capabilityReply(requestId, enabled, installed) {
  const installedPackIds = installed ? ["marly-dev-v1"] : [];
  return {
    schema_version: 1,
    request_id: requestId,
    type: "local_route_capabilities_result",
    enabled,
    engine: "valhalla-mobile",
    engine_version: "0.5.1/valhalla-3.6.3",
    installed_pack_count: installedPackIds.length,
    installed_pack_ids: installedPackIds,
  };
}

function trackingReply(requestId, active = false) {
  return {
    schema_version: 1,
    request_id: requestId,
    type: "tracking_status",
    outing_slug: active ? SLUG : null,
    participant_id: active ? PARTICIPANT : null,
    active,
    state: active ? "sharing" : "stopped",
    last_published_at: null,
    pending_sample: false,
    stop_warning: null,
  };
}

function terminalFailureReply(requestId) {
  return {
    schema_version: 1,
    request_id: requestId,
    type: "permanent_failure",
    code: "participant_not_found",
    event_id: 7,
    outing_slug: SLUG,
    participant_id: PARTICIPANT,
  };
}

function routeReply(requestId, coldStart = true) {
  const geometry = [
    [2.0966, 48.8716],
    [2.089, 48.879],
    [2.084, 48.89],
    [2.0968, 48.8982],
  ];
  return {
    schema_version: 1,
    request_id: requestId,
    type: "local_route_result",
    profile: "hike",
    engine: "valhalla-mobile",
    engine_version: "0.5.1/valhalla-3.6.3",
    pack_id: "marly-dev-v1",
    distance_m: 3450.5,
    duration_s: 2600,
    geometry,
    snapped_origin: { lat: geometry[0][1], lon: geometry[0][0] },
    snapped_destination: { lat: geometry.at(-1)[1], lon: geometry.at(-1)[0] },
    measurements: {
      cold_start: coldStart,
      engine_initialization_ms: 80,
      route_ms: 12,
      memory_before_initialization_bytes: 1000,
      memory_after_initialization_bytes: 2000,
      memory_after_route_bytes: 2100,
    },
  };
}

function routeInput() {
  return {
    origin: { lat: 48.8715, lon: 2.0965 },
    destination: { lat: 48.8983, lon: 2.0969 },
    profile: "hike",
  };
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function equal(actual, expected, message) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${message}: ${JSON.stringify(actual)} !== ${JSON.stringify(expected)}`);
  }
}
