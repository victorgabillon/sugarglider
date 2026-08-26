import {
  applyNativeTerminalFailureToCurrentPage,
  createNativeTrackingBridge,
  createRetainedTerminalFailureProcessor,
  nativeStatusBelongsToOuting,
  nativeStatusBusy,
  projectNativeStatusForCurrentOuting,
} from "../../src/sugarglider/web/static/outing_native_bridge.js";

const ORIGIN = "https://example.test";
const SLUG = "native_outing_slug_12345";
const PARTICIPANT = "native_participant_12345";
const TOKEN = "synthetic_native_token_123456789";
const PAGE_A = "0123456789abcdef0123456789abcdef";
const PAGE_B = "fedcba9876543210fedcba9876543210";

export async function runPr27NativeBridgeHarness() {
  const scenarios = [];
  await scenarioOrdinaryBrowserHasNoBridge();
  scenarios.push("ordinary_browser_uses_no_native_bridge");
  await scenarioTrustedHandshakeAndStatus();
  scenarios.push("trusted_handshake_and_status");
  await scenarioExplicitStartUsesNativeMessage();
  scenarios.push("explicit_start_uses_native_message");
  await scenarioGetStatusDoesNotRestart();
  scenarios.push("reload_get_status_does_not_restart");
  await scenarioPageScopedLedgerAcrossReload();
  scenarios.push("page_scoped_ledger_across_reload");
  await scenarioStaleStartReplyIgnoredAfterStop();
  scenarios.push("stale_start_reply_ignored_after_stop");
  scenarioStatusCannotMutateAnotherOuting();
  scenarios.push("status_cannot_mutate_another_outing");
  scenarioProductionProjectionIsolatesAnotherOuting();
  scenarios.push("production_projection_isolates_another_outing");
  await scenarioTerminalFailureSurvivesPageAndAcknowledges();
  scenarios.push("terminal_failure_survives_page_and_acknowledges");
  scenarioTerminalCleanupPreservesNewerAndOwnerAuthority();
  scenarios.push("terminal_cleanup_preserves_newer_and_owner_authority");
  await scenarioTerminalStorageFailureRetries();
  scenarios.push("terminal_storage_failure_is_retryable");
  await scenarioTerminalAcknowledgementFailureRetries();
  scenarios.push("terminal_acknowledgement_failure_is_retryable");
  await scenarioTerminalSuccessIgnoresDuplicate();
  scenarios.push("terminal_success_ignores_duplicate");
  await scenarioStaleTerminalCannotMutateNewerAuthority();
  scenarios.push("stale_terminal_cannot_mutate_newer_authority");
  scenarioStoppingStatusIsGloballyBusy();
  scenarios.push("stopping_status_is_globally_busy");
  await scenarioMalformedAndAuthorityReplyIgnored();
  scenarios.push("malformed_authority_reply_ignored");
  await scenarioNativeStatusCreatesNoEventSource();
  scenarios.push("native_status_creates_no_event_source");
  return scenarios;
}

async function scenarioOrdinaryBrowserHasNoBridge() {
  const bridge = createNativeTrackingBridge({ port: null, origin: ORIGIN });
  equal(await bridge.initialize(), false, "ordinary browser remains non-native");
  equal(bridge.available(), false, "ordinary browser fallback stays available");
}

async function scenarioTrustedHandshakeAndStatus() {
  const port = automaticPort();
  const bridge = bridgeFor(port, PAGE_A);
  equal(await bridge.initialize(), true, "native hello is trusted");
  const status = await bridge.getStatus();
  equal(status.active, false, "safe stopped status returned");
  equal(port.types.join(","), "hello,get_status", "only handshake and status requested");
}

