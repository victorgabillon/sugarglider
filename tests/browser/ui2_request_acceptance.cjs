// Integration test against the running application, using real controls and JSON import.
// Requires Playwright, the application server and its six-profile routing configuration.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const fs = require("fs"),
  assert = require("assert/strict"),
  O = process.env.UI2_EVIDENCE_DIR,
  phase = process.env.UI2_PHASE || "after",
  B = process.env.UI2_BASE_URL || "http://127.0.0.1:8000";
if (!O) throw Error("Set UI2_EVIDENCE_DIR to an external evidence directory.");
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.UI2_CHROME || "/usr/bin/google-chrome",
    headless: true,
    args: ["--no-sandbox", "--enable-unsafe-swiftshader"],
  });
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 800 },
  });
  await ctx.route("**/*", (r) =>
    new URL(r.request().url()).hostname === "127.0.0.1"
      ? r.continue()
      : r.abort(),
  );
  const page = await ctx.newPage();
  await page.goto(B + "/");
  await page.evaluate(async () => {
    const { openPwaStore, PWA_STORES } = await import("/static/pwa_store.js");
    const s = await openPwaStore();
    await s.put(PWA_STORES.trailProfile, "current", {
      schema_version: 1,
      display_name: "Request tests",
      avatar_key: "forest",
    });
    s.close();
  });
  await page.goto(B + "/");
  await page.waitForFunction(
    () => document.querySelector("#profile").options.length >= 6,
  );
  const records = [];
  const coord = (name, lat, lon) => ({ name, lat, lon }),
    start = coord("Start", 48.806, 2.1304),
    end = coord("End", 48.813, 2.145);
  function fixture(kind, profile, priority, topology = "loop") {
    const common = {
      schema_version: 1,
      kind,
      name: [kind, profile, priority, topology].join("-"),
      topology,
      start,
      end: topology === "loop" ? null : end,
      routing_profile: profile,
      candidate_count: 3,
      seed: 41,
      distance_objective: {
        target_m: 10000,
        tolerance_m: 2000,
        maximum_m: priority === "strict" ? 14000 : null,
        priority,
      },
    };
    return kind === "auto_tour"
      ? {
          ...common,
          preferences: {
            nature: "prefer",
            path_selection: "low_overlap",
            loop_geometry: topology === "loop" ? "prefer" : "off",
            scenic: "prefer",
            drinking_water: "off",
            direction: topology === "loop" ? "clockwise" : "any",
          },
          hard_waypoints: [],
          requested_stops: [],
          preferred_discovered_poi_ids: [],
          free_poi_spur_physical_m: 200,
        }
      : {
          ...common,
          preferences: {
            nature: "off",
            path_selection: "shortest",
            loop_geometry: "off",
          },
          waypoint_order: "fixed",
          waypoints: [
            {
              id: "point-1",
              name: "Chosen point",
              coordinate: coord("Chosen point", 48.81, 2.138),
              constraint_strength: "exact",
              access_search_radius_m: 500,
              maximum_best_effort_distance_m: null,
              approach_override: null,
            },
          ],
        };
  }
  async function load(value) {
    await page
      .locator("#request-file")
      .setInputFiles({
        name: "intent.json",
        mimeType: "application/json",
        buffer: Buffer.from(JSON.stringify(value)),
      });
    await page.waitForFunction(
      (name) => document.querySelector("#route-name").value === name,
      value.name,
    );
  }
  async function snapshot() {
    return page.evaluate(async () =>
      JSON.parse(
        JSON.stringify((await import("/static/state.js")).currentPlanRequest()),
      ),
    );
  }
  for (const kind of ["auto_tour", "waypoint_route"])
    for (const profile of [
      "trail_run",
      "hike",
      "city_bike",
      "gravel_bike",
      "mountain_bike",
      "road_bike",
    ])
      for (const priority of ["flexible", "balanced", "strict"]) {
        const input = fixture(kind, profile, priority);
        await load(input);
        const output = await snapshot();
        assert.deepEqual(output, input);
        records.push({ case: input.name, input, output });
      }
  for (const kind of ["auto_tour", "waypoint_route"]) {
    const input = fixture(kind, "hike", "balanced", "point_to_point");
    input.name += "-rich";
    if (kind === "auto_tour") {
      input.hard_waypoints = [
        {
          id: "anchor",
          name: "Anchor",
          coordinate: coord("Anchor", 48.81, 2.136),
        },
      ];
      input.requested_stops = [
        {
          id: "requested",
          name: "Imported place",
          semantic_coordinate: coord("Imported place", 48.812, 2.139),
          importance: "preferred",
          constraint_strength: "best_effort",
          osm_reference: "node/123",
          access_search_radius_m: 400,
          maximum_best_effort_distance_m: 600,
          approach_override: coord("Approach override", 48.8121, 2.1391),
        },
      ];
      input.preferred_discovered_poi_ids = ["node/9739373333"];
    } else {
      input.waypoint_order = "optimize";
      input.waypoints = ["exact", "approach", "best_effort"].map(
        (strength, i) => ({
          id: "point-" + i,
          name: "Place " + i,
          coordinate: coord(
            "Place " + i,
            48.809 + i * 0.001,
            2.134 + i * 0.002,
          ),
          constraint_strength: strength,
          access_search_radius_m: 300,
          maximum_best_effort_distance_m:
            strength === "best_effort" ? 500 : null,
          approach_override:
            strength === "approach"
              ? coord("Approach override", 48.8101, 2.1361)
              : null,
        }),
      );
    }
    await load(input);
    const output = await snapshot();
    assert.deepEqual(output, input);
    const unsupported = await page.evaluate(async (request) => {
      try {
        const mod = await import("/static/local_planner.js");
        if (request.kind === "auto_tour")
          mod.validateLocalAutoTourPlanRequest(request);
        else {
          const { validateLocalWaypointRouteRequest } = await import(
            "/static/local_waypoint_route.js"
          );
          if (validateLocalWaypointRouteRequest)
            validateLocalWaypointRouteRequest(request);
        }
        return null;
      } catch (e) {
        return e.code || e.message;
      }
    }, output);
    records.push({ case: input.name, input, output, unsupported });
  }
  // This is the actual DOM restoration path, not merely switchPlanningMode in isolation.
  const a = fixture("auto_tour", "hike", "strict"),
    w = fixture("waypoint_route", "hike", "flexible");
  a.name = "strict-auto-draft";
  w.name = "blank-maximum-waypoint-draft";
  await load(a);
  await load(w);
  for (const mode of [
    "auto_tour",
    "waypoint_route",
    "auto_tour",
    "waypoint_route",
  ])
    await page.locator(`input[name="planning-mode"][value="${mode}"]`).check();
  const roundtrip = await snapshot();
  const preservation = {
    expected: w,
    actual: roundtrip,
    pass: require("util").isDeepStrictEqual(w, roundtrip),
  };
  fs.writeFileSync(
    O + "/requests-" + phase + ".json",
    JSON.stringify({ records, preservation }, null, 2),
  );
  console.log(
    records.length,
    "canonical requests",
    preservation.pass
      ? "roundtrip PASS"
      : "roundtrip FAIL: " + JSON.stringify(roundtrip.distance_objective),
  );
  await browser.close();
  if (phase === "after")
    assert(preservation.pass, "independent blank maximum survives switching");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
