import { createRegionalPlanningContext } from "../../src/sugarglider/web/static/regional_planning.js";
import { regionalRoutingReference } from "../../src/sugarglider/web/static/regional_routing_reference.js";
import { RegionalDataError } from "../../src/sugarglider/web/static/regional_manifest.js";
import { createLocalPlanner } from "../../src/sugarglider/web/static/local_planner.js";
import { createLocationSearch } from "../../src/sugarglider/web/static/location_search.js";
import { PUBLIC_LOCAL_ROUTE_PROFILES } from "../../src/sugarglider/web/static/local_routing.js";
import { request } from "./pr41_normal_planner_harness.js";

const assert = (value, message) => { if (!value) throw Error(message); };
async function rejects(operation, code) {
  const error = await operation.then(() => null, caught => caught);
  assert(error?.code === code, `Expected ${code}, got ${error?.code}`);
}

export async function run() {
  const fixture = await (await fetch("../fixtures/pr40_regional_data.json")).json();
  const manifest = fixture.manifest, reference = await regionalRoutingReference(manifest);
  const originalFetch = globalThis.fetch, cases = [];
  let remoteCalls = 0;
  globalThis.fetch = async () => { remoteCalls += 1; throw Error("All HTTP denied by this test"); };
  try {
    const committed = { region_id: manifest.region_id, status: "committed", manifest };
    const identity = { region_id: manifest.region_id, build_id: manifest.build_id, routing_pack_id: reference.pack_id };
    let rows = [committed], selection = manifest.region_id, nativeReady = true, brokenMap = false;
    let brokenIndex = false, wrongIdentity = false, callbacks = 0;
    const inspected = [];
    const withRegion = createRegionalPlanningContext({
      versions: { withCommittedRegions: callback => callback(rows), committedDirectory: async () => ({}) },
      selectedRegionId: () => selection,
      inspectNative: async value => { inspected.push(value); return nativeReady ? { status: "ready" } : { status: "failed", code: "regional_routing_unavailable" }; },
      components: async () => ({ verifyMap: async () => { if (brokenMap) throw new RegionalDataError("map_pack_unavailable"); } }),
      regionClient: { loadVersion: async () => {
        if (brokenIndex) throw new RegionalDataError("local_index_invalid");
        return { identity: wrongIdentity ? { ...identity, build_id: "f".repeat(64) } : identity };
      } },
      bridge: { forRegion: value => { assert(value.build_id === manifest.build_id, "Only the selected installed graph"); return {}; } },
    });
    await withRegion(async region => { callbacks += 1; assert((await region.getRegionData(reference.pack_id)).identity === identity, "Exact local index"); });
    assert(callbacks === 1 && remoteCalls === 0, "Verified installed context needs no server");
    cases.push("installed_context_with_all_http_denied");
    rows = [];
    await rejects(withRegion(async () => { callbacks += 1; }), "regional_required");
    rows = [{ ...committed, status: "unavailable", code: "regional_install_incomplete" }];
    await rejects(withRegion(async () => { callbacks += 1; }), "regional_install_incomplete");
    rows = [committed, { ...committed, region_id: "second" }]; selection = null;
    await rejects(withRegion(async () => { callbacks += 1; }), "regional_selection_required");
    assert(callbacks === 1 && inspected.length === 1, "No alternate graph inspected for missing or ambiguous data");
    cases.push("missing_incomplete_and_ambiguous_region_fail_locally");
    rows = [committed]; selection = manifest.region_id;
    nativeReady = false;
    await rejects(withRegion(async () => { callbacks += 1; }), "regional_routing_unavailable");
    nativeReady = true; brokenMap = true;
    await rejects(withRegion(async () => { callbacks += 1; }), "map_pack_unavailable");
    brokenMap = false; brokenIndex = true;
    await rejects(withRegion(async () => { callbacks += 1; }), "local_index_invalid");
    brokenIndex = false; wrongIdentity = true;
    await rejects(withRegion(async () => { callbacks += 1; }), "regional_identity_mismatch");
    assert(callbacks === 1 && remoteCalls === 0, "Required-data failures cannot publish or download substitutes");
    cases.push("required_map_routing_and_index_failures_never_fall_back");
    cases.push("immutable_source_mismatch_rejected_before_planning");

    for (const profile of PUBLIC_LOCAL_ROUTE_PROFILES) {
      let calls = 0;
      const planner = createLocalPlanner({ lifecycleTarget: null, bridge: {
        capabilities: async () => ({ enabled: true, installed_pack_count: 1, supported_profile_ids: PUBLIC_LOCAL_ROUTE_PROFILES }),
        route: async input => { calls += 1; assert(input.profile === profile, "Public profile preserved");
          return { schema_version: 1, request_id: "synthetic", type: "local_route_failure", code: "no_covering_routing_pack" }; },
      } });
      try {
        const result = await planner.generate(request("waypoint_route", profile));
        assert(result.candidates.length === 0 && calls === 1, "No server, straight line or weakened retry");
        assert(result.search_diagnostics.details.local_planning.failure_code === "no_covering_routing_pack", "Truthful coverage failure");
      } finally { planner.invalidate(); }
    }
    assert(remoteCalls === 0, "No HTTP routing fallback on any public profile");
    cases.push("six_profiles_outside_coverage_without_remote_retry");

    let onlineAttempts = 0;
    const search = createLocationSearch({ config: () => ({ available: true, provider: "ign_geoplateforme", endpoint: "https://data.geopf.fr/geocodage/search" }),
      localSearch: async () => ({ available: true, results: [{ name: "Synthetic local place", lat: 48, lon: 2 }] }),
      fetcher: async () => { onlineAttempts += 1; throw Error("Network denied"); }, online: () => false });
    assert(onlineAttempts === 0, "Opening the client does not perform online acquisition");
    const found = await search.searchResolvedLocations("Synthetic");
    assert(found.local.length === 1 && found.remote.length === 0 && found.remoteMessage.includes("offline"), "Local Places remain useful with visible online failure");
    assert(onlineAttempts === 0 && remoteCalls === 0, "No implicit remote attempt while offline");
    cases.push("offline_places_search_with_explicit_online_unavailability");
    return cases;
  } finally { globalThis.fetch = originalFetch; }
}
