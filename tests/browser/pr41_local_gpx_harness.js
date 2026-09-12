import {
  exportCanonicalCandidate, fixedCoordinate, localGpxFilename, LocalGpxExportError,
  MAX_GPX_STOPS, MAX_GPX_VERTICES,
} from "../../src/sugarglider/web/static/local_gpx_export.js";
import { PUBLIC_PROFILE_METADATA } from "../../src/sugarglider/web/static/public_profile_metadata.js";

export async function runPr41LocalGpxHarness() {
  const fixture = await (await fetch("/tests/fixtures/pr41_local_gpx.json")).json();
  const candidate = () => structuredClone(fixture.candidate);
  const scenarios = [];
  for (const [name, run] of [
    ["canonical_python_gpx_fields_and_clean_single_track", async () => {
      const { document } = await exported(candidate());
      equal(projection(document), fixture.expected, "Python canonical GPX fields");
      equal(document.querySelectorAll("trk").length, 1, "one track");
      equal(document.querySelectorAll("trkseg").length, 1, "one segment");
      equal(document.querySelectorAll("rte, extensions, ele, time").length, 0, "no invented extensions/elevation/timestamps");
    }],
    ["all_six_public_profiles_preserved", async () => {
      equal(Object.keys(PUBLIC_PROFILE_METADATA).sort(), ["city_bike", "gravel_bike", "hike", "mountain_bike", "road_bike", "trail_run"], "exact public IDs");
      for (const profile of Object.values(PUBLIC_PROFILE_METADATA)) {
        const input = candidate(); input.routing_profile = input.route.routing_profile = profile.id;
        const { document } = await exported(input);
        equal(document.querySelector("trk > name").textContent, `${input.route.name} — ${profile.display_name}`, "profile name");
        equal(document.querySelector("trk > type").textContent, {walking:"hiking",running:"running",cycling:"cycling"}[profile.activity_kind], "activity type");
      }
      assert(Object.isFrozen(PUBLIC_PROFILE_METADATA.hike.capabilities), "generated metadata immutable");
    }],
    ["no_network_or_input_mutation", async () => {
      const input = candidate(), before = JSON.stringify(input), previous = globalThis.fetch;
      try {
        globalThis.fetch = () => { throw new Error("Export attempted a network request"); };
        freeze(input);
        await exported(input);
        equal(JSON.stringify(input), before, "canonical candidate unchanged");
      } finally { globalThis.fetch = previous; }
    }],
    ["reached_and_approximated_stops_interleave_in_visit_order", async () => {
      const { document } = await exported(candidate());
      const stops = [...document.querySelectorAll("wpt")];
      equal(stops.map((stop) => stop.querySelector("name").textContent), ["1. Forêt <ouverte> — approximate", "2. Étape & source"], "actual visit order");
      const approach = fixture.candidate.approximated_stops[0].resolved_approach.coordinate;
      equal(Number(stops[0].getAttribute("lat")), approach.lat, "routed approach, not semantic place");
    }],
    ["dropped_stops_and_private_extra_fields_never_exported", async () => {
      const input = candidate();
      input.dropped_stops.push({id:"dropped",name:"SECRET_DROPPED"});
      input.diagnostics.details.private_test = "SECRET_DIAGNOSTIC";
      input.route.extra_test = "SECRET_EXTRA";
      const { xml } = await exported(input);
      assert(!xml.includes("SECRET_"), "only GPX field allowlist");
      equal(new DOMParser().parseFromString(xml, "application/xml").querySelectorAll("wpt").length, 2, "dropped stop omitted");
    }],
    ["python_float_rounding_including_negative_zero_and_even_ties", () => {
      for (const { value, formatted } of fixture.coordinates) equal(fixedCoordinate(value), formatted, "Python .8f");
      equal(fixedCoordinate(-0), "-0.00000000", "negative zero retained");
    }],
    ["unicode_filename_and_xml_cleaning", async () => {
      for (const { name, filename } of fixture.filenames) equal(localGpxFilename(name), filename, "Python attachment filename");
      const input = candidate(); input.route.name = 'Water & <woods> "été"\u0000\u0009\uFFFE\uFFFF\uD800';
      const { document } = await exported(input);
      equal(document.querySelector("metadata > name").textContent, 'Water & <woods> "été" — Hike', "XML controls/surrogates removed; text escaped");
    }],
    ["forged_arrival_and_reported_distance_rejected", () => {
      const far = candidate(); far.reached_stops[0].resolved_approach.coordinate.lat += 1;
      rejects(() => exportCanonicalCandidate(far), "export_stop_not_reached");
      const falseMeasurement = candidate(); falseMeasurement.reached_stops[0].route_to_approach_m = 3;
      rejects(() => exportCanonicalCandidate(falseMeasurement), "export_stop_not_reached");
    }],
    ["arrival_just_inside_and_outside_tolerance", async () => {
      for (const offset of [24.99, 25.01]) {
        const input = candidate(); input.approximated_stops = [];
        input.route.geometry = [[2, 48], [2.01, 48]];
        const stop = input.reached_stops[0];
        stop.resolved_approach.coordinate = {lon:2.005,lat:48+offset/6_371_008.8*180/Math.PI};
        stop.route_to_approach_m = offset;
        if (offset < 25) await exported(input);
        else rejects(() => exportCanonicalCandidate(input), "export_stop_not_reached");
      }
    }],
    ["invalid_approximation_is_explicit", () => {
      for (const change of [{distance_m:20}, {distance_m:501}, {normal_tolerance_m:NaN}, {configured_maximum_m:-1}]) {
        const input = candidate(); Object.assign(input.approximated_stops[0], change);
        rejects(() => exportCanonicalCandidate(input), "invalid_export_approximation");
      }
    }],
    ["invalid_profile_and_identity_never_fall_back", () => {
      for (const id of ["foot", "bike", "constructor", "unknown", null]) {
        const input = candidate(); input.routing_profile = input.route.routing_profile = id;
        rejects(() => exportCanonicalCandidate(input), "invalid_export_profile");
      }
      const mismatch = candidate(); mismatch.routing_profile = "road_bike";
      rejects(() => exportCanonicalCandidate(mismatch), "invalid_export_profile");
    }],
    ["invalid_geometry_and_segment_breaks_never_repaired", () => {
      for (const geometry of [[], [[2,48]], [[2,48],[NaN,48]], [[2,48],[181,48]], [[2,48],null,[3,48]], [[[2,48],[3,48]],[[4,48],[5,48]]]]) {
        const input = candidate(); input.route.geometry = geometry;
        rejects(() => exportCanonicalCandidate(input), "invalid_export_geometry");
      }
    }],
    ["bounded_vertices_stops_and_arrival_work", () => {
      const tooMany = candidate(); tooMany.route.geometry = Array(MAX_GPX_VERTICES+1).fill([2,48]);
      rejects(() => exportCanonicalCandidate(tooMany), "invalid_export_geometry");
      const stops = candidate(); stops.reached_stops = Array(MAX_GPX_STOPS+1).fill(stops.reached_stops[0]);
      rejects(() => exportCanonicalCandidate(stops), "export_limit_exceeded");
      const work = candidate(); work.route.geometry = Array(MAX_GPX_VERTICES).fill([2,48]);
      work.reached_stops = Array(20).fill(work.reached_stops[0]);
      rejects(() => exportCanonicalCandidate(work), "export_limit_exceeded");
    }],
    ["duplicate_or_conflicting_stop_outcomes_rejected", () => {
      const duplicate = candidate(); duplicate.reached_stops.push(duplicate.reached_stops[0]);
      rejects(() => exportCanonicalCandidate(duplicate), "invalid_export_stops");
      const conflict = candidate(); conflict.dropped_stops.push({id:conflict.reached_stops[0].id});
      rejects(() => exportCanonicalCandidate(conflict), "invalid_export_stops");
    }],
  ]) { await run(); scenarios.push(name); }
  return scenarios;
}

