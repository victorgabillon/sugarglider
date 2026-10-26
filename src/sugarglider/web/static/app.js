import { t, tr, getLanguage, initializeLocalization, onLanguageChange, setLocalizedText } from "./i18n.js";
import { createSelectedRouteElevation } from "./route_elevation.js";
import { initializeAdventureDialog } from "./adventure_dialog.js";
import { nativeBridgeTransport } from "./native_bridge_transport.js";
import { nearbyAdventurePlaceContext } from "./adventure_grounding.js";
import { createAdventureResults } from "./adventure_results.js";
import { renderAdventurePlaces, zoomMap, resetMapNorth, mapViewportPadding } from "./map.js";
import { regionalRoutingReference } from "./regional_routing_reference.js";
import { selectCommittedRegion } from "./regional_planning.js";
import { initializeSourceInformation } from "./data_notices.js";
import { createElevationView } from "./elevation_view.js";
import { clearElevationMapPosition, showElevationMapPosition } from "./map.js";
import { placeCompatibilityMessage } from "./place_capabilities.js";
import { initializeNativeItineraryHandoff } from "./native_itinerary_handoff.js";
import { createLocationSearch } from "./location_search.js";
import { initializeLocationSearchDialog } from "./location_search_dialog.js";
import { initializeItineraryDialog } from "./itinerary_dialog.js";
import { validateLocalWaypointRouteRequest, LOCAL_WAYPOINT_MAX_WAYPOINTS } from "./local_waypoint_route.js";
import { endpointSnapPolicy, restoreEndpointSnapIntent } from "./endpoint_snapping.js";
import { renderEndpointAdjustments } from "./endpoint_adjustment_view.js";
import { renderRouteDock, setRouteDockExpanded } from "./route_dock.js";
import { addResolvedRouteLocation, replaceResolvedRouteLocation } from "./route_point_acquisition.js";
import { resolvedPoiLocation } from "./poi_route_location.js";
import { reconcileAutomaticIntent, hasDiscoveryIntent, routeIntentPresentation, rememberPointEdit, undoPointEdit, clearPointUndo, pointUndoLabel, redoPointEdit, changeMapTopology } from "./automatic_intent.js";
import { renderWaypointEditor } from "./waypoint_editor.js";
import { renderRouteChoices, emptyResultsMarkup } from "./route_results.js";
import { initializeAppShell } from "./app_shell.js";
import { ApiError, generatePlan, getConfig, getPoiStatus, getRoutingProfiles, reversePlan, searchPois, visualizeRoute } from "./api.js";
import { createLocalPlaceSearch, createLocalPlaceNameSearch } from "./local_places.js";
import { createLocalGpxExporter } from "./local_gpx_client.js";
import { isBundledAndroidApp } from "./android_app.js";
import { createGpxFileSaver } from "./native_gpx_save.js";
import { escapeHtml, formatCount, formatDistance, formatPercent, friendlyLabel, metricRows } from "./format.js";
import { parseGpx } from "./gpx.js";
import { createIcon, decorateIcons } from "./icons.js";
import { clearRoutes, currentViewportBounds, fitCoordinates, focusCoordinate, focusSpur, initializeMap, positionDirectionLayer, renderCandidates, renderEndpointAdjustmentMap, renderHardEndpoints, renderImportedGpx, renderOptionalMarkers, renderOutingRoutes, renderPois, renderRequestedPlaces as renderRequestedPlaceMarkers, renderRequiredMarkers, renderSpurs, renderVisualization, resizeMap, keepCoordinateVisible } from "./map.js";
import { createLocalRoutingBridge } from "./local_routing.js";
import { createLocalPlanner, LocalPlannerError } from "./local_planner.js";
import { createLocalRegionClient, createRegionInstallerClient } from "./local_region_client.js";
import { createRegionVersionStore } from "./region_versions.js";
import { createRegionalNativeClient } from "./regional_native.js";
import { createRegionalPlanningContext } from "./regional_planning.js";
import { createRegionalMapStore } from "./regional_map_store.js";
import { createRegionProduct } from "./region_product.js";
import { createRegionPreference } from "./region_preference.js";
import { createRegionScreen, regionFailureMessage } from "./region_screen.js";
import { requireData } from "./regional_manifest.js";
import { createPlannerProfilePreference, initialLocalPlannerProfile } from "./planner_profile.js";
import { PUBLIC_PROFILE_METADATA } from "./public_profile_metadata.js";
import { addLocalWaypointProfileOptions } from "./local_waypoint_route.js";
import { initializeOfflineMaps } from "./offline_map.js";
import {
  centerPlannerCurrentLocation,
  clearPlannerCurrentLocation,
  positionPlannerLocationLayers,
  renderPlannerCurrentLocation,
} from "./map.js";
import {
  bindOutingController,
  forgetCurrentOutingParticipant,
  outingOutboxPresenceIsCurrent,
  outingMutationIsPending,
  renderCurrentOutingConnectivity,
  rememberCurrentOutingParticipant,
  retryCurrentOutingConnection,
  startOutingPage,
} from "./outing_controller.js";
import {
  clearUnavailableSavedRouteState,
  readOptionalStorage,
  resolveNetworkResource,
  settleOptionalPersistence,
} from "./pwa_network.js";
import { outingSlug } from "./outings.js";
import { createPlannerLocationController } from "./planner_location.js";
import { renderOutingCreationAction, renderOutingReceipt } from "./outing_view.js";
import {
  applyOfflineCopyRefresh,
  clearOfflineSnapshotStatus,
  initializePwaRuntime,
  pwaRuntime,
  loadOfflineSnapshot,
  markOfflineSnapshot,
  offlineMapConfig,
  refreshOfflineSnapshot,
  reportOptionalStorageFailure,
  removeOfflineSnapshot,
  restorePublicConfig,
  setPwaNetworkStatus,
  storePublicConfig,
  transportFailure,
} from "./pwa_runtime.js";
import {
  renderOfflineCopyControls,
  renderPwaStatus,
} from "./pwa_view.js";
import { createSavedRoute, deleteSavedRoute, getSavedRoute, savedRouteShareUrl, shareSavedRoute, sharedRouteSlug } from "./saved_routes.js";
import { assignRouteEndpoint, currentAdventureContext, currentDisplayContext, currentDisplayedCandidates, currentPlanRequest, currentSearchDiagnostics, generationAvailability, invalidateCandidates, isImmutableSnapshotDisplay, isSavedRouteSnapshotDisplay, pointDisplayName, readPlannerOptionsFromControls, renderEndpointTopologyControls, requestedPlaceIdentifier, saveActivePoints, selectedCandidate, setRouteTopology, state, switchPlanningMode } from "./state.js";
import {
  initializeTrailProfile,
  subscribeTrailProfile,
  trailProfileAvatarKey,
} from "./trail_profile.js";

const byId = (id) => document.getElementById(id);
const localGpxExporter = createLocalGpxExporter();
const gpxFileSaver = createGpxFileSaver();
const localRoutingBridge = createLocalRoutingBridge();
let sharedLocalRegionClient = null;
let selectedRegionId = null;
let regionPreference = null;
let regionScreen = null;
let plannerProfilePreference = null;
let localAvailabilityStatusText = null;
let offlineMaps = null;
let regionPlanningError = "regional_checking";
const regionVersions = createRegionVersionStore();
const nativeRegions = createRegionalNativeClient();
const regionalMaps = createRegionalMapStore({ versions: regionVersions, selectedRegionId: () => selectedRegionId });
function localRegionClient() {
  sharedLocalRegionClient ??= createLocalRegionClient();
  return sharedLocalRegionClient;
}
const searchLocalPlaces = createLocalPlaceSearch({ versions: regionVersions,
  regionClient: { loadVersion: (...args) => localRegionClient().loadVersion(...args) },
  selectedRegionId: () => selectedRegionId });
const searchLocalPlaceNames = createLocalPlaceNameSearch({ versions: regionVersions,
  regionClient: { loadVersion: (...args) => localRegionClient().loadPlacesVersion(...args) },
  selectedRegionId: () => selectedRegionId });
const locationSearch = createLocationSearch({ config: () => state.config?.geocoding, localSearch: searchLocalPlaceNames });
let locationSearchDialog = null;
function openLocationSearch(target, launcher) {
  clearPointPlacement(); locationSearchDialog?.open(target, launcher);
}

const withPlanningRegion = createRegionalPlanningContext({ versions: regionVersions, bridge: localRoutingBridge,
  verifyMap: (manifest, directory) => regionalMaps.verifyMap(manifest, directory),
  selectedRegionId: () => selectedRegionId,
  regionClient: { loadVersion: (...args) => localRegionClient().loadVersion(...args) },
  inspectNative: async (reference) => {
    // The route worker can inspect an installed archive while the independent
    // regional worker downloads an inactive replacement.
    const capabilities = await localRoutingBridge.forRegion(reference).capabilities();
    requireData(capabilities?.enabled && capabilities.installed_pack_ids.length === 1
      && capabilities.installed_pack_ids[0] === reference.pack_id, "regional_routing_unavailable");
    return { status: "ready", capabilities };
  } });
const localPlanner = isBundledAndroidApp()
  ? createLocalPlanner({ withRegion: withPlanningRegion }) : null;
let adventureDialog = null, adventurePlanning = false, manualAdventureSnapshot = null, pendingAdventureSnapshot = null;
let adventureMapEndpoint = null;
let adventureSnapshots = null, forgottenAdventureOutput = null, adventureRestoreEpoch = 0;
const adventureElevationViews = new Map();
const adventureResults = createAdventureResults({ root: byId("adventure-result"), candidatesRoot: byId("candidate-list"),
  onManual: () => returnToManualPlan(),
  onShowMap: coordinate => { appShell?.show("map"); focusCoordinate(coordinate); },
  onShowStories: () => appShell?.show("routes") });
const elevationView = createElevationView({root:byId("route-elevation"),
  isCurrent:(value, candidate) => isAdventureElevation(value, candidate) || !isImmutableSnapshotDisplay()
    && candidate === selectedCandidate() && selectedRouteElevation?.owns(value,candidate,state.generationResult,selectedRegionId),
  onPosition:position => position ? showElevationMapPosition(position) : clearElevationMapPosition(),
  onShowMap:position => {
    appShell?.show("map", {focus:true});
    requestAnimationFrame(() => {
      if (position === elevationView.diagnostics().position
        && (isAdventureElevation(adventureElevationView(), selectedCandidate())
          || selectedRouteElevation?.owns(state.selectedElevation,selectedCandidate(),state.generationResult,selectedRegionId))) {
        focusCoordinate(position.coordinate);
      }
    });
  },
  onCancel:() => selectedRouteElevation?.cancel(), onRetry:() => selectedRouteElevation?.retry()});
const selectedRouteElevation = localPlanner ? createSelectedRouteElevation({versions:regionVersions,
  onChange: value => { state.selectedElevation = value; renderElevation(value); }}) : null;

function adventureElevationView() {
  return state.adventureDisplay ? adventureElevationViews.get(selectedCandidate()?.id) ?? null : null;
}
function isAdventureElevation(value, candidate) {
  const output = state.adventureDisplay && state.adventureResult;
  return Boolean(output && candidate === selectedCandidate() && state.generationResult === output.chosen.result
    && value === adventureElevationViews.get(candidate.id) && value?.candidate_id === candidate.id
    && (value.status !== "ready" || value.result === output.chosen.elevations[candidate.id]));
}
function returnToManualPlan({ refresh = true } = {}) {
  if (!state.adventureDisplay) return;
  adventureDialog?.cancel(); adventureElevationViews.clear();
  state.adventureDisplay = false; state.adventureResult = null;
  if (manualAdventureSnapshot) {
    const id = state.request.id + 1;
    Object.assign(state, manualAdventureSnapshot);
    state.request = { ...manualAdventureSnapshot.request, id, startedAt: null };
  } else invalidateCandidates();
  manualAdventureSnapshot = null; state.visualizationCache.clear();
  if (refresh) { render(); appShell?.show("plan"); }
}
async function adventureContext({ includePlaces = false, useStart = true, useEnd = true, signal } = {}) {
  if (!localPlanner || regionPlanningError) throw new Error(regionFailureMessage(regionPlanningError ?? "regional_required"));
  const request = state.adventureDisplay ? state.generationSourceRequest : null;
  const context = request ? { start: request.start, end: request.end,
    hardWaypoints: request.waypoints.filter(point => point.constraint_strength === "exact"),
    suggested_profile: request.routing_profile, seed: request.seed, endpointSnapPolicy: request.endpoint_snap_policy }
    : currentAdventureContext();
  if (context.hardWaypoints.length > 14) throw new Error(t("This adventure can preserve up to 14 exact intermediate points. Review your required points first."));
  return regionVersions.withCommittedRegions(async rows => {
    signal?.throwIfAborted();
    const row = selectCommittedRegion(rows, selectedRegionId), reference = await regionalRoutingReference(row.manifest);
    const center = (useStart ? context.start : null) ?? (useEnd ? context.end : null);
    let localPlaces = [];
    if (includePlaces && center) {
      const directory = await regionVersions.committedDirectory(row.region_id, row.manifest.build_id);
      const session = await localRegionClient().loadVersion(row.manifest, directory);
      localPlaces = await nearbyAdventurePlaceContext({ session, reference, center, signal });
    }
    signal?.throwIfAborted();
    return { ...context, reference, localPlaces };
  });
}
async function displayExactAdventure(output, selectedId, requestId) {
  state.adventureDisplay = true; state.adventureResult = output;
  state.generationResult = output.chosen.result; state.generationSourceRequest = output.chosen.request;
  state.selectedSignature = selectedId;
  state.resultsInvalidated = false; state.visualizationCache.clear(); adventureElevationViews.clear();
  for (const candidate of output.chosen.result.candidates) {
    const result = output.chosen.elevations[candidate.id] ?? null;
    adventureElevationViews.set(candidate.id, Object.freeze({ status: result ? "ready" : "unavailable",
      candidate_id: candidate.id, result, diagnostic: result ? null : "elevation_unavailable", cache_hit: true }));
  }
  state.request = { status: "success", id: requestId, startedAt: null };
  render(); fitCoordinates(selectedCandidate().route.geometry);
  await selectCandidate(selectedId); appShell?.show("routes");
}
async function persistAdventureSelection() {
  const output = state.adventureDisplay && state.adventureResult, selected = state.selectedSignature;
  if (!output || output === forgottenAdventureOutput) return;
  setLocalizedText(byId("adventure-storage-status"), () => t("Saving this exact adventure on this device…"));
  const saved = adventureSnapshots && await adventureSnapshots.save(output, selected);
  if (state.adventureResult !== output || state.selectedSignature !== selected || forgottenAdventureOutput === output) return;
  setLocalizedText(byId("adventure-storage-status"), () => saved
    ? t("Saved on this device. Reopen the exact adventure from Plan after restarting. Only the latest adventure is kept.")
    : t("This adventure is open, but local recovery could not be saved. Export GPX before closing."));
  if (saved) byId("restore-adventure").hidden = false;
}
async function reopenSavedAdventure() {
  const owned = ++adventureRestoreEpoch, generation = state.generationResult, requestId = state.request.id;
  const regionId = selectedRegionId, selection = state.selectedSignature;
  const allowed = () => owned === adventureRestoreEpoch && !adventurePlanning && !state.adventureDisplay
    && !state.outingDisplay && !isSavedRouteSnapshotDisplay() && !byId("adventure-dialog").open
    && !["running", "reversing"].includes(state.request.status) && state.request.id === requestId
    && state.generationResult === generation && state.selectedSignature === selection
    && selectedRegionId === regionId;
  if (!allowed()) return;
  setLocalizedText(byId("adventure-recovery-status"), () => t("Checking the saved adventure…"));
  const record = adventureSnapshots && await adventureSnapshots.read();
  if (!allowed()) {
    setLocalizedText(byId("adventure-recovery-status"), () => t("Your plan changed while the saved adventure was checked. Reopen it when you are ready.")); return;
  }
  if (!record) {
    byId("restore-adventure").hidden = true;
    setLocalizedText(byId("adventure-recovery-status"), () => t("No valid saved adventure is available. Your current plan is unchanged.")); return;
  }
  manualAdventureSnapshot = { generationResult: state.generationResult, generationSourceRequest: state.generationSourceRequest,
    selectedSignature: state.selectedSignature, forkedSavedCandidate: state.forkedSavedCandidate,
    resultsInvalidated: state.resultsInvalidated, request: state.request };
  forgottenAdventureOutput = null;
  await displayExactAdventure(record.output, record.selected_id, requestId + 1);
  setLocalizedText(byId("request-status"), () => t("Saved adventure reopened exactly. New planning still requires a ready offline region."));
  byId("adventure-recovery-status").textContent = "";
}
async function forgetSavedAdventure() {
  adventureRestoreEpoch++; forgottenAdventureOutput = state.adventureResult;
  const cleared = adventureSnapshots && await adventureSnapshots.clear();
  byId("restore-adventure").hidden = true;
  setLocalizedText(byId("adventure-storage-status"), () => cleared
    ? t("Saved adventure forgotten. The displayed route remains open.")
    : t("The local saved adventure could not be removed. Try clearing saved offline data."));
}
async function checkAdventureRecovery() {
  const owned = adventureRestoreEpoch;
  const record = adventureSnapshots && await adventureSnapshots.read();
  if (owned !== adventureRestoreEpoch) return;
  byId("restore-adventure").hidden = !record;
}
function initializeNativeAppTools() {
  let languageSync = Promise.resolve();
  const syncLanguage = language => {
    languageSync = languageSync.then(() => nativeBridgeTransport.request("set_ui_language", { language }, {
      owner: "app-language", timeoutMs: 2000,
      parseReply: payload => { const value = JSON.parse(payload); return value.type === "set_ui_language_result" && value.selected === true && value.language === language; },
    }));
  };
  syncLanguage(getLanguage());
  onLanguageChange(syncLanguage);
  const privacy = byId("native-privacy"), identity = byId("app-build-identity");
  privacy.hidden = false;
  setLocalizedText(privacy, () => t("Privacy"));
  privacy.addEventListener("click", async () => {
    const shown = await nativeBridgeTransport.request("show_privacy", {}, {
      owner: "app-tools", timeoutMs: 2000, parseReply: payload => {
        const value = JSON.parse(payload);
        return value.type === "show_privacy_result" && value.shown === true;
      },
    });
    if (!shown) showError(() => (t("The privacy dialog is unavailable. Try again from the app.")));
  });
  let identityPending = false;
  identity.closest("details").addEventListener("toggle", async event => {
    if (!event.currentTarget.open || identityPending || identity.dataset.loaded) return;
    identityPending = true; identity.hidden = false;
    setLocalizedText(identity, () => t("Reading packaged build…"));
    const value = await nativeBridgeTransport.request("get_app_identity", {}, {
      owner: "app-tools", timeoutMs: 2000, parseReply: payload => {
        const data = JSON.parse(payload);
        if (data.type !== "app_identity_result" || !/^[a-f0-9]{7,40}(?:-dirty)?$/.test(data.revision)
          || !["debug", "release", "v2Debug", "v2Staging"].includes(data.variant)
          || typeof data.label !== "string" || data.label.length > 80 || typeof data.version !== "string" || data.version.length > 80) return null;
        return data;
      },
    });
    identityPending = false;
    if (value) {
      const variant = { v2Staging: "V2 Staging", v2Debug: "V2 Research", debug: "Debug", release: "Production" }[value.variant];
      identity.textContent = `${value.label} · ${value.revision} · ${variant} · ${value.version}`;
      identity.dataset.loaded = "true";
    } else setLocalizedText(identity, () => t("Packaged build identity unavailable."));
  });

}

function initializeAdventure() {
  byId("adventure-launch").hidden = !localPlanner;
  byId("ask-chatgpt").hidden = !localPlanner;
  document.body.classList.toggle("has-adventure-planner", Boolean(localPlanner));
  if (!localPlanner) return;
  const launchers = [byId("ask-chatgpt"), byId("plan-with-ai")];
  for (const action of launchers) action.addEventListener("click", () => { adventureRestoreEpoch++; adventureMapEndpoint = null; }, { capture: true });
  initializeNativeAppTools();
  byId("route-form").addEventListener("input", () => { adventureRestoreEpoch++; });
  byId("restore-adventure").addEventListener("click", () => void reopenSavedAdventure());
  byId("forget-adventure").addEventListener("click", () => void forgetSavedAdventure());
  let priorRequest = null, requestId = null;
  adventureDialog = initializeAdventureDialog({ root: byId("adventure-dialog"), launcher: byId("plan-with-ai"), launchers, planner: localPlanner,
    canOpen: () => !state.outingDisplay && !isSavedRouteSnapshotDisplay() && !["running", "reversing"].includes(state.request.status),
    getContext: adventureContext,
    onBusy: busy => {
      adventurePlanning = busy;
      if (busy) {
        adventureRestoreEpoch++;
        priorRequest = state.request; requestId = state.request.id + 1;
        if (!state.adventureDisplay) pendingAdventureSnapshot = { generationResult: state.generationResult,
          generationSourceRequest: state.generationSourceRequest, selectedSignature: state.selectedSignature,
          forkedSavedCandidate: state.forkedSavedCandidate, resultsInvalidated: state.resultsInvalidated, request: priorRequest };
        state.request = { status: "running", id: requestId, startedAt: Date.now() };
      } else {
        if (state.request.id === requestId && state.request.status === "running") state.request = { ...priorRequest, id: requestId, startedAt: null };
        pendingAdventureSnapshot = null;
      }
      render();
    },
    onResult: async output => {
      if (!adventurePlanning || state.request.id !== requestId) throw new DOMException(t("Adventure cancelled."), "AbortError");
      if (!manualAdventureSnapshot) manualAdventureSnapshot = pendingAdventureSnapshot;
      forgottenAdventureOutput = null;
      await displayExactAdventure(output, output.chosen.result.candidates[0].id, requestId);
      setLocalizedText(byId("request-status"), () => t("Your AI adventure is ready. Route calculations used the selected offline region."));
    },
    onChooseStart: () => { returnToManualPlan(); clearPointPlacement(); byId("set-hard-start").click(); adventureMapEndpoint = "start"; appShell?.show("map"); },
    onChooseEnd: () => { returnToManualPlan(); clearPointPlacement(); changeMapTopology("point_to_point", "near"); updateControlsFromOptions(); byId("set-hard-end").click(); adventureMapEndpoint = "end"; appShell?.show("map"); },
  });
  window.addEventListener("pagehide", () => adventureDialog?.clear(), { once: true });
}
localGpxExporter.prepare();
let pendingGpxExport = null;
let elapsedTimer = null;
let mapReady = false;
let appShell = null;
let poiDebounceTimer = null;
let pendingPoiBounds = null;
let savedRoutePageEpoch = 0;
let savedRouteReconnectOperation = null;
let plannerLocation = null;

