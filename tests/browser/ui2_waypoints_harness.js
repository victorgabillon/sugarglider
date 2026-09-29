import { renderWaypointEditor } from '../../src/sugarglider/web/static/waypoint_editor.js';
import { state, switchPlanningMode, currentPlanRequest, generationAvailability } from '../../src/sugarglider/web/static/state.js';
const assert = (ok, message) => { if (!ok) throw Error(message); };
const same = (a, b, message) => assert(JSON.stringify(a) === JSON.stringify(b), message);
export async function runWaypointHarness() {
  const cases = [], initial = structuredClone(state), list = document.createElement('div');
  list.role = 'list'; document.body.append(list);
  let points = ['exact', 'approach', 'best_effort'].map((constraintStrength, i) => ({ id: `stop-${i}`, name: `Chosen ${i + 1}`, lat: 48.81 + i * .001, lon: 2.14 + i * .001, constraintStrength, accessSearchRadiusM: 300 + i * 100, maximumBestEffortDistanceM: i === 2 ? 650 : null, approachOverride: i === 1 ? { lat: 48.8111, lon: 2.1411 } : null }));
  let selected = 1, placement = null;
  const render = () => renderWaypointEditor({ list, points, selectedIndex: selected, visitOrders: new Map([[1, 3]]),
    onSelect: i => { selected = i; render(); }, onChange: (i, key, value) => { points[i] = { ...points[i], [key]: value }; render(); },
    onMove: (from, to) => { const point = points[selected]; const [moved] = points.splice(from, 1); points.splice(to, 0, moved); selected = points.indexOf(point); render(); },
    onRemove: i => { points.splice(i, 1); selected = points.length ? Math.min(i, points.length - 1) : null; render(); }, onPlace: i => { placement = i; },
  });
  const check = (name, fn) => { fn(); cases.push(name); };
  const click = selector => list.querySelector(selector).click();
  const change = (key, value) => { const input = list.querySelector(`[data-field="${key}"]`); input.value = value; input.dispatchEvent(new Event('change')); };
  try {
    render();
    check('compact_three_stops_one_editor', () => assert(list.querySelectorAll('.point-select').length === 3 && list.querySelectorAll('.stop-editor').length === 1, 'one editor'));
    check('truthful_constraint_and_generated_order', () => assert(list.textContent.includes('Nearby access') && list.textContent.includes('Generated visit 3') && list.textContent.includes('Best effort'), 'constraint/order text'));
    check('coordinates_progressively_disclosed', () => assert(!list.querySelector('details').open && list.textContent.includes('approach override'), 'advanced coordinates/override'));
    const exact = structuredClone(points);
    click('[data-point-index="2"] .point-select');
    check('selection_does_not_mutate_points', () => same(points, exact, 'no selection mutation'));
    check('selection_is_aria_pressed', () => assert(list.querySelector('[data-point-index="2"] .point-select').getAttribute('aria-pressed') === 'true', 'pressed'));
    list.querySelector('[data-point-index="2"] .point-select').dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }));
    check('keyboard_selects_and_focuses_previous', () => assert(selected === 1 && document.activeElement === list.querySelector('[data-point-index="1"] .point-select'), 'keyboard selection'));
    const name = list.querySelector('[data-field="name"]'); name.focus(); change('name', 'Renamed stop');
    check('name_edit_preserves_imported_constraints', () => same(points[1], { ...exact[1], name: 'Renamed stop' }, 'only name changed'));
    check('name_focus_survives_render', () => assert(document.activeElement?.dataset.field === 'name', 'focus retained'));
    change('constraintStrength', 'best_effort');
    check('explicit_constraint_change_only', () => same(points[1], { ...exact[1], name: 'Renamed stop', constraintStrength: 'best_effort' }, 'constraint changed only'));
    change('maximumBestEffortDistanceM', '850');
    check('explicit_maximum_edit', () => assert(points[1].maximumBestEffortDistanceM === 850, 'numeric maximum'));
    change('maximumBestEffortDistanceM', '');
    check('blank_maximum_preserved', () => assert(points[1].maximumBestEffortDistanceM === null, 'blank is null'));
    change('lat', '48.81512345');
    check('coordinate_not_rounded_or_snapped', () => assert(points[1].lat === 48.81512345, 'exact input coordinate'));
    const selectedPoint = points[1]; click('[data-action="up"]');
    check('manual_order_keeps_selected_identity', () => assert(selected === 0 && points[0] === selectedPoint, 'same object moved'));
    check('boundary_actions_disabled', () => assert(list.querySelector('[data-action="up"]').disabled && !list.querySelector('[data-action="down"]').disabled, 'boundary'));
    click('[data-action="place"]');
    check('move_intent_targets_selected_point_without_mutation', () => assert(placement === 0 && points[0] === selectedPoint, 'movement is explicit'));
    click('[data-action="remove"]');
    check('remove_exact_target_keeps_remaining_order', () => same(points.map(p => p.id), ['stop-0', 'stop-2'], 'only chosen target removed'));
    check('remove_selects_neighbor', () => assert(selected === 0 && list.querySelectorAll('.stop-editor').length === 1, 'neighbor'));
    points = []; selected = null; render();
    check('empty_loop_guidance', () => assert(list.textContent.includes('loop needs at least one stop'), 'empty guidance'));
    state.routingProfile = 'hike'; switchPlanningMode('waypoint_route');
    state.points = exact; state.waypointEndpoints.start = { name: 'Start', lat: 48.8, lon: 2.13 };
    state.waypointEndpoints.end = { name: 'End', lat: 48.82, lon: 2.15 }; state.waypointEndpoints.routeTopology = 'point_to_point';
    state.options = { ...state.options, waypointOrder: 'optimize', targetDistanceKm: 9, toleranceKm: 2, maximumDistanceKm: 14, distancePriority: 'strict' };
    const request = currentPlanRequest(); state.movingPointIndex = 2; state.addPointMode = true; state.endpointSetMode = 'end'; state.selectedEndpointKind = 'end';
    switchPlanningMode('auto_tour');
    check('mode_switch_cancels_transient_placement', () => assert(state.movingPointIndex === null && !state.addPointMode && state.endpointSetMode === null && state.selectedEndpointKind === null, 'placement cleared'));
    switchPlanningMode('waypoint_route');
    check('rich_request_restores_exactly', () => same(currentPlanRequest(), request, 'all constraints/end/order/activity/distances'));
    const args = { planningMode: 'waypoint_route', routeTopology: 'loop', start: null, end: null, mandatoryPointCount: 0, pointValidationMessage: '', profileAvailable: true };
    check('missing_start_explicit_guidance', () => assert(generationAvailability(args).reason.includes('Choose Start'), 'choose start'));
    check('loop_requires_stop', () => assert(!generationAvailability({ ...args, start: request.start }).enabled, 'loop stop'));
    check('loop_start_and_stop_ready', () => assert(generationAvailability({ ...args, start: request.start, mandatoryPointCount: 1 }).enabled, 'ready'));
    check('open_route_needs_end', () => assert(!generationAvailability({ ...args, start: request.start, routeTopology: 'point_to_point' }).enabled, 'end'));
    check('open_route_start_end_ready', () => assert(generationAvailability({ ...args, start: request.start, end: request.end, routeTopology: 'point_to_point' }).enabled, 'ready'));
    check('validation_and_profile_errors_not_hidden', () => assert(!generationAvailability({ ...args, start: request.start, mandatoryPointCount: 3, profileAvailable: false }).enabled && generationAvailability({ ...args, pointValidationMessage: 'Outside coverage' }).reason === 'Outside coverage', 'blocking preserved'));
  } finally { Object.assign(state, initial); list.remove(); }
  return cases;
}
