import { gpxFeatureCollection } from "./gpx.js";
import { requestedPlaceIdentifier } from "./state.js";

const REQUIRED_LABEL_SOURCE = "required-point-labels";
const REQUIRED_LABEL_LAYER = "required-point-labels-ordinary";
const SELECTED_LABEL_LAYER = "required-point-labels-selected";
const REQUIRED_PIN_URL = "/static/brand/sugarglider-map-pin.png";
const VERIFIED_WATER_PIN_URL = "/static/brand/sugarglider-water-pin.png";
const EMPTY_COLLECTION = { type: "FeatureCollection", features: [] };
const POI_SOURCE = "places-pois";
const POI_SELECTED_SOURCE = "places-poi-selected-source";
const POI_CLUSTER_LAYER = "places-poi-clusters";
const POI_CLUSTER_COUNT_LAYER = "places-poi-cluster-count";
const POI_MARKER_LAYER = "places-poi-markers";
const POI_SELECTED_LAYER = "places-poi-selected";
const POI_SELECTED_MARKER_LAYER = "places-poi-selected-marker";
const POI_LABEL_LAYER = "places-poi-labels";
const POI_SELECTED_LABEL_LAYER = "places-poi-selected-label";
const POI_VISITED_LAYER = "places-poi-visited";
const REQUESTED_SOURCE = "auto-tour-requested-places";
const REQUESTED_RADIUS_SOURCE = "auto-tour-requested-place-radii";
const REQUESTED_RADIUS_FILL_LAYER = "auto-tour-requested-radius-fill";
const REQUESTED_RADIUS_LINE_LAYER = "auto-tour-requested-radius-line";
const REQUESTED_MARKER_LAYER = "auto-tour-requested-markers";
const REQUESTED_PREFERRED_LAYER = "auto-tour-requested-preferred-ring";
const REQUESTED_ORDER_LAYER = "auto-tour-requested-order";
const REQUESTED_LABEL_LAYER = "auto-tour-requested-labels";
const REQUESTED_SELECTED_LAYER = "auto-tour-requested-selected";
const REQUESTED_RADIUS_SEGMENTS = 48;

const POI_ICON_SVGS = {
  "poi-viewpoint": '<path d="M6 36 20 14l8 12 6-8 8 18Z" fill="#fff"/><path d="m13 30 7-11 7 11" fill="none" stroke="#214b3b" stroke-width="3"/>',
  "poi-historic": '<path d="M9 17h6v-5h6v5h6v-5h6v5h6v22H9Z" fill="#fff"/><path d="M18 39V28h12v11M9 21h30" fill="none" stroke="#6d4a2d" stroke-width="3"/>',
  "poi-tower": '<path d="M19 10h10l-2 7 7 22H14l7-22Z" fill="#fff"/><path d="M16 24h16M13 39h22" fill="none" stroke="#3c5268" stroke-width="3"/>',
  "poi-attraction": '<path d="m24 8 4.5 9.3 10.2 1.5-7.4 7.2 1.8 10.2L24 31.4l-9.1 4.8L16.7 26l-7.4-7.2 10.2-1.5Z" fill="#fff" stroke="#7b4d7f" stroke-width="2.5"/>',
  "poi-water-unknown": '<path d="M24 7c-2 6-11 14-11 23a11 11 0 0 0 22 0C35 21 26 13 24 7Z" fill="#fff"/><path d="M21 24c0-4 7-4 7 0 0 3-4 3-4 6m0 5h.01" fill="none" stroke="#9a6816" stroke-linecap="round" stroke-width="3.5"/>',
  "poi-water-nonpotable": '<path d="M24 7c-2 6-11 14-11 23a11 11 0 0 0 22 0C35 21 26 13 24 7Z" fill="#fff"/><path d="m18 24 12 12m0-12L18 36" fill="none" stroke="#a73535" stroke-linecap="round" stroke-width="3.5"/>',
};