const PRIMARY_SCENIC_CATEGORIES = [
  "viewpoint",
  "observation_tower",
  "castle",
  "archaeological_site",
  "ruins",
];
const HYDRATION_CATEGORIES = ["drinking_water", "fountain", "water_tap"];

const GENERATION_SUGGESTION = "Use Suggest a route for approximate places, or remove or move the exact waypoint.";
let lastExactFailure = null;
let localRouteCapabilities = null;

function showError(message, details = "", code = "", context = "", suggestion = "") {
  const codeElement = byId("error-code");
  const contextElement = byId("error-context");
  const suggestionElement = byId("error-suggestion");
  setLocalizedText(codeElement, () => code ? tr`Error code: ${code}` : "");
  codeElement.classList.toggle("hidden", !code);
  setLocalizedText(byId("error-message"), () => t(typeof message === "function" ? message() : message));
  contextElement.textContent = context;
  contextElement.classList.toggle("hidden", !context);
  suggestionElement.textContent = suggestion;
  suggestionElement.classList.toggle("hidden", !suggestion);
  byId("error-details").textContent = details;
  byId("error-details").closest("details").open = false;
  byId("error-banner").classList.remove("hidden");
  byId("exact-error-actions").classList.toggle(
    "hidden",
    code !== "exact_waypoint_not_reached",
  );
}

function hideError() { byId("error-banner").classList.add("hidden"); }

function showMapError(message) {
  byId("map-error-message").textContent = message;
  byId("map-error").classList.remove("hidden");
}

function updatePoiFiltersFromControls() {
  state.poiFilters = {
    iceCream: byId("place-ice-cream").checked,
    toilets: byId("place-toilets").checked,
    picnicAreas: byId("place-picnic-areas").checked,
    cafes: byId("place-cafes").checked,
    bakeries: byId("place-bakeries").checked,
    scenic: byId("place-scenic").checked,
    verifiedWater: byId("place-verified-water").checked,
    unknownWater: byId("place-unknown-water").checked,
    broadAttractions: byId("place-broad").checked,
    restrictedAccess: byId("place-restricted").checked,
    includePrivate: byId("place-private").checked,
    nonPotable: byId("place-non-potable").checked,
  };
}

function poiCategoriesAndPotability() {
  const categories = [];
  const potability = [];
  if (state.poiFilters.iceCream) categories.push("ice_cream");
  if (state.poiFilters.toilets) categories.push("toilets");
  if (state.poiFilters.picnicAreas) categories.push("picnic_area");
  if (state.poiFilters.cafes) categories.push("cafe");
  if (state.poiFilters.bakeries) categories.push("bakery");
  if (state.poiFilters.scenic) categories.push(...PRIMARY_SCENIC_CATEGORIES);
  if (state.poiFilters.broadAttractions) categories.push("tourism_attraction");
  if (state.poiFilters.verifiedWater) {
    categories.push("drinking_water");
    potability.push("verified");
  }
  if (state.poiFilters.unknownWater) {
    categories.push("fountain", "water_tap");
    potability.push(t("unknown"));
  }
  if (state.poiFilters.nonPotable) {
    categories.push(...HYDRATION_CATEGORIES);
    potability.push("non_potable");
  }
  return {
    categories: [...new Set(categories)],
    potability: [...new Set(potability)],
  };
}

function normalizedViewportBounds(bounds) {
  if (!bounds) return null;
  const normalized = {
    west: Math.max(-180, bounds.west),
    south: Math.max(-90, bounds.south),
    east: Math.min(180, bounds.east),
    north: Math.min(90, bounds.north),
  };
  if (normalized.west >= normalized.east || normalized.south >= normalized.north) return null;
  return normalized;
}

function clearPoiFeatures(status) {
  state.poiFeatures = [];
  state.selectedPoiId = null;
  state.selectedPoiFeature = null;
  byId("places-count").textContent = "";
  byId("places-status").textContent = status;
  if (mapReady) renderPois([], null, selectPoi, poiRenderOptions());
}

function poiRequestBody(bounds) {
  const filters = poiCategoriesAndPotability();
  if (!filters.categories.length) return null;
  const groups = [];
  if (filters.categories.some((category) => ["ice_cream", "cafe", "bakery"].includes(category))) groups.push("refreshment");
  if (filters.categories.some((category) => ["toilets", "picnic_area"].includes(category))) groups.push("practical");
  if (filters.categories.some((category) => PRIMARY_SCENIC_CATEGORIES.includes(category) || category === "tourism_attraction")) {
    groups.push("scenic");
  }
  if (filters.categories.some((category) => HYDRATION_CATEGORIES.includes(category))) {
    groups.push("hydration");
  }
  const access = ["public", t("unknown")];
  if (state.poiFilters.restrictedAccess) access.push("restricted");
  if (state.poiFilters.includePrivate) access.push("private");
  return {
    bbox: bounds,
    groups,
    categories: filters.categories,
    potability: filters.potability,
    access,
    include_private: state.poiFilters.includePrivate,
    limit: Math.min(200, state.config.poi_default_limit, state.config.poi_max_limit),
  };
}

function selectPoi(id, { revealMap = false } = {}) {
  const visitFeatures = (selectedCandidate()?.poi_visits ?? []).map((visit) => visit.poi);
  const allFeatures = [...new Map(
    [...state.poiFeatures, ...visitFeatures, ...(state.selectedPoiFeature ? [state.selectedPoiFeature] : [])].map((feature) => [feature.id, feature]),
  ).values()];
  if (id === null) {
    state.selectedPoiId = null;
    state.selectedPoiFeature = null;
    renderPois(allFeatures, null, selectPoi, poiRenderOptions());
    return;
  }
  const feature = allFeatures.find((value) => value.id === id);
  if (!feature) return;
  state.selectedPoiId = id;
  state.selectedPoiFeature = feature;
  renderPois(allFeatures, state.selectedPoiId, selectPoi, poiRenderOptions());
  if (revealMap) {
    focusCoordinate([feature.coordinate.lon, feature.coordinate.lat]);
  }
}

function selectedVisitedPoiIds() {
  return (selectedCandidate()?.poi_visits ?? []).map((visit) => visit.poi.id);
}

function canPassThroughPoi(feature) {
  return Boolean(state.config) && !isImmutableSnapshotDisplay()
    && !["running", "reversing"].includes(state.request.status)
    && resolvedPoiLocation(feature) !== null;
}

function passThroughPoi(feature) {
  if (state.selectedPoiId !== feature.id || !canPassThroughPoi(feature)) return false;
  try {
    const changed = addResolvedRouteLocation(resolvedPoiLocation(feature), { assignEndpoint: assignActiveEndpoint });
    if (!changed) return false;
    clearPointPlacement();
    selectPoi(null);
    invalidateAndRender();
    (document.querySelector('#route-dock [aria-pressed="true"]') ?? byId("dock-add"))?.focus({ preventScroll: true });
    return true;
  } catch (error) {
    showError(() => (error.message));
    return false;
  }
}

function poiRenderOptions() {
  return {
    onDeselect: () => selectPoi(null),
    onPrefer: preferPoi,
    onPassThrough: passThroughPoi,
    canPassThrough: canPassThroughPoi,
    preferredIds: state.autoTour.preferredPoiIds,
    visitedIds: selectedVisitedPoiIds(),
  };
}

function preferPoi(feature) {
  if (isSavedRouteSnapshotDisplay()) return;
  const eligibleAccess = ["public", t("unknown")].includes(feature.access_status);
  const scenic = PRIMARY_SCENIC_CATEGORIES.includes(feature.category) || feature.category === "tourism_attraction";
  const verifiedWater = feature.category === "drinking_water" && feature.potability === "verified";
  if (!eligibleAccess || (!scenic && !verifiedWater) || feature.potability === "non_potable") return;
  if (state.autoTour.preferredPoiIds.includes(feature.id)) return;
  if (state.autoTour.preferredPoiIds.length >= 8) {
    showError(() => (t("Suggested routes support at most eight preferred places.")));
    return;
  }
  rememberPointEdit("Place preference added");
  state.autoTour.preferredPoiIds.push(feature.id);
  invalidateAndRender();
  setEditableRequestStatus(
    () => (tr`${feature.display_name} added as a suggested-route preference.`),
  );
}

async function fetchViewportPois(id, bounds) {
  if (state.outingDisplay) return;
  if (!state.config?.poi_index_available) return;
  const normalized = normalizedViewportBounds(bounds);
  const request = normalized ? poiRequestBody(normalized) : null;
  if (!request) {
    state.poiRequest = { status: "idle", id };
    clearPoiFeatures(normalized ? t("Place filters are off.") : t("This viewport cannot be searched."));
    return;
  }
  const controller = new AbortController();
  state.poiAbortController = controller;
  state.poiRequest = { status: "loading", id };
  setLocalizedText(byId("places-status"), () => t("Loading mapped places for this viewport…"));
  try {
    const response = await (localPlanner ? searchLocalPlaces : searchPois)(request, controller.signal);
    if (state.poiRequest.id !== id) return;
    state.poiFeatures = response.features;
    const retained = state.selectedPoiFeature;
    const visibleFeatures = retained && !state.poiFeatures.some((feature) => feature.id === retained.id)
      ? [...state.poiFeatures, retained] : state.poiFeatures;
    state.poiRequest = { status: "success", id };
    renderPois(visibleFeatures, state.selectedPoiId, selectPoi, poiRenderOptions());
    byId("places-count").textContent = String(response.returned_count);
    if (!response.available) {
      setLocalizedText(byId("places-status"), () => t("POI index unavailable. Routing still works."));
    } else if (!response.returned_count) {
      setLocalizedText(byId("places-status"), () => t("No matching mapped places in this viewport."));
    } else if (response.truncated) {
      setLocalizedText(byId("places-status"), () => tr`Showing ${response.returned_count} of ${response.total_matching} matches — zoom in to narrow the viewport.`);
    } else {
      setLocalizedText(byId("places-status"), () => tr`${response.returned_count} mapped place${response.returned_count === 1 ? "" : "s"} in this viewport.`);
    }
    const compatibility = placeCompatibilityMessage(poiCategoriesAndPotability().categories,
      response.identity?.poi_classifier_version ?? state.poiIndexStatus?.classifier_version);
    if (response.available && compatibility) byId("places-status").textContent += ` ${compatibility}`;
  } catch (error) {
    if (state.poiRequest.id !== id || error.name === "AbortError") return;
    state.poiRequest = { status: "error", id };
    setLocalizedText(byId("places-status"), () => t("Places could not be loaded; routing still works."));
  } finally {
    if (state.poiRequest.id === id) state.poiAbortController = null;
  }
}

function schedulePoiRefresh(bounds = currentViewportBounds()) {
  if (state.outingDisplay) return;
  if (!state.config?.poi_index_available) return;
  pendingPoiBounds = bounds;
  window.clearTimeout(poiDebounceTimer);
  state.poiAbortController?.abort();
  state.poiAbortController = null;
  const id = state.poiRequest.id + 1;
  state.poiRequest = { status: "scheduled", id };
  poiDebounceTimer = window.setTimeout(() => fetchViewportPois(id, pendingPoiBounds), 250);
}

function updateOptionsFromControls() {
  changeMapTopology(byId("route-topology").value, localPlanner ? "near" : undefined);
  state.routingProfile = byId("profile").value;
  state.options = readPlannerOptionsFromControls(byId);
  if (state.planningMode === "auto_tour") {
    state.autoTour.directionPreference = byId("direction-preference").value;
    state.autoTour.distancePriority = state.options.distancePriority;
    state.autoTour.maximumDistanceKm = state.options.maximumDistanceKm;
    state.autoTour.scenicPreference = byId("scenic-preference").value;
    state.autoTour.drinkingWaterPreference = byId("water-preference").value;
  }
  const routeTopology = byId("route-topology").value;
  if (routeTopology === "loop" && state.endpointSetMode === "end") {
    state.endpointSetMode = null;
  }
}

function updateControlsFromOptions() {
  byId("profile").value = state.routingProfile;
  byId("route-name").value = state.options.name;
  byId("target-distance").value = state.options.targetDistanceKm;
  byId("tolerance").value = state.options.toleranceKm;
  byId("candidate-count").value = state.options.candidateCount;
  byId("seed").value = state.options.seed;
  byId("point-order-mode").value = state.options.waypointOrder;
  byId("path-selection-mode").value = state.options.pathSelectionMode;
  byId("nature-preference").value = state.options.naturePreference;
  byId("loop-geometry-preference").value = state.options.loopGeometryPreference;
  byId("free-poi-spur").value = state.options.freePoiSpurRepeatedM ?? 200;
  byId("direction-preference").value = state.autoTour.directionPreference;
  byId("distance-priority").value = state.options.distancePriority
    ?? state.autoTour.distancePriority;
  // Null is an intentional blank maximum in this draft, not a fallback request.
  byId("maximum-distance").value = state.options.maximumDistanceKm ?? "";
  byId("scenic-preference").value = state.autoTour.scenicPreference;
  byId("water-preference").value = state.autoTour.drinkingWaterPreference;
  updateProfileDescription();
}

function renderRoutingProfiles({ preserveUnavailableSelection = false } = {}) {
  if (localPlanner) {
    state.routingProfileCatalog = { profiles: Object.values(PUBLIC_PROFILE_METADATA).map((profile) => ({ profile,
      available: Boolean(localRouteCapabilities?.enabled && localRouteCapabilities.supported_profile_ids.includes(profile.id)),
      warnings: [] })) };
  }
  if (localPlanner) {
    state.routingProfile = initialLocalPlannerProfile(state.routingProfile, state.routingProfileCatalog.profiles);
  }
  const select = byId("profile");
  select.replaceChildren();
  const groups = new Map([
    ["running", "Running"],
    ["walking", "Walking"],
    ["cycling", "Cycling"],
  ]);
  for (const [kind, label] of groups) {
    const statuses = state.routingProfileCatalog.profiles.filter(
      (status) => status.profile.activity_kind === kind,
    );
    if (!statuses.length) continue;
    const group = document.createElement("optgroup");
    group.label = label;
    statuses.forEach((status) => {
      const option = document.createElement("option");
      option.value = status.profile.id;
      setLocalizedText(option, () => status.available
        ? t(status.profile.display_name)
        : `${t(status.profile.display_name)} — unavailable`);
      option.disabled = !status.available;
      group.append(option);
    });
    select.append(group);
  }
  const localProfiles = localPlanner ? [] : addLocalWaypointProfileOptions(select, localRouteCapabilities);
  const selected = selectedProfileStatus();
  if (!selected?.available && !localPlanner && !preserveUnavailableSelection && !localProfiles.includes(state.routingProfile)) {
    state.routingProfile = state.routingProfileCatalog.profiles.find(
      (status) => status.available,
    )?.profile.id ?? null;
  }
  select.value = state.routingProfile ?? "";
  updateProfileDescription();
}

function renderSnapshotProfileIdentity(profileId) {
  const select = byId("profile");
  select.replaceChildren();
  const option = document.createElement("option");
  option.value = profileId;
  setLocalizedText(option, () => tr`${friendlyLabel(profileId)} — saved snapshot`);
  select.append(option);
  select.value = profileId;
  setLocalizedText(byId("profile-description"), () => t("Showing the activity saved with this route."));
}

function selectedProfileStatus(profileId = state.routingProfile) {
  return state.routingProfileCatalog?.profiles.find(
    (status) => status.profile.id === profileId,
  ) ?? null;
}

function profileDisplayName(profileId) {
  return t(selectedProfileStatus(profileId)?.profile.display_name ?? profileId)
    ?? friendlyLabel(profileId);
}

function updateProfileDescription() {
  if (isSavedRouteSnapshotDisplay()) {
    setLocalizedText(byId("profile-description"), () => t("Showing the activity saved with this route."));
    return;
  }
  const status = selectedProfileStatus(byId("profile").value);
  if (localPlanner) {
    setLocalizedText(byId("profile-description"), () => regionPlanningError === "regional_checking"
      ? t("Checking the installed region’s activity profiles…")
      : !status ? t("Choose an available activity after the region is ready.")
      : status.available
      ? t("Uses this device’s installed region. Activity preferences depend on mapped OpenStreetMap data.")
      : t("Install a compatible offline region to use this activity on your device."));
    return;
  }
  if (!status?.available && localRouteCapabilities?.enabled
      && localRouteCapabilities.supported_profile_ids.includes(byId("profile").value)) {
    setLocalizedText(byId("profile-description"), () => t("Experimental local Valhalla profile only. Server Generate remains unavailable; no GraphHopper profile parity is claimed."));
    return;
  }
  setLocalizedText(byId("profile-description"), () => status
    ? tr`${t(status.profile.short_description)} Elevation-aware routing: ${t(status.profile.capabilities.elevation_aware ? t("yes") : t("no"))}.${status.available ? "" : t(" This profile is unavailable in the routing backend.")}`
    : t("Select a routing profile."));
}

function activeEndpoints() {
  return state.planningMode === "auto_tour"
    ? state.autoTour
    : state.waypointEndpoints;
}

function isOpenPlan() {
  const endpoints = activeEndpoints();
  return endpoints.routeTopology === "point_to_point";
}

function assignActiveEndpoint(kind, point) {
  const endpoints = activeEndpoints();
  if (point && localPlanner && point.snapPolicy === undefined) point = { ...point, snapPolicy: endpoints[kind]?.snapPolicy ?? "near" };
  if (state.planningMode === "auto_tour") {
    saveActivePoints();
    if (!assignRouteEndpoint(endpoints, kind, point)) {
      state.endpointSetMode = null;
      return false;
    }
    if (kind === "start") {
      state.points = point
        ? [point, ...state.autoTour.hardPoints]
        : [...state.autoTour.hardPoints];
    }
  } else {
    if (!assignRouteEndpoint(endpoints, kind, point)) {
      state.endpointSetMode = null;
      return false;
    }
  }
  return true;
}

function endpointFromControls(kind) {
  if (!byId(`hard-${kind}-enabled`).checked) return null;
  const latitudeValue = byId(`hard-${kind}-lat`).value.trim();
  const longitudeValue = byId(`hard-${kind}-lon`).value.trim();
  if (!latitudeValue || !longitudeValue) return null;
  const lat = Number(latitudeValue);
  const lon = Number(longitudeValue);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  return {
    ...activeEndpoints()[kind],
    name: byId(`hard-${kind}-name`).value.trim() || tr`Hard ${kind}`,
    lat,
    lon,
  };
}

function updateEndpointControls() {
  const endpoints = activeEndpoints();
  setRouteTopology(endpoints, endpoints.routeTopology);
  if (endpoints.routeTopology === "loop" && state.endpointSetMode === "end") {
    state.endpointSetMode = null;
  }
  if (endpoints.routeTopology === "loop" && state.selectedEndpointKind === "end") state.selectedEndpointKind = null;
  byId("route-topology").value = endpoints.routeTopology;
  for (const kind of ["start", "end"]) {
    const point = endpoints[kind];
    byId(`hard-${kind}-enabled`).checked = Boolean(point);
    byId(`hard-${kind}-snap-policy`).value = point?.snapPolicy ?? "exact";
    byId(`hard-${kind}-snap-policy`).parentElement.hidden = !localPlanner;
    byId(`hard-${kind}-name`).value = point?.name ?? "";
    byId(`hard-${kind}-lat`).value = point?.lat ?? "";
    byId(`hard-${kind}-lon`).value = point?.lon ?? "";
    setLocalizedText(byId(`set-hard-${kind}`), () => state.endpointSetMode === kind
      ? tr`Click map for ${kind}`
      : kind === "start" ? (point ? t("Move Start") : t("Choose on map")) : point ? t("Move End") : t("Set on map"));
  }
  const topology = endpoints.routeTopology;
  renderEndpointTopologyControls(
    byId("hard-end-control"),
    byId("loop-end-explanation"),
    topology,
  );
  const orderSelect = byId("point-order-mode");
  if (state.planningMode === "waypoint_route") {
    const optimized = orderSelect.querySelector('option[data-optimized="true"]');
    setLocalizedText(optimized, () => t("Optimize stops"));
    orderSelect.value = state.options.waypointOrder;
  }
}

function renderPreferredPois() {
  const ids = state.autoTour.preferredPoiIds;
  byId("preferred-poi-count").textContent = `${ids.length} / 8`;
  byId("preferred-poi-empty").classList.toggle("hidden", ids.length > 0);
  const list = byId("preferred-poi-list");
  list.replaceChildren();
  ids.forEach((id) => {
    const feature = state.poiFeatures.find((item) => item.id === id);
    const item = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = feature?.display_name ?? id;
    const remove = document.createElement("button");
    remove.type = "button";
    setLocalizedText(remove, () => t("Remove"));
    remove.setAttribute("aria-label", tr`Remove preferred place ${label.textContent}`);
    remove.addEventListener("click", () => {
      state.autoTour.preferredPoiIds = ids.filter((value) => value !== id);
      invalidateAndRender();
    });
    item.append(label, remove);
    list.append(item);
  });
}

function selectedRequestedVisits() {
  const candidate = selectedCandidate();
  const decisions = [
    ...(candidate?.reached_stops ?? [])
      .filter((stop) => stop.selection_origin === "requested")
      .map((stop) => [stop.id, { decision: "reached" }]),
    ...(candidate?.approximated_stops ?? [])
      .filter((stop) => stop.selection_origin === "requested")
      .map((stop) => [stop.id, { decision: "approximated" }]),
    ...(candidate?.dropped_stops ?? [])
      .filter((stop) => stop.selection_origin === "requested")
      .map((stop) => [stop.id, { decision: "dropped" }]),
  ];
  return new Map(decisions);
}

function requestedPlaceStatus(place, index, visits = selectedRequestedVisits()) {
  const visit = visits.get(place.id ?? requestedPlaceIdentifier(place, index));
  return visit?.decision ?? "pending";
}

function scrollRequestedPlaceIntoView(id) {
  const row = byId("requested-place-list").querySelector(
    `[data-requested-place-id="${CSS.escape(id)}"]`,
  );
  row?.scrollIntoView({ block: "nearest" });
}

function selectRequestedPlace(
  id,
  { revealMap = false, scrollList = false } = {},
) {
  if (!state.autoTour.requestedPlaces.some((place, index) => (
    (place.id ?? requestedPlaceIdentifier(place, index)) === id
  ))) return;
  state.selectedRequestedPlaceId = id;
  if (revealMap) state.pendingRequestedPlacePopupId = id;
  renderRequestedPlacesList();
  if (scrollList) scrollRequestedPlaceIntoView(id);
  renderMapData();
}

