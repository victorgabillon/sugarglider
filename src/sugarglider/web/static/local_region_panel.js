import { createLocalRegionClient } from "./local_region_client.js";

// Temporary development surface over the reusable component store. PR42 supplies
// the normal catalog and coordinates map/native routing installation separately.
export function createLocalRegionPanel(elements, client = createLocalRegionClient()) {
  let busy = false;
  async function refresh() {
    try {
      const regions = await client.list();
      elements.regions.replaceChildren();
      for (const region of regions) {
        const item = document.createElement("li");
        item.textContent = region.status === "installed"
          ? `${region.manifest.display_name} · places and nature installed · ${region.manifest.build_id.slice(0, 12)}`
          : `${region.region_id} · ${region.code} · remove and reinstall to recover`;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "button secondary";
        remove.textContent = "Remove places and nature";
        remove.disabled = busy;
        remove.addEventListener("click", async () => {
          if (busy || !globalThis.confirm(`Remove local places and nature for ${region.region_id}?`)) return;
          try { await client.remove(region.region_id); await refresh(); }
          catch (error) { elements.status.textContent = `Region removal failed (${error.code ?? "storage_unavailable"}).`; }
        });
        item.append(remove);
        elements.regions.append(item);
      }
      if (!regions.length) elements.status.textContent = "No local places/nature installed. Local routing remains independent.";
    } catch (error) { elements.status.textContent = `Local places/nature unavailable (${error.code ?? "storage_unavailable"}).`; }
  }
  async function install() {
    if (busy) return;
    busy = true;
    elements.install.disabled = true;
    elements.cancel.disabled = false;
    elements.status.textContent = "Downloading and validating regional places and nature…";
    try {
      const manifest = await client.install(elements.url.value);
      elements.status.textContent = `${manifest.display_name}: verified places and nature installed. Map and routing installation are separate.`;
    } catch (error) {
      elements.status.textContent = `Places/nature installation failed (${error.code ?? "storage_unavailable"}); any previous active version is preserved.`;
    } finally {
      busy = false;
      elements.install.disabled = false;
      elements.cancel.disabled = true;
      await refresh();
    }
  }
  elements.install.addEventListener("click", install);
  elements.cancel.addEventListener("click", () => client.cancelInstall());
  void refresh();
  async function getRegionData(packId) {
    if (!packId || busy) return null;
    const regions = (await client.list()).filter((region) => region.status === "installed"
      && region.manifest.components.routing.component_id === packId);
    if (regions.length !== 1) return null;
    return client.load(regions[0].region_id);
  }
  return Object.freeze({ getRegionData });
}
