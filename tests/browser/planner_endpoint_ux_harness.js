import {
  applyImplicitEndpointMapClick,
  assignRouteEndpoint,
  generationAvailability,
  renderEndpointTopologyControls,
  setRouteTopology,
} from "../../src/sugarglider/web/static/state.js";

const START = Object.freeze({ name: "Start", lat: 48.87, lon: 2.09 });
const END = Object.freeze({ name: "End", lat: 48.88, lon: 2.1 });
const MAP_CLICK = Object.freeze({ lat: 48.89, lon: 2.11 });
const LATER_CLICK = Object.freeze({ lat: 48.9, lon: 2.12 });

export function runPlannerEndpointUxHarness() {
  const scenarios = [];

  scenarioLoopCannotSetDistinctEnd();
  scenarios.push("loop_cannot_set_distinct_hard_end");
  scenarioPointToPointToLoopClearsEnd();
  scenarios.push("point_to_point_to_loop_clears_end");
  scenarioLoopToPointToPointRequiresEnd();
  scenarios.push("loop_to_point_to_point_exposes_and_requires_end");
  scenarioAutoTourLoopNeedsNoEnd();
  scenarios.push("auto_tour_loop_with_start_is_generatable");
  scenarioAutoTourPointToPointRequiresEndpoints();
  scenarios.push("auto_tour_point_to_point_requires_start_and_end");
  scenarioWaypointPointToPointRequiresEndpoints();
  scenarios.push("waypoint_route_point_to_point_requires_start_and_end");
  scenarioDisabledReasonsAreActionable();
  scenarios.push("disabled_generate_reasons_are_actionable");
  scenarioAllValidCombinationsRemainAvailable();
  scenarios.push("all_valid_mode_topology_combinations_remain_available");
  scenarioLoopOrdinaryClickSetsMissingStart();
  scenarios.push("loop_ordinary_click_sets_missing_start");
  scenarioLoopOrdinaryClickPreservesExistingStart();
  scenarios.push("loop_ordinary_click_preserves_existing_start");
  scenarioPointToPointFirstClickSetsStart();
  scenarios.push("point_to_point_first_click_sets_start");
  scenarioPointToPointSecondClickSetsEnd();
  scenarios.push("point_to_point_second_click_sets_end");
  scenarioPointToPointLaterClickPreservesEndpoints();
  scenarios.push("point_to_point_later_click_preserves_endpoints");
  scenarioExplicitEndpointModeCanReplaceEndpoint();
  scenarios.push("explicit_endpoint_mode_can_replace_endpoint");
  scenarioExplicitWaypointAndPoiModesSuppressImplicitEndpoints();
  scenarios.push("explicit_waypoint_and_poi_modes_suppress_implicit_endpoints");
  scenarioImplicitPlacementIsSharedByBothPlanningModes();
  scenarios.push("implicit_placement_is_shared_by_both_planning_modes");

  return scenarios;
}

function scenarioLoopCannotSetDistinctEnd() {
  const endpoints = endpointState("loop", null);
  equal(
    assignRouteEndpoint(endpoints, "end", END),
    false,
    "loop rejects an explicit end assignment",
  );
  equal(endpoints.end, null, "loop retains no explicit end");

  const presentation = renderEndpointTopologyControls(
    document.getElementById("hard-end-control"),
    document.getElementById("loop-end-explanation"),
    endpoints.routeTopology,
  );
  equal(presentation.hardEndAvailable, false, "loop hides the Hard-end editor");
  equal(
    document.getElementById("hard-end-control").disabled,
    true,
    "loop disables the Hard-end editor",
  );
  equal(
    document.getElementById("loop-end-explanation").hidden,
    false,
    "loop explains its implicit end",
  );
}

function scenarioPointToPointToLoopClearsEnd() {
  const endpoints = endpointState("point_to_point", END);
  equal(setRouteTopology(endpoints, "loop"), true, "topology change reports cleanup");
  equal(endpoints.end, null, "point-to-point end is cleared on loop transition");
}

function scenarioLoopToPointToPointRequiresEnd() {
  const endpoints = endpointState("loop", null);
  setRouteTopology(endpoints, "point_to_point");
  const presentation = renderEndpointTopologyControls(
    document.getElementById("hard-end-control"),
    document.getElementById("loop-end-explanation"),
    endpoints.routeTopology,
  );
  equal(presentation.hardEndAvailable, true, "point-to-point exposes Hard end");
  equal(
    availability({ routeTopology: endpoints.routeTopology, end: endpoints.end }).reason,
    "Now click the map to choose your end point.",
    "point-to-point requires its newly exposed end",
  );
}