let map = null;
let ready = false;
let requiredMarkers = [];
let optionalMarkers = [];
let waypointMarkers = [];
let candidateClickHandler = null;
let requiredPointActivateHandler = null;
let poiActivateHandler = null;
let poiPreferHandler = null;
let preferredPoiIds = new Set();
let poiById = new Map();
let poiPopup = null;
let requestedPlaceActivateHandler = null;
let requestedPlaceById = new Map();
let requestedPlacePopup = null;
let requestedPlacePopupId = null;
let requestedRadiusFeatureCount = 0;

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
  map.on("load", async () => {
    try {
      await installPoiImages();
    } catch {
      handlers.onError("Local place icons could not be prepared. Route controls remain available.");
    }
    ready = true;
    handlers.onReady();
    handlers.onViewportChange?.(currentViewportBounds());
  });
  map.on("moveend", () => {
    if (ready) handlers.onViewportChange?.(currentViewportBounds());
  });
  map.on("click", (event) => {
    const labelLayers = [SELECTED_LABEL_LAYER, REQUIRED_LABEL_LAYER].filter((id) => map.getLayer(id));
    const label = labelLayers.length ? map.queryRenderedFeatures(event.point, { layers: labelLayers })[0] : null;
    if (label?.properties?.source_index !== undefined) {
      requiredPointActivateHandler?.(Number(label.properties.source_index));
      return;
    }
    const requestedLayers = [
      REQUESTED_SELECTED_LAYER,
      REQUESTED_ORDER_LAYER,
      REQUESTED_PREFERRED_LAYER,
      REQUESTED_MARKER_LAYER,
    ].filter((id) => map.getLayer(id));
    const requested = requestedLayers.length
      ? map.queryRenderedFeatures(event.point, { layers: requestedLayers })[0]
      : null;
    if (requested?.properties?.requested_id) {
      const feature = requestedPlaceById.get(requested.properties.requested_id);
      if (feature) {
        requestedPlaceActivateHandler?.(feature.id);
        showRequestedPlacePopup(feature);
      }
      return;
    }
    const poiLayers = [POI_SELECTED_MARKER_LAYER, POI_MARKER_LAYER]
      .filter((id) => map.getLayer(id));
    const poi = poiLayers.length
      ? map.queryRenderedFeatures(event.point, { layers: poiLayers })[0]
      : null;
    if (poi?.properties?.poi_id) {
      const feature = poiById.get(poi.properties.poi_id);
      if (feature) {
        poiActivateHandler?.(feature.id);
        showPoiPopup(feature);
      }
      return;
    }
    const cluster = map.getLayer(POI_CLUSTER_LAYER)
      ? map.queryRenderedFeatures(event.point, { layers: [POI_CLUSTER_LAYER] })[0]
      : null;
    if (cluster?.properties?.cluster_id !== undefined) {
      const source = map.getSource(POI_SOURCE);
      source?.getClusterExpansionZoom(cluster.properties.cluster_id)
        .then((zoom) => map.easeTo({ center: cluster.geometry.coordinates, zoom }))
        .catch(() => {});
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
      ...[
        REQUESTED_SELECTED_LAYER,
        REQUESTED_ORDER_LAYER,
        REQUESTED_PREFERRED_LAYER,
        REQUESTED_MARKER_LAYER,
      ].filter((id) => map.getLayer(id)),
      ...[POI_SELECTED_MARKER_LAYER, POI_MARKER_LAYER, POI_CLUSTER_LAYER]
        .filter((id) => map.getLayer(id)),
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

function svgMarkup(body) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48"><circle cx="24" cy="24" r="22" fill="#fffdf7" stroke="#214b3b" stroke-width="3"/>${body}</svg>`;
}

function loadSvgImage(body) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(new Blob([svgMarkup(body)], { type: "image/svg+xml" }));
    const image = new Image(48, 48);
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = (error) => {
      URL.revokeObjectURL(url);
      reject(error);
    };
    image.src = url;
  });
}

function loadRasterImage(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = url;
  });
}

async function installPoiImages() {
  if (!map.hasImage("poi-water-verified")) {
    map.addImage("poi-water-verified", await loadRasterImage(VERIFIED_WATER_PIN_URL), {
      pixelRatio: 32,
    });
  }
  for (const [name, body] of Object.entries(POI_ICON_SVGS)) {
    if (!map.hasImage(name)) {
      map.addImage(name, await loadSvgImage(body), { pixelRatio: 2 });
    }
  }
}

