import {
  PLANNER_LOCATION_WATCH_OPTIONS,
  PLANNER_PERMISSION_QUERY_TIMEOUT_MS,
  createPlannerLocationController,
} from "../../src/sugarglider/web/static/planner_location.js";

const VIEWPORTS = Object.freeze([
  [360, 800],
  [390, 844],
  [412, 915],
  [600, 900],
  [768, 1024],
  [1280, 800],
  [1440, 900],
]);

export async function runPr31PrivatePlannerLocationHarness() {
  const scenarios = [];
  await grantedPermissionScenario();
  scenarios.push("granted_permission_auto_watch_private_render_follow");
  await promptPermissionScenario();
  scenarios.push("prompt_waits_for_deliberate_control");
  await deniedPermissionScenario();
  scenarios.push("denied_is_graceful_and_not_retried");
  await pendingPermissionsQueryScenario();
  scenarios.push("pending_permissions_query_never_blocks_control");
  await lifecycleScenario();
  scenarios.push("page_lifecycle_clears_and_restarts_one_watch");
  await fallbackScenario();
  scenarios.push("missing_profile_uses_blue_without_history");
  await noPublicationScenario();
  scenarios.push("private_fixes_make_no_network_request");
  await responsiveControlScenario();
  scenarios.push("responsive_control_all_viewports");
  return scenarios;
}

async function grantedPermissionScenario() {
  const rig = createRig({ permission: "granted", avatar: "orange" });
  await rig.controller.initialize();
  equal(rig.geolocation.watchCount(), 1, "granted permission starts watcher");
  equal(rig.centers.length, 0, "automatic marker does not steal camera");
  equal(rig.geolocation.options(), PLANNER_LOCATION_WATCH_OPTIONS, "bounded options");

  rig.geolocation.emit(rawPosition(48.85661, 2.35222, 17, 1_700_000_000_000));
  equal(rig.renders.length, 1, "first fix rendered once");
  equal(
    rig.renders[0],
    {
      fix: {
        coordinate: { lat: 48.85661, lon: 2.35222 },
        accuracy_m: 17,
        captured_at: "2023-11-14T22:13:20.000Z",
      },
      avatar: "orange",
    },
    "exact unsnapped fix, accuracy, and profile avatar rendered",
  );
  equal(rig.centers.length, 0, "first automatic fix remains marker-only");

  rig.control.click();
  equal(rig.centers.length, 1, "control recenters current fix");
  equal(rig.control.getAttribute("aria-pressed"), "true", "follow is pressed");
  assert(
    rig.control.querySelector("img").src.endsWith("gps-recenter-active.png"),
    "active asset used while following",
  );
  rig.geolocation.emit(rawPosition(48.8567, 2.3524, 12, 1_700_000_001_000));
  equal(rig.centers.length, 2, "new fix follows while active");
  rig.controller.manualMapInteraction();
  equal(rig.control.getAttribute("aria-pressed"), "false", "manual pan exits follow");
  equal(rig.clears, 0, "manual pan does not hide marker");
  rig.geolocation.emit(rawPosition(48.8568, 2.3526, 11, 1_700_000_002_000));
  equal(rig.centers.length, 2, "free camera ignores later fixes");
  equal(rig.renders.length, 3, "marker continues updating after manual pan");

  rig.changeAvatar("mask");
  equal(rig.renders.at(-1).avatar, "mask", "profile change updates marker artwork");
  rig.geolocation.emit(rawPosition(NaN, 2, 10, 1_700_000_003_000));
  equal(rig.renders.length, 4, "invalid fix is rejected");
  rig.controller.dispose();
}

async function promptPermissionScenario() {
  const rig = createRig({ permission: "prompt", avatar: "forest" });
  await rig.controller.initialize();
  equal(rig.geolocation.watchCount(), 0, "prompt state makes no load-time request");
  rig.control.click();
  equal(rig.geolocation.watchCount(), 1, "deliberate click starts geolocation");
  equal(rig.control.getAttribute("aria-busy"), "true", "acquisition is busy");
  assert(
    rig.control.querySelector("img").src.endsWith("gps-recenter-default.png"),
    "acquiring retains neutral asset",
  );
  rig.geolocation.emit(rawPosition(43.6, 1.44, 25, 1_700_000_000_000));
  equal(rig.centers.length, 1, "first deliberate fix centers map");
  equal(rig.control.getAttribute("aria-pressed"), "true", "first fix enables follow");
  rig.controller.dispose();
}

