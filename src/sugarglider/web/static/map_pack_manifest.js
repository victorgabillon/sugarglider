export const MAP_PACK_SCHEMA_VERSION = 1;
export const MAP_PACK_ARCHIVE_FILENAME = "basemap.pmtiles";
export const MAXIMUM_MAP_PACK_BYTES = 2_147_483_648;
export const MAXIMUM_MAP_PACK_MANIFEST_BYTES = 16 * 1024;

const MANIFEST_FIELDS = Object.freeze([
  "archive_filename",
  "attribution",
  "bounds",
  "build_id",
  "byte_size",
  "data_source",
  "display_name",
  "format",
  "max_zoom",
  "min_zoom",
  "pack_id",
  "schema_version",
  "tile_type",
]);
const PACK_ID_PATTERN = /^[a-z0-9][a-z0-9._-]{0,63}$/;
const BUILD_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const MAXIMUM_MERCATOR_LATITUDE = 85.051129;

export class MapPackManifestError extends Error {
  constructor(message) {
    super(message);
    this.name = "MapPackManifestError";
    this.code = "map_pack_invalid";
  }
}

export function parseMapPackManifestJson(text) {
  if (typeof text !== "string" || new TextEncoder().encode(text).byteLength > MAXIMUM_MAP_PACK_MANIFEST_BYTES) {
    throw new MapPackManifestError("Map-pack manifest exceeds its size limit.");
  }
  let value;
  try {
    value = JSON.parse(text);
  } catch {
    throw new MapPackManifestError("Map-pack manifest is not valid JSON.");
  }
  return parseMapPackManifest(value);
}

export function parseMapPackManifest(value) {
  if (!isPlainObject(value)) {
    throw new MapPackManifestError("Map-pack manifest must be an object.");
  }
  const fields = Object.keys(value).sort();
  if (!sameStrings(fields, MANIFEST_FIELDS)) {
    throw new MapPackManifestError("Map-pack manifest fields do not match schema v1.");
  }
  if (value.schema_version !== MAP_PACK_SCHEMA_VERSION) {
    throw new MapPackManifestError("Unsupported map-pack manifest schema.");
  }
  const packId = requiredSafeString(value.pack_id, "pack_id", 64);
  if (!PACK_ID_PATTERN.test(packId) || packId.includes("..")) {
    throw new MapPackManifestError("Map-pack ID is unsafe.");
  }
  const displayName = requiredText(value.display_name, "display_name", 120);
  const bounds = validateBounds(value.bounds);
  const minZoom = requiredInteger(value.min_zoom, "min_zoom", 0, 22);
  const maxZoom = requiredInteger(value.max_zoom, "max_zoom", 0, 22);
  if (minZoom > maxZoom) {
    throw new MapPackManifestError("Map-pack zoom range is invalid.");
  }
  if (value.format !== "pmtiles-v3" || value.tile_type !== "mvt") {
    throw new MapPackManifestError("Map pack must contain PMTiles v3 vector tiles.");
  }
  if (value.archive_filename !== MAP_PACK_ARCHIVE_FILENAME) {
    throw new MapPackManifestError("Map-pack archive filename is invalid.");
  }
  const byteSize = requiredInteger(
    value.byte_size,
    "byte_size",
    1,
    MAXIMUM_MAP_PACK_BYTES,
  );
  const attribution = requiredText(value.attribution, "attribution", 2048);
  const dataSource = requiredText(value.data_source, "data_source", 240);
  const buildId = requiredSafeString(value.build_id, "build_id", 128);
  if (!BUILD_ID_PATTERN.test(buildId) || buildId.includes("..")) {
    throw new MapPackManifestError("Map-pack build ID is unsafe.");
  }
  return Object.freeze({
    schema_version: MAP_PACK_SCHEMA_VERSION,
    pack_id: packId,
    display_name: displayName,
    bounds: Object.freeze(bounds),
    min_zoom: minZoom,
    max_zoom: maxZoom,
    format: "pmtiles-v3",
    tile_type: "mvt",
    archive_filename: MAP_PACK_ARCHIVE_FILENAME,
    byte_size: byteSize,
    attribution,
    data_source: dataSource,
    build_id: buildId,
  });
}

export function serializeMapPackManifest(manifest) {
  return `${JSON.stringify(parseMapPackManifest(manifest), null, 2)}\n`;
}

export function mapPackCoversCoordinate(manifest, coordinate) {
  const [lon, lat] = validCoordinate(coordinate);
  const [west, south, east, north] = manifest.bounds;
  return lon >= west && lon <= east && lat >= south && lat <= north;
}

export function selectMapPackForCoordinate(manifests, coordinate) {
  validCoordinate(coordinate);
  const covering = manifests.filter((manifest) => (
    mapPackCoversCoordinate(manifest, coordinate)
  ));
  covering.sort((left, right) => {
    const areaDifference = boundsArea(left.bounds) - boundsArea(right.bounds);
    return areaDifference || compareAscii(left.pack_id, right.pack_id);
  });
  return covering[0] ?? null;
}

function validateBounds(value) {
  if (!Array.isArray(value) || value.length !== 4) {
    throw new MapPackManifestError("Map-pack bounds must have four numbers.");
  }
  const [west, south, east, north] = value;
  if (
    !finiteInRange(west, -180, 180)
    || !finiteInRange(east, -180, 180)
    || !finiteInRange(south, -MAXIMUM_MERCATOR_LATITUDE, MAXIMUM_MERCATOR_LATITUDE)
    || !finiteInRange(north, -MAXIMUM_MERCATOR_LATITUDE, MAXIMUM_MERCATOR_LATITUDE)
    || west >= east
    || south >= north
  ) {
    throw new MapPackManifestError("Map-pack geographic bounds are invalid.");
  }
  return [west, south, east, north];
}

function validCoordinate(value) {
  const lon = value?.lon;
  const lat = value?.lat;
  if (!finiteInRange(lon, -180, 180) || !finiteInRange(lat, -90, 90)) {
    throw new MapPackManifestError("Map-pack selection coordinate is invalid.");
  }
  return [lon, lat];
}

function requiredText(value, field, maximumLength) {
  const text = requiredSafeString(value, field, maximumLength);
  if (/[\u0000-\u001f\u007f]/u.test(text)) {
    throw new MapPackManifestError(`Map-pack ${field} contains control characters.`);
  }
  return text;
}

function requiredSafeString(value, field, maximumLength) {
  if (typeof value !== "string" || value.trim() !== value || value.length < 1 || value.length > maximumLength) {
    throw new MapPackManifestError(`Map-pack ${field} is invalid.`);
  }
  return value;
}

function requiredInteger(value, field, minimum, maximum) {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new MapPackManifestError(`Map-pack ${field} is invalid.`);
  }
  return value;
}

function finiteInRange(value, minimum, maximum) {
  return typeof value === "number"
    && Number.isFinite(value)
    && value >= minimum
    && value <= maximum;
}

function boundsArea(bounds) {
  return (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]);
}

function compareAscii(left, right) {
  if (left < right) return -1;
  if (left > right) return 1;
  return 0;
}

function sameStrings(left, right) {
  return left.length === right.length
    && left.every((value, index) => value === right[index]);
}

function isPlainObject(value) {
  return value !== null
    && typeof value === "object"
    && !Array.isArray(value)
    && Object.getPrototypeOf(value) === Object.prototype;
}