function renderRequestedPlacesList() {
  const places = state.autoTour.requestedPlaces;
  const visits = selectedRequestedVisits();
  byId("requested-place-count").textContent = `${places.length} / 30`;
  byId("requested-place-empty").classList.toggle("hidden", places.length > 0);
  const list = byId("requested-place-list");
  list.replaceChildren();
  places.forEach((place, index) => {
    const id = place.id ?? requestedPlaceIdentifier(place, index);
    const status = requestedPlaceStatus(place, index, visits);
    const item = document.createElement("li");
    item.className = `requested-place-row requested-status-${status}${id === state.selectedRequestedPlaceId ? " selected" : ""}`;
    item.dataset.requestedPlaceId = id;
    item.tabIndex = 0;
    item.setAttribute("role", "button");
    item.setAttribute("aria-label", tr`Show requested place ${index + 1}, ${place.name}, ${status}`);
    if (id === state.selectedRequestedPlaceId) item.setAttribute("aria-current", "true");
    const label = document.createElement("span");
    setLocalizedText(label, () => tr`${index + 1}. ${place.name} · access search ${place.accessSearchRadiusM ?? place.visitRadiusM ?? 500} m · ${friendlyLabel(place.importance)}`);
    const statusLabel = document.createElement("span");
    statusLabel.className = "requested-place-status";
    statusLabel.textContent = friendlyLabel(status);
    const remove = document.createElement("button");
    remove.type = "button";
    setLocalizedText(remove, () => t("Remove"));
    remove.setAttribute("aria-label", tr`Remove requested place ${place.name}`);
    remove.addEventListener("click", () => {
      rememberPointEdit("Requested place removed");
      state.autoTour.requestedPlaces = places.filter((_value, placeIndex) => placeIndex !== index);
      if (state.selectedRequestedPlaceId === id) {
        state.selectedRequestedPlaceId = null;
        state.pendingRequestedPlacePopupId = null;
      }
      invalidateAndRender();
    });
    item.addEventListener("click", (event) => {
      if (event.target.closest("button")) return;
      selectRequestedPlace(id, { revealMap: true });
    });
    item.addEventListener("keydown", (event) => {
      if (!["Enter", " "].includes(event.key)) return;
      event.preventDefault();
      selectRequestedPlace(id, { revealMap: true });
    });
    const details = document.createElement("span");
    details.className = "requested-place-copy";
    details.append(label, statusLabel);
    const approach = document.createElement("button");
    approach.type = "button";
    approach.className = "text-button";
    setLocalizedText(approach, () => t("Set approach on map"));
    approach.addEventListener("click", () => {
      state.settingRequestedApproachId = id;
      state.selectedRequestedPlaceId = id;
      setLocalizedText(approach, () => t("Click map once…"));
      renderStatus();
    });
    const clearApproach = document.createElement("button");
    clearApproach.type = "button";
    clearApproach.className = "text-button";
    setLocalizedText(clearApproach, () => t("Clear approach"));
    clearApproach.disabled = !place.approachOverride;
    clearApproach.addEventListener("click", () => {
      rememberPointEdit("Place approach cleared");
      place.approachOverride = null;
      invalidateAndRender();
    });
    item.append(details, approach, clearApproach, remove);
    list.append(item);
  });
}

function renderModeControls() {
  const auto = state.planningMode === "auto_tour";
  document.querySelectorAll('input[name="planning-mode"]').forEach((input) => {
    input.checked = input.value === state.planningStrategy;
  });
  byId("auto-tour-fields").classList.toggle("hidden", !auto);
  byId("waypoint-order-field").classList.toggle("hidden", auto);
  byId("preferred-pois").classList.toggle("hidden", !auto);
  byId("requested-places").classList.toggle("hidden", !auto);
  setLocalizedText(byId("point-editor-title"), () => auto ? t("Places and advanced anchors") : t("Points to connect"));
  const pointsEditor = byId("planning-points");
  if (pointsEditor.dataset.mode !== state.planningMode) {
    pointsEditor.open = !auto;
    if (auto) byId("route-form").after(pointsEditor);
    else byId("connect-end").before(pointsEditor);
    const shape = byId("route-shape-field"), end = byId("hard-end-control"), loop = byId("loop-end-explanation"), order = byId("waypoint-order-field");
    if (auto) {
      byId("endpoint-options-anchor").append(shape, loop, end);
      byId("advanced-order-anchor").append(order);
    } else {
      byId("connect-shape").append(shape);
      byId("connect-order").append(order);
      byId("connect-end").append(loop, end);
    }
    pointsEditor.dataset.mode = state.planningMode;
  }
  byId("connect-shape").classList.toggle("hidden", auto);
  byId("connect-end").classList.toggle("hidden", auto);
  setLocalizedText(byId("clear-points"), () => auto ? t("Clear all") : t("Clear route points"));
  const generateLabel = t("Generate");
  for (const id of ["generate", "generate-top", "generate-map"]) byId(id).textContent = generateLabel;
  setLocalizedText(byId("places-explanation"), () => auto
    ? t("Browse mapped places and optionally prefer eligible places in your suggested route. Simply selecting a place never changes the route.")
    : t("Explore places on the map. Selecting one does not change your route points or exported route."));
  updateEndpointControls();
  const start = activeEndpoints().start;
  const end = activeEndpoints().end;
  setLocalizedText(byId("plan-end-summary"), () => end ? end.name || t("End selected") : t("Choose End on the map"));
  byId("clear-hard-end").hidden = !end;
  setLocalizedText(byId("plan-start-summary"), () => start
    ? `${start.name === "Hard start" ? t("Start set ✓") : start.name || t("Start set ✓")}`
    : t("Choose Start on the map"));
  byId("clear-hard-start").hidden = !start;
  const intent = routeIntentPresentation();
  byId("route-intent-summary").textContent = intent.title;
  byId("route-intent-help").textContent = intent.detail;
  byId("map-route-summary").textContent = intent.compactTitle ?? intent.title;
  byId("map-route-help").textContent = intent.detail;
  setLocalizedText(byId("planning-strategy-note"), () => state.planningStrategy === "automatic" ? t("Uses your map points to choose how to plan.") : t("Explicit strategy retained. Imported plans keep their original routing intent."));
  renderPreferredPois();
  byId("show-dropped-requested-radii-control").classList.toggle("hidden", !auto);
  renderRequestedPlacesList();
}

function validPoint(point) {
  return Number.isFinite(point.lat)
    && Number.isFinite(point.lon)
    && Math.abs(point.lat) <= 90
    && Math.abs(point.lon) <= 180;
}

function pointValidation() {
  const maximum = state.planningMode === "auto_tour"
    ? 6 + Number(Boolean(state.autoTour.start))
    : (state.config?.max_required_points ?? 30);
  if (state.points.length > maximum) return tr`This mode supports at most ${maximum} points.`;
  for (let index = 1; index < state.points.length; index += 1) {
    const previous = state.points[index - 1];
    const current = state.points[index];
    if (previous.lat === current.lat && previous.lon === current.lon) {
      return tr`Points ${index} and ${index + 1} have identical adjacent coordinates.`;
    }
  }
  if (state.points.some((point) => !validPoint(point))) {
    return t("Every point needs valid latitude and longitude coordinates.");
  }
  const endpoints = activeEndpoints();
  if (endpoints.routeTopology === "loop" && endpoints.end) {
    return t("Loop plans must not contain an end.");
  }
  for (const [label, point] of [[t("Hard start"), endpoints.start], [t("Hard end"), endpoints.end]]) {
    if (point && !validPoint(point)) return tr`${label} needs valid coordinates.`;
  }
  if (
    endpoints.routeTopology === "point_to_point"
    && endpoints.start
    && endpoints.end
    && endpoints.start.lat === endpoints.end.lat
    && endpoints.start.lon === endpoints.end.lon
  ) return t("Point-to-point start and end must have distinct coordinates.");
  return "";
}

function currentGenerationAvailability() {
  if (localPlanner && regionPlanningError) return { enabled: false, reason: regionFailureMessage(regionPlanningError) };
  if (localPlanner && !localRouteCapabilities?.enabled) return {
    enabled: false, reason: t("On-device routing is unavailable in this app build."),
  };
  if (localPlanner && !localRouteCapabilities.installed_pack_count) return {
    enabled: false, reason: t("Download a supported offline region before planning a route."),
  };
  const endpoints = activeEndpoints();
  return generationAvailability({
    planningMode: state.planningMode,
    routeTopology: endpoints.routeTopology,
    start: endpoints.start,
    end: endpoints.end,
    mandatoryPointCount: state.points.length,
    pointValidationMessage: pointValidation(),
    profileAvailable: Boolean(selectedProfileStatus()?.available),
  });
}

function setEditableRequestStatus(message) {
  const availability = currentGenerationAvailability();
  const placementGuidance = pointValidation()
    ? ""
    : activeMapPlacementGuidance();
  setLocalizedText(byId("request-status"), () => placementGuidance
    || (availability.enabled ? (typeof message === "function" ? message() : t(message)) : t(availability.reason)));
}

function activeMapPlacementGuidance() {
  if (state.settingRequestedApproachId) {
    return t("Click the map to set the requested-place approach.");
  }
  if (state.endpointSetMode) {
    return tr`Click the map to set your ${state.endpointSetMode} point.`;
  }
  if (state.movingPointIndex !== null) return tr`Choose a new position for ${pointDisplayName(state.points[state.movingPointIndex], state.movingPointIndex)}. Other points stay unchanged.`;
  if (state.addPointMode) return state.planningStrategy === "automatic" ? t("Tap an empty map position to extend the route.") : t("Tap an empty map position to add one stop.");
  return "";
}

function invalidateAndRender() {
  adventureRestoreEpoch++;
  if (reconcileAutomaticIntent()) updateControlsFromOptions();
  localPlanner?.invalidate();
  saveActivePoints();
  if (state.request.status === "running") {
    state.abortController?.abort();
    state.request = {
      status: "cancelled",
      id: state.request.id + 1,
      startedAt: null,
    };
    state.abortController = null;
    window.clearInterval(elapsedTimer);
    setLocalizedText(byId("request-status"), () => t("Generation cancelled because the route changed."));
  }
  invalidateCandidates();
  clearRoutes();
  if (state.selectedPointIndex !== null && state.selectedPointIndex >= state.points.length) {
    state.selectedPointIndex = state.points.length ? state.points.length - 1 : null;
  }
  render();
}

function iconButton(action, icon, label, disabled = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.dataset.action = action;
  button.disabled = disabled;
  button.setAttribute("aria-label", label);
  button.title = label;
  button.append(createIcon(icon));
  button.addEventListener("click", (event) => event.stopPropagation());
  return button;
}

function candidateVisitOrders() {
  const candidate = selectedCandidate();
  return new Map(
    (candidate?.diagnostics.details.required_waypoint_order ?? []).map((visit, index) => [
      visit.original_index,
      index + 1,
    ]),
  );
}

function updatePoiSelection(scrollSelected = false) {
  const list = byId("poi-list");
  list.querySelectorAll(".poi-row").forEach((row) => {
    const selected = Number(row.dataset.pointIndex) === state.selectedPointIndex;
    row.classList.toggle("selected", selected);
    if (selected) row.setAttribute("aria-current", "true");
    else row.removeAttribute("aria-current");
    if (selected && scrollSelected) {
      const rowTop = row.offsetTop;
      const rowBottom = rowTop + row.offsetHeight;
      if (rowTop < list.scrollTop) list.scrollTop = rowTop;
      else if (rowBottom > list.scrollTop + list.clientHeight) {
        list.scrollTop = rowBottom - list.clientHeight;
      }
    }
  });
}

function selectPoint(index, { scrollSelected = false, requestPopup = false } = {}) {
  if (state.planningMode === "auto_tour" && state.autoTour.start && index === 0) { selectEndpoint("start"); return; }
  if (!Number.isInteger(index) || index < 0 || index >= state.points.length) return;
  setRouteDockExpanded(byId("route-dock"), true);
  clearPointPlacement();
  state.selectedEndpointKind = null;
  state.selectedPointIndex = index;
  if (requestPopup) state.pendingPointPopupIndex = index;
  if (state.planningMode === "waypoint_route") renderPoiEditor();
  else updatePoiSelection(scrollSelected);
  renderMapData();
  updateEndpointControls();
  renderStatus();
  if (scrollSelected) appShell?.reveal(".poi-row.selected");
  const point = state.points[index];
  keepCoordinateVisible([point.lon, point.lat]);
}

function clearPointPlacement() {
  adventureMapEndpoint = null;
  state.addPointMode = false;
  state.endpointSetMode = null;
  state.movingPointIndex = null;
  state.settingRequestedApproachId = null;
}

function selectEndpoint(kind) {
  setRouteDockExpanded(byId("route-dock"), true);
  clearPointPlacement();
  state.selectedEndpointKind = kind;
  state.selectedPointIndex = null;
  render();
  const point = activeEndpoints()[kind];
  if (point) keepCoordinateVisible([point.lon, point.lat]);
}

locationSearchDialog = initializeLocationSearchDialog({ root: byId("location-search-dialog"),
  search: (...args) => locationSearch.searchResolvedLocations(...args), config: () => state.config?.geocoding,
  canEdit: () => Boolean(state.config) && !isImmutableSnapshotDisplay() && !["running", "reversing"].includes(state.request.status),
  onSelect: (target, location) => {
    const changed = target ? replaceResolvedRouteLocation(target, location, { assignEndpoint: assignActiveEndpoint })
      : addResolvedRouteLocation(location, { assignEndpoint: assignActiveEndpoint });
    if (changed) { clearPointPlacement(); invalidateAndRender(); }
    return changed;
  },
  restoreFocus: () => {
    const selected = byId("route-dock").querySelector('[aria-pressed="true"]');
    (selected ?? byId("dock-add"))?.focus({ preventScroll: true });
  },
});

function beginPointMove(index) {
  clearPointPlacement();
  state.selectedPointIndex = index;
  state.selectedEndpointKind = null;
  state.movingPointIndex = index;
  renderStatus();
  appShell?.show("map", { focus: true });
}

function renderPoiEditor() {
  if (state.planningMode !== "waypoint_route") return renderLegacyPoiEditor();
  renderWaypointEditor({
    list: byId("poi-list"), points: state.points, selectedIndex: state.selectedPointIndex,
    visitOrders: candidateVisitOrders(), reorderDisabled: state.options.waypointOrder !== "fixed",
    onSelect: (index) => selectPoint(index),
    onChange: (index, field, value) => {
      rememberPointEdit("Stop updated");
      clearPointPlacement();
      state.points[index] = { ...state.points[index], [field]: value };
      invalidateAndRender();
    },
    onMove: movePoint, onRemove: removePoint, onPlace: beginPointMove,
  });
  setLocalizedText(byId("poi-count"), () => t(state.points.length === 1 ? "{count} stop" : "{count} stops", { count: state.points.length }));
  byId("poi-validation").textContent = pointValidation();
}

function renderLegacyPoiEditor() {
  const list = byId("poi-list");
  const visitOrders = candidateVisitOrders();
  list.replaceChildren();
  state.points.forEach((point, index) => {
    const visitOrder = visitOrders.get(index) ?? index + 1;
    const row = document.createElement("div");
    row.className = `poi-row${index === 0 ? " start" : ""}${index === state.selectedPointIndex ? " selected" : ""}${validPoint(point) ? "" : " invalid"}`;
    row.dataset.pointIndex = String(index);
    row.tabIndex = 0;
    row.role = "listitem";
    if (index === state.selectedPointIndex) row.setAttribute("aria-current", "true");

    const identity = document.createElement("div");
    identity.className = "poi-identity";
    const number = document.createElement("span");
    number.className = "poi-number";
    number.textContent = String(visitOrder);
    identity.append(number);
    if (index === 0) {
      const start = document.createElement("span");
      start.className = "poi-start-label";
      start.textContent = "Start/end";
      identity.append(start);
    }

    const main = document.createElement("div");
    main.className = "poi-main";
    const name = document.createElement("strong");
    name.className = "poi-name";
    name.textContent = pointDisplayName(point, index);
    main.append(name);
    const fields = document.createElement("div");
    fields.className = "poi-fields";
    const fieldDefinitions = [
      ["name", t("Edit point name"), "text", point.name ?? ""],
      ["lat", "Latitude", "number", point.lat],
      ["lon", "Longitude", "number", point.lon],
    ];
    fieldDefinitions.forEach(([field, labelText, type, value]) => {
      const label = document.createElement("label");
      if (field === "name") label.className = "name";
      label.textContent = labelText;
      const input = document.createElement("input");
      input.dataset.field = field;
      input.type = type;
      input.value = String(value);
      if (field === "name") input.maxLength = 120;
      if (field === "lat") { input.min = "-90"; input.max = "90"; input.step = "0.000001"; }
      if (field === "lon") { input.min = "-180"; input.max = "180"; input.step = "0.000001"; }
      input.addEventListener("focus", () => selectPoint(index));
      input.addEventListener("change", () => {
        rememberPointEdit("Point updated");
        state.points[index] = {
          ...state.points[index],
          [field]: field === "name" ? input.value : Number(input.value),
        };
        invalidateAndRender();
      });
      label.append(input);
      fields.append(label);
    });
    main.append(fields);
    const metadata = document.createElement("div");
    metadata.className = "poi-meta";
    const originalIndex = Number.isInteger(point.originalIndex) ? point.originalIndex : index;
    setLocalizedText(metadata, () => visitOrder === index + 1
      ? tr`Original request point ${originalIndex + 1}`
      : tr`Request position ${index + 1} · optimized visit ${visitOrder} · original ${originalIndex + 1}`);
    main.append(metadata);

    const actions = document.createElement("div");
    actions.className = "poi-actions";
    const auto = state.planningMode === "auto_tour";
    const up = iconButton("up", "up", tr`Move ${pointDisplayName(point, index)} up`, auto || index === 0);
    const down = iconButton("down", "down", tr`Move ${pointDisplayName(point, index)} down`, auto || index === state.points.length - 1);
    const remove = iconButton("remove", "delete", tr`Remove ${pointDisplayName(point, index)}`);
    up.addEventListener("click", () => movePoint(index, index - 1));
    down.addEventListener("click", () => movePoint(index, index + 1));
    remove.addEventListener("click", () => removePoint(index));
    actions.append(up, down, remove);

    row.addEventListener("click", (event) => {
      if (event.target.closest("input, button, label")) return;
      selectPoint(index, { requestPopup: true });
    });
    row.addEventListener("keydown", (event) => {
      if (event.target !== row) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const delta = event.key === "ArrowDown" ? 1 : -1;
        const next = Math.max(0, Math.min(state.points.length - 1, index + delta));
        selectPoint(next, { scrollSelected: true });
        byId("poi-list").querySelector(`[data-point-index="${next}"]`)?.focus();
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectPoint(index, { requestPopup: true });
      }
    });
    row.append(identity, main, actions);
    list.append(row);
  });
  const maximum = state.planningMode === "auto_tour" ? 7 : (state.config?.max_required_points ?? 30);
  const hardCount = state.planningMode === "auto_tour"
    ? Math.max(state.points.length - Number(Boolean(state.autoTour.start)), 0)
    : state.points.length;
  byId("poi-count").textContent = state.planningMode === "auto_tour"
    ? `${hardCount} / 6 anchors`
    : `${state.points.length} / ${maximum}`;
  byId("poi-validation").textContent = pointValidation();
}

function movePoint(from, to) {
  if (isImmutableSnapshotDisplay() || ["running", "reversing"].includes(state.request.status)) return;
  if (state.planningMode === "waypoint_route" && state.options.waypointOrder !== "fixed") return;
  if (to < 0 || to >= state.points.length || from === to || !state.points[from]) return;
  const focusPlan = byId("poi-list").contains(document.activeElement);
  rememberPointEdit("Stop reordered");
  clearPointPlacement();
  const selectedPoint = state.selectedPointIndex === null ? null : state.points[state.selectedPointIndex];
  const [point] = state.points.splice(from, 1);
  state.points.splice(to, 0, point);
  state.selectedPointIndex = selectedPoint ? state.points.indexOf(selectedPoint) : null;
  invalidateAndRender();
  if (focusPlan) byId("poi-list").querySelector(".poi-row.selected .point-select")?.focus({ preventScroll: true });
}

function removePoint(index) {
  if (isImmutableSnapshotDisplay() || ["running", "reversing"].includes(state.request.status)) return;
  if (!state.points[index]) return;
  const focusPlan = byId("poi-list").contains(document.activeElement);
  rememberPointEdit("Point removed");
  clearPointPlacement();
  if (state.planningMode === "auto_tour" && state.autoTour.start && index === 0) {
    saveActivePoints();
    state.autoTour.start = null;
    state.points = [...state.autoTour.hardPoints];
    state.selectedEndpointKind = null;
    state.selectedPointIndex = state.points.length ? 0 : null;
    invalidateAndRender();
    return;
  }
  const selectedPoint = state.selectedPointIndex === null ? null : state.points[state.selectedPointIndex];
  state.points.splice(index, 1);
  if (selectedPoint && state.points.includes(selectedPoint)) {
    state.selectedPointIndex = state.points.indexOf(selectedPoint);
  } else {
    state.selectedPointIndex = state.points.length ? Math.min(index, state.points.length - 1) : null;
  }
  invalidateAndRender();
  if (focusPlan) (byId("poi-list").querySelector(".poi-row.selected .point-select") ?? byId("add-point-mode")).focus({ preventScroll: true });
}