async function scenarioExplicitStartUsesNativeMessage() {
  const port = automaticPort();
  const bridge = bridgeFor(port, PAGE_A);
  await bridge.initialize();
  const reply = await bridge.start({
    receipt: {
      slug: SLUG,
      participant_id: PARTICIPANT,
      participant_token: TOKEN,
    },
    outingExpiresAt: "2026-08-07T00:00:00Z",
    currentSequence: 12,
  });
  equal(reply.type, "start_result", "native Start receives safe result");
  equal(port.types.filter((value) => value === "start_tracking").length, 1, "one native Start");
  const outgoing = port.requests.find((value) => value.type === "start_tracking");
  equal(outgoing.participant_token, TOKEN, "token travels only in trusted outgoing start");
  assert(!JSON.stringify(reply).includes(TOKEN), "native reply excludes token");
  assert(!JSON.stringify(reply).includes("coordinate"), "native reply excludes coordinate");
}

async function scenarioGetStatusDoesNotRestart() {
  const port = automaticPort({ active: true });
  const reloadedBridge = bridgeFor(port, PAGE_A);
  await reloadedBridge.initialize();
  await reloadedBridge.getStatus();
  equal(
    port.types.filter((value) => value === "start_tracking").length,
    0,
    "reload status never starts tracking",
  );
}

async function scenarioPageScopedLedgerAcrossReload() {
  const native = nativeLedger();
  const first = bridgeFor(native.page(), PAGE_A);
  await first.initialize();
  equal((await first.getStatus()).active, false, "first page sees stopped");

  native.status = safeStatus(true, "sharing");
  const second = bridgeFor(native.page(), PAGE_B);
  await second.initialize();
  equal((await second.getStatus()).active, true, "reloaded page sees current sharing");

  await first.start({
    receipt: { slug: SLUG, participant_id: PARTICIPANT, participant_token: TOKEN },
    outingExpiresAt: "2026-08-07T00:00:00Z",
  });
  await second.stop({ outingSlug: SLUG, participantId: PARTICIPANT });
  equal(native.startCalls, 1, "cross-page Start counter is distinct");
  equal(native.stopCalls, 1, "cross-page Stop counter is distinct");
  equal(native.ledger.size, 6, "one native ledger retains both page namespaces");
}

async function scenarioStaleStartReplyIgnoredAfterStop() {
  const held = new Map();
  const port = automaticPort({
    hold(type, request, respond) {
      if (["start_tracking", "stop_tracking"].includes(type)) {
        held.set(type, { request, respond });
        return true;
      }
      return false;
    },
  });
  const bridge = bridgeFor(port, PAGE_A);
  await bridge.initialize();
  const starting = bridge.start({
    receipt: { slug: SLUG, participant_id: PARTICIPANT, participant_token: TOKEN },
    outingExpiresAt: "2026-08-07T00:00:00Z",
  });
  await microtasks();
  const stopping = bridge.stop({ outingSlug: SLUG, participantId: PARTICIPANT });
  await microtasks();
  held.get("stop_tracking").respond(statusReply(
    held.get("stop_tracking").request,
    "stop_result",
    false,
    "stopping",
  ));
  held.get("start_tracking").respond(statusReply(
    held.get("start_tracking").request,
    "start_result",
    true,
    "sharing",
  ));
  equal((await stopping).state, "stopping", "current Stop owns its result");
  equal(await starting, null, "late Start reply is quarantined");
}

function scenarioStatusCannotMutateAnotherOuting() {
  const status = {
    outing_slug: SLUG,
    participant_id: PARTICIPANT,
    active: true,
  };
  const another = {
    slug: "different_outing_slug_1",
    participants: [{ participant_id: PARTICIPANT }],
  };
  equal(nativeStatusBelongsToOuting(status, another), false, "outing identity must match");
}

