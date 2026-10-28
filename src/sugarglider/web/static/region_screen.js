import { t, tr, onLanguageChange, setLocalizedText } from "./i18n.js";
import { appendRegionSources } from "./terrain_attribution.js";
import { loadRegionCatalog } from "./region_catalog.js";
import { selectCommittedRegion } from "./regional_planning.js";

const PHASES = { checking: "Checking the download", map: "Downloading the map", routing: "Downloading routing and elevation data",
  places_nature: "Downloading and checking places and nature", verifying: "Verifying all regional data", ready: "Region installed" };

export function regionFailureMessage(code) {
  return {
    regional_required: t("Download a region to plan and view maps offline."),
    no_covering_routing_pack: t("No single installed routing region covers these points. Map display and routing coverage are separate."),
    regional_selection_required: t("Choose one installed region for this plan."),
    regional_checking: t("Checking the selected region…"),
    regional_operation_busy: t("Another region operation is still finishing. Try again shortly."),
    regional_routing_busy: t("Routing data is still in use. Try again when the current operation finishes."),
    regional_install_cancelled: t("Download cancelled. Any previously installed version is unchanged. Incomplete files can be resumed or removed below."),
    regional_insufficient_storage: t("There is not enough free space for this download. Free some space or remove an unused region."),
    regional_storage_unavailable: t("Offline storage is unavailable. Reopen the app and try again."),
    regional_staging_limit: t("Remove the unused version shown below before downloading another update."),
    regional_catalog_unavailable: t("The list of available downloads could not be opened. Installed regions remain independent."),
    regional_catalog_changed: t("The available download has changed. Refresh the list before trying again."),
    regional_checksum_mismatch: t("The regional data failed its integrity check. Remove the affected version and download it again."),
    regional_corrupt_remove_and_reinstall: t("The stored data is damaged. Remove the affected version and download it again."),
    regional_install_incomplete: t("The installation is incomplete. Resume its download or remove it below."),
    regional_v2_install_required: t("This region needs a new V2 installation. Its existing files have been kept."),
    regional_elevation_invalid: t("The region's elevation data failed verification. Install a complete V2 region."),
    regional_metadata_recovery_required: t("The stored region details are damaged. Recovery is required before this version can be removed."),
    regional_active_record_invalid: t("The stored region selection is damaged. Remove this region and download it again."),
    regional_native_outcome_uncertain: t("The app could not confirm that file work finished. Existing data has been retained. Reopen the app to check it before retrying."),
    regional_commit_uncertain: t("The app could not confirm the version change. Both versions have been retained. Reopen the app to check the installation."),
    regional_transfer_timeout: t("The download timed out. Keep the app open and try again with a working connection."),
    regional_routing_unavailable: t("Routing data for this region is unavailable. Remove and download the region again."),
    regional_version_in_use: t("This version is selected for use. Remove the whole region to stop using it first."),
  }[code] ?? t("This region could not be prepared. Check your connection and free space, then resume or remove the incomplete download.");
}

