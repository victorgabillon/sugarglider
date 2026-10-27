import { nativeBridgeTransport } from "./native_bridge_transport.js";
import { t } from "./i18n.js";

const cancelled = () => new DOMException(t("Calculation cancelled. Your previous route is kept."), "AbortError");
const states = new Set(["running", "completed", "cancelled", "failed", "interrupted", "timeout", "idle", "busy", "stale", "unavailable", "notifications_required"]);
export function parseCalculationReply(raw) {
  let value;
  try { value = JSON.parse(raw); } catch { return null; }
  if (!value || value.schema_version !== 1 || value.type !== "calculation_result"
    || Object.keys(value).sort().join(",") !== "operation_id,recovery,request_id,schema_version,state,type"
    || !states.has(value.state) || !(value.operation_id === null || /^[a-f0-9]{32}$/.test(value.operation_id))) return null;
  if (value.recovery !== null) {
    const record = value.recovery;
    if (Object.keys(record).sort().join(",") !== "kind,operation_id,prompt,schema_version,state"
      || record.schema_version !== 1 || record.kind !== "adventure" || record.state !== "interrupted"
      || !/^[a-f0-9]{32}$/.test(record.operation_id) || typeof record.prompt !== "string"
      || record.prompt.length < 3 || record.prompt.length > 8000) return null;
  }
  return value;
}

// A visible Generate action owns both model rounds, regional work and publication.
// Resume only displays the same running operation or its already returned result.
export function createCalculationOperations({ transport = nativeBridgeTransport,
  cryptoObject = globalThis.crypto, lifecycleTarget = globalThis } = {}) {
  let active = null;
  const invoke = (action, fields = {}) => transport.request(`calculation_${action}`, fields, {
    owner: "calculation", timeoutMs: 10_000, parseReply: parseCalculationReply,
  });
  const unsubscribe = transport.subscribeUnsolicited?.(raw => {
    const reply = parseCalculationReply(raw);
    if (active && reply?.operation_id === active.id && reply.state === "cancelled") active.abort.abort();
  });
  async function run({ kind, prompt = null }, work, signal) {
    if (active) throw Error(t("A calculation is already running."));
    if (signal?.aborted) throw cancelled();
    if (!transport.nativeAvailable) return work(signal, null);
    const bytes = cryptoObject.getRandomValues(new Uint8Array(16));
    const id = Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
    const abort = new AbortController(), owned = { id, abort, interrupted: false };
    active = owned;
    const fromCaller = () => abort.abort();
    signal?.addEventListener("abort", fromCaller, { once: true });
    let outcome = "failed";
    try {
      const receipt = await invoke("begin", { operation_id: id, kind, prompt });
      if (abort.signal.aborted) throw cancelled();
      if (receipt?.state !== "running" || receipt.operation_id !== id) throw Error(t(receipt?.state === "notifications_required"
        ? "Allow calculation notifications in Android, then press Generate again. No calculation has started."
        : "Background calculation could not start. Return to Sugarglider and try again."));
      const result = await work(abort.signal, id);
      if (abort.signal.aborted) throw cancelled();
      outcome = "completed";
      return result;
    } catch (error) {
      if (abort.signal.aborted) {
        outcome = owned.interrupted ? "interrupted" : "cancelled";
        throw cancelled();
      }
      throw error;
    } finally {
      signal?.removeEventListener("abort", fromCaller);
      try { await invoke("finish", { operation_id: id, state: outcome }); }
      finally { if (active === owned) active = null; }
    }
  }
  function cancel() { active?.abort.abort(); }
  lifecycleTarget?.addEventListener?.("pagehide", () => {
    if (active) active.interrupted = true;
    cancel();
  }, { once: true });
  return Object.freeze({ run, cancel,
    forget: async id => (await invoke("forget", { operation_id: id }))?.state === "completed",
    recovery: async () => {
      if (!transport.nativeAvailable) return null;
      return (await invoke("recovery"))?.recovery ?? null;
    },
    close() { cancel(); unsubscribe?.(); },
    activeId: () => active?.id ?? null,
  });
}
export const calculationOperations = createCalculationOperations();