function scenarioProductionProjectionIsolatesAnotherOuting() {
  const priorIdentity = Object.freeze({
    outing_slug: "different_outing_slug_1",
    participant_id: "different_participant_1",
  });
  const applicationState = {
    outingSnapshot: {
      slug: "different_outing_slug_1",
      participants: [{ participant_id: "different_participant_1" }],
    },
    nativeServiceStatus: null,
    nativeTrackingOtherActive: false,
    outingTrackingBackend: "browser",
    nativeTrackingIdentity: priorIdentity,
    outingTrackingStatus: "inactive",
    outingTrackingActive: false,
    outingTrackingTransitionPending: false,
    outingTrackingClearFailed: false,
    outingTrackingLastPublishedAt: 42,
    outingTrackingMessage: "B remains unchanged",
  };
  const pageFieldsBefore = JSON.stringify({
    backend: applicationState.outingTrackingBackend,
    identity: applicationState.nativeTrackingIdentity,
    status: applicationState.outingTrackingStatus,
    active: applicationState.outingTrackingActive,
    transition: applicationState.outingTrackingTransitionPending,
    clearFailed: applicationState.outingTrackingClearFailed,
    published: applicationState.outingTrackingLastPublishedAt,
    message: applicationState.outingTrackingMessage,
  });
  equal(
    projectNativeStatusForCurrentOuting(
      applicationState,
      safeStatus(true, "sharing"),
    ),
    false,
    "outing A is not projected into outing B",
  );
  equal(JSON.stringify({
    backend: applicationState.outingTrackingBackend,
    identity: applicationState.nativeTrackingIdentity,
    status: applicationState.outingTrackingStatus,
    active: applicationState.outingTrackingActive,
    transition: applicationState.outingTrackingTransitionPending,
    clearFailed: applicationState.outingTrackingClearFailed,
    published: applicationState.outingTrackingLastPublishedAt,
    message: applicationState.outingTrackingMessage,
  }), pageFieldsBefore, "all page-scoped tracking fields remain unchanged");
  equal(applicationState.nativeTrackingOtherActive, true, "safe global busy hint remains");
}

async function scenarioTerminalFailureSurvivesPageAndAcknowledges() {
  const native = nativeLedger();
  native.terminalFailure = {
    event_id: 7,
    outing_slug: SLUG,
    participant_id: PARTICIPANT,
    code: "outing_not_found",
  };
  const failures = [];
  const first = bridgeFor(native.page(), PAGE_A);
  first.subscribe((event) => {
    if (event.kind === "permanent_failure") failures.push(event.failure);
  });
  await first.initialize();
  await first.getStatus();
  equal(failures.length, 1, "retained terminal event reaches recreated page");
  equal(await first.acknowledgeTerminalFailure(failures[0]), true, "matching page acks event");

  const laterFailures = [];
  const second = bridgeFor(native.page(), PAGE_B);
  second.subscribe((event) => {
    if (event.kind === "permanent_failure") laterFailures.push(event.failure);
  });
  await second.initialize();
  await second.getStatus();
  equal(laterFailures.length, 0, "acknowledged event is one-shot");
}

function scenarioTerminalCleanupPreservesNewerAndOwnerAuthority() {
  const owner = Object.freeze({ slug: SLUG, owner_token: "never-serialized" });
  const failedReceipt = Object.freeze({
    slug: SLUG,
    participant_id: PARTICIPANT,
    participant_token: TOKEN,
  });
  const state = {
    outingSnapshot: {
      slug: SLUG,
      participants: [{ participant_id: PARTICIPANT }],
    },
    outingOwnerReceipt: owner,
    outingParticipantReceipt: failedReceipt,
    participantRemembered: true,
    durableOutboxPresent: true,
    nativeServiceStatus: safeStatus(false, "stopped"),
    nativeTrackingOtherActive: false,
    nativeTrackingIdentity: {
      outing_slug: SLUG,
      participant_id: PARTICIPANT,
    },
    outingTrackingBackend: "native",
    outingTrackingStatus: "sharing",
    outingTrackingMessage: "Sharing",
    outingTrackingActive: true,
    outingTrackingTransitionPending: false,
    outingTrackingClearFailed: false,
    outingTrackingLastPublishedAt: 1,
  };
  const failure = {
    outing_slug: SLUG,
    participant_id: PARTICIPANT,
  };
  equal(
    applyNativeTerminalFailureToCurrentPage(state, failure),
    true,
    "matching failure applies",
  );
  equal(state.outingParticipantReceipt, null, "failed receipt cleared");
  equal(state.participantRemembered, false, "remembered identity cleared");
  equal(state.durableOutboxPresent, false, "latest-only outbox state cleared");
  equal(state.outingTrackingActive, false, "failed tracker is inactive");
  equal(state.outingOwnerReceipt, owner, "independent owner authority remains");

  const newerReceipt = Object.freeze({
    slug: SLUG,
    participant_id: "newer_participant_12345",
    participant_token: "newer_synthetic_participant_token_12345",
  });
  state.outingParticipantReceipt = newerReceipt;
  state.nativeTrackingIdentity = {
    outing_slug: SLUG,
    participant_id: newerReceipt.participant_id,
  };
  state.outingTrackingActive = true;
  equal(
    applyNativeTerminalFailureToCurrentPage(state, failure),
    false,
    "stale failure does not match newer authority",
  );
  equal(state.outingParticipantReceipt, newerReceipt, "newer receipt remains");
  equal(state.outingTrackingActive, true, "newer tracker state remains");
}

