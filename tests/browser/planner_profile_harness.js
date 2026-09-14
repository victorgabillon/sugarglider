import { createPlannerProfilePreference, DEFAULT_PLANNER_PROFILE, initialLocalPlannerProfile } from "../../src/sugarglider/web/static/planner_profile.js";
import { PUBLIC_LOCAL_ROUTE_PROFILES } from "../../src/sugarglider/web/static/local_routing.js";
import { createMemoryPwaStore, PWA_STORES } from "../../src/sugarglider/web/static/pwa_store.js";
import { generationAvailability } from "../../src/sugarglider/web/static/state.js";

export async function runPlannerProfileHarness() {
  const cases = [];
  // Reverse the catalog so a first-option implementation fails.
  const statuses = (ids) => [...PUBLIC_LOCAL_ROUTE_PROFILES].reverse().map((id) => ({ profile: { id }, available: ids.includes(id) }));
  const all = statuses(PUBLIC_LOCAL_ROUTE_PROFILES), none = statuses([]);
  equal(DEFAULT_PLANNER_PROFILE, "trail_run", "explicit product default");
  equal(initialLocalPlannerProfile(null, all), "trail_run", "fresh default ignores catalog order");
  cases.push("fresh_local_startup_explicit_trail_run_default");
  equal(initialLocalPlannerProfile(initialLocalPlannerProfile(null, none), all), "trail_run", "ready refresh fills absent choice");
  cases.push("readiness_refresh_initializes_only_absent_choice");
  for (const id of PUBLIC_LOCAL_ROUTE_PROFILES) {
    equal(initialLocalPlannerProfile(id, all), id, "explicit choice retained");
    equal(initialLocalPlannerProfile(id, none), id, "unavailable explicit choice retained");
  }
  cases.push("all_explicit_choices_retained_during_rerender_and_temporary_unavailability");
  equal(initialLocalPlannerProfile(null, statuses(["hike", "gravel_bike"])), "hike", "stable fallback");
  equal(initialLocalPlannerProfile(null, statuses(["road_bike", "gravel_bike"])), "gravel_bike", "supported fallback order");
  equal(initialLocalPlannerProfile(null, [{ profile: { id: "unknown" }, available: true }]), null, "unknown never selected");
  cases.push("deterministic_supported_fallback_without_trail_run");
  const profile = initialLocalPlannerProfile(null, none);
  equal(profile, null, "none supported");
  equal(generationAvailability({ planningMode: "auto_tour", routeTopology: "loop", start: { lat: 48.87, lon: 2.1 }, end: null,
    mandatoryPointCount: 1, pointValidationMessage: "", profileAvailable: none.some((row) => row.profile.id === profile && row.available) }),
  { enabled: false, reason: "The selected routing profile is unavailable." }, "availability unchanged");
  cases.push("no_supported_activity_still_blocks_generate");
  const store = createMemoryPwaStore();
  const preference = createPlannerProfilePreference(store);
  equal(await preference.restore(), null, "fresh storage");
  initialLocalPlannerProfile(null, all);
  equal(await preference.restore(), null, "implicit default never persists");
  for (const id of PUBLIC_LOCAL_ROUTE_PROFILES) {
    await preference.remember(id);
    equal(await createPlannerProfilePreference(store).restore(), id, "restart preserves explicit identity");
  }
  cases.push("all_explicit_preferences_restore_across_restart_without_persisting_defaults");
  await Promise.all([preference.remember("hike"), preference.remember("gravel_bike"), preference.remember("road_bike")]);
  equal(await preference.restore(), "road_bike", "last rapid choice wins");
  equal(await preference.remember("unknown"), false, "unsupported persistence rejected");
  equal(await preference.restore(), "road_bike", "invalid choice cannot replace valid record");
  cases.push("ordered_rapid_writes_and_unsupported_preference_rejection");
  await store.put(PWA_STORES.publicRuntime, "planner-routing-profile", { schema_version: 1, profile: "unknown" });
  equal(await preference.restore(), null, "corrupt preference ignored");
  await store.put(PWA_STORES.publicRuntime, "planner-routing-profile", { schema_version: 2, profile: "hike" });
  equal(await preference.restore(), null, "unsupported version ignored");
  const broken = createPlannerProfilePreference({ get: async () => { throw new Error("read failure"); }, put: async () => { throw new Error("quota"); } });
  equal(await broken.restore(), null, "optional storage read failure");
  equal(await broken.remember("hike"), false, "optional write failure");
  equal(await broken.remember("gravel_bike"), false, "failed write does not poison queue");
  cases.push("invalid_records_and_optional_storage_failure_do_not_block_planning");
  return cases;
}
function equal(actual, expected, label) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error(`${label}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`);
}
