import {
  nativeBridgeTransport,
} from "./native_bridge_transport.js";

const SCHEMA_VERSION = 1;
const LOCAL_ROUTE_VERSION = 2;
const MIN_ROUTE_POINTS = 2;
const MAX_ROUTE_POINTS = 16;
const MAX_ROUTE_VERTICES = 20_000;
const ROUTE_TIMEOUT_MS = 90_000;
export const PUBLIC_LOCAL_ROUTE_PROFILES = Object.freeze([
  "trail_run", "hike", "city_bike", "gravel_bike", "mountain_bike", "road_bike",
]);
const PROFILE_ACCESS_MODE = Object.freeze({
  trail_run: "foot",
  hike: "foot",
  city_bike: "bicycle",
  gravel_bike: "bicycle",
  mountain_bike: "bicycle",
  road_bike: "bicycle",
});
const ACCESS_MODES = Object.freeze(["foot", "bicycle"]);
const CAPABILITY_FIELDS = new Set([
  "schema_version", "request_id", "type", "enabled", "engine",
  "engine_version", "installed_pack_count", "installed_pack_ids",
  "supported_profile_ids", "pack_capabilities",
]);
const PACK_CAPABILITY_FIELDS = new Set(["pack_id", "access_modes"]);
const ROUTE_FIELDS = new Set([
  "schema_version", "request_id", "type", "profile", "engine",
  "engine_version", "pack_id", "distance_m", "duration_s", "geometry",
  "snapped_points", "measurements",
]);
const FAILURE_FIELDS = new Set([
  "schema_version", "request_id", "type", "code",
]);
const COORDINATE_FIELDS = new Set(["lat", "lon"]);
const MEASUREMENT_FIELDS = new Set([
  "cold_start", "engine_initialization_ms", "route_ms",
  "memory_before_initialization_bytes", "memory_after_initialization_bytes",
  "memory_after_route_bytes",
]);
const FAILURE_CODES = new Set([
  "invalid_request", "unsupported_profile", "routing_pack_unavailable",
  "no_covering_routing_pack", "no_compatible_routing_pack", "no_route", "route_too_large",
  "routing_busy", "routing_failure",
]);
export const MARLY_OFFLINE_SMOKE_TEST = Object.freeze({
  points: Object.freeze([
    Object.freeze({ lat: 48.8715, lon: 2.0965 }),
    Object.freeze({ lat: 48.8983, lon: 2.0969 }),
  ]),
  profile: "hike",
});
export const PARIS_OFFLINE_SMOKE_TEST = Object.freeze({
  points: Object.freeze([
    Object.freeze({ lat: 48.8584, lon: 2.2945 }),
    Object.freeze({ lat: 48.8606, lon: 2.3376 }),
  ]),
  profile: "hike",
});
export const MARLY_VIA_SMOKE_TEST = Object.freeze({
  points: Object.freeze([
    MARLY_OFFLINE_SMOKE_TEST.points[0],
    Object.freeze({ lat: 48.8840, lon: 2.0830 }),
    MARLY_OFFLINE_SMOKE_TEST.points[1],
  ]),
  profile: "hike",
});
export const CROSS_PACK_FAILURE_TEST = Object.freeze({
  points: Object.freeze([
    MARLY_OFFLINE_SMOKE_TEST.points[0],
    PARIS_OFFLINE_SMOKE_TEST.points[1],
  ]),
  profile: "hike",
});

export function createLocalRoutingBridge({
  transport = nativeBridgeTransport,
} = {}) {
  const nativeAvailable = transport.nativeAvailable;
  let trusted = false;
  let operationCounter = 0;
  let currentOperation = 0;
  let initialization = null;
  const requestOwner = Object.freeze({ client: "local-routing" });

  async function initialize() {
    if (initialization) return initialization;
    initialization = transport.initialize().then((payload) => {
      const reply = parseLocalRoutingReply(payload);
      trusted = reply?.type === "hello_result";
      return trusted;
    }).catch(() => false);
    return initialization;
  }

  async function capabilities() {
    if (!await initialize()) return null;
    const reply = await request(
      "get_local_route_capabilities", {}, 5_000, null,
    );
    return reply?.type === "local_route_capabilities_result" ? reply : null;
  }

  async function route({ points, profile = "hike" }) {
    if (!await initialize()) return null;
    const operation = ++operationCounter;
    currentOperation = operation;
    const reply = await request("local_route", {
      route_version: LOCAL_ROUTE_VERSION,
      profile,
      points: points.map(({ lat, lon }) => ({ lat, lon })),
    }, ROUTE_TIMEOUT_MS, operation);
    return operation === currentOperation ? reply : null;
  }

  function invalidate() {
    currentOperation = ++operationCounter;
    transport.cancelOwner(requestOwner);
  }

  async function request(type, fields, timeoutMs, operation) {
    const reply = await transport.request(type, fields, {
      owner: requestOwner,
      parseReply: parseLocalRoutingReply,
      timeoutMs,
    });
    return operation !== null && operation !== currentOperation ? null : reply;
  }

  return Object.freeze({
    nativeAvailable,
    initialize,
    capabilities,
    route,
    invalidate,
  });
}