function renderMapData() {
  if (mapReady) renderEndpointAdjustmentMap(currentEndpointAdjustments());
  if (state.outingDisplay && state.outingSnapshot) {
    if (mapReady) {
      renderOutingRoutes(
        state.outingSnapshot.participants,
        state.selectedOutingParticipantId,
      );
    }
    return;
  }
  if (!mapReady) return;
  const candidate = selectedCandidate();
  const adventure = state.adventureDisplay ? state.adventureResult : null;
  const adventureRequest = adventure?.chosen.request;
  const hardPoints = adventureRequest?.waypoints.filter(point => point.constraint_strength === "exact");
  const points = hardPoints?.map(point => ({ ...point.coordinate, id: point.id, name: point.name })) ?? state.points;
  const visits = candidate?.diagnostics.details.required_waypoint_order;
  const markerVisits = adventureRequest ? visits?.map(visit => ({ ...visit,
    original_index: hardPoints.findIndex(point => point.id === adventureRequest.waypoints[visit.original_index]?.id) })) : visits;
  const popupIndex = state.pendingPointPopupIndex;
  state.pendingPointPopupIndex = null;
  const requestedPopupId = state.pendingRequestedPlacePopupId;
  state.pendingRequestedPlacePopupId = null;
  renderRequiredMarkers(
    points,
    markerVisits,
    state.selectedEndpointKind === "start" && state.planningMode === "auto_tour" ? 0 : state.selectedPointIndex,
    popupIndex,
    isImmutableSnapshotDisplay()
      || ["running", "reversing"].includes(state.request.status),
    {
      onDrag: (index, coordinate) => {
        const start = state.planningMode === "auto_tour" && state.autoTour.start && index === 0;
        replaceResolvedRouteLocation(start ? { endpoint: "start" } : { index }, coordinate, { assignEndpoint: assignActiveEndpoint });
        clearPointPlacement();
        invalidateAndRender();
      },
      onActivate: (index) => selectPoint(index, {
        requestPopup: false,
      }),
    },
    !adventure && state.planningMode === "auto_tour",
  );
  const endpoints = adventureRequest ? { start: adventureRequest.start, end: adventureRequest.end } : activeEndpoints();
  renderHardEndpoints(
    !adventure && state.planningMode === "auto_tour" ? null : endpoints.start,
    endpoints.end,
    { onActivate: selectEndpoint, selectedKind: state.selectedEndpointKind,
      disabled: isImmutableSnapshotDisplay() || ["running", "reversing"].includes(state.request.status) },
  );
  renderOptionalMarkers(candidate?.optional_points ?? []);
  renderImportedGpx(adventure ? null : state.importedGpx);
  renderCandidates(
    currentDisplayedCandidates(),
    state.selectedSignature,
    state.showAllCandidates,
    state.showDirectionArrows,
    selectCandidate,
  );
  renderVisualization(
    candidate ? state.visualizationCache.get(candidate.id) ?? null : null,
    state.showNatureContext,
  );
  renderSpurs(candidate);
  const allFeatures = [...new Map([...state.poiFeatures,
    ...(state.selectedPoiFeature ? [state.selectedPoiFeature] : [])].map((feature) => [feature.id, feature])).values()];
  renderPois(allFeatures, state.selectedPoiId, selectPoi, poiRenderOptions());
  renderAdventurePlaces(adventure?.chosen ?? null, candidate?.id, id => adventureResults.showPlace(id));
  const constraintPlaces = adventure ? [] : state.planningMode === "auto_tour"
    ? state.autoTour.requestedPlaces
    : state.points.flatMap((point, index) => (point.constraintStrength ?? "exact") === "exact" ? [] : [{
      id: point.id ?? `route-waypoint-${index + 1}`,
      name: point.name,
      coordinate: { lat: point.lat, lon: point.lon },
      importance: "must_visit",
      accessSearchRadiusM: point.accessSearchRadiusM ?? 500,
    }]);
  const constraintVisits = [
    ...(candidate?.reached_stops ?? []),
    ...(candidate?.approximated_stops ?? []),
    ...(candidate?.dropped_stops ?? []),
  ].filter((stop) => stop.selection_origin === "requested");
  renderRequestedPlaceMarkers(
    constraintPlaces,
    constraintVisits,
    state.planningMode === "auto_tour" ? state.selectedRequestedPlaceId
      : state.selectedPointIndex === null ? null
        : state.points[state.selectedPointIndex]?.id ?? `route-waypoint-${state.selectedPointIndex + 1}`,
    state.showDroppedRequestedRadii,
    (id) => {
      if (state.planningMode === "auto_tour") {
        selectRequestedPlace(id, { scrollList: true });
      } else {
        const index = state.points.findIndex((point, index) => (point.id ?? `route-waypoint-${index + 1}`) === id);
        if (index >= 0) selectPoint(index, { scrollSelected: true, requestPopup: true });
      }
    },
    requestedPopupId,
  );
  positionDirectionLayer();
  positionPlannerLocationLayers();
}

function directionLabel(traversal) {
  return {
    start_to_end: "Start → End",
    clockwise: "Clockwise",
    counterclockwise: "Counterclockwise",
    complex_loop: t("Complex loop"),
  }[traversal?.direction] ?? t("Direction unavailable");
}

function traversalSummary(candidate, result) {
  const anchors = candidate.traversal?.anchors ?? [];
  const start = anchors.find((anchor) => anchor.kind === "start")?.name ?? t("Start");
  const end = anchors.find((anchor) => anchor.kind === "end")?.name ?? t("End");
  const label = result.topology === "point_to_point"
    ? `${start} → ${end}`
    : directionLabel(candidate.traversal);
  return `<section class="direction-summary" role="status" aria-label="${t("Route traversal direction")}"><h3>${t("Traversal direction")}</h3><p><strong>${escapeHtml(label)}</strong></p><p class="context-note">${t("Direction arrows follow the returned routed geometry. They are planning context, not turn-by-turn instructions.")}</p></section>`;
}

// Display only availability/coverage supplied by the canonical analysis.
function repetitionShare(analysis) {
  return analysis.repetition.available ? analysis.repetition.repeated_distance.share : null;
}
function backtrackShare(analysis) {
  return analysis.backtrack_edge_id_coverage.share > 0 ? analysis.immediate_backtrack.share : null;
}
function detailShare(analysis, metric, detail) {
  return analysis.detail_breakdowns?.[detail]?.coverage_share > 0 ? analysis[metric].share : null;
}

function activityQualitySection(analysis) {
  const quality = analysis.activity_quality;
  const metric = (label, value, detail) => {
    const coverage = Number(quality.detail_coverage?.[detail] ?? 0);
    return [
      label,
      coverage > 0
        ? `${formatDistance(value.distance_m)} · ${formatPercent(value.share)}`
        : t("not evaluated"),
    ];
  };
  if (quality.activity_kind === "walking") {
    return section(t("Hiking quality"), [
      metric("Trail-like", quality.trail_like, "road_class"),
      metric(t("Hiking network"), quality.official_hiking_network, "foot_network"),
      metric(t("Technical hiking"), quality.technical_hiking, "hike_rating"),
      metric(t("Steps"), quality.steps, "road_class"),
      metric(t("Poor smoothness"), quality.poor_smoothness, "smoothness"),
    ]);
  }
  if (quality.activity_kind === "running") {
    return section(t("Trail-running quality"), [
      metric(t("Runnable surface"), quality.runnable_surface, "surface"),
      metric("Trail-like", quality.trail_like, "road_class"),
      metric(t("Technical trail"), quality.technical_trail, "hike_rating"),
      metric(t("Steps"), quality.steps, "road_class"),
      metric(t("Poor smoothness"), quality.poor_smoothness, "smoothness"),
      metric(t("Major roads"), quality.major_road, "road_class"),
    ]);
  }
  if (quality.activity_kind === "cycling") {
    return section(t("Cycling quality"), [
      metric(t("Cycling network"), quality.cycling_network, "bike_network"),
      metric("Cycleway-like", quality.cycleway_like, "road_class"),
      metric("Paved", quality.paved, "surface"),
      metric(t("Suitable unpaved"), quality.suitable_unpaved, "surface"),
      metric("Tracks", quality.track, "road_class"),
      metric(t("Rough surface"), quality.rough_surface, "surface"),
      metric(t("Steps"), quality.steps, "road_class"),
      metric(t("Major roads"), quality.major_road, "road_class"),
      [
        t("MTB-rating coverage"),
        Number(quality.detail_coverage?.mtb_rating ?? 0) > 0
          ? formatPercent(quality.mtb_rating.coverage_share)
          : t("not evaluated"),
      ],
    ]);
  }
  return "";
}

function structuralAlternativeSummary(candidate) {
  if (
    !candidate.roles?.includes("best_structural_refinement") &&
    !candidate.roles?.includes("distinct_structural_refinement")
  ) return "";
  const details = candidate.diagnostics?.details ?? {};
  const oppositeImprovement = Number(details.opposite_direction_improvement_m);
  const spurImprovement = Number(details.spur_repeated_distance_improvement_m);
  const backtrackingImprovement = Number(details.immediate_backtracking_improvement_m);
  const repetitionImprovement = Number(details.total_repetition_improvement_m);
  const shapeStatements = [];
  if (Number.isFinite(oppositeImprovement) && oppositeImprovement > 0) {
    shapeStatements.push(tr`${escapeHtml(formatDistance(oppositeImprovement))} less opposite-direction travel.`);
  }
  if (Number.isFinite(repetitionImprovement) && repetitionImprovement > 0) {
    shapeStatements.push(tr`${escapeHtml(formatDistance(repetitionImprovement))} less repeated travel.`);
  } else if (Number.isFinite(spurImprovement) && spurImprovement > 0) {
    shapeStatements.push(tr`${escapeHtml(formatDistance(spurImprovement))} less repeated excursion travel.`);
  } else if (Number.isFinite(backtrackingImprovement) && backtrackingImprovement > 0) {
    shapeStatements.push(tr`${escapeHtml(formatDistance(backtrackingImprovement))} less immediate backtracking.`);
  }
  if (!shapeStatements.length) return "";
  const distanceChange = Number(details.distance_change_m);
  const distanceStatement = Number.isFinite(distanceChange)
    ? distanceChange > 0
      ? tr` Total route is ${escapeHtml(formatDistance(distanceChange))} longer.`
      : distanceChange < 0
        ? tr` Total route is ${escapeHtml(formatDistance(Math.abs(distanceChange)))} shorter.`
        : t(" Total route distance is unchanged.")
    : "";
  const coverageUnchanged = Number(details.reached_change) === 0
    && Number(details.approximated_change) === 0
    && Number(details.dropped_change) === 0;
  const coverageStatement = coverageUnchanged
    ? t(" Requested-place coverage is unchanged.")
    : t(" Requested-place coverage remains valid.");
  const heading = candidate.roles?.includes("distinct_structural_refinement")
    ? t("Distinct major-spur alternative")
    : t("Best route-shape alternative");
  return `<section class="repair-summary structural-alternative-summary"><h3>${heading}</h3><p>${shapeStatements.join(" ")}${distanceStatement}${coverageStatement}</p></section>`;
}

function bestExcludedRefinementSummary(diagnostics) {
  const details = diagnostics?.details?.best_excluded_refinement;
  if (!details) return "";
  const oppositeImprovement = Number(details.opposite_direction_improvement_m);
  const spurImprovement = Number(details.spur_repeated_distance_improvement_m);
  const backtrackingImprovement = Number(details.immediate_backtracking_improvement_m);
  const repetitionImprovement = Number(details.total_repetition_improvement_m);
  const removed = Math.max(
    Number.isFinite(oppositeImprovement) ? oppositeImprovement : 0,
    Number.isFinite(spurImprovement) ? spurImprovement : 0,
    Number.isFinite(backtrackingImprovement) ? backtrackingImprovement : 0,
    Number.isFinite(repetitionImprovement) ? repetitionImprovement : 0,
  );
  const distanceChange = Number(details.distance_change_m);
  const distanceStatement = Number.isFinite(distanceChange)
    ? distanceChange > 0
      ? tr`Added ${escapeHtml(formatDistance(distanceChange))}.`
      : distanceChange < 0
        ? tr`Shortened by ${escapeHtml(formatDistance(Math.abs(distanceChange)))}.`
        : t("Route distance unchanged.")
    : "";
  const coverageUnchanged = Number(details.reached_change) === 0
    && Number(details.approximated_change) === 0
    && Number(details.dropped_change) === 0;
  return `<section class="repair-summary excluded-refinement-summary"><h3>${t("Best excluded route refinement")}</h3><p>${tr`Removed ${escapeHtml(formatDistance(removed))} of repeated travel. ${distanceStatement} ${coverageUnchanged ? t("Requested-place coverage unchanged. ") : ""}Not included in the displayed portfolio.`}</p></section>`;
}

function currentEndpointAdjustments() {
  if (state.resultsInvalidated || ["running", "reversing"].includes(state.request.status)) return [];
  const candidate = selectedCandidate();
  return (candidate ? candidate.diagnostics.details.local_routing?.endpoint_adjustments ?? []
    : isImmutableSnapshotDisplay() ? [] : state.generationResult?.search_diagnostics.details.local_planning?.endpoint_proposals ?? [])
    .filter(item => item.status === "adjusted" || item.status === "review_required");
}

function renderEndpointAdjustmentViews() {
  const adjustments = currentEndpointAdjustments();
  const disabled = isImmutableSnapshotDisplay() || ["running", "reversing"].includes(state.request.status);
  const profile = currentDisplayContext()?.routing_profile ?? state.routingProfile;
  for (const id of ["endpoint-adjustments-map", "endpoint-adjustments-routes"]) renderEndpointAdjustments(byId(id), adjustments, {
    profileLabel: profile ? profileDisplayName(profile) : t("the selected activity"), disabled,
    onShow: item => {
      if (!currentEndpointAdjustments().includes(item)) return;
      appShell?.show("map");
      setRouteDockExpanded(byId("route-dock"), false);
      const disclosures = byId("endpoint-adjustments-map").querySelectorAll("details");
      for (const disclosure of disclosures) {
        disclosure.open = false;
        if (disclosure.dataset.adjustmentRole === item.role) disclosure.querySelector("summary").focus({ preventScroll: true });
      }
      // Wait for the shell's map resize, then keep both markers above the dock.
      requestAnimationFrame(() => {
        if (!currentEndpointAdjustments().includes(item)) return;
        fitCoordinates([item.requested_coordinate, item.routed_coordinate].map(point => [point.lon, point.lat]), {
          maxZoom: 18,
          padding: mapViewportPadding(24),
        });
      });
    },
    onMove: item => { if (!disabled && currentEndpointAdjustments().includes(item)) byId(`set-hard-${item.endpoint}`).click(); },
    onUse: item => {
      if (disabled || !currentEndpointAdjustments().includes(item)) return;
      replaceResolvedRouteLocation({ endpoint: item.endpoint }, item.routed_coordinate, { assignEndpoint: assignActiveEndpoint });
      clearPointPlacement(); hideError(); invalidateAndRender();
      setLocalizedText(byId("request-status"), () => t("Routed point adopted. Generate again to use the updated request."));
      appShell?.show("map");
    },
  });
}

function changeEndpointSnapPolicy(kind, policy) {
  const point = activeEndpoints()[kind];
  if (!point || isImmutableSnapshotDisplay() || ["running", "reversing"].includes(state.request.status)) return;
  endpointSnapPolicy({ start: policy, end: policy });
  rememberPointEdit(`${kind === "start" ? "Start" : "End"} snap policy changed`);
  assignActiveEndpoint(kind, { ...point, snapPolicy: policy });
  invalidateAndRender();
}

function renderCandidatesPanel() {
  const container = byId("candidate-list");
  const candidates = currentDisplayedCandidates();
  const result = currentDisplayContext();
  setLocalizedText(byId("candidates-title"), () => candidates.length === 1 ? t("Your route") : candidates.length ? tr`${candidates.length} routes to explore` : t("Routes"));
  setLocalizedText(byId("search-summary"), () => candidates.length
    ? `${result?.kind === "waypoint_route" ? t("Connect my points") : t("Suggest a route")} · ${profileDisplayName(result?.routing_profile)}`
    : "");
  byId("results-back-to-plan").classList.toggle("hidden", Boolean(candidates.length));
  if (!candidates.length) {
    container.innerHTML = emptyResultsMarkup(state);
    return;
  }
  renderRouteChoices(container, candidates, state.selectedSignature, selectCandidate);
}

function section(title, rows) {
  return `<section><h3>${escapeHtml(title)}</h3>${metricRows(rows)}</section>`;
}

function routeShapeIssuesSection(analysis, candidate) {
  if (!analysis.spurs || analysis.spurs.warnings?.includes("spur_analysis_unavailable")) {
    return '<section class="route-shape-issues"><h3>Route shape issues</h3><p>Excursion analysis is unknown because routed edge identity is unavailable.</p></section>';
  }
  const spurAnalysis = analysis.spurs ?? {
    spurs: [],
    spur_count: 0,
    total_repeated_distance_m: 0,
  };
  if (!spurAnalysis.spurs.length) {
    return '<section class="route-shape-issues"><h3>Route shape issues</h3><p>No substantial out-and-back excursion detected.</p><p class="context-note">This does not claim that the route is globally optimal.</p></section>';
  }
  const cards = spurAnalysis.spurs.map((spur, index) => {
    const stopNames = spur.deliberate_stop_names ?? [];
    const turnaround = stopNames.length
      ? `near ${stopNames[0]}`
      : t("on the routed corridor");
    const construction = candidate?.diagnostics?.details?.construction;
    const refinementStatus = construction === "edge_aware_global_optimization"
      ? t("The edge-aware optimizer tested route-wide alternatives; this excursion remains in the final route.")
      : t("No published edge-aware alternative removed this excursion.");
    return `<button type="button" class="spur-card" data-spur-id="${escapeHtml(spur.id)}" aria-label="Focus map on out-and-back excursion ${index + 1}"><strong>${t("Out-and-back excursion")}</strong><span>${tr`Repeated corridor: ${formatDistance(spur.repeated_distance_m)}`}</span><span>${tr`Complete excursion: ${formatDistance(spur.total_excursion_distance_m)}`}</span><span>${tr`Turnaround: ${escapeHtml(turnaround)}`}</span><span>${tr`Deliberate stops inside this excursion: ${stopNames.length ? escapeHtml(stopNames.join(", ")) : t("None")}`}</span><em>${t("Candidate for route refinement")}</em><small>${escapeHtml(refinementStatus)}</small></button>`;
  }).join("");
  return `<section class="route-shape-issues"><h3>${t("Route shape issues")}</h3><p><strong>${tr`${formatCount(spurAnalysis.spur_count)} out-and-back excursion${spurAnalysis.spur_count === 1 ? "" : "s"}`}</strong><br>${tr`${formatDistance(spurAnalysis.total_repeated_distance_m)} repeated inside excursions`}</p><div class="spur-list">${cards}</div></section>`;
}

function natureSection(nature, search) {
  if (!nature) {
    return section(t("Mapped nature context"), [
      [t("Index available"), search.nature_index_available ? "Yes" : "No"],
      [t("Nature analysis"), t("not evaluated")],
    ]) + '<p class="context-note">Nature metrics are not zero: they were not evaluated because the local OSM nature index or analysis was unavailable.</p>';
  }
  const breakdown = nature.score_breakdown;
  const component = (value) => `${value.points >= 0 ? "+" : ""}${value.points.toFixed(1)} points · weight ${value.weight.toFixed(2)} × ${formatPercent(value.share)}`;
  const waterBuffer = state.config?.nature_water_buffer_m ?? 100;
  const warnings = nature.warnings.map((warning) => friendlyLabel(warning)).join("; ") || t("None");
  return section(t("Mapped nature context"), [
    [t("Nature score"), `${nature.nature_score.toFixed(1)} / 100`],
    [t("Base score"), breakdown.base_score.toFixed(1)],
    [t("Woodland reward"), component(breakdown.woodland_reward)],
    [t("Open-natural reward"), component(breakdown.open_natural_reward)],
    [t("Agriculture reward"), component(breakdown.agriculture_reward)],
    [t("Park/protected reward"), component(breakdown.park_or_protected_reward)],
    [t("Near-water reward"), component(breakdown.near_water_reward)],
    [t("Urban penalty"), component(breakdown.urban_penalty)],
    [t("Unknown penalty"), component(breakdown.unknown_penalty)],
    ["Woodland", `${formatDistance(nature.woodland.distance_m)} · ${formatPercent(nature.woodland.share)}`],
    [t("Open natural"), `${formatDistance(nature.open_natural.distance_m)} · ${formatPercent(nature.open_natural.share)}`],
    ["Agriculture", `${formatDistance(nature.agriculture.distance_m)} · ${formatPercent(nature.agriculture.share)}`],
    [t("Water crossing"), `${formatDistance(nature.water_crossing.distance_m)} · ${formatPercent(nature.water_crossing.share)}`],
    ["Urban/developed", `${formatDistance(nature.urban.distance_m)} · ${formatPercent(nature.urban.share)}`],
    [t("Unknown land cover"), `${formatDistance(nature.unknown_landcover.distance_m)} · ${formatPercent(nature.unknown_landcover.share)}`],
    [t("Park or protected"), `${formatDistance(nature.park_or_protected.distance_m)} · ${formatPercent(nature.park_or_protected.share)}`],
    [tr`Within ${waterBuffer} m of mapped water`, `${formatDistance(nature.near_water.distance_m)} · ${formatPercent(nature.near_water.share)}`],
    [t("Nature warnings"), warnings],
    [t("Index features"), formatCount(nature.index_feature_count)],
  ]) + '<p class="context-note">Derived from local OpenStreetMap polygons. Unknown means unmapped or outside the index. Near water describes proximity to mapped water, not a water view. Protected-area tags do not guarantee public access. The score describes mapped environmental context—not beauty, biodiversity, accessibility, or safety.</p>';
}

function loopGeometrySection(geometry) {
  const sectorGrid = (shares) => `<ol class="loop-sector-grid">${Array.from({ length: 8 }, (_, index) => `<li><span>${tr`Sector ${index + 1}`}</span><strong>${shares ? shares[index].toFixed(6) : t("not evaluated")}</strong></li>`).join("")}</ol>`;
  if (!geometry) {
    return `<section class="loop-geometry-panel"><h3>${t("Loop geometry")}</h3>${metricRows([
      [t("Shape penalty (lower is better)"), t("not evaluated")],
      [t("Compactness"), t("not evaluated")],
      [t("Sector balance"), t("not evaluated")],
      [t("Near-parallel corridor"), t("not evaluated")],
      [t("Outbound/return proximity"), t("not evaluated")],
      ["Self-crossings", t("not evaluated")],
    ])}<details class="loop-geometry-exact"><summary>${t("Exact geometry details")}</summary>${sectorGrid(null)}${metricRows([
      [t("Elongation"), t("not evaluated")],
      [t("Angular monotonicity"), t("not evaluated")],
      [t("Maximum sector share"), t("not evaluated")],
      [t("Occupied sectors"), t("not evaluated")],
      [t("Enclosed area"), t("not evaluated")],
      [t("Convex-hull area"), t("not evaluated")],
      [t("Mean radius"), t("not evaluated")],
      [t("Maximum radius"), t("not evaluated")],
      [t("Start/end gap"), t("not evaluated")],
      [t("Closed within 25 m"), t("not evaluated")],
      [t("Crossing component"), t("not evaluated")],
      [t("Near-parallel component"), t("not evaluated")],
      [t("Compactness component"), t("not evaluated")],
      [t("Sector-imbalance component"), t("not evaluated")],
      [t("Elongation component"), t("not evaluated")],
    ])}</details><p class="context-note">${t("Loop-geometry metrics are unknown, not numeric zero.")}</p></section>`;
  }
  const penalty = geometry.penalty_breakdown;
  return `<section class="loop-geometry-panel"><h3>${t("Loop geometry")}</h3>${metricRows([
    [t("Shape penalty (lower is better)"), penalty.total.toFixed(6)],
    [t("Compactness"), geometry.compactness.toFixed(6)],
    [t("Sector balance"), geometry.sector_balance.toFixed(6)],
    [t("Near-parallel corridor"), `${geometry.near_parallel.distance_m.toFixed(2)} m · ${formatPercent(geometry.near_parallel.share)}`],
    [t("Outbound/return proximity"), `${geometry.outbound_return_proximity.distance_m.toFixed(2)} m · ${formatPercent(geometry.outbound_return_proximity.share)}`],
    ["Self-crossings", formatCount(geometry.self_crossing_count)],
  ])}<details class="loop-geometry-exact"><summary>${t("Exact geometry details")}</summary>${sectorGrid(geometry.sector_distance_shares)}${metricRows([
    [t("Elongation"), geometry.elongation.toFixed(6)],
    [t("Angular monotonicity"), geometry.angular_monotonicity.toFixed(6)],
    [t("Maximum sector share"), formatPercent(geometry.maximum_sector_distance_share)],
    [t("Occupied sectors"), `${geometry.occupied_sector_count} / ${geometry.sector_count}`],
    [t("Enclosed area"), `${geometry.enclosed_area_m2.toFixed(2)} m²`],
    [t("Convex-hull area"), `${geometry.convex_hull_area_m2.toFixed(2)} m²`],
    [t("Mean radius"), `${geometry.mean_radius_m.toFixed(2)} m`],
    [t("Maximum radius"), `${geometry.max_radius_m.toFixed(2)} m`],
    [t("Start/end gap"), `${geometry.start_end_gap_m.toFixed(2)} m`],
    [t("Closed within 25 m"), geometry.closed ? "Yes" : "No"],
    [t("Crossing component"), `${penalty.crossing_penalty.toFixed(6)} = ${penalty.crossing_penalty_per_crossing.toFixed(2)} × ${penalty.crossing_count_input}`],
    [t("Near-parallel component"), `${penalty.near_parallel_penalty.toFixed(6)} = ${penalty.near_parallel_penalty_weight.toFixed(2)} × ${penalty.near_parallel_share_input.toFixed(6)}`],
    [t("Compactness component"), `${penalty.compactness_penalty.toFixed(6)} = ${penalty.compactness_penalty_weight.toFixed(2)} × (1 − ${penalty.compactness_input.toFixed(6)})`],
    [t("Sector-imbalance component"), `${penalty.sector_imbalance_penalty.toFixed(6)} = ${penalty.sector_imbalance_penalty_weight.toFixed(2)} × (1 − ${penalty.sector_balance_input.toFixed(6)})`],
    [t("Elongation component"), `${penalty.elongation_penalty.toFixed(6)} = ${penalty.elongation_penalty_weight.toFixed(2)} × (1 − ${penalty.elongation_input.toFixed(6)})`],
  ])}</details><p class="context-note">${t("These projected shape diagnostics do not measure scenic beauty, safety or accessibility. Dense networks and routed geometry resolution can affect corridor detection.")}</p></section>`;
}

