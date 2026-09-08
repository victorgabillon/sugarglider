import {
  MAP_PACK_ARCHIVE_FILENAME,
  MAXIMUM_MAP_PACK_MANIFEST_BYTES,
  parseMapPackManifestJson,
  selectMapPackForCoordinate,
  serializeMapPackManifest,
} from "./map_pack_manifest.js";
import {
  OpfsPmtilesSource,
  validateOpfsPmtilesArchive,
} from "./opfs_pmtiles_source.js";

export const MAP_PACK_DIRECTORY = "sugarglider-map-packs";
const CAPABILITY_PROBE_PREFIX = ".opfs-capability-probe-";

export class MapPackStoreError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "MapPackStoreError";
    this.code = code;
  }
}

export async function probeOpfsMapPackStorage({
  storageManager = globalThis.navigator?.storage,
  probeSuffix = "shared",
} = {}) {
  if (!storageManager || typeof storageManager.getDirectory !== "function") {
    return capabilityFailure("navigator.storage.getDirectory is unavailable");
  }
  let packRoot = null;
  const probeName = `${CAPABILITY_PROBE_PREFIX}${probeSuffix}`;
  let probeCreated = false;
  try {
    const originRoot = await storageManager.getDirectory();
    if (!originRoot || typeof originRoot.getDirectoryHandle !== "function") {
      return capabilityFailure("OPFS directory handles are unavailable");
    }
    packRoot = await originRoot.getDirectoryHandle(MAP_PACK_DIRECTORY, { create: true });
    const fileHandle = await packRoot.getFileHandle(probeName, { create: true });
    probeCreated = true;
    const writable = await fileHandle.createWritable();
    await writable.write(new Uint8Array([17, 29, 41, 53, 67]));
    await writable.close();
    const file = await fileHandle.getFile();
    const range = new Uint8Array(await file.slice(1, 4).arrayBuffer());
    if (range.length !== 3 || range[0] !== 29 || range[1] !== 41 || range[2] !== 53) {
      return capabilityFailure("OPFS byte-range read did not preserve written bytes");
    }
    await packRoot.removeEntry(probeName);
    probeCreated = false;
    const persisted = typeof storageManager.persisted === "function"
      ? await optionalBoolean(() => storageManager.persisted())
      : null;
    return Object.freeze({
      opfs_supported: true,
      random_access: true,
      state: "map_pack_storage_available",
      persisted,
      reason: null,
    });
  } catch (error) {
    return capabilityFailure(safeErrorMessage(error));
  } finally {
    if (probeCreated && packRoot) {
      try {
        await packRoot.removeEntry(probeName);
      } catch {
        // A failed best-effort cleanup is reflected by the failed capability probe.
      }
    }
  }
}

export class MapPackStore {
  constructor({
    storageManager = globalThis.navigator?.storage,
    fetchRequest = globalThis.fetch?.bind(globalThis),
    pageLocation = globalThis.location,
    probeSuffix = "runtime",
    sourceFactory = (options) => new OpfsPmtilesSource(options),
    archiveValidator = validateOpfsPmtilesArchive,
  } = {}) {
    this.storageManager = storageManager;
    this.fetchRequest = fetchRequest;
    this.pageLocation = pageLocation;
    this.probeSuffix = probeSuffix;
    this.sourceFactory = sourceFactory;
    this.archiveValidator = archiveValidator;
    this.capabilityPromise = null;
    this.activeInstalls = new Map();
    this.installGenerations = new Map();
  }

  capabilities() {
    if (!this.capabilityPromise) {
      this.capabilityPromise = probeOpfsMapPackStorage({
        storageManager: this.storageManager,
        probeSuffix: this.probeSuffix,
      });
    }
    return this.capabilityPromise;
  }

  async listInstalledPacks() {
    const scan = await this.scanInstalledPacks();
    return scan.packs;
  }

