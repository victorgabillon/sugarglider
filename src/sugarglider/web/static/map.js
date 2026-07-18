import { gpxFeatureCollection } from "./gpx.js";

const REQUIRED_LABEL_SOURCE = "required-point-labels";
const REQUIRED_LABEL_LAYER = "required-point-labels-ordinary";
const SELECTED_LABEL_LAYER = "required-point-labels-selected";
const REQUIRED_PIN_URL = "/static/brand/sugarglider-map-pin.png";
const EMPTY_COLLECTION = { type: "FeatureCollection", features: [] };

let map = null;
let ready = false;
let requiredMarkers = [];
let optionalMarkers = [];
let waypointMarkers = [];
let candidateClickHandler = null;
let requiredPointActivateHandler = null;

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
        glyphs: `${window.location.origin}/static/fonts/{fontstack}/{range}.pbf`,
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
    const labelLayers = [SELECTED_LABEL_LAYER, REQUIRED_LABEL_LAYER].filter((id) => map.getLayer(id));
    const label = labelLayers.length ? map.queryRenderedFeatures(event.point, { layers: labelLayers })[0] : null;
    if (label?.properties?.source_index !== undefined) {
      requiredPointActivateHandler?.(Number(label.properties.source_index));
      return;
    }
    const candidateLayers = candidateLineLayerIds();
    const candidate = candidateLayers.length ? map.queryRenderedFeatures(event.point, { layers: candidateLayers })[0] : null;
    if (candidate?.properties?.signature) {
      candidateClickHandler?.(candidate.properties.signature);
      return;
    }
    handlers.onMapClick({ lon: event.lngLat.lng, lat: event.lngLat.lat });
  });
  map.on("mousemove", (event) => {
    const interactiveLayers = [
      ...candidateLineLayerIds(),
      ...[SELECTED_LABEL_LAYER, REQUIRED_LABEL_LAYER].filter((id) => map.getLayer(id)),
    ];
    const interactive = interactiveLayers.length && map.queryRenderedFeatures(event.point, { layers: interactiveLayers }).length;
    map.getCanvas().style.cursor = interactive ? "pointer" : "";
  });
  map.on("error", (event) => {
    const rawMessage = event?.error?.message;
    const message = typeof rawMessage === "string" && rawMessage.length < 240 ? rawMessage : "A map tile, label, or style resource failed to load.";
    handlers.onError(`Map resource error: ${message}`);
  });
  return true;
}

function candidateLineLayerIds() {
  return (map?.getStyle()?.layers ?? [])
    .map((layer) => layer.id)
    .filter((id) => id.startsWith("candidate-") && id.endsWith("-line"));
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

function moveRequiredLabelsToTop() {
  if (!map) return;
  if (map.getLayer(REQUIRED_LABEL_LAYER)) map.moveLayer(REQUIRED_LABEL_LAYER);
  if (map.getLayer(SELECTED_LABEL_LAYER)) map.moveLayer(SELECTED_LABEL_LAYER);
}

export function renderCandidates(candidates, selectedSignature, showAll, onSelect) {
  if (!ready || !map) return;
  clearByPrefix("candidate-");
  candidateClickHandler = onSelect;
  candidates.forEach((candidate, index) => {
    if (!showAll && candidate.signature !== selectedSignature) return;
    const sourceId = `candidate-${index}`;
    sourceData(sourceId, {
      type: "Feature",
      properties: { signature: candidate.signature },
      geometry: { type: "LineString", coordinates: candidate.route.geometry },
    });
    const selected = candidate.signature === selectedSignature;
    map.addLayer({
      id: `${sourceId}-casing`,
      type: "line",
      source: sourceId,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": "#fffdf7",
        "line-width": selected ? 9 : 5,
        "line-opacity": selected ? 0.86 : 0.52,
      },
    });
    map.addLayer({
      id: `${sourceId}-line`,
      type: "line",
      source: sourceId,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": selected ? "#214b3b" : ["match", index % 4, 0, "#497c6c", 1, "#5f6d91", 2, "#7d6b52", "#596f63"],
        "line-width": selected ? 6 : 3,
        "line-opacity": selected ? 0.94 : 0.55,
        "line-dasharray": selected ? [1, 0] : [2.2, 1.4],
      },
    });
  });
  moveRequiredLabelsToTop();
}

