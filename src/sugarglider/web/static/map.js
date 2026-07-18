import { gpxFeatureCollection } from "./gpx.js";

let map = null;
let ready = false;
let requiredMarkers = [];
let optionalMarkers = [];
let waypointMarkers = [];
let candidateClickHandler = null;

const EMPTY_COLLECTION = { type: "FeatureCollection", features: [] };

export function initializeMap(config, handlers) {
  if (!window.maplibregl) {
    handlers.onError("MapLibre could not load. Check the browser network policy or CDN availability.");
    return false;
  }
  try {
    map = new window.maplibregl.Map({
      container: "map",
      center: config.initial_center,
      zoom: config.initial_zoom,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: [config.tile_url_template],
            tileSize: 256,
            attribution: config.tile_attribution,
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      attributionControl: true,
    });
  } catch {
    handlers.onError("MapLibre loaded, but this browser could not initialize WebGL. Route controls remain available.");
    return false;
  }
  map.addControl(new window.maplibregl.NavigationControl(), "top-left");
  map.on("load", () => { ready = true; handlers.onReady(); });
  map.on("click", (event) => {
    const candidateLayers = (map.getStyle()?.layers ?? []).map((layer) => layer.id).filter((id) => id.startsWith("candidate-") && id.endsWith("-line"));
    const candidate = candidateLayers.length ? map.queryRenderedFeatures(event.point, { layers: candidateLayers })[0] : null;
    if (candidate?.properties?.signature) {
      candidateClickHandler?.(candidate.properties.signature);
      return;
    }
    handlers.onMapClick({ lon: event.lngLat.lng, lat: event.lngLat.lat });
  });
  map.on("mousemove", (event) => {
    const candidateLayers = (map.getStyle()?.layers ?? []).map((layer) => layer.id).filter((id) => id.startsWith("candidate-") && id.endsWith("-line"));
    const overCandidate = candidateLayers.length && map.queryRenderedFeatures(event.point, { layers: candidateLayers }).length;
    map.getCanvas().style.cursor = overCandidate ? "pointer" : "";
  });
  map.on("error", (event) => {
    const rawMessage = event?.error?.message;
    const message = typeof rawMessage === "string" && rawMessage.length < 240 ? rawMessage : "A map tile or style resource failed to load.";
    handlers.onError(`Map resource error: ${message}`);
  });
  return true;
}

function sourceData(id, data) {
  if (!ready || !map) return;
  const source = map.getSource(id);
  if (source) source.setData(data);
  else map.addSource(id, { type: "geojson", data });
}

function removeLayer(id) {
  if (map?.getLayer(id)) map.removeLayer(id);
}

function removeSource(id) {
  if (map?.getSource(id)) map.removeSource(id);
}

function clearByPrefix(prefix) {
  if (!map) return;
  for (const layer of [...(map.getStyle()?.layers ?? [])].reverse()) {
    if (layer.id.startsWith(prefix)) removeLayer(layer.id);
  }
  for (const id of Object.keys(map.getStyle()?.sources ?? {})) {
    if (id.startsWith(prefix)) removeSource(id);
  }
}

export function renderCandidates(candidates, selectedSignature, showAll, onSelect) {
  if (!ready || !map) return;
  clearByPrefix("candidate-");
  candidateClickHandler = onSelect;
  candidates.forEach((candidate, index) => {
    if (!showAll && candidate.signature !== selectedSignature) return;
    const sourceId = `candidate-${index}`;
    const layerId = `${sourceId}-line`;
    sourceData(sourceId, { type: "Feature", properties: { signature: candidate.signature }, geometry: { type: "LineString", coordinates: candidate.route.geometry } });
    const selected = candidate.signature === selectedSignature;
    map.addLayer({
      id: layerId,
      type: "line",
      source: sourceId,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": selected ? "#173d32" : ["match", index % 4, 0, "#497c6c", 1, "#5f6d91", 2, "#7d6b52", "#596f63"],
        "line-width": selected ? 6 : 3,
        "line-opacity": selected ? 0.9 : 0.48,
      },
    });
  });
}

