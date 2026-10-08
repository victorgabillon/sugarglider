// Volatile transport only. The normal dialog's Review/Import remain authoritative.
import { nativeBridgeTransport } from "./native_bridge_transport.js";
import { ITINERARY_MAX_BYTES } from "./itinerary_draft.js";
const BUNDLED_ORIGIN = "https://appassets.androidplatform.net";
const BASE_FIELDS = ["schema_version", "request_id", "type"];
function exact(value, fields) {
  return Object.keys(value).length === fields.length && fields.every(key => Object.hasOwn(value, key));
}
export function parseExternalItineraryEvent(payload) {
  if (typeof payload !== "string" || payload.length > ITINERARY_MAX_BYTES * 6 + 1024) return null;
  let value; try { value = JSON.parse(payload); } catch { return null; }
  if (!value || Array.isArray(value) || value.schema_version !== 1
    || typeof value.request_id !== "string" || value.request_id.length > 64
    || !/^native-[a-f0-9]{32}-[1-9][0-9]*$/.test(value.request_id ?? "")) return null;
  if (value.type === "itinerary_dialog_back") return exact(value, BASE_FIELDS) ? value : null;
  if (value.type !== "external_itinerary_draft" || !exact(value, [...BASE_FIELDS, "text", "source_kind"])
    || !["shared_text", "shared_json_file", "opened_json_file"].includes(value.source_kind)
    || typeof value.text !== "string" || value.text.length > ITINERARY_MAX_BYTES
    || new TextEncoder().encode(value.text).byteLength > ITINERARY_MAX_BYTES) return null;
  return value;
}
function parseStateReply(payload) {
  let value; try { value = JSON.parse(payload); } catch { return null; }
  return value?.schema_version === 1 && value.type === "itinerary_dialog_state_result"
    && exact(value, [...BASE_FIELDS, "open"]) && typeof value.open === "boolean" ? payload : null;
}
export function initializeNativeItineraryHandoff({ dialog, transport = nativeBridgeTransport,
  origin = globalThis.location?.origin } = {}) {
  if (origin !== BUNDLED_ORIGIN || !transport.nativeAvailable) return Object.freeze({ close() {} });
  const owner = {}; let closed = false, lastCounter = 0n;
  const unsubscribe = transport.subscribeUnsolicited(payload => {
    if (closed || !transport.available()) return;
    const event = parseExternalItineraryEvent(payload); if (!event) return;
    const counter = BigInt(event.request_id.split("-").at(-1));
    if (counter <= lastCounter) return; lastCounter = counter;
    if (event.type === "itinerary_dialog_back") dialog.cancel();
    else dialog.openWithText(event.text, { sourceKind: event.source_kind });
  });
  function state(open) {
    if (!closed) void transport.request("itinerary_dialog_state", { open }, {
      owner, parseReply: parseStateReply, timeoutMs: 2000,
    });
  }
  const unsubscribeOpen = dialog.subscribeOpenChange(state);
  // The controller/subscriber exist before this request declares the UI ready.
  void transport.initialize().then(reply => { if (reply && !closed) state(dialog.isOpen()); });
  return Object.freeze({ close() { closed = true; unsubscribe(); unsubscribeOpen(); transport.cancelOwner(owner); } });
}