export function renderVisualization(collection, showNature = false) {
  if (!ready || !map) return;
  clearByPrefix("selected-section-");
  sourceData("selected-sections", collection ?? EMPTY_COLLECTION);
  if (!collection) {
    moveRequiredLabelsToTop();
    return;
  }

  if (showNature) {
    const natureStyles = {
      woodland: { color: "#32744d", dash: [1, 0] },
      open_natural: { color: "#78a43b", dash: [3, 1.5] },
      agriculture: { color: "#a68b35", dash: [1, 1.4] },
      water: { color: "#2f84b7", dash: [1, 0] },
      urban: { color: "#747474", dash: [2, 1.5] },
      unknown: { color: "#aaa194", dash: [1, 1.5] },
    };
    Object.entries(natureStyles).forEach(([natureClass, style]) => {
      map.addLayer({
        id: `selected-section-nature-${natureClass}`,
        type: "line",
        source: "selected-sections",
        filter: ["==", ["get", "nature_class"], natureClass],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": style.color, "line-width": 13, "line-opacity": 0.48, "line-dasharray": style.dash },
      });
    });
  }

  const styles = {
    normal: { color: "#214b3b", width: 6, dash: [1, 0] },
    repeated: { color: "#d46a1f", width: 7, dash: [2, 1.4] },
    immediate_backtrack: { color: "#b73131", width: 9, dash: [1, .65] },
  };
  Object.entries(styles).forEach(([kind, style]) => {
    map.addLayer({
      id: `selected-section-${kind}`,
      type: "line",
      source: "selected-sections",
      filter: ["==", ["get", "kind"], kind],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": style.color,
        "line-width": style.width,
        "line-dasharray": style.dash,
      },
    });
  });
  moveRequiredLabelsToTop();
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

function displayName(point, orderIndex) {
  const name = typeof point?.name === "string" ? point.name.trim() : "";
  return name || `Point ${orderIndex + 1}`;
}

function validCoordinate(point) {
  return Number.isFinite(point?.lat)
    && Number.isFinite(point?.lon)
    && Math.abs(point.lat) <= 90
    && Math.abs(point.lon) <= 180;
}

function orderedEntries(points, visits) {
  if (!visits?.length) {
    return points.map((point, sourceIndex) => ({ point, sourceIndex }));
  }
  return visits
    .map((visit) => ({
      point: points[visit.original_index] ?? visit.coordinate,
      sourceIndex: visit.original_index,
    }))
    .filter(({ point }) => point !== undefined);
}

function popupContent(point, sourceIndex, visitOrder, start) {
  const content = document.createElement("div");
  content.className = "point-popup";
  const heading = document.createElement("strong");
  heading.textContent = `${visitOrder}. ${displayName(point, visitOrder - 1)}`;
  content.append(heading);
  if (start) {
    const status = document.createElement("p");
    status.className = "popup-status";
    status.textContent = "Start and end of the loop";
    content.append(status);
  }
  const coordinate = document.createElement("p");
  coordinate.textContent = `${Number(point.lat).toFixed(6)}, ${Number(point.lon).toFixed(6)}`;
  content.append(coordinate);
  const original = document.createElement("p");
  const originalIndex = Number.isInteger(point.originalIndex) ? point.originalIndex : sourceIndex;
  original.textContent = `Original request point ${originalIndex + 1}`;
  content.append(original);
  return content;
}

function requiredMarkerElement(point, sourceIndex, visitOrder, selected, start, disabled) {
  const name = displayName(point, visitOrder - 1);
  const element = document.createElement("button");
  element.type = "button";
  element.className = `required-marker${start ? " start" : ""}${selected ? " selected" : ""}${disabled ? " disabled" : ""}`;
  element.dataset.pointIndex = String(sourceIndex);
  element.disabled = disabled;
  element.setAttribute("aria-pressed", String(selected));
  element.dataset.accessibleLabel = `Required point ${visitOrder}, ${name}${start ? ", start and end" : ""}`;
  element.setAttribute("aria-label", element.dataset.accessibleLabel);
  element.title = `${visitOrder}. ${name}${start ? " · start/end" : ""}`;

  const visual = document.createElement("span");
  visual.className = "required-marker-visual";
  const image = document.createElement("img");
  image.src = REQUIRED_PIN_URL;
  image.alt = "";
  image.width = 40;
  image.height = 60;
  image.draggable = false;
  const number = document.createElement("span");
  number.className = "required-marker-number";
  number.textContent = String(visitOrder);
  visual.append(image, number);
  if (start) {
    const startBadge = document.createElement("span");
    startBadge.className = "required-marker-start";
    startBadge.textContent = "START";
    visual.append(startBadge);
  }
  element.append(visual);
  return element;
}

