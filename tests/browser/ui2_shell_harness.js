import { initializeAppShell } from "../../src/sugarglider/web/static/app_shell.js";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
const settle = () => new Promise((resolve) => setTimeout(resolve, 80));

// Real application markup/CSS with only the presentation controller. Planning
// integration is covered separately by the endpoint, profile and real-map tests.
export async function runShellHarness() {
  const response = await fetch("../../src/sugarglider/web/static/index.html");
  assert(response.ok, "application markup available");
  const markup = new DOMParser().parseFromString(await response.text(), "text/html");
  markup.querySelectorAll("script, link[rel=manifest]").forEach((node) => node.remove());
  markup.querySelectorAll("link[href]").forEach((link) => {
    link.href = new URL(`../../src/sugarglider/web${link.getAttribute("href")}`, location.href).href;
  });
  markup.querySelectorAll('img[src^="/static/"]').forEach((image) => {
    image.src = new URL(`../../src/sugarglider/web${image.getAttribute("src")}`, location.href).href;
  });
  const scenarios = [];
  for (const [width, height, scale] of [
    [360, 800, 1], [390, 844, 1], [412, 915, 1],
    [840, 800, 1], [841, 800, 1], [1280, 800, 1], [1440, 900, 1],
    [390, 420, 1], [360, 640, 2],
  ]) {
    const frame = globalThis.document.createElement("iframe");
    frame.title = `Workspace ${width} × ${height} at ${scale}x text`;
    frame.style.cssText = `width:${width}px;height:${height}px;border:0;display:block;`;
    const loaded = new Promise((resolve) => frame.addEventListener("load", resolve, { once: true }));
    frame.srcdoc = `<!doctype html>${markup.documentElement.outerHTML}`;
    globalThis.document.body.append(frame);
    await loaded;
    const document = frame.contentDocument;
    const window = frame.contentWindow;
    document.documentElement.style.fontSize = `${16 * scale}px`;
    const byId = (id) => document.getElementById(id);
    const nav = (view) => document.querySelector(`[data-shell-view="${view}"]`);
    const key = () => document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    const rect = (selector) => document.querySelector(selector).getBoundingClientRect();
    const canvas = document.createElement("canvas");
    canvas.className = "maplibregl-canvas";
    canvas.tabIndex = 0;
    byId("map").append(canvas);
    let resizes = 0;
    const shell = initializeAppShell({ document, resizeMap: () => { resizes += 1; } });
    try {
      await settle();
      assert(byId("planner").dataset.view === (width <= 840 ? "map" : "plan"), "responsive initial workspace");
      assert(document.documentElement.scrollWidth <= width + 1, `no horizontal document overflow at ${width}x${height} / ${scale}x: ${document.documentElement.scrollWidth}`);
      assert(document.body.scrollHeight <= height + 1, "workspace fits viewport");
      assert(rect(".map-panel").height > 100, "map has usable initial height");
      if (width > 840) assert(rect(".map-panel").width > width * .5, "desktop map dominates width");
      byId("target-distance").value = "17";
      nav("plan").click();
      await settle();
      assert(!byId("planning-panel").hidden && byId("results-panel").hidden, "Plan reveals only planning panel");
      assert(document.activeElement.id === "controls-title", "Plan moves focus to heading");
      assert(rect(".map-panel").height > 80, "map context remains while planning");
      assert(byId("planning-panel").scrollHeight > byId("planning-panel").clientHeight, "long form has own scroll area");
      byId("planning-panel").scrollTop = 250;
      const scroll = byId("planning-panel").scrollTop;
      nav("routes").click();
      await settle();
      assert(byId("planning-panel").hidden && !byId("results-panel").hidden, "Routes reveals only results");
      assert(document.activeElement.id === "candidates-title", "Routes moves focus to heading");
      assert(nav("routes").getAttribute("aria-pressed") === "true", "selected workspace exposed to assistive technology");
      nav("plan").click();
      assert(byId("target-distance").value === "17", "changing workspace preserves form values");
      assert(byId("planning-panel").scrollTop === scroll, "changing workspace preserves scroll position");
      byId("target-distance").focus();
      shell.show("routes");
      assert(document.activeElement.id === "candidates-title", "automatic results reveal never strands focus in hidden Plan");
      assert(byId("candidate-list").compareDocumentPosition(byId("metrics-title")) & window.Node.DOCUMENT_POSITION_FOLLOWING, "keyboard order follows visible candidates then details");
      shell.show("map", { focus: true });
      assert(document.activeElement === canvas, "map editing can focus canvas");
      if (width <= 840) {
        assert(byId("planning-panel").hidden && byId("results-panel").hidden, "Map hides both task panels");
        for (const view of ["map", "plan", "routes"]) assert(nav(view).getBoundingClientRect().height >= 44, "comfortable navigation hit targets");
      }
      scenarios.push(`layout_navigation_state_${width}_${height}_${scale}x`);

      document.querySelector(".skip-link").click();
      assert(!byId("planning-panel").hidden && document.activeElement.id === "controls-title", "skip link opens Plan and focuses its heading");
      const tools = document.querySelector(".header-tools");
      tools.open = true;
      await settle();
      assert(rect(".header-tools-menu").right <= width + 1, "Tools fits viewport at enlarged text sizes");
      assert(rect("#import-gpx").width > 100, "Tools uses one readable column");
      byId("offline-regions").classList.remove("hidden");
      byId("offline-regions").open = true;
      byId("regional-refresh").click();
      assert(tools.open, "region actions keep their setup menu open");
      byId("planning-region").scrollIntoView({ block: "nearest" });
      assert(rect("#planning-region").width > 100, "regional selection remains accessible inside Tools");
      byId("offline-regions").classList.add("hidden");
      key();
      assert(!tools.open && document.activeElement === tools.querySelector("summary"), "Escape closes Tools and restores focus");
      assert(!byId("planning-panel").hidden, "closing Tools does not also dismiss Plan");
      byId("trail-profile-dialog").showModal();
      key();
      assert(!byId("planning-panel").hidden, "dialog owns Escape before workspace");
      byId("trail-profile-dialog").close();
      key();
      if (width <= 840) assert(byId("planner").dataset.view === "map" && document.activeElement === nav("map"), "Escape dismisses phone panel and restores navigation focus");
      shell.reveal("#target-distance");
      await settle();
      assert(!byId("planning-panel").hidden, "reveal exposes hidden planning content");
      shell.reveal("#candidate-list");
      await settle();
      assert(!byId("results-panel").hidden, "reveal exposes hidden results content");
      scenarios.push(`focus_escape_reveal_${width}_${height}_${scale}x`);

      for (const [button, input] of [["import-gpx", "gpx-file"], ["import-plan", "request-file"]]) {
        let clicked = 0;
        byId(input).addEventListener("click", (event) => { event.preventDefault(); clicked += 1; });
        assert(byId(button).tagName === "BUTTON", "file chooser trigger supports native keyboard activation");
        byId(button).click();
        assert(clicked === 1, "file chooser dispatched once");
      }
      document.body.classList.add("outing-mode");
      await settle();
      assert(!byId("results-panel").hidden && !byId("planning-panel").hidden, "outing content restored to independent layout");
      assert(window.getComputedStyle(document.querySelector(".workspace-navigation")).display === "none", "outing has no planner workspace navigation");
      document.body.classList.remove("outing-mode");
      await settle();
      assert(!byId("results-panel").hidden, "returning to planner restores last workspace");
      const settledResizes = resizes;
      await settle();
      assert(resizes === settledResizes, "idle shell causes no continuous map resize loop");
      assert(resizes > 0 && resizes < 30, "map resizing follows bounded layout changes");
      scenarios.push(`utilities_outing_resize_${width}_${height}_${scale}x`);

      if (width === 390 && height === 844) {
        shell.show("map");
        frame.style.width = "1280px";
        await settle();
        assert(byId("planner").dataset.view === "plan", "phone Map becomes desktop Plan beside map");
        frame.style.width = "390px";
        await settle();
        assert(byId("planner").dataset.view === "plan", "resizing retains active Plan rather than discarding context");
        scenarios.push("breakpoint_preserves_task");
      }
    } finally {
      shell.destroy();
      assert(!document.body.classList.contains("ui-shell") && !byId("planning-panel").hidden, "destroy restores document layout");
      frame.remove();
    }
  }
  return scenarios;
}