export function createLocalRoutingExperiment({
  bridge = createLocalRoutingBridge(),
  getPoints = () => [],
  renderRoute,
  clearRoute,
  elements,
} = {}) {
  let currentRequest = 0;
  let packAvailable = false;
  let supportedProfiles = new Set();

  async function initialize() {
    const capabilities = await bridge.capabilities();
    if (!capabilities) {
      if (bridge.nativeAvailable) {
        elements.container.classList.remove("hidden");
        elements.status.textContent = "Native routing handshake unavailable.";
        setBusy(false);
      }
      return false;
    }
    if (!capabilities.enabled) return false;
    packAvailable = capabilities.installed_pack_count > 0;
    supportedProfiles = new Set(capabilities.supported_profile_ids);
    for (const option of elements.profileSelect.options) {
      option.disabled = !supportedProfiles.has(option.value);
    }
    if (!supportedProfiles.has(elements.profileSelect.value)) {
      elements.profileSelect.value = capabilities.supported_profile_ids[0] ?? "hike";
    }
    elements.container.classList.remove("hidden");
    elements.status.textContent = packAvailable
      ? `${packCapabilitySummary(capabilities)} Supported local profiles: ${
        capabilities.supported_profile_ids.join(", ") || "none"
      }.`
      : "No valid regional routing packs are installed.";
    setBusy(false);
    return true;
  }

  async function requestRoute() {
    const points = getPoints();
    if (!Array.isArray(points) || points.length < MIN_ROUTE_POINTS) {
      elements.status.textContent = "Choose at least two planner points for local routing.";
      return null;
    }
    if (points.length > MAX_ROUTE_POINTS) {
      elements.status.textContent = `Local routing accepts at most ${MAX_ROUTE_POINTS} points.`;
      return null;
    }
    return runRoute({
      points,
      profile: selectedProfile(),
    });
  }

  function requestSmokeTest() {
    return runFixture(MARLY_OFFLINE_SMOKE_TEST);
  }

  function requestParisSmokeTest() {
    return runFixture(PARIS_OFFLINE_SMOKE_TEST);
  }

  function requestViaSmokeTest() {
    return runFixture(MARLY_VIA_SMOKE_TEST);
  }

  function requestCrossPackTest() {
    return runFixture(CROSS_PACK_FAILURE_TEST);
  }

  function runFixture(fixture) {
    return runRoute({ ...fixture, profile: selectedProfile() });
  }

  function selectedProfile() {
    return elements.profileSelect.value;
  }

  async function runRoute(input) {
    const request = ++currentRequest;
    setBusy(true);
    elements.status.textContent = "Calculating with the local Valhalla experiment…";
    const reply = await bridge.route(input);
    if (request !== currentRequest) return null;
    setBusy(false);
    if (reply?.type === "local_route_result") {
      renderRoute(reply.geometry);
      const duration = reply.duration_s === null
        ? "duration unavailable"
        : `${Math.round(reply.duration_s / 60)} min`;
      const measurements = reply.measurements;
      const pss = [
        measurements.memory_before_initialization_bytes,
        measurements.memory_after_initialization_bytes,
        measurements.memory_after_route_bytes,
      ].map((value) => (value / 1_048_576).toFixed(1));
      elements.status.textContent = (
        `${measurements.cold_start ? "Cold" : "Warm"} local Valhalla experiment · `
        + `${(reply.distance_m / 1_000).toFixed(2)} km · ${duration} · `
        + `${reply.geometry.length} vertices · ${reply.snapped_points.length} snapped points · `
        + `profile ${reply.profile} · pack ${reply.pack_id} · `
        + `engine ${reply.engine} `
        + `${reply.engine_version} · initialization `
        + `${measurements.engine_initialization_ms} ms · route `
        + `${measurements.route_ms} ms · PSS before initialization ${pss[0]} MiB / `
        + `after initialization ${pss[1]} MiB / after routing ${pss[2]} MiB`
      );
      return reply;
    }
    clearRoute();
    elements.status.textContent = failureMessage(reply?.code);
    return reply;
  }

  function bind() {
    elements.button.addEventListener("click", requestRoute);
    elements.smokeButton.addEventListener("click", requestSmokeTest);
    elements.parisSmokeButton.addEventListener("click", requestParisSmokeTest);
    elements.viaSmokeButton.addEventListener("click", requestViaSmokeTest);
    elements.crossPackButton.addEventListener("click", requestCrossPackTest);
    elements.profileSelect.addEventListener("change", () => setBusy(false));
    return initialize();
  }

  function setBusy(busy) {
    for (const button of [
      elements.button,
      elements.smokeButton,
      elements.parisSmokeButton,
      elements.viaSmokeButton,
      elements.crossPackButton,
    ]) {
      button.disabled = busy || !packAvailable || !supportedProfiles.has(selectedProfile());
      button.setAttribute("aria-busy", String(busy));
    }
    elements.profileSelect.disabled = busy || !packAvailable;
  }

  function invalidate() {
    currentRequest += 1;
    bridge.invalidate();
    clearRoute();
  }

  return Object.freeze({
    bind,
    initialize,
    requestRoute,
    requestSmokeTest,
    requestParisSmokeTest,
    requestViaSmokeTest,
    requestCrossPackTest,
    invalidate,
  });
}