function renderRequiredLabels(entries, selectedIndex) {
  if (!ready || !map) return;
  const features = entries
    .filter(({ point }) => validCoordinate(point))
    .map(({ point, sourceIndex }, orderIndex) => {
      const selected = sourceIndex === selectedIndex;
      const start = orderIndex === 0;
      return {
        type: "Feature",
        id: sourceIndex,
        geometry: { type: "Point", coordinates: [point.lon, point.lat] },
        properties: {
          display_name: displayName(point, orderIndex),
          visit_order: orderIndex + 1,
          original_request_index: Number.isInteger(point.originalIndex) ? point.originalIndex : sourceIndex,
          source_index: sourceIndex,
          start,
          selected,
          sort_priority: selected ? 0 : start ? 1 : orderIndex + 10,
        },
      };
    });
  if (!features.length) {
    removeLayer(SELECTED_LABEL_LAYER);
    removeLayer(REQUIRED_LABEL_LAYER);
    removeSource(REQUIRED_LABEL_SOURCE);
    return;
  }

  sourceData(REQUIRED_LABEL_SOURCE, { type: "FeatureCollection", features });
  const sharedLayout = {
    "symbol-placement": "point",
    "symbol-sort-key": ["get", "sort_priority"],
    "text-field": ["concat", ["to-string", ["get", "visit_order"]], ". ", ["get", "display_name"]],
    "text-font": ["Open Sans Semibold"],
    "text-size": ["interpolate", ["linear"], ["zoom"], 8, 10, 12, 11, 15, 13],
    "text-variable-anchor": ["top", "bottom", "left", "right", "top-left", "top-right"],
    "text-radial-offset": 3.1,
    "text-justify": "auto",
    "text-max-width": 14,
    "text-line-height": 1.15,
    "text-padding": 3,
  };
  const sharedPaint = {
    "text-color": "#252721",
    "text-halo-color": "#fffef9",
    "text-halo-width": 2,
    "text-halo-blur": .5,
  };
  if (!map.getLayer(REQUIRED_LABEL_LAYER)) {
    map.addLayer({
      id: REQUIRED_LABEL_LAYER,
      type: "symbol",
      source: REQUIRED_LABEL_SOURCE,
      minzoom: 10.5,
      filter: ["==", ["get", "selected"], false],
      layout: {
        ...sharedLayout,
        "text-allow-overlap": false,
        "text-ignore-placement": false,
      },
      paint: {
        ...sharedPaint,
        "text-opacity": ["interpolate", ["linear"], ["zoom"], 10.5, .72, 12, .88, 15, 1],
      },
    });
  }
  if (!map.getLayer(SELECTED_LABEL_LAYER)) {
    map.addLayer({
      id: SELECTED_LABEL_LAYER,
      type: "symbol",
      source: REQUIRED_LABEL_SOURCE,
      minzoom: 7,
      filter: ["==", ["get", "selected"], true],
      layout: {
        ...sharedLayout,
        "text-size": 13,
        "text-allow-overlap": true,
        "text-ignore-placement": true,
      },
      paint: {
        ...sharedPaint,
        "text-color": "#153d2e",
        "text-halo-width": 3,
      },
    });
  }
  moveRequiredLabelsToTop();
}