  async scanInstalledPacks() {
    const root = await this.mapPackRoot();
    const names = [];
    for await (const [name, handle] of root.entries()) {
      if (handle.kind === "directory" && safePackDirectoryName(name)) names.push(name);
    }
    names.sort();
    const packs = [];
    const partial_pack_ids = [];
    const invalid_pack_ids = [];
    for (const packId of names) {
      const directory = await root.getDirectoryHandle(packId);
      try {
        const record = await this.readPackDirectory(directory, packId);
        packs.push(record.manifest);
      } catch (error) {
        if (error?.code === "map_pack_partial") partial_pack_ids.push(packId);
        else invalid_pack_ids.push(packId);
      }
    }
    return Object.freeze({
      packs: Object.freeze(packs),
      partial_pack_ids: Object.freeze(partial_pack_ids),
      invalid_pack_ids: Object.freeze(invalid_pack_ids),
    });
  }

  async getPack(packId) {
    requireSafePackId(packId);
    const root = await this.mapPackRoot();
    let directory;
    try {
      directory = await root.getDirectoryHandle(packId);
    } catch (error) {
      if (isNotFound(error)) {
        throw new MapPackStoreError("map_pack_not_found", "Map pack is not installed.");
      }
      throw error;
    }
    return this.readPackDirectory(directory, packId);
  }

  async selectPackForCoordinate(coordinate) {
    return selectMapPackForCoordinate(await this.listInstalledPacks(), coordinate);
  }

  async openPackSource(packId) {
    const record = await this.getPack(packId);
    const source = this.sourceFactory({
      fileHandle: record.archiveHandle,
      key: `sugarglider-map-pack/${record.manifest.pack_id}/${record.manifest.build_id}`,
      expectedSize: record.manifest.byte_size,
    });
    const validated = await this.archiveValidator({
      source,
      manifest: record.manifest,
    });
    return Object.freeze({
      manifest: record.manifest,
      source,
      archive: validated.archive,
      header: validated.header,
      metadata: validated.metadata,
    });
  }

  async installPack(manifestUrl, { signal, onProgress } = {}) {
    if (typeof this.fetchRequest !== "function") {
      throw new MapPackStoreError("map_pack_install_failed", "Pack download is unavailable.");
    }
    const safeManifestUrl = validateMapPackInstallUrl(manifestUrl, this.pageLocation);
    const manifestResponse = await this.fetchRequest(safeManifestUrl.href, fetchOptions(signal));
    validateFetchResponse(manifestResponse, safeManifestUrl, "manifest");
    const manifestText = await readBoundedResponseText(
      manifestResponse,
      MAXIMUM_MAP_PACK_MANIFEST_BYTES,
      signal,
    );
    const manifest = parseMapPackManifestJson(manifestText);
    if (this.activeInstalls.has(manifest.pack_id)) {
      throw new MapPackStoreError(
        "map_pack_install_in_progress",
        "This map pack is already being installed.",
      );
    }
    const generation = (this.installGenerations.get(manifest.pack_id) ?? 0) + 1;
    this.installGenerations.set(manifest.pack_id, generation);
    const controller = new AbortController();
    const unlinkSignal = forwardAbort(signal, controller);
    const operation = {
      controller,
      generation,
      promise: null,
    };
    operation.promise = this.finishInstall({
      manifest,
      manifestUrl: safeManifestUrl,
      operation,
      onProgress,
    });
    this.activeInstalls.set(manifest.pack_id, operation);
    try {
      return await operation.promise;
    } finally {
      unlinkSignal();
      if (this.activeInstalls.get(manifest.pack_id) === operation) {
        this.activeInstalls.delete(manifest.pack_id);
      }
    }
  }

  async removePack(packId) {
    requireSafePackId(packId);
    const generation = (this.installGenerations.get(packId) ?? 0) + 1;
    this.installGenerations.set(packId, generation);
    const active = this.activeInstalls.get(packId);
    if (active) {
      active.controller.abort();
      try {
        await active.promise;
      } catch {
        // The removal owns cleanup after the cancelled install settles.
      }
    }
    const root = await this.mapPackRoot();
    try {
      await root.removeEntry(packId, { recursive: true });
    } catch (error) {
      if (!isNotFound(error)) throw error;
    }
  }

