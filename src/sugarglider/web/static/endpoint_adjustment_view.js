import { t, tr, setLocalizedText } from "./i18n.js";
// Persistent per-candidate disclosures; callbacks keep editing authority in the app.
export function renderEndpointAdjustments(root, adjustments, { profileLabel, disabled, onShow, onMove, onUse }) {
  if (!root) return;
  const focused = root.contains(document.activeElement) ? document.activeElement.dataset.adjustmentAction : null;
  const open = new Set([...root.querySelectorAll("details[open]")].map(node => node.dataset.adjustmentRole));
  root.replaceChildren(); root.hidden = !adjustments.length;
  for (const item of adjustments) {
    const label = item.role === "start" ? t("Start") : item.endpoint === "start" ? t("Return to Start") : t("End");
    const metres = Math.round(item.distance_m);
    const details = document.createElement("details"); details.dataset.adjustmentRole = item.role;
    details.open = open.has(item.role) || item.status === "review_required";
    const title = document.createElement("summary");
    setLocalizedText(title, () => item.status === "review_required" ? tr`${label}: review ${metres} m adjustment` : tr`${label} adjusted by ${metres} m`);
    const text = document.createElement("p");
    setLocalizedText(text, () => item.status === "review_required"
      ? tr`The routed location returned for ${profileLabel} is ${metres} m from your selected ${item.endpoint === "start" ? t("Start") : t("End")}. Review it before using it. No route has been accepted. Generate again after editing.`
      : tr`Your selected point is ${metres} m from the ${item.role === "start" ? t("starting") : t("finishing")} point used by this route for ${profileLabel}. The dashed connector only explains the displacement; it is not part of the route.`);
    const actions = document.createElement("div"); actions.className = "endpoint-adjustment-actions";
    for (const [key, label, callback] of [["show", t("Show adjustment"), onShow], ["move", tr`Move ${item.endpoint === "start" ? t("Start") : t("End")}`, onMove], ["use", t("Use routed point"), onUse]]) {
      const button = document.createElement("button"); button.type = "button"; button.textContent = label;
      button.dataset.adjustmentAction = `${item.role}-${key}`; button.disabled = key !== "show" && disabled;
      button.addEventListener("click", () => callback(item)); actions.append(button);
    }
    details.append(title, text, actions); root.append(details);
  }
  if (focused) root.querySelector(`[data-adjustment-action="${focused}"]`)?.focus({ preventScroll: true });
}