export function parseLocalRoutingReply(payload) {
  let value;
  try {
    value = JSON.parse(payload);
  } catch {
    return null;
  }
  if (!baseReply(value)) return null;
  if (value.type === "hello_result") return validHello(value) ? value : null;
  if (value.type === "local_route_capabilities_result") {
    return exactFields(value, CAPABILITY_FIELDS)
      && typeof value.enabled === "boolean"
      && Number.isSafeInteger(value.installed_pack_count)
      && value.installed_pack_count >= 0
      && value.installed_pack_count <= 64
      && validPackIds(value.installed_pack_ids, value.installed_pack_count)
      && validProfileIds(value.supported_profile_ids)
      && validPackCapabilities(
        value.pack_capabilities,
        value.installed_pack_ids,
        value.supported_profile_ids,
      )
      && safeIdentifier(value.engine)
      && safeVersion(value.engine_version)
      ? value
      : null;
  }
  if (value.type === "local_route_failure") {
    return exactFields(value, FAILURE_FIELDS) && FAILURE_CODES.has(value.code)
      ? value
      : null;
  }
  if (value.type !== "local_route_result" || !exactFields(value, ROUTE_FIELDS)) {
    return null;
  }
  if (
    !PUBLIC_LOCAL_ROUTE_PROFILES.includes(value.profile)
    || !safeIdentifier(value.engine)
    || !safeVersion(value.engine_version)
    || !safePackId(value.pack_id)
    || !positiveFinite(value.distance_m)
    || !(value.duration_s === null || nonNegativeFinite(value.duration_s))
    || !validGeometry(value.geometry)
    || !validSnappedPoints(value.snapped_points)
    || !validMeasurements(value.measurements)
  ) return null;
  const first = value.geometry[0];
  const last = value.geometry[value.geometry.length - 1];
  const snappedFirst = value.snapped_points[0];
  const snappedLast = value.snapped_points.at(-1);
  if (
    first[0] !== snappedFirst.lon
    || first[1] !== snappedFirst.lat
    || last[0] !== snappedLast.lon
    || last[1] !== snappedLast.lat
  ) return null;
  return value;
}

function validHello(value) {
  const fields = new Set([
    "schema_version", "request_id", "type", "outing_slug", "participant_id",
    "active", "state", "last_published_at", "pending_sample", "stop_warning",
  ]);
  return exactFields(value, fields)
    && typeof value.active === "boolean"
    && typeof value.state === "string"
    && typeof value.pending_sample === "boolean";
}

function baseReply(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    && value.schema_version === SCHEMA_VERSION
    && /^[A-Za-z0-9_-]{1,64}$/.test(value.request_id ?? "");
}

function validGeometry(value) {
  return Array.isArray(value)
    && value.length >= 2
    && value.length <= MAX_ROUTE_VERTICES
    && value.every((coordinate) => (
      Array.isArray(coordinate)
      && coordinate.length === 2
      && coordinate.every(Number.isFinite)
      && coordinate[0] >= -180 && coordinate[0] <= 180
      && coordinate[1] >= -90 && coordinate[1] <= 90
    ));
}

