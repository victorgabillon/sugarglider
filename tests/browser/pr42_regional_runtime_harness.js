import { createRegionalNativeClient, parseRegionalNativeReply } from "../../src/sugarglider/web/static/regional_native.js";
import { createRegionalPlanningContext } from "../../src/sugarglider/web/static/regional_planning.js";
import { regionalRoutingReference, captureRegionalRoutingReference } from "../../src/sugarglider/web/static/regional_routing_reference.js";
import { createLocalRoutingBridge } from "../../src/sugarglider/web/static/local_routing.js";
import { createLocalPlanner } from "../../src/sugarglider/web/static/local_planner.js";
import { publishLocalPlan } from "../../src/sugarglider/web/static/local_plan_publisher.js";
import { regionalBuildIdentity, RegionalDataError } from "../../src/sugarglider/web/static/regional_manifest.js";
import { syntheticRegionalReference } from "./regional_routing_fixture.js";
import { request, nativeReply } from "./pr41_normal_planner_harness.js";

export const publishedPlans = [];
const id = "a".repeat(32);
const capabilities = { enabled: true, installed_pack_count: 1, supported_profile_ids: ["hike", "city_bike"] };
const assert = (value, message) => { if (!value) throw new Error(message); };
const equal = (a, b, message) => assert(JSON.stringify(a) === JSON.stringify(b), message);
async function rejects(promise, code) {
  const error = await promise.then(() => null, (caught) => caught);
  equal(typeof error?.code === "string" ? error.code : error?.name, code, `Expected ${code}, got ${error?.code ?? error?.name}`);
}
const reply = (state, extra = {}) => ({ schema_version: 1, request_id: "web-page-1", type: "regional_routing_result",
  operation_id: id, state, received_bytes: 0, total_bytes: 0, code: null, ...extra });

function clientRig(handler, options = {}) {
  const calls = [];
  let clock = 0;
  const client = createRegionalNativeClient({ transport: { initialize: async () => true,
    request: async (type, fields, settings) => { calls.push({ type, fields });
      const value = await handler(type, fields, calls.length);
      return value === null ? null : settings.parseReply(JSON.stringify(value)); } }, randomId: () => id,
    pause: async () => { clock += 500; }, now: () => clock, ...options });
  return { client, calls };
}