function firstRouteLayerId() {
  return (map?.getStyle()?.layers ?? []).find((layer) => (
    layer.id.startsWith("candidate-")
    || layer.id.startsWith("selected-section-")
    || layer.id.startsWith("imported-gpx-")
  ))?.id;
}

function addPoiLayer(layer) {
  if (!map.getLayer(layer.id)) map.addLayer(layer, firstRouteLayerId());
}

function ensurePoiLayers() {
  if (!ready || !map) return;
  if (!map.getSource(POI_SOURCE)) {
    map.addSource(POI_SOURCE, {
      type: "geojson",
      data: EMPTY_COLLECTION,
      cluster: true,
      clusterMaxZoom: 13,
      clusterRadius: 44,
    });
  }
  if (!map.getSource(POI_SELECTED_SOURCE)) {
    map.addSource(POI_SELECTED_SOURCE, { type: "geojson", data: EMPTY_COLLECTION });
  }
  addPoiLayer({
    id: POI_CLUSTER_LAYER,
    type: "circle",
    source: POI_SOURCE,
    filter: ["has", "point_count"],
    paint: {
      "circle-color": "#fff8df",
      "circle-stroke-color": "#214b3b",
      "circle-stroke-width": 3,
      "circle-radius": ["step", ["get", "point_count"], 15, 25, 19, 100, 23],
    },
  });
  addPoiLayer({
    id: POI_CLUSTER_COUNT_LAYER,
    type: "symbol",
    source: POI_SOURCE,
    filter: ["has", "point_count"],
    layout: {
      "text-field": ["get", "point_count_abbreviated"],
      "text-font": ["Open Sans Semibold"],
      "text-size": 11,
    },
    paint: { "text-color": "#214b3b" },
  });
  addPoiLayer({
    id: POI_SELECTED_LAYER,
    type: "circle",
    source: POI_SELECTED_SOURCE,
    paint: {
      "circle-radius": 19,
      "circle-color": "#fff",
      "circle-opacity": .8,
      "circle-stroke-color": "#d9582b",
      "circle-stroke-width": 4,
    },
  });
  addPoiLayer({
    id: POI_VISITED_LAYER,
    type: "circle",
    source: POI_SOURCE,
    filter: ["all", ["!", ["has", "point_count"]], ["==", ["get", "visited"], true]],
    paint: {
      "circle-radius": 20,
      "circle-color": "#fffdf7",
      "circle-opacity": .82,
      "circle-stroke-color": "#d9582b",
      "circle-stroke-width": 5,
    },
  });
  addPoiLayer({
    id: POI_MARKER_LAYER,
    type: "symbol",
    source: POI_SOURCE,
    filter: ["!", ["has", "point_count"]],
    layout: {
      "icon-image": ["get", "icon_name"],
      "icon-size": ["interpolate", ["linear"], ["zoom"], 8, .75, 14, 1],
      "icon-allow-overlap": false,
      "icon-padding": 2,
      "symbol-sort-key": ["case", ["get", "selected"], 0, 1],
    },
  });
  addPoiLayer({
    id: POI_SELECTED_MARKER_LAYER,
    type: "symbol",
    source: POI_SELECTED_SOURCE,
    layout: {
      "icon-image": ["get", "icon_name"],
      "icon-size": 1.08,
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
    },
  });
  addPoiLayer({
    id: POI_LABEL_LAYER,
    type: "symbol",
    source: POI_SOURCE,
    minzoom: 13,
    filter: ["all", ["!", ["has", "point_count"]], ["==", ["get", "selected"], false]],
    layout: {
      "text-field": ["get", "display_name"],
      "text-font": ["Open Sans Semibold"],
      "text-size": 11,
      "text-variable-anchor": ["top", "bottom", "left", "right"],
      "text-radial-offset": 1.6,
      "text-max-width": 13,
      "text-allow-overlap": false,
      "text-ignore-placement": false,
    },
    paint: { "text-color": "#26372f", "text-halo-color": "#fffef9", "text-halo-width": 2 },
  });
  addPoiLayer({
    id: POI_SELECTED_LABEL_LAYER,
    type: "symbol",
    source: POI_SELECTED_SOURCE,
    layout: {
      "text-field": ["get", "display_name"],
      "text-font": ["Open Sans Semibold"],
      "text-size": 12,
      "text-variable-anchor": ["top", "bottom", "left", "right"],
      "text-radial-offset": 1.7,
      "text-max-width": 14,
      "text-allow-overlap": true,
      "text-ignore-placement": true,
    },
    paint: { "text-color": "#153d2e", "text-halo-color": "#fffef9", "text-halo-width": 3 },
  });
}

