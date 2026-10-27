import { t, tr, setLocalizedText } from "./i18n.js";
import { pointDisplayName } from "./state.js";

export const constraintLabels = Object.freeze({
  exact: "Exact point",
  approach: "Nearby access",
  best_effort: "Best effort",
});

export function renderWaypointEditor({ list, points, selectedIndex, visitOrders, reorderDisabled = false, onSelect, onChange, onMove, onRemove, onPlace }) {
  const document = list.ownerDocument;
  const active = list.contains(document.activeElement) ? document.activeElement : null;
  const focus = active ? { index: active.closest(".poi-row")?.dataset.pointIndex, field: active.dataset.field, action: active.dataset.action, select: active.classList.contains("point-select") } : null;
  const openCoordinates = list.querySelector('.poi-row.selected details')?.open ?? false;
  list.replaceChildren();
  if (!points.length) {
    const empty = document.createElement("p"); empty.className = "field-help";
    setLocalizedText(empty, () => t("Add the places you want to pass through. A loop needs at least one stop.")); list.append(empty);
  }
  points.forEach((point, index) => {
    const selected = index === selectedIndex;
    const row = document.createElement("div"); row.className = `poi-row waypoint-row${selected ? " selected" : ""}`;
    row.dataset.pointIndex = String(index); row.role = "listitem";
    if (selected) row.setAttribute("aria-current", "true");
    const button = document.createElement("button"); button.type = "button"; button.className = "point-select";
    button.setAttribute("aria-pressed", String(selected));
    const order = document.createElement("span"); order.className = "stop-order"; setLocalizedText(order, () => (tr`Stop ${index + 1}${selected ? " · " + t("Selected") : ""}`));
    const name = document.createElement("strong"); name.className = "poi-name"; name.textContent = pointDisplayName(point, index);
    const hint = document.createElement("span"); hint.className = "stop-constraint";
    setLocalizedText(hint, () => t(constraintLabels[point.constraintStrength ?? "exact"] ?? "Unsupported constraint — review imported plan"));
    const visit = visitOrders.get(index);
    if (visit && visit !== index + 1) hint.textContent += tr` · Generated visit ${visit}`;
    button.append(order, name, hint); button.addEventListener("click", () => onSelect(index));
    button.addEventListener("keydown", event => {
      if (!["ArrowUp", "ArrowDown"].includes(event.key)) return;
      event.preventDefault(); const next = Math.max(0, Math.min(points.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)));
      onSelect(next); list.querySelector(`[data-point-index="${next}"] .point-select`)?.focus();
    });
    row.append(button);
    if (selected) {
      const editor = document.createElement("div"); editor.className = "stop-editor";
      const field = (parent, key, labelText, type, value) => {
        const label = document.createElement("label"); label.textContent = labelText;
        const input = document.createElement("input"); input.type = type; input.dataset.field = key; input.value = value ?? "";
        if (type === "number") input.step = "any"; else input.maxLength = 120;
        input.addEventListener("change", () => onChange(index, key, type === "number" ? input.value.trim() ? Number(input.value) : (key === "lat" || key === "lon" ? NaN : null) : input.value));
        label.append(input); parent.append(label);
      };
      if (point.itineraryReason) {
        const reason = document.createElement("p"); reason.className = "itinerary-reason";
        setLocalizedText(reason, () => tr`Suggested because: ${point.itineraryReason}`); editor.append(reason);
      }
      field(editor, "name", "Name", "text", point.name);
      const label = document.createElement("label"); setLocalizedText(label, () => t("How closely should the route visit?"));
      const strength = document.createElement("select"); strength.dataset.field = "constraintStrength";
      for (const [value, text] of Object.entries(constraintLabels)) strength.add(new Option(t(text), value));
      strength.value = point.constraintStrength ?? "exact";
      strength.addEventListener("change", () => onChange(index, "constraintStrength", strength.value)); label.append(strength); editor.append(label);
      const help = document.createElement("p"); help.className = "field-help";
      setLocalizedText(help, () => ({
        exact: t("Required within routing tolerance. If unreachable, planning stops; this point is never silently relaxed."),
        approach: t("Use a compatible approach to this place. If none is found, the stop is omitted and reported."),
        best_effort: t("May use a nearby reachable point within your limit, or omit the stop. The result explains any compromise."),
      }[point.constraintStrength ?? "exact"] ?? t("Review this unsupported constraint before generating."))); editor.append(help);
      const actions = document.createElement("div"); actions.className = "stop-actions";
      for (const [action, text, handler, disabled] of [
        ["place", t("Move on map"), () => onPlace(index), false],
        ["up", t("Move earlier"), () => onMove(index, index - 1), reorderDisabled || index === 0],
        ["down", t("Move later"), () => onMove(index, index + 1), reorderDisabled || index === points.length - 1],
        ["remove", t("Remove stop"), () => onRemove(index), false],
      ]) {
        const actionButton = document.createElement("button"); actionButton.type = "button"; actionButton.className = "button secondary";
        actionButton.dataset.action = action; actionButton.textContent = text; actionButton.disabled = disabled;
        actionButton.dataset.boundaryDisabled = String(disabled);
        actionButton.setAttribute("aria-label", `${text}: ${pointDisplayName(point, index)}`); actionButton.addEventListener("click", handler); actions.append(actionButton);
      }
      editor.append(actions);
      const details = document.createElement("details"); details.open = openCoordinates; const summary = document.createElement("summary"); setLocalizedText(summary, () => t("Coordinates and access limits")); details.append(summary);
      field(details, "lat", "Latitude", "number", point.lat); field(details, "lon", "Longitude", "number", point.lon);
      field(details, "accessSearchRadiusM", t("Access search radius (m)"), "number", point.accessSearchRadiusM ?? 500);
      field(details, "maximumBestEffortDistanceM", t("Maximum best-effort distance (m; blank uses access radius)"), "number", point.maximumBestEffortDistanceM);
      const capabilityNote = document.createElement("p"); capabilityNote.className = "field-help"; setLocalizedText(capabilityNote, () => t("Available options depend on the routing engine. Unsupported choices report an error; they are never weakened.")); details.append(capabilityNote);
      if (point.approachOverride) { const note = document.createElement("p"); note.className = "field-help"; setLocalizedText(note, () => t("This imported stop has an explicit approach override. It is preserved when editing its name or coordinate.")); details.append(note); }
      editor.append(details); row.append(editor);
    }
    list.append(row);
  });
  if (focus) {
    const row = list.querySelector(`[data-point-index="${focus.index}"]`);
    const target = focus.select ? row?.querySelector(".point-select") : focus.field ? row?.querySelector(`[data-field="${focus.field}"]`) : row?.querySelector(`[data-action="${focus.action}"]`);
    target?.focus({ preventScroll: true });
  }
}