function constraintItinerary(candidate) {
  const reached = (candidate.reached_stops ?? []).map((stop, index) => {
    return `<li class="itinerary-stop" role="button" tabindex="0" data-itinerary-stop-id="${escapeHtml(stop.id)}" data-itinerary-origin="${escapeHtml(stop.selection_origin)}"><strong>${index + 1}. ${escapeHtml(stop.name)}</strong><span>${tr`${escapeHtml(friendlyLabel(stop.category))} · ${escapeHtml(friendlyLabel(stop.resolved_approach.kind))} · arrival ${Number(stop.route_to_approach_m).toFixed(1)} m / ${Number(stop.resolved_approach.arrival_tolerance_m).toFixed(0)} m · ${escapeHtml(friendlyLabel(stop.selection_method))}`}</span></li>`;
  }).join("");
  const approximated = (candidate.approximated_stops ?? []).map((stop) => `<li class="itinerary-stop approximated" role="button" tabindex="0" data-itinerary-stop-id="${escapeHtml(stop.id)}" data-itinerary-origin="${escapeHtml(stop.selection_origin)}"><strong>${tr`${escapeHtml(stop.name)} — approximated`}</strong><span>${tr`${formatDistance(stop.distance_m)} from the semantic place · normal tolerance ${formatDistance(stop.normal_tolerance_m)} · ${escapeHtml(friendlyLabel(stop.reason))} · access ${escapeHtml(friendlyLabel(stop.resolved_approach.access))}`}</span><div class="button-row"><button type="button" data-compromise-action="exact" data-constraint-id="${escapeHtml(stop.id)}">${t("Make exact")}</button><button type="button" data-compromise-action="accept" data-constraint-id="${escapeHtml(stop.id)}">${t("Accept approximation")}</button><button type="button" data-compromise-action="remove" data-constraint-id="${escapeHtml(stop.id)}">${t("Remove stop")}</button></div></li>`).join("");
  const dropped = (candidate.dropped_stops ?? []).map((stop) => `<li><strong>${escapeHtml(stop.name)}</strong><span>${tr`Drop reason: ${escapeHtml(friendlyLabel(stop.reason))}`}</span></li>`).join("");
  if (!reached && !approximated && !dropped) {
    return "";
  }
  return `<section><h3>${t("Route itinerary")}</h3><ol class="tour-itinerary">${reached}${approximated}</ol>${dropped ? `<details><summary>${tr`Dropped stops (${candidate.dropped_stops.length})`}</summary><ul class="tour-itinerary dropped">${dropped}</ul></details>` : ""}</section>`;
}

function compromiseSummary(candidate) {
  const target = candidate.compromises.find((item) => item.code === "target_distance_missed");
  return `<section class="compromise-summary" role="status" aria-live="polite"><h3>${t("Route generated")}</h3>${metricRows([
    [t("Reached"), formatCount(candidate.reached_stops.length)],
    [t("Approximated"), formatCount(candidate.approximated_stops.length)],
    [t("Dropped"), formatCount(candidate.dropped_stops.length)],
    ["Target", target ? tr`Missed by ${formatDistance(target.distance_m)}` : t("Within requested tolerance")],
  ])}</section>`;
}

function endpointSection(result) {
  const visits = result.endpoint_visits ?? [];
  const startVisit = visits[0];
  const endVisit = visits[1];
  const coordinate = (point) => point
    ? `${point.name ? `${point.name} · ` : ""}${Number(point.lat).toFixed(6)}, ${Number(point.lon).toFixed(6)}`
    : t("Not available");
  return section(t("Route endpoints"), [
    [t("Route topology"), friendlyLabel(result.topology ?? "loop")],
    [t("Effective start"), coordinate(result.effective_start)],
    [t("Start source"), friendlyLabel(startVisit?.source ?? "explicit")],
    [t("Start snap distance"), startVisit?.snap_distance_m == null ? t("Unknown") : formatDistance(startVisit.snap_distance_m)],
    [t("Effective end"), coordinate(result.effective_end)],
    [
      t("End source"),
      friendlyLabel(
        endVisit?.source ?? (result.topology === "point_to_point" ? "explicit" : "loop_closure"),
      ),
    ],
    [t("End snap distance"), endVisit?.snap_distance_m == null ? t("Unknown") : formatDistance(endVisit.snap_distance_m)],
  ]);
}

function renderMetrics() {
  const candidate = selectedCandidate();
  const result = currentDisplayContext();
  byId("metrics-empty").classList.toggle("hidden", Boolean(candidate));
  byId("metrics-content").classList.toggle("hidden", !candidate);
  const busy = ["running", "reversing"].includes(state.request.status);
  const readOnly = isImmutableSnapshotDisplay();
  const savingUnavailable = !state.config?.saved_routes_available;
  byId("selected-route-panel").classList.toggle("hidden", !candidate);
  setLocalizedText(byId("metrics-title"), () => candidate ? tr`Route ${candidate.rank} · selected` : t("Selected route"));
  setLocalizedText(byId("selected-route-context"), () => candidate
    ? `${profileDisplayName(candidate.routing_profile)} · ${candidate.topology === "loop" ? t("Loop") : t("Point to point")}` : "");
  byId("download-gpx").setAttribute("aria-label", candidate ? tr`Export Route ${candidate.rank} as GPX` : t("Export GPX"));
  byId("save-route-selected").classList.toggle("hidden", savingUnavailable || readOnly || !candidate);
  byId("download-gpx").disabled = !candidate || busy || pendingGpxExport !== null;
  byId("download-gpx").setAttribute("aria-busy", String(pendingGpxExport !== null));
  byId("reverse-route").disabled = readOnly || !candidate || busy || Boolean(localPlanner) || Boolean(state.importedGpx && !state.generationResult);
  byId("reverse-route").title = localPlanner ? t("On-device route reversal is not available yet. Edit the ordered points and generate a new route.") : "";
  byId("save-route").disabled = savingUnavailable || readOnly || !candidate || busy;
  byId("save-route").classList.toggle("hidden", savingUnavailable || readOnly || !candidate);
  byId("save-route-selected").disabled = savingUnavailable || readOnly || !candidate || busy;
  setLocalizedText(byId("reverse-route"), () => result?.topology === "loop"
    ? t("Reverse loop direction")
    : t("Reverse direction"));
  if (candidate && result) renderCanonicalMetrics(candidate, result);
}
function renderCanonicalMetrics(candidate, result) {
  const analysis = candidate.route.analysis;
  const diagnostics = currentSearchDiagnostics();
  const phaseRows = Object.entries(diagnostics?.budget.phases ?? {}).map(([phase, usage]) => [
    `${friendlyLabel(phase)} budget`,
    `${usage.used} / ${usage.limit}${usage.exhausted ? " · exhausted" : ""}`,
  ]);
  const scoreRows = Object.entries(candidate.score.components).map(([component, value]) => [
    friendlyLabel(component),
    Number(value).toFixed(6),
  ]);
  const warnings = [...new Set([
    ...(diagnostics?.warnings ?? []),
    ...analysis.warnings,
    ...(analysis.spurs?.warnings ?? []),
    ...(analysis.loop_geometry?.warnings ?? []),
    ...(analysis.nature?.warnings ?? []),
  ])];
  byId("metrics-content").innerHTML = compromiseSummary(candidate)
    + traversalSummary(candidate, result)
    + constraintItinerary(candidate)
    + section(t("Route quality"), [
      [t("Total repetition"), repetitionShare(analysis) === null ? t("Unknown") : `${formatDistance(analysis.repetition.repeated_distance.distance_m)} · ${formatPercent(analysis.repetition.repeated_distance.share)}`],
      [t("Immediate backtracking"), backtrackShare(analysis) === null ? t("Unknown") : `${formatDistance(analysis.immediate_backtrack.distance_m)} · ${formatPercent(analysis.immediate_backtrack.share)}`],
      ["Paved", detailShare(analysis, "paved", "surface") === null ? t("Unknown") : formatPercent(analysis.paved.share)],
      [t("Major roads"), detailShare(analysis, "major_road", "road_class") === null ? t("Unknown") : formatPercent(analysis.major_road.share)],
    ])
    + routeShapeIssuesSection(analysis, candidate)
    + activityQualitySection(analysis)
    + section(t("Mapped environment"), analysis.nature ? [
      ["Woodland", formatPercent(analysis.nature.woodland.share)],
      [t("Open natural land"), formatPercent(analysis.nature.open_natural.share)],
      [t("Unknown land cover"), formatPercent(analysis.nature.unknown_landcover.share)],
    ] : [[t("Nature"), t("Unknown — mapped nature analysis is unavailable")]])
    + '<p class="context-note">Mapped measurements may have incomplete coverage. They do not guarantee current conditions or access.</p>'
    + '<details class="route-diagnostics"><summary>Technical diagnostics</summary>'
    + endpointSection(result)
    + structuralAlternativeSummary(candidate)
    + natureSection(analysis.nature, { nature_index_available: Boolean(analysis.nature) })
    + section(t("Canonical candidate"), [
      [t("Candidate ID"), candidate.id],
      [t("Routing profile"), profileDisplayName(candidate.routing_profile)],
      ["Traversal", directionLabel(candidate.traversal)],
      ["Roles", candidate.roles.map(friendlyLabel).join(", ") || t("None")],
      [t("Distance"), formatDistance(candidate.route.summary.distance_m)],
      [t("Target error"), formatDistance(candidate.diagnostics.target_error_m)],
      [t("Within tolerance"), candidate.diagnostics.within_tolerance ? "Yes" : "No"],
      [t("Planning constraints met"), candidate.diagnostics.safety_eligible ? "Yes" : "No"],
      ["Reached / approximated / dropped", `${candidate.reached_stops.length} / ${candidate.approximated_stops.length} / ${candidate.dropped_stops.length}`],
    ])
    + section("Score", [["Total", Number(candidate.score.total).toFixed(6)], ...scoreRows])
    + (result.topology === "loop" ? loopGeometrySection(analysis.loop_geometry) : "")
    + (diagnostics ? bestExcludedRefinementSummary(diagnostics) : "")
    + (diagnostics
      ? section(t("Search budget"), [
        [t("Total used"), `${diagnostics.budget.total_used} / ${diagnostics.budget.total_limit}`],
        [t("Cache hits / misses"), `${diagnostics.cache.hit_count} / ${diagnostics.cache.miss_count}`],
        ...phaseRows,
      ])
      : `<section><h3>${t("Search diagnostics")}</h3><p>${tr`Not applicable — loaded immutable ${state.outingDisplay ? "outing" : "saved-route"} snapshot.`}</p></section>`)
    + `<section><h3>${t("Warnings")}</h3><ul class="warning-list">${warnings.length ? warnings.map((warning) => `<li>${escapeHtml(friendlyLabel(warning))}</li>`).join("") : `<li>${diagnostics ? t("No route or search warnings.") : t("No route warnings. Search diagnostics are not applicable.")}</li>`}</ul></section>` + '</details>';
  wireCompromiseActions(candidate);
}

function constraintStateById(id) {
  if (state.planningMode === "auto_tour") {
    const index = state.autoTour.requestedPlaces.findIndex((place, position) => (
      requestedPlaceIdentifier(place, position) === id
    ));
    return index < 0 ? null : { collection: state.autoTour.requestedPlaces, index };
  }
  const index = state.points.findIndex((point) => point.id === id);
  return index < 0 ? null : { collection: state.points, index };
}

function wireCompromiseActions(candidate) {
  if (isImmutableSnapshotDisplay()) {
    byId("metrics-content")
      .querySelectorAll("[data-compromise-action]")
      .forEach((button) => button.remove());
  }
  byId("metrics-content").querySelectorAll("[data-spur-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const spur = candidate.route.analysis.spurs?.spurs.find(
        (value) => value.id === button.dataset.spurId,
      );
      if (!spur) return;
      focusSpur(spur);
      setLocalizedText(byId("request-status"), () => t("Focused map on the complete out-and-back excursion."));
    });
  });
  byId("metrics-content").querySelectorAll(".itinerary-stop[data-itinerary-stop-id]").forEach((item) => {
    const focusStop = () => {
      const id = item.dataset.itineraryStopId;
      const stop = [...candidate.reached_stops, ...candidate.approximated_stops]
        .find((value) => value.id === id);
      if (!stop) return;
      state.selectedRequestedPlaceId = id;
      state.pendingRequestedPlacePopupId = id;
      renderMapData();
      const coordinate = stop.resolved_approach.coordinate;
      focusCoordinate([coordinate.lon, coordinate.lat]);
    };
    item.addEventListener("click", (event) => {
      if (event.target.closest("button")) return;
      focusStop();
    });
    item.addEventListener("keydown", (event) => {
      if (event.target.closest("button") || !["Enter", " "].includes(event.key)) return;
      event.preventDefault();
      focusStop();
    });
  });
  byId("metrics-content").querySelectorAll("[data-compromise-action]").forEach((button) => {
    button.disabled = isImmutableSnapshotDisplay();
    button.addEventListener("click", () => {
      if (isImmutableSnapshotDisplay()) return;
      const id = button.dataset.constraintId;
      const target = constraintStateById(id);
      if (!target) return;
      const stop = candidate.approximated_stops.find((value) => value.id === id);
      if (!stop) return;
      rememberPointEdit("Stop constraint updated");
      const item = target.collection[target.index];
      if (button.dataset.compromiseAction === "remove") {
        target.collection.splice(target.index, 1);
      } else if (button.dataset.compromiseAction === "exact") {
        if (state.planningMode === "auto_tour") {
          target.collection.splice(target.index, 1);
          state.autoTour.hardPoints.push({
            id: stop.id,
            name: stop.name,
            ...stop.semantic_coordinate,
            constraintStrength: "exact",
          });
          state.points = [state.autoTour.start, ...state.autoTour.hardPoints].filter(Boolean);
        } else {
          item.constraintStrength = "exact";
          item.approachOverride = null;
        }
      } else {
        item.constraintStrength = "best_effort";
        item.approachOverride = { ...stop.resolved_approach.coordinate };
      }
      invalidateAndRender();
      setEditableRequestStatus(() => (t("Constraint updated. Generate again to apply it.")));
    });
  });
}

function renderStatus() {
  if (localPlanner) updateProfileDescription();
  const running = ["running", "reversing"].includes(state.request.status);
  const readOnly = isImmutableSnapshotDisplay();
  const open = isOpenPlan();
  setLocalizedText(byId("controls-title"), () => t("Plan"));
  byId("map-route-intent").classList.toggle("hidden", running || readOnly || !activeEndpoints().start || Boolean(activeMapPlacementGuidance()));
  const undoLabel = pointUndoLabel();
  for (const id of ["undo-point-edit-plan"]) {
    byId(id).hidden = !undoLabel || running || readOnly;
    setLocalizedText(byId(id), () => tr`${t(undoLabel)} · Undo`);
    byId(id).setAttribute("aria-label", tr`${t(undoLabel)} · Undo`);
  }
  setLocalizedText(byId("generation-title"), () => state.request.status === "reversing"
    ? t("Reversing route…")
    : open ? t("Planning your route…") : t("Planning your loop…"));
  const availability = currentGenerationAvailability();
  const guidance = activeMapPlacementGuidance();
  byId("map-edit-notice").classList.toggle("hidden", !guidance || running || readOnly);
  byId("map-edit-guidance").textContent = guidance;
  byId("add-point-mode").setAttribute("aria-pressed", String(state.addPointMode));
  setLocalizedText(byId("add-point-mode").lastChild, () => state.addPointMode ? t(" Cancel adding") : state.planningMode === "waypoint_route" ? t(" Add stop on map") : t(" Add on map"));
  for (const kind of ["start", "end"]) byId(`hard-${kind}-control`).classList.toggle("selected-endpoint", state.selectedEndpointKind === kind);
  // Derive copy from the same authorities as Generate, never a second readiness store.
  const profile = selectedProfileStatus();
  setLocalizedText(byId("planning-readiness"), () => localPlanner
    ? regionPlanningError ? regionFailureMessage(regionPlanningError)
      : !localRouteCapabilities?.enabled ? t("On-device routing is unavailable in this app build.")
      : !localRouteCapabilities.installed_pack_count ? t("Download a supported region to plan.")
      : !profile?.available ? t("This activity is unavailable in the installed region.")
      : tr`Ready on device · ${byId("planning-region").selectedOptions[0]?.textContent || t("Installed region")}`
    : profile?.available ? t("Routing service ready") : t("Selected activity unavailable in the routing service"));
  byId("plan-regions").classList.toggle("hidden", !localPlanner);
  setLocalizedText(byId("plan-capabilities"), () => localPlanner
    ? state.planningMode === "auto_tour"
      ? t("On-device suggestions support loops from Start, without required interior points or imported stops. Other settings are kept and unsupported requests report an error.")
      : t("On-device connections support exact points and shortest paths, with nature and loop preferences off. Unsupported choices report an error; your points are not weakened.")
    : t("Choose a loop back to Start, or a point-to-point route with a destination. Available activities use the routing service."));
  byId("import-itinerary").disabled = readOnly || running;
  for (const id of ["ask-chatgpt", "plan-with-ai"]) byId(id).disabled = running || readOnly && !state.adventureDisplay;
  byId("restore-adventure").disabled = running || readOnly;
  byId("generate").disabled = readOnly || running || !availability.enabled;
  byId("generate-top").disabled = byId("generate").disabled;
  byId("generate-map").disabled = byId("generate").disabled;
  byId("generate-map").hidden = !localPlanner || readOnly || !availability.enabled;
  byId("cancel").classList.toggle("hidden", !running);
  byId("hard-start-control").disabled = running || readOnly;
  byId("generation-state").classList.toggle("hidden", !running);
  document
    .querySelectorAll("#route-form input, #route-form select, #poi-list input, #poi-list button, #add-point-mode, #clear-points, input[name='planning-mode']")
    .forEach((control) => { control.disabled = running || readOnly || control.dataset.boundaryDisabled === "true"; });
  renderEndpointTopologyControls(
    byId("hard-end-control"),
    byId("loop-end-explanation"),
    activeEndpoints().routeTopology,
    { controlsDisabled: running || readOnly },
  );
  byId("route-form").closest(".panel.controls").inert = readOnly && !state.adventureDisplay;
  byId("route-form").hidden = Boolean(state.adventureDisplay);
  byId("planning-points").hidden = Boolean(state.adventureDisplay);
  byId("route-dock").classList.toggle("hidden", Boolean(state.adventureDisplay || readOnly));
  if (state.adventureDisplay) setLocalizedText(byId("planning-readiness"), () => tr`Viewing ${state.adventureResult.chosen.proposal.name}. Your manual plan is kept; return to it from Routes.`);
  byId("clear-results").disabled = readOnly;
  byId("request-status").classList.toggle("running", running);
  if (!running && !readOnly) {
    const placementGuidance = pointValidation()
      ? ""
      : activeMapPlacementGuidance();
    if (placementGuidance) {
      byId("request-status").textContent = placementGuidance;
    } else if (!availability.enabled) {
      setLocalizedText(byId("request-status"), () => t(availability.reason));
    } else if (localPlanner && byId("request-status").textContent === localAvailabilityStatusText) {
      setLocalizedText(byId("request-status"), () => t("Ready to generate."));
    }
    if (localPlanner) localAvailabilityStatusText = placementGuidance || (!availability.enabled ? availability.reason : null);
  }
  renderRouteDock({ root: byId("route-dock"), disabled: running || readOnly,
    requiresReview: currentEndpointAdjustments().some(item => item.status === "review_required"),
    visits: selectedCandidate()?.diagnostics.details.required_waypoint_order ?? [],
    onSelectPoint: selectPoint, onSelectEndpoint: selectEndpoint,
    onClearSelection: () => { clearPointPlacement(); state.selectedPointIndex = null; state.selectedEndpointKind = null; render(); },
    onMove: beginPointMove, onRemove: removePoint, onReorder: movePoint,
    onEndpointPolicy: localPlanner ? changeEndpointSnapPolicy : null,
    onMoveEndpoint: kind => byId(`set-hard-${kind}`).click(),
    onClearEndpoint: kind => byId(`clear-hard-${kind}`).click(),
    onSearch: openLocationSearch,
    onChooseMap: () => {
      clearPointPlacement(); state.addPointMode = true;
      render(); appShell?.show("map", { focus: true });
    },
    onDetails: () => { appShell?.show("plan"); appShell?.reveal(state.selectedEndpointKind ? `#hard-${state.selectedEndpointKind}-control` : ".poi-row.selected"); },
  });
}

