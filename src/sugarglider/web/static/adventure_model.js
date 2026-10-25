import { nativeBridgeTransport } from "./native_bridge_transport.js";

const messages = { unavailable: "ChatGPT connection is available in the Android app.", cancelled: "Adventure planning cancelled.",
  browser_unavailable: "Android could not open a system browser for ChatGPT sign-in. Enable a browser, then try again.",
  network: "ChatGPT could not be reached. Your existing route is unchanged.", auth_expired: "Reconnect your ChatGPT account to continue.",
  auth_timeout: "Sign-in timed out. Try again and return to Sugarglider after the browser confirmation.",
  usage_limit: "Your ChatGPT usage limit was reached. Manage usage in your ChatGPT settings.",
  unsupported: "This account or model does not support the requested operation. Choose another available model or disable online research.",
  invalid_response: "ChatGPT did not return a usable complete answer. Your existing route is unchanged.", storage: "The protected ChatGPT account store is unavailable." };
export class AdventureModelError extends Error {
  constructor(code) { super(messages[code] ?? messages.invalid_response); this.code = Object.hasOwn(messages, code) ? code : "invalid_response"; }
}
export function createAdventureModel({ transport = nativeBridgeTransport, origin = globalThis.location?.origin } = {}) {
  const owner = {};
  async function invoke(action, fields = {}, signal = null) {
    if (origin !== "https://appassets.androidplatform.net" || !transport.nativeAvailable) throw new AdventureModelError("unavailable");
    if (signal?.aborted) throw new AdventureModelError("cancelled");
    const abort = () => cancel();
    signal?.addEventListener("abort", abort, { once: true });
    try {
      // Sign-in owns a 180 s browser phase followed by up to 120 s native HTTP.
      const payload = await transport.request(`chatgpt_${action}`, fields, { owner, timeoutMs: action === "sign_in" ? 310_000 : 130_000,
        parseReply: raw => {
          if (typeof raw !== "string" || raw.length > 524_288) return null;
          let value; try { value = JSON.parse(raw); } catch { return null; }
          if (value?.type !== "chatgpt_result" || Object.keys(value).sort().join(",") !== "error,request_id,result,schema_version,type"
            || !(value.error === null || Object.hasOwn(messages, value.error)) || !(value.result === null || typeof value.result === "object" && !Array.isArray(value.result))) return null;
          return value;
        } });
      if (signal?.aborted) throw new AdventureModelError("cancelled");
      if (!payload) throw new AdventureModelError("network");
      if (payload.error) throw new AdventureModelError(payload.error);
      if (!payload.result) throw new AdventureModelError("invalid_response");
      return payload.result;
    } finally { signal?.removeEventListener("abort", abort); }
  }
  function cancel() {
    // Send native cancellation before releasing the JS request owner. A delayed
    // page callback cannot authorize another inference or restore cancelled work.
    void transport.request("chatgpt_cancel", {}, { owner: null, timeoutMs: 2000, parseReply: raw => { try { return JSON.parse(raw).type === "chatgpt_result" ? raw : null; } catch { return null; } } });
    transport.cancelOwner(owner);
  }
  return Object.freeze({ status: () => invoke("status"), models: signal => invoke("models", {}, signal),
    signIn: (accountId = null, signal) => invoke("sign_in", { account_id: accountId }, signal),
    select: accountId => invoke("select", { account_id: accountId }), signOut: () => invoke("sign_out"),
    infer: (input, signal) => invoke("infer", input, signal), cancel });
}
