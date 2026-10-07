// Presentation policy over the existing planner authorities, not another plan.
import { state, saveActivePoints, isImmutableSnapshotDisplay } from "./state.js";
import { rememberPointEdit, commitPointEdit } from "./route_edit_history.js";
export { rememberPointEdit, undoPointEdit, redoPointEdit, clearPointUndo, pointUndoLabel, pointRedoLabel } from "./route_edit_history.js";

const commonOptions = ["name", "targetDistanceKm", "toleranceKm", "maximumDistanceKm",
  "distancePriority", "candidateCount", "seed", "waypointOrder"];
const endpointKeys = new Set(["name", "lat", "lon", "id", "originalIndex", "_mapCreated", "constraintStrength"]);
function exactEndpointCompatible(point) {
  return point && (point.constraintStrength ?? "exact") === "exact"
    && Object.keys(point).every(key => endpointKeys.has(key));
}
export function changeMapTopology(topology) {
  const endpoints = state.planningMode === "auto_tour" ? state.autoTour : state.waypointEndpoints;
  if (!["loop", "point_to_point"].includes(topology) || topology === endpoints.routeTopology) return false;
  saveActivePoints();
  const firstStop = state.planningMode === "auto_tour" && endpoints.start ? 1 : 0;
  const last = state.points.length > firstStop ? state.points.at(-1) : null;
  const end = endpoints.end;
  const maximum = state.planningStrategy === "auto_tour" ? 6 : (state.config?.max_required_points ?? 30);
  if (topology === "loop" && end && (!exactEndpointCompatible(end) || state.points.length - firstStop >= maximum)) {
    throw new Error("Keep Finish elsewhere: End cannot become an exact stop without losing intent or exceeding the stop limit.");
  }
  rememberPointEdit("Finish changed");
  if (topology === "point_to_point" && last?._mapCreated && exactEndpointCompatible(last)) {
    state.points.pop(); endpoints.end = last;
    state.selectedEndpointKind = "end"; state.selectedPointIndex = null;
  } else if (topology === "loop" && end) {
    state.points.push(end); endpoints.end = null;
    state.selectedEndpointKind = null; state.selectedPointIndex = state.points.length - 1;
  }
  endpoints.routeTopology = topology;
  state.endpointSetMode = null; state.movingPointIndex = null; state.addPointMode = false;
  reconcileAutomaticIntent(); commitPointEdit();
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
    rememberPointEdit("Start added"); assignEndpoint("start", { name: "Hard start", ...coordinate, _mapCreated: true });
    state.selectedEndpointKind = "start"; state.selectedPointIndex = null;
    commitPointEdit(); return true;
  }
  if (endpoints.routeTopology === "point_to_point" && !endpoints.end) {
    rememberPointEdit("End added"); assignEndpoint("end", { name: "Hard end", ...coordinate, _mapCreated: true });
    reconcileAutomaticIntent(); state.selectedEndpointKind = "end"; state.selectedPointIndex = null;
    commitPointEdit(); return true;
  }
  const count = state.planningMode === "auto_tour" ? state.points.length - Number(Boolean(endpoints.start)) : state.points.length;
  const maximum = state.planningStrategy === "auto_tour" ? 6 : (state.config?.max_required_points ?? 30);
  if (count >= maximum) throw new Error(`This route already has the maximum ${maximum} stops.`);
  const extending = endpoints.routeTopology === "point_to_point" && state.planningStrategy === "automatic";
  if (extending && !exactEndpointCompatible(endpoints.end)) throw new Error("Choose Move End to preserve this imported End’s intent.");
  rememberPointEdit(extending ? "End extended" : "Stop added");
  const next = state.points.reduce((n, p) => Math.max(n, p.originalIndex ?? -1), endpoints.end?.originalIndex ?? -1) + 1;
  const point = extending ? endpoints.end : { name: `Point ${count + 1}`, ...coordinate, originalIndex: next, _mapCreated: true };
  if (extending) assignEndpoint("end", { name: "Hard end", ...coordinate, originalIndex: next, _mapCreated: true });
  state.points.push(point); reconcileAutomaticIntent();
  state.selectedPointIndex = extending ? null : state.points.indexOf(point); state.selectedEndpointKind = extending ? "end" : null;
  commitPointEdit();
  return true;
}
export function routeIntentPresentation() {
  const endpoints = state.planningMode === "auto_tour" ? state.autoTour : state.waypointEndpoints;
  const count = state.planningMode === "auto_tour" ? Math.max(0, state.points.length - Number(Boolean(endpoints.start))) : state.points.length;
  if (!endpoints.start) return { title: "Tap the map to choose Start", detail: "Then generate a route, or keep tapping to add stops." };
  if (endpoints.routeTopology === "point_to_point" && !endpoints.end) return { title: "Start set · Choose End", detail: "Tap the map to choose End. Each further tap extends the route." };
  if (state.planningMode === "auto_tour") return {
    compactTitle: `${state.options.targetDistanceKm} km ${endpoints.routeTopology === "loop" ? "loop" : "route to End"}`,
    title: `${state.options.targetDistanceKm} km ${endpoints.routeTopology === "loop" ? "loop from Start" : "route to End"}`,
    detail: count || state.autoTour.requestedPlaces.length ? "Sugarglider will design a route with your chosen places." : "Start set. Generate now, or tap the map to add places to pass through.",
  };
  return { title: ["Start", ...Array.from({ length: count }, (_, i) => String(i + 1)), endpoints.routeTopology === "loop" ? "Start" : "End"].join(" → "),
    detail: `Sugarglider will connect your points. ${endpoints.routeTopology === "loop" ? "Tap the map to add stops" : "Tap the map to extend End"}; select a point to edit it.` };
}
