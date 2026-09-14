import { loadRegionCatalog } from "./region_catalog.js";
import { selectCommittedRegion } from "./regional_planning.js";

const PHASES = { checking: "Checking the download", map: "Downloading the map", routing: "Downloading routing data",
  places_nature: "Downloading and checking places and nature", verifying: "Verifying all regional data", ready: "Region installed" };

export function regionFailureMessage(code) {
  return {
    regional_required: "Download a region to plan and view maps offline.",
    regional_selection_required: "Choose one installed region for this plan.",
    regional_checking: "Checking the selected region…",
    regional_operation_busy: "Another region operation is still finishing. Try again shortly.",
    regional_routing_busy: "Routing data is still in use. Try again when the current operation finishes.",
    regional_install_cancelled: "Download cancelled. Any previously installed version is unchanged. Incomplete files can be resumed or removed below.",
    regional_insufficient_storage: "There is not enough free space for this download. Free some space or remove an unused region.",
    regional_storage_unavailable: "Offline storage is unavailable. Reopen the app and try again.",
    regional_staging_limit: "Remove the unused version shown below before downloading another update.",
    regional_catalog_unavailable: "The list of available downloads could not be opened. Installed regions remain independent.",
    regional_catalog_changed: "The available download has changed. Refresh the list before trying again.",
    regional_checksum_mismatch: "The regional data failed its integrity check. Remove the affected version and download it again.",
    regional_corrupt_remove_and_reinstall: "The stored data is damaged. Remove the affected version and download it again.",
    regional_install_incomplete: "The installation is incomplete. Resume its download or remove it below.",
    regional_metadata_recovery_required: "The stored region details are damaged. Recovery is required before this version can be removed.",
    regional_active_record_invalid: "The stored region selection is damaged. Remove this region and download it again.",
    regional_native_outcome_uncertain: "The app could not confirm that file work finished. Existing data has been retained. Reopen the app to check it before retrying.",
    regional_commit_uncertain: "The app could not confirm the version change. Both versions have been retained. Reopen the app to check the installation.",
    regional_transfer_timeout: "The download timed out. Keep the app open and try again with a working connection.",
    regional_routing_unavailable: "Routing data for this region is unavailable. Remove and download the region again.",
    regional_version_in_use: "This version is selected for use. Remove the whole region to stop using it first.",
  }[code] ?? "This region could not be prepared. Check your connection and free space, then resume or remove the incomplete download.";
}