function renderEmptyState() {
  const hasWork = state.points.length > 0
    || state.importedGpx
    || currentDisplayedCandidates().length > 0;
  byId("planner-empty").classList.toggle("hidden", Boolean(hasWork || activeEndpoints().start || activeMapPlacementGuidance()));
  setLocalizedText(byId("empty-title"), () => localPlanner ? t("Or start on the map") : t("Start on the map"));
  setLocalizedText(byId("planner-empty").querySelector("p"), () => localPlanner ? t("Choose your Start.") : t("Tap the map to choose Start, then keep tapping to add stops."));
}

function renderElevation(value) {
  elevationView.render(adventureElevationView() ?? value,selectedCandidate());
  if (state.adventureDisplay) {
    byId("cancel-route-elevation").hidden = true;
    byId("retry-route-elevation").hidden = true;
  }
}

function render() {
  selectedRouteElevation?.sync(isImmutableSnapshotDisplay() || adventurePlanning ? null : selectedCandidate(),state.generationResult,selectedRegionId);
  renderElevation(state.selectedElevation);
  regionScreen?.render();
  renderModeControls();
  renderPoiEditor();
  renderCandidatesPanel();
  adventureResults.render(state.adventureDisplay ? state.adventureResult : null, selectedCandidate());
  renderEndpointAdjustmentViews();
  renderMetrics();
  renderStatus();
  renderMapData();
  renderEmptyState();
  renderSavedRoutePanel();
  renderOutingReceipt(state);
  renderPwaStatus(state);
  renderOfflineCopyControls(state);
  const imported = state.importedGpx;
  byId("gpx-summary").classList.toggle("hidden", !imported);
  if (imported) {
    setLocalizedText(byId("gpx-details"), () => tr`${imported.filename} · ${formatCount(imported.pointCount)} trackpoints · ${formatDistance(imported.distanceM)} locally calculated`);
  }
}

function renderPwaApplication() {
  if (state.outingDisplay) {
    renderCurrentOutingConnectivity();
    return;
  }
  render();
}

async function selectCandidate(candidateId) {
  if (!currentDisplayedCandidates().some((candidate) => candidate.id === candidateId)) return;
  state.selectedSignature = candidateId;
  if (state.adventureDisplay) void persistAdventureSelection();
  renderVisualization(null, false);
  if (!pendingGpxExport) byId("export-status").textContent = "";
  render();
  const candidate = selectedCandidate();
  if (!candidate) return;
  if (candidate.diagnostics.details.local_routing?.engine === "valhalla-mobile") {
    // The canonical result already supplies the exact routed line. Native edge
    // classifications are unavailable, so there is no extra highlight projection.
    // Keep the normal candidate line and direction arrows; never ask a server to
    // infer repetition or nature sections for a local route.
    renderVisualization(null, false);
    return;
  }
  try {
    let visualization = state.visualizationCache.get(candidateId);
    if (!visualization) {
      visualization = await visualizeRoute(candidate.route);
      if (!currentDisplayedCandidates().some((current) => current.id === candidateId)) return;
      state.visualizationCache.set(candidateId, visualization);
    }
    if (state.selectedSignature === candidateId) {
      renderVisualization(visualization, state.showNatureContext);
    }
  } catch (error) {
    handleError(error, t("Route highlighting failed."));
  }
}

function validateRequestControls() {
  updateOptionsFromControls();
  saveActivePoints();
  const availability = currentGenerationAvailability();
  if (!availability.enabled) throw new Error(availability.reason);
  const request = currentPlanRequest();
  if (request.distance_objective.target_m < 1000 || request.distance_objective.target_m > 200000) {
    throw new Error(t("Target distance must be between 1 and 200 km."));
  }
  if (request.distance_objective.tolerance_m < 100 || request.distance_objective.tolerance_m > 10000) {
    throw new Error(t("Tolerance must be between 0.1 and 10 km."));
  }
  if (
    request.distance_objective.maximum_m !== null
    && (!Number.isFinite(request.distance_objective.maximum_m)
      || request.distance_objective.maximum_m <= 0
      || request.distance_objective.maximum_m > 200000)
  ) {
    throw new Error(t("Maximum distance must be blank or between 0.1 and 200 km."));
  }
  return request;
}

async function generate() {
  if (isImmutableSnapshotDisplay()) return;
  hideError();
  let request;
  try {
    request = validateRequestControls();
  } catch (error) {
    showError(() => (error.message));
    return;
  }
  invalidateCandidates();
  state.resultsInvalidated = false;
  const id = state.request.id + 1;
  state.request = { status: "running", id, startedAt: Date.now() };
  setRouteDockExpanded(byId("route-dock"), false);
  state.abortController = new AbortController();
  const planningLabel = isOpenPlan() ? t("Planning your route") : t("Planning your loop");
  byId("request-status").textContent = `${planningLabel}… 0 s elapsed`;
  elapsedTimer = window.setInterval(() => {
    if (state.request.status !== "running" || state.request.startedAt === null) return;
    const seconds = Math.floor((Date.now() - state.request.startedAt) / 1000);
    byId("request-status").textContent = `${planningLabel}… ${seconds} s elapsed`;
  }, 1000);
  render();
  appShell?.reveal("#generation-state");
  try {
    const result = localPlanner
      ? await localPlanner.generate(request, state.abortController.signal)
      : await generatePlan(request, state.abortController.signal);
    if (state.request.id !== id) return;
    state.resultsInvalidated = false;
    state.generationResult = result;
    state.generationSourceRequest = request;
    state.selectedSignature = result.candidates[0]?.id ?? null;
    state.visualizationCache.clear();
    state.request = { status: "success", id, startedAt: null };
    setLocalizedText(byId("request-status"), () => result.candidates.length
      ? t(result.candidates.length === 1 ? "{count} route generated." : "{count} routes generated.", { count: result.candidates.length })
      : t("No route matches the required points and settings."));
    render();
    if (result.candidates.length) {
      fitCoordinates(result.candidates[0].route.geometry);
      await selectCandidate(result.candidates[0].id);
      appShell?.show("routes");
      byId("results-panel").scrollTop = 0;
    } else {
      showNoCandidateError(result);
    }
  } catch (error) {
    if (state.request.id !== id) return;
    const cancelled = error.name === "AbortError";
    state.request = { status: cancelled ? "cancelled" : "error", id, startedAt: null };
    setLocalizedText(byId("request-status"), () => cancelled ? t("Generation cancelled.") : t("Generation failed."));
    if (!cancelled) handleGenerationError(error);
  } finally {
    window.clearInterval(elapsedTimer);
    if (state.request.id === id) {
      state.abortController = null;
      render();
    }
  }
}

async function reverseSelectedRoute() {
  if (localPlanner) {
    showError(() => (t("On-device route reversal is not available yet. Edit the ordered points and generate a new route.")));
    return;
  }
  const sourceCandidate = selectedCandidate();
  const sourceRequest = state.generationSourceRequest;
  if (
    !sourceCandidate
    || !sourceRequest
    || ["running", "reversing"].includes(state.request.status)
  ) return;
  hideError();
  const sourceResult = state.generationResult;
  const id = state.request.id + 1;
  state.request = { status: "reversing", id, startedAt: Date.now() };
  state.abortController = new AbortController();
  setLocalizedText(byId("request-status"), () => t("Reversing route… 0 s elapsed"));
  elapsedTimer = window.setInterval(() => {
    if (state.request.status !== "reversing" || state.request.startedAt === null) return;
    const seconds = Math.floor((Date.now() - state.request.startedAt) / 1000);
    setLocalizedText(byId("request-status"), () => tr`Reversing route… ${seconds} s elapsed`);
  }, 1000);
  render();
  try {
    const response = await reversePlan(
      sourceRequest,
      sourceCandidate,
      1,
      state.abortController.signal,
    );
    if (state.request.id !== id) return;
    applyCanonicalRequestState(response.transformed_request);
    state.generationSourceRequest = response.transformed_request;
    state.generationResult = response.result;
    state.selectedSignature = response.result.candidates[0]?.id ?? null;
    state.visualizationCache.clear();
    state.request = { status: "success", id, startedAt: null };
    const reversed = response.result.candidates[0];
    const distanceChange = reversed
      ? reversed.route.summary.distance_m - sourceCandidate.route.summary.distance_m
      : 0;
    const outcomeChanges = reversed
      ? [
        ["reached", reversed.reached_stops.length - sourceCandidate.reached_stops.length],
        ["approximated", reversed.approximated_stops.length - sourceCandidate.approximated_stops.length],
        ["dropped", reversed.dropped_stops.length - sourceCandidate.dropped_stops.length],
      ].filter(([, difference]) => difference !== 0)
      : [];
    const outcomeSummary = outcomeChanges.length
      ? outcomeChanges.map(([outcome, difference]) => {
        const count = Math.abs(difference);
        const noun = `stop${count === 1 ? "" : "s"}`;
        if (difference < 0) return `${formatCount(count)} fewer ${outcome} ${noun}`;
        if (outcome === "approximated") return tr`${formatCount(count)} ${noun} became approximated`;
        if (outcome === "dropped") return `${formatCount(count)} ${noun} ${count === 1 ? "was" : "were"} dropped`;
        return tr`${formatCount(count)} more reached ${noun}`;
      }).join(", ") + "."
      : t("Stop outcome counts are unchanged.");
    const distanceSummary = Math.abs(distanceChange) < 50
      ? t("Distance is essentially unchanged.")
      : `${distanceChange >= 0 ? t("Distance increased") : t("Distance decreased")} by ${formatDistance(Math.abs(distanceChange))}.`;
    const directionalWarning = response.result.search_diagnostics.warnings.includes(
      "opposite_direction_uses_different_roads",
    )
      ? t("The opposite direction uses different roads.")
      : "";
    const changes = [outcomeSummary, distanceSummary, directionalWarning].filter(Boolean);
    setLocalizedText(byId("request-status"), () => tr`Route reversed and rerouted for ${profileDisplayName(response.result.routing_profile)}. ${changes.join(" ")}`);
    render();
    if (reversed) {
      fitCoordinates(reversed.route.geometry);
      await selectCandidate(reversed.id);
    }
  } catch (error) {
    if (state.request.id !== id) return;
    const cancelled = error.name === "AbortError";
    state.request = { status: cancelled ? "cancelled" : "error", id, startedAt: null };
    state.generationResult = sourceResult;
    state.selectedSignature = sourceCandidate.id;
    setLocalizedText(byId("request-status"), () => cancelled ? t("Reversal cancelled.") : t("Route reversal failed."));
    if (!cancelled) {
      if (error instanceof ApiError) {
        showError(
          () => (error.message),
          error.details,
          error.code,
          error.code === "exact_waypoint_not_reached"
            ? exactWaypointContext(error.metadata)
            : t("The selected source route remains displayed."),
          error.metadata?.suggestion ?? t("Review exact constraints or keep the current direction."),
        );
      } else {
        showError(
          () => (t("Route reversal failed.")),
          t("A browser error interrupted reversal; no raw traceback is displayed."),
          "browser_reverse_error",
          t("The selected source route remains displayed."),
          t("Keep the current direction or generate another candidate."),
        );
      }
    }
  } finally {
    window.clearInterval(elapsedTimer);
    if (state.request.id === id) {
      state.abortController = null;
      renderStatus();
      renderMapData();
    }
  }
}

function exactWaypointContext(metadata) {
  const name = metadata?.point_name;
  const index = metadata?.point_index;
  const label = name
    ? tr`Exact mandatory waypoint “${name}”`
    : Number.isInteger(index)
      ? tr`Exact mandatory point ${index + 1}`
      : t("An exact mandatory waypoint");
  const indexText = Number.isInteger(index) ? tr` (required-point index ${index})` : "";
  const snap = metadata?.snap_distance_m;
  const maximum = metadata?.maximum_snap_distance_m;
  const distanceText = typeof snap === "number" && typeof maximum === "number"
    ? tr` snapped ${snap.toFixed(1)} m away; the permitted threshold is ${maximum.toFixed(1)} m.`
    : t(" could not be reached within the permitted snap threshold.");
  return `${label}${indexText}${distanceText}`;
}

function safeGenerationDiagnostics(result) {
  const diagnostics = result?.search_diagnostics;
  return JSON.stringify({
    code: "no_route_candidate",
    kind: result?.kind ?? null,
    topology: result?.topology ?? null,
    routing_profile: result?.routing_profile ?? null,
    candidate_count: result?.candidates?.length ?? 0,
    budget: diagnostics ? {
      total_used: diagnostics.budget.total_used,
      total_limit: diagnostics.budget.total_limit,
    } : null,
    cache: diagnostics ? {
      hit_count: diagnostics.cache.hit_count,
      miss_count: diagnostics.cache.miss_count,
      backend_call_count: diagnostics.cache.backend_call_count,
    } : null,
  }, null, 2);
}

function showNoCandidateError(result) {
  const localFailure = result.search_diagnostics.details.local_planning?.failure_code;
  if (localFailure) {
    const error = new LocalPlannerError(localFailure);
    const attempt = result.search_diagnostics.details.local_planning.rejected_attempts?.find((item) => item.code === localFailure);
    const details = attempt?.details;
    const source = state.generationSourceRequest;
    const pointName = details?.waypoint_id
      ? (source?.waypoints ?? source?.hard_waypoints ?? []).find((point) => point.id === details.waypoint_id)?.name ?? t("Exact waypoint")
      : details?.position === 0 ? source?.start?.name || t("Start") : source?.end?.name || t("End");
    const measured = Number.isFinite(details?.snap_distance_m) && Number.isFinite(details?.maximum_snap_distance_m)
      ? tr`${pointName} snapped ${details.snap_distance_m.toFixed(1)} m away; the permitted limit is ${details.maximum_snap_distance_m.toFixed(0)} m. `
      : "";
    if (localFailure === "endpoint_review_required") { hideError(); appShell?.show("map"); return; }
    showError(() => (error.message), safeGenerationDiagnostics(result), error.code,
      tr`${measured}Your requested points and settings are unchanged.`, t("Review the points, activity and installed region before trying again."));
    return;
  }
  showError(
    () => (t("No matching route found.")),
    safeGenerationDiagnostics(result),
    "no_route_candidate",
    t("Your points and constraints have been kept."),
    t("Try changing the distance or your points in Plan."),
  );
}

function handleGenerationError(error) {
  if (error instanceof LocalPlannerError) {
    showError(() => (error.message), "", error.code, t("Your requested points and settings are unchanged."),
      t("Review the request and installed regional data before trying again."));
    return;
  }
  if (error instanceof ApiError) {
    const context = error.code === "exact_waypoint_not_reached"
      ? exactWaypointContext(error.metadata)
      : t("The planning request was not completed.");
    lastExactFailure = error.code === "exact_waypoint_not_reached" ? error.metadata : null;
    showError(
      () => (error.code === "exact_waypoint_not_reached" ? error.message : t("Route planning couldn’t finish.")),
      `${error.message}\n${error.details}`,
      error.code,
      context,
      error.metadata?.suggestion ?? (error.code === "exact_waypoint_not_reached"
        ? GENERATION_SUGGESTION : t("Check your points and routing availability in Plan, then try again.")),
    );
    return;
  }
  showError(
    () => (t("Route generation failed.")),
    t("A browser error interrupted generation; no raw traceback is displayed."),
    "browser_generation_error",
    t("Your points and preferences are kept."),
    t("Return to Plan and try again."),
  );
}

function handleError(error, fallback) {
  if (error instanceof ApiError) showError(() => (error.message), `${error.code}\n${error.details}`);
  else showError(() => (fallback), t("A browser error interrupted this action; no raw traceback is displayed."));
}

function normalizeImportedRequest(value, { requireKnownProfile = true } = {}) {
  if (!value || typeof value !== "object") {
    throw new Error(t("Request JSON must contain an object."));
  }
  if (
    value.schema_version !== 1
    || !["auto_tour", "waypoint_route"].includes(value.kind)
  ) {
    throw new Error(
      "Unsupported legacy Sugarglider request.\nConvert it with scripts/migrate_plan_json.py.",
    );
  }
  const commonKeys = new Set([
    "schema_version", "kind", "name", "topology", "start", "end",
    "routing_profile", "candidate_count", "seed", "distance_objective",
    "preferences", "endpoint_snap_policy",
  ]);
  const modeKeys = value.kind === "auto_tour"
    ? ["hard_waypoints", "requested_stops", "preferred_discovered_poi_ids", "free_poi_spur_physical_m"]
    : ["waypoints", "waypoint_order"];
  const unknownKeys = Object.keys(value).filter(
    (key) => !commonKeys.has(key) && !modeKeys.includes(key),
  );
  if (unknownKeys.length) {
    throw new Error(tr`Canonical request contains unknown fields: ${unknownKeys.join(", ")}.`);
  }
  if (!["loop", "point_to_point"].includes(value.topology)) {
    throw new Error(t("Canonical request topology must be loop or point_to_point."));
  }
  const profileStatus = state.routingProfileCatalog?.profiles.find(
    (status) => status.profile.id === value.routing_profile,
  );
  if (requireKnownProfile && !profileStatus) {
    throw new Error(t("Canonical request contains an unknown routing profile."));
  }
  if (!value.start || (value.topology === "point_to_point" && !value.end)) {
    throw new Error(t("Canonical request endpoints are incomplete."));
  }
  if (value.topology === "loop" && value.end != null) {
    throw new Error(t("A loop request must not contain an end."));
  }
  const objective = value.distance_objective;
  const preferences = value.preferences;
  if (!objective || !preferences) {
    throw new Error(t("Canonical distance_objective and preferences are required."));
  }
  const normalize = (point, label) => {
    const lat = Number(point?.lat);
    const lon = Number(point?.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      throw new Error(tr`${label} has invalid coordinates.`);
    }
    return { ...point, name: point.name || label, lat, lon };
  };
  const start = normalize(value.start, t("Start"));
  const end = value.end == null ? null : normalize(value.end, t("End"));
  restoreEndpointSnapIntent(value, start, end);
  const autoTour = value.kind === "auto_tour";
  const strength = (raw, fallback) => {
    const resolved = raw ?? fallback;
    if (!["exact", "approach", "best_effort"].includes(resolved)) {
      throw new Error(tr`Unknown constraint strength: ${resolved}.`);
    }
    return resolved;
  };
  const hardPoints = autoTour
    ? (value.hard_waypoints ?? []).map((point, index) => ({
      ...normalize(point.coordinate, point.name || tr`Hard waypoint ${index + 1}`),
      id: point.id,
      constraintStrength: "exact",
    }))
    : [];
  const points = autoTour
    ? [start, ...hardPoints]
    : (value.waypoints ?? []).map((point, index) => ({
      ...normalize(point.coordinate, point.name || tr`Waypoint ${index + 1}`),
      id: point.id,
      constraintStrength: strength(point.constraint_strength, "exact"),
      accessSearchRadiusM: point.access_search_radius_m ?? 500,
      maximumBestEffortDistanceM: point.maximum_best_effort_distance_m,
      approachOverride: point.approach_override == null
        ? null
        : normalize(point.approach_override, tr`Approach override ${index + 1}`),
    }));
  const requestedPlaces = autoTour
    ? (value.requested_stops ?? []).map((stop, index) => ({
      id: stop.id,
      name: stop.name,
      coordinate: normalize(stop.semantic_coordinate, tr`Requested stop ${index + 1}`),
      accessSearchRadiusM: stop.access_search_radius_m,
      constraintStrength: strength(stop.constraint_strength, "approach"),
      maximumBestEffortDistanceM: stop.maximum_best_effort_distance_m,
      importance: stop.importance,
      osmReference: stop.osm_reference,
      approachOverride: stop.approach_override == null
        ? null
        : normalize(stop.approach_override, tr`Approach override ${index + 1}`),
    }))
    : [];
  return {
    points,
    start,
    end,
    hardPoints,
    requestedPlaces,
    autoTourStart: autoTour ? start : null,
    importDiagnostics: {
      supplied_location_count: points.length + requestedPlaces.length + Number(Boolean(end)),
      imported_requested_place_count: requestedPlaces.length,
      consumed_as_start_count: 1,
      consumed_as_end_count: Number(Boolean(end)),
      discarded_count: 0,
    },
    maximumDistanceKm: objective.maximum_m == null ? null : objective.maximum_m / 1000,
    routeTopology: value.topology,
    options: {
      name: value.name,
      targetDistanceKm: objective.target_m / 1000,
      toleranceKm: objective.tolerance_m / 1000,
      maximumDistanceKm: objective.maximum_m == null ? null : objective.maximum_m / 1000,
      distancePriority: objective.priority,
      candidateCount: value.candidate_count,
      seed: value.seed,
      waypointOrder: value.kind === "waypoint_route" ? value.waypoint_order : "fixed",
      pathSelectionMode: preferences.path_selection,
      naturePreference: preferences.nature,
      loopGeometryPreference: preferences.loop_geometry,
      freePoiSpurRepeatedM: value.free_poi_spur_physical_m ?? 200,
    },
    canonical: value,
  };
}

function applyCanonicalRequestState(value, options = {}) {
  const imported = normalizeImportedRequest(value, options);
  clearPointPlacement();
  state.selectedEndpointKind = null;
  state.planningMode = imported.canonical.kind;
  state.planningStrategy = imported.canonical.kind;
  clearPointUndo();
  state.routingProfile = imported.canonical.routing_profile;
  document.querySelectorAll('input[name="planning-mode"]').forEach((input) => {
    input.checked = input.value === state.planningMode;
  });
  state.options = imported.options;
  if (state.planningMode === "auto_tour") {
    state.autoTour.start = imported.autoTourStart;
    state.autoTour.end = imported.end;
    state.autoTour.hardPoints = imported.hardPoints;
    state.autoTour.requestedPlaces = imported.requestedPlaces;
    state.importDiagnostics = imported.importDiagnostics;
    state.autoTour.maximumDistanceKm = imported.maximumDistanceKm;
    state.autoTour.routeTopology = imported.routeTopology;
    state.autoTour.preferredPoiIds = [
      ...(imported.canonical.preferred_discovered_poi_ids ?? []),
    ];
    state.autoTour.distancePriority = imported.canonical.distance_objective.priority;
    state.autoTour.directionPreference = imported.canonical.preferences.direction;
    state.autoTour.scenicPreference = imported.canonical.preferences.scenic;
    state.autoTour.drinkingWaterPreference = imported.canonical.preferences.drinking_water;
    state.autoTourOptions = { ...imported.options };
    state.points = [state.autoTour.start, ...state.autoTour.hardPoints].filter(Boolean);
  } else {
    state.points = imported.points;
    state.waypointPoints = [...imported.points];
    state.waypointEndpoints.start = imported.start;
    state.waypointEndpoints.end = imported.end;
    state.waypointEndpoints.routeTopology = imported.routeTopology;
  }
  state.selectedPointIndex = state.points.length ? 0 : null;
  state.selectedRequestedPlaceId = null;
  state.pendingRequestedPlacePopupId = null;
  state.pendingPointPopupIndex = null;
  state.plan = {
    schema_version: 1,
    kind: imported.canonical.kind,
    common: null,
    auto_tour: null,
    waypoint_route: null,
  };
  updateControlsFromOptions();
  return imported;
}
async function importRequest(file) {
  if (isSavedRouteSnapshotDisplay()) return;
  try {
    const imported = applyCanonicalRequestState(JSON.parse(await file.text()));
    invalidateAndRender();
    setEditableRequestStatus(() => (state.planningMode === "auto_tour"
      ? tr`${file.name} loaded. ${state.importDiagnostics.supplied_location_count} supplied locations: ${state.importDiagnostics.consumed_as_start_count} START, ${state.importDiagnostics.consumed_as_end_count} END, ${state.autoTour.requestedPlaces.length} requested places; ${state.importDiagnostics.discarded_count} discarded.`
      : tr`${file.name} loaded. All ${state.points.length} named waypoint constraints and strengths are ready for review.`));
    appShell?.show("plan");
    fitCoordinates([
      ...imported.points,
      ...imported.hardPoints,
      imported.start,
      imported.end,
      ...imported.requestedPlaces.map((place) => place.coordinate),
    ].filter(Boolean).map((point) => [point.lon, point.lat]));
  } catch (error) {
    showError(() => (t("Could not import request JSON.")), error.message);
  }
}

