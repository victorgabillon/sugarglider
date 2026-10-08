// A view of existing editor authorities. Menus and gesture previews hold no route state.
import { state } from "./state.js";
import { pointUndoLabel, pointRedoLabel } from "./route_edit_history.js";
import { configurePointStripDrag } from "./route_point_drag.js";

const popoverListeners = new WeakMap();

function action(parent, key, text, callback, disabled) {
  const button = document.createElement("button"); button.type = "button";
  button.dataset.dockAction = key; button.textContent = text; button.disabled = disabled;
  button.addEventListener("click", callback); parent.append(button); return button;
}
function attachPopover(button, popover, root) {
  button.popoverTargetElement = popover; button.setAttribute("aria-haspopup", "dialog");
  button.setAttribute("aria-expanded", "false");
  const previous = popoverListeners.get(popover);
  if (previous) popover.removeEventListener("toggle", previous);
  const toggle = event => {
    const open = event.newState === "open";
    button.setAttribute("aria-expanded", String(open));
    if (open) {
      const r = root.getBoundingClientRect();
      popover.style.left = `${r.left}px`; popover.style.bottom = `${innerHeight - r.top + 6}px`;
      popover.style.width = `${r.width}px`;
      popover.style.maxHeight = `${Math.max(80, r.top - 8)}px`;
      popover.querySelector("button:not(:disabled)")?.focus({ preventScroll: true });
    }
  };
  popover.addEventListener("toggle", toggle); popoverListeners.set(popover, toggle);
}
export function renderRouteDock({ root, disabled, visits = [], onSelectPoint, onSelectEndpoint, onMove, onRemove, onReorder, onMoveEndpoint, onClearEndpoint, onChooseMap, onDetails, onClearSelection, onSearch }) {
  const active = document.activeElement;
  const focus = root.contains(active) ? { id: active.id, action: active.dataset.dockAction, chip: active.dataset.routeChip } : null;
  const endpoints = state.planningMode === "auto_tour" ? state.autoTour : state.waypointEndpoints;
  const offset = state.planningMode === "auto_tour" && endpoints.start ? 1 : 0;
  const canReorder = state.planningMode === "waypoint_route" && state.options.waypointOrder === "fixed";
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
  order.title = state.planningMode === "waypoint_route" ? "Choose As tapped for manual reorder; Start and End stay fixed" : "Add stops to choose their visit order";
  const strip = root.querySelector("#route-point-strip");
  configurePointStripDrag({ root, strip, onReorder, onRemove, canReorder, disabled });
  const scroll = strip.scrollLeft;
  strip.replaceChildren();
  function chip(key, text, label, selected, select, stopIndex = null) {
    const button = document.createElement("button"); button.type = "button";
    button.dataset.routeChip = key; button.textContent = text; button.disabled = disabled;
    button.setAttribute("aria-label", label); button.setAttribute("aria-pressed", String(selected));
    if (stopIndex !== null) {
      button.dataset.stopIndex = String(stopIndex);
      if (selected && !disabled) {
        button.setAttribute("aria-describedby", "route-strip-help");
        button.title = canReorder ? "Drag to reorder or remove; More actions has keyboard alternatives" : "Drag to remove; choose As tapped to reorder";
      }
    }
    button.addEventListener("click", selected && onClearSelection ? onClearSelection : select); strip.append(button);
  }
  if (endpoints.start) chip("start", "S", "Start", state.selectedEndpointKind === "start", () => onSelectEndpoint("start"));
  const visitOrder = new Map(visits.map((visit, i) => [visit.original_index, i]));
  const stops = state.points.slice(offset).map((point, i) => ({ point, index: i + offset }));
  if (visits.length) stops.sort((a, b) => (visitOrder.get(a.index) ?? a.index) - (visitOrder.get(b.index) ?? b.index));
  stops.forEach(({ point, index }, i) => chip(String(index), String(i + 1), `Stop ${i + 1}: ${point.name || "Unnamed stop"}`,
    state.selectedPointIndex === index && !state.selectedEndpointKind, () => onSelectPoint(index), index));
  if (endpoints.end) chip("end", "E", "End", state.selectedEndpointKind === "end", () => onSelectEndpoint("end"));
  if (!disabled) {
    const add = document.createElement("button"); add.type = "button"; add.id = "dock-add";
    add.textContent = "+"; add.setAttribute("aria-label", "Add route point"); strip.append(add);
    attachPopover(add, root.querySelector("#route-add-menu"), root);
  }
  const chooseMap = root.querySelector('[data-dock-action="choose-map"]');
  chooseMap.disabled = disabled; chooseMap.onclick = () => { root.querySelector("#route-add-menu").hidePopover(); onChooseMap(); };
  const searchLocation = root.querySelector('[data-dock-action="search-location"]');
  searchLocation.disabled = disabled || !onSearch;
  searchLocation.onclick = event => { root.querySelector("#route-add-menu").hidePopover(); onSearch?.(null, event.currentTarget); };
  strip.scrollLeft = scroll;
  if (strip.clientWidth) strip.querySelector('[aria-pressed="true"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
  const hint = root.querySelector("#route-dock-hint");
  hint.textContent = !endpoints.start ? "Tap the map to choose Start" : endpoints.routeTopology !== "loop" && !endpoints.end ? "Tap the map to choose End" : "";
  root.querySelector("#route-strip-help").textContent = canReorder
    ? "Select a stop, then drag its gripped chip to reorder or Remove. Swipe other chips or ribbon gaps to scroll. More actions offers Move earlier, Move later, and Remove."
    : "Select a stop, then drag its gripped chip to Remove. Choose As tapped to reorder. Swipe other chips or ribbon gaps to scroll. More actions offers Remove.";
  const editor = root.querySelector("#route-quick-editor"); editor.replaceChildren();
  const kind = state.selectedEndpointKind, index = state.selectedPointIndex;
  const point = kind ? endpoints[kind] : index !== null && index >= offset ? state.points[index] : null;
  const placing = state.endpointSetMode || state.movingPointIndex !== null || state.addPointMode || state.settingRequestedApproachId;
  editor.hidden = !point || Boolean(placing);
  if (point && !placing) {
    const label = kind ? kind === "start" ? "Start" : "End" : `Stop ${stops.findIndex(stop => stop.index === index) + 1}`;
    const title = document.createElement("strong"); title.textContent = label; editor.append(title);
    const move = action(editor, "move", "Move", () => {}, disabled);
    const acquisition = document.createElement("div"); acquisition.id = "route-move-menu"; acquisition.popover = "auto";
    acquisition.className = "route-dock-popover"; acquisition.role = "dialog"; acquisition.setAttribute("aria-label", `Move ${label}`);
    action(acquisition, "move-search", "Search place or address", event => {
      acquisition.hidePopover(); onSearch?.(kind ? { endpoint: kind } : { index }, event.currentTarget);
    }, disabled || !onSearch);
    action(acquisition, "move-map", "Choose on map", () => {
      acquisition.hidePopover(); kind ? onMoveEndpoint(kind) : onMove(index);
    }, disabled);
    editor.append(acquisition); attachPopover(move, acquisition, root);
    const more = action(editor, "more", "⋯", () => {}, disabled);
    more.setAttribute("aria-label", `More actions for ${label}`);
    const menu = document.createElement("div"); menu.id = "route-point-actions"; menu.popover = "auto";
    menu.className = "route-dock-popover"; menu.role = "dialog"; menu.setAttribute("aria-label", `Actions for ${label}`);
    if (!kind) {
      action(menu, "earlier", "Move earlier", () => onReorder(index, index - 1), disabled || !canReorder || index <= offset);
      action(menu, "later", "Move later", () => onReorder(index, index + 1), disabled || !canReorder || index >= state.points.length - 1);
      if (!canReorder) { const note = document.createElement("p"); note.textContent = "Choose As tapped to reorder stops."; menu.append(note); }
    }
    action(menu, "remove", kind ? `Clear ${label}` : "Remove", () => kind ? onClearEndpoint(kind) : onRemove(index), disabled);
    action(menu, "details", "Edit details in Plan", onDetails, disabled);
    editor.append(menu); attachPopover(more, menu, root);
  }
  if (focus) {
    const replacement = focus.id ? root.querySelector(`#${CSS.escape(focus.id)}`)
      : focus.action ? editor.querySelector(`[data-dock-action="${focus.action}"]`)
      : strip.querySelector('[aria-pressed="true"]') ?? strip.querySelector(`[data-route-chip="${focus.chip}"]`);
    const target = replacement && !replacement.disabled && replacement.getClientRects().length ? replacement
      : strip.querySelector('[aria-pressed="true"]') ?? root.querySelector("#dock-add") ?? undo;
    target.focus({ preventScroll: true });
  }
  root.closest(".map-panel").style.setProperty("--route-dock-height", `${root.getBoundingClientRect().height}px`);
}
