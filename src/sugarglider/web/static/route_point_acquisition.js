// Input locations become ordinary planner points. Source-specific UI belongs to callers.
import { state, isImmutableSnapshotDisplay } from "./state.js";
import { appendMapIntent } from "./automatic_intent.js";
import { rememberPointEdit, commitPointEdit } from "./route_edit_history.js";

function resolvedCoordinate(location) {
  const { lat, lon } = location;
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
    throw new Error("Choose a valid route location.");
  }
  // Acquisition metadata is never spread into a routing constraint.
  const name = location.name;
  if (name !== undefined && (typeof name !== "string" || !name.trim() || name.length > 200
    || /[\u0000-\u001f\u007f-\u009f]/u.test(name))) throw new Error("Choose a valid location name.");
  return { lat, lon, ...(name === undefined ? {} : { name: name.trim() }) };
}
function editable() {
  return !isImmutableSnapshotDisplay() && !["running", "reversing"].includes(state.request.status);
}
export function addResolvedRouteLocation(location, { assignEndpoint, explicitStop = false }) {
  if (!editable()) return false;
  const coordinate = resolvedCoordinate(location);
  if (!explicitStop) return appendMapIntent(coordinate, assignEndpoint);
  // Retain the detailed editor's explicit-strategy Add stop grammar.
  const maximum = state.planningMode === "auto_tour"
    ? 6 + Number(Boolean(state.autoTour.start)) : state.config.max_required_points;
  if (state.points.length >= maximum) throw new Error("This route already has the maximum required points.");
  rememberPointEdit("Point added");
  const next = state.points.reduce((n, p) => Math.max(n, Number.isInteger(p.originalIndex) ? p.originalIndex : -1), -1) + 1;
  const point = { name: state.planningMode === "auto_tour"
    ? (state.points.length ? `Hard anchor ${state.points.length}` : "Start") : `Point ${state.points.length + 1}`,
    ...coordinate, originalIndex: next, _mapCreated: true };
  if (state.planningMode === "auto_tour" && !state.autoTour.start) assignEndpoint("start", point);
  else state.points.push(point);
  state.selectedEndpointKind = null; state.selectedPointIndex = state.points.length - 1;
  commitPointEdit();
  return true;
}
export function replaceResolvedRouteLocation(target, location, { assignEndpoint, name } = {}) {
  if (!editable()) return false;
  const coordinate = resolvedCoordinate(location);
  const endpoints = state.planningMode === "auto_tour" ? state.autoTour : state.waypointEndpoints;
  const kind = target.endpoint;
  if (kind && !["start", "end"].includes(kind)) return false;
  const existing = kind ? endpoints[kind] : state.points[target.index];
  if (!kind && !existing) return false;
  rememberPointEdit(kind ? `${kind === "start" ? "Start" : "End"} moved` : "Stop moved");
  const point = { ...existing, ...coordinate };
  if (kind) {
    point.name = name || coordinate.name || existing?.name || `Hard ${kind}`;
    assignEndpoint(kind, point);
  } else state.points[target.index] = point;
  state.selectedEndpointKind = kind ?? null;
  state.selectedPointIndex = kind ? null : target.index;
  commitPointEdit();
  return true;
}
