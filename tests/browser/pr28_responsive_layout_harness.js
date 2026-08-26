const VIEWPORTS = Object.freeze([360, 390, 412, 600, 768, 1280, 1440]);
const MOBILE_STACK_MAX = 840;
const PHONE_MAX = 600;

export async function runPr28ResponsiveLayoutHarness() {
  const source = await loadApplicationMarkup();
  const scenarios = [];

  for (const width of VIEWPORTS) {
    const frame = await applicationFrame(source, width);
    try {
      plannerScenario(frame, width);
      scenarios.push(`planner_${width}`);
      savedRouteScenario(frame, width);
      scenarios.push(`saved_route_${width}`);
      outingCreatedScenario(frame, width);
      scenarios.push(`outing_created_${width}`);
      publicOutingScenario(frame, width, false);
      scenarios.push(`public_outing_${width}`);
      publicOutingScenario(frame, width, true);
      scenarios.push(`native_live_outing_${width}`);
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
    frame.title = `Sugarglider responsive fixture at ${width}px`;
    frame.style.width = `${width}px`;
    frame.style.height = "900px";
    frame.style.border = "0";
    frame.addEventListener("load", () => {
      try {
        const document = frame.contentDocument;
        assert(document, `fixture document exists at ${width}px`);
        installFixtureContent(document);
        resolve(frame);
      } catch (error) {
        reject(error);
      }
    }, { once: true });
    frame.srcdoc = source;
    document.body.append(frame);
  });
}

function installFixtureContent(document) {
  const candidateList = byId(document, "candidate-list");
  candidateList.innerHTML = `
    <article class="candidate-card selected recommended">
      <button class="candidate-select" type="button">
        <span class="candidate-title"><strong>Recommended route</strong><span>20.4 km</span></span>
        <span class="candidate-badges"><span class="badge recommended">Recommended</span></span>
        <span class="candidate-key-metrics"><span>Repeated trail</span><strong>1.2 km</strong></span>
      </button>
    </article>
    <article class="candidate-card">
      <button class="candidate-select" type="button">
        <span class="candidate-title"><strong>Alternative route</strong><span>19.8 km</span></span>
      </button>
    </article>`;

  const participantCards = byId(document, "outing-participant-cards");
  participantCards.innerHTML = `
    <button class="outing-participant-card selected" type="button">
      <span class="outing-participant-heading"><i class="outing-participant-swatch"></i><strong>Fairphone walker</strong></span>
      <span>Participant 1</span>
      <span>A long independent immutable participant route name</span>
      <span>Hike · Loop · 20.4 km</span>
      <span class="outing-participant-live fresh">Live</span>
      <span class="outing-participant-live-facts">Accuracy ±12 m · updated just now</span>
    </button>`;
  byId(document, "outing-view-title").textContent = "Shared forest outing";
  byId(document, "outing-view-summary").textContent = (
    "1 of 8 participants · available until tomorrow afternoon"
  );
  for (const id of [
    "saved-route-link",
    "outing-public-link",
    "outing-invite-link",
  ]) {
    byId(document, id).value = (
      "https://example.test/unlisted/sugarglider-route-with-a-long-stable-identifier"
    );
  }
}

function plannerScenario(frame, width) {
  const document = fixtureDocument(frame);
  resetState(document);
  const planner = byId(document, "planner");
  const mapPanel = document.querySelector(".map-panel");
  const tools = document.querySelector(".map-tools");
  const empty = document.querySelector(".map-empty-state");

  assertNoPageOverflow(frame, `planner ${width}px`);
  assertInside(tools, mapPanel, `map tools stay inside map at ${width}px`);
  assertInside(empty, mapPanel, `map onboarding stays inside map at ${width}px`);
  assert(
    document.querySelectorAll(".candidate-card").length === 2,
    `candidate actions remain present at ${width}px`,
  );

  if (width <= MOBILE_STACK_MAX) {
    const style = frame.contentWindow.getComputedStyle(planner);
    equal(style.display, "flex", `planner stacks at ${width}px`);
    equal(style.flexDirection, "column", `planner stack is vertical at ${width}px`);
  }
  if (width <= PHONE_MAX) {
    const generate = byId(document, "generate-top").getBoundingClientRect();
    const importGpx = document.querySelector("label[for='gpx-file']").getBoundingClientRect();
    const save = byId(document, "save-route").getBoundingClientRect();
    const utility = byId(document, "export-plan").getBoundingClientRect();
    assert(generate.top < utility.top, `Generate precedes utilities at ${width}px`);
    assert(generate.width >= viewportWidth(frame) * .9, `Generate is full-width at ${width}px`);
    assert(generate.height >= 48, `Generate has a primary hit area at ${width}px`);
    assert(importGpx.height >= 44 && save.height >= 44, `important header actions are touchable at ${width}px`);
    const card = document.querySelector(".candidate-card").getBoundingClientRect();
    assert(card.width <= viewportWidth(frame) - 16, `candidate card fits its scroller at ${width}px`);
  }
}

function savedRouteScenario(frame, width) {
  const document = fixtureDocument(frame);
  resetState(document);
  reveal(document, "saved-route-panel");
  for (const id of [
    "use-saved-route",
    "delete-saved-route",
    "dismiss-saved-route",
    "show-create-outing",
    "save-saved-route-offline",
  ]) reveal(document, id);

  assertNoPageOverflow(frame, `saved route ${width}px`);
  assertReasonablePanelWidth(frame, byId(document, "saved-route-panel"), `saved route ${width}px`);
  assertWithinViewport(frame, byId(document, "saved-route-link"), `saved route link ${width}px`);
  assert(
    byId(document, "show-create-outing").classList.contains("primary"),
    `Create outing retains primary hierarchy at ${width}px`,
  );
  if (width <= PHONE_MAX) assertHitArea(byId(document, "copy-saved-route-link"), 44, `Copy link ${width}px`);
}