async function scenarioTerminalStorageFailureRetries() {
  const rig = terminalProcessorRig({
    cleanup: [new Error("synthetic storage failure"), true],
    acknowledgements: [true],
  });
  const first = rig.processor.process(rig.failure);
  equal(rig.state.outingParticipantReceipt, null, "authority clears before storage await");
  equal(await first, false, "storage failure leaves retained event retryable");
  equal(rig.storageFailures, 1, "optional storage failure is reported safely");
  equal(rig.acknowledgements, 0, "failed storage is never acknowledged");
  equal(rig.state.outingOwnerReceipt, rig.owner, "owner survives failed cleanup");
  equal(await rig.processor.process(rig.failure), true, "same event retries successfully");
  equal(rig.acknowledgements, 1, "retry acknowledges once");
}

async function scenarioTerminalAcknowledgementFailureRetries() {
  const rig = terminalProcessorRig({
    cleanup: [true, true],
    acknowledgements: [false, true],
  });
  equal(await rig.processor.process(rig.failure), false, "failed acknowledgement retries");
  equal(rig.cleared, 1, "UI authority clears only once");
  equal(await rig.processor.process(rig.failure), true, "second delivery re-acknowledges");
  equal(rig.acknowledgements, 2, "native acknowledgement attempted twice");
  equal(rig.cleared, 1, "retry does not resurrect or reclear UI authority");
}

async function scenarioTerminalSuccessIgnoresDuplicate() {
  let resolveCleanup;
  const heldCleanup = new Promise((resolve) => { resolveCleanup = resolve; });
  const rig = terminalProcessorRig({
    cleanup: [heldCleanup],
    acknowledgements: [true],
  });
  const first = rig.processor.process(rig.failure);
  equal(
    await rig.processor.process(rig.failure),
    false,
    "concurrent duplicate cannot start another cleanup",
  );
  resolveCleanup(true);
  equal(await first, true, "first cleanup and acknowledgement succeeds");
  equal(await rig.processor.process(rig.failure), false, "completed duplicate is ignored");
  equal(rig.cleanupCalls, 1, "successful event executes one cleanup");
  equal(rig.acknowledgements, 1, "successful event executes one acknowledgement");
}

async function scenarioStaleTerminalCannotMutateNewerAuthority() {
  const rig = terminalProcessorRig({ cleanup: [true], acknowledgements: [true] });
  rig.state.outingSnapshot = {
    slug: "newer_outing_slug_12345",
    participants: [{ participant_id: "newer_participant_12345" }],
  };
  rig.state.outingParticipantReceipt = Object.freeze({
    slug: "newer_outing_slug_12345",
    participant_id: "newer_participant_12345",
    participant_token: "newer_synthetic_participant_token_12345",
  });
  const newerReceipt = rig.state.outingParticipantReceipt;
  equal(await rig.processor.process(rig.failure), false, "stale event is rejected");
  equal(rig.state.outingParticipantReceipt, newerReceipt, "newer receipt is untouched");
  equal(rig.cleanupCalls, 0, "stale event performs no durable deletion");
  equal(rig.acknowledgements, 0, "stale event is not acknowledged by newer page");
}