async function importGpx(file) {
  if (isSavedRouteSnapshotDisplay()) return;
  try {
    state.importedGpx = parseGpx(await file.text(), file.name);
    render();
    appShell?.show("map");
    fitCoordinates(state.importedGpx.segments.flat());
  } catch (error) {
    showError(() => (t("Could not import GPX.")), error.message);
  }
}

async function downloadSelected() {
  const candidate = selectedCandidate();
  if (!candidate || pendingGpxExport || ["running", "reversing"].includes(state.request.status)) return;
  const operation = {};
  pendingGpxExport = operation;
  renderMetrics();
  setLocalizedText(byId("export-status"), () => tr`Preparing Route ${candidate.rank} as GPX…`);
  try {
    const prepared = await localGpxExporter.exportCandidate(candidate);
    setLocalizedText(byId("export-status"), () => t("Choose where to save the GPX file…"));
    const result = await gpxFileSaver.save(prepared);
    if (result.status === "cancelled") {
      setLocalizedText(byId("export-status"), () => t("GPX save cancelled. Your route is unchanged."));
      return;
    }
    if (result.status === "saved") {
      setLocalizedText(byId("export-status"), () => tr`Route ${candidate.rank} GPX saved.`);
      return;
    }
    const { blob, filename } = result;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
    setLocalizedText(byId("export-status"), () => tr`${filename} prepared from the selected route.`);
  } catch (error) {
    if (error.name !== "AbortError") {
      setLocalizedText(byId("export-status"), () => t("Could not export GPX. Try again."));
      handleError(error, t("GPX export failed."));
    }
  } finally {
    if (pendingGpxExport === operation) pendingGpxExport = null;
    renderMetrics();
  }
}

function renderSavedRoutePanel() {
  const saved = state.savedRouteReceipt ?? state.savedRouteSnapshot;
  const panel = byId("saved-route-panel");
  panel.classList.toggle("hidden", !saved);
  renderOutingCreationAction(state);
  if (!saved) return;
  const url = savedRouteShareUrl(saved);
  byId("saved-route-link").value = url;
  setLocalizedText(byId("saved-route-message"), () => isSavedRouteSnapshotDisplay()
    ? state.offlineSnapshotKind === "saved_route"
      ? t("Showing your saved offline route. Reconnect to use online actions.")
      : t("This read-only route opens exactly as saved, without planning it again.")
    : state.savedRouteReceipt
      ? t("Your selected route is stored at this unlisted link.")
      : t("Your saved route remains available at this unlisted link."));
  byId("share-saved-route").classList.toggle(
    "hidden",
    typeof navigator.share !== "function",
  );
  byId("use-saved-route").classList.toggle(
    "hidden",
    !isSavedRouteSnapshotDisplay() || serverFeaturesUnavailable(),
  );
  byId("delete-saved-route").classList.toggle(
    "hidden",
    !state.savedRouteReceipt?.owner_token
      || serverFeaturesUnavailable(),
  );
  byId("dismiss-saved-route").classList.toggle(
    "hidden",
    !state.savedRouteReceipt,
  );
}

function serverFeaturesUnavailable() {
  return state.networkStatus === "offline"
    || Boolean(state.offlineSnapshotKind);
}

async function saveSelectedRoute() {
  const candidate = selectedCandidate();
  const sourceRequest = state.generationSourceRequest;
  if (!candidate || !sourceRequest || isSavedRouteSnapshotDisplay()) return;
  try {
    const saved = await createSavedRoute(sourceRequest, candidate);
    state.savedRouteReceipt = {
      slug: saved.slug,
      share_path: saved.share_path,
      gpx_path: saved.gpx_path,
      expires_at: saved.expires_at,
      owner_token: saved.owner_token,
      route_name: candidate.route.name,
    };
    render();
    setLocalizedText(byId("request-status"), () => t("Route saved. Copy or share its unlisted link when ready."));
  } catch (error) {
    handleError(error, t("The selected route could not be saved."));
  }
}

async function copySavedRouteLink() {
  const saved = state.savedRouteReceipt ?? state.savedRouteSnapshot;
  if (!saved) return;
  try {
    await navigator.clipboard.writeText(savedRouteShareUrl(saved));
    setLocalizedText(byId("request-status"), () => t("Saved-route link copied."));
  } catch (error) {
    handleError(error, t("The saved-route link could not be copied."));
  }
}

async function shareCurrentSavedRoute() {
  const saved = state.savedRouteReceipt ?? state.savedRouteSnapshot;
  if (!saved) return;
  try {
    await shareSavedRoute(saved);
    setLocalizedText(byId("request-status"), () => t("Saved-route link shared."));
  } catch (error) {
    if (error.name === "AbortError") {
      setLocalizedText(byId("request-status"), () => t("Sharing cancelled."));
      return;
    }
    handleError(error, t("The saved-route link could not be shared."));
  }
}

async function removeSavedRoute() {
  const saved = state.savedRouteReceipt;
  if (!saved) return;
  if (!window.confirm(t("Permanently delete this saved route and invalidate its unlisted link?"))) return;
  try {
    await deleteSavedRoute(saved.slug, saved.owner_token);
    state.savedRouteReceipt = null;
    render();
    setLocalizedText(byId("request-status"), () => t("Saved route deleted."));
  } catch (error) {
    handleError(error, t("The saved route could not be deleted."));
  }
}

function dismissSavedRouteReceipt() {
  state.savedRouteReceipt = null;
  render();
}

function displaySavedRoute(saved) {
  applyCanonicalRequestState(saved.source_request, { requireKnownProfile: false });
  state.generationSourceRequest = null;
  state.generationResult = null;
  state.selectedSignature = saved.candidate.id;
  state.visualizationCache.clear();
  state.savedRouteSnapshot = saved;
  state.savedRouteSnapshotDisplay = true;
  state.request = { status: "success", id: state.request.id, startedAt: null };
}

async function useSavedRouteAsNewPlan() {
  const snapshot = state.savedRouteSnapshot;
  if (!snapshot || !isSavedRouteSnapshotDisplay()) return;
  try {
    const [catalog, poiStatus] = await Promise.all([
      getRoutingProfiles(),
      state.config.poi_index_available
        ? getPoiStatus()
        : Promise.resolve({ available: false, feature_count: null }),
    ]);
    state.routingProfileCatalog = catalog;
    state.poiIndexStatus = poiStatus;
    applyCanonicalRequestState(snapshot.source_request);
    state.savedRouteSnapshotDisplay = false;
    state.generationResult = null;
    state.generationSourceRequest = snapshot.source_request;
    state.forkedSavedCandidate = snapshot.candidate;
    state.selectedSignature = snapshot.candidate.id;
    renderRoutingProfiles({ preserveUnavailableSelection: true });
    const poiAvailable = Boolean(
      state.config.poi_index_available && state.poiIndexStatus?.available,
    );
    state.config.poi_index_available = poiAvailable;
    byId("places-filters").querySelectorAll("input").forEach((input) => {
      input.disabled = !poiAvailable;
    });
    setLocalizedText(byId("places-status"), () => poiAvailable
      ? tr`Local OSM places index ready · ${formatCount(state.poiIndexStatus.feature_count)} regional features.`
      : t("POI index unavailable. Place discovery is disabled; routing still works."));
    render();
    setEditableRequestStatus(
      () => (t("Saved request copied into a new editable plan. Generate when ready.")),
    );
  } catch (error) {
    handleError(error, t("The saved route could not be prepared as a new plan."));
  }
}

function failedExactPoint() {
  const id = lastExactFailure?.point_id;
  if (state.planningMode === "auto_tour") {
    const index = state.autoTour.hardPoints.findIndex((point) => point.id === id);
    return index < 0 ? null : { collection: state.autoTour.hardPoints, index };
  }
  let index = state.points.findIndex((point) => point.id === id);
  if (index < 0 && Number.isInteger(lastExactFailure?.point_index)) {
    index = lastExactFailure.point_index - 1;
  }
  return index < 0 || index >= state.points.length
    ? null
    : { collection: state.points, index };
}

function updateFailedExactPoint(action) {
  const target = failedExactPoint();
  if (!target) return;
  if (action !== "move") rememberPointEdit("Stop constraint updated");
  clearPointPlacement();
  state.selectedEndpointKind = null;
  const point = target.collection[target.index];
  if (["nearest", "best_effort"].includes(action)) {
    point.constraintStrength = "best_effort";
    point.accessSearchRadiusM = Math.max(point.accessSearchRadiusM ?? 500, 1000);
    point.maximumBestEffortDistanceM = point.accessSearchRadiusM;
  } else if (action === "remove") {
    target.collection.splice(target.index, 1);
  } else if (action === "requested") {
    target.collection.splice(target.index, 1);
    const wasWaypointRoute = state.planningMode === "waypoint_route";
    state.autoTour.requestedPlaces.push({
      id: point.id,
      name: point.name,
      coordinate: { lat: point.lat, lon: point.lon },
      importance: "must_visit",
      constraintStrength: "approach",
      accessSearchRadiusM: 500,
    });
    if (wasWaypointRoute) {
      state.waypointPoints = [...state.points];
      state.autoTour.start = state.waypointEndpoints.start;
      state.autoTour.end = state.waypointEndpoints.end;
      state.autoTour.routeTopology = state.waypointEndpoints.routeTopology;
      state.autoTour.hardPoints = [];
      state.planningMode = "auto_tour";
      state.points = [state.autoTour.start].filter(Boolean);
      document.querySelector('input[name="planning-mode"][value="auto_tour"]').checked = true;
    }
  } else if (action === "move") {
    state.selectedPointIndex = state.planningMode === "auto_tour"
      ? target.index + 1
      : target.index;
    state.movingPointIndex = state.selectedPointIndex;
    state.addPointMode = false;
  }
  if (state.planningMode === "auto_tour") {
    state.points = [state.autoTour.start, ...state.autoTour.hardPoints].filter(Boolean);
  }
  hideError();
  invalidateAndRender();
  setEditableRequestStatus(() => (action === "move"
    ? t("Drag the selected waypoint or place it on the map, then generate again.")
    : t("Constraint updated. Generate again to apply it.")));
  if (action === "move") appShell?.show("map", { focus: true });
}

let itineraryDialog = null;
function bindEvents() {
  initializeAdventure();
  byId("map-zoom-in").addEventListener("click", () => zoomMap(1));
  byId("map-zoom-out").addEventListener("click", () => zoomMap(-1));
  byId("map-reset-north").addEventListener("click", resetMapNorth);
  byId("map-fit-points").addEventListener("click", () => byId("fit-points").click());
  byId("redo-point-edit").addEventListener("click", () => {
    if (redoPointEdit()) { updateControlsFromOptions(); invalidateAndRender(); }
  });
  byId("dock-finish").addEventListener("change", () => {
    try { changeMapTopology(byId("dock-finish").value, localPlanner ? "near" : undefined); updateControlsFromOptions(); invalidateAndRender(); }
    catch (error) { render(); showError(() => (error.message)); }
  });
  byId("dock-order").addEventListener("change", () => {
    rememberPointEdit("Visit order changed");
    state.options.waypointOrder = byId("dock-order").value;
    updateControlsFromOptions(); invalidateAndRender();
  });
  const dockPanel = byId("route-dock").closest(".map-panel");
  const measureDock = () => {
    const dock = byId("route-dock");
    dockPanel.style.setProperty("--route-dock-height", `${dock.getBoundingClientRect().height}px`);
    const attribution = dockPanel.querySelector(".maplibregl-ctrl-attrib");
    if (attribution) dockObserver.observe(attribution);
    const credits = attribution?.getBoundingClientRect();
    const canvas = byId("map").getBoundingClientRect();
    const compact = attribution?.classList.contains("maplibregl-compact") && !attribution.classList.contains("maplibregl-compact-show");
    dockPanel.dataset.dockLayout = matchMedia("(max-width: 840px)").matches && dock.dataset.expanded === "false" && compact ? "compact" : "stacked";
    dockPanel.style.setProperty("--map-credit-width", `${credits?.width ?? 44}px`);
    dockPanel.style.setProperty("--route-attribution-clearance", `${Math.max(8, credits ? canvas.bottom - credits.top + 8 : 8)}px`);
  };
  const dockObserver = new ResizeObserver(measureDock);
  dockObserver.observe(byId("route-dock")); dockObserver.observe(dockPanel);
  byId("route-dock").addEventListener("route-dock-layout", measureDock);
  new MutationObserver(measureDock).observe(dockPanel, { childList: true, subtree: true });
  byId("cancel-point-placement").addEventListener("click", () => { clearPointPlacement(); render(); appShell?.show("map"); });
  byId("dismiss-error").addEventListener("click", hideError);
  byId("error-use-nearest").addEventListener("click", () => updateFailedExactPoint("nearest"));
  byId("error-best-effort").addEventListener("click", () => updateFailedExactPoint("best_effort"));
  byId("error-requested-place").addEventListener("click", () => updateFailedExactPoint("requested"));
  byId("error-move-waypoint").addEventListener("click", () => updateFailedExactPoint("move"));
  byId("error-remove-waypoint").addEventListener("click", () => updateFailedExactPoint("remove"));
  byId("generate").addEventListener("click", generate);
  byId("generate-top").addEventListener("click", generate);
  byId("generate-map").addEventListener("click", generate);
  byId("cancel").addEventListener("click", () => { state.abortController?.abort(); adventureDialog?.cancel(); });
  byId("clear-results").addEventListener("click", () => invalidateAndRender());
  for (const id of ["undo-point-edit", "undo-point-edit-plan"]) {
    byId(id).addEventListener("click", () => {
      if (undoPointEdit()) { updateControlsFromOptions(); invalidateAndRender(); }
    });
  }
  byId("route-form").addEventListener("change", (event) => {
    if (event.target.name === "planning-mode" || event.target.id.startsWith("hard-") || (event.target.closest("#planning-points") && event.target.id !== "point-order-mode")) return;
    rememberPointEdit("Route settings changed");
    try { updateOptionsFromControls(); } catch (error) { updateControlsFromOptions(); render(); showError(() => (error.message)); return; }
    if (event.target.id === "profile" && plannerProfilePreference) {
      void plannerProfilePreference.remember(state.routingProfile).then((persisted) => {
        if (!persisted) reportOptionalStorageFailure();
      });
    }
    invalidateAndRender();
  });
  document.querySelectorAll('input[name="planning-mode"]').forEach((input) => {
    input.addEventListener("change", () => {
      if (!input.checked) return;
      if (input.value === "automatic" && hasDiscoveryIntent()) {
        showError(() => (t("This plan has discovery-specific places.")), t("Keep Suggest a route to preserve them, or remove those choices before using Automatic."));
        renderModeControls(); return;
      }
      rememberPointEdit("Planning choice changed");
      clearPointPlacement();
      updateOptionsFromControls();
      if (input.value === "automatic") {
        state.planningStrategy = "automatic";
        reconcileAutomaticIntent();
      } else {
        state.planningStrategy = input.value;
        switchPlanningMode(input.value);
      }
      updateControlsFromOptions();
      invalidateAndRender();
    });
  });
  for (const kind of ["start", "end"]) {
    byId(`hard-${kind}-snap-policy`).addEventListener("change", event => changeEndpointSnapPolicy(kind, event.target.value));
    for (const suffix of ["enabled", "name", "lat", "lon"]) {
      byId(`hard-${kind}-${suffix}`).addEventListener("change", () => {
        const point = endpointFromControls(kind);
        if (byId(`hard-${kind}-enabled`).checked && !point) return;
        rememberPointEdit(`${kind === "start" ? "Start" : "End"} updated`);
        clearPointPlacement();
        assignActiveEndpoint(kind, point);
        state.selectedEndpointKind = point ? kind : null;
        state.selectedPointIndex = null;
        invalidateAndRender();
      });
    }
    byId(`set-hard-${kind}`).addEventListener("click", () => {
      const active = state.endpointSetMode === kind;
      clearPointPlacement();
      state.endpointSetMode = active ? null : kind;
      state.selectedEndpointKind = kind;
      state.selectedPointIndex = null;
      setLocalizedText(byId(`set-hard-${kind}`), () => state.endpointSetMode === kind
        ? tr`Click map for ${kind}`
        : t("Set on map"));
      renderStatus();
      if (state.endpointSetMode) appShell?.show("map", { focus: true });
    });
    byId(`clear-hard-${kind}`).addEventListener("click", () => {
      rememberPointEdit(`${kind === "start" ? "Start" : "End"} removed`);
      assignActiveEndpoint(kind, null);
      if (state.selectedEndpointKind === kind) state.selectedEndpointKind = null;
      if (state.endpointSetMode === kind) state.endpointSetMode = null;
      invalidateAndRender();
    });
  }
  itineraryDialog = initializeItineraryDialog({
    root: byId("itinerary-dialog"), launcher: byId("import-itinerary"),
    maximumStops: () => state.config?.max_required_points ?? 30,
    capability: (request) => {
      const profile = state.routingProfileCatalog?.profiles.find(status => status.profile.id === request.routing_profile);
      if (!localPlanner) return profile?.available
        ? t("Uses the routing service when you explicitly Generate.")
        : t("This activity is currently unavailable. The itinerary can be imported; generation will report the limitation.");
      const limitations = [];
      try { validateLocalWaypointRouteRequest(request); }
      catch (error) { limitations.push(tr`This itinerary cannot generate on device: ${friendlyLabel(error.code)}.`); }
      if (regionPlanningError) limitations.push(regionFailureMessage(regionPlanningError));
      else if (!localRouteCapabilities?.enabled) limitations.push(t("On-device routing is unavailable in this app build."));
      else if (!localRouteCapabilities.installed_pack_count) limitations.push(t("Download a supported offline region before generating."));
      else if (!profile?.available) limitations.push(t("This activity is unavailable in the installed region."));
      return tr`On-device connections accept up to ${LOCAL_WAYPOINT_MAX_WAYPOINTS} interior stops. Local paths are experimental and differ from server routing. ${limitations.join(" ")} All stops and exact constraints will be preserved.`;
    },
    promptSettings: () => ({ start: activeEndpoints().start, end: activeEndpoints().end,
      topology: activeEndpoints().routeTopology, activity: state.routingProfile,
      target_distance_km: state.options.targetDistanceKm, tolerance_km: state.options.toleranceKm }),
    canImport: () => !isImmutableSnapshotDisplay() && !["running", "reversing"].includes(state.request.status),
    onImport: (request, draft) => {
      const imported = applyCanonicalRequestState(request);
      state.points.forEach((point, index) => {
        if (draft.stops[index].reason) point.itineraryReason = draft.stops[index].reason;
      });
      invalidateAndRender();
      setEditableRequestStatus(() => (t("Itinerary imported. Review the locations on the map, then Generate when ready.")));
      appShell?.show("plan");
      fitCoordinates([imported.start, ...state.points, imported.end].filter(Boolean).map(point => [point.lon, point.lat]));
    },
  });
  byId("request-file").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (file) importRequest(file);
    event.target.value = "";
  });
  byId("gpx-file").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (file) importGpx(file);
    event.target.value = "";
  });
  byId("clear-gpx").addEventListener("click", () => {
    state.importedGpx = null;
    render();
  });
  byId("add-point-mode").addEventListener("click", () => {
    if (state.planningStrategy === "automatic") { clearPointPlacement(); appShell?.show("map", { focus: true }); renderStatus(); return; }
    const active = state.addPointMode;
    clearPointPlacement();
    state.addPointMode = !active;
    byId("add-point-mode").setAttribute("aria-pressed", String(state.addPointMode));
    setLocalizedText(byId("add-point-mode").lastChild, () => state.addPointMode ? t(" Click map once…") : t(" Add on map"));
    if (state.addPointMode) appShell?.show("map", { focus: true });
    renderStatus();
  });
  byId("fit-points").addEventListener("click", () => {
    const requested = state.planningMode === "auto_tour"
      ? state.autoTour.requestedPlaces.map((place) => [place.coordinate.lon, place.coordinate.lat])
      : [];
    const endpoints = activeEndpoints();
    const endpointCoordinates = [endpoints.start, endpoints.end]
      .filter(Boolean)
      .map((point) => [point.lon, point.lat]);
    fitCoordinates([...state.points.map((point) => [point.lon, point.lat]), ...endpointCoordinates, ...requested]);
  });
  byId("clear-points").addEventListener("click", () => {
    if (state.points.length > 1 && !window.confirm(t("Remove all mandatory points and generated results?"))) return;
    rememberPointEdit("Route points cleared");
    clearPointPlacement();
    state.points = [];
    if (state.planningMode === "auto_tour") {
      state.autoTour.start = null;
      state.autoTour.end = null;
      state.autoTour.requestedPlaces = [];
      state.selectedRequestedPlaceId = null;
      state.pendingRequestedPlacePopupId = null;
    } else {
      state.waypointEndpoints.start = null;
      state.waypointEndpoints.end = null;
    }
    state.selectedEndpointKind = null;
    state.selectedPointIndex = null;
    state.pendingPointPopupIndex = null;
    invalidateAndRender();
  });
  byId("show-all").addEventListener("change", (event) => {
    state.showAllCandidates = event.target.checked;
    renderMapData();
  });
  byId("show-nature").addEventListener("change", (event) => {
    state.showNatureContext = event.target.checked;
    renderMapData();
  });
  byId("show-direction").addEventListener("change", (event) => {
    state.showDirectionArrows = event.target.checked;
    renderMapData();
  });
  byId("show-dropped-requested-radii").addEventListener("change", (event) => {
    state.showDroppedRequestedRadii = event.target.checked;
    renderMapData();
  });
  byId("places-filters").addEventListener("change", () => {
    selectPoi(null);
    updatePoiFiltersFromControls();
    schedulePoiRefresh();
  });
  byId("results-back-to-plan").addEventListener("click", () => appShell?.show("plan", { focus: true }));
  byId("download-gpx").addEventListener("click", downloadSelected);
  byId("save-route").addEventListener("click", saveSelectedRoute);
  byId("save-route-selected").addEventListener("click", saveSelectedRoute);
  byId("copy-saved-route-link").addEventListener("click", copySavedRouteLink);
  byId("share-saved-route").addEventListener("click", shareCurrentSavedRoute);
  byId("use-saved-route").addEventListener("click", useSavedRouteAsNewPlan);
  byId("delete-saved-route").addEventListener("click", removeSavedRoute);
  byId("dismiss-saved-route").addEventListener("click", dismissSavedRouteReceipt);
  bindOutingController({
    handleError,
    showError,
    setStatus: (message) => {
      byId("request-status").textContent = message;
    },
    renderMetrics,
  });
  byId("reverse-route").addEventListener("click", reverseSelectedRoute);
  byId("export-plan").addEventListener("click", () => {
    try {
      if (!state.adventureDisplay) updateOptionsFromControls();
      const request = state.adventureDisplay ? state.generationSourceRequest : currentPlanRequest();
      const blob = new Blob([`${JSON.stringify(request, null, 2)}\n`], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "sugarglider-plan.json";
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      setLocalizedText(byId("request-status"), () => t("Canonical plan JSON exported."));
    } catch (error) {
      showError(() => (t("Could not export plan JSON.")), error.message);
    }
  });
  byId("copy-request").addEventListener("click", async () => {
    try {
      if (!state.adventureDisplay) { updateOptionsFromControls(); saveActivePoints(); }
      const request = state.adventureDisplay ? state.generationSourceRequest : currentPlanRequest();
      await navigator.clipboard.writeText(JSON.stringify(request, null, 2));
      setLocalizedText(byId("request-status"), () => state.planningMode === "auto_tour"
        ? t("Suggested-route plan copied with places, distance settings and preferences.")
        : t("Request JSON copied with every required-point name."));
    } catch (error) {
      showError(() => (t("Could not copy request JSON.")), error.message);
    }
  });
  window.addEventListener("resize", resizeMap);
}