function validCoordinateObject(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    && exactFields(value, COORDINATE_FIELDS)
    && Number.isFinite(value.lat) && value.lat >= -90 && value.lat <= 90
    && Number.isFinite(value.lon) && value.lon >= -180 && value.lon <= 180;
}

function validSnappedPoints(value) {
  return Array.isArray(value)
    && value.length >= MIN_ROUTE_POINTS
    && value.length <= MAX_ROUTE_POINTS
    && value.every(validCoordinateObject);
}

function validMeasurements(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    && exactFields(value, MEASUREMENT_FIELDS)
    && typeof value.cold_start === "boolean"
    && [
      value.engine_initialization_ms,
      value.route_ms,
      value.memory_before_initialization_bytes,
      value.memory_after_initialization_bytes,
      value.memory_after_route_bytes,
    ].every((item) => Number.isSafeInteger(item) && item >= 0);
}

function failureMessage(code) {
  const description = {
    routing_pack_unavailable: "The local development routing pack is unavailable.",
    no_covering_routing_pack: "No single installed regional pack covers all requested points.",
    no_compatible_routing_pack: "The region is installed but no pack supports this profile's access mode.",
    no_route: "Valhalla found no graph route between these points.",
    invalid_request: "The local route request was rejected.",
    unsupported_profile: "The local public profile ID is unsupported.",
    route_too_large: "The local route exceeded the bounded result size.",
    routing_busy: "A local route is already being calculated.",
    routing_failure: "The local routing engine failed explicitly; no fallback was used.",
  }[code];
  const explicitCode = FAILURE_CODES.has(code) ? code : "invalid_native_reply";
  return `Local Valhalla experiment failed (${explicitCode}): ${
    description ?? "No valid native reply was received."
  }`;
}

function exactFields(value, expected) {
  const fields = Object.keys(value);
  return fields.length === expected.size
    && fields.every((field) => expected.has(field));
}

function safeIdentifier(value) {
  return typeof value === "string" && /^[A-Za-z0-9._/-]{1,64}$/.test(value);
}

function safeVersion(value) {
  return typeof value === "string" && /^[A-Za-z0-9._/-]{1,96}$/.test(value);
}

function safePackId(value) {
  return typeof value === "string" && /^[a-z0-9][a-z0-9._-]{0,63}$/.test(value);
}

function validPackIds(value, expectedCount) {
  return Array.isArray(value)
    && value.length === expectedCount
    && value.every(safePackId)
    && new Set(value).size === value.length
    && value.every((packId, index) => index === 0 || value[index - 1] < packId);
}

function validProfileIds(value) {
  return Array.isArray(value)
    && value.every((profile) => PUBLIC_LOCAL_ROUTE_PROFILES.includes(profile))
    && value.every((profile, index) => (
      index === 0
      || PUBLIC_LOCAL_ROUTE_PROFILES.indexOf(value[index - 1])
        < PUBLIC_LOCAL_ROUTE_PROFILES.indexOf(profile)
    ));
}

function validPackCapabilities(value, installedPackIds, supportedProfileIds) {
  if (!Array.isArray(value) || value.length !== installedPackIds.length) return false;
  const valid = value.every((pack, index) => (
    pack && typeof pack === "object" && !Array.isArray(pack)
    && exactFields(pack, PACK_CAPABILITY_FIELDS)
    && pack.pack_id === installedPackIds[index]
    && Array.isArray(pack.access_modes)
    && pack.access_modes.length >= 1
    && pack.access_modes.length <= ACCESS_MODES.length
    && pack.access_modes.every((mode) => ACCESS_MODES.includes(mode))
    && pack.access_modes.every((mode, modeIndex) => (
      modeIndex === 0
      || ACCESS_MODES.indexOf(pack.access_modes[modeIndex - 1])
        < ACCESS_MODES.indexOf(mode)
    ))
  ));
  if (!valid) return false;
  const derivedProfiles = PUBLIC_LOCAL_ROUTE_PROFILES.filter((profile) => (
    value.some((pack) => pack.access_modes.includes(PROFILE_ACCESS_MODE[profile]))
  ));
  return JSON.stringify(derivedProfiles) === JSON.stringify(supportedProfileIds);
}

function packCapabilitySummary(capabilities) {
  const packs = capabilities.pack_capabilities.map((pack) => (
    `${pack.pack_id} [${pack.access_modes.join("+")}]`
  ));
  return `Installed regional packs (${capabilities.installed_pack_count}): ${packs.join(", ")}.`;
}

function positiveFinite(value) {
  return Number.isFinite(value) && value > 0;
}

function nonNegativeFinite(value) {
  return Number.isFinite(value) && value >= 0;
}