  cancelActiveInstalls() {
    for (const operation of this.activeInstalls.values()) operation.controller.abort();
  }

  async requestPersistence() {
    if (typeof this.storageManager?.persist !== "function") return null;
    return optionalBoolean(() => this.storageManager.persist());
  }

  async finishInstall({ manifest, manifestUrl, operation, onProgress }) {
    const root = await this.mapPackRoot();
    let ownsDirectory = false;
    let writable = null;
    try {
      const existing = await optionalDirectory(root, manifest.pack_id);
      if (existing) {
        const completion = await optionalFile(existing, "manifest.json");
        if (completion) {
          throw new MapPackStoreError(
            "map_pack_already_installed",
            "Remove the installed map pack before replacing it.",
          );
        }
        await root.removeEntry(manifest.pack_id, { recursive: true });
      }
      this.requireCurrentInstall(manifest.pack_id, operation);
      const directory = await root.getDirectoryHandle(manifest.pack_id, { create: true });
      ownsDirectory = true;
      const archiveHandle = await directory.getFileHandle(MAP_PACK_ARCHIVE_FILENAME, {
        create: true,
      });
      writable = await archiveHandle.createWritable();
      const archiveUrl = new URL(MAP_PACK_ARCHIVE_FILENAME, manifestUrl);
      if (archiveUrl.origin !== manifestUrl.origin) {
        throw new MapPackStoreError("map_pack_install_failed", "Archive URL changed origin.");
      }
      const response = await this.fetchRequest(
        archiveUrl.href,
        fetchOptions(operation.controller.signal),
      );
      validateFetchResponse(response, archiveUrl, "archive");
      validateArchiveHeaders(response, manifest.byte_size);
      const bytesWritten = await streamArchive({
        response,
        writable,
        maximumBytes: manifest.byte_size,
        signal: operation.controller.signal,
        onProgress,
      });
      writable = null;
      if (bytesWritten !== manifest.byte_size) {
        throw new MapPackStoreError(
          "map_pack_install_failed",
          "Downloaded archive size differs from its manifest.",
        );
      }
      this.requireCurrentInstall(manifest.pack_id, operation);
      const source = this.sourceFactory({
        fileHandle: archiveHandle,
        key: `sugarglider-map-pack/${manifest.pack_id}/${manifest.build_id}`,
        expectedSize: manifest.byte_size,
      });
      await this.archiveValidator({ source, manifest });
      this.requireCurrentInstall(manifest.pack_id, operation);
      const manifestHandle = await directory.getFileHandle("manifest.json", { create: true });
      const manifestWriter = await manifestHandle.createWritable();
      await manifestWriter.write(serializeMapPackManifest(manifest));
      await manifestWriter.close();
      this.requireCurrentInstall(manifest.pack_id, operation);
      return manifest;
    } catch (error) {
      if (writable) {
        try {
          await writable.abort();
        } catch {
          // Directory cleanup below remains authoritative.
        }
      }
      if (ownsDirectory) {
        try {
          await root.removeEntry(manifest.pack_id, { recursive: true });
        } catch {
          // A remnant has no manifest and is ignored as a partial install.
        }
      }
      if (operation.controller.signal.aborted || error?.name === "AbortError") {
        throw new MapPackStoreError("map_pack_download_cancelled", "Map-pack installation was cancelled.");
      }
      if (error instanceof MapPackStoreError || error?.code === "map_pack_invalid") throw error;
      throw new MapPackStoreError(
        "map_pack_install_failed",
        `Map-pack installation failed: ${safeErrorMessage(error)}`,
      );
    }
  }

