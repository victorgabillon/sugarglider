// Eligibility and reduction only: acquisition remains owned by the shared planner.
export function resolvedPoiLocation(feature) {
  if (!["public", "unknown"].includes(feature?.access_status)
      || feature.potability === "non_potable") return null;
  const { lat, lon } = feature.coordinate ?? {};
  const name = typeof feature.display_name === "string" ? feature.display_name.trim() : "";
  if (!Number.isFinite(lat) || Math.abs(lat) > 90
      || !Number.isFinite(lon) || Math.abs(lon) > 180
      || !name || name.length > 200 || /[\u0000-\u001f\u007f]/u.test(name)) return null;
  return { name, lat, lon };
}
