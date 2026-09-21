// Presentation only. These entries never assign routing eligibility or rewards.
export const ICE_CREAM_ART_URL = "/static/brand/sugarglider-ice-cream-pin.png";
const category = (label, icon, priority = 20, minZoom = 0, labelZoom = 13, richImage = null) =>
  Object.freeze({ label, icon, priority, minZoom, labelZoom, richImage });
export const PLACE_PRESENTATIONS = Object.freeze({
  viewpoint: category("Viewpoint", "poi-viewpoint"),
  observation_tower: category("Observation tower", "poi-tower"),
  castle: category("Castle", "poi-historic"),
  archaeological_site: category("Archaeological site", "poi-historic"),
  ruins: category("Historic ruins", "poi-historic"),
  tourism_attraction: category("Tourist attraction", "poi-attraction", 30),
  drinking_water: category("Drinking water", "poi-water-verified", 10),
  fountain: category("Fountain", "poi-water-unknown", 10),
  water_tap: category("Water tap", "poi-water-unknown", 10),
  ice_cream: category("Ice cream", "poi-ice-cream", 40, 13, 15, ICE_CREAM_ART_URL),
});

export const ICE_CREAM_ICON_SVG = '<path d="m17 27 7 14 7-14Z" fill="#f4c48d" stroke="#873054" stroke-width="2.5" stroke-linejoin="round"/><path d="M14 23a10 10 0 0 1 20 0c4 1 3 7-1 7-2 0-3-1-4-2-2 3-7 3-9 0-4 4-10-1-6-5Z" fill="#f5a9c7" stroke="#873054" stroke-width="2.5"/>';

export function placePresentation(feature) {
  const presentation = PLACE_PRESENTATIONS[feature.category];
  if (!presentation) return category("Mapped place", "poi-attraction");
  if (feature.potability === "non_potable") return { ...presentation, icon: "poi-water-nonpotable" };
  if (feature.potability === "unknown") return { ...presentation, icon: "poi-water-unknown" };
  if (feature.potability === "verified") return { ...presentation, icon: "poi-water-verified" };
  return presentation;
}

export function placeAddress(feature) {
  const tags = Object.fromEntries(feature.tags ?? []);
  const street = [tags["addr:housenumber"], tags["addr:street"] ?? tags["addr:place"]].filter(Boolean).join(" ");
  const town = [tags["addr:postcode"], tags["addr:city"]].filter(Boolean).join(" ");
  return [street, town].filter(Boolean).join(", ");
}

export function createPlaceDetails(feature, { onCenter = null } = {}) {
  const presentation = placePresentation(feature);
  const content = document.createElement("section");
  content.className = "place-details";
  content.setAttribute("aria-label", `${presentation.label}: ${feature.display_name}`);
  const header = document.createElement("div"); header.className = "place-details-heading";
  if (presentation.richImage) {
    const artwork = document.createElement("img");
    artwork.src = presentation.richImage; artwork.alt = "";
    artwork.width = 72; artwork.height = 108;
    header.append(artwork);
  }
  const identity = document.createElement("div");
  const label = document.createElement("p"); label.className = "place-category"; label.textContent = presentation.label;
  const name = document.createElement("h3"); name.textContent = feature.display_name;
  identity.append(label, name); header.append(identity); content.append(header);
  const address = placeAddress(feature);
  const location = document.createElement("p"); location.className = "place-address";
  location.textContent = address || `${feature.coordinate.lat.toFixed(5)}, ${feature.coordinate.lon.toFixed(5)}`;
  content.append(location);
  const tags = Object.fromEntries(feature.tags ?? []);
  for (const [label, value] of [["Mapped hours", tags.opening_hours], ["Seasonal", tags.seasonal],
    ["Access", ["private", "restricted"].includes(feature.access_status) ? feature.access_status : null]]) {
    if (!value) continue;
    const row = document.createElement("p"); row.textContent = `${label}: ${value}`; content.append(row);
  }
  if (onCenter) {
    const center = document.createElement("button"); center.type = "button";
    center.className = "button secondary place-center"; center.textContent = "Center on map";
    center.addEventListener("click", () => onCenter(feature)); content.append(center);
  }
  const credit = document.createElement("p"); credit.className = "place-data-note";
  credit.textContent = "OpenStreetMap · Opening times may have changed."; content.append(credit);
  return content;
}
