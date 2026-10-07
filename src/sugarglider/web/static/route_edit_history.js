// Volatile route intent only. Results, map state and capabilities never enter history.
import { state, saveActivePoints, isImmutableSnapshotDisplay } from "./state.js";

export const ROUTE_HISTORY_LIMIT = 32;
const fields = ["planningMode", "planningStrategy", "points", "autoTour", "waypointEndpoints",
  "waypointPoints", "options", "autoTourOptions", "waypointOptions", "routingProfile",
  "selectedPointIndex", "selectedEndpointKind"];
const undo = [], redo = [];
let pending = null;
function snapshot() {
  saveActivePoints();
  return structuredClone(Object.fromEntries(fields.map(key => [key, state[key]])));
}
function intent(values) {
  return JSON.stringify(Object.fromEntries(Object.entries(values).filter(([key]) => !key.startsWith("selected"))));
}
function editable() {
  return !isImmutableSnapshotDisplay() && !["running", "reversing"].includes(state.request.status);
}
export function clearPointUndo() { undo.length = 0; redo.length = 0; pending = null; }
export function rememberPointEdit(label) {
  if (editable() && !pending) pending = { label, values: snapshot() };
}
export function commitPointEdit() {
  if (!pending) return;
  const edit = pending; pending = null;
  if (intent(edit.values) === intent(snapshot())) return;
  undo.push(edit);
  if (undo.length > ROUTE_HISTORY_LIMIT) undo.shift();
  redo.length = 0;
}
export function pointUndoLabel() { commitPointEdit(); return undo.at(-1)?.label ?? ""; }
export function pointRedoLabel() { commitPointEdit(); return redo.at(-1)?.label ?? ""; }
function restore(source, destination) {
  commitPointEdit();
  if (!editable() || !source.length) return false;
  const edit = source.pop();
  destination.push({ label: edit.label, values: snapshot() });
  Object.assign(state, structuredClone(edit.values));
  state.endpointSetMode = null; state.addPointMode = false; state.movingPointIndex = null;
  state.pendingPointPopupIndex = null; state.settingRequestedApproachId = null;
  state.selectedRequestedPlaceId = null; state.pendingRequestedPlacePopupId = null;
  return true;
}
export function undoPointEdit() { return restore(undo, redo); }
export function redoPointEdit() { return restore(redo, undo); }
