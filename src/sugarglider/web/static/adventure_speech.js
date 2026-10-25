import { nativeBridgeTransport } from "./native_bridge_transport.js";

const modes = ["on_device", "platform", "unavailable"];
const statuses = ["ready", "completed", "cancelled", "unavailable", "busy", "timeout", "no_match",
  "permission_denied", "language_unavailable", "platform_consent_required"];
export function createAdventureSpeech({ transport = nativeBridgeTransport, origin = globalThis.location?.origin } = {}) {
  const owner = {};
  let active = null;
  async function invoke(action, fields = {}, signal) {
    if (origin !== "https://appassets.androidplatform.net" || !transport.nativeAvailable) return { status: "unavailable", mode: "unavailable", text: null };
    if (signal?.aborted) throw new DOMException("Speech cancelled.", "AbortError");
    const owned = action === "start" ? {} : null;
    if (owned && active) return { status: "busy", mode: "unavailable", text: null };
    if (owned) active = owned;
    const abort = () => { if (owned && active === owned) cancel(); };
    signal?.addEventListener("abort", abort, { once: true });
    try {
      const result = await transport.request(`adventure_speech_${action}`, fields, { owner: action === "cancel" ? null : owner, timeoutMs: 65000, parseReply: raw => {
        if (typeof raw !== "string" || raw.length > 40000) return null;
        try {
          const value = JSON.parse(raw);
          return Object.keys(value).sort().join(",") === "mode,request_id,schema_version,status,text,type"
            && value.schema_version === 1 && value.type === "adventure_speech_result" && modes.includes(value.mode)
            && statuses.includes(value.status) && (value.status === "completed"
              ? typeof value.text === "string" && value.text.length > 0 && value.text.length <= 8000
              : value.text === null) ? value : null;
        } catch { return null; }
      } });
      if (signal?.aborted) throw new DOMException("Speech cancelled.", "AbortError");
      return result ?? { status: "unavailable", mode: "unavailable", text: null };
    } finally {
      signal?.removeEventListener("abort", abort);
      if (owned && active === owned) active = null;
    }
  }
  function cancel() {
    if (!active) return;
    active = null;
    void invoke("cancel").catch(() => {});
    transport.cancelOwner(owner);
  }
  return Object.freeze({ status: () => invoke("status"), start: (language, allowPlatform, signal) => invoke("start", { language, allow_platform: allowPlatform }, signal), cancel });
}
