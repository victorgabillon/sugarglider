const VIEWPORTS = Object.freeze([360, 390, 412, 600, 768, 1280, 1440]);
const PHONE_MAX = 600;

export async function runPr29UxPolishHarness() {
  const source = await loadApplicationMarkup();
  const scenarios = [];
  for (const width of VIEWPORTS) {
    const frame = await applicationFrame(source, width);
    try {
      shellScenario(frame, width);
      scenarios.push(`shell_${width}`);
      candidateScenario(frame, width);
      scenarios.push(`candidate_${width}`);
      savedRouteScenario(frame, width);
      scenarios.push(`saved_route_${width}`);
      outingReceiptScenario(frame, width);
      scenarios.push(`outing_receipt_${width}`);
      liveOutingScenario(frame, width);
      scenarios.push(`live_outing_${width}`);
    } finally {
      frame.remove();
    }
  }
  return scenarios;
}

async function loadApplicationMarkup() {
  const applicationUrl = new URL(
    "../../src/sugarglider/web/static/index.html",
    window.location.href,
  );
  const response = await fetch(applicationUrl);
  assert(response.ok, "application markup loads");
  const parsed = new DOMParser().parseFromString(await response.text(), "text/html");
  parsed.querySelectorAll("script, link[rel='manifest']").forEach((node) => node.remove());
  parsed.querySelectorAll("link[href*='maplibre-gl.css']").forEach((node) => node.remove());
  const stylesheet = parsed.querySelector("link[href='/static/styles.css']");
  assert(stylesheet, "application stylesheet link remains present");
  stylesheet.href = new URL(
    "../../src/sugarglider/web/static/styles.css",
    window.location.href,
  ).href;
  return `<!doctype html>${parsed.documentElement.outerHTML}`;
}

function applicationFrame(source, width) {
  return new Promise((resolve, reject) => {
    const frame = document.createElement("iframe");
    frame.title = `Sugarglider PR29 fixture at ${width}px`;
    frame.style.width = `${width}px`;
    frame.style.height = "900px";
    frame.style.border = "0";
    frame.addEventListener("load", () => {
      try {
        installCandidateFixture(frame.contentDocument);
        resolve(frame);
      } catch (error) {
        reject(error);
      }
    }, { once: true });
    frame.srcdoc = source;
    document.body.append(frame);
  });
}

function installCandidateFixture(document) {
  byId(document, "candidate-list").innerHTML = `
    <article class="candidate-card selected recommended">
      <button class="candidate-select" type="button" aria-pressed="true">
        <span class="candidate-choice-heading"><strong>Your route</strong><strong>20.4 km</strong></span>
        <span class="candidate-badges"><span class="badge recommended">Recommended</span></span>
        <span class="candidate-choice-metrics">
          <span><small>Nature</small><strong>78 / 100</strong></span>
          <span><small>Trail-like</small><strong>64%</strong></span>
          <span><small>Repeated</small><strong>6%</strong></span>
        </span>
        <span class="candidate-choice-action">Selected route</span>
      </button>
      <ul class="card-warnings"><li>Some route detail remains unknown</li></ul>
      <details class="candidate-route-details">
        <summary>Route details</summary>
        <div class="candidate-detail-content">Exact route metrics remain available.</div>
      </details>
    </article>`;
}

function shellScenario(frame, width) {
  const document = fixtureDocument(frame);
  resetPanels(document);
  const nav = document.querySelector(".topbar nav");
  const tools = document.querySelector(".header-tools");
  const layers = document.querySelector(".map-tools");
  const advanced = document.querySelector(".route-advanced");
  assert(byId(document, "generate-top").parentElement === nav, "Generate stays top-level");
  assert(byId(document, "save-route").parentElement === nav, "Save stays contextual and top-level");
  assert(document.querySelector("label[for='gpx-file']").parentElement === nav, "GPX import stays top-level");
  assert(byId(document, "export-plan").closest(".header-tools") === tools, "JSON export moves under Tools");
  assert(byId(document, "request-file").closest(".header-tools") === tools, "JSON import moves under Tools");
  assert(!tools.open && !layers.open && !advanced.open, "secondary controls start collapsed");
  assert(byId(document, "show-all").checked, "alternative-layer default remains on");
  assert(!byId(document, "show-nature").checked, "nature-layer default remains off");
  assert(byId(document, "show-direction").checked, "direction-layer default remains on");
  tools.open = true;
  layers.open = true;
  advanced.closest(".control-section").open = true;
  advanced.open = true;
  assertVisible(byId(document, "export-plan"), "Tools contents are reachable");
  assertVisible(byId(document, "show-dropped-requested-radii"), "all map layers are reachable");
  assertVisible(byId(document, "path-selection-mode"), "advanced preferences are reachable");
  assertNoPageOverflow(frame, `shell ${width}px`);
  if (width <= PHONE_MAX) {
    assertHitArea(byId(document, "generate-top"), 48, `Generate ${width}px`);
    assertHitArea(tools.querySelector(":scope > summary"), 44, `Tools ${width}px`);
    assertHitArea(layers.querySelector(":scope > summary"), 44, `Layers ${width}px`);
  }
}

