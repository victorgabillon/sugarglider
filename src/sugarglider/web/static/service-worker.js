import {
  cacheFirstStatic,
  classifyShellRequest,
  createCurrentCacheAccess,
  networkFirstNavigation,
} from "/static/service_worker_policy.js";

const SHELL_CACHE_PREFIX = "sugarglider-shell-";
const SHELL_CACHE = `${SHELL_CACHE_PREFIX}v31`;
const ROOT_SHELL = "/";
const shellCache = createCurrentCacheAccess(caches, SHELL_CACHE);

const CORE_ASSETS = Object.freeze([
  ROOT_SHELL,
  "/static/styles.css",
  "/static/vendor/maplibre-gl-4.7.1/maplibre-gl.css",
  "/static/vendor/maplibre-gl-4.7.1/maplibre-gl.js",
  "/static/vendor/pmtiles-4.5.0/pmtiles.js",
  "/static/vendor/protomaps-basemaps-5.7.2/basemaps.js",
  "/static/app.js",
  "/static/avatar.js",
  "/static/api.js",
  "/static/format.js",
  "/static/gpx.js",
  "/static/local_gpx_export.js",
  "/static/local_gpx_client.js",
  "/static/native_gpx_save.js",
  "/static/local_gpx_worker.js",
  "/static/public_profile_metadata.js",
  "/static/icons.js",
  "/static/map.js",
  "/static/map_pack_manifest.js",
  "/static/map_pack_store.js",
  "/static/opfs_pmtiles_source.js",
  "/static/offline_map.js",
  "/static/state.js",
  "/static/saved_routes.js",
  "/static/outings.js",
  "/static/outing_controller.js",
  "/static/outing_live.js",
  "/static/outing_live_lifecycle.js",
  "/static/outing_live_state.js",
  "/static/native_bridge_transport.js",
  "/static/outing_native_bridge.js",
  "/static/local_routing.js",
  "/static/local_auto_tour.js",
  "/static/local_planning_context.js",
  "/static/canonical_numbers.js",
  "/static/local_analysis_templates.js",
  "/static/local_plan_geometry.js",
  "/static/local_candidate_enrichment.js",
  "/static/local_candidate_evaluator.js",
  "/static/local_plan_publisher.js",
  "/static/local_plan_worker.js",
  "/static/local_plan_client.js",
  "/static/local_waypoint_route.js",
  "/static/regional_manifest.js",
  "/static/local_region_data.js",
  "/static/local_region_store.js",
  "/static/local_region_worker.js",
  "/static/local_region_client.js",
  "/static/local_region_panel.js",
  "/static/outing_tracking.js",
  "/static/planner_location.js",
  "/static/outing_view.js",
  "/static/pwa_controller.js",
  "/static/pwa_store.js",
  "/static/pwa_view.js",
  "/static/pwa_runtime.js",
  "/static/pwa_network.js",
  "/static/service_worker_policy.js",
  "/static/offline_snapshots.js",
  "/static/outing_durable_session.js",
  "/static/trail_profile.js",
  "/static/brand/sugarglider-compact-icon.png",
  "/static/brand/sugarglider-map-pin.png",
  "/static/brand/sugarglider-water-pin.png",
  "/static/brand/gps-recenter-default.png",
  "/static/brand/gps-recenter-active.png",
  "/static/brand/profile-badges/blue.png",
  "/static/brand/profile-badges/forest.png",
  "/static/brand/profile-badges/orange.png",
  "/static/brand/profile-badges/tomato.png",
  "/static/brand/profile-badges/mask.png",
  "/static/pwa/icon-192.png",
  "/static/pwa/icon-512.png",
]);

function navigationResponse(request) {
  return networkFirstNavigation(request, {
    fetchRequest: fetch,
    matchRootShell: () => shellCache.match(ROOT_SHELL),
    fallbackResponse: () => new Response(
      "Sugarglider is offline and its application shell is unavailable.",
      {
        status: 503,
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      },
    ),
  });
}

function staticResponse(request) {
  return cacheFirstStatic(request, {
    matchRequest: (candidate) => shellCache.match(candidate),
    fetchRequest: fetch,
    storeResponse: (candidate, response) => shellCache.put(
      candidate,
      response,
    ),
  });
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(CORE_ASSETS)),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => Promise.all(
      cacheNames
        .filter((name) => (
          name.startsWith(SHELL_CACHE_PREFIX) && name !== SHELL_CACHE
        ))
        .map((name) => caches.delete(name)),
    )).then(() => self.clients.claim()),
  );
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "ACTIVATE_UPDATE") {
    event.waitUntil(self.skipWaiting());
  }
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const classification = classifyShellRequest(request, self.location.origin);
  if (classification === "navigation") {
    event.respondWith(navigationResponse(request));
    return;
  }
  if (classification === "static") {
    event.respondWith(staticResponse(request));
  }
});