  requireCurrentInstall(packId, operation) {
    if (
      operation.controller.signal.aborted
      || this.installGenerations.get(packId) !== operation.generation
    ) {
      throw new DOMException("The operation was aborted.", "AbortError");
    }
  }

  async readPackDirectory(directory, expectedPackId) {
    const manifestHandle = await optionalFile(directory, "manifest.json");
    if (!manifestHandle) {
      throw new MapPackStoreError("map_pack_partial", "Map-pack installation is incomplete.");
    }
    let manifest;
    try {
      const manifestFile = await manifestHandle.getFile();
      if (manifestFile.size > MAXIMUM_MAP_PACK_MANIFEST_BYTES) {
        throw new Error("manifest too large");
      }
      manifest = parseMapPackManifestJson(await manifestFile.text());
      if (manifest.pack_id !== expectedPackId) throw new Error("pack ID mismatch");
      const archiveHandle = await directory.getFileHandle(MAP_PACK_ARCHIVE_FILENAME);
      const archiveFile = await archiveHandle.getFile();
      if (archiveFile.size !== manifest.byte_size) throw new Error("archive size mismatch");
      return Object.freeze({ manifest, archiveHandle });
    } catch (error) {
      if (error instanceof MapPackStoreError) throw error;
      throw new MapPackStoreError(
        "map_pack_invalid",
        `Installed map pack is invalid: ${safeErrorMessage(error)}`,
      );
    }
  }

  async mapPackRoot() {
    const capability = await this.capabilities();
    if (!capability.opfs_supported) {
      throw new MapPackStoreError(
        "map_pack_storage_unavailable",
        capability.reason ?? "OPFS is unavailable.",
      );
    }
    const originRoot = await this.storageManager.getDirectory();
    return originRoot.getDirectoryHandle(MAP_PACK_DIRECTORY, { create: true });
  }
}

export function createMapPackStore(options) {
  return new MapPackStore(options);
}

export function validateMapPackInstallUrl(value, pageLocation = globalThis.location) {
  let url;
  let pageUrl;
  try {
    url = new URL(value);
    pageUrl = pageLocation ? new URL(pageLocation.href) : null;
  } catch {
    throw new MapPackStoreError("map_pack_install_failed", "Map-pack manifest URL is invalid.");
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new MapPackStoreError(
      "map_pack_install_failed",
      "Map-pack URLs may not contain credentials, query parameters, or fragments.",
    );
  }
  const secure = url.protocol === "https:";
  const developmentHttp = url.protocol === "http:"
    && pageUrl?.protocol === "http:"
    && developmentHost(url.hostname)
    && developmentHost(pageUrl.hostname);
  if (!secure && !developmentHttp) {
    throw new MapPackStoreError(
      "map_pack_install_failed",
      "Map packs require HTTPS except on localhost or a private-LAN debug origin.",
    );
  }
  return url;
}

async function streamArchive({ response, writable, maximumBytes, signal, onProgress }) {
  const reader = response.body?.getReader?.();
  if (!reader) {
    throw new MapPackStoreError(
      "map_pack_install_failed",
      "Streaming downloads are unavailable in this browser.",
    );
  }
  let bytesWritten = 0;
  while (true) {
    signal?.throwIfAborted?.();
    const { done, value } = await reader.read();
    if (done) break;
    if (!(value instanceof Uint8Array) || bytesWritten + value.byteLength > maximumBytes) {
      await reader.cancel();
      throw new MapPackStoreError("map_pack_install_failed", "Map-pack archive exceeds its declared size.");
    }
    await writable.write(value);
    bytesWritten += value.byteLength;
    onProgress?.(Object.freeze({ bytes_written: bytesWritten, byte_size: maximumBytes }));
  }
  await writable.close();
  return bytesWritten;
}

