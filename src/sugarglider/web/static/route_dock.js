// A view of the existing editor authorities, with callbacks into the Plan editor.
import { state } from "./state.js";
import { pointUndoLabel, pointRedoLabel } from "./route_edit_history.js";

export function renderRouteDock({ root, disabled, visits = [], onSelectPoint, onSelectEndpoint, onMove, onRemove, onReorder, onMoveEndpoint, onClearEndpoint }) {
  const active = document.activeElement;
  const focus = root.contains(active) ? { id: active.id, action: active.dataset.dockAction, chip: active.dataset.routeChip } : null;
  const endpoints = state.planningMode === "auto_tour" ? state.autoTour : state.waypointEndpoints;
  const offset = state.planningMode === "auto_tour" && endpoints.start ? 1 : 0;
  const undo = root.querySelector("#undo-point-edit"), redo = root.querySelector("#redo-point-edit");
  undo.disabled = disabled || !pointUndoLabel(); redo.disabled = disabled || !pointRedoLabel();
  undo.setAttribute("aria-label", pointUndoLabel() ? `Undo: ${pointUndoLabel()}` : "Undo route edit");
  redo.setAttribute("aria-label", pointRedoLabel() ? `Redo: ${pointRedoLabel()}` : "Redo route edit");
  const finish = root.querySelector("#dock-finish"), order = root.querySelector("#dock-order");
  finish.value = endpoints.routeTopology; finish.disabled = disabled;
  root.querySelector("#dock-finish-label").textContent = endpoints.routeTopology === "loop" ? "Loop" : "Finish elsewhere";
  root.querySelector("#dock-order-label").textContent = state.options.waypointOrder === "fixed" ? "As tapped" : "Optimize stops";
  order.value = state.options.waypointOrder;
  order.disabled = disabled || state.planningMode !== "waypoint_route";
  order.title = state.planningMode === "waypoint_route" ? "Start and End stay fixed" : "Add stops to choose their visit order";
  const strip = root.querySelector("#route-point-strip");
  const scroll = strip.scrollLeft;
  strip.replaceChildren();
  function chip(key, text, label, selected, select) {
    const button = document.createElement("button"); button.type = "button";
    button.dataset.routeChip = key; button.textContent = text; button.disabled = disabled;
    button.setAttribute("aria-label", label); button.setAttribute("aria-pressed", String(selected));
    button.addEventListener("click", select); strip.append(button);
  }
  if (endpoints.start) chip("start", "S", "Start", state.selectedEndpointKind === "start", () => onSelectEndpoint("start"));
  const visitOrder = new Map(visits.map((visit, i) => [visit.original_index, i]));
  const stops = state.points.slice(offset).map((point, i) => ({ point, index: i + offset }));
  if (visits.length) stops.sort((a, b) => (visitOrder.get(a.index) ?? a.index) - (visitOrder.get(b.index) ?? b.index));
  stops.forEach(({ point, index }, i) => chip(String(index), String(i + 1), `Stop ${i + 1}: ${point.name || "Unnamed stop"}`,
    state.selectedPointIndex === index && !state.selectedEndpointKind, () => onSelectPoint(index)));
  if (endpoints.end) chip("end", "E", "End", state.selectedEndpointKind === "end", () => onSelectEndpoint("end"));
  strip.scrollLeft = scroll;
  if (strip.clientWidth) strip.querySelector('[aria-pressed="true"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
  const hint = root.querySelector("#route-dock-hint");
  hint.hidden = Boolean(endpoints.start && (endpoints.routeTopology === "loop" || endpoints.end));
  hint.textContent = !endpoints.start ? "Tap the map to choose Start" : "Tap the map to choose End";
  const editor = root.querySelector("#route-quick-editor"); editor.replaceChildren();
  const kind = state.selectedEndpointKind;
  const index = state.selectedPointIndex;
  const point = kind ? endpoints[kind] : index !== null && index >= offset ? state.points[index] : null;
  const placing = state.endpointSetMode || state.movingPointIndex !== null || state.addPointMode || state.settingRequestedApproachId;
  editor.hidden = !point || Boolean(placing);
  if (point && !placing) {
    const title = document.createElement("strong");
    title.textContent = kind ? kind === "start" ? "Start" : "End" : `Stop ${stops.findIndex(stop => stop.index === index) + 1}`;
    editor.append(title);
    const actions = document.createElement("div"); actions.className = "route-quick-actions";
    function action(key, text, callback, unavailable = false) {
      const button = document.createElement("button"); button.type = "button";
      button.dataset.dockAction = key; button.textContent = text;
      button.disabled = disabled || unavailable; button.addEventListener("click", callback); actions.append(button);
    }
    action("move", "Move", () => kind ? onMoveEndpoint(kind) : onMove(index));
    if (!kind) {
      action("earlier", "Earlier", () => onReorder(index, index - 1), index <= offset || state.planningMode === "auto_tour");
      action("later", "Later", () => onReorder(index, index + 1), index >= state.points.length - 1 || state.planningMode === "auto_tour");
    }
    action("remove", kind ? "Clear" : "Remove", () => kind ? onClearEndpoint(kind) : onRemove(index));
    editor.append(actions);
  }
  if (focus) {
    const replacement = focus.id ? root.querySelector(`#${CSS.escape(focus.id)}`)
      : focus.action ? editor.querySelector(`[data-dock-action="${focus.action}"]`)
      : strip.querySelector('[aria-pressed="true"]') ?? strip.querySelector(`[data-route-chip="${focus.chip}"]`);
    const target = replacement && !replacement.disabled ? replacement : strip.querySelector('[aria-pressed="true"]') ?? undo;
    target.focus({ preventScroll: true });
  }
  root.closest(".map-panel").style.setProperty("--route-dock-height", `${root.getBoundingClientRect().height}px`);
}