function poiIcon(feature) {
  if (feature.potability === "verified") return "poi-water-verified";
  if (feature.potability === "unknown") return "poi-water-unknown";
  if (feature.potability === "non_potable") return "poi-water-nonpotable";
  if (feature.category === "viewpoint") return "poi-viewpoint";
  if (feature.category === "observation_tower") return "poi-tower";
  if (feature.category === "tourism_attraction") return "poi-attraction";
  return "poi-historic";
}

function poiCollection(features, selectedId, visitedIds = new Set()) {
  return {
    type: "FeatureCollection",
    features: features.map((feature) => ({
      type: "Feature",
      id: feature.id,
      geometry: {
        type: "Point",
        coordinates: [feature.coordinate.lon, feature.coordinate.lat],
      },
      properties: {
        poi_id: feature.id,
        display_name: feature.display_name,
        icon_name: poiIcon(feature),
        selected: feature.id === selectedId,
        visited: visitedIds.has(feature.id),
      },
    })),
  };
}

function selectedPoiCollection(features, selectedId, visitedIds) {
  const selected = features.find((feature) => feature.id === selectedId);
  return poiCollection(selected ? [selected] : [], selectedId, visitedIds);
}

function popupRow(content, label, value, prominent = false) {
  if (!value) return;
  const row = document.createElement("p");
  if (prominent) row.className = "popup-status";
  const heading = document.createElement("strong");
  heading.textContent = `${label}: `;
  row.append(heading, document.createTextNode(value));
  content.append(row);
}

function poiPopupContent(feature) {
  const content = document.createElement("div");
  content.className = "point-popup place-popup";
  const heading = document.createElement("h3");
  heading.textContent = feature.display_name;
  content.append(heading);
  popupRow(content, "Category", feature.category.replaceAll("_", " "));
  popupRow(content, "Potability", feature.potability.replaceAll("_", " "));
  popupRow(
    content,
    "Access",
    feature.access_status,
    ["private", "restricted"].includes(feature.access_status),
  );
  const tags = Object.fromEntries(feature.tags ?? []);
  popupRow(content, "Operator", tags.operator);
  popupRow(content, "Opening hours", tags.opening_hours);
  popupRow(content, "Seasonal", tags.seasonal);
  popupRow(content, "Bottle filling", tags.bottle);
  const explanation = document.createElement("p");
  explanation.className = "place-explanation";
  if (feature.potability === "verified") {
    explanation.textContent = "Mapped in OpenStreetMap as drinking water.";
  } else if (feature.potability === "unknown") {
    explanation.textContent = "Potability is not specified in the mapped data.";
  } else if (feature.potability === "non_potable") {
    explanation.textContent = "Mapped as non-potable.";
  } else {
    explanation.textContent = "Mapped place information may be incomplete or out of date.";
  }
  content.append(explanation);
  for (const warning of feature.warnings ?? []) {
    const note = document.createElement("p");
    note.className = "popup-warning";
    note.textContent = warning.replaceAll("_", " ");
    content.append(note);
  }
  popupRow(
    content,
    "Coordinates",
    `${Number(feature.coordinate.lat).toFixed(6)}, ${Number(feature.coordinate.lon).toFixed(6)}`,
  );
  popupRow(content, "OSM object", `${feature.osm_type}/${feature.osm_id}`);
  const scenic = ["viewpoint", "observation_tower", "castle", "archaeological_site", "ruins", "tourism_attraction"].includes(feature.category);
  const verifiedWater = feature.category === "drinking_water" && feature.potability === "verified";
  const eligibleAccess = ["public", "restricted"].includes(feature.access_status);
  if (eligibleAccess && (scenic || verifiedWater) && feature.potability !== "non_potable") {
    const prefer = document.createElement("button");
    prefer.type = "button";
    prefer.className = "button secondary popup-prefer";
    prefer.textContent = preferredPoiIds.has(feature.id) ? "Preferred in Auto Tour" : "Prefer in Auto Tour";
    prefer.disabled = preferredPoiIds.has(feature.id);
    prefer.addEventListener("click", () => {
      poiPreferHandler?.(feature);
      prefer.textContent = "Preferred in Auto Tour";
      prefer.disabled = true;
    });
    content.append(prefer);
  }
  return content;
}