async function readBoundedResponseText(response, maximumBytes, signal) {
  const reader = response.body?.getReader?.();
  if (!reader) {
    throw new MapPackStoreError("map_pack_install_failed", "Streaming manifest reads are unavailable.");
  }
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let bytesRead = 0;
  let text = "";
  while (true) {
    signal?.throwIfAborted?.();
    const { done, value } = await reader.read();
    if (done) break;
    bytesRead += value.byteLength;
    if (bytesRead > maximumBytes) {
      await reader.cancel();
      throw new MapPackStoreError("map_pack_install_failed", "Map-pack manifest exceeds its size limit.");
    }
    text += decoder.decode(value, { stream: true });
  }
  return text + decoder.decode();
}

function validateFetchResponse(response, expectedUrl, kind) {
  if (!response?.ok) {
    throw new MapPackStoreError("map_pack_install_failed", `Map-pack ${kind} download failed.`);
  }
  if (response.url) {
    const finalUrl = validateMapPackInstallUrl(response.url, { href: expectedUrl.href });
    if (finalUrl.href !== expectedUrl.href) {
      throw new MapPackStoreError("map_pack_install_failed", `Map-pack ${kind} redirected unexpectedly.`);
    }
  }
}

function validateArchiveHeaders(response, expectedBytes) {
  const encoding = response.headers?.get?.("Content-Encoding");
  if (encoding && encoding.toLowerCase() !== "identity") {
    throw new MapPackStoreError("map_pack_install_failed", "PMTiles archive must not use content encoding.");
  }
  const length = response.headers?.get?.("Content-Length");
  if (length !== null && length !== undefined && length !== "") {
    if (!/^\d+$/u.test(length) || Number(length) !== expectedBytes) {
      throw new MapPackStoreError("map_pack_install_failed", "Archive Content-Length differs from its manifest.");
    }
  }
}

function fetchOptions(signal) {
  return {
    method: "GET",
    credentials: "omit",
    redirect: "error",
    cache: "no-store",
    referrerPolicy: "no-referrer",
    signal,
  };
}

function forwardAbort(signal, controller) {
  if (!signal) return () => {};
  if (signal.aborted) controller.abort();
  const abort = () => controller.abort();
  signal.addEventListener("abort", abort, { once: true });
  return () => signal.removeEventListener("abort", abort);
}

async function optionalDirectory(root, name) {
  try {
    return await root.getDirectoryHandle(name);
  } catch (error) {
    if (isNotFound(error)) return null;
    throw error;
  }
}

async function optionalFile(directory, name) {
  try {
    return await directory.getFileHandle(name);
  } catch (error) {
    if (isNotFound(error)) return null;
    throw error;
  }
}

function isNotFound(error) {
  return error?.name === "NotFoundError";
}

function safePackDirectoryName(value) {
  return typeof value === "string"
    && /^[a-z0-9][a-z0-9._-]{0,63}$/u.test(value)
    && !value.includes("..");
}

function requireSafePackId(packId) {
  if (!safePackDirectoryName(packId)) {
    throw new MapPackStoreError("map_pack_invalid", "Map-pack ID is unsafe.");
  }
}

function developmentHost(hostname) {
  const host = hostname.toLowerCase().replace(/^\[|\]$/gu, "").replace(/\.$/u, "");
  if (host === "localhost" || host === "127.0.0.1" || host === "::1") return true;
  const octets = host.split(".").map((part) => Number(part));
  if (octets.length !== 4 || octets.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) return false;
  return octets[0] === 10
    || (octets[0] === 192 && octets[1] === 168)
    || (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31)
    || (octets[0] === 169 && octets[1] === 254);
}

function capabilityFailure(reason) {
  return Object.freeze({
    opfs_supported: false,
    random_access: false,
    state: "map_pack_storage_unavailable",
    persisted: null,
    reason,
  });
}

async function optionalBoolean(action) {
  try {
    const value = await action();
    return typeof value === "boolean" ? value : null;
  } catch {
    return null;
  }
}

function safeErrorMessage(error) {
  return typeof error?.message === "string" && error.message.length <= 240
    ? error.message
    : "storage or download error";
}
