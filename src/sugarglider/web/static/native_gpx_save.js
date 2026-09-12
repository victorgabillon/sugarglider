import { nativeBridgeTransport } from "./native_bridge_transport.js";
import { MAX_GPX_OUTPUT_BYTES } from "./local_gpx_client.js";

const RESULT_FIELDS = new Set(["schema_version", "request_id", "type", "status"]);
const STATUSES = new Set(["saved", "cancelled", "busy", "unavailable", "write_failed"]);

export function createGpxFileSaver({ transport = nativeBridgeTransport, lifecycleTarget = globalThis } = {}) {
  let pending = null;
  let epoch = 0;
  lifecycleTarget?.addEventListener?.("pagehide", () => {
    epoch += 1;
    if (pending) transport.cancelOwner(pending);
  });

  async function save({ blob, filename }) {
    if (pending) throw new Error("Another GPX save is in progress.");
    if (!(blob instanceof Blob) || blob.type !== "application/gpx+xml" || !blob.size
      || blob.size > MAX_GPX_OUTPUT_BYTES || typeof filename !== "string"
      || !/^[^<>:"/\\|?*\x00-\x1F\x7F]+\.gpx$/u.test(filename) || filename.length > 104) {
      throw new Error("This GPX file cannot be saved.");
    }
    if (!transport.nativeAvailable) return { status: "browser", blob, filename };
    const owner = {}, ownedEpoch = epoch;
    pending = owner;
    try {
      const bytes = await blob.arrayBuffer();
      if (ownedEpoch !== epoch) throw new DOMException("Page left.", "AbortError");
      const reply = await transport.saveGpx(filename, bytes, {
        owner, parseReply: parseSaveReply, timeoutMs: 10 * 60_000,
      });
      if (ownedEpoch !== epoch) throw new DOMException("Page left.", "AbortError");
      if (!reply) throw new Error("GPX save status is unavailable. If you selected a file, check it before trying again.");
      if (reply.status === "busy") throw new Error("Finish or cancel the open file picker before saving another GPX.");
      if (reply.status === "unavailable") throw new Error("Android could not open the file picker. Reopen the app and try again.");
      if (reply.status === "write_failed") throw new Error("The GPX file could not be saved completely. Check the chosen folder and retry.");
      return { status: reply.status, filename };
    } finally { if (pending === owner) pending = null; }
  }
  return Object.freeze({ save });
}

export function parseSaveReply(payload) {
  let value;
  try { value = JSON.parse(payload); } catch { return null; }
  if (!value || Array.isArray(value) || value.schema_version !== 1
    || typeof value.request_id !== "string" || !/^[A-Za-z0-9_-]{1,64}$/.test(value.request_id)
    || value.type !== "save_gpx_result" || !STATUSES.has(value.status)
    || Object.keys(value).length !== RESULT_FIELDS.size
    || !Object.keys(value).every((key) => RESULT_FIELDS.has(key))) return null;
  return value;
}
