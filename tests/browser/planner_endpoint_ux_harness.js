import {
  assignRouteEndpoint,
  generationAvailability,
  renderEndpointTopologyControls,
  setRouteTopology,
} from "../../src/sugarglider/web/static/state.js";

const START = Object.freeze({ name: "Start", lat: 48.87, lon: 2.09 });
const END = Object.freeze({ name: "End", lat: 48.88, lon: 2.1 });

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
    "Choose an end point.",
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
    "Choose a start point.",
    "Auto Tour open route first requires a start",
  );
  equal(
    availability({
      planningMode: "auto_tour",
      routeTopology: "point_to_point",
      end: null,
    }).reason,
    "Choose an end point.",
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
    "Choose a start point.",
    "Waypoint open route first requires a start",
  );
  equal(
    availability({
      planningMode: "waypoint_route",
      routeTopology: "point_to_point",
      end: null,
    }).reason,
    "Choose an end point.",
    "Waypoint open route then requires an end",
  );
}

function scenarioDisabledReasonsAreActionable() {
  equal(
    availability({ start: null }).reason,
    "Choose a start point for this loop.",
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

function endpointState(routeTopology, end) {
  return { start: START, end, routeTopology };
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
