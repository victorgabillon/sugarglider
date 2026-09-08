export const MAXIMUM_PM_TILES_RANGE_BYTES = 32 * 1024 * 1024;

const REQUIRED_VECTOR_LAYERS = Object.freeze([
  "buildings",
  "earth",
  "landcover",
  "landuse",
  "roads",
  "water",
]);
const HEADER_RANGES = Object.freeze([
  ["rootDirectoryOffset", "rootDirectoryLength"],
  ["jsonMetadataOffset", "jsonMetadataLength"],
  ["leafDirectoryOffset", "leafDirectoryLength"],
  ["tileDataOffset", "tileDataLength"],
]);

export class OpfsPmtilesSourceError extends Error {
  constructor(message, code = "map_pack_invalid") {
    super(message);
    this.name = "OpfsPmtilesSourceError";
    this.code = code;
  }
}

export class OpfsPmtilesSource {
  constructor({ fileHandle, key, expectedSize }) {
    if (!fileHandle || typeof fileHandle.getFile !== "function") {
      throw new OpfsPmtilesSourceError("Map-pack archive handle is unavailable.");
    }
    if (typeof key !== "string" || !key.startsWith("sugarglider-map-pack/")) {
      throw new OpfsPmtilesSourceError("Map-pack source key is invalid.");
    }
    if (!Number.isSafeInteger(expectedSize) || expectedSize < 1) {
      throw new OpfsPmtilesSourceError("Map-pack source size is invalid.");
    }
    this.fileHandle = fileHandle;
    this.key = key;
    this.expectedSize = expectedSize;
    this.readCount = 0;
    this.bytesRead = 0;
  }

  getKey() {
    return this.key;
  }

  async getBytes(offset, length, signal) {
    throwIfAborted(signal);
    if (
      !Number.isSafeInteger(offset)
      || !Number.isSafeInteger(length)
      || offset < 0
      || length < 1
      || length > MAXIMUM_PM_TILES_RANGE_BYTES
    ) {
      throw new OpfsPmtilesSourceError("PMTiles byte range is invalid.");
    }
    const file = await this.fileHandle.getFile();
    throwIfAborted(signal);
    if (file.size !== this.expectedSize) {
      throw new OpfsPmtilesSourceError("Map-pack archive size changed after installation.");
    }
    if (offset >= file.size) {
      throw new OpfsPmtilesSourceError("PMTiles byte range starts beyond EOF.");
    }
    const end = Math.min(file.size, offset + length);
    const data = await file.slice(offset, end).arrayBuffer();
    throwIfAborted(signal);
    if (data.byteLength !== end - offset) {
      throw new OpfsPmtilesSourceError("PMTiles byte range could not be read exactly.");
    }
    this.readCount += 1;
    this.bytesRead += data.byteLength;
    return { data };
  }

  diagnostics() {
    return Object.freeze({
      read_count: this.readCount,
      bytes_read: this.bytesRead,
    });
  }
}

export async function validateOpfsPmtilesArchive({
  source,
  manifest,
  createPmtiles = createPmtilesArchive,
}) {
  const archive = createPmtiles(source);
  let header;
  let metadata;
  try {
    header = await archive.getHeader();
    validateHeader(header, manifest, source.expectedSize);
    metadata = await archive.getMetadata();
    validateMetadata(metadata);
  } catch (error) {
    if (error instanceof OpfsPmtilesSourceError) throw error;
    throw new OpfsPmtilesSourceError(
      `Map-pack archive validation failed: ${safeErrorMessage(error)}`,
    );
  }
  return Object.freeze({ archive, header, metadata });
}

function validateHeader(header, manifest, byteSize) {
  if (header?.specVersion !== 3 || header?.tileType !== 1) {
    throw new OpfsPmtilesSourceError("Archive is not PMTiles v3 MVT data.");
  }
  if (header.minZoom !== manifest.min_zoom || header.maxZoom !== manifest.max_zoom) {
    throw new OpfsPmtilesSourceError("Archive zoom range differs from its manifest.");
  }
  const headerBounds = [header.minLon, header.minLat, header.maxLon, header.maxLat];
  if (!headerBounds.every((value, index) => (
    Number.isFinite(value) && Math.abs(value - manifest.bounds[index]) <= 0.000001
  ))) {
    throw new OpfsPmtilesSourceError("Archive bounds differ from its manifest.");
  }
  for (const [offsetName, lengthName] of HEADER_RANGES) {
    const offset = header[offsetName];
    const length = header[lengthName];
    if (
      !Number.isSafeInteger(offset)
      || !Number.isSafeInteger(length)
      || offset < 0
      || length < 0
      || offset + length > byteSize
    ) {
      throw new OpfsPmtilesSourceError("Archive header contains an invalid byte range.");
    }
  }
  if (header.rootDirectoryLength < 1 || header.jsonMetadataLength < 2) {
    throw new OpfsPmtilesSourceError("Archive header is missing required directories or metadata.");
  }
}

function createPmtilesArchive(source) {
  const Pmtiles = globalThis.pmtiles?.PMTiles;
  if (typeof Pmtiles !== "function") {
    throw new OpfsPmtilesSourceError("The packaged PMTiles runtime is unavailable.");
  }
  return new Pmtiles(source);
}

function validateMetadata(metadata) {
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) {
    throw new OpfsPmtilesSourceError("Archive metadata is invalid.");
  }
  const layers = metadata.vector_layers;
  if (!Array.isArray(layers)) {
    throw new OpfsPmtilesSourceError("Archive does not describe vector layers.");
  }
  const layerIds = new Set(layers.map((layer) => layer?.id));
  if (!REQUIRED_VECTOR_LAYERS.every((layerId) => layerIds.has(layerId))) {
    throw new OpfsPmtilesSourceError("Archive does not use the required open basemap schema.");
  }
}

function throwIfAborted(signal) {
  if (!signal?.aborted) return;
  if (typeof signal.throwIfAborted === "function") signal.throwIfAborted();
  throw new DOMException("The operation was aborted.", "AbortError");
}

function safeErrorMessage(error) {
  return typeof error?.message === "string" && error.message.length <= 240
    ? error.message
    : "invalid archive";
}
