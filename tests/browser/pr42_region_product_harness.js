import { createRegionVersionStore } from "../../src/sugarglider/web/static/region_versions.js";
import { createRegionProduct } from "../../src/sugarglider/web/static/region_product.js";
import { createVersionedRegionComponents } from "../../src/sugarglider/web/static/region_components.js";
import { createRegionScreen } from "../../src/sugarglider/web/static/region_screen.js";
import { createRegionalPlanningContext } from "../../src/sugarglider/web/static/regional_planning.js";
import { createRegionalMapStore } from "../../src/sugarglider/web/static/regional_map_store.js";
import { regionalDistributionUrl, fetchRegionalManifest, regionalDownloadBytes } from "../../src/sugarglider/web/static/regional_distribution.js";
import { parseRegionCatalog } from "../../src/sugarglider/web/static/region_catalog.js";
import { regionalBuildIdentity, RegionalDataError } from "../../src/sugarglider/web/static/regional_manifest.js";
import { distribution } from "./pr42_region_components_harness.js";

const assert = (value, message) => { if (!value) throw new Error(message); };
const equal = (a, b, message) => assert(JSON.stringify(a) === JSON.stringify(b), `${message}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`);
const source = "https://packs.example/manifest.json";
const pageLocation = { href: "https://appassets.androidplatform.net/" };
const pause = () => new Promise((resolve) => setTimeout(resolve, 0));
async function until(check) { for (let i = 0; i < 500; i++) { if (check()) return; await new Promise((resolve) => setTimeout(resolve, 10)); } throw new Error("UI did not settle"); }
async function rejects(action, code) {
  const error = await action().then(() => null, (caught) => caught);
  equal(error?.code ?? error?.name, code, "explicit failure");
}