export function createRegionScreen({ elements, versions, product, withRegion,
  selectedRegionId, selectRegion, onReady = () => {}, onMapChange = async () => {},
  viewRegion = () => {},
  isPlanning = () => false, loadCatalog = loadRegionCatalog,
  confirmRemoval = (message) => globalThis.confirm(message), lifecycleTarget = globalThis,
} = {}) {
  let catalog = [], rows = [], pending = false, closed = false, readyBuild = null, cancelling = false;
  const { container, selector, list, status, cancel, refresh: refreshButton, mapStatus } = elements;

  function message(text, code = "") {
    if (closed) return;
    status.textContent = text; status.dataset.state = code;
  }
  function render() {
    if (closed) return;
    selector.disabled = pending || isPlanning();
    refreshButton.disabled = pending || isPlanning();
    cancel.classList.toggle("hidden", !pending || !product.busy());
    cancel.disabled = cancelling;
    for (const button of list.querySelectorAll("button")) {
      button.disabled = pending || (button.dataset.mutation === "remove" && isPlanning()) || button.dataset.unavailable === "true";
    }
  }
  function renderRows() {
    if (closed) return;
    selector.replaceChildren(option("", "Choose an installed region"));
    for (const row of rows.filter((item) => item.status === "committed")) {
      selector.append(option(row.region_id, row.manifest.display_name));
    }
    selector.value = selectedRegionId() ?? "";
    list.replaceChildren();
    const ids = [...new Set([...catalog.map((row) => row.region_id), ...rows.map((row) => row.region_id)])];
    for (const id of ids) {
      const offering = catalog.find((row) => row.region_id === id), stored = rows.find((row) => row.region_id === id);
      const item = document.createElement("li"); item.className = "offline-region-card";
      const name = document.createElement("strong"); name.textContent = offering?.display_name ?? stored?.manifest?.display_name ?? id;
      item.append(name);
      if (offering) {
        appendText(item, offering.description);
        appendText(item, `About ${bytes(offering.download_bytes)} to download, plus small region details. All six activities are included.`);
      }
      const verified = stored?.manifest?.build_id === readyBuild && id === selectedRegionId();
      appendText(item, verified ? "Map ✓ · Routing ✓ · Places ✓ · Nature ✓"
        : stored?.status === "committed" ? "Stored on this device. Select this region to check all four components."
        : stored ? regionFailureMessage(stored.code ?? "regional_install_incomplete") : "Not installed");
      if (stored?.manifest) appendText(item, `Installed version ${stored.manifest.build_id.slice(0, 12)}`);
      if (stored?.status === "committed" && id === selectedRegionId()) {
        item.append(button("Show region on map", async () => { viewRegion(stored.manifest.bounds); }));
      }
      if (offering?.manifest_url) {
        const same = stored?.manifest?.build_id === offering.build_id;
        item.append(button(same ? "Verify download" : stored?.manifest ? "Update region" : "Download region", async () => {
          await act(async () => {
            const installed = await product.install(offering.manifest_url, { expectedRegionId: id, expectedBuildId: offering.build_id,
              expectedDownloadBytes: offering.download_bytes, onProgress: ({ component, received_bytes: received, total_bytes: total }) => {
                message(`${PHASES[component] ?? "Preparing region"}${total ? `: ${bytes(received)} of ${bytes(total)}` : "…"}`, "regional_installing");
                render();
              } });
            if (closed) return;
            if (selectedRegionId() === null) selectRegion(installed.region_id);
            message(`${installed.display_name} is installed.`, "regional_installed");
          });
        }));
      } else if (offering) {
        const unavailable = button("Download unavailable", async () => {}); unavailable.dataset.unavailable = "true"; item.append(unavailable);
        appendText(item, "Region files are not available from a download service yet.");
      }
      if (stored || offering) {
        const remove = button(stored ? "Remove region" : "Clear regional data", async () => {
          if (isPlanning() || !confirmRemoval(`Remove ${name.textContent} and all of its offline data from this device? Saved route snapshots are kept.`)) return;
          await act(async () => { await product.remove(id); message("Region removed from this device.", "regional_removed"); });
        });
        remove.dataset.mutation = "remove"; item.append(remove);
        for (const buildId of stored?.inactive_build_ids ?? []) {
          const discard = button(`Remove unused version ${buildId.slice(0, 12)}`, async () => {
            if (isPlanning() || !confirmRemoval("Remove this unused download? The currently installed version is kept.")) return;
            await act(async () => { await product.discardUpdate(id, buildId); message("Unused download removed.", "regional_removed"); });
          });
          discard.dataset.mutation = "remove"; item.append(discard);
        }
      }
      list.append(item);
    }
    render();
  }

  async function inspectSelection() {
    let row;
    try { row = selectCommittedRegion(rows, selectedRegionId()); }
    catch (error) {
      readyBuild = null; onReady(null, error.code, null);
      message(regionFailureMessage(error.code), error.code);
      renderRows(); await onMapChange(); return;
    }
    if (selectedRegionId() === null) selectRegion(row.region_id);
    onReady(null, "regional_checking", null);
    message(regionFailureMessage("regional_checking"), "regional_checking");
    try {
      const checked = await withRegion(async (region) => ({ capabilities: region.capabilities ?? await region.bridge.capabilities(), reference: region.reference }));
      if (closed) return;
      readyBuild = checked.reference.build_id;
      onReady(checked.capabilities, null, checked.reference);
      message("The selected region is ready for offline planning.", "regional_ready");
    } catch (error) {
      if (closed) return;
      readyBuild = null; onReady(null, error.code ?? "regional_components_unavailable", null);
      message(regionFailureMessage(error.code), error.code ?? "regional_components_unavailable");
    }
    renderRows();
    await onMapChange();
  }

  async function refresh({ catalogToo = false } = {}) {
    let catalogUnavailable = false;
    if (catalogToo) {
      try { catalog = await loadCatalog(); }
      catch { catalogUnavailable = true; }
    }
    try { rows = await versions.list(); }
    catch {
      rows = []; onReady(null, "regional_storage_unavailable", null);
      message(regionFailureMessage("regional_storage_unavailable"), "regional_storage_unavailable");
      renderRows(); await onMapChange(); return;
    }
    if (closed) return;
    renderRows();
    await inspectSelection();
    if (catalogUnavailable) message(regionFailureMessage("regional_catalog_unavailable"), "regional_catalog_unavailable");
  }

  async function act(action, { refreshAfter = true } = {}) {
    if (pending || closed) return;
    pending = true; cancelling = false; render();
    let failure = null;
    try { await action(); }
    catch (error) {
      const code = error.name === "AbortError" ? "regional_install_cancelled" : error.code ?? "regional_operation_failed";
      failure = { text: regionFailureMessage(code), code };
      message(failure.text, failure.code);
    }
    finally {
      if (!closed) {
        try { if (refreshAfter) await refresh(); }
        catch { message("The region list could not be refreshed. Reopen the app to check it.", "regional_storage_unavailable"); }
        // Checking the retained region must not conceal a failed/cancelled update.
        if (failure) message(failure.text, failure.code);
        pending = false; render();
      }
    }
  }

  selector.addEventListener("change", () => {
    if (pending || isPlanning()) return;
    selectRegion(selector.value || null);
    void act(async () => { message("Checking the selected region…", "regional_checking"); });
  });
  refreshButton.addEventListener("click", () => { if (!isPlanning()) void act(async () => refresh({ catalogToo: true }), { refreshAfter: false }); });
  cancel.addEventListener("click", () => { cancelling = true; product.cancel(); message("Cancelling download and waiting for file work to finish…", "regional_cancelling"); render(); });
  lifecycleTarget?.addEventListener?.("pagehide", () => { closed = true; product.cancel(); }, { once: true });

  return Object.freeze({
    initialize: async () => { container.classList.remove("hidden"); await act(async () => refresh({ catalogToo: true }), { refreshAfter: false });
      if (!rows.some((row) => row.status === "committed")) container.open = true; },
    refresh, render,
    mapState: (snapshot) => {
      if (closed || !mapStatus) return;
      mapStatus.textContent = {
        local_pack_active: "The selected region’s offline map is displayed.",
        map_pack_ready: "The regional map is stored on this device.",
        no_covering_map_pack: "The map view is outside the selected region. Use Show region on map to return to its coverage.",
        no_map_packs_installed: "Download a region to view its offline map.",
        map_pack_storage_unavailable: "Offline map storage is unavailable. Reopen the app and try again.",
        map_pack_invalid: "The stored map could not be opened. Remove this region and download it again.",
      }[snapshot?.status?.state] ?? "Offline map unavailable.";
    },
  });
}

function option(value, text) { const element = document.createElement("option"); element.value = value; element.textContent = text; return element; }
function appendText(parent, text) { const element = document.createElement("p"); element.textContent = text; parent.append(element); }
function button(label, action) { const element = document.createElement("button"); element.type = "button";
  element.className = "button secondary"; element.textContent = label; element.addEventListener("click", () => { void action(); }); return element; }
function bytes(value) { return `${(value / 1_000_000).toFixed(1)} MB`; }