function scenarioStoppingStatusIsGloballyBusy() {
  const stopping = {
    ...safeStatus(false, "stopping"),
    outing_slug: SLUG,
    participant_id: PARTICIPANT,
  };
  equal(nativeStatusBusy(stopping), true, "stopping is busy even when inactive");
  const applicationState = {
    outingSnapshot: {
      slug: "different_outing_slug_1",
      participants: [{ participant_id: "different_participant_1" }],
    },
    nativeTrackingOtherActive: false,
  };
  equal(
    projectNativeStatusForCurrentOuting(applicationState, stopping),
    false,
    "stopping session cannot project into another outing",
  );
  equal(applicationState.nativeTrackingOtherActive, true, "other outing sees global busy");
}

function terminalProcessorRig({ cleanup, acknowledgements }) {
  const owner = Object.freeze({ slug: SLUG, owner_token: "never-serialized" });
  const state = {
    outingSnapshot: {
      slug: SLUG,
      participants: [{ participant_id: PARTICIPANT }],
    },
    outingOwnerReceipt: owner,
    outingParticipantReceipt: Object.freeze({
      slug: SLUG,
      participant_id: PARTICIPANT,
      participant_token: TOKEN,
    }),
    participantRemembered: true,
    durableOutboxPresent: true,
    nativeServiceStatus: safeStatus(false, "stopped"),
    nativeTrackingOtherActive: false,
    nativeTrackingIdentity: {
      outing_slug: SLUG,
      participant_id: PARTICIPANT,
    },
    outingTrackingBackend: "native",
    outingTrackingStatus: "sharing",
    outingTrackingMessage: "Sharing",
    outingTrackingActive: true,
    outingTrackingTransitionPending: false,
    outingTrackingClearFailed: false,
    outingTrackingLastPublishedAt: 1,
  };
  const failure = Object.freeze({
    event_id: 27,
    outing_slug: SLUG,
    participant_id: PARTICIPANT,
    code: "outing_not_found",
  });
  const rig = {
    state,
    owner,
    failure,
    cleanupCalls: 0,
    acknowledgements: 0,
    storageFailures: 0,
    cleared: 0,
  };
  rig.processor = createRetainedTerminalFailureProcessor({
    matches: (value) => (
      state.outingSnapshot?.slug === value.outing_slug
      && state.outingSnapshot.participants.some(
        (participant) => participant.participant_id === value.participant_id,
      )
    ),
    clearInMemory: (value) => (
      applyNativeTerminalFailureToCurrentPage(state, value)
    ),
    durableCleanup: async () => {
      const outcome = cleanup[rig.cleanupCalls++];
      if (outcome instanceof Error) throw outcome;
      return await outcome;
    },
    acknowledge: async () => acknowledgements[rig.acknowledgements++],
    onCleared: () => { rig.cleared += 1; },
    onStorageFailure: () => { rig.storageFailures += 1; },
  });
  return rig;
}

async function scenarioMalformedAndAuthorityReplyIgnored() {
  const port = automaticPort({ malformedHello: true });
  const bridge = bridgeFor(port, PAGE_A);
  equal(await bridge.initialize(), false, "extra authority in reply rejects bridge trust");
}

async function scenarioNativeStatusCreatesNoEventSource() {
  let eventSources = 0;
  const original = globalThis.EventSource;
  globalThis.EventSource = function FakeEventSource() { eventSources += 1; };
  try {
    const bridge = bridgeFor(automaticPort({ active: true }), PAGE_A);
    await bridge.initialize();
    await bridge.getStatus();
    equal(eventSources, 0, "native status does not create public SSE connections");
  } finally {
    globalThis.EventSource = original;
  }
}

