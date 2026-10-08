// Volatile acquisition UI. Only explicit result selection hands name/lat/lon to editing.
import { validateLocationQuery } from "./location_search.js";
export function initializeLocationSearchDialog({ root, search, config, canEdit, onSelect, restoreFocus }) {
  const element = name => root.querySelector(`#location-search-${name}`);
  let controller = null, epoch = 0, target = null, launcher = null;
  function invalidate() { epoch += 1; controller?.abort(); controller = null; }
  function close() { invalidate(); root.close(); }
  function addText(parent, tag, value) { const node = document.createElement(tag); node.textContent = value; parent.append(node); return node; }
  function rows(group, results) {
    const list = element(group); list.replaceChildren();
    for (const result of results) {
      const item = document.createElement("li"), button = document.createElement("button"); button.type = "button";
      addText(button, "strong", result.name); addText(button, "span", result.secondaryLabel);
      addText(button, "small", `${result.lat.toFixed(6)}, ${result.lon.toFixed(6)}`);
      button.addEventListener("click", () => {
        if (!canEdit()) { element("error").textContent = "This route cannot be edited right now."; return; }
        try {
          if (onSelect(target, { name: result.name, lat: result.lat, lon: result.lon }) !== false) close();
        } catch (error) { element("error").textContent = error.message; }
      });
      item.append(button); list.append(item);
    }
  }
  function announce(message) { element("status").textContent = message; }
  function focusResult() { (element("local").querySelector("button") ?? element("online").querySelector("button"))?.focus(); }
  element("form").addEventListener("submit", async event => {
    event.preventDefault();
    let query;
    try { query = validateLocationQuery(element("query").value); }
    catch (error) { element("error").textContent = error.message; element("query").focus(); return; }
    invalidate(); controller = new AbortController(); const owned = epoch;
    const current = () => root.open && owned === epoch;
    rows("local", []); rows("online", []); element("error").textContent = "";
    element("local-message").textContent = "Checking installed mapped places…";
    element("online-message").textContent = "";
    announce("Searching…"); element("results").setAttribute("aria-busy", "true");
    try {
      const response = await search(query, { signal: controller.signal, onLocal: response => {
        if (!current()) return;
        rows("local", response.results); element("local-message").textContent = response.message;
        element("online-message").textContent = "Searching online…";
      } });
      if (!current()) return;
      element("retrieved").textContent = response.remote.length ? `Retrieved ${new Date().toISOString().slice(0, 10)}` : "";
      rows("online", response.remote); element("online-message").textContent = response.remoteMessage;
      if (response.remoteMessage && response.remote.length === 0 && !response.remoteMessage.startsWith("No online results")) {
        element("error").textContent = response.remoteMessage; element("online-message").textContent = "";
      }
      announce(`${response.local.length + response.remote.length} results. Choose one to ${target ? "move this point" : "add a point"}.`);
      if (root.contains(document.activeElement) && [element("query"), element("submit")].includes(document.activeElement)) focusResult();
    } catch { if (current()) announce("Search cancelled."); }
    finally { if (current()) element("results").setAttribute("aria-busy", "false"); }
  });
  element("close").addEventListener("click", close);
  root.addEventListener("cancel", invalidate);
  root.addEventListener("close", () => {
    if (root.open) return; invalidate(); target = null;
    restoreFocus?.(launcher); launcher = null;
  });
  element("results").addEventListener("keydown", event => {
    if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
    const buttons = [...element("results").querySelectorAll("button")];
    const index = buttons.indexOf(document.activeElement); if (index < 0) return;
    event.preventDefault(); buttons[(index + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length]?.focus();
  });
  return Object.freeze({ open(nextTarget = null, trigger = document.activeElement) {
    if (!canEdit()) return;
    invalidate(); target = nextTarget; launcher = trigger;
    element("title").textContent = nextTarget ? "Move point · Search place or address" : "Search place or address";
    element("query").value = ""; element("error").textContent = ""; announce("");
    rows("local", []); rows("online", []); element("local-message").textContent = "Mapped places in the installed region; not a street-address database.";
    element("online-message").textContent = ""; element("results").setAttribute("aria-busy", "false");
    const settings = config(); element("coverage").textContent = settings?.coverage ?? "Online search is unavailable.";
    const attribution = element("attribution"); attribution.textContent = settings?.attribution ?? "";
    attribution.removeAttribute("href");
    try { const url = new URL(settings?.attribution_url); if (url.protocol === "https:") attribution.href = url.href; } catch { /* Unavailable config. */ }
    element("retrieved").textContent = "";
    if (!root.open) root.showModal(); element("query").focus();
  } });
}