export function renderRequiredMarkers(points, visits, selectedIndex, popupIndex, disabled, handlers) {
  if (!map) return;
  clearMarkers(requiredMarkers);
  requiredPointActivateHandler = handlers.onActivate;
  const entries = orderedEntries(points, visits);
  entries.forEach(({ point, sourceIndex }, orderIndex) => {
    if (!validCoordinate(point)) return;
    const selected = sourceIndex === selectedIndex;
    const start = orderIndex === 0;
    const element = requiredMarkerElement(point, sourceIndex, orderIndex + 1, selected, start, disabled);
    const marker = new window.maplibregl.Marker({
      element,
      draggable: !disabled,
      anchor: "bottom",
      offset: [0, start ? 16 : 13],
    })
      .setLngLat([point.lon, point.lat])
      .addTo(map);
    // MapLibre assigns a generic root label while attaching a marker. Restore the
    // point-specific accessible name after attachment.
    element.setAttribute("aria-label", element.dataset.accessibleLabel);
    const popup = new window.maplibregl.Popup({
      offset: [0, start ? -58 : -48],
      closeButton: true,
      focusAfterOpen: false,
    })
      .setDOMContent(popupContent(point, sourceIndex, orderIndex + 1, start));
    marker.setPopup(popup);
    element.addEventListener("click", (event) => {
      event.stopPropagation();
      handlers.onActivate(sourceIndex);
    });
    marker.on("dragstart", () => {
      element.classList.add("dragging");
    });
    marker.on("dragend", () => {
      element.classList.remove("dragging");
      const position = marker.getLngLat();
      // Finalize selection with the coordinate update so rendering never replaces
      // the active MapLibre marker halfway through its drag gesture.
      handlers.onDrag(sourceIndex, { lon: position.lng, lat: position.lat });
    });
    if (popupIndex === sourceIndex) marker.togglePopup();
    requiredMarkers.push(marker);
  });
  renderRequiredLabels(entries, selectedIndex);
}

function simpleMarkerElement(className, label) {
  const element = document.createElement("button");
  element.type = "button";
  element.className = `map-marker ${className}`;
  element.setAttribute("aria-label", label);
  element.title = label;
  return element;
}

export function renderOptionalMarkers(points) {
  if (!map) return;
  clearMarkers(optionalMarkers);
  points.forEach((point) => {
    const marker = new window.maplibregl.Marker({
      element: simpleMarkerElement("optional", "Generated routing point"),
    })
      .setLngLat([point.lon, point.lat])
      .setPopup(new window.maplibregl.Popup({ offset: 12 }).setText("Generated routing point"))
      .addTo(map);
    optionalMarkers.push(marker);
  });
}

export function renderImportedGpx(imported) {
  if (!ready || !map) return;
  removeLayer("imported-gpx-line");
  removeLayer("imported-gpx-casing");
  removeSource("imported-gpx");
  clearMarkers(waypointMarkers);
  if (!imported) return;
  sourceData("imported-gpx", gpxFeatureCollection(imported));
  map.addLayer({
    id: "imported-gpx-casing",
    type: "line",
    source: "imported-gpx",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#fff", "line-width": 7, "line-opacity": .75 },
  });
  map.addLayer({
    id: "imported-gpx-line",
    type: "line",
    source: "imported-gpx",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#276f92", "line-width": 4, "line-opacity": .88, "line-dasharray": [1.2, 1] },
  });
  imported.waypoints.forEach((waypoint) => {
    const marker = new window.maplibregl.Marker({
      element: simpleMarkerElement("waypoint", `Imported GPX waypoint: ${waypoint.name}`),
    })
      .setLngLat(waypoint.coordinate)
      .setPopup(new window.maplibregl.Popup({ offset: 12 }).setText(waypoint.name))
      .addTo(map);
    waypointMarkers.push(marker);
  });
  moveRequiredLabelsToTop();
}

export function fitCoordinates(coordinates) {
  if (!map) return;
  const valid = coordinates.filter((coordinate) => Array.isArray(coordinate)
    && coordinate.length >= 2
    && Number.isFinite(coordinate[0])
    && Number.isFinite(coordinate[1]));
  if (!valid.length) return;
  const bounds = valid.reduce(
    (result, coordinate) => result.extend(coordinate),
    new window.maplibregl.LngLatBounds(valid[0], valid[0]),
  );
  map.fitBounds(bounds, {
    padding: 70,
    maxZoom: 15,
    duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 500,
  });
}

export function resizeMap() { map?.resize(); }
