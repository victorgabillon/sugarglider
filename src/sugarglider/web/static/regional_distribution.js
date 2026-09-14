import { validateMapPackInstallUrl } from "./map_pack_store.js";
import { REGIONAL_MANIFEST_MAX_BYTES, RegionalDataError, parseRegionalManifest, requireData } from "./regional_manifest.js";

export function regionalDistributionUrl(value, pageLocation = globalThis.location) {
  try {
    requireData(typeof value === "string" && value.length <= 2_048 && value === value.trim(), "invalid_regional_source");
    const url = validateMapPackInstallUrl(value, pageLocation);
    requireData(url.href === value && url.pathname.endsWith("/manifest.json")
      && url.pathname.slice(1).split("/").every((part) => /^[A-Za-z0-9._~-]+$/.test(part)
        && part !== "." && !part.includes("..")), "invalid_regional_source");
    return url;
  } catch { throw new RegionalDataError("invalid_regional_source"); }
}

export async function fetchRegionalManifest(value, {
  signal, pageLocation = globalThis.location, fetchResource = (...args) => globalThis.fetch(...args),
} = {}) {
  const url = regionalDistributionUrl(value, pageLocation);
  signal?.throwIfAborted();
  const timeout = AbortSignal.timeout(30_000);
  const bounded = signal ? AbortSignal.any([signal, timeout]) : timeout;
  try {
    const response = await fetchResource(url.href, { method: "GET", signal: bounded, cache: "no-store",
      redirect: "error", credentials: "omit", referrerPolicy: "no-referrer" });
    requireData(response.status === 200 && !response.redirected && (!response.url || response.url === url.href), "regional_download_failed");
    const text = await readRegionalText(response, REGIONAL_MANIFEST_MAX_BYTES, bounded);
    bounded.throwIfAborted();
    return await parseRegionalManifest(text);
  } catch (error) {
    if (signal?.aborted) throw new DOMException("Cancelled", "AbortError");
    if (error instanceof RegionalDataError) throw error;
    throw new RegionalDataError(timeout.aborted ? "regional_transfer_timeout" : "regional_download_failed");
  }
}

export async function readRegionalText(response, maximum, signal) {
  const reader = response.body?.getReader();
  requireData(reader, "regional_download_failed");
  try {
    const decoder = new TextDecoder("utf-8", { fatal: true });
    let text = "", total = 0;
    while (true) {
      signal?.throwIfAborted();
      const { done, value: bytes } = await reader.read();
      if (done) break;
      total += bytes.byteLength;
      requireData(total <= maximum, "invalid_regional_manifest");
      text += decoder.decode(bytes, { stream: true });
    }
    signal?.throwIfAborted();
    return text + decoder.decode();
  } catch (error) { await reader.cancel().catch(() => {}); throw error; }
  finally { reader.releaseLock(); }
}

export function regionalDownloadBytes(manifest) {
  return Object.values(manifest.components).flatMap((component) => component.files)
    .reduce((sum, file) => sum + file.byte_size, 0);
}
