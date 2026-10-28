import { createPlannerMapStore, plannerMapOffers, ILE_DE_FRANCE_MAP } from "../../src/sugarglider/web/static/planner_map_store.js";
import { MapPackStore } from "../../src/sugarglider/web/static/map_pack_store.js";
import { createRegionalMapStore } from "../../src/sugarglider/web/static/regional_map_store.js";
import { createRegionVersionStore } from "../../src/sugarglider/web/static/region_versions.js";
import { createOfflineMapRuntime } from "../../src/sugarglider/web/static/offline_map.js";
import { selectMapPackForCoordinate } from "../../src/sugarglider/web/static/map_pack_manifest.js";
import { seedRegion } from "./region_preference_harness.js";
import { manifest, tinyPmtiles, createFakeMap } from "./pr36_offline_maps_harness.js";

const assert = (v, message) => { if (!v) throw Error(message); };
const equal = (a, b, message) => assert(JSON.stringify(a) === JSON.stringify(b), `${message}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`);
async function rejects(action, code) {
  const error = await action().then(() => null, value => value);
  equal(error?.code ?? error?.name, code, "explicit failure");
}
const digest = async bytes => ({ byte_size: bytes.byteLength,
  sha256: Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("") });
async function until(check) { for (let i = 0; i < 500; i++) {
  if (check()) return; await new Promise(resolve => setTimeout(resolve, 10));
} throw Error("Map controls did not settle"); }

