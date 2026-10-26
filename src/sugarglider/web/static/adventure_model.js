import { nativeBridgeTransport } from "./native_bridge_transport.js";

const messages = { unavailable: "ChatGPT connection is available in the Android app.", cancelled: "Adventure planning cancelled.",
  browser_unavailable: "Android could not open a system browser for ChatGPT sign-in. Enable a browser, then try again.",
  deadline: "ChatGPT reached the 120-second request deadline. Try a shorter request; your existing route is unchanged.",
  network_timeout: "The network stopped responding while waiting for ChatGPT. Your existing route is unchanged.",
  network: "ChatGPT could not be reached. Your existing route is unchanged.", auth_expired: "Reconnect your ChatGPT account to continue.",
  auth_timeout: "Sign-in timed out. Try again and return to Sugarglider after the browser confirmation.",
  usage_limit: "Your ChatGPT usage limit was reached. Manage usage in your ChatGPT settings.",
  unsupported: "This account or model does not support the requested operation. Choose another available model or disable online research.",
  invalid_response: "ChatGPT did not return a usable complete answer. Your existing route is unchanged.", storage: "The protected ChatGPT account store is unavailable." };
const frenchMessages = {
  cancelled: "Planification annulée à votre demande.", deadline: "ChatGPT a atteint le délai maximal de 120 secondes. Essayez une demande plus courte ; votre parcours actuel est conservé.",
  network_timeout: "Le réseau a cessé de répondre pendant l’attente de ChatGPT. Votre parcours actuel est conservé.",
  network: "ChatGPT est injoignable. Votre parcours actuel est conservé.", auth_expired: "Reconnectez votre compte ChatGPT pour continuer.",
  usage_limit: "La limite d’utilisation de votre compte ChatGPT est atteinte. Consultez vos paramètres ChatGPT.",
  invalid_response: "ChatGPT n’a pas renvoyé de réponse complète utilisable. Votre parcours actuel est conservé.",
  unsupported: "Ce compte ou ce modèle ne prend pas en charge cette opération. Choisissez un autre modèle disponible ou désactivez la recherche en ligne.",
};
export class AdventureModelError extends Error {
  constructor(code) { super((/^fr(?:-|$)/i.test(globalThis.navigator?.language ?? "") ? frenchMessages[code] : null) ?? messages[code] ?? messages.invalid_response); this.code = Object.hasOwn(messages, code) ? code : "invalid_response"; }
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
      if (payload.error) {
        const error = new AdventureModelError(payload.error);
        if (action === "models" && payload.error === "invalid_response") error.message = "Your ChatGPT account is connected, but its model list could not be read. Try Refresh available models.";
        throw error;
      }
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