async function deniedPermissionScenario() {
  const rig = createRig({ permission: "denied" });
  await rig.controller.initialize();
  equal(rig.geolocation.watchCount(), 0, "denied state does not start geolocation");
  rig.control.click();
  equal(rig.geolocation.watchCount(), 1, "Permissions API denial is advisory");
  rig.geolocation.reject({ code: 1 });
  rig.control.click();
  equal(rig.geolocation.watchCount(), 1, "authoritative denial is not retried");
  assert(rig.status.textContent.includes("blocked"), "blocked state is disclosed");
  rig.controller.dispose();
}

async function pendingPermissionsQueryScenario() {
  const rig = createRig({
    permission: "prompt",
    permissionQuery: () => new Promise(() => {}),
  });
  const initialization = rig.controller.initialize();
  await wait(0);
  equal(rig.geolocation.watchCount(), 0, "pending query causes no automatic prompt");
  rig.control.click();
  equal(rig.geolocation.watchCount(), 1, "control bypasses pending query");
  const settled = await Promise.race([
    initialization.then(() => true),
    wait(PLANNER_PERMISSION_QUERY_TIMEOUT_MS + 500).then(() => false),
  ]);
  assert(settled, "initialization has a bounded permission query timeout");
  rig.controller.dispose();
}

async function lifecycleScenario() {
  const rig = createRig({ permission: "granted" });
  await rig.controller.initialize();
  rig.geolocation.emit(rawPosition(45, 3, 8, 1_700_000_000_000));
  rig.windowTarget.dispatchEvent(new Event("pagehide"));
  equal(rig.geolocation.clearCount(), 1, "pagehide clears owned watch");
  equal(rig.clears, 1, "pagehide drops ephemeral fix");
  equal(rig.controller.diagnostics().currentFix, null, "no fix survives pagehide");
  rig.windowTarget.dispatchEvent(new Event("pageshow"));
  await wait(0);
  equal(rig.geolocation.watchCount(), 2, "pageshow re-evaluates granted permission");
  equal(rig.geolocation.activeCount(), 1, "only one current watch remains");
  rig.controller.dispose();
}

async function fallbackScenario() {
  const rig = createRig({ permission: "prompt", avatar: undefined });
  await rig.controller.initialize();
  rig.control.click();
  for (let index = 0; index < 4; index += 1) {
    rig.geolocation.emit(rawPosition(40 + index, 2, 10, 1_700_000_000_000 + index));
  }
  equal(rig.renders.at(-1).avatar, "blue", "missing profile falls back to blue key");
  const diagnostics = rig.controller.diagnostics();
  equal(diagnostics.currentFix.coordinate.lat, 43, "only latest current fix retained");
  assert(!("history" in diagnostics), "controller exposes no coordinate history");
  rig.controller.dispose();
}

async function noPublicationScenario() {
  const originalFetch = globalThis.fetch;
  let networkCalls = 0;
  globalThis.fetch = async () => {
    networkCalls += 1;
    throw new Error("Private planner location attempted a network request.");
  };
  try {
    const rig = createRig({ permission: "prompt", avatar: "tomato" });
    await rig.controller.initialize();
    rig.control.click();
    rig.geolocation.emit(rawPosition(47, 4, 9, 1_700_000_000_000));
    rig.controller.manualMapInteraction();
    rig.geolocation.emit(rawPosition(47.1, 4.1, 8, 1_700_000_001_000));
    rig.controller.dispose();
    equal(networkCalls, 0, "private fixes never publish or call an API");
  } finally {
    globalThis.fetch = originalFetch;
  }
}

async function responsiveControlScenario() {
  const source = await applicationMarkup();
  for (const [width, height] of VIEWPORTS) {
    const frame = await applicationFrame(source, width, height);
    try {
      const document = frame.contentDocument;
      const control = document.getElementById("planner-location-control");
      control.classList.remove("hidden");
      const attribution = document.createElement("div");
      attribution.textContent = "Map data attribution";
      attribution.style.cssText = "position:absolute;right:0;bottom:0;width:150px;height:24px";
      document.querySelector(".map-panel").append(attribution);
      const controlRect = control.getBoundingClientRect();
      const layersRect = document.querySelector(".map-tools").getBoundingClientRect();
      const legendRect = document.querySelector(".legend").getBoundingClientRect();
      const attributionRect = attribution.getBoundingClientRect();
      assert(controlRect.width >= 44 && controlRect.height >= 44, `touch target ${width}`);
      assert(!overlaps(controlRect, layersRect), `does not cover Layers ${width}`);
      assert(!overlaps(controlRect, legendRect), `does not cover legend ${width}`);
      assert(!overlaps(controlRect, attributionRect), `does not cover attribution ${width}`);
      assert(
        document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        `no horizontal overflow ${width}`,
      );
    } finally {
      frame.remove();
    }
  }
}

