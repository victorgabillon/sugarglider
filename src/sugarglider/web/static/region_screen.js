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
  const { container, selector, list, status, cancel, refresh: refreshButton, mapStatus, progress, diagnostics, diagnosticCode } = elements;
  let focusKey = null;

  function message(text, code = "") {
    if (closed) return;
    status.textContent = text; status.dataset.state = code;
    const failure = code && !["regional_ready", "regional_checking", "regional_installing", "regional_installed", "regional_removed", "regional_cancelling", "regional_required", "regional_selection_required"].includes(code);
    if (diagnostics) diagnostics.hidden = !failure;
    if (diagnosticCode) diagnosticCode.textContent = failure ? code : "";
  }
  function render() {
    if (closed) return;
    selector.disabled = pending || isPlanning();
    refreshButton.disabled = pending || isPlanning();
    cancel.classList.toggle("hidden", !pending || !product.busy());
    cancel.disabled = cancelling;
    list.setAttribute("aria-busy", String(pending));
    if (progress) progress.hidden = !pending || !product.busy();
    for (const button of list.querySelectorAll("button")) {
      button.disabled = pending || (button.dataset.mutation === "remove" && isPlanning()) || button.dataset.unavailable === "true";
    }
    if (!pending && focusKey) {
      const active = document.activeElement;
      if (active === document.body || list.contains(active)) {
        const target = [...list.querySelectorAll("button")].find((button) => button.dataset.regionAction === focusKey);
        (target && !target.disabled ? target : selector).focus({ preventScroll: true });
      }
      focusKey = null;
    }
  }
  function renderRows() {
    if (closed) return;
    selector.replaceChildren(option("", "Choose an installed region"));
    for (const row of rows.filter((item) => item.status === "committed")) {
      selector.append(option(row.region_id, row.manifest.display_name));
    }
    selector.value = selectedRegionId() ?? "";
    const openDetails = new Set([...list.querySelectorAll("details[open]")].map((detail) => detail.dataset.regionId));
    list.replaceChildren();
    const ids = [...new Set([...catalog.map((row) => row.region_id), ...rows.map((row) => row.region_id)])];
    for (const id of ids) {
      const offering = catalog.find((row) => row.region_id === id), stored = rows.find((row) => row.region_id === id);
      const item = document.createElement("li"); item.className = "offline-region-card";
      const name = document.createElement("strong"); name.textContent = offering?.display_name ?? stored?.manifest?.display_name ?? id;
      item.append(name);
      const same = stored?.manifest?.build_id === offering?.build_id;
      const verified = stored?.manifest?.build_id === readyBuild && id === selectedRegionId();
      const installed = stored?.status === "committed";
      const stateLabel = installed && offering && !same ? "Update available" : verified ? "Ready" : installed ? "Installed" : stored ? "Needs attention" : offering?.manifest_url ? "Available" : "Download unavailable";
      item.dataset.regionState = stateLabel;
      const badge = document.createElement("p"); badge.className = "region-state"; badge.textContent = stateLabel; item.append(badge);
      const technical = document.createElement("details"); technical.className = "region-technical"; technical.dataset.regionId = id; technical.open = openDetails.has(id);
      const summary = document.createElement("summary"); summary.textContent = "Technical details"; technical.append(summary);
      appendText(technical, `Region ID: ${id}`);
      if (stored?.manifest) appendText(technical, `Installed build: ${stored.manifest.build_id}`);
      if (offering) appendText(technical, `Available build: ${offering.build_id}`);
      if (offering) {
        appendText(item, offering.description);
        appendText(item, `About ${bytes(offering.download_bytes)} to download, plus small region details. All six activities are included.`);
      }
      appendText(item, verified ? "Map ✓ · Routing ✓ · Places ✓ · Nature ✓"
        : stored?.status === "committed" ? "Installed on this device. Select this region to check it is ready."
        : stored ? regionFailureMessage(stored.code ?? "regional_install_incomplete") : "Not installed. Download once to use this region offline.");
      if (installed && offering && !same) appendText(item, "A newer download is available. Your installed region stays available until the update is ready.");
      if (stored?.status === "committed" && id === selectedRegionId()) {
        item.append(button("Show region on map", async () => { viewRegion(stored.manifest.bounds); }, `${id}:view`));
      }
      if (offering?.manifest_url) {
        item.append(button(same ? "Verify download" : stored?.manifest ? "Update region" : "Download region", async () => {
          await act(async () => {
            const action = same ? "Checking" : stored?.manifest ? "Updating" : "Downloading";
            message(`${action} ${name.textContent}…`, "regional_installing");
            if (progress) progress.removeAttribute("value");
            const installed = await product.install(offering.manifest_url, { expectedRegionId: id, expectedBuildId: offering.build_id,
              expectedDownloadBytes: offering.download_bytes, onProgress: ({ component, received_bytes: received, total_bytes: total }) => {
                message(`${action} ${name.textContent} · ${PHASES[component] ?? "Preparing region"}${total ? `: ${bytes(received)} of ${bytes(total)}` : "…"}`, "regional_installing");
                if (progress) {
                  progress.setAttribute("aria-label", PHASES[component] ?? "Preparing region");
                  if (total > 0 && Number.isFinite(received)) { progress.max = total; progress.value = Math.min(received, total); }
                  else progress.removeAttribute("value");
                }
                render();
              } });
            if (closed) return;
            if (selectedRegionId() === null) selectRegion(installed.region_id);
            message(`${installed.display_name} is installed.`, "regional_installed");
          });
        }, `${id}:install`, !same));
      } else if (offering) {
        const unavailable = button("Download unavailable", async () => {}); unavailable.dataset.unavailable = "true"; item.append(unavailable);
        appendText(item, "Region files are not available from a download service yet.");
      }
      if (stored || offering) {
        const remove = button(stored ? "Remove region" : "Clear regional data", async () => {
          if (isPlanning() || !confirmRemoval(`Remove ${name.textContent} and all of its offline data from this device? Saved route snapshots are kept.`)) return;
          await act(async () => { await product.remove(id); message("Region removed from this device.", "regional_removed"); });
        }, `${id}:remove`);
        remove.classList.add("danger");
        remove.dataset.mutation = "remove"; (stored ? item : technical).append(remove);
        for (const buildId of stored?.inactive_build_ids ?? []) {
          appendText(technical, `Unused build: ${buildId}`);
          const discard = button("Remove unused download", async () => {
            if (isPlanning() || !confirmRemoval("Remove this unused download? The currently installed version is kept.")) return;
            await act(async () => { await product.discardUpdate(id, buildId); message("Unused download removed.", "regional_removed"); });
          }, `${id}:discard:${buildId}`);
          discard.setAttribute("aria-label", `Remove unused download ${buildId.slice(0, 12)}`);
          discard.classList.add("danger");
          discard.dataset.mutation = "remove"; technical.append(discard);
        }
      }
      item.append(technical);
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
    focusKey = document.activeElement?.dataset.regionAction ?? null;
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
function button(label, action, key = "", primary = false) { const element = document.createElement("button"); element.type = "button";
  element.className = primary ? "button primary" : "button secondary"; element.dataset.regionAction = key; element.textContent = label; element.addEventListener("click", () => { void action(); }); return element; }
function bytes(value) { return `${(value / 1_000_000).toFixed(1)} MB`; }
