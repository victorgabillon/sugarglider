// A single style-independent DOM marker, owned by the existing map instance.
// Factory injection keeps lifecycle tests independent of WebGL/native Android.
export function createElevationMapMarker({createMarker}) {
  let map = null, marker = null, position = null;
  let created = 0, updates = 0;
  function clear() {
    marker?.remove(); marker = null; position = null;
  }
  function removed() { clear(); map = null; }
  function attach(nextMap) {
    if (map === nextMap) return;
    clear(); map?.off("remove", removed);
    map = nextMap; map?.on("remove", removed);
  }
  function show(value) {
    if (!map || !value?.coordinate || value.height_m === null) { clear(); return; }
    if (!marker) {
      const element = map.getContainer().ownerDocument.createElement("div");
      element.className = "elevation-map-marker";
      element.setAttribute("aria-hidden", "true");
      marker = createMarker(element).setLngLat(value.coordinate).addTo(map); created++;
    } else marker.setLngLat(value.coordinate);
    position = value; updates++;
  }
  function destroy() { clear(); map?.off("remove", removed); map = null; }
  return Object.freeze({attach, show, clear, destroy,
    diagnostics:() => ({active:Boolean(marker), coordinate:position?.coordinate ?? null,
      distance_m:position?.distance_m ?? null, created, updates})});
}