export async function runPr42RegionalRuntimeHarness() {
  const cases = [];
  for (const mutation of [
    { extra: "private" }, { code: "private-source" }, { state: "started" }, { operation_id: "../other" },
    { total_bytes: 2 ** 31 + 1 }, { received_bytes: -1 }, { received_bytes: 1 }, { schema_version: 2 },
    { state: "failed", code: null },
  ]) assert(parseRegionalNativeReply(JSON.stringify({ ...reply("ready"), ...mutation })) === null, "strict native status boundary");
  assert(parseRegionalNativeReply(JSON.stringify(reply("failed", { code: "regional_checksum_mismatch" }))), "bounded failure accepted");
  cases.push("native_status_rejects_extra_fields_unknown_codes_and_invalid_counts");

  const captured = captureRegionalRoutingReference(structuredClone(syntheticRegionalReference));
  assert(Object.isFrozen(captured.archive) && Object.isFrozen(captured.bounds), "nested reference immutable");
  for (const mutation of [{ extra: "private" }, { pack_id: "../private" }, { build_id: "A".repeat(64) }, { bounds: [0, 1, 0, 1] },
    { archive: { ...captured.archive, byte_size: 513 } }]) {
    await rejects(Promise.resolve().then(() => captureRegionalRoutingReference({ ...captured, ...mutation })), "invalid_regional_routing_reference");
  }
  cases.push("reference_is_immutable_strict_and_archive_aligned");

  let checks = 0;
  const wire = [];
  const base = createLocalRoutingBridge({ transport: { nativeAvailable: true,
    initialize: async () => JSON.stringify({ schema_version: 1, request_id: "web-page-1", type: "hello_result",
      outing_slug: null, participant_id: null, active: false, state: "stopped", last_published_at: null,
      pending_sample: false, stop_warning: null }),
    request: async (type, fields) => { wire.push({ type, fields }); return type === "get_local_route_capabilities"
      ? { type: "local_route_capabilities_result" } : { type: "local_route_failure", code: "no_route" }; }, cancelOwner() {} } });
  equal(await base.route({ profile: "hike", points: [] }), null, "unbound bridge never routes");
  equal(wire, [], "unbound bridge has no implicit graph selection");
  const selected = base.forRegion(captured);
  await selected.capabilities();
  await selected.route({ profile: "city_bike", points: [{ lat: 48, lon: 2 }, { lat: 48.1, lon: 2.1 }] });
  equal(wire.map((item) => item.fields.regional_reference), [captured, captured], "every capability/route call carries same version");
  equal(wire[1].fields.route_version, 3, "v2 never sent");
  cases.push("unbound_bridge_does_not_route_and_bound_calls_preserve_version");

  const progress = [];
  let rig = clientRig((type) => type === "regional_routing_install"
    ? reply("running", { total_bytes: 512 }) : reply(++checks === 1 ? "running" : "ready", { received_bytes: checks === 1 ? 256 : 512, total_bytes: 512 }));
  equal(await rig.client.install(captured, "https://packs.example/manifest.json", { onProgress: (bytes) => progress.push(bytes) }), { status: "ready" }, "install waits for native acknowledgement");
  equal(progress, [0, 256, 512], "bounded archive byte progress");
  assert(rig.calls.every(({ fields }) => !Object.hasOwn(fields, "participant_token")), "no participant authority");
  cases.push("native_install_polls_definite_completion_with_byte_progress");

  const controller = new AbortController();
  let cleaned = false;
  rig = clientRig((type) => {
    if (type === "regional_routing_install") { controller.abort(); return reply("running"); }
    if (type === "regional_routing_cancel") return reply("running");
    cleaned = true; return reply("failed", { code: "regional_install_cancelled" });
  });
  await rejects(rig.client.install(captured, "https://packs.example/manifest.json", { signal: controller.signal }), "regional_install_cancelled");
  assert(cleaned && rig.calls.length === 3, "cancel drains native worker before rejection");
  cases.push("cancel_retains_operation_until_native_cleanup_finishes");

  rig = clientRig((type) => type === "regional_routing_inspect" ? null
    : reply("failed", { code: "regional_routing_unavailable" }));
  await rejects(rig.client.inspect(captured), "regional_native_outcome_uncertain");
  equal(rig.calls.map((call) => call.type), ["regional_routing_inspect", "regional_routing_cancel"], "uncertain start is cancelled without assuming rollback");
  cases.push("lost_start_reply_never_authorizes_destructive_cleanup");

  rig = clientRig(() => reply("running"), { now: () => 0, pause: async () => { throw new RegionalDataError("test_pause_stop"); } });
  await rejects(rig.client.inspect(captured, { signal: AbortSignal.abort() }), "AbortError");
  equal(rig.calls.length, 0, "preabort performs no native work");
  let elapsed = 0;
  rig = clientRig(() => reply("running"), { now: () => (elapsed += 32 * 60 * 1000) });
  await rejects(rig.client.inspect(captured), "regional_native_outcome_uncertain");
  cases.push("preabort_and_bounded_uncertain_transport_are_explicit");

  const fixture = await (await fetch("../fixtures/pr40_regional_data.json")).json();
  const manifest = structuredClone(fixture.manifest);
  manifest.components.routing.files[1].byte_size = 512;
  manifest.build_id = await regionalBuildIdentity(manifest);
  const reference = await regionalRoutingReference(manifest);
  let rows = [{ region_id: manifest.region_id, manifest, status: "committed" }], selection = null, owned = false;
  const session = { identity: { region_id: manifest.region_id, build_id: manifest.build_id, routing_pack_id: reference.pack_id } };
  const nativeCalls = [], validations = [];
  const versions = { withCommittedRegions: async (run) => { assert(!owned, "one lease"); owned = true;
    try { return await run(rows); } finally { owned = false; } },
  committedDirectory: async (regionId, buildId) => { assert(owned, "directory read under lease");
    equal([regionId, buildId], [manifest.region_id, manifest.build_id], "strict chosen directory"); return { kind: "directory" }; } };
  const withRegion = createRegionalPlanningContext({ versions, selectedRegionId: () => selection,
    inspectNative: async (ref) => { equal(ref, reference, "inspect chosen reference"); validations.push("routing"); return { status: "ready" }; },
    components: async () => ({ verifyMap: async () => { validations.push("map"); return true; } }),
    regionClient: { loadVersion: async () => { validations.push("indexes"); return session; } },
    bridge: { forRegion: (ref) => ({ capabilities: async () => capabilities, route: async (input) => {
      assert(owned, "native route retains whole-region lease"); nativeCalls.push(ref);
      return { ...nativeReply(input), pack_id: ref.pack_id }; } }) },
  });
  await withRegion(async (region) => {
    assert(owned, "context callback owns commit"); equal(await region.getRegionData("wrong-pack"), null, "no cross-region index fallback");
    equal(await region.getRegionData(reference.pack_id), session, "matching index session only");
  });
  assert(!owned, "lease released after callback");
  equal(validations, ["routing", "map", "indexes"], "all components checked before callback");
  cases.push("selected_context_validates_all_components_and_exact_index_identity");

  for (const [snapshot, explicit, code] of [
    [[], null, "regional_required"], [[...rows, { ...rows[0], region_id: "second" }], null, "regional_selection_required"],
    [rows, "missing", "regional_required"], [[{ ...rows[0], status: "unavailable", code: "regional_install_incomplete" }], manifest.region_id, "regional_install_incomplete"],
  ]) {
    const before = validations.length, originalRows = rows; rows = snapshot; selection = explicit;
    await rejects(withRegion(async () => { throw new Error("unavailable context must not run"); }), code);
    equal(validations.length, before, "no alternate region tried"); rows = originalRows;
  }
  selection = manifest.region_id;
  cases.push("missing_ambiguous_or_broken_selection_never_chooses_another_region");

  const badSession = session.identity; session.identity = { ...badSession, build_id: "f".repeat(64) };
  await rejects(withRegion(async () => {}), "regional_identity_mismatch"); session.identity = badSession;
  cases.push("index_version_mismatch_fails_before_native_route");

  // Real canonical publication worker; native geometry remains a synthetic fixture.
  const planner = createLocalPlanner({ withRegion, lifecycleTarget: null });
  const source = request("waypoint_route");
  const result = await planner.generate(source);
  const provenance = { region_id: reference.region_id, build_id: reference.build_id, routing_pack_id: reference.pack_id };
  equal(result.search_diagnostics.details.local_planning.regional_version, provenance, "canonical search provenance");
  equal(result.candidates[0].diagnostics.details.local_routing.regional_version, provenance, "stored candidate provenance");
  assert(nativeCalls.length > 0 && nativeCalls.every((ref) => ref === nativeCalls[0]), "one version through whole search");
  assert(!owned && Object.isFrozen(result.candidates[0]), "published snapshot immutable after lease released");
  publishedPlans.push({ request: source, result });
  planner.invalidate();
  cases.push("canonical_worker_preserves_region_version_in_results_and_candidates");

  const wrongPack = createLocalPlanner({ lifecycleTarget: null,
    withRegion: (run) => run({ reference, getRegionData: async () => null,
      bridge: { capabilities: async () => capabilities, route: async (input) => nativeReply(input) } }) });
  await rejects(wrongPack.generate(source), "routing_pack_identity_changed");
  wrongPack.invalidate();
  cases.push("canonical_publication_rejects_native_pack_different_from_committed_reference");

  let finishPublish, publishEntered = false;
  const controlled = createLocalPlanner({ withRegion, lifecycleTarget: null, publisher: {
    publish: async (...args) => { publishEntered = true; assert(owned, "publication keeps lease");
      await new Promise((resolve) => { finishPublish = resolve; }); return publishLocalPlan(...args); }, invalidate() {},
  } });
  const active = controlled.generate(source);
  while (!publishEntered) await new Promise((resolve) => setTimeout(resolve, 0));
  assert(owned, "lease lasts through delayed publication");
  const cancelled = rejects(active, "AbortError"); controlled.invalidate();
  await rejects(controlled.generate(source), "local_generation_busy");
  assert(owned, "invalidation cannot release incomplete publication"); finishPublish(); await cancelled;
  assert(!owned, "definite finalizer releases lease");
  cases.push("cancellation_retains_commit_lease_through_publication_and_drain");
  return cases;
}
