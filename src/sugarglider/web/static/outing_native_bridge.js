const SCHEMA_VERSION = 1;
const REQUEST_TIMEOUT_MS = 15_000;
const STATUS_FIELDS = new Set([
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
const FAILURE_FIELDS = new Set([
  "schema_version",
  "request_id",
  "type",
  "code",
  "event_id",
  "outing_slug",
  "participant_id",
]);
const STATUS_TYPES = new Set([
  "hello_result",
  "tracking_status",
  "start_result",
  "stop_result",
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
const NATIVE_BUSY_STATES = new Set([
  "starting",
  "waiting",
  "sharing",
  "offline_retrying",
  "stopping",
]);
const IDENTITY_PATTERN = /^[A-Za-z0-9_-]{20,64}$/;

export function createNativeTrackingBridge({
  port = globalThis.sugargliderNative ?? null,
  origin = globalThis.location?.origin ?? null,
  schedule = (callback, delay) => globalThis.setTimeout(callback, delay),
  cancelScheduled = (timer) => globalThis.clearTimeout(timer),
  pageNonce = cryptographicPageNonce(globalThis.crypto),
} = {}) {
  let initialized = false;
  let trusted = false;
  let requestCounter = 0;
  let operationCounter = 0;
  let currentOperation = 0;
  let currentStatus = null;
  let initialization = null;
  const pending = new Map();
  const subscribers = new Set();

  async function initialize() {
    if (initialization) return initialization;
    if (
      !validPort(port)
      || typeof origin !== "string"
      || !/^[a-f0-9]{32}$/.test(pageNonce ?? "")
    ) return false;
    initialized = true;
    port.onmessage = receive;
    initialization = request("hello", {}, { operation: null, timeoutMs: 2_000 })
      .then((reply) => {
        trusted = reply?.type === "hello_result";
        if (trusted) applyStatus(reply);
        return trusted;
      })
      .catch(() => false);
    return initialization;
  }

  async function getStatus() {
    if (!await initialize()) return null;
    const reply = await request("get_status", {}, { operation: null });
    if (reply) applyStatus(reply);
    return currentStatus;
  }

  async function start({
    receipt,
    outingExpiresAt,
    currentSequence = 0,
  }) {
    if (!await initialize()) return null;
    const operation = ownOperation();
    const sequence = Number.isSafeInteger(currentSequence) && currentSequence >= 0
      ? currentSequence
      : 0;
    const reply = await request("start_tracking", {
      server_origin: origin,
      outing_slug: receipt.slug,
      participant_id: receipt.participant_id,
      participant_token: receipt.participant_token,
      outing_expires_at: outingExpiresAt,
      current_sequence: sequence,
    }, { operation });
    if (!owns(operation)) return null;
    if (reply?.type === "permanent_failure") notifyFailure(reply);
    else if (reply) applyStatus(reply);
    return reply;
  }

  async function stop({ outingSlug, participantId } = {}) {
    if (!await initialize()) return null;
    if (
      !IDENTITY_PATTERN.test(outingSlug ?? "")
      || !IDENTITY_PATTERN.test(participantId ?? "")
    ) return null;
    const operation = ownOperation();
    const reply = await request("stop_tracking", {
      outing_slug: outingSlug,
      participant_id: participantId,
    }, { operation });
    if (!owns(operation)) return null;
    if (reply?.type === "permanent_failure") notifyFailure(reply);
    else if (reply) applyStatus(reply);
    return reply;
  }

  async function acknowledgeTerminalFailure(failure) {
    if (!await initialize() || !Number.isSafeInteger(failure?.event_id)) {
      return false;
    }
    const reply = await request("ack_terminal_failure", {
      event_id: failure.event_id,
      outing_slug: failure.outing_slug,
      participant_id: failure.participant_id,
    }, { operation: null });
    return reply?.type === "tracking_status";
  }

  function subscribe(callback) {
    subscribers.add(callback);
    if (currentStatus) callback({ kind: "status", status: currentStatus });
    return () => subscribers.delete(callback);
  }

  function available() {
    return trusted;
  }

  function status() {
    return currentStatus;
  }

  function receive(event) {
    const reply = parseReply(event?.data);
    if (!reply) return;
    const requestState = pending.get(reply.request_id);
    if (requestState) {
      pending.delete(reply.request_id);
      cancelScheduled(requestState.timer);
      if (
        requestState.operation !== null
        && !owns(requestState.operation)
      ) {
        requestState.resolve(null);
        return;
      }
      requestState.resolve(reply);
      return;
    }
    if (reply.type === "tracking_status") applyStatus(reply);
    else if (reply.type === "permanent_failure") notifyFailure(reply);
  }

  function request(type, fields, { operation, timeoutMs = REQUEST_TIMEOUT_MS }) {
    if (!initialized || !validPort(port)) return Promise.resolve(null);
    requestCounter += 1;
    const requestId = `web-${pageNonce}-${requestCounter}`;
    const payload = JSON.stringify({
      schema_version: SCHEMA_VERSION,
      request_id: requestId,
      type,
      ...fields,
    });
    return new Promise((resolve) => {
      const timer = schedule(() => {
        const requestState = pending.get(requestId);
        if (!requestState) return;
        pending.delete(requestId);
        requestState.resolve(null);
      }, timeoutMs);
      pending.set(requestId, { operation, resolve, timer });
      try {
        port.postMessage(payload);
      } catch {
        pending.delete(requestId);
        cancelScheduled(timer);
        resolve(null);
      }
    });
  }

  function ownOperation() {
    operationCounter += 1;
    currentOperation = operationCounter;
    return currentOperation;
  }

  function owns(operation) {
    return currentOperation === operation;
  }

  function applyStatus(reply) {
    const statusValue = statusFromReply(reply);
    if (!statusValue) return;
    currentStatus = statusValue;
    subscribers.forEach((callback) => callback({
      kind: "status",
      status: statusValue,
    }));
  }

  function notifyFailure(reply) {
    subscribers.forEach((callback) => callback({
      kind: "permanent_failure",
      failure: Object.freeze({
        code: reply.code,
        event_id: reply.event_id,
        outing_slug: reply.outing_slug,
        participant_id: reply.participant_id,
      }),
    }));
  }

  return {
    initialize,
    getStatus,
    start,
    stop,
    acknowledgeTerminalFailure,
    subscribe,
    available,
    status,
  };
}

export const nativeTrackingBridge = createNativeTrackingBridge();

export function nativeStatusBusy(status) {
  return Boolean(status?.active || NATIVE_BUSY_STATES.has(status?.state));
}

export function nativeStatusBelongsToOuting(status, outing) {
  return Boolean(
    status
    && outing
    && status.outing_slug === outing.slug
    && outing.participants.some(
      (participant) => participant.participant_id === status.participant_id,
    )
  );
}

export function projectNativeStatusForCurrentOuting(
  applicationState,
  status,
) {
  applicationState.nativeServiceStatus = status;
  const belongs = nativeStatusBelongsToOuting(
    status,
    applicationState.outingSnapshot,
  );
  applicationState.nativeTrackingOtherActive = Boolean(
    nativeStatusBusy(status) && !belongs,
  );
  if (!belongs) return false;
  applicationState.outingTrackingBackend = "native";
  applicationState.nativeTrackingIdentity = Object.freeze({
    outing_slug: status.outing_slug,
    participant_id: status.participant_id,
  });
  applicationState.outingTrackingStatus = status.state;
  applicationState.outingTrackingActive = status.active;
  applicationState.outingTrackingTransitionPending = [
    "starting",
    "stopping",
  ].includes(status.state);
  applicationState.outingTrackingClearFailed = Boolean(status.stop_warning);
  applicationState.outingTrackingLastPublishedAt = status.last_published_at
    ? Date.parse(status.last_published_at)
    : null;
  return true;
}

export function resetNativePageProjection(applicationState) {
  applicationState.outingTrackingBackend = "browser";
  applicationState.nativeTrackingIdentity = null;
  applicationState.outingTrackingStatus = "inactive";
  applicationState.outingTrackingMessage = "Position sharing stopped";
  applicationState.outingTrackingActive = false;
  applicationState.outingTrackingTransitionPending = false;
  applicationState.outingTrackingClearFailed = false;
  applicationState.outingTrackingLastPublishedAt = null;
  applicationState.nativeTrackingOtherActive = Boolean(
    nativeStatusBusy(applicationState.nativeServiceStatus),
  );
}

export function createRetainedTerminalFailureProcessor({
  matches,
  clearInMemory,
  durableCleanup,
  acknowledge,
  onCleared = () => {},
  onStorageFailure = () => {},
  completedLimit = 64,
}) {
  const processing = new Set();
  const completed = new Set();
  const accepted = new Map();

  function sameAcceptedFailure(failure) {
    const prior = accepted.get(failure.event_id);
    return prior?.outingSlug === failure.outing_slug
      && prior.participantId === failure.participant_id;
  }

  async function process(failure) {
    const eventId = failure?.event_id;
    if (!Number.isSafeInteger(eventId) || eventId <= 0) return false;
    if (completed.has(eventId) || processing.has(eventId)) return false;
    if (accepted.has(eventId)) {
      if (!sameAcceptedFailure(failure)) return false;
    } else {
      if (!matches(failure)) return false;
      accepted.set(eventId, Object.freeze({
        outingSlug: failure.outing_slug,
        participantId: failure.participant_id,
      }));
    }

    processing.add(eventId);
    try {
      if (clearInMemory(failure)) onCleared(failure);

      let cleanup;
      try {
        cleanup = await durableCleanup(failure);
      } catch (error) {
        try {
          onStorageFailure(error);
        } catch {
          // Optional-storage reporting must not replace retryable cleanup.
        }
        return false;
      }
      if (cleanup === false || cleanup?.failed) {
        try {
          onStorageFailure(cleanup);
        } catch {
          // Optional-storage reporting must not replace retryable cleanup.
        }
        return false;
      }

      let acknowledged = false;
      try {
        acknowledged = await acknowledge(failure);
      } catch {
        acknowledged = false;
      }
      if (!acknowledged) return false;

      completed.add(eventId);
      accepted.delete(eventId);
      if (completed.size > completedLimit) {
        completed.delete(completed.values().next().value);
      }
      return true;
    } finally {
      processing.delete(eventId);
    }
  }

  return Object.freeze({ process });
}

export function applyNativeTerminalFailureToCurrentPage(
  applicationState,
  failure,
) {
  if (applicationState.outingSnapshot?.slug !== failure?.outing_slug) {
    return false;
  }
  const receiptMatches = Boolean(
    applicationState.outingParticipantReceipt?.slug === failure.outing_slug
    && applicationState.outingParticipantReceipt.participant_id
      === failure.participant_id
  );
  const nativeMatches = Boolean(
    applicationState.nativeTrackingIdentity?.outing_slug === failure.outing_slug
    && applicationState.nativeTrackingIdentity.participant_id
      === failure.participant_id
  );
  if (!receiptMatches && !nativeMatches) return false;
  if (receiptMatches) {
    applicationState.outingParticipantReceipt = null;
    applicationState.participantRemembered = false;
    applicationState.durableOutboxPresent = false;
  }
  if (nativeMatches) resetNativePageProjection(applicationState);
  if (nativeMatches || !applicationState.nativeTrackingIdentity) {
    applicationState.outingTrackingStatus = "inactive";
    applicationState.outingTrackingMessage = (
      "Participant access is no longer available"
    );
    applicationState.outingTrackingActive = false;
    applicationState.outingTrackingTransitionPending = false;
  }
  return true;
}

function parseReply(payload) {
  let value;
  try {
    value = JSON.parse(payload);
  } catch {
    return null;
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  if (value.schema_version !== SCHEMA_VERSION) return null;
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(value.request_id)) return null;
  if (STATUS_TYPES.has(value.type)) {
    return exactFields(value, STATUS_FIELDS) && statusFromReply(value)
      ? value
      : null;
  }
  if (value.type === "permanent_failure") {
    return exactFields(value, FAILURE_FIELDS)
      && typeof value.code === "string"
      && (value.event_id === null || (
        Number.isSafeInteger(value.event_id) && value.event_id > 0
      ))
      && optionalIdentity(value.outing_slug)
      && optionalIdentity(value.participant_id)
      ? value
      : null;
  }
  return null;
}

function statusFromReply(value) {
  if (
    !STATUS_TYPES.has(value.type)
    || typeof value.active !== "boolean"
    || !SAFE_STATES.has(value.state)
    || typeof value.pending_sample !== "boolean"
    || !optionalIdentity(value.outing_slug)
    || !optionalIdentity(value.participant_id)
    || !optionalTimestamp(value.last_published_at)
    || !(value.stop_warning === null || typeof value.stop_warning === "string")
  ) return null;
  if (value.active && (!value.outing_slug || !value.participant_id)) return null;
  return Object.freeze({
    outing_slug: value.outing_slug,
    participant_id: value.participant_id,
    active: value.active,
    state: value.state,
    last_published_at: value.last_published_at,
    pending_sample: value.pending_sample,
    stop_warning: value.stop_warning,
  });
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