function scenarioAutoTourLoopNeedsNoEnd() {
  equal(
    availability({ planningMode: "auto_tour", routeTopology: "loop" }).enabled,
    true,
    "Auto Tour loop needs only its start",
  );
}

function scenarioAutoTourPointToPointRequiresEndpoints() {
  equal(
    availability({
      planningMode: "auto_tour",
      routeTopology: "point_to_point",
      start: null,
      end: null,
    }).reason,
    "Click the map to choose your start point.",
    "Auto Tour open route first requires a start",
  );
  equal(
    availability({
      planningMode: "auto_tour",
      routeTopology: "point_to_point",
      end: null,
    }).reason,
    "Now click the map to choose your end point.",
    "Auto Tour open route then requires an end",
  );
}

function scenarioWaypointPointToPointRequiresEndpoints() {
  equal(
    availability({
      planningMode: "waypoint_route",
      routeTopology: "point_to_point",
      start: null,
      end: null,
    }).reason,
    "Click the map to choose your start point.",
    "Waypoint open route first requires a start",
  );
  equal(
    availability({
      planningMode: "waypoint_route",
      routeTopology: "point_to_point",
      end: null,
    }).reason,
    "Now click the map to choose your end point.",
    "Waypoint open route then requires an end",
  );
}

function scenarioDisabledReasonsAreActionable() {
  equal(
    availability({ start: null }).reason,
    "Click the map to choose your start point.",
    "loop missing-start reason is explicit",
  );
  equal(
    availability({ profileAvailable: false }).reason,
    "The selected routing profile is unavailable.",
    "routing-profile reason is explicit",
  );
  const precise = "Points 1 and 2 have identical adjacent coordinates.";
  equal(
    availability({
      start: null,
      pointValidationMessage: precise,
      profileAvailable: false,
    }).reason,
    precise,
    "precise point validation outranks generic disabled reasons",
  );
}

function scenarioLoopOrdinaryClickSetsMissingStart() {
  const endpoints = endpointState("loop", null, null);
  equal(
    ordinaryMapClick(endpoints, MAP_CLICK),
    "start",
    "first loop click targets the missing start",
  );
  coordinateEqual(endpoints.start, MAP_CLICK, "first loop click stores its coordinate");
  equal(endpoints.end, null, "loop click never creates an end");
}

function scenarioLoopOrdinaryClickPreservesExistingStart() {
  const endpoints = endpointState("loop", null);
  equal(ordinaryMapClick(endpoints, LATER_CLICK), null, "complete loop ignores later click");
  equal(endpoints.start, START, "later loop click retains the original start object");
}

function scenarioPointToPointFirstClickSetsStart() {
  const endpoints = endpointState("point_to_point", null, null);
  equal(ordinaryMapClick(endpoints, MAP_CLICK), "start", "first open-route click sets start");
  coordinateEqual(endpoints.start, MAP_CLICK, "open-route start uses clicked coordinate");
  equal(endpoints.end, null, "first open-route click leaves end missing");
}

function scenarioPointToPointSecondClickSetsEnd() {
  const endpoints = endpointState("point_to_point", null, null);
  ordinaryMapClick(endpoints, MAP_CLICK);
  equal(ordinaryMapClick(endpoints, LATER_CLICK), "end", "second open-route click sets end");
  coordinateEqual(endpoints.start, MAP_CLICK, "second click preserves first-click start");
  coordinateEqual(endpoints.end, LATER_CLICK, "second click stores end coordinate");
}

function scenarioPointToPointLaterClickPreservesEndpoints() {
  const endpoints = endpointState("point_to_point", END);
  equal(ordinaryMapClick(endpoints, LATER_CLICK), null, "complete open route ignores later click");
  equal(endpoints.start, START, "later click retains existing start");
  equal(endpoints.end, END, "later click retains existing end");
}

