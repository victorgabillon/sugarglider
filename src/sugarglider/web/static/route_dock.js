import { t, tr, setLocalizedText } from "./i18n.js";
// A view of existing editor authorities. Menus and gesture previews hold no route state.
import { state } from "./state.js";
import { pointUndoLabel, pointRedoLabel } from "./route_edit_history.js";
import { configurePointStripDrag } from "./route_point_drag.js";

const popoverListeners = new WeakMap();
const dockViews = new WeakMap();

// Disclosure state is presentation only. Closing preserves the selected point,
// canonical route, candidate and the existing Undo/Redo authority.
function dockView(root) {
  if (dockViews.has(root)) return dockViews.get(root);
  const mobile = root.ownerDocument.defaultView.matchMedia("(max-width: 840px)");
  const toggle = root.querySelector("#route-editor-toggle"), body = root.querySelector("#route-editor-body");
  const view = { expanded: !mobile.matches, review: false, set(expanded, focus = false) {
    view.expanded = Boolean(expanded) || !mobile.matches;
    if (!view.expanded) for (const menu of root.querySelectorAll(":popover-open")) menu.hidePopover();
    root.dataset.expanded = String(view.expanded); body.hidden = !view.expanded;
    if (view.expanded) body.scrollTop = 0;
    toggle.setAttribute("aria-expanded", String(view.expanded));
    const generate = root.querySelector("#generate-map");
    const destination = root.querySelector(mobile.matches ? ".route-dock-summary" : ".route-dock-actions");
    if (generate?.parentElement !== destination) destination.append(generate);
    if (focus) toggle.focus({ preventScroll: true });
    root.dispatchEvent(new CustomEvent("route-dock-layout", { bubbles: true }));
  } };
  toggle.addEventListener("click", () => view.set(!view.expanded));
  root.querySelector("#route-editor-close").addEventListener("click", () => view.set(false, true));
  root.addEventListener("keydown", event => {
    if (event.key !== "Escape" || event.defaultPrevented || !view.expanded || !mobile.matches
      || root.ownerDocument.querySelector("dialog[open], :popover-open")) return;
    view.set(false, true); event.preventDefault();
  });
  mobile.addEventListener("change", () => view.set(!mobile.matches));
  dockViews.set(root, view); view.set(view.expanded); return view;
}
export function setRouteDockExpanded(root, expanded, options = {}) {
  if (root) dockView(root).set(expanded, options.focus ?? false);
}

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
export function renderRouteDock({ root, disabled, visits = [], requiresReview = false, onSelectPoint, onSelectEndpoint, onMove, onRemove, onReorder, onMoveEndpoint, onClearEndpoint, onEndpointPolicy, onChooseMap, onDetails, onClearSelection, onSearch }) {
  const view = dockView(root);
  if (requiresReview && !view.review) view.set(true);
  view.review = requiresReview;
  const active = document.activeElement;
  const focus = root.contains(active) ? { id: active.id, action: active.dataset.dockAction, chip: active.dataset.routeChip } : null;
  const endpoints = state.planningMode === "auto_tour" ? state.autoTour : state.waypointEndpoints;
  const offset = state.planningMode === "auto_tour" && endpoints.start ? 1 : 0;
  const canReorder = state.planningMode === "waypoint_route" && state.options.waypointOrder === "fixed";
  const undo = root.querySelector("#undo-point-edit"), redo = root.querySelector("#redo-point-edit");
  undo.disabled = disabled || !pointUndoLabel(); redo.disabled = disabled || !pointRedoLabel();
  undo.setAttribute("aria-label", pointUndoLabel() ? tr`Undo: ${t(pointUndoLabel())}` : t("Undo route edit"));
  redo.setAttribute("aria-label", pointRedoLabel() ? tr`Redo: ${t(pointRedoLabel())}` : t("Redo route edit"));
  const finish = root.querySelector("#dock-finish"), order = root.querySelector("#dock-order");
  finish.value = endpoints.routeTopology; finish.disabled = disabled;
  setLocalizedText(root.querySelector("#dock-finish-label"), () => endpoints.routeTopology === "loop" ? t("Loop") : t("Finish elsewhere"));
  setLocalizedText(root.querySelector("#dock-order-label"), () => state.options.waypointOrder === "fixed" ? t("As tapped") : t("Optimize stops"));
  order.value = state.options.waypointOrder;
  order.disabled = disabled || state.planningMode !== "waypoint_route";
  order.title = state.planningMode === "waypoint_route" ? t("Choose As tapped for manual reorder; Start and End stay fixed") : t("Add stops to choose their visit order");
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
        button.title = canReorder ? t("Drag to reorder or remove; More actions has keyboard alternatives") : t("Drag to remove; choose As tapped to reorder");
      }
    }
    button.addEventListener("click", () => { view.set(true); (selected && onClearSelection ? onClearSelection : select)(); }); strip.append(button);
  }
  if (endpoints.start) chip("start", "S", t("Start"), state.selectedEndpointKind === "start", () => onSelectEndpoint("start"));
  const visitOrder = new Map(visits.map((visit, i) => [visit.original_index, i]));
  const stops = state.points.slice(offset).map((point, i) => ({ point, index: i + offset }));
  if (visits.length) stops.sort((a, b) => (visitOrder.get(a.index) ?? a.index) - (visitOrder.get(b.index) ?? b.index));
  setLocalizedText(root.querySelector("#route-collapsed-summary"), () => {
    if (!endpoints.start) return t("Tap the map to choose Start");
    const order = [t("Start"), ...stops.map((_, i) => String(i + 1))];
    if (endpoints.end) order.push(t("End"));
    return `${order.join(" → ")} · ${endpoints.routeTopology === "loop" ? t("Loop") : t("Point-to-point")}`;
  });
  root.querySelector("#route-editor-toggle").title = t("Edit route");
  stops.forEach(({ point, index }, i) => chip(String(index), String(i + 1), tr`Stop ${i + 1}: ${point.name || t("Unnamed stop")}`,
    state.selectedPointIndex === index && !state.selectedEndpointKind, () => onSelectPoint(index), index));
  if (endpoints.end) chip("end", "E", t("End"), state.selectedEndpointKind === "end", () => onSelectEndpoint("end"));
  if (!disabled) {
    const add = document.createElement("button"); add.type = "button"; add.id = "dock-add";
    add.textContent = "+"; add.setAttribute("aria-label", t("Add route point")); strip.append(add);
    attachPopover(add, root.querySelector("#route-add-menu"), root);
  }
  const chooseMap = root.querySelector('[data-dock-action="choose-map"]');
  chooseMap.disabled = disabled; chooseMap.onclick = () => { view.set(true); root.querySelector("#route-add-menu").hidePopover(); onChooseMap(); };
  const searchLocation = root.querySelector('[data-dock-action="search-location"]');
  searchLocation.disabled = disabled || !onSearch;
  searchLocation.onclick = event => { root.querySelector("#route-add-menu").hidePopover(); onSearch?.(null, event.currentTarget); };
  strip.scrollLeft = scroll;
  // Reveal only within the horizontal ribbon. scrollIntoView would also scroll
  // the containing sheet past the selected point's contextual actions.
  const selectedChip = strip.querySelector('[aria-pressed="true"]');
  if (strip.clientWidth && selectedChip) {
    const bounds = strip.getBoundingClientRect(), selected = selectedChip.getBoundingClientRect();
    if (selected.left < bounds.left) strip.scrollLeft -= bounds.left - selected.left;
    else if (selected.right > bounds.right) strip.scrollLeft += selected.right - bounds.right;
  }
  const hint = root.querySelector("#route-dock-hint");
  setLocalizedText(hint, () => !endpoints.start ? t("Tap the map to choose Start") : endpoints.routeTopology !== "loop" && !endpoints.end ? t("Tap the map to choose End") : "");
  setLocalizedText(root.querySelector("#route-strip-help"), () => canReorder
    ? t("Select a stop, then drag its gripped chip to reorder or Remove. Swipe other chips or ribbon gaps to scroll. More actions offers Move earlier, Move later, and Remove.")
    : t("Select a stop, then drag its gripped chip to Remove. Choose As tapped to reorder. Swipe other chips or ribbon gaps to scroll. More actions offers Remove."));
  const editor = root.querySelector("#route-quick-editor"); editor.replaceChildren();
  const kind = state.selectedEndpointKind, index = state.selectedPointIndex;
  const point = kind ? endpoints[kind] : index !== null && index >= offset ? state.points[index] : null;
  const placing = state.endpointSetMode || state.movingPointIndex !== null || state.addPointMode || state.settingRequestedApproachId;
  // Choosing a map position is an explicit transition. Keep its instruction and
  // Cancel action visible, while returning secondary editing controls to the bar.
  if (placing && !view.placing) { view.returnAfterPlacement = view.expanded; view.set(false); }
  if (!placing && view.placing && view.returnAfterPlacement) view.set(true);
  view.placing = Boolean(placing);
  editor.hidden = !point || Boolean(placing);
  if (point && !placing) {
    const label = kind ? kind === "start" ? t("Start") : t("End") : tr`Stop ${stops.findIndex(stop => stop.index === index) + 1}`;
    const title = document.createElement("strong"); title.textContent = label; editor.append(title);
    if (kind && onEndpointPolicy) {
      const label = document.createElement("label"); setLocalizedText(label, () => t("Snap "));
      const select = document.createElement("select"); select.dataset.dockAction = "snap-policy"; select.setAttribute("aria-label", tr`${kind === "start" ? t("Start") : t("End")} snap policy`);
      for (const [value, text] of [["near", t("Near this point")], ["exact", t("Exact point")]]) {
        const option = document.createElement("option"); option.value = value; option.textContent = text; select.append(option);
      }
      select.value = point.snapPolicy ?? "exact"; select.disabled = disabled;
      select.addEventListener("change", () => onEndpointPolicy(kind, select.value)); label.append(select); editor.append(label);
    }
    const move = action(editor, "move", t("Move"), () => {}, disabled);
    const acquisition = document.createElement("div"); acquisition.id = "route-move-menu"; acquisition.popover = "auto";
    acquisition.className = "route-dock-popover"; acquisition.role = "dialog"; acquisition.setAttribute("aria-label", tr`Move ${label}`);
    action(acquisition, "move-search", t("Search place or address"), event => {
      acquisition.hidePopover(); onSearch?.(kind ? { endpoint: kind } : { index }, event.currentTarget);
    }, disabled || !onSearch);
    action(acquisition, "move-map", t("Choose on map"), () => {
      acquisition.hidePopover(); kind ? onMoveEndpoint(kind) : onMove(index);
    }, disabled);
    editor.append(acquisition); attachPopover(move, acquisition, root);
    const more = action(editor, "more", "⋯", () => {}, disabled);
    more.setAttribute("aria-label", tr`More actions for ${label}`);
    const menu = document.createElement("div"); menu.id = "route-point-actions"; menu.popover = "auto";
    menu.className = "route-dock-popover"; menu.role = "dialog"; menu.setAttribute("aria-label", tr`Actions for ${label}`);
    if (!kind) {
      action(menu, "earlier", t("Move earlier"), () => onReorder(index, index - 1), disabled || !canReorder || index <= offset);
      action(menu, "later", t("Move later"), () => onReorder(index, index + 1), disabled || !canReorder || index >= state.points.length - 1);
      if (!canReorder) { const note = document.createElement("p"); setLocalizedText(note, () => t("Choose As tapped to reorder stops.")); menu.append(note); }
    }
    action(menu, "remove", kind ? tr`Clear ${label}` : t("Remove"), () => kind ? onClearEndpoint(kind) : onRemove(index), disabled);
    action(menu, "details", t("Edit details in Plan"), () => { menu.hidePopover(); onDetails(); }, disabled);
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
