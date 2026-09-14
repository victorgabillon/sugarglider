// Only platform/storage fixtures: the application owns all planner state and events.
import { distribution } from "./pr42_region_components_harness.js";
import { createRegionVersionStore } from "../../src/sugarglider/web/static/region_versions.js";
import { createVersionedRegionComponents } from "../../src/sugarglider/web/static/region_components.js";
import { openPwaStore, PWA_STORES } from "../../src/sugarglider/web/static/pwa_store.js";

export async function installStartupRegion() {
  const fixture = await (await fetch("/tests/fixtures/pr40_regional_data.json")).json();
  // Translate the synthetic fixture around the unchanged bundled initial center.
  // This keeps the sole test interaction inside installed coverage without moving
  // the map or changing application configuration/defaults before the tap.
  const offset = [2.09, 48.86];
  const translate = (value) => typeof value[0] === "number"
    ? value.map((number, index) => number + offset[index % 2]) : value.map(translate);
  fixture.manifest.bounds = translate(fixture.manifest.bounds);
  fixture.manifest.source.header_bounds = translate(fixture.manifest.source.header_bounds);
  fixture.pois.metadata.bounding_box = translate(fixture.pois.metadata.bounding_box);
  fixture.nature.metadata.bounding_box = translate(fixture.nature.metadata.bounding_box);
  fixture.nature.metadata.reference_latitude += offset[1];
  for (const feature of fixture.pois.features) {
    for (const coordinate of [feature.coordinate, ...feature.approach_candidates.map((row) => row.coordinate)]) {
      coordinate.lon += offset[0]; coordinate.lat += offset[1];
    }
  }
  for (const feature of fixture.nature.features) feature.geometry.coordinates = translate(feature.geometry.coordinates);
  // The golden index fixture uses placeholder native bytes; the bridge reference
  // requires a tar-aligned archive descriptor, as in native regional fixtures.
  fixture.manifest.components.routing.files[1].byte_size = 512;
  const { manifest, files } = await distribution(fixture, "Startup fixture");
  const versions = createRegionVersionStore();
  const components = (value, directory) => createVersionedRegionComponents({ manifest: value, directory,
    fetchResource: async (url) => {
      const bytes = files.get(new URL(url).pathname.slice(1));
      if (!bytes) throw new Error(`Unexpected fixture download: ${url}`);
      return new Response(bytes, { headers: { "Content-Length": String(bytes.byteLength) } });
    }, pageLocation: location });
  const ticket = await versions.stage(JSON.stringify(manifest));
  await versions.withStagedVersion(ticket, async ({ manifest: value, directory }) => {
    const scoped = await components(value, directory);
    await scoped.installMap(`${location.origin}/manifest.json`);
    await scoped.installIndexes(`${location.origin}/manifest.json`);
  });
  await versions.activate(ticket, { verifyComponent: async (kind, value, directory) => {
    const scoped = await components(value, directory);
    if (kind === "routing") return true; // Native boundary attestation; JVM tests cover native storage.
    if (kind === "map") return scoped.verifyMap();
    await scoped.openIndexes(); return true;
  } });
  const store = await openPwaStore();
  await store.put(PWA_STORES.trailProfile, "current", {
    schema_version: 1, display_name: "Startup test", avatar_key: "blue",
  });
  store.close();
  return manifest;
}

// Installed before document scripts by CDP, standing in only for Android's message port.
export function installNativeFixture() {
  const profiles = ["trail_run", "hike", "city_bike", "gravel_bike", "mountain_bike", "road_bike"];
  globalThis.nativeFixtureRequests = [];
  globalThis.sugargliderNative = {
    onmessage: null,
    postMessage(payload) {
      const request = JSON.parse(payload);
      globalThis.nativeFixtureRequests.push(request);
      let reply;
      if (request.type === "hello") {
        reply = { type: "hello_result", outing_slug: null, participant_id: null, active: false,
          state: "stopped", last_published_at: null, pending_sample: false, stop_warning: null };
      } else if (request.type === "get_local_route_capabilities") {
        const pack = request.regional_reference?.pack_id;
        const modes = globalThis.nativeFixtureAccessModes ?? ["foot", "bicycle"];
        const supported = profiles.filter((id) => modes.includes(["trail_run", "hike"].includes(id) ? "foot" : "bicycle"));
        reply = { type: "local_route_capabilities_result", enabled: true,
          engine: "valhalla-mobile", engine_version: "0.5.1/valhalla-3.6.3",
          installed_pack_count: pack ? 1 : 0, installed_pack_ids: pack ? [pack] : [],
          supported_profile_ids: pack ? supported : [],
          pack_capabilities: pack ? [{ pack_id: pack, access_modes: modes }] : [] };
      } else throw new Error(`Unexpected native request: ${request.type}`);
      queueMicrotask(() => this.onmessage?.({ data: JSON.stringify({ schema_version: 1,
        request_id: request.request_id, ...reply }) }));
    },
  };
}

// Read-only observation of the same modules used by index.html; no helper drives planner state.
export async function startupSnapshot() {
  const { state } = await import("/static/state.js");
  const { currentViewportBounds } = await import("/static/map.js");
  const get = (id) => document.getElementById(id);
  const canvas = document.querySelector(".maplibregl-canvas");
  const rect = canvas?.getBoundingClientRect();
  const marker = document.querySelector(".required-marker-start")?.closest(".required-marker");
  const markerRect = marker?.getBoundingClientRect();
  // The canonical pin has transparent padding: map.js anchors its painted tip
  // 16px above the 72px START element bottom.
  return { mode: state.planningMode, topology: state.autoTour.routeTopology,
    start: state.autoTour.start, end: state.autoTour.end, points: state.points,
    profile: state.routingProfile, profileLabel: get("profile")?.selectedOptions[0]?.textContent,
    profiles: state.routingProfileCatalog?.profiles,
    profileAvailable: Boolean(state.routingProfileCatalog?.profiles.find((row) => row.profile.id === state.routingProfile)?.available),
    startFields: [get("hard-start-lat")?.value, get("hard-start-lon")?.value],
    validation: get("poi-validation")?.textContent,
    status: get("request-status")?.textContent, help: get("profile-description")?.textContent,
    disabled: [get("generate")?.disabled, get("generate-top")?.disabled],
    regionRefreshDisabled: get("regional-refresh")?.disabled,
    region: get("regional-status")?.textContent, regionValue: get("planning-region")?.value,
    marker: marker && { title: marker.title, text: marker.textContent, x: markerRect.x + markerRect.width / 2, y: markerRect.bottom - 16 },
    canvas: rect && { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    bounds: canvas && currentViewportBounds(),
    error: get("error-message")?.textContent, modal: document.querySelector("dialog[open]")?.id,
  };
}