async function exported(input) {
  const { blob, filename } = exportCanonicalCandidate(input);
  equal(blob.type, "application/gpx+xml", "GPX MIME");
  const xml = await blob.text();
  const document = new DOMParser().parseFromString(xml, "application/xml");
  assert(!document.querySelector("parsererror"), "valid XML");
  equal(document.documentElement.namespaceURI, "http://www.topografix.com/GPX/1/1", "GPX namespace");
  return { xml, document, filename };
}
function projection(document) {
  return {name:document.querySelector("metadata > name").textContent, description:document.querySelector("metadata > desc").textContent,
    type:document.querySelector("trk > type").textContent,
    points:[...document.querySelectorAll("trkpt")].map(coordinate),
    waypoints:[...document.querySelectorAll("wpt")].map((point)=>({coordinate:coordinate(point),name:point.querySelector("name").textContent,
      description:point.querySelector("desc").textContent,type:point.querySelector("type").textContent}))};
}
function coordinate(element) { return {lat:element.getAttribute("lat"),lon:element.getAttribute("lon")}; }
function freeze(value) { if(value && typeof value === "object") {Object.values(value).forEach(freeze);Object.freeze(value);} }
function rejects(run, code) { let error; try { run(); } catch (caught) { error=caught; } assert(error instanceof LocalGpxExportError && error.code===code, `expected ${code}; got ${error}`); }
function assert(value, message) { if (!value) throw new Error(message); }
function equal(actual, expected, message) { assert(JSON.stringify(actual)===JSON.stringify(expected), `${message}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`); }