function candidateScenario(frame, width) {
  const document = fixtureDocument(frame);
  resetPanels(document);
  const card = document.querySelector(".candidate-card");
  const details = card.querySelector(".candidate-route-details");
  assertVisible(card.querySelector(".candidate-choice-metrics"), "choice metrics stay visible");
  assertVisible(card.querySelector(".candidate-choice-action"), "selection action stays visible");
  assertVisible(card.querySelector(".card-warnings"), "warnings stay visible");
  assert(!details.open, "technical route detail starts collapsed");
  details.open = true;
  assertVisible(card.querySelector(".candidate-detail-content"), "route detail remains reachable");
  assertNoPageOverflow(frame, `candidate ${width}px`);
}

function savedRouteScenario(frame, width) {
  const document = fixtureDocument(frame);
  resetPanels(document);
  reveal(document, "saved-route-panel");
  reveal(document, "show-create-outing");
  const panel = byId(document, "saved-route-panel");
  const more = panel.querySelector(".action-disclosure");
  assertVisible(byId(document, "copy-saved-route-link"), "Copy link stays visible");
  assertVisible(byId(document, "show-create-outing"), "Create outing stays visible");
  assert(byId(document, "show-create-outing").classList.contains("primary"), "Create outing is primary");
  assert(byId(document, "delete-saved-route").closest(".action-disclosure") === more, "destructive action is secondary");
  more.open = true;
  assertNoPageOverflow(frame, `saved route ${width}px`);
}

function outingReceiptScenario(frame, width) {
  const document = fixtureDocument(frame);
  resetPanels(document);
  reveal(document, "outing-receipt-panel");
  reveal(document, "open-outing-live-here");
  const panel = byId(document, "outing-receipt-panel");
  const more = panel.querySelector(".action-disclosure");
  assertVisible(byId(document, "copy-outing-invite-link"), "Copy invitation stays visible");
  assertVisible(byId(document, "open-outing-live-here"), "Open live outing stays visible");
  assert(byId(document, "outing-public-link").closest(".action-disclosure") === more, "public link is secondary");
  more.open = true;
  assertNoPageOverflow(frame, `outing receipt ${width}px`);
}

function liveOutingScenario(frame, width) {
  const document = fixtureDocument(frame);
  resetPanels(document);
  document.body.classList.add("outing-mode");
  reveal(document, "outing-view-panel");
  reveal(document, "outing-live-panel");
  reveal(document, "outing-live-own-controls");
  const title = byId(document, "outing-view-title");
  const eyebrow = title.parentElement.querySelector(".eyebrow");
  assert(title.compareDocumentPosition(eyebrow) & Node.DOCUMENT_POSITION_FOLLOWING, "outing title leads its context");
  assert(byId(document, "stop-outing-live-sharing").classList.contains("danger"), "Stop is visibly destructive");
  assert(byId(document, "outing-live-sharing-disclosure").closest(".sharing-details"), "technical sharing caveats are disclosed");
  document.querySelector(".outing-secondary-actions").open = true;
  document.querySelector(".sharing-details").open = true;
  assertNoPageOverflow(frame, `live outing ${width}px`);
}

function resetPanels(document) {
  document.body.classList.remove("outing-mode");
  for (const id of ["saved-route-panel", "outing-receipt-panel", "outing-view-panel", "outing-live-panel", "outing-live-own-controls"]) {
    byId(document, id).classList.add("hidden");
  }
  document.querySelectorAll("details").forEach((details) => details.open = false);
}

function assertVisible(element, message) {
  const rect = element.getBoundingClientRect();
  assert(rect.width > 0 && rect.height > 0, message);
}

function assertNoPageOverflow(frame, label) {
  const document = fixtureDocument(frame);
  assert(document.documentElement.scrollWidth <= frame.contentWindow.innerWidth + 1, `${label} has no horizontal overflow`);
}

function assertHitArea(element, minimum, label) {
  assert(element.getBoundingClientRect().height >= minimum, `${label} has a ${minimum}px hit area`);
}

function reveal(document, id) {
  byId(document, id).classList.remove("hidden");
}

function fixtureDocument(frame) {
  const document = frame.contentDocument;
  assert(document, "fixture document remains available");
  return document;
}

function byId(document, id) {
  const element = document.getElementById(id);
  assert(element, `#${id} remains present`);
  return element;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