function showPoiPopup(feature) {
  poiPopup?.remove();
  poiPopup = new window.maplibregl.Popup({ offset: 24, closeButton: true })
    .setLngLat([feature.coordinate.lon, feature.coordinate.lat])
    .setDOMContent(poiPopupContent(feature))
    .addTo(map);
}

function backendRequestedPlace(visit) {
  const place = visit?.requested_place ?? {};
  return {
    name: place.name,
    coordinate: place.coordinate,
    importance: place.importance,
    visitRadiusM: place.visit_radius_m,
    originalIndex: place.original_index,
  };
}

export function requestedPlaceFeatureCollection(places, visits = [], selectedId = null) {
  const visitsById = new Map(visits.map((visit, index) => [
    requestedPlaceIdentifier(backendRequestedPlace(visit), index),
    visit,
  ]));
  return {
    type: "FeatureCollection",
    features: places.map((place, index) => {
      const id = place.id ?? requestedPlaceIdentifier(place, index);
      const visit = visitsById.get(id);
      const status = visit ? (visit.satisfied ? "satisfied" : "missed") : "pending";
      const originalOrder = Number(place.originalIndex ?? index + 1);
      const measuredDistance = Number(visit?.measured_distance_m);
      return {
        type: "Feature",
        id,
        geometry: {
          type: "Point",
          coordinates: [place.coordinate.lon, place.coordinate.lat],
        },
        properties: {
          requested_id: id,
          original_order: originalOrder,
          name: place.name || `Requested place ${originalOrder}`,
          longitude: place.coordinate.lon,
          latitude: place.coordinate.lat,
          importance: place.importance,
          visit_radius_m: place.visitRadiusM,
          status,
          measured_distance_m: Number.isFinite(measuredDistance)
            ? measuredDistance
            : null,
          visit_reason: visit?.reason ?? null,
          selected: id === selectedId,
        },
      };
    }),
  };
}

function destinationCoordinate(longitude, latitude, distanceM, bearingRadians) {
  const earthRadiusM = 6371008.8;
  const angularDistance = distanceM / earthRadiusM;
  const latitudeRadians = latitude * Math.PI / 180;
  const longitudeRadians = longitude * Math.PI / 180;
  const destinationLatitude = Math.asin(
    Math.sin(latitudeRadians) * Math.cos(angularDistance)
      + Math.cos(latitudeRadians) * Math.sin(angularDistance) * Math.cos(bearingRadians),
  );
  const destinationLongitude = longitudeRadians + Math.atan2(
    Math.sin(bearingRadians) * Math.sin(angularDistance) * Math.cos(latitudeRadians),
    Math.cos(angularDistance) - Math.sin(latitudeRadians) * Math.sin(destinationLatitude),
  );
  return [
    destinationLongitude * 180 / Math.PI,
    destinationLatitude * 180 / Math.PI,
  ];
}

