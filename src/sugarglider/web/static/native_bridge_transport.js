const SCHEMA_VERSION = 1;
const HELLO_TIMEOUT_MS = 2_000;
const PAGE_NONCE_PATTERN = /^[a-f0-9]{32}$/;
const REQUEST_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;
const IDENTITY_PATTERN = /^[A-Za-z0-9_-]{20,64}$/;
const HELLO_FIELDS = new Set([
  "schema_version",
  "request_id",
  "type",
  "outing_slug",
  "participant_id",
  "active",
  "state",
  "last_published_at",
  "pending_sample",
  "stop_warning",
]);
const SAFE_STATES = new Set([
  "starting",
  "waiting",
  "sharing",
  "offline_retrying",
  "stopping",
  "stopped",
  "outing_closed",
]);

export function createNativeBridgeTransport({
  port = globalThis.sugargliderNative ?? null,
  cryptoObject = globalThis.crypto,
  schedule = (callback, delay) => globalThis.setTimeout(callback, delay),
  cancelScheduled = (timer) => globalThis.clearTimeout(timer),
  lifecycleTarget = globalThis,
  pageNonce = cryptographicPageNonce(cryptoObject),
} = {}) {
  const nativeAvailable = validPort(port);
  let initialized = null;
  let listening = false;
  let trusted = false;
  let invalidated = false;
  let requestCounter = 0;
  const pending = new Map();
  const unsolicitedSubscribers = new Set();

  if (typeof lifecycleTarget?.addEventListener === "function") {
    lifecycleTarget.addEventListener("pagehide", invalidate, { once: true });
  }

  function initialize() {
    if (initialized) return initialized;
    if (
      invalidated
      || !nativeAvailable
      || !PAGE_NONCE_PATTERN.test(pageNonce ?? "")
    ) {
      initialized = Promise.resolve(null);
      return initialized;
    }
    try {
      port.onmessage = receive;
      listening = true;
    } catch {
      initialized = Promise.resolve(null);
      return initialized;
    }
    initialized = postRequest("hello", {}, {
      owner: null,
      parseReply: parseHelloReply,
      timeoutMs: HELLO_TIMEOUT_MS,
    }).then((payload) => {
      trusted = payload !== null && !invalidated;
      return trusted ? payload : null;
    });
    return initialized;
  }

  function request(type, fields, {
    owner,
    parseReply,
    timeoutMs,
  }) {
    if (trusted && !invalidated) {
      return postRequest(type, fields, { owner, parseReply, timeoutMs });
    }
    return initialize().then((payload) => (
      payload && trusted && !invalidated
        ? postRequest(type, fields, { owner, parseReply, timeoutMs })
        : null
    ));
  }

  function postRequest(type, fields, { owner, parseReply, timeoutMs }) {
    if (
      invalidated
      || !listening
      || typeof parseReply !== "function"
      || !Number.isFinite(timeoutMs)
      || timeoutMs <= 0
    ) return Promise.resolve(null);
    requestCounter += 1;
    const requestId = `web-${pageNonce}-${requestCounter}`;
    const payload = JSON.stringify({
      schema_version: SCHEMA_VERSION,
      request_id: requestId,
      type,
      ...fields,
    });
    return new Promise((resolve) => {
      const timer = schedule(() => settle(requestId, null), timeoutMs);
      pending.set(requestId, { owner, parseReply, resolve, timer });
      try {
        port.postMessage(payload);
      } catch {
        settle(requestId, null);
      }
    });
  }

  function receive(event) {
    if (invalidated) return;
    const envelope = parseEnvelope(event?.data);
    if (!envelope) return;
    const state = pending.get(envelope.request_id);
    if (state) {
      let reply = null;
      try {
        reply = state.parseReply(event.data);
      } catch {
        reply = null;
      }
      if (reply !== null) settle(envelope.request_id, reply);
      return;
    }
    if (!isUnsolicitedRequestId(envelope.request_id, pageNonce)) return;
    unsolicitedSubscribers.forEach((callback) => {
      try {
        callback(event.data);
      } catch {
        // One client cannot prevent safe native broadcasts reaching another.
      }
    });
  }

  function settle(requestId, reply) {
    const state = pending.get(requestId);
    if (!state) return;
    pending.delete(requestId);
    cancelScheduled(state.timer);
    state.resolve(reply);
  }

  function cancelOwner(owner) {
    if (owner === null || owner === undefined) return;
    for (const [requestId, state] of pending) {
      if (state.owner === owner) settle(requestId, null);
    }
  }

  function subscribeUnsolicited(callback) {
    if (typeof callback !== "function") return () => {};
    unsolicitedSubscribers.add(callback);
    return () => unsolicitedSubscribers.delete(callback);
  }

  function invalidate() {
    if (invalidated) return;
    invalidated = true;
    trusted = false;
    for (const requestId of [...pending.keys()]) settle(requestId, null);
    unsolicitedSubscribers.clear();
  }

  function available() {
    return trusted && !invalidated;
  }

  return Object.freeze({
    nativeAvailable,
    initialize,
    request,
    cancelOwner,
    subscribeUnsolicited,
    invalidate,
    available,
  });
}

export const nativeBridgeTransport = createNativeBridgeTransport();

function parseEnvelope(payload) {
  let value;
  try {
    value = JSON.parse(payload);
  } catch {
    return null;
  }
  return value && typeof value === "object" && !Array.isArray(value)
    && value.schema_version === SCHEMA_VERSION
    && REQUEST_ID_PATTERN.test(value.request_id ?? "")
    ? value
    : null;
}

function parseHelloReply(payload) {
  const value = parseEnvelope(payload);
  if (
    !value
    || value.type !== "hello_result"
    || !exactFields(value, HELLO_FIELDS)
    || typeof value.active !== "boolean"
    || !SAFE_STATES.has(value.state)
    || typeof value.pending_sample !== "boolean"
    || !optionalIdentity(value.outing_slug)
    || !optionalIdentity(value.participant_id)
    || !optionalTimestamp(value.last_published_at)
    || !(value.stop_warning === null || typeof value.stop_warning === "string")
    || (value.active && (!value.outing_slug || !value.participant_id))
  ) return null;
  return payload;
}

function isUnsolicitedRequestId(requestId, pageNonce) {
  const prefix = `native-${pageNonce}-`;
  return requestId.startsWith(prefix)
    && /^[1-9][0-9]*$/.test(requestId.slice(prefix.length));
}

function optionalIdentity(value) {
  return value === null || (
    typeof value === "string" && IDENTITY_PATTERN.test(value)
  );
}

function optionalTimestamp(value) {
  return value === null || (
    typeof value === "string" && Number.isFinite(Date.parse(value))
  );
}

function exactFields(value, expected) {
  const fields = Object.keys(value);
  return fields.length === expected.size
    && fields.every((field) => expected.has(field));
}

function validPort(value) {
  return value && typeof value.postMessage === "function";
}

function cryptographicPageNonce(cryptoObject) {
  if (typeof cryptoObject?.getRandomValues !== "function") return null;
  const bytes = new Uint8Array(16);
  cryptoObject.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0"))
    .join("");
}