function automaticPort({ active = false, hold = null, malformedHello = false } = {}) {
  const port = {
    onmessage: null,
    requests: [],
    types: [],
    postMessage(payload) {
      const request = JSON.parse(payload);
      this.requests.push(request);
      this.types.push(request.type);
      const respond = (reply) => queueMicrotask(() => this.onmessage?.({
        data: JSON.stringify(reply),
      }));
      if (hold?.(request.type, request, respond)) return;
      const type = {
        hello: "hello_result",
        get_status: "tracking_status",
        start_tracking: "start_result",
        stop_tracking: "stop_result",
      }[request.type];
      const reply = statusReply(
        request,
        type,
        request.type === "start_tracking" || active,
        request.type === "start_tracking" || active ? "sharing" : "stopped",
      );
      if (malformedHello && request.type === "hello") {
        reply.participant_token = TOKEN;
      }
      respond(reply);
    },
  };
  return port;
}

function bridgeFor(port, pageNonce) {
  return createNativeTrackingBridge({ port, origin: ORIGIN, pageNonce });
}

function nativeLedger() {
  const native = {
    ledger: new Map(),
    status: safeStatus(false, "stopped"),
    terminalFailure: null,
    startCalls: 0,
    stopCalls: 0,
  };
  native.page = function page() {
    const port = { onmessage: null, postMessage: null };
    port.postMessage = (payload) => {
      const request = JSON.parse(payload);
      const nonce = request.request_id.split("-")[1];
      const key = `${nonce}:${request.request_id}`;
      const cached = native.ledger.get(key);
      if (cached) {
        queueMicrotask(() => port.onmessage?.({ data: cached }));
        return;
      }
      let type = "tracking_status";
      if (request.type === "hello") type = "hello_result";
      if (request.type === "start_tracking") {
        native.startCalls += 1;
        native.status = safeStatus(true, "sharing");
        type = "start_result";
      } else if (request.type === "stop_tracking") {
        native.stopCalls += 1;
        native.status = safeStatus(false, "stopped");
        type = "stop_result";
      } else if (request.type === "ack_terminal_failure") {
        if (
          native.terminalFailure?.event_id === request.event_id
          && native.terminalFailure.outing_slug === request.outing_slug
          && native.terminalFailure.participant_id === request.participant_id
        ) native.terminalFailure = null;
      }
      const reply = JSON.stringify(statusReplyFromStatus(request, type, native.status));
      native.ledger.set(key, reply);
      queueMicrotask(() => {
        port.onmessage?.({ data: reply });
        if (request.type === "get_status" && native.terminalFailure) {
          port.onmessage?.({
            data: JSON.stringify(failureReply(request, native.terminalFailure)),
          });
        }
      });
    };
    return port;
  };
  return native;
}

function safeStatus(active, state) {
  return {
    outing_slug: active ? SLUG : null,
    participant_id: active ? PARTICIPANT : null,
    active,
    state,
    last_published_at: null,
    pending_sample: false,
    stop_warning: null,
  };
}

function statusReplyFromStatus(request, type, status) {
  return { schema_version: 1, request_id: request.request_id, type, ...status };
}

function failureReply(request, failure) {
  return {
    schema_version: 1,
    request_id: `native-${request.request_id.split("-")[1]}-${failure.event_id}`,
    type: "permanent_failure",
    code: failure.code,
    event_id: failure.event_id,
    outing_slug: failure.outing_slug,
    participant_id: failure.participant_id,
  };
}

function statusReply(request, type, active, state) {
  return {
    schema_version: 1,
    request_id: request.request_id,
    type,
    outing_slug: active ? SLUG : null,
    participant_id: active ? PARTICIPANT : null,
    active,
    state,
    last_published_at: null,
    pending_sample: false,
    stop_warning: null,
  };
}

function equal(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${expected}, received ${actual}`);
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function microtasks() {
  await Promise.resolve();
  await Promise.resolve();
}