export function requestedPlaceRadiusCollection(collection, showMissed = false) {
  return {
    type: "FeatureCollection",
    features: collection.features
      .filter((feature) => feature.properties.selected
        || (showMissed && feature.properties.status === "missed"))
      .map((feature) => {
        const [longitude, latitude] = feature.geometry.coordinates;
        const coordinates = Array.from(
          { length: REQUESTED_RADIUS_SEGMENTS + 1 },
          (_value, index) => destinationCoordinate(
            longitude,
            latitude,
            feature.properties.visit_radius_m,
            2 * Math.PI * index / REQUESTED_RADIUS_SEGMENTS,
          ),
        );
        return {
          type: "Feature",
          id: feature.id,
          geometry: { type: "Polygon", coordinates: [coordinates] },
          properties: {
            requested_id: feature.id,
            status: feature.properties.status,
            visit_radius_m: feature.properties.visit_radius_m,
          },
        };
      }),
  };
}

function addRequestedRadiusLayer(layer) {
  if (!map.getLayer(layer.id)) map.addLayer(layer, firstRouteLayerId());
}

function addRequestedMarkerLayer(layer) {
  if (!map.getLayer(layer.id)) map.addLayer(layer);
}

function ensureRequestedPlaceLayers() {
  if (!ready || !map) return;
  if (!map.getSource(REQUESTED_SOURCE)) {
    map.addSource(REQUESTED_SOURCE, { type: "geojson", data: EMPTY_COLLECTION });
  }
  if (!map.getSource(REQUESTED_RADIUS_SOURCE)) {
    map.addSource(REQUESTED_RADIUS_SOURCE, {
      type: "geojson",
      data: EMPTY_COLLECTION,
    });
  }
  const statusColor = [
    "match", ["get", "status"],
    "satisfied", "#4f8c61",
    "missed", "#c94f47",
    "#fff1c7",
  ];
  addRequestedRadiusLayer({
    id: REQUESTED_RADIUS_FILL_LAYER,
    type: "fill",
    source: REQUESTED_RADIUS_SOURCE,
    paint: {
      "fill-color": statusColor,
      "fill-opacity": .13,
    },
  });
  addRequestedRadiusLayer({
    id: REQUESTED_RADIUS_LINE_LAYER,
    type: "line",
    source: REQUESTED_RADIUS_SOURCE,
    paint: {
      "line-color": statusColor,
      "line-width": 2,
      "line-opacity": .78,
      "line-dasharray": [2, 1.5],
    },
  });
  addRequestedMarkerLayer({
    id: REQUESTED_MARKER_LAYER,
    type: "circle",
    source: REQUESTED_SOURCE,
    layout: {
      "circle-sort-key": ["case", ["get", "selected"], 0, 1],
    },
    paint: {
      "circle-radius": [
        "case", ["==", ["get", "importance"], "prefer"], 9, 12,
      ],
      "circle-color": statusColor,
      "circle-stroke-color": "#25372f",
      "circle-stroke-width": 2.5,
      "circle-opacity": .98,
    },
  });
  addRequestedMarkerLayer({
    id: REQUESTED_PREFERRED_LAYER,
    type: "circle",
    source: REQUESTED_SOURCE,
    filter: ["==", ["get", "importance"], "prefer"],
    paint: {
      "circle-radius": 14,
      "circle-color": "#fffdf7",
      "circle-opacity": 0,
      "circle-stroke-color": "#25372f",
      "circle-stroke-width": 1.5,
    },
  });
  addRequestedMarkerLayer({
    id: REQUESTED_SELECTED_LAYER,
    type: "circle",
    source: REQUESTED_SOURCE,
    filter: ["==", ["get", "selected"], true],
    paint: {
      "circle-radius": 18,
      "circle-color": "#fffdf7",
      "circle-opacity": .34,
      "circle-stroke-color": "#d9582b",
      "circle-stroke-width": 3,
    },
  });
  addRequestedMarkerLayer({
    id: REQUESTED_ORDER_LAYER,
    type: "symbol",
    source: REQUESTED_SOURCE,
    layout: {
      "text-field": [
        "concat", "R", ["to-string", ["get", "original_order"]],
      ],
      "text-font": ["Open Sans Semibold"],
      "text-size": 10,
      "text-allow-overlap": true,
      "text-ignore-placement": true,
    },
    paint: {
      "text-color": [
        "match", ["get", "status"],
        "pending", "#25372f",
        "#fffef9",
      ],
      "text-halo-color": [
        "match", ["get", "status"],
        "pending", "#fff1c7",
        "rgba(0,0,0,0)",
      ],
      "text-halo-width": 1,
    },
  });
  addRequestedMarkerLayer({
    id: REQUESTED_LABEL_LAYER,
    type: "symbol",
    source: REQUESTED_SOURCE,
    minzoom: 12.5,
    layout: {
      "text-field": ["get", "name"],
      "text-font": ["Open Sans Semibold"],
      "text-size": 11,
      "text-variable-anchor": ["top", "bottom", "left", "right"],
      "text-radial-offset": 1.4,
      "text-max-width": 13,
      "text-allow-overlap": false,
      "text-ignore-placement": false,
      "text-optional": true,
    },
    paint: {
      "text-color": "#26372f",
      "text-halo-color": "#fffef9",
      "text-halo-width": 2,
    },
  });
}

