// Presentation only: changing workspace never mutates a plan, map selection or storage.
export function initializeAppShell({ document = globalThis.document, resizeMap = () => {} } = {}) {
  const window = document.defaultView;
  const planner = document.getElementById("planner");
  const navigation = document.querySelector(".workspace-navigation");
  const controls = document.getElementById("planning-panel");
  const results = document.getElementById("results-panel");
  const mapPanel = document.querySelector(".map-panel");
  if (!planner || !navigation || !controls || !results || !mapPanel) return { show() {}, reveal() {} };
  const mobile = window.matchMedia("(max-width: 840px)");
  const buttons = [...navigation.querySelectorAll("[data-shell-view]")];
  let current = mobile.matches ? "map" : "plan";
  let resizeFrame = null;
  let previousSize = null;
  const listeners = new window.AbortController();
  const header = document.querySelector(".topbar");
  const headerHome = header && document.createComment("Map toolbar returns here outside the mobile Map workspace");
  header?.before(headerHome);
  function placeToolbar() {
    const overlay = mobile.matches && current === "map" && !document.body.classList.contains("outing-mode");
    document.body.classList.toggle("mobile-map-view", overlay);
    if (header && headerHome) {
      if (overlay && header.parentElement !== mapPanel) mapPanel.prepend(header);
      else if (!overlay && header.previousSibling !== headerHome) headerHome.after(header);
    }
  }
  function resized() {
    if (resizeFrame !== null) window.cancelAnimationFrame(resizeFrame);
    resizeFrame = window.requestAnimationFrame(() => {
      resizeFrame = null;
      const size = [mapPanel.clientWidth, mapPanel.clientHeight];
      const layoutChanged = previousSize !== null && size.some((value, index) => value !== previousSize[index]);
      previousSize = size;
      resizeMap({ layoutChanged, view: current });
    });
  }
  function show(view, { focus = false } = {}) {
    if (!["map", "plan", "routes"].includes(view) || document.body.classList.contains("outing-mode")) return;
    const focusMap = view === "map";
    current = !mobile.matches && focusMap ? (current === "routes" ? "routes" : "plan") : view;
    placeToolbar();
    const hiddenFocus = (current !== "plan" && controls.contains(document.activeElement))
      || (current !== "routes" && results.contains(document.activeElement));
    planner.dataset.view = current;
    controls.hidden = current !== "plan";
    results.hidden = current !== "routes";
    buttons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.shellView === current)));
    if (focus || hiddenFocus) {
      const target = focusMap ? document.querySelector(".maplibregl-canvas")
        : document.getElementById(current === "plan" ? "controls-title" : "candidates-title");
      target?.focus({ preventScroll: true });
    }
    resized();
  }
  function reveal(selector) {
    const target = document.querySelector(selector);
    if (!target) return;
    if (controls.contains(target)) show("plan");
    else if (results.contains(target)) show("routes");
    window.requestAnimationFrame(() => target.scrollIntoView({ block: "nearest" }));
  }
  buttons.forEach((button) => button.addEventListener("click", () => show(button.dataset.shellView, { focus: true }), { signal: listeners.signal }));
  document.querySelector(".skip-link")?.addEventListener("click", (event) => {
    event.preventDefault(); show("plan", { focus: true });
  }, { signal: listeners.signal });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || event.defaultPrevented || document.querySelector("dialog[open]")) return;
    const menu = document.querySelector(".header-tools[open]");
    if (menu) { menu.open = false; menu.querySelector("summary")?.focus(); event.preventDefault(); return; }
    if (mobile.matches && current !== "map") {
      show("map"); buttons.find((button) => button.dataset.shellView === "map")?.focus(); event.preventDefault();
    }
  }, { signal: listeners.signal });
  for (const [button, input] of [["import-gpx", "gpx-file"], ["import-plan", "request-file"]]) {
    document.getElementById(button)?.addEventListener("click", () => document.getElementById(input)?.click(), { signal: listeners.signal });
  }
  const tools = document.querySelector(".header-tools");
  tools?.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button || button.closest("#offline-regions, .map-tools")) return;
    tools.open = false;
    if (tools.contains(document.activeElement)) tools.querySelector("summary")?.focus();
  }, { signal: listeners.signal });
  const onBreakpoint = () => show(current);
  mobile.addEventListener("change", onBreakpoint);
  const observer = new window.ResizeObserver(resized);
  observer.observe(mapPanel);
  // Existing outing pages retain their independent, tested layout and capabilities.
  let outingMode = document.body.classList.contains("outing-mode");
  const modeObserver = new window.MutationObserver(() => {
    const next = document.body.classList.contains("outing-mode");
    if (next === outingMode) return;
    outingMode = next;
    if (outingMode) { placeToolbar(); controls.hidden = false; results.hidden = false; }
    else show(current);
  });
  modeObserver.observe(document.body, { attributes: true, attributeFilter: ["class"] });
  document.body.classList.add("ui-shell");
  navigation.hidden = false;
  show(current);
  return { show, reveal, destroy() {
    listeners.abort(); observer.disconnect(); modeObserver.disconnect(); mobile.removeEventListener("change", onBreakpoint);
    if (resizeFrame !== null) window.cancelAnimationFrame(resizeFrame);
    controls.hidden = false; results.hidden = false; navigation.hidden = true;
    document.body.classList.remove("ui-shell");
    document.body.classList.remove("mobile-map-view");
    if (headerHome) { headerHome.after(header); headerHome.remove(); }
  } };
}