function createRig({ permission, avatar = "blue", permissionQuery = null }) {
  const fixture = document.createElement("section");
  fixture.innerHTML = `
    <button type="button" class="hidden" aria-pressed="false">
      <img src="/static/brand/gps-recenter-default.png" alt="">
    </button>
    <p></p>
  `;
  document.body.append(fixture);
  const control = fixture.querySelector("button");
  const status = fixture.querySelector("p");
  const geolocation = fakeGeolocation();
  const permissionStatus = fakePermissionStatus(permission);
  const windowTarget = new EventTarget();
  const renders = [];
  const centers = [];
  let clears = 0;
  let currentAvatar = avatar;
  let avatarListener = null;
  const controller = createPlannerLocationController({
    geolocation: geolocation.api,
    permissions: {
      query: permissionQuery ?? (async () => permissionStatus),
    },
    windowTarget,
    control,
    status,
    renderFix: (fix, avatarKey) => renders.push({ fix, avatar: avatarKey }),
    clearFix: () => { clears += 1; },
    centerFix: (fix) => centers.push(fix),
    avatarKey: () => currentAvatar,
    subscribeAvatar: (listener) => {
      avatarListener = listener;
      return () => { avatarListener = null; };
    },
  });
  return {
    controller,
    geolocation,
    permissionStatus,
    windowTarget,
    control,
    status,
    renders,
    centers,
    get clears() { return clears; },
    changeAvatar(value) {
      currentAvatar = value;
      avatarListener?.();
    },
  };
}

function fakeGeolocation() {
  let nextId = 1;
  const watches = new Map();
  const starts = [];
  let clears = 0;
  return {
    api: {
      watchPosition(success, error, options) {
        const id = nextId;
        nextId += 1;
        watches.set(id, { success, error, options });
        starts.push(id);
        return id;
      },
      clearWatch(id) {
        clears += 1;
        watches.delete(id);
      },
    },
    emit(position) {
      watches.get(starts.at(-1))?.success(position);
    },
    reject(error) {
      watches.get(starts.at(-1))?.error(error);
    },
    watchCount: () => starts.length,
    clearCount: () => clears,
    activeCount: () => watches.size,
    options: () => watches.get(starts.at(-1))?.options,
  };
}

function fakePermissionStatus(state) {
  const target = new EventTarget();
  target.state = state;
  return target;
}

function rawPosition(latitude, longitude, accuracy, timestamp) {
  return {
    coords: {
      latitude,
      longitude,
      accuracy,
      altitude: null,
      speed: null,
      heading: null,
    },
    timestamp,
  };
}

async function applicationMarkup() {
  const response = await fetch(new URL(
    "../../src/sugarglider/web/static/index.html",
    window.location.href,
  ));
  assert(response.ok, "application markup loads");
  const parsed = new DOMParser().parseFromString(await response.text(), "text/html");
  parsed.querySelectorAll("script, link[rel='manifest']").forEach((node) => node.remove());
  parsed.querySelectorAll("link[rel='stylesheet']").forEach((node) => {
    if (node.href.endsWith("/static/styles.css")) {
      node.href = new URL(
        "../../src/sugarglider/web/static/styles.css",
        window.location.href,
      ).href;
    } else {
      node.remove();
    }
  });
  return `<!doctype html>${parsed.documentElement.outerHTML}`;
}

function applicationFrame(source, width, height) {
  return new Promise((resolve, reject) => {
    const frame = document.createElement("iframe");
    frame.style.cssText = `width:${width}px;height:${height}px;border:0`;
    frame.addEventListener("load", () => resolve(frame), { once: true });
    frame.addEventListener("error", reject, { once: true });
    frame.srcdoc = source;
    document.body.append(frame);
  });
}

function overlaps(first, second) {
  return first.left < second.right
    && first.right > second.left
    && first.top < second.bottom
    && first.bottom > second.top;
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function equal(actual, expected, message) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(
      `${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
    );
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