function requestedPlaceStatusLabel(status) {
  if (status === "satisfied") return "Satisfied";
  if (status === "missed") return "Missed";
  return "Pending route generation";
}

function requestedVisitReason(reason) {
  const values = {
    already_on_route: "Already on the routed path",
    deliberately_routed_close_enough: "Deliberately routed close enough",
    not_reached: "The selected route did not reach this place",
    snapped_outside_visit_radius: "The routed snap remained outside the visit radius",
  };
  return values[reason] ?? null;
}

function requestedPlacePopupContent(feature) {
  const properties = feature.properties;
  const content = document.createElement("div");
  content.className = "point-popup requested-place-popup";
  const heading = document.createElement("h3");
  heading.textContent = properties.name;
  content.append(heading);
  const identity = document.createElement("p");
  identity.textContent = `Requested place ${properties.original_order} · ${properties.importance === "must_visit" ? "Must visit" : "Preferred"}`;
  content.append(identity);
  const status = document.createElement("p");
  status.className = `popup-status requested-status-${properties.status}`;
  status.textContent = requestedPlaceStatusLabel(properties.status);
  content.append(status);
  if (Number.isFinite(properties.measured_distance_m)) {
    popupRow(
      content,
      "Closest route passage",
      `${Number(properties.measured_distance_m).toFixed(1)} m`,
    );
  }
  popupRow(content, "Required radius", `${Number(properties.visit_radius_m)} m`);
  popupRow(content, "Visit result", requestedVisitReason(properties.visit_reason));
  return content;
}

function showRequestedPlacePopup(feature, reveal = false) {
  requestedPlacePopup?.remove();
  requestedPlacePopupId = feature.id;
  requestedPlacePopup = new window.maplibregl.Popup({
    offset: 22,
    closeButton: true,
    focusAfterOpen: false,
    maxWidth: "min(300px, calc(100vw - 24px))",
  })
    .setLngLat(feature.geometry.coordinates)
    .setDOMContent(requestedPlacePopupContent(feature))
    .addTo(map);
  requestedPlacePopup.on("close", () => {
    requestedPlacePopup = null;
    requestedPlacePopupId = null;
  });
  if (reveal) {
    map.easeTo({
      center: feature.geometry.coordinates,
      duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? 0
        : 350,
    });
  }
}

function moveRequestedPlaceLayersIntoOrder() {
  if (!map) return;
  const routeLayer = firstRouteLayerId();
  for (const id of [REQUESTED_RADIUS_FILL_LAYER, REQUESTED_RADIUS_LINE_LAYER]) {
    if (map.getLayer(id) && routeLayer) map.moveLayer(id, routeLayer);
  }
  for (const id of [
    REQUESTED_MARKER_LAYER,
    REQUESTED_PREFERRED_LAYER,
    REQUESTED_SELECTED_LAYER,
    REQUESTED_ORDER_LAYER,
    REQUESTED_LABEL_LAYER,
  ]) {
    if (map.getLayer(id)) map.moveLayer(id);
  }
  for (const id of [
    POI_SELECTED_LAYER,
    POI_SELECTED_MARKER_LAYER,
    POI_SELECTED_LABEL_LAYER,
  ]) {
    if (map.getLayer(id)) map.moveLayer(id);
  }
  moveRequiredLabelsToTop();
}

