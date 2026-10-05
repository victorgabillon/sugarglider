import { state, switchPlanningMode, currentPlanRequest, generationAvailability, readPlannerOptionsFromControls } from "../../src/sugarglider/web/static/state.js";
import { pointVisibilityOffset, keepMapCoordinateVisible } from "../../src/sugarglider/web/static/map_viewport.js";
import { initializeAppShell } from "../../src/sugarglider/web/static/app_shell.js";
const assert = (ok, message) => { if (!ok) throw Error(message); };
const same = (a, b, message) => assert(JSON.stringify(a) === JSON.stringify(b), message);
const settle = () => new Promise(resolve => setTimeout(resolve, 100));
export async function runPlanningHarness() {
  const cases = [];
  for (const [point, width, height, expected] of [
    [{ x: 150, y: 120 }, 360, 240, null],
    [{ x: 150, y: 500 }, 360, 240, [0, 380]],
    [{ x: -20, y: 20 }, 360, 240, [-116, -60]],
    [{ x: 400, y: 200 }, 360, 240, [136, 80]],
    [{ x: 20, y: 20 }, 0, 0, null],
    [{ x: NaN, y: 20 }, 360, 240, null],
  ]) { same(pointVisibilityOffset(point, width, height), expected, 'bounded point correction'); cases.push('visibility_' + cases.length); }
  const coordinate = [2.13, 48.806], calls = [];
  let projected = { x: 72, y: 295 };
  const resizedMap = {
    project: () => projected,
    getContainer: () => ({ clientWidth: 360, clientHeight: 262 }),
    getCanvas: () => ({ clientWidth: 360, clientHeight: 656 }),
    panBy: (offset, options) => { calls.push({ offset, options }); projected = { x: projected.x - offset[0], y: projected.y - offset[1] }; },
  };
  assert(keepMapCoordinateVisible(resizedMap, coordinate), 'container corrects point while canvas still has old height');
  same(calls, [{ offset: [-24, 161], options: { duration: 0 } }], 'one minimal screen-space correction');
  same(coordinate, [2.13, 48.806], 'coordinate unchanged');
  assert(!keepMapCoordinateVisible(resizedMap, coordinate) && calls.length === 1, 'already visible point never pans again');
  cases.push('resized_projection_with_stale_canvas_dimensions');
  const initial = structuredClone(state);
  try {
    const start = { name: 'A', lat: 48.806, lon: 2.13 };
    state.routingProfile = 'hike'; state.autoTour.start = start; state.points = [start];
    state.options = { ...state.options, targetDistanceKm: 10, maximumDistanceKm: 14, distancePriority: 'strict' };
    const auto = currentPlanRequest();
    switchPlanningMode('waypoint_route');
    assert(state.waypointEndpoints.start === null, 'other mode never inherits Start');
    assert(state.routingProfile === 'hike', 'Activity shared');
    state.waypointEndpoints.start = { name: 'B', lat: 48.81, lon: 2.14 };
    state.points = ['exact', 'approach', 'best_effort'].map((constraintStrength, i) => ({ name: `Place ${i}`, lat: 48.812 + i * .001, lon: 2.141 + i * .001, constraintStrength, accessSearchRadiusM: 300, maximumBestEffortDistanceM: 500 }));
    state.options = { ...state.options, targetDistanceKm: 7, maximumDistanceKm: null, distancePriority: 'balanced', waypointOrder: 'optimize' };
    const waypoint = currentPlanRequest();
    switchPlanningMode('auto_tour'); same(currentPlanRequest(), auto, 'exact auto draft restored');
    switchPlanningMode('waypoint_route'); same(currentPlanRequest(), waypoint, 'exact waypoint draft restored');
    assert(state.request.status !== 'running', 'switching never generates');
    cases.push('independent_drafts_exact_roundtrip_shared_activity');
    const args = { planningMode: 'auto_tour', routeTopology: 'loop', start: null, end: null, mandatoryPointCount: 0, pointValidationMessage: '', profileAvailable: true };
    assert(!generationAvailability(args).enabled, 'missing Start blocks');
    assert(generationAvailability({ ...args, start }).enabled, 'Start enables suggestion');
    assert(!generationAvailability({ ...args, start, profileAvailable: false }).enabled, 'unavailable activity blocks');
    assert(generationAvailability({ ...args, start, pointValidationMessage: 'Invalid coordinate' }).reason === 'Invalid coordinate', 'validation preserved');
    assert(!generationAvailability({ ...args, start, planningMode: 'waypoint_route' }).enabled, 'loop needs chosen point');
    cases.push('shared_generation_authority_start_profile_errors');
  } finally { Object.assign(state, initial); }
  const response = await fetch('../../src/sugarglider/web/static/index.html');
  const markup = new DOMParser().parseFromString(await response.text(), 'text/html');
  markup.querySelectorAll('script, link').forEach(n => n.remove());
  for (const width of [360, 390, 412, 1280, 1440]) {
    const frame = document.createElement('iframe'); frame.style.cssText = `width:${width}px;height:800px`;
    const loaded = new Promise(resolve => frame.onload = resolve); frame.srcdoc = markup.documentElement.outerHTML; document.body.append(frame); await loaded;
    const doc = frame.contentDocument, byId = id => doc.getElementById(id);
    const labels = [...doc.querySelectorAll('.planning-mode strong')].map(n => n.textContent);
    same(labels, ['Automatic', 'Suggest a route', 'Connect my points'], 'advanced strategies');
    assert(byId('planning-preferences').contains(doc.querySelector('.planning-mode')), 'strategy is advanced, not required');
    assert(doc.querySelectorAll('#profile').length === 1 && doc.querySelectorAll('#hard-start-control').length === 1, 'one shared Activity and Start');
    assert(byId('plan-start-summary').textContent === 'Choose Start on the map', 'empty other draft guidance');
    const form = byId('route-form');
    assert(form.contains(byId('maximum-distance')) && form.contains(byId('target-distance')), 'one shared distance objective');
    byId('profile').innerHTML = '<option value="hike">Hike</option>';
    byId('target-distance').value = '10'; byId('maximum-distance').value = '';
    assert(readPlannerOptionsFromControls(byId).targetDistanceKm === 10, 'distance editing uses canonical reader');
    assert(readPlannerOptionsFromControls(byId).maximumDistanceKm === null, 'blank maximum retained');
    const resizeEvents = [];
    const shell = initializeAppShell({ document: doc, resizeMap: event => resizeEvents.push(event) });
    await settle(); shell.show('plan'); await settle();
    const count = resizeEvents.filter(e => e.layoutChanged).length;
    shell.show('plan'); await settle();
    assert(resizeEvents.filter(e => e.layoutChanged).length === count, 'same layout does not request recenter');
    const panel = doc.querySelector('.map-panel'); panel.style.height = '200px'; await settle();
    assert(resizeEvents.at(-1).layoutChanged && resizeEvents.at(-1).view === 'plan', 'real resize flagged once for Plan');
    const settled = resizeEvents.length; await settle(); assert(resizeEvents.length === settled, 'no idle resize loop');
    shell.show('routes'); assert(!byId('results-panel').hidden, 'common Routes transition');
    shell.destroy(); frame.remove(); cases.push(`presentation_controls_resize_${width}`);
  }
  return cases;
}
