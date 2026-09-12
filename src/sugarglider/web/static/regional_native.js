import { nativeBridgeTransport } from "./native_bridge_transport.js";
import { RegionalDataError, freezeData, requireData, requireFields, safeRegionalId, validSha256 } from "./regional_manifest.js";
import { captureRegionalRoutingReference } from "./regional_routing_reference.js";

const CODES = new Set([
  "invalid_regional_routing_reference", "regional_routing_unavailable", "regional_routing_incomplete",
  "regional_routing_busy", "regional_install_cancelled", "regional_size_mismatch", "regional_checksum_mismatch",
  "regional_identity_mismatch", "regional_routing_unsupported", "regional_routing_invalid",
  "regional_insufficient_storage", "regional_storage_unavailable", "regional_storage_limit",
  "regional_transfer_failed", "invalid_regional_source", "regional_transfer_timeout", "regional_encoded_download",
]);
const FIELDS = ["schema_version", "request_id", "type", "operation_id", "state", "received_bytes", "total_bytes", "code"];

export function parseRegionalNativeReply(payload) {
  let value;
  try { value = JSON.parse(payload); } catch { return null; }
  if (!value || typeof value !== "object" || Array.isArray(value)
    || Object.keys(value).length !== FIELDS.length || !FIELDS.every((key) => Object.hasOwn(value, key))
    || value.schema_version !== 1 || value.type !== "regional_routing_result"
    || !/^[A-Za-z0-9_-]{1,64}$/.test(value.request_id ?? "")
    || !/^[a-f0-9]{32}$/.test(value.operation_id ?? "")
    || !["running", "ready", "removed", "failed"].includes(value.state)
    || !Number.isSafeInteger(value.received_bytes) || !Number.isSafeInteger(value.total_bytes)
    || value.received_bytes < 0 || value.total_bytes < value.received_bytes || value.total_bytes > 2 ** 31
    || (value.state === "failed" ? !CODES.has(value.code) : value.code !== null)) return null;
  return freezeData(value);
}

// The native manager retains work until definite completion. Cancellation drains
// it before this promise settles; uncertain transport never authorizes cleanup.
export function createRegionalNativeClient({
  transport = nativeBridgeTransport,
  randomId = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join(""),
  pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  now = () => performance.now(),
} = {}) {
  async function run(action, value, { manifestUrl, signal, onProgress = () => {} } = {}) {
    const removesData = ["remove", "remove_version", "remove_region"].includes(action);
    let reference;
    if (action === "remove_version" || action === "remove_region") {
      requireFields(value, action === "remove_version" ? ["region_id", "build_id"] : ["region_id"]);
      requireData(safeRegionalId(value.region_id) && (action === "remove_region" || validSha256(value.build_id)), "invalid_regional_routing_reference");
      reference = freezeData(structuredClone(value));
    } else reference = captureRegionalRoutingReference(value);
    signal?.throwIfAborted();
    requireData(await transport.initialize().catch(() => false), "regional_native_unavailable");
    if (action === "install") requireData(typeof manifestUrl === "string" && manifestUrl.length > 0
      && manifestUrl.length <= 2_048, "invalid_regional_source");
    const operationId = randomId();
    requireData(/^[a-f0-9]{32}$/.test(operationId), "invalid_regional_operation");
    const owner = Object.freeze({ operationId });
    const fields = action === "remove_region" ? { operation_id: operationId, region_id: reference.region_id }
      : { operation_id: operationId, [action === "remove_version" ? "regional_version" : "regional_reference"]: reference };
    if (action === "install") fields.manifest_url = manifestUrl;
    const started = now();
    const progress = (status) => {
      // A presentation failure cannot release ownership of running file work.
      try { onProgress(status.received_bytes, status.total_bytes); } catch { /* Cosmetic callback only. */ }
    };
    const request = async (type, data) => {
      let reply = null;
      try { reply = await transport.request(`regional_routing_${type}`, data,
        { owner, parseReply: parseRegionalNativeReply, timeoutMs: 5_000 }); }
      catch { /* Treat transport failure as an uncertain outcome and drain. */ }
      return reply?.operation_id === operationId ? reply : null;
    };
    let reply = await request(action, fields);
    let cancelRequested = false;
    let uncertain = reply === null;
    while (!reply || reply.state === "running") {
      if ((signal?.aborted || uncertain) && !cancelRequested) {
        cancelRequested = true;
        reply = await request("cancel", { operation_id: operationId });
        if (reply && reply.state !== "running") break;
      }
      // This bounds browser ownership; an unconfirmed operation stays staged.
      if (now() - started > 31 * 60 * 1_000) throw new RegionalDataError("regional_native_outcome_uncertain");
      if (reply) progress(reply);
      await pause(500);
      reply = await request("status", { operation_id: operationId });
      uncertain ||= reply === null;
    }
    if (uncertain && reply.state === "failed" && reply.code === "regional_routing_unavailable") {
      throw new RegionalDataError("regional_native_outcome_uncertain");
    }
    if (reply.state === "failed") throw new RegionalDataError(reply.code);
    requireData(reply.state === (removesData ? "removed" : "ready"), "regional_native_outcome_uncertain");
    if (!removesData) signal?.throwIfAborted();
    progress(reply);
    return Object.freeze({ status: reply.state });
  }

  return Object.freeze({
    inspect: (reference, options) => run("inspect", reference, options),
    install: (reference, manifestUrl, options = {}) => run("install", reference, { ...options, manifestUrl }),
    remove: (reference, options) => run("remove", reference, options),
    removeVersion: (version, options) => run("remove_version", version, options),
    removeRegion: (regionId, options) => run("remove_region", { region_id: regionId }, options),
  });
}
