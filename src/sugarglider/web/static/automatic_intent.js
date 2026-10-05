// Presentation policy over the existing planner authorities, not another plan.
import { state, saveActivePoints, isImmutableSnapshotDisplay } from "./state.js";

const commonOptions = ["name", "targetDistanceKm", "toleranceKm", "maximumDistanceKm",
  "distancePriority", "candidateCount", "seed", "waypointOrder"];
let undo = null;
const undoFields = ["planningMode", "planningStrategy", "points", "autoTour", "waypointEndpoints",
  "waypointPoints", "options", "autoTourOptions", "waypointOptions", "selectedPointIndex", "selectedEndpointKind"];
export function clearPointUndo() { undo = null; }
export function pointUndoLabel() { return undo?.label ?? ""; }
export function rememberPointEdit(label) {
  undo = { label, values: structuredClone(Object.fromEntries(undoFields.map(k => [k, state[k]]))) };
}
export function undoPointEdit() {
  if (!undo || isImmutableSnapshotDisplay() || ["running", "reversing"].includes(state.request.status)) return false;
  Object.assign(state, undo.values); undo = null;
  state.endpointSetMode = null; state.addPointMode = false; state.movingPointIndex = null;
  state.pendingPointPopupIndex = null; state.settingRequestedApproachId = null;
  return true;
}
export function hasDiscoveryIntent() {
  return state.planningMode === "auto_tour"
    && Boolean(state.autoTour.requestedPlaces.length || state.autoTour.preferredPoiIds.length);
}
export function reconcileAutomaticIntent() {
  if (state.planningStrategy !== "automatic" || isImmutableSnapshotDisplay()) return false;
  saveActivePoints();
  // Discovery-only intent cannot be converted into waypoint constraints losslessly.
  if (hasDiscoveryIntent()) { state.planningStrategy = "auto_tour"; return false; }
  const fromAuto = state.planningMode === "auto_tour";
  const endpoints = fromAuto ? state.autoTour : state.waypointEndpoints;
  const stops = fromAuto ? state.autoTour.hardPoints : state.points;
  // Automatic editing owns one geometry. Discard parked geometry from an
  // earlier explicit strategy, including discovery places which would otherwise
  // reappear when the final stop is removed. Mode-specific options remain parked.
  if (fromAuto) {
    Object.assign(state.waypointEndpoints, { start: null, end: null });
    state.waypointPoints = [];
  } else {
    Object.assign(state.autoTour, { start: null, end: null, hardPoints: [], requestedPlaces: [], preferredPoiIds: [] });
  }
  const mode = stops.length || endpoints.end ? "waypoint_route" : "auto_tour";
  if (mode === state.planningMode) return false;
  const selected = state.points[state.selectedPointIndex];
  const shared = Object.fromEntries(commonOptions.map(k => [k, state.options[k]]));
  const destination = mode === "auto_tour" ? state.autoTour : state.waypointEndpoints;
  const { start, end, routeTopology } = endpoints;
  Object.assign(destination, { start, end, routeTopology });
  // Move geometry, do not clone a second live draft. Explicit legacy switching
  // still owns its independent saved drafts; automatic inference never calls it.
  endpoints.start = null; endpoints.end = null;
  if (fromAuto) {
    state.autoTour.hardPoints = [];
    state.points = [...stops];
    state.waypointPoints = [...stops];
  } else {
    state.waypointPoints = [];
    state.autoTour.hardPoints = [...stops];
    state.points = [start, ...stops].filter(Boolean);
  }
  state.planningMode = mode;
  state.options = { ...(mode === "auto_tour" ? (state.autoTourOptions ?? state.options) : state.waypointOptions), ...shared };
  const index = state.points.indexOf(selected);
  state.selectedPointIndex = index < 0 ? null : index;
  if (selected === start) state.selectedEndpointKind = "start";
  saveActivePoints();
  return true;
}
export function appendMapIntent(coordinate, assignEndpoint) {
  const endpoints = state.planningMode === "auto_tour" ? state.autoTour : state.waypointEndpoints;
  if (!endpoints.start) {
    rememberPointEdit("Start added"); assignEndpoint("start", { name: "Hard start", ...coordinate });
    state.selectedEndpointKind = "start"; state.selectedPointIndex = null;
    return true;
  }
  if (endpoints.routeTopology === "point_to_point" && !endpoints.end) {
    rememberPointEdit("End added"); assignEndpoint("end", { name: "Hard end", ...coordinate });
    reconcileAutomaticIntent(); state.selectedEndpointKind = "end"; state.selectedPointIndex = null;
    return true;
  }
  const count = state.planningMode === "auto_tour" ? state.points.length - Number(Boolean(endpoints.start)) : state.points.length;
  const maximum = state.planningStrategy === "auto_tour" ? 6 : (state.config?.max_required_points ?? 30);
  if (count >= maximum) throw new Error(`This route already has the maximum ${maximum} stops.`);
  rememberPointEdit("Stop added");
  const next = state.points.reduce((n, p) => Math.max(n, p.originalIndex ?? -1), -1) + 1;
  const point = { name: `Point ${count + 1}`, ...coordinate, originalIndex: next };
  state.points.push(point); reconcileAutomaticIntent();
  state.selectedPointIndex = state.points.indexOf(point); state.selectedEndpointKind = null;
  return true;
}
export function routeIntentPresentation() {
  const endpoints = state.planningMode === "auto_tour" ? state.autoTour : state.waypointEndpoints;
  const count = state.planningMode === "auto_tour" ? Math.max(0, state.points.length - Number(Boolean(endpoints.start))) : state.points.length;
  if (!endpoints.start) return { title: "Tap the map to choose Start", detail: "Then generate a route, or keep tapping to add stops." };
  if (endpoints.routeTopology === "point_to_point" && !endpoints.end) return { title: "Start set · Choose End", detail: "Tap the map to set End. Further taps add stops before End." };
  if (state.planningMode === "auto_tour") return {
    compactTitle: `${state.options.targetDistanceKm} km ${endpoints.routeTopology === "loop" ? "loop" : "route to End"}`,
    title: `${state.options.targetDistanceKm} km ${endpoints.routeTopology === "loop" ? "loop from Start" : "route to End"}`,
    detail: count || state.autoTour.requestedPlaces.length ? "Sugarglider will design a route with your chosen places." : "Start set. Generate now, or tap the map to add places to pass through.",
  };
  return { title: ["Start", ...Array.from({ length: count }, (_, i) => String(i + 1)), endpoints.routeTopology === "loop" ? "Start" : "End"].join(" → "),
    detail: "Sugarglider will connect your points. Tap the map to add stops; select a point to edit it." };
}