export async function runPlannerMapStoreHarness() {
  const cases = [], origin = await navigator.storage.getDirectory(), name = `planner-maps-${crypto.randomUUID()}`;
  const root = await origin.getDirectoryHandle(name, { create: true });
  const storage = { getDirectory: async () => root };
  const versions = createRegionVersionStore({ storage });
  const fixture = await (await fetch("/tests/fixtures/pr40_regional_data.json")).json();
  let mode = "good", requests = [], slowPending = false;
  const bounds = [-.1, -.1, .1, .1], archive = tinyPmtiles(bounds, 0, 14);
  const map = manifest("synthetic-independent", bounds, archive.byteLength);
  const text = new TextEncoder().encode(JSON.stringify(map));
  const offer = { pack_id: map.pack_id, display_name: map.display_name,
    manifest_url: "https://packs.example/maps/synthetic-independent/manifest.json",
    manifest: await digest(text), archive: await digest(archive) };
  const fetchRequest = async (url, options) => {
    requests.push({ url, options });
    const isManifest = url === offer.manifest_url;
    assert(isManifest || url === new URL("basemap.pmtiles", offer.manifest_url).href, "only trusted static files requested");
    options.signal?.throwIfAborted();
    if (isManifest && mode === "slow-manifest") {
      slowPending = true;
      await new Promise((_, reject) => options.signal.addEventListener("abort", () => reject(new DOMException("Cancelled", "AbortError")), { once: true }));
    }
    if (!isManifest && mode === "missing") return new Response(null, { status: 404 });
    if (!isManifest && mode === "interrupted") return new Response(new ReadableStream({ start(c) {
      c.enqueue(archive.slice(0, 32)); c.error(Error("Disconnected"));
    } }));
    const bytes = (isManifest ? text : archive).slice();
    if ((isManifest && mode === "manifest-mismatch") || (!isManifest && mode === "checksum-mismatch")) bytes[bytes.length - 2] ^= 1;
    return new Response(bytes);
  };
  const independent = () => new MapPackStore({ storageManager: storage, fetchRequest });
  let separate = independent();
  const regional = createRegionalMapStore({ versions, selectedRegionId: () => "yvelines",
    includeAllCommittedMaps: true, probe: separate });
  const compose = (store = separate) => createPlannerMapStore({ regional, independent: store,
    offers: [offer], loadOffers: async () => [offer] });
  let composed = compose();
  try {
    equal(await plannerMapOffers({ loadCatalog: async () => [] }), [], "production has no private download offer");
    equal(await plannerMapOffers({ loadCatalog: async () => [{ manifest_url: "https://evil.example/regions/test/manifest.json" }] }), [], "untrusted catalog origin cannot offer map");
    equal(await plannerMapOffers({ loadCatalog: async () => [{ manifest_url: "https://localhost:9444/regions/test/manifest.json" }] }), [ILE_DE_FRANCE_MAP], "only pinned private distribution offers full map");
    equal(ILE_DE_FRANCE_MAP.archive, { byte_size: 243080284, sha256: "eeea1321da3641ebb867473114bcd3706cb0d9f0b6ab2692baaf51058230b7a9" }, "reviewed artifact identity");
    cases.push("trusted_offer_requires_matching_private_distribution_and_pinned_full_sha256");

    await seedRegion(fixture, versions, "marly", "Marly");
    await seedRegion(fixture, versions, "yvelines", "Yvelines");
    const before = await versions.list();
    await composed.loadOffers();
    let scan = await composed.scanInstalledPacks();
    equal(scan.packs.length, 2, "all complete regional maps available without copies or routing switch");
    equal(regional.selectedMapBounds(), fixture.manifest.bounds, "routing selection remains independent");
    for (const pack of scan.packs) assert((await composed.openPackSource(pack.pack_id)).source, "shared regional bounded reader");
    const marly = before.find(row => row.region_id === "marly").manifest;
    await versions.withCommittedRegions(async () => {
      await rejects(() => regional.verifyMap(marly), "regional_version_changed");
      const directory = await versions.committedDirectory(marly.region_id, marly.build_id);
      equal(await regional.verifyMap(marly, directory), true, "automatic selection verifies its leased directory");
    });
    cases.push("all_committed_maps_read_under_existing_lease_without_weakening_planning_selection");

    await rejects(() => composed.installPack("https://evil.example/manifest.json"), "map_pack_untrusted");
    equal(requests.length, 0, "arbitrary URL rejected before download");
    for (const [failure, code] of [["manifest-mismatch", "regional_checksum_mismatch"], ["checksum-mismatch", "regional_checksum_mismatch"],
      ["missing", "map_pack_install_failed"], ["interrupted", "map_pack_install_failed"]]) {
      mode = failure;
      await rejects(() => composed.installPack(offer.manifest_url), code);
      scan = await composed.scanInstalledPacks();
      equal(scan.packs.length, 2, "failed install preserves complete maps");
      equal(scan.partial_pack_ids, [], "failed write drained and cleaned");
    }
    cases.push("manifest_and_same_size_archive_checksum_missing_and_interrupted_download_fail_closed");

    mode = "good";
    const controller = new AbortController();
    await rejects(() => composed.installPack(offer.manifest_url, { signal: controller.signal,
      onProgress: () => controller.abort() }), "map_pack_download_cancelled");
    equal((await composed.scanInstalledPacks()).packs.length, 2, "cancellation cannot activate partial map");
    cases.push("cancelled_stream_cannot_activate_or_replace_complete_regions");

    const standaloneRoot = await root.getDirectoryHandle("sugarglider-map-packs");
    const partial = await standaloneRoot.getDirectoryHandle(offer.pack_id, { create: true });
    const writePartial = await (await partial.getFileHandle("basemap.pmtiles", { create: true })).createWritable();
    await writePartial.write(archive.slice(0, 32)); await writePartial.close();
    separate = independent(); composed = compose(); await composed.loadOffers();
    equal((await composed.scanInstalledPacks()).partial_pack_ids, [offer.pack_id], "restart exposes interrupted install");
    await composed.installPack(offer.manifest_url);
    scan = await composed.scanInstalledPacks(); equal(scan.packs.length, 3, "explicit reinstall recovers incomplete archive");
    assert(requests.every(({ options }) => options.credentials === "omit" && options.redirect === "error" && options.cache === "no-store"), "no credentials, redirects or cache");
    cases.push("restart_ignores_incomplete_pack_and_explicit_install_recovers_without_database");

    equal(selectMapPackForCoordinate(scan.packs, { lon: .01, lat: .01 }).pack_id, "marly-map", "smallest covering map wins with deterministic tie");
    equal(selectMapPackForCoordinate(scan.packs, { lon: .08, lat: .08 }).pack_id, offer.pack_id, "broad map covers outside routing region");
    const controls = document.createElement("div");
    controls.innerHTML = '<ul></ul><form><select><option></option></select><input value="https://evil.example/manifest.json"><button type="submit">Install</button><button type="button">Cancel</button></form>';
    const form = controls.querySelector("form"), packageInput = controls.querySelector("select"), installButton = form.querySelector("button");
    const cancelButton = form.querySelector('button[type="button"]');
    packageInput.options[0].value = offer.manifest_url;
    let managed = 0;
    const runtime = createOfflineMapRuntime({ store: composed, maplibregl: { addProtocol() {} },
      browserWindow: new EventTarget(), confirmRemoval: () => true, onManageRegions: () => managed++,
      elements: { list: controls.querySelector("ul"), form, packageInput, installButton,
        urlInput: controls.querySelector("input"), cancelButton } });
    await runtime.initialize();
    const fake = createFakeMap({ lon: .08, lat: .08 });
    await runtime.attachMap(fake, { offline_mode: true });
    equal(runtime.snapshot().active_pack_id, offer.pack_id, "existing MapLibre/PMTiles path displays independent map");
    await runtime.applyForCoordinate({ lon: .01, lat: .01 });
    equal(runtime.snapshot().active_pack_id, "marly-map", "small complete map takes deterministic priority");
    runtime.detachMap(fake);
    cases.push("overlapping_maps_use_smallest_coverage_and_existing_single_source_runtime");

    controls.querySelector("li button").click(); equal(managed, 1, "complete maps lead to region manager");
    await runtime.remove(offer.pack_id);
    mode = "slow-manifest";
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await until(() => slowPending);
    assert(!cancelButton.disabled, "Cancel remains usable inside the disabled installation form");
    cancelButton.click();
    await until(() => installButton.getAttribute("aria-busy") === "false");
    equal(runtime.snapshot().status.state, "map_pack_install_cancelled", "cancel during manifest request remains explicit");
    mode = "good";
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await until(() => runtime.snapshot().packs.length === 3 && installButton.getAttribute("aria-busy") === "false");
    assert(controls.querySelector("ul").textContent.includes(offer.pack_id), "normal form lists installed trusted map");
    equal(await versions.list(), before, "form install and cancellation preserve complete products");
    cases.push("tools_form_uses_trusted_selection_and_cancels_pending_manifest_without_touching_regions");

    const count = requests.length;
    const raced = independent(), openSource = raced.openPackSource.bind(raced);
    raced.openPackSource = async (...args) => {
      const opened = await openSource(...args);
      return { ...opened, manifest: { ...opened.manifest, build_id: "unverified-replacement" } };
    };
    equal((await compose(raced).scanInstalledPacks()).invalid_pack_ids, [offer.pack_id],
      "metadata replacement between verification and source opening cannot adopt an unverified identity");
    separate = independent(); composed = compose();
    equal((await composed.scanInstalledPacks()).packs.length, 3, "cold restart revalidates independent identity without download");
    equal(requests.length, count, "restart is local only");
    const record = await separate.getPack(offer.pack_id);
    const bad = archive.slice(); bad[bad.length - 1] ^= 1;
    const writer = await record.archiveHandle.createWritable(); await writer.write(bad); await writer.close();
    scan = await composed.scanInstalledPacks();
    equal(scan.packs.length, 2, "warm same-size replacement cannot displace working complete maps");
    equal(scan.invalid_pack_ids, [offer.pack_id], "corruption is explicit");
    composed = compose(independent());
    equal((await composed.scanInstalledPacks()).invalid_pack_ids, [offer.pack_id], "cold restart rehashes same-size corruption");
    cases.push("cold_and_warm_revalidation_reject_same_size_corruption_without_routing_effect");

    await composed.removePack(offer.pack_id); await composed.loadOffers();
    await composed.installPack(offer.manifest_url);
    const directory = await standaloneRoot.getDirectoryHandle(offer.pack_id);
    await directory.removeEntry("basemap.pmtiles");
    equal((await composed.scanInstalledPacks()).invalid_pack_ids, [offer.pack_id], "missing archive explicit after restart");
    await composed.removePack(offer.pack_id);
    await rejects(() => composed.removePack("marly-map"), "regional_use_download_screen");
    equal(await versions.list(), before, "regional identities and selection untouched by install, failure, corruption or removal");
    const optional = compose({ scanInstalledPacks: async () => { throw Error("Optional storage failed"); } });
    equal((await optional.scanInstalledPacks()).packs.length, 2, "optional store failure preserves normal maps");
    assert((await optional.scanInstalledPacks()).independent_storage_unavailable, "optional storage failure visible");
    cases.push("missing_archive_removal_and_optional_storage_failure_preserve_complete_regions");
    return cases;
  } finally { await origin.removeEntry(name, { recursive: true }); }
}