export function createRegionScreen({ elements, versions, product, withRegion,
  selectedRegionId, selectRegion, onReady = () => {}, onMapChange = async () => {},
  viewRegion = () => {}, planningRequest = () => null,
  isPlanning = () => false, loadCatalog = loadRegionCatalog,
  confirmRemoval = (message) => globalThis.confirm(message), lifecycleTarget = globalThis,
} = {}) {
  let catalog = [], rows = [], pending = false, closed = false, readyBuild = null, cancelling = false;
  const { container, selector, list, status, cancel, refresh: refreshButton, mapStatus, progress, diagnostics, diagnosticCode } = elements;
  let focusKey = null, coverageKey = null, coverageDirty = false;

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
    selector.replaceChildren(option("", t("Choose an installed region")));
    for (const row of rows.filter((item) => item.status === "committed")) {
      selector.append(option(row.region_id, row.manifest.display_name));
    }
    selector.value = selectedRegionId() ?? "";
    const openDetails = new Set([...list.querySelectorAll("details[open]")].map((detail) => detail.dataset.regionDisclosure));
    const disclosureFocus = list.contains(document.activeElement) ? document.activeElement.dataset.regionFocus : null;
    list.replaceChildren();
    const ids = [...new Set([...catalog.map((row) => row.region_id), ...rows.map((row) => row.region_id)])];
    for (const id of ids) {
      const offering = catalog.find((row) => row.region_id === id), stored = rows.find((row) => row.region_id === id);
      const item = document.createElement("li"); item.className = "offline-region-card";
      const name = document.createElement("strong"); name.textContent = offering?.display_name ?? stored?.manifest?.display_name ?? id;
      item.append(name);
      if (stored) {
        const sources = appendRegionSources(item, stored.status === "committed" ? stored.manifest : null);
        for (const detail of [sources, ...sources.querySelectorAll("details")]) {
          const key = `${id}:${detail.dataset.sourceDisclosure}`;
          detail.dataset.regionDisclosure = key; detail.open = openDetails.has(key);
          detail.querySelector("summary").dataset.regionFocus = key;
        }
        [...sources.querySelectorAll("a")].forEach((link, index) => { link.dataset.regionFocus = `${id}:source-link:${index}`; });
      }
      const same = stored?.manifest?.build_id === offering?.build_id;
      const verified = stored?.manifest?.build_id === readyBuild && id === selectedRegionId();
      const installed = stored?.status === "committed";
      const stateLabel = installed && offering && !same ? t("Update available") : verified ? t("Ready") : installed ? t("Installed") : stored ? t("Needs attention") : offering?.manifest_url ? t("Available") : t("Download unavailable");
      item.dataset.regionState = stateLabel;
      const badge = document.createElement("p"); badge.className = "region-state"; badge.textContent = stateLabel; item.append(badge);
      const technical = document.createElement("details"); technical.className = "region-technical"; technical.dataset.regionId = id;
      technical.dataset.regionDisclosure = `${id}:technical`; technical.open = openDetails.has(`${id}:technical`);
      const summary = document.createElement("summary"); setLocalizedText(summary, () => t("Technical details")); summary.dataset.regionFocus = `${id}:technical`; technical.append(summary);
      appendText(technical, tr`Region ID: ${id}`);
      if (stored?.manifest) appendText(technical, tr`Installed build: ${stored.manifest.build_id}`);
      if (offering) appendText(technical, tr`Available build: ${offering.build_id}`);
      if (offering) {
        appendText(item, offering.description);
        appendText(item, tr`About ${bytes(offering.download_bytes)} to download, plus small region details. All six activities are included.`);
      }
      appendText(item, verified ? "Map ✓ · Routing ✓ · Places ✓ · Nature ✓ · Elevation ✓"
        : stored?.status === "committed" ? t("Installed on this device. Select this region to check it is ready.")
        : stored ? regionFailureMessage(stored.code ?? "regional_install_incomplete") : t("Not installed. Download once to use this region offline."));
      if (installed && offering && !same) appendText(item, t("A newer download is available. Your installed region stays available until the update is ready."));
      if (stored?.status === "committed" && id === selectedRegionId()) {
        item.append(button(t("Show region on map"), async () => { viewRegion(stored.manifest.bounds); }, `${id}:view`));
      }
      if (offering?.manifest_url) {
        item.append(button(same ? t("Verify download") : stored?.manifest ? t("Update region") : t("Download region"), async () => {
          await act(async () => {
            const action = same ? t("Checking") : stored?.manifest ? t("Updating") : t("Downloading");
            message(`${action} ${name.textContent}…`, "regional_installing");
            if (progress) progress.removeAttribute("value");
            const installed = await product.install(offering.manifest_url, { expectedRegionId: id, expectedBuildId: offering.build_id,
              expectedDownloadBytes: offering.download_bytes, onProgress: ({ component, received_bytes: received, total_bytes: total }) => {
                message(`${action} ${name.textContent} · ${t(PHASES[component] ?? "Preparing region")}${total ? `: ${bytes(received)} of ${bytes(total)}` : "…"}`, "regional_installing");
                if (progress) {
                  progress.setAttribute("aria-label", t(PHASES[component] ?? "Preparing region"));
                  if (total > 0 && Number.isFinite(received)) { progress.max = total; progress.value = Math.min(received, total); }
                  else progress.removeAttribute("value");
                }
                render();
              } });
            if (closed) return;
            if (selectedRegionId() === null) selectRegion(installed.region_id);
            message(tr`${installed.display_name} is installed.`, "regional_installed");
          });
        }, `${id}:install`, !same));
      } else if (offering) {
        const unavailable = button(t("Download unavailable"), async () => {}); unavailable.dataset.unavailable = "true"; item.append(unavailable);
        appendText(item, t("Region files are not available from a download service yet."));
      }
      if (stored || offering) {
        const remove = button(stored ? t("Remove region") : t("Clear regional data"), async () => {
          if (isPlanning() || !confirmRemoval(tr`Remove ${name.textContent} and all of its offline data from this device? Saved route snapshots are kept.`)) return;
          await act(async () => { await product.remove(id);
            if (selectedRegionId() === id) selectRegion(null);
            message(t("Region removed from this device."), "regional_removed"); });
        }, `${id}:remove`);
        remove.classList.add("danger");
        remove.dataset.mutation = "remove"; (stored ? item : technical).append(remove);
        for (const buildId of stored?.inactive_build_ids ?? []) {
          appendText(technical, tr`Unused build: ${buildId}`);
          const discard = button(t("Remove unused download"), async () => {
            if (isPlanning() || !confirmRemoval(t("Remove this unused download? The currently installed version is kept."))) return;
            await act(async () => { await product.discardUpdate(id, buildId); message(t("Unused download removed."), "regional_removed"); });
          }, `${id}:discard:${buildId}`);
          discard.setAttribute("aria-label", tr`Remove unused download ${buildId.slice(0, 12)}`);
          discard.classList.add("danger");
          discard.dataset.mutation = "remove"; technical.append(discard);
        }
      }
      item.append(technical);
      list.append(item);
    }
    render();
    if (disclosureFocus) [...list.querySelectorAll("[data-region-focus]")]
      .find(element => element.dataset.regionFocus === disclosureFocus)?.focus({preventScroll:true});
  }

  async function inspectSelection() {
    let row;
    const request = planningRequest();
    coverageKey = JSON.stringify([selectedRegionId(), request]);
    try { row = selectCommittedRegion(rows, selectedRegionId(), request); }
    catch (error) {
      readyBuild = null; onReady(null, error.code, null);
      message(regionFailureMessage(error.code), error.code);
      renderRows(); await onMapChange(); return;
    }
    // The sole-region default is implicit; it must not undo an explicit clear.
    if (selectedRegionId() !== row.region_id) selectRegion(row.region_id, { remember: false });
    coverageKey = JSON.stringify([selectedRegionId(), request]);
    onReady(null, "regional_checking", null);
    message(regionFailureMessage("regional_checking"), "regional_checking");
    try {
      const checked = await withRegion(async (region) => ({ capabilities: region.capabilities ?? await region.bridge.capabilities(), reference: region.reference }), request);
      if (closed) return;
      readyBuild = checked.reference.build_id;
      onReady(checked.capabilities, null, checked.reference);
      message(t("The selected region is ready for offline planning."), "regional_ready");
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
    const selected = rows.find(row => row.region_id === selectedRegionId());
    if (selectedRegionId() !== null && (!selected || selected.status === "not_installed")) selectRegion(null);
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
        catch { message(t("The region list could not be refreshed. Reopen the app to check it."), "regional_storage_unavailable"); }
        // Checking the retained region must not conceal a failed/cancelled update.
        if (failure) message(failure.text, failure.code);
        pending = false; render();
        if (coverageDirty) {
          coverageDirty = false; coverageKey = null;
          refreshCoverage();
        }
      }
    }
  }

  function refreshCoverage() {
    if (closed || isPlanning()) return;
    const request = planningRequest();
    const key = JSON.stringify([selectedRegionId(), request]);
    if (key === coverageKey) return;
    coverageKey = key;
    if (pending) { coverageDirty = true; return; }
    // Point edits within the same already verified build do not replace an
    // open editor/menu. Every actual planning request still verifies its lease,
    // native data and web components; explicit refresh/install also rechecks.
    try {
      const row = selectCommittedRegion(rows, selectedRegionId(), request);
      if (readyBuild === row.manifest.build_id && selectedRegionId() === row.region_id) return;
    } catch { /* Refresh below publishes the explicit coverage failure. */ }
    void act(async () => {});
  }

  selector.addEventListener("change", () => {
    if (pending || isPlanning()) return;
    const id = selector.value || null;
    selectRegion(id);
    void act(async () => { message(t("Checking the selected region…"), "regional_checking"); });
  });
  refreshButton.addEventListener("click", () => { if (!isPlanning()) void act(async () => refresh({ catalogToo: true }), { refreshAfter: false }); });
  cancel.addEventListener("click", () => { cancelling = true; product.cancel(); message(t("Cancelling download and waiting for file work to finish…"), "regional_cancelling"); render(); });
  lifecycleTarget?.addEventListener?.("pagehide", () => { closed = true; product.cancel(); }, { once: true });

  onLanguageChange(() => { renderRows(); render(); });
  return Object.freeze({
    initialize: async () => { container.classList.remove("hidden"); await act(async () => refresh({ catalogToo: true }), { refreshAfter: false });
      if (!rows.some((row) => row.status === "committed")) container.open = true; },
    refresh, render, refreshCoverage,
    mapState: (snapshot) => {
      if (closed || !mapStatus) return;
      setLocalizedText(mapStatus, () => ({
        local_pack_active: t("The selected region’s offline map is displayed."),
        map_pack_ready: t("The regional map is stored on this device."),
        no_covering_map_pack: t("The map view is outside the selected region. Use Show region on map to return to its coverage."),
        no_map_packs_installed: t("Download a region to view its offline map."),
        map_pack_storage_unavailable: t("Offline map storage is unavailable. Reopen the app and try again."),
        map_pack_invalid: t("The stored map could not be opened. Remove this region and download it again."),
      }[snapshot?.status?.state] ?? t("Offline map unavailable.")));
    },
  });
}

function option(value, text) { const element = document.createElement("option"); element.value = value; element.textContent = text; return element; }
function appendText(parent, text) { const element = document.createElement("p"); element.textContent = text; parent.append(element); }
function button(label, action, key = "", primary = false) { const element = document.createElement("button"); element.type = "button";
  element.className = primary ? "button primary" : "button secondary"; element.dataset.regionAction = key; element.textContent = label; element.addEventListener("click", () => { void action(); }); return element; }
function bytes(value) { return `${(value / 1_000_000).toFixed(1)} MB`; }