function outingCreatedScenario(frame, width) {
  const document = fixtureDocument(frame);
  resetState(document);
  reveal(document, "outing-receipt-panel");
  reveal(document, "open-outing-live-here");

  assertNoPageOverflow(frame, `outing created ${width}px`);
  assertReasonablePanelWidth(frame, byId(document, "outing-receipt-panel"), `outing created ${width}px`);
  assertWithinViewport(frame, byId(document, "outing-public-link"), `public outing link ${width}px`);
  assertWithinViewport(frame, byId(document, "outing-invite-link"), `invitation link ${width}px`);
  if (width <= PHONE_MAX) {
    const primary = byId(document, "open-outing-live-here").getBoundingClientRect();
    assert(primary.height >= 48, `Open live outing is touchable at ${width}px`);
    assert(primary.width >= viewportWidth(frame) * .75, `Open live outing is prominent at ${width}px`);
  }
}

function publicOutingScenario(frame, width, native) {
  const document = fixtureDocument(frame);
  resetState(document);
  document.body.classList.add("outing-mode");
  reveal(document, "outing-view-panel");
  reveal(document, "outing-live-panel");
  reveal(document, "save-outing-offline");
  reveal(document, "outing-remember-actions");
  if (native) {
    reveal(document, "outing-live-own-controls");
    const start = byId(document, "start-outing-live-sharing");
    start.textContent = "Start Android background sharing";
    start.disabled = false;
  }

  const planner = byId(document, "planner");
  const map = document.querySelector(".map-panel").getBoundingClientRect();
  const outing = byId(document, "outing-view-panel").getBoundingClientRect();
  const copy = byId(document, "outing-view-panel").querySelector(".notice-copy").getBoundingClientRect();
  const metrics = document.querySelector(".metrics").getBoundingClientRect();
  const title = byId(document, "outing-view-title").getBoundingClientRect();

  assertNoPageOverflow(frame, `${native ? "native live" : "public"} outing ${width}px`);
  assertReasonablePanelWidth(frame, byId(document, "outing-view-panel"), `outing ${width}px`);
  assert(copy.width >= outing.width * .85, `outing copy uses its panel width at ${width}px`);
  assert(title.width >= Math.min(240, viewportWidth(frame) * .65), `outing title has readable width at ${width}px`);
  assertWithinViewport(frame, byId(document, "save-outing-offline"), `offline action ${width}px`);

  if (width <= MOBILE_STACK_MAX) {
    const style = frame.contentWindow.getComputedStyle(planner);
    equal(style.display, "flex", `outing planner stacks at ${width}px`);
    equal(style.flexDirection, "column", `outing planner is one column at ${width}px`);
    assert(map.bottom <= outing.top + 1, `map precedes outing content at ${width}px`);
    assert(outing.bottom <= metrics.top + 1, `outing content precedes details at ${width}px`);
  } else {
    const style = frame.contentWindow.getComputedStyle(planner);
    equal(style.display, "grid", `outing keeps desktop dashboard at ${width}px`);
    assert(style.gridTemplateAreas.includes("outing outing"), `outing spans desktop dashboard at ${width}px`);
    assert(outing.bottom <= map.top + 1, `desktop outing summary precedes map at ${width}px`);
  }

  if (native && width <= PHONE_MAX) {
    const start = byId(document, "start-outing-live-sharing").getBoundingClientRect();
    assert(start.height >= 48, `native Start has primary hit area at ${width}px`);
    assert(start.width >= viewportWidth(frame) * .75, `native Start uses mobile width at ${width}px`);
  }
}

function resetState(document) {
  document.body.classList.remove("outing-mode");
  for (const id of [
    "saved-route-panel",
    "outing-receipt-panel",
    "outing-view-panel",
    "outing-live-panel",
    "outing-live-own-controls",
    "outing-remember-actions",
  ]) byId(document, id).classList.add("hidden");
  byId(document, "start-outing-live-sharing").textContent = "Start sharing";
}

function assertNoPageOverflow(frame, label) {
  const document = fixtureDocument(frame);
  assert(
    document.documentElement.scrollWidth <= frame.contentWindow.innerWidth + 1,
    `${label} has no horizontal page overflow`,
  );
}

function assertReasonablePanelWidth(frame, panel, label) {
  const width = panel.getBoundingClientRect().width;
  assert(width >= viewportWidth(frame) * .85, `${label} uses the viewport width`);
}

function assertWithinViewport(frame, element, label) {
  const rect = element.getBoundingClientRect();
  assert(rect.left >= -1, `${label} does not escape left`);
  assert(rect.right <= viewportWidth(frame) + 1, `${label} does not escape right`);
}

function viewportWidth(frame) {
  return fixtureDocument(frame).documentElement.clientWidth;
}

function assertInside(element, container, label) {
  const elementRect = element.getBoundingClientRect();
  const containerRect = container.getBoundingClientRect();
  assert(elementRect.left >= containerRect.left - 1, `${label}: left edge`);
  assert(elementRect.right <= containerRect.right + 1, `${label}: right edge`);
  assert(elementRect.top >= containerRect.top - 1, `${label}: top edge`);
  assert(elementRect.bottom <= containerRect.bottom + 1, `${label}: bottom edge`);
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

function equal(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
  }
}