export function renderRequestedPlaces(
  places,
  visits,
  selectedId,
  showMissedRadii,
  onSelect,
  revealId = null,
) {
  if (!ready || !map) return;
  ensureRequestedPlaceLayers();
  const collection = requestedPlaceFeatureCollection(places, visits, selectedId);
  requestedPlaceById = new Map(collection.features.map((feature) => [
    feature.id,
    feature,
  ]));
  requestedPlaceActivateHandler = onSelect;
  map.getSource(REQUESTED_SOURCE).setData(collection);
  const radii = requestedPlaceRadiusCollection(collection, showMissedRadii);
  requestedRadiusFeatureCount = radii.features.length;
  map.getSource(REQUESTED_RADIUS_SOURCE).setData(radii);
  const selected = selectedId ? requestedPlaceById.get(selectedId) : null;
  if (!selected) {
    requestedPlacePopup?.remove();
    requestedPlacePopup = null;
    requestedPlacePopupId = null;
  } else if (requestedPlacePopup && requestedPlacePopupId === selected.id) {
    requestedPlacePopup
      .setLngLat(selected.geometry.coordinates)
      .setDOMContent(requestedPlacePopupContent(selected));
  }
  const reveal = revealId ? requestedPlaceById.get(revealId) : null;
  if (reveal) showRequestedPlacePopup(reveal, true);
  moveRequestedPlaceLayersIntoOrder();
}

export function requestedPlaceMapDiagnostics() {
  const features = [...requestedPlaceById.values()];
  const statuses = { pending: 0, satisfied: 0, missed: 0 };
  for (const feature of features) statuses[feature.properties.status] += 1;
  const requestedLayerIds = [
    REQUESTED_RADIUS_FILL_LAYER,
    REQUESTED_RADIUS_LINE_LAYER,
    REQUESTED_MARKER_LAYER,
    REQUESTED_PREFERRED_LAYER,
    REQUESTED_SELECTED_LAYER,
    REQUESTED_ORDER_LAYER,
    REQUESTED_LABEL_LAYER,
  ];
  const styleLayerIds = (map?.getStyle()?.layers ?? []).map((layer) => layer.id);
  const visible = ready && map?.getLayer(REQUESTED_MARKER_LAYER)
    ? map.queryRenderedFeatures(undefined, { layers: [REQUESTED_MARKER_LAYER] })
    : [];
  return {
    sourceExists: Boolean(map?.getSource(REQUESTED_SOURCE)),
    radiusSourceExists: Boolean(map?.getSource(REQUESTED_RADIUS_SOURCE)),
    featureCount: features.length,
    visibleFeatureCount: new Set(
      visible.map((feature) => feature.properties?.requested_id),
    ).size,
    radiusFeatureCount: requestedRadiusFeatureCount,
    statuses,
    duplicateLayerCount: requestedLayerIds.reduce(
      (count, id) => count + Math.max(
        0,
        styleLayerIds.filter((layerId) => layerId === id).length - 1,
      ),
      0,
    ),
  };
}

export function renderPois(features, selectedId, onSelect, options = {}) {
  if (!ready || !map) return;
  ensurePoiLayers();
  poiById = new Map(features.map((feature) => [feature.id, feature]));
  poiActivateHandler = onSelect;
  poiPreferHandler = options.onPrefer ?? null;
  preferredPoiIds = new Set(options.preferredIds ?? []);
  const visitedIds = new Set(options.visitedIds ?? []);
  map.getSource(POI_SOURCE).setData(
    poiCollection(features.filter((feature) => feature.id !== selectedId), null, visitedIds),
  );
  map.getSource(POI_SELECTED_SOURCE).setData(selectedPoiCollection(features, selectedId, visitedIds));
  if (selectedId === null || !poiById.has(selectedId)) {
    poiPopup?.remove();
    poiPopup = null;
  }
  moveRequiredLabelsToTop();
}

export function currentViewportBounds() {
  if (!map) return null;
  const bounds = map.getBounds();
  return {
    west: bounds.getWest(),
    south: bounds.getSouth(),
    east: bounds.getEast(),
    north: bounds.getNorth(),
  };
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