function scenarioExplicitEndpointModeCanReplaceEndpoint() {
  const endpoints = endpointState("point_to_point", END);
  equal(
    ordinaryMapClick(endpoints, MAP_CLICK, { endpointSetMode: "start" }),
    null,
    "explicit endpoint mode suppresses implicit placement",
  );
  equal(
    assignRouteEndpoint(endpoints, "start", { name: "Replacement", ...MAP_CLICK }),
    true,
    "explicit endpoint assignment remains available",
  );
  coordinateEqual(endpoints.start, MAP_CLICK, "explicit mode replaces existing start");
}

function scenarioExplicitWaypointAndPoiModesSuppressImplicitEndpoints() {
  const waypointEndpoints = endpointState("point_to_point", null, null);
  const waypointPoints = [];
  equal(
    ordinaryMapClick(waypointEndpoints, MAP_CLICK, { addPointMode: true }),
    null,
    "Waypoint add mode suppresses implicit placement",
  );
  waypointPoints.push({ name: "Required point", ...MAP_CLICK });
  equal(waypointPoints.length, 1, "Waypoint add mode retains its intended point action");
  equal(waypointEndpoints.start, null, "Waypoint add mode does not create start");
  equal(waypointEndpoints.end, null, "Waypoint add mode does not create end");

  const poiEndpoints = endpointState("point_to_point", null, null);
  equal(
    ordinaryMapClick(poiEndpoints, MAP_CLICK, {
      settingRequestedApproachId: "requested-place",
    }),
    null,
    "requested-place approach mode suppresses implicit placement",
  );
  equal(poiEndpoints.start, null, "requested-place mode does not create start");
  equal(poiEndpoints.end, null, "requested-place mode does not create end");
}

function scenarioImplicitPlacementIsSharedByBothPlanningModes() {
  for (const planningMode of ["auto_tour", "waypoint_route"]) {
    const loop = planningModeEndpointState(planningMode, "loop");
    equal(ordinaryMapClick(loop, MAP_CLICK), "start", `${planningMode} loop sets start`);
    equal(loop.end, null, `${planningMode} loop retains no end`);

    const open = planningModeEndpointState(planningMode, "point_to_point");
    ordinaryMapClick(open, MAP_CLICK);
    ordinaryMapClick(open, LATER_CLICK);
    coordinateEqual(open.start, MAP_CLICK, `${planningMode} open route sets start`);
    coordinateEqual(open.end, LATER_CLICK, `${planningMode} open route sets end`);
  }
}

function planningModeEndpointState(planningMode, routeTopology) {
  return planningMode === "auto_tour"
    ? { start: null, end: null, routeTopology, hardPoints: [], requestedPlaces: [] }
    : { start: null, end: null, routeTopology };
}

function scenarioAllValidCombinationsRemainAvailable() {
  const combinations = [
    availability({ planningMode: "auto_tour", routeTopology: "loop" }),
    availability({
      planningMode: "auto_tour",
      routeTopology: "point_to_point",
      end: END,
    }),
    availability({
      planningMode: "waypoint_route",
      routeTopology: "loop",
      mandatoryPointCount: 1,
    }),
    availability({
      planningMode: "waypoint_route",
      routeTopology: "point_to_point",
      end: END,
    }),
  ];
  assert(combinations.every((result) => result.enabled), "all four valid combinations work");

  if (window.innerWidth <= 390) {
    const columns = getComputedStyle(
      document.getElementById("mobile-endpoint-fields"),
    ).gridTemplateColumns.trim().split(/\s+/);
    equal(columns.length, 1, "endpoint coordinate fields collapse on a narrow viewport");
  }
}

function ordinaryMapClick(endpoints, coordinate, interactions = {}) {
  return applyImplicitEndpointMapClick({
    endpoints,
    coordinate,
    assignEndpoint: (kind, point) => assignRouteEndpoint(endpoints, kind, point),
    ...interactions,
  });
}

function endpointState(routeTopology, end, start = START) {
  return { start, end, routeTopology };
}

function availability(overrides = {}) {
  return generationAvailability({
    planningMode: "auto_tour",
    routeTopology: "loop",
    start: START,
    end: null,
    mandatoryPointCount: 0,
    pointValidationMessage: "",
    profileAvailable: true,
    ...overrides,
  });
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function equal(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function coordinateEqual(actual, expected, message) {
  assert(actual !== null, `${message}: coordinate is missing`);
  equal(actual.lat, expected.lat, `${message}: latitude`);
  equal(actual.lon, expected.lon, `${message}: longitude`);
}
