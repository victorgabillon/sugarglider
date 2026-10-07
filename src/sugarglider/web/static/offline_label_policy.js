// Regional orientation, not a second Places catalog. Keep Protomaps light
// geometry, placement and colors; use only the font bundled with our shell.
const TEXT_FAMILIES = new Set([
  "places_locality", "places_subplace", "roads_labels_major", "roads_labels_minor",
  "water_waterway_label", "water_label_lakes", "water_label_ocean", "earth_label_islands",
]);

export function offlineBasemapPresentationLayer(original) {
  if (original.type === "background") return null;
  if (original.type !== "symbol") return original;
  // Exclude commercial/transit POIs, shields/arrows, house numbers and
  // country/region names: a regional trail map needs towns and streets first.
  if (!TEXT_FAMILIES.has(original.id)) return null;
  const textOnly = (fields = {}) => Object.fromEntries(
    Object.entries(fields).filter(([key]) => !key.startsWith("icon-")),
  );
  return {
    ...original,
    minzoom: original.id === "places_subplace" ? 14 : original.minzoom,
    layout: {
      ...textOnly(original.layout),
      // Avoid upstream formatted names that request unbundled script fonts.
      "text-field": ["coalesce", ["get", "name:fr"], ["get", "name"], ["get", "name:en"], ""],
      "text-font": ["Open Sans Semibold"],
      "text-allow-overlap": false,
      "text-ignore-placement": false,
    },
    paint: { ...textOnly(original.paint), "text-opacity": .85 },
  };
}
