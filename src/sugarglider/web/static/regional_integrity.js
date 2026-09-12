import { sha256 } from "./vendor/noble-hashes-2.4.0/sha2.js";
import { RegionalDataError, positiveInteger, requireData, validSha256 } from "./regional_manifest.js";

export const REGIONAL_HASH_READ_BYTES = 256 * 1024;
const MAXIMUM_FILE_BYTES = 2 ** 31;

export function regionalFileIntegrity(descriptor) {
  const byteSize = descriptor?.byte_size;
  const digest = descriptor?.sha256;
  requireData(positiveInteger(byteSize) && byteSize <= MAXIMUM_FILE_BYTES
    && validSha256(digest), "invalid_regional_file");
  return Object.freeze({ byte_size: byteSize, sha256: digest });
}

// The caller supplies an inactive OPFS File snapshot. Verification never writes,
// activates a component, changes a manifest, or retains the file's contents.
export async function verifyRegionalFile(file, descriptor, { signal, onProgress = () => {} } = {}) {
  const expected = regionalFileIntegrity(descriptor);
  requireData(file?.size === expected.byte_size, "regional_size_mismatch");
  signal?.throwIfAborted();
  const hash = sha256.create();
  let offset = 0;
  try {
    while (offset < expected.byte_size) {
      signal?.throwIfAborted();
      const end = Math.min(offset + REGIONAL_HASH_READ_BYTES, expected.byte_size);
      const bytes = new Uint8Array(await file.slice(offset, end).arrayBuffer());
      signal?.throwIfAborted();
      requireData(bytes.byteLength === end - offset, "regional_size_mismatch");
      hash.update(bytes);
      offset = end;
      onProgress({ verified_bytes: offset, byte_size: expected.byte_size });
      // Let worker cancellation messages run even with immediately resolved reads.
      if (offset % (8 * REGIONAL_HASH_READ_BYTES) === 0) {
        await new Promise((resolve) => globalThis.setTimeout(resolve, 0));
      }
    }
    signal?.throwIfAborted();
    const digest = Array.from(hash.digest(), (byte) => byte.toString(16).padStart(2, "0")).join("");
    requireData(digest === expected.sha256, "regional_checksum_mismatch");
    return Object.freeze({ byte_size: offset, sha256: digest });
  } catch (error) {
    if (error instanceof RegionalDataError || error?.name === "AbortError") throw error;
    throw new RegionalDataError("regional_read_failed");
  } finally {
    hash.destroy();
  }
}