async function loadSavedRoutePage(slug) {
  const epoch = ++savedRoutePageEpoch;
  try {
    const loaded = await resolveNetworkResource({
      loadResource: () => getSavedRoute(slug),
      loadConfig: () => getConfig(),
      loadStoredConfig: restorePublicConfig,
      fallbackConfig: (snapshot) => onlineFallbackConfig(snapshot),
    });
    if (epoch !== savedRoutePageEpoch) return null;
    state.config = loaded.config;
    clearOfflineSnapshotStatus();
    void persistSavedRouteNetworkData(
      loaded,
      () => epoch === savedRoutePageEpoch,
    );
    return loaded.resource;
  } catch (error) {
    if (epoch !== savedRoutePageEpoch) return null;
    if (error?.code === "saved_route_not_found") {
      await Promise.allSettled([
        removeOfflineSnapshot("saved_route", slug),
      ]);
      if (epoch !== savedRoutePageEpoch) return null;
      throw error;
    }
    if (!transportFailure(error)) throw error;
    const [recordResult, configResult] = await Promise.allSettled([
      loadOfflineSnapshot("saved_route", slug),
      restorePublicConfig(),
    ]);
    if (epoch !== savedRoutePageEpoch) return null;
    const record = recordResult.status === "fulfilled"
      ? recordResult.value
      : null;
    if (!record) throw error;
    const storedConfig = configResult.status === "fulfilled"
      ? configResult.value
      : null;
    state.config = offlineMapConfig(storedConfig, record.payload);
    markOfflineSnapshot("saved_route", slug);
    return record.payload;
  }
}

async function retrySavedRouteConnection() {
  const slug = state.savedRouteSnapshot?.slug;
  if (!slug) return false;
  if (savedRouteReconnectOperation) {
    return savedRouteReconnectOperation.promise;
  }
  const epoch = savedRoutePageEpoch;
  const identity = Object.freeze({ epoch, slug });
  const operation = { identity, promise: null };
  savedRouteReconnectOperation = operation;
  operation.promise = (async () => {
    try {
      const wasOfflineSnapshot = state.offlineSnapshotKind === "saved_route";
      const loaded = await resolveNetworkResource({
        loadResource: () => getSavedRoute(slug),
        loadConfig: () => getConfig(),
        loadStoredConfig: restorePublicConfig,
        fallbackConfig: (snapshot) => onlineFallbackConfig(snapshot),
      });
      if (!currentSavedRouteReconnect(operation)) return false;
      const snapshot = loaded.resource;
      state.config = loaded.config;
      clearOfflineSnapshotStatus();
      displaySavedRoute(snapshot);
      renderSnapshotProfileIdentity(snapshot.candidate.routing_profile);
      if (wasOfflineSnapshot) {
        mapReady = false;
        initializeMap(state.config, {
          onReady: () => {
            mapReady = true;
            renderMapData();
            fitCoordinates(snapshot.candidate.route.geometry);
          },
          onError: showMapError,
          onViewportChange: () => {},
          onMapClick: () => {},
        });
      }
      render();
      if (wasOfflineSnapshot) await selectCandidate(snapshot.candidate.id);
      if (!currentSavedRouteReconnect(operation)) return false;
      await persistSavedRouteNetworkData(
        loaded,
        () => currentSavedRouteReconnect(operation),
      );
      if (!currentSavedRouteReconnect(operation)) return false;
      setLocalizedText(byId("request-status"), () => t("Saved route reconnected from its fresh immutable server snapshot."));
      return true;
    } catch (error) {
      if (!currentSavedRouteReconnect(operation)) return false;
      if (error?.code === "saved_route_not_found") {
        const cleanup = await settleOptionalPersistence([
          () => removeOfflineSnapshot("saved_route", slug),
        ]);
        if (!currentSavedRouteReconnect(operation)) return false;
        clearUnavailableSavedRouteState(state, slug);
        clearRoutes();
        render();
        if (cleanup.failed) reportOptionalStorageFailure();
        handleError(error, t("The saved route no longer exists."));
      } else if (transportFailure(error)) {
        setPwaNetworkStatus("offline");
      } else {
        setPwaNetworkStatus("online");
        handleError(error, t("The saved route could not be refreshed."));
      }
      return false;
    } finally {
      if (savedRouteReconnectOperation === operation) {
        savedRouteReconnectOperation = null;
      }
    }
  })();
  return operation.promise;
}

function currentSavedRouteReconnect(operation) {
  return savedRouteReconnectOperation === operation
    && operation.identity.epoch === savedRoutePageEpoch
    && state.savedRouteSnapshot?.slug === operation.identity.slug;
}

function onlineFallbackConfig(snapshot) {
  return { ...offlineMapConfig(null, snapshot), offline_mode: false };
}

async function persistSavedRouteNetworkData(loaded, isCurrent) {
  const actions = [
    () => refreshOfflineSnapshot("saved_route", loaded.resource),
  ];
  if (loaded.configFromNetwork) {
    actions.push(() => storePublicConfig(loaded.config));
  }
  const persisted = await settleOptionalPersistence(actions);
  if (!isCurrent()) return;
  if (persisted.results[0].status === "fulfilled") {
    applyOfflineCopyRefresh(persisted.results[0].value);
  }
  if (persisted.failed) reportOptionalStorageFailure();
}

async function retryCurrentConnection() {
  if (state.outingDisplay) return retryCurrentOutingConnection();
  if (state.savedRouteSnapshotDisplay) return retrySavedRouteConnection();
  if (isBundledAndroidApp()) { window.location.reload(); return true; }
  try {
    const [config, catalog] = await Promise.all([
      getConfig(),
      getRoutingProfiles(),
    ]);
    state.config = config;
    state.routingProfileCatalog = catalog;
    clearOfflineSnapshotStatus();
    const persisted = await settleOptionalPersistence([
      () => storePublicConfig(config),
    ]);
    if (persisted.failed) reportOptionalStorageFailure();
    window.location.reload();
    return true;
  } catch (error) {
    if (transportFailure(error)) setPwaNetworkStatus("offline");
    else {
      setPwaNetworkStatus("online");
      handleError(error, t("The application could not be refreshed."));
    }
    return false;
  }
}

async function initializeRegionScreen() {
  const product = createRegionProduct({ versions: regionVersions, native: nativeRegions,
    installerClient: createRegionInstallerClient() });
  regionScreen = createRegionScreen({ versions: regionVersions, product, withRegion: withPlanningRegion,
    selectedRegionId: () => selectedRegionId,
    selectRegion: (id, { remember = true } = {}) => {
      if (remember) void regionPreference?.remember(id);
      if (selectedRegionId === id) return;
      adventureDialog?.clear();
      if (state.adventureDisplay) returnToManualPlan({ refresh: false });
      // Clearing/removing a region must release its worker heap too, even when
      // no replacement region will be loaded. Old sessions reject after close.
      sharedLocalRegionClient?.close();
      sharedLocalRegionClient = null;
      selectedRegionId = id;
      state.poiAbortController?.abort();
      state.poiRequest = { status: "idle", id: state.poiRequest.id + 1 };
      clearPoiFeatures(t("Checking places in the selected region…"));
      if (mapReady && !isImmutableSnapshotDisplay()) invalidateAndRender();
    },
    isPlanning: () => state.request.status === "running",
    viewRegion: ([west, south, east, north]) => fitCoordinates([[west, south], [east, north]]),
    onReady: (capabilities, code, reference) => {
      selectedRouteElevation?.regionChanged(reference);
      if(code && code!=="regional_checking")selectedRouteElevation?.invalidate();
      localRouteCapabilities = capabilities; regionPlanningError = code;
      if (state.config) {
        const available = Boolean(capabilities && !code);
        state.config.poi_index_available = available;
        state.poiIndexStatus = { available, feature_count: null };
        byId("places-filters").querySelectorAll("input").forEach((input) => { input.disabled = !available; });
        if (available && mapReady) schedulePoiRefresh();
        if (!available) {
          state.poiAbortController?.abort();
          state.poiRequest = { status: "idle", id: state.poiRequest.id + 1 };
          clearPoiFeatures(t("Choose a ready installed region to browse places."));
        }
      }
      if (mapReady && !isImmutableSnapshotDisplay()) { renderRoutingProfiles({ preserveUnavailableSelection: true }); render(); }
    },
    onMapChange: async () => { if (offlineMaps) regionScreen.mapState(await offlineMaps.refresh({ reopen: true })); },
    elements: { container: byId("offline-regions"), selector: byId("planning-region"), list: byId("regional-list"),
      status: byId("regional-status"), mapStatus: byId("regional-map-status"), cancel: byId("regional-cancel"), refresh: byId("regional-refresh"),
      progress: byId("regional-progress"), diagnostics: byId("regional-diagnostics"), diagnosticCode: byId("regional-error-code") },
  });
  await regionScreen.initialize();
}

async function start() {
  await initializeLocalization(document);
  onLanguageChange(() => {
    if (state.config) render();
  });
  initializeSourceInformation(document);
  appShell = initializeAppShell({ resizeMap: ({ layoutChanged, view }) => {
    resizeMap();
    if (!layoutChanged || view !== "plan" || isImmutableSnapshotDisplay()
      || ["running", "reversing"].includes(state.request.status)) return;
    const endpoints = activeEndpoints();
    const point = state.endpointSetMode === "end" ? endpoints.end
      : state.endpointSetMode === "start" ? endpoints.start
      : state.selectedEndpointKind ? endpoints[state.selectedEndpointKind] : state.points[state.selectedPointIndex] ?? endpoints.start;
    if (point) keepCoordinateVisible([point.lon, point.lat]);
  } });
  byId("plan-regions").addEventListener("click", () => {
    byId("offline-regions").open = true;
    document.querySelector(".header-tools").open = true;
    byId("planning-region").focus();
  });
  decorateIcons();
  try {
    await initializePwaRuntime({
      render: renderPwaApplication,
      onStorageCleared: () => {
        adventureRestoreEpoch++; forgottenAdventureOutput = state.adventureResult;
        byId("restore-adventure").hidden = true;
        setLocalizedText(byId("adventure-storage-status"), () => t("Saved offline data cleared. The displayed route remains open."));
      },
      retry: retryCurrentConnection,
      rememberParticipant: rememberCurrentOutingParticipant,
      forgetParticipant: forgetCurrentOutingParticipant,
      isMutationPending: outingMutationIsPending,
      ownsOutboxPresence: outingOutboxPresenceIsCurrent,
    });
    const currentOutingSlug = outingSlug();
    const currentSharedRouteSlug = sharedRouteSlug();
    const prepareRegion = async () => {
      if (!localPlanner || currentSharedRouteSlug || regionScreen) return;
      try { await initializeRegionScreen(); }
      catch (error) { handleError(error, t("The selected region could not be prepared.")); }
    };

    if (localPlanner) {
      const { store, adventures } = await pwaRuntime();
      adventureSnapshots = adventures;
      regionPreference = createRegionPreference(store);
      // Restore before initializeOfflineMaps performs its first regional scan.
      selectedRegionId = await regionPreference.restore(regionVersions);
      if (!currentOutingSlug && !currentSharedRouteSlug) {
        plannerProfilePreference = createPlannerProfilePreference(store);
        state.routingProfile = await plannerProfilePreference.restore();
      }
    }
    await initializeTrailProfile({
      requireSetup: !currentOutingSlug && !currentSharedRouteSlug,
    });
    try {
      if (localPlanner) byId("offline-maps").classList.add("hidden");
      offlineMaps = await initializeOfflineMaps({
        ...(localPlanner ? { store: regionalMaps,
          onStatus: (snapshot) => {
            regionScreen?.mapState(snapshot);
            // The opened basemap no longer needs the version lease. Start the
            // independent planning checks while tiles and icons are rendering.
            if (snapshot.status.state === "local_pack_active") void prepareRegion();
          } } : {}),
        elements: localPlanner ? {} : {
          container: byId("offline-maps"),
          support: byId("offline-map-storage-support"),
          status: byId("offline-map-pack-status"),
          active: byId("offline-map-active"),
          list: byId("offline-map-pack-list"),
          form: byId("offline-map-install-form"),
          urlInput: byId("offline-map-manifest-url"),
          installButton: byId("offline-map-install"),
          cancelButton: byId("offline-map-cancel-install"),
        },
      });
    } catch {
      setLocalizedText(byId("offline-map-storage-support"), () => t("OPFS random-access storage unavailable."));
      const mapPackStatus = byId("offline-map-pack-status");
      mapPackStatus.dataset.state = "map_pack_storage_unavailable";
      setLocalizedText(mapPackStatus, () => t("Offline map storage is unavailable in this browser."));
    }
    if (currentOutingSlug) {
      await startOutingPage(currentOutingSlug, {
        handleError,
        showError,
        showMapError,
        setStatus: (message) => {
          byId("request-status").textContent = message;
        },
        renderMetrics,
        onMapReady: () => {
          mapReady = true;
        },
      });
      return;
    }
    // Public native identities are known before asynchronous regional checks.
    // Their availability stays false until the selected engine is verified.
    if (localPlanner) renderRoutingProfiles();
    bindEvents();
    const sharedSlug = currentSharedRouteSlug;
    let sharedSnapshot = null;
    if (sharedSlug) {
      sharedSnapshot = await loadSavedRoutePage(sharedSlug);
    } else {
      try {
        [state.config, state.routingProfileCatalog] = await Promise.all([
          getConfig(),
          localPlanner ? Promise.resolve(state.routingProfileCatalog) : getRoutingProfiles(),
        ]);
        if (isBundledAndroidApp()) state.config = { ...state.config, offline_mode: true };
        clearOfflineSnapshotStatus();
        const persisted = await settleOptionalPersistence([
          () => storePublicConfig(state.config),
        ]);
        if (persisted.failed) reportOptionalStorageFailure();
      } catch (error) {
        if (!transportFailure(error)) throw error;
        const storedConfig = await readOptionalStorage(
          restorePublicConfig,
          { onFailure: reportOptionalStorageFailure },
        );
        state.config = offlineMapConfig(storedConfig, null);
        if (!localPlanner) state.routingProfileCatalog = { profiles: [] };
        state.poiIndexStatus = { available: false, feature_count: null };
        setPwaNetworkStatus("offline");
      }
    }
    if (sharedSnapshot) {
      state.poiIndexStatus = { available: false, feature_count: null };
      displaySavedRoute(sharedSnapshot);
      renderSnapshotProfileIdentity(sharedSnapshot.candidate.routing_profile);
    } else {
      if (localPlanner) {
        // Basemap attachment starts checking the selected region. Planning
        // remains unavailable until every required component has passed.
      }
      renderRoutingProfiles();
      try {
        if (!localPlanner) {
          if (state.networkStatus === "offline") throw new TypeError();
          state.poiIndexStatus = await getPoiStatus();
        }
      } catch {
        state.poiIndexStatus = { available: false, feature_count: null };
      }
    }
    const natureAvailable = Boolean(localPlanner || state.config.nature_index_available);
    const preferOption = byId("nature-preference").querySelector('option[value="prefer"]');
    preferOption.disabled = !natureAvailable;
    if (!natureAvailable && !sharedSnapshot) state.options.naturePreference = "off";
    updateControlsFromOptions();
    setLocalizedText(byId("nature-availability"), () => localPlanner
      ? t("Suggested routes use installed regional nature data. Missing data and uncovered sections remain unknown.")
      : natureAvailable
      ? tr`Local OSM nature index available. Water proximity uses ${state.config.nature_water_buffer_m} m.`
      : t("Local OSM nature index unavailable. Prefer mapped nature is disabled; routing still works."));
    byId("show-nature").disabled = !natureAvailable || Boolean(localPlanner);
    byId("show-nature").title = localPlanner ? t("Local nature totals appear in route details; map coloring is unavailable.") : "";
    state.showNatureContext = natureAvailable && !localPlanner;
    byId("show-nature").checked = state.showNatureContext;
    const poiAvailable = Boolean(
      state.config.poi_index_available && state.poiIndexStatus?.available,
    );
    if (!sharedSnapshot) state.config.poi_index_available = poiAvailable;
    byId("places-filters").querySelectorAll("input").forEach((input) => {
      input.disabled = !poiAvailable;
    });
    setLocalizedText(byId("places-status"), () => poiAvailable
      ? tr`Local OSM places index ready · ${formatCount(state.poiIndexStatus.feature_count)} regional features.`
      : t("POI index unavailable. Place discovery is disabled; routing still works."));
    if (!sharedSlug) {
      plannerLocation = createPlannerLocationController({
        renderFix: renderPlannerCurrentLocation,
        clearFix: clearPlannerCurrentLocation,
        centerFix: centerPlannerCurrentLocation,
        avatarKey: trailProfileAvatarKey,
        subscribeAvatar: subscribeTrailProfile,
      });
    }
    const mapInitialized = initializeMap(state.config, {
      onReady: () => {
        mapReady = true;
        renderMapData();
        plannerLocation?.mapReady();
        // Either map images or the regional worker may finish first.
        if (localPlanner) { renderRoutingProfiles({ preserveUnavailableSelection: true }); render(); }
        void prepareRegion();
      },
      onError: (message) => { showMapError(message); void prepareRegion(); },
      onViewportChange: schedulePoiRefresh,
      onUserMapInteraction: () => plannerLocation?.manualMapInteraction(),
      onMapClick: (coordinate) => {
        if (isImmutableSnapshotDisplay() || ["running", "reversing"].includes(state.request.status)) return;
        if (state.settingRequestedApproachId) {
          const place = state.autoTour.requestedPlaces.find((value, index) => (
            (value.id ?? requestedPlaceIdentifier(value, index))
            === state.settingRequestedApproachId
          ));
          if (place) { rememberPointEdit("Place approach updated"); place.approachOverride = coordinate; }
          state.settingRequestedApproachId = null;
          invalidateAndRender();
          setEditableRequestStatus(() => (t("Requested-place approach set from map.")));
          return;
        }
        if (state.endpointSetMode) {
          const kind = state.endpointSetMode;
          replaceResolvedRouteLocation({ endpoint: kind }, coordinate, {
            assignEndpoint: assignActiveEndpoint, name: byId(`hard-${kind}-name`).value.trim(),
          });
          state.endpointSetMode = null;
          setLocalizedText(byId(`set-hard-${kind}`), () => t("Set on map"));
          invalidateAndRender();
          setEditableRequestStatus(
            () => (tr`${kind === "start" ? t("Start") : t("End")} point set from map.`),
          );
          const reopenAdventure = adventureMapEndpoint === kind;
          adventureMapEndpoint = null;
          if (reopenAdventure) void adventureDialog?.open();

          return;
        }
        if (state.movingPointIndex !== null) {
          const index = state.movingPointIndex;
          replaceResolvedRouteLocation({ index }, coordinate);
          clearPointPlacement();
          invalidateAndRender();

          setEditableRequestStatus(() => (t("Stop moved. Generate again to use the new position.")));
          return;
        }
        if (state.addPointMode) {
          try {
            addResolvedRouteLocation(coordinate, { assignEndpoint: assignActiveEndpoint,
              explicitStop: state.planningStrategy !== "automatic" });
            clearPointPlacement(); updateControlsFromOptions(); invalidateAndRender();
            keepCoordinateVisible([coordinate.lon, coordinate.lat]);
            setEditableRequestStatus(() => (t("Route point set from map.")));
          } catch (error) { showError(() => (error.message)); }
          return;
        }

        try {
          addResolvedRouteLocation(coordinate, { assignEndpoint: assignActiveEndpoint });
          updateControlsFromOptions();
          invalidateAndRender();
          keepCoordinateVisible([coordinate.lon, coordinate.lat]);
          setEditableRequestStatus(() => (t("Ready to generate.")));
        } catch (error) { showError(() => (error.message)); }
      },
    });
    if (mapInitialized) void plannerLocation?.initialize();
    if (localPlanner) initializeNativeItineraryHandoff({ dialog: itineraryDialog });
    render();
    if (!mapInitialized) void prepareRegion();
    if (localPlanner && !sharedSnapshot) void checkAdventureRecovery();
    if (sharedSnapshot) {
      fitCoordinates(sharedSnapshot.candidate.route.geometry);
      if (state.networkStatus !== "offline") {
        await selectCandidate(sharedSnapshot.candidate.id);
        setLocalizedText(byId("request-status"), () => t("Saved route opened. Its route and settings are unchanged."));
      } else {
        setLocalizedText(byId("request-status"), () => t("Showing the saved offline copy. Its route and settings are unchanged."));
      }
    } else if (state.networkStatus === "offline") {
      setLocalizedText(byId("request-status"), () => localPlanner ? t("Planning uses installed data on this device.")
          : t("Sugarglider is offline. The application shell is ready; reconnect to plan a route."));
    }
  } catch (error) {
    handleError(error, t("The Sugarglider API is unavailable."));
    showMapError(t("Map configuration could not be loaded."));
  }
}

window.addEventListener("DOMContentLoaded", start, { once: true });