export function renderVisualization(collection, showNature = false) {
  if (!ready || !map) return;
  clearByPrefix("selected-section-");
  sourceData("selected-sections", collection ?? EMPTY_COLLECTION);
  const styles = {
    normal: { color: "#173d32", width: 6, dash: [1, 0] },
    repeated: { color: "#d97706", width: 7, dash: [2, 1.4] },
    immediate_backtrack: { color: "#bb2d2d", width: 9, dash: [1, 0.65] },
  };
  if (showNature) {
    const natureStyles = {
      woodland: { color: "#32744d", dash: [1, 0] },
      open_natural: { color: "#78a43b", dash: [3, 1.2] },
      agriculture: { color: "#b59a48", dash: [1.2, 1.2] },
      urban: { color: "#787878", dash: [2, 0.8] },
      water: { color: "#2f84b7", dash: [3, 1] },
      unknown: { color: "#b8afa4", dash: [0.6, 1.4] },
    };
    Object.entries(natureStyles).forEach(([natureClass, style]) => {
      map.addLayer({
        id: `selected-section-nature-${natureClass}`,
        type: "line",
        source: "selected-sections",
        filter: ["==", ["get", "nature_class"], natureClass],
        layout: { "line-cap": "butt", "line-join": "round" },
        paint: { "line-color": style.color, "line-width": 16, "line-opacity": 0.72, "line-dasharray": style.dash },
      });
    });
  }
  Object.entries(styles).forEach(([kind, style]) => {
    map.addLayer({
      id: `selected-section-${kind}`,
      type: "line",
      source: "selected-sections",
      filter: ["==", ["get", "kind"], kind],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": style.color, "line-width": style.width, "line-dasharray": style.dash },
    });
  });
}

export function clearRoutes() {
  if (!ready) return;
  clearByPrefix("candidate-");
  clearByPrefix("selected-section-");
  removeSource("selected-sections");
  clearMarkers(optionalMarkers);
}

function clearMarkers(markers) {
  markers.forEach((marker) => marker.remove());
  markers.length = 0;
}

function markerElement(className, label = "") {
  const element = document.createElement("div");
  element.className = `map-marker ${className}`;
  element.textContent = label;
  element.setAttribute("aria-label", label ? `Mandatory point ${label}` : className);
  return element;
}

export function renderRequiredMarkers(points, visits, onDrag) {
  if (!map) return;
  clearMarkers(requiredMarkers);
  const ordered = visits?.length ? visits.map((visit) => ({
    point: points[visit.original_index] ?? visit.coordinate,
    originalIndex: visit.original_index,
  })) : points.map((point, originalIndex) => ({ point, originalIndex }));
  ordered.forEach(({ point, originalIndex }, orderIndex) => {
    const marker = new window.maplibregl.Marker({ element: markerElement("mandatory", String(orderIndex + 1)), draggable: true })
      .setLngLat([point.lon, point.lat])
      .addTo(map);
    marker.on("dragend", () => {
      const position = marker.getLngLat();
      onDrag(originalIndex, { lon: position.lng, lat: position.lat });
    });
    requiredMarkers.push(marker);
  });
}

export function renderOptionalMarkers(points) {
  if (!map) return;
  clearMarkers(optionalMarkers);
  points.forEach((point) => optionalMarkers.push(new window.maplibregl.Marker({ element: markerElement("optional") }).setLngLat([point.lon, point.lat]).addTo(map)));
}

export function renderImportedGpx(imported) {
  if (!ready || !map) return;
  removeLayer("imported-gpx-line");
  removeSource("imported-gpx");
  clearMarkers(waypointMarkers);
  if (!imported) return;
  sourceData("imported-gpx", gpxFeatureCollection(imported));
  map.addLayer({
    id: "imported-gpx-line",
    type: "line",
    source: "imported-gpx",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#276c8e", "line-width": 4, "line-opacity": 0.82, "line-dasharray": [1.2, 1] },
  });
  imported.waypoints.forEach((waypoint) => {
    const marker = new window.maplibregl.Marker({ element: markerElement("waypoint") }).setLngLat(waypoint.coordinate).setPopup(new window.maplibregl.Popup({ offset: 12 }).setText(waypoint.name)).addTo(map);
    waypointMarkers.push(marker);
  });
}

export function fitCoordinates(coordinates) {
  if (!map || !coordinates.length) return;
  const bounds = coordinates.reduce((result, coordinate) => result.extend(coordinate), new window.maplibregl.LngLatBounds(coordinates[0], coordinates[0]));
  map.fitBounds(bounds, { padding: 65, maxZoom: 15, duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 500 });
}

export function resizeMap() { map?.resize(); }