export async function runPr42RegionProductHarness() {
  const cases = [];
  for (const url of ["http://localhost/manifest.json", "https://x/a/../manifest.json", "https://x/%2e/manifest.json",
    "https://x//manifest.json", "https://user@x/manifest.json", "https://x/manifest.json?key=private", "https://x/other.json"]) {
    await rejects(async () => regionalDistributionUrl(url, pageLocation), "invalid_regional_source");
  }
  equal(regionalDistributionUrl(source, pageLocation).href, source, "HTTPS distribution layout accepted");
  cases.push("distribution_uses_canonical_credential_free_https_layout");

  const fixture = await (await fetch("../fixtures/pr40_regional_data.json")).json();
  const origin = await navigator.storage.getDirectory(), name = `pr42-product-${crypto.randomUUID()}`;
  const root = await origin.getDirectoryHandle(name, { create: true });
  const storage = { getDirectory: async () => root, estimate: async () => ({ quota: 1e9, usage: 0 }) };
  const versions = createRegionVersionStore({ storage });
  let current, nativePause = null, selected = null, nativeError = null, ready = null;
  const requests = [], nativeCalls = [], nativeStored = new Set();
  const fetchResource = async (url, options) => {
    requests.push({ url, options });
    const path = new URL(url).pathname.slice(1);
    const bytes = path === "manifest.json" ? new TextEncoder().encode(JSON.stringify(current.manifest)) : current.files.get(path);
    assert(bytes, "Only declared static distribution files requested");
    return new Response(bytes, { headers: { "Content-Length": String(bytes.byteLength) } });
  };
  const components = ({ manifest, directory }) => createVersionedRegionComponents({ manifest, directory, storage, pageLocation, fetchResource });
  // Native archive installation is a bounded synthetic acknowledgement in this
  // harness. Its downloader/checksums/leases are separately tested on the JVM.
  const native = {
    install: async (reference, url, { signal, onProgress }) => {
      equal(url, source, "same captured distribution source"); nativeCalls.push(["install", reference.build_id]);
      onProgress(0, reference.archive.byte_size);
      if (nativePause) await nativePause;
      if (signal.aborted) throw new RegionalDataError("regional_install_cancelled");
      if (nativeError) throw new RegionalDataError(nativeError);
      nativeStored.add(reference.build_id); onProgress(reference.archive.byte_size, reference.archive.byte_size);
      return { status: "ready" };
    },
    inspect: async (reference) => { assert(nativeStored.has(reference.build_id), "only installed native version can pass validation"); return { status: "ready" }; },
    remove: async (reference) => { nativeCalls.push(["remove", reference.build_id]); nativeStored.delete(reference.build_id); return { status: "removed" }; },
    removeVersion: async (version) => { nativeCalls.push(["remove", version.build_id]); nativeStored.delete(version.build_id); return { status: "removed" }; },
    removeRegion: async (regionId) => { equal(regionId, fixture.manifest.region_id, "only explicit region cleanup"); nativeStored.clear(); return { status: "removed" }; },
  };
  const installerClient = { installVersion: async (url, manifest, directory) => (await components({ manifest, directory })).installIndexes(url), cancelInstall() {} };
  const product = createRegionProduct({ versions, native, installerClient, components,
    readManifest: (url, options) => fetchRegionalManifest(url, { ...options, fetchResource, pageLocation }) });
  const bridge = { forRegion: (reference) => ({ capabilities: async () => ({ enabled: nativeStored.has(reference.build_id),
    installed_pack_count: 1, installed_pack_ids: [reference.pack_id], supported_profile_ids: ["hike", "city_bike"] }) }) };
  const withRegion = createRegionalPlanningContext({ versions, bridge, selectedRegionId: () => selected, components, inspectNative: native.inspect,
    regionClient: { loadVersion: async (manifest, directory) => (await components({ manifest, directory })).openIndexes() } });
  const mapStore = createRegionalMapStore({ versions, selectedRegionId: () => selected, components });
  const container = document.createElement("details"); container.innerHTML = '<select></select><ul></ul><p data-status></p><p data-map></p><button data-cancel>Cancel</button><button data-refresh>Check</button>';
  document.body.append(container);
  const elements = { container, selector: container.querySelector("select"), list: container.querySelector("ul"),
    status: container.querySelector("[data-status]"), mapStatus: container.querySelector("[data-map]"),
    cancel: container.querySelector("[data-cancel]"), refresh: container.querySelector("[data-refresh]") };
  const offering = () => ({ region_id: current.manifest.region_id, display_name: current.manifest.display_name, description: "Synthetic fixture coverage",
    build_id: current.manifest.build_id, bounds: current.manifest.bounds, download_bytes: regionalDownloadBytes(current.manifest), manifest_url: source });
  let catalogUnavailable = false;
  const screen = createRegionScreen({ elements, versions, product, withRegion, selectedRegionId: () => selected, selectRegion: (id) => { selected = id; },
    onReady: (capabilities, code) => { ready = code ?? (capabilities?.enabled ? "ready" : "failed"); },
    onMapChange: async () => { await mapStore.scanInstalledPacks(); },
    loadCatalog: async () => {
      if (catalogUnavailable) throw new Error("Fixture catalog unavailable");
      return parseRegionCatalog({ schema_version: 1, regions: [offering()] }, pageLocation);
    },
    confirmRemoval: () => true, lifecycleTarget: null });
  async function nextDistribution(label) {
    current = await distribution(fixture, label);
    current.manifest.components.routing.files[1].byte_size = 512;
    current.manifest.build_id = await regionalBuildIdentity(current.manifest);
    return current;
  }
  function click(label) {
    const control = [...elements.list.querySelectorAll("button")].find((item) => item.textContent === label);
    assert(control && !control.disabled, `${label} is available`); control.click();
  }
  async function settled() { await until(() => !product.busy() && !elements.refresh.disabled); }
  try {
    const first = await nextDistribution("First region");
    await screen.initialize();
    equal(ready, "regional_required", "fresh page requires region"); equal(requests.length, 0, "loading catalog never downloads region files");
    equal(elements.status.dataset.state, "regional_required", "finished empty discovery does not retain checking text");
    assert(container.open && elements.list.textContent.includes("Not installed"), "first user sees clear download entry");
    cases.push("fresh_region_screen_has_no_implicit_download_or_fake_readiness");

    click("Download region"); await settled();
    equal(ready, "ready", "all components ready through actual UI");
    equal(elements.status.dataset.state, "regional_ready", "finished verification replaces checking status");
    equal((await versions.read(first.manifest.region_id)).build_id, first.manifest.build_id, "committed exact version");
    assert(elements.list.textContent.includes("Map ✓ · Routing ✓ · Places ✓ · Nature ✓"), "checks reflect verified components");
    equal(requests.map((entry) => new URL(entry.url).pathname), ["/manifest.json", "/map/manifest.json", "/map/basemap.pmtiles", "/pois/index.json.gz", "/nature/index.json.gz"], "single top-level manifest and independent web files");
    assert(requests.every(({ options }) => options.credentials === "omit" && options.redirect === "error" && options.cache === "no-store"), "component requests carry no credentials or redirects");
    const map = (await mapStore.scanInstalledPacks()).packs[0];
    assert((await (await mapStore.openPackSource(map.pack_id)).source.getBytes(0, 8)).data.byteLength === 8, "selected map uses real bounded shared source");
    cases.push("one_download_action_validates_and_activates_all_components");
    cases.push("selected_region_map_uses_existing_pmtiles_source_and_exact_version");

    catalogUnavailable = true; await screen.refresh({ catalogToo: true });
    equal(ready, "ready", "optional catalog failure cannot disable the verified installed region");
    equal(elements.status.dataset.state, "regional_catalog_unavailable", "catalog failure remains visible after retained-region verification");
    catalogUnavailable = false; await screen.refresh({ catalogToo: true });
    equal(elements.status.dataset.state, "regional_ready", "successful explicit recheck clears the previous catalog warning");
    cases.push("catalog_failure_and_recovery_keep_region_readiness_and_status_truthful");

    const before = requests.length; click("Verify download"); await settled();
    equal(requests.length, before + 1, "completed components are reused without another archive download");
    cases.push("repeat_install_verifies_committed_data_without_component_redownload");

    await nextDistribution("Update"); await screen.refresh({ catalogToo: true });
    nativeError = "regional_checksum_mismatch"; click("Update region"); await settled();
    equal((await versions.read(first.manifest.region_id)).build_id, first.manifest.build_id, "failed update keeps original commit");
    assert(elements.status.dataset.state === "regional_checksum_mismatch", "checksum failure is explicit");
    cases.push("failed_update_keeps_committed_region_and_exposes_staged_cleanup");

    nativeError = null;
    let drain;
    nativePause = new Promise((resolve) => { drain = resolve; });
    click("Update region"); await until(() => nativeCalls.filter((call) => call[0] === "install").length === 3);
    elements.cancel.click(); await pause();
    assert(product.busy() && elements.refresh.disabled, "Cancel waits for native outcome");
    equal((await versions.read(first.manifest.region_id)).build_id, first.manifest.build_id, "cancellation cannot switch active version");
    drain(); await settled(); nativePause = null;
    equal(elements.status.dataset.state, "regional_install_cancelled", "definite cancellation visible");
    cases.push("cancel_keeps_ui_owned_until_native_drain_and_old_commit_survives");

    const updateStart = requests.length; click("Update region"); await settled();
    equal((await versions.read(first.manifest.region_id)).build_id, current.manifest.build_id, "resumed update commits replacement");
    assert(!requests.slice(updateStart).some((entry) => entry.url.endsWith("basemap.pmtiles")), "resume hashes and reuses staged map");
    cases.push("resumed_update_reuses_staged_map_and_switches_only_after_verification");

    click(`Remove unused version ${first.manifest.build_id.slice(0, 12)}`); await settled();
    assert(!nativeStored.has(first.manifest.build_id) && nativeStored.has(current.manifest.build_id), "unused cleanup only removes old native version");
    equal(ready, "ready", "current version remains usable");
    cases.push("unused_version_removal_preserves_current_region");

    click("Remove region"); await settled();
    equal(await versions.list(), [], "all owned regional web versions removed");
    equal(nativeStored.size, 0, "native counterpart removed");
    equal((await mapStore.scanInstalledPacks()).packs, [], "map cannot retain removed selection");
    equal(ready, "regional_required", "no region remains explicit");
    equal(elements.status.dataset.state, "regional_required", "removal ends in a completed no-region state");
    cases.push("explicit_region_removal_clears_components_and_map_selection");

    click("Download region"); await settled();
    const regionRoot = await (await root.getDirectoryHandle("sugarglider-installed-regions")).getDirectoryHandle(current.manifest.region_id);
    const versionRoot = await regionRoot.getDirectoryHandle(current.manifest.build_id);
    await versionRoot.removeEntry("manifest.json");
    await screen.refresh();
    assert(ready !== "ready", "missing committed manifest never stays ready");
    click("Remove region"); await settled();
    equal(await versions.list(), [], "damaged metadata can be explicitly removed");
    equal(nativeStored.size, 0, "native cleanup never needs fabricated hashes");
    cases.push("damaged_committed_manifest_can_be_removed_without_a_fake_reference");

    nativeStored.add("orphaned-native-fixture");
    click("Clear regional data"); await settled();
    equal(nativeStored.size, 0, "explicit catalog-region cleanup works after web metadata loss");
    equal(await versions.list(), [], "native orphan cleanup never invents a web installation");
    cases.push("explicit_cleanup_handles_native_data_after_web_metadata_loss");

    const ticket = await versions.stage(JSON.stringify(current.manifest));
    let writerEntered = false, finishWriter, nativeEntered = false, finishNative;
    const writer = versions.withStagedVersion(ticket, async () => { writerEntered = true;
      await new Promise((resolve) => { finishWriter = resolve; }); });
    await until(() => writerEntered);
    const removing = versions.removeRegion(current.manifest.region_id, { beforeRemove: async () => {
      nativeEntered = true; await new Promise((resolve) => { finishNative = resolve; });
    } });
    await pause(); await pause();
    assert(!nativeEntered, "whole-region removal waits for staged writers");
    assert((await versions.list()).length === 1, "waiting for a writer does not monopolize metadata lock");
    finishWriter(); await writer; await until(() => nativeEntered);
    let observed = false;
    const reading = versions.withCommittedRegions(async (rows) => { observed = true; return rows; });
    await pause(); await pause();
    assert(!observed, "native cleanup keeps metadata ownership until its definite outcome");
    finishNative(); await removing;
    equal(await reading, [], "new reader sees only fully removed state");
    cases.push("whole_region_removal_waits_for_writers_and_holds_metadata_through_native_cleanup");
    return cases;
  } finally { container.remove(); await origin.removeEntry(name, { recursive: true }); }
}
