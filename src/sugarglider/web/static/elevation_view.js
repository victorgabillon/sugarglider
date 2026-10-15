import { elevationDistanceLabel, elevationPositionAtDistance, elevationSampleIndex, projectElevationProfile } from "./elevation_profile.js";

const SVG = "http://www.w3.org/2000/svg";
const metres = value => value === null ? "Unavailable" : `${Math.round(value)} m`;

export function createElevationView({root, onPosition = () => {}, onShowMap = () => {},
  onCancel = () => {}, onRetry = () => {}, isCurrent = () => false} = {}) {
  if (!root) return {render() {}, destroy() {}, diagnostics:() => ({})};
  const document = root.ownerDocument, window = document.defaultView;
  const find = selector => root.querySelector(selector);
  const status = find("#route-elevation-status"), cancel = find("#cancel-route-elevation");
  const retry = find("#retry-route-elevation"), showMap = find("#show-elevation-on-map");
  const clearPosition = find("#clear-elevation-position"), host = find("[data-elevation-chart]");
  const summary = find("[data-elevation-summary]"), note = find("[data-elevation-note]");
  const observed = find("[data-elevation-observed]"), badge = find("[data-elevation-coverage]");
  const readout = find("#elevation-position-readout");
  const listeners = new window.AbortController();
  let value = null, candidate = null, projection = null, control = null, svg = null;
  let cursor = null, cursorPoint = null, position = null, width = 0, pointer = null;
  let frame = null, pendingDistance = null, destroyed = false;
  let chartListeners = null;
  let chartRenders = 0, renderMs = 0, interactionFrames = 0;

  function owns() { return !destroyed && isCurrent(value, candidate); }
  function clearInspection() {
    if (frame !== null) window.cancelAnimationFrame(frame);
    frame = null; pendingDistance = null; position = null;
    if (pointer !== null && control?.hasPointerCapture?.(pointer)) control.releasePointerCapture(pointer);
    pointer = null;
    cursor?.setAttribute("hidden", ""); cursorPoint?.setAttribute("hidden", "");
    showMap.hidden = true; clearPosition.hidden = true;
    readout.textContent = "Touch the profile or use arrow keys to inspect a position.";
    control?.setAttribute("aria-valuenow", "0");
    control?.setAttribute("aria-valuetext", "No position selected. Use arrow keys to inspect.");
    onPosition(null);
  }
  function removeChart() {
    clearInspection(); chartListeners?.abort(); chartListeners = null;
    host.replaceChildren(); host.hidden = true;
    projection = null; control = null; svg = null; cursor = null; cursorPoint = null;
    note.hidden = true;
  }
  function inspect(distance) {
    if (!owns() || value.status !== "ready" || !projection) { clearInspection(); return; }
    const analysis = value.result.analysis;
    position = elevationPositionAtDistance(analysis, value.result.sample_coordinates, distance);
    if (!position) return;
    interactionFrames++;
    const label = elevationDistanceLabel(position.distance_m, analysis.route_distance_m);
    const available = position.height_m !== null;
    readout.textContent = `${label} km · ${available ? `${position.height_m.toFixed(1)} m altitude` : "Elevation unavailable here"}`;
    control.setAttribute("aria-valuenow", String(position.distance_m));
    control.setAttribute("aria-valuetext", `${label} kilometres, ${available ? `${position.height_m.toFixed(1)} metres altitude` : "elevation unavailable here"}`);
    const x = projection.x(position.distance_m);
    cursor.removeAttribute("hidden"); cursor.setAttribute("x1", x); cursor.setAttribute("x2", x);
    cursorPoint.toggleAttribute("hidden", !available);
    if (available) { cursorPoint.setAttribute("cx", x); cursorPoint.setAttribute("cy", projection.y(position.height_m)); }
    showMap.hidden = !available; clearPosition.hidden = false;
    onPosition(available ? position : null);
  }
  function schedule(distance) {
    pendingDistance = distance;
    if (frame !== null) return;
    frame = window.requestAnimationFrame(() => {
      frame = null; const next = pendingDistance; pendingDistance = null; inspect(next);
    });
  }
  function pointerDistance(event) {
    const bounds = svg.getBoundingClientRect();
    return ((event.clientX - bounds.left) * projection.width / bounds.width - projection.left)
      / (projection.right - projection.left) * value.result.analysis.route_distance_m;
  }
  function bindControl() {
    chartListeners = new window.AbortController();
    const options = {signal:chartListeners.signal};
    control.addEventListener("pointerdown", event => {
      if (!event.isPrimary || event.button !== 0 || !owns()) return;
      pointer = event.pointerId; control.setPointerCapture?.(pointer);
      control.focus({preventScroll:true}); schedule(pointerDistance(event));
    }, options);
    control.addEventListener("pointermove", event => {
      if (!owns() || (pointer !== event.pointerId && event.pointerType !== "mouse")) return;
      schedule(pointerDistance(event));
    }, options);
    const release = event => { if (pointer === event.pointerId) pointer = null; };
    control.addEventListener("pointerup", release, options);
    control.addEventListener("pointercancel", release, options);
    control.addEventListener("focus", () => { if (!position) inspect(0); }, options);
    control.addEventListener("keydown", event => {
      if (!owns()) return;
      if (event.key === "Escape") { clearInspection(); event.preventDefault(); event.stopPropagation(); return; }
      const samples = value.result.analysis.samples;
      let index = position ? elevationSampleIndex(samples, position.distance_m) : 0;
      if (event.key === "Home") index = 0;
      else if (event.key === "End") index = samples.length - 1;
      else if (["ArrowRight", "ArrowUp", "PageUp"].includes(event.key)) {
        if (position && samples[index].distance_m <= position.distance_m) index++;
        if (event.key === "PageUp") index += 9;
      } else if (["ArrowLeft", "ArrowDown", "PageDown"].includes(event.key)) {
        if (position) index--;
        if (event.key === "PageDown") index -= 9;
      } else return;
      event.preventDefault();
      if (frame !== null) window.cancelAnimationFrame(frame);
      frame = null; pendingDistance = null;
      inspect(samples[Math.max(0, Math.min(samples.length - 1, index))].distance_m);
    }, options);
  }
  function node(name, attributes = {}, text = null) {
    const element = document.createElementNS(SVG, name);
    for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
    if (text !== null) element.textContent = text;
    return element;
  }
  function draw() {
    if (!owns() || value.status !== "ready") return;
    const started = window.performance.now();
    width = Math.round(host.clientWidth) || width || 300;
    projection = projectElevationProfile(value.result.analysis, value.result.sample_coordinates, width);
    if (!projection) { removeChart(); return; }
    if (!control) {
      control = document.createElement("div"); control.className = "elevation-profile-control";
      control.tabIndex = 0; control.setAttribute("role", "slider");
      control.setAttribute("aria-label", "Position on elevation profile");
      control.setAttribute("aria-describedby", "elevation-chart-help elevation-position-readout");
      control.setAttribute("aria-orientation", "horizontal"); control.setAttribute("aria-valuemin", "0");
      control.setAttribute("aria-valuemax", value.result.analysis.route_distance_m);
      control.setAttribute("aria-valuenow", "0"); control.setAttribute("aria-valuetext", "Use arrow keys to inspect the elevation profile.");
      host.append(control); bindControl();
    }
    const p = projection;
    svg = node("svg", {viewBox:`0 0 ${p.width} ${p.height}`, role:"img", "aria-labelledby":"elevation-chart-title elevation-chart-description"});
    svg.append(node("title", {id:"elevation-chart-title"}, "Route elevation profile"),
      node("desc", {id:"elevation-chart-description"}, "Filtered altitude in metres against cumulative routed distance in kilometres. Separate lines and isolated points preserve gaps in available elevation."));
    svg.append(node("text", {x:p.left, y:13, class:"elevation-axis-title"}, "Altitude (m)"));
    for (const tick of p.altitudeTicks) {
      svg.append(node("line", {x1:p.left, x2:p.right, y1:p.y(tick), y2:p.y(tick), class:"elevation-grid-line"}),
        node("text", {x:p.left - 7, y:p.y(tick) + 4, "text-anchor":"end", class:"elevation-axis-tick"}, String(Math.round(tick))));
    }
    for (const tick of p.distanceTicks) svg.append(node("text", {x:p.x(tick), y:p.bottom + 18,
      "text-anchor":tick === 0 ? "start" : tick === value.result.analysis.route_distance_m ? "end" : "middle", class:"elevation-axis-tick"},
      elevationDistanceLabel(tick, value.result.analysis.route_distance_m)));
    svg.append(node("text", {x:(p.left + p.right) / 2, y:p.height - 3, "text-anchor":"middle", class:"elevation-axis-title"}, "Distance (km)"));
    for (const path of p.paths) svg.append(node("path", {d:path, class:"elevation-profile-line"}));
    for (const point of p.points) svg.append(node("circle", {cx:point.x, cy:point.y, r:3, class:"elevation-isolated-point"}));
    cursor = node("line", {y1:p.top, y2:p.bottom, class:"elevation-cursor", hidden:""});
    cursorPoint = node("circle", {r:4.5, class:"elevation-cursor-point", hidden:""});
    svg.append(cursor, cursorPoint); control.replaceChildren(svg);
    chartRenders++; renderMs = window.performance.now() - started;
    if (position) inspect(position.distance_m);
    root.dispatchEvent(new window.CustomEvent("elevation-rendered", {detail:{duration_ms:renderMs, samples:value.result.analysis.samples.length}}));
  }
  function render(next, selectedCandidate) {
    if (destroyed) return;
    if (next === value && selectedCandidate === candidate && owns()) return;
    value = next; candidate = selectedCandidate;
    removeChart();
    const current = owns() && value.status !== "idle";
    root.hidden = !current;
    if (!current) return;
    summary.hidden = false;
    find("[data-elevation-distance]").textContent = `${elevationDistanceLabel(candidate.route.summary.distance_m, candidate.route.summary.distance_m)} km`;
    for (const selector of ["[data-elevation-ascent]", "[data-elevation-descent]", "[data-elevation-altitude]"]) find(selector).textContent = "Unavailable";
    cancel.hidden = value.status !== "loading"; retry.hidden = true; observed.hidden = true;
    status.hidden = false;
    if (value.status === "loading") {
      badge.textContent = "Calculating"; status.textContent = "Calculating elevation… Your route is ready to use."; return;
    }
    if (value.status !== "ready") {
      badge.textContent = "Unavailable"; retry.hidden = false;
      status.textContent = value.diagnostic === "elevation_cancelled"
        ? "Elevation calculation cancelled. Your route remains available." : "Elevation unavailable. Your route remains available.";
      return;
    }
    const analysis = value.result.analysis;
    badge.textContent = analysis.coverage === "complete" ? "Complete" : analysis.coverage === "partial" ? "Partial coverage" : "Unavailable";
    if (analysis.coverage === "complete") {
      find("[data-elevation-ascent]").textContent = metres(analysis.total_ascent_m);
      find("[data-elevation-descent]").textContent = metres(analysis.total_descent_m);
      status.textContent = "Elevation profile ready.";
    } else if (analysis.coverage === "partial") {
      status.textContent = "Partial elevation. Full-route D+ and D− are unavailable.";
      observed.hidden = false;
      const coverage = (100 * analysis.analyzed_distance_m / analysis.route_distance_m).toFixed(1);
      observed.textContent = `Measured segments cover ${coverage}% of the route. ${analysis.observed_ascent_m === null
        ? "Available heights are isolated; ascent and descent cannot be measured."
        : `Measured segments only: D+ ${metres(analysis.observed_ascent_m)} · D− ${metres(analysis.observed_descent_m)}.`}`;
    } else {
      status.textContent = "Elevation unavailable for this route. Your route remains available."; retry.hidden = false; return;
    }
    find("[data-elevation-altitude]").textContent = analysis.minimum_height_m === analysis.maximum_height_m
      ? metres(analysis.minimum_height_m) : `${Math.round(analysis.minimum_height_m)}–${Math.round(analysis.maximum_height_m)} m`;
    host.hidden = false; note.hidden = false; draw();
  }
  cancel.addEventListener("click", () => { if (owns()) onCancel(); }, {signal:listeners.signal});
  retry.addEventListener("click", () => { if (owns()) onRetry(); }, {signal:listeners.signal});
  showMap.addEventListener("click", () => { if (owns() && position?.coordinate) onShowMap(position); }, {signal:listeners.signal});
  clearPosition.addEventListener("click", clearInspection, {signal:listeners.signal});
  const observer = new window.ResizeObserver(() => {
    const nextWidth = Math.round(host.clientWidth);
    if (nextWidth > 0 && nextWidth !== width && value?.status === "ready" && owns()) draw();
  });
  observer.observe(host);
  const destroy = () => {
    if (destroyed) return;
    destroyed = true; listeners.abort(); observer.disconnect(); removeChart(); root.hidden = true;
  };
  window.addEventListener("pagehide", destroy, {once:true, signal:listeners.signal});
  return Object.freeze({render, destroy, diagnostics:() => ({chart_renders:chartRenders, chart_render_ms:renderMs,
    interaction_frames:interactionFrames, samples:projection ? value.result.analysis.samples.length : 0, position})});
}
