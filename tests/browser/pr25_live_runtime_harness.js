import {
  createDirtyRerun,
  createGuardedSingleFlight,
  createOutingLiveLifecycle,
  discardStaleParticipantReceipt,
  participantReceiptBelongsToOuting,
} from "../../src/sugarglider/web/static/outing_live_lifecycle.js";
import {
  applyLiveEvent,
  emptyOutingLiveState,
  replaceWithSnapshot,
} from "../../src/sugarglider/web/static/outing_live_state.js";
import {
  createOutingTracker,
  normalizeGeolocationPosition,
} from "../../src/sugarglider/web/static/outing_tracking.js";

const SLUG = "runtime_outing_slug_12345";
const PARTICIPANT_ID = "runtime_participant_12345";
const RECEIPT = {
  slug: SLUG,
  participant_id: PARTICIPANT_ID,
  participant_token: "p".repeat(32),
};

export async function runPr25LiveRuntimeHarness() {
  const scenarios = [];
  await scenarioLatePutAfterStop();
  scenarios.push("late_put_after_stop");
  await scenarioOldPutFinallyAfterNewStart();
  scenarios.push("old_put_finally_after_new_start");
  await scenarioTransportFailureStopUncertain();
  scenarios.push("transport_failure_stop_uncertain");
  await scenarioQueuedFixAfterStop();
  scenarios.push("queued_fix_after_stop");
  await scenarioConflictRecoveryAfterStop();
  scenarios.push("conflict_recovery_after_stop");
  await scenarioClearAfterShutdown();
  scenarios.push("clear_after_shutdown");
  await scenarioNewStartResetsCadenceAndRetry();
  scenarios.push("new_start_resets_cadence_and_retry");
  scenarioStrictMalformedValues();
  scenarios.push("strict_malformed_values");
  await scenarioClosedDuringRecovery();
  scenarios.push("outing_closed_during_recovery");
  await scenarioTransientRecoveryReconnect();
  scenarios.push("transient_recovery_reconnect");
  await scenarioMembershipDirtyRerun();
  scenarios.push("membership_dirty_rerun");
  await scenarioJoinInvalidatesStaleMembershipRefresh();
  scenarios.push("join_invalidates_stale_membership_refresh");
  scenarioStaleParticipantReceipt();
  scenarios.push("stale_participant_receipt");
  scenarioOldSessionHandler();
  scenarios.push("old_session_handler");
  return scenarios;
}

async function scenarioLatePutAfterStop() {
  const publication = deferred();
  const rig = createTrackerRig({
    publishPosition: () => publication.promise,
  });
  rig.tracker.start(RECEIPT, { available: true });
  rig.geolocation.emit(rig.geolocation.latest(), rawPosition());
  rig.scheduler.runNext();
  equal(rig.publishCalls(), 1, "first PUT dispatched");
  const statusBoundary = rig.statuses.length;
  const stopping = rig.tracker.stop(RECEIPT);
  publication.resolve({ sequence: 1_000 });
  const result = await stopping;
  equal(result.cleared, true, "serialized Stop clears after definite PUT");
  equal(rig.published.length, 0, "late PUT cannot publish optimistically");
  equal(
    rig.statuses.slice(statusBoundary).some((value) => value.status === "sharing"),
    false,
    "late PUT cannot restore sharing status",
  );
}

async function scenarioOldPutFinallyAfterNewStart() {
  const oldPublication = deferred();
  const newPublication = deferred();
  let publicationIndex = 0;
  const rig = createTrackerRig({
    publishPosition: () => {
      publicationIndex += 1;
      return publicationIndex === 1
        ? oldPublication.promise
        : newPublication.promise;
    },
    stopPublishWaitMs: 10,
  });
  rig.tracker.start(RECEIPT, { available: true });
  rig.geolocation.emit(rig.geolocation.latest(), rawPosition());
  rig.scheduler.runNext();
  const stopping = rig.tracker.stop(RECEIPT);
  rig.scheduler.runNext((task) => task.delay === 10);
  const stopResult = await stopping;
  equal(stopResult.uncertain, true, "timed-out PUT makes Stop uncertain");

  rig.tracker.start(RECEIPT, { available: true });
  rig.geolocation.emit(rig.geolocation.latest(), rawPosition(2));
  rig.scheduler.runNext((task) => task.delay === 0);
  equal(
    rig.tracker.status().requestInFlight,
    true,
    "new session owns its PUT",
  );
  oldPublication.resolve({ sequence: 1_001 });
  await microtasks();
  equal(
    rig.tracker.status().requestInFlight,
    true,
    "old finally cannot clear new PUT ownership",
  );
  newPublication.resolve({ sequence: 1_002 });
  await microtasks();
  equal(rig.published.length, 1, "only new session publishes");
}

async function scenarioQueuedFixAfterStop() {
  const rig = createTrackerRig();
  rig.tracker.start(RECEIPT, { available: true });
  const oldWatch = rig.geolocation.latest();
  await rig.tracker.stop(RECEIPT);
  rig.geolocation.emit(oldWatch, rawPosition());
  rig.scheduler.runAll();
  equal(rig.publishCalls(), 0, "queued callback after clearWatch is ignored");
}

async function scenarioTransportFailureStopUncertain() {
  const rig = createTrackerRig({
    publishPosition: () => Promise.reject(new TypeError("offline")),
  });
  rig.tracker.start(RECEIPT, { available: true });
  rig.geolocation.emit(rig.geolocation.latest(), rawPosition());
  rig.scheduler.runNext();
  await microtasks();
  const result = await rig.tracker.stop(RECEIPT);
  equal(result.uncertain, true, "transport failure keeps Stop uncertain");
  equal(rig.cleared.length, 0, "uncertain Stop cannot remove optimistically");
  equal(
    rig.tracker.status().clearingFailed,
    true,
    "uncertain Stop remains retryable",
  );
}

async function scenarioConflictRecoveryAfterStop() {
  const snapshot = deferred();
  const rig = createTrackerRig({
    publishPosition: () => Promise.reject({
      code: "outing_position_sequence_conflict",
      metadata: { status: 409 },
    }),
    getLiveSnapshot: () => snapshot.promise,
  });
  rig.tracker.start(RECEIPT, { available: true });
  rig.geolocation.emit(rig.geolocation.latest(), rawPosition());
  rig.scheduler.runNext();
  await microtasks();
  equal(rig.snapshotCalls(), 1, "409 starts authoritative GET");
  await rig.tracker.stop(RECEIPT);
  snapshot.resolve({ positions: [{ participant_id: PARTICIPANT_ID, sequence: 8 }] });
  await microtasks();
  rig.scheduler.runAll();
  equal(rig.publishCalls(), 1, "stale recovery cannot retry");
  equal(
    rig.tracker.status().hasPendingSample,
    false,
    "stale recovery cannot restore pending sample",
  );
}

async function scenarioClearAfterShutdown() {
  for (const rejected of [false, true]) {
    const clearing = deferred();
    const rig = createTrackerRig({
      clearPosition: () => clearing.promise,
    });
    rig.tracker.start(RECEIPT, { available: true });
    const stopping = rig.tracker.stop(RECEIPT);
    await microtasks();
    equal(rig.clearCalls(), 1, "Stop owns exactly one clear request");
    rig.tracker.shutdown();
    if (rejected) clearing.reject(new TypeError("offline"));
    else clearing.resolve();
    const result = await stopping;
    equal(result.stale, true, "stale clear result is quarantined");
    equal(rig.cleared.length, 0, "stale clear cannot invoke onCleared");
    equal(rig.tracker.status().status, "inactive", "shutdown status persists");
  }
}

async function scenarioNewStartResetsCadenceAndRetry() {
  let now = 10_000;
  let rejectNewSession = false;
  const rig = createTrackerRig({
    clock: () => now,
    publishPosition: () => rejectNewSession
      ? Promise.reject(new TypeError("offline"))
      : Promise.resolve({ sequence: now }),
  });
  rig.tracker.start(RECEIPT, { available: true });
  rig.geolocation.emit(rig.geolocation.latest(), rawPosition());
  rig.scheduler.runNext();
  await microtasks();
  await rig.tracker.stop(RECEIPT);

  now += 1;
  rejectNewSession = true;
  rig.tracker.start(RECEIPT, { available: true });
  rig.geolocation.emit(rig.geolocation.latest(), rawPosition(2));
  equal(
    rig.scheduler.nextDelay(),
    0,
    "new Start first fix has no inherited cadence delay",
  );
  rig.scheduler.runNext();
  await microtasks();
  equal(
    rig.scheduler.nextDelay(),
    1_000,
    "new Start uses initial retry delay",
  );
}

function scenarioStrictMalformedValues() {
  const invalidGeolocationValues = [
    withRawPosition({ latitude: null }),
    withRawPosition({ longitude: "" }),
    withRawPosition({ accuracy: true }),
    { ...rawPosition(), timestamp: null },
    withRawPosition({ latitude: "48.8" }),
  ];
  for (const value of invalidGeolocationValues) {
    equal(
      normalizeGeolocationPosition(value),
      null,
      "coerced required geolocation value rejected",
    );
  }
  equal(
    normalizeGeolocationPosition(
      withRawPosition({ altitude: "100" }),
    ).altitude_m,
    null,
    "invalid browser optional value becomes null",
  );

  const valid = liveSnapshot();
  equal(
    replaceWithSnapshot(emptyOutingLiveState(), valid, SLUG, 0).status,
    "applied",
    "valid snapshot applies",
  );
  const malformed = [
    mutateSnapshot(valid, (value) => { value.positions[0].coordinate.lat = null; }),
    mutateSnapshot(valid, (value) => { value.positions[0].coordinate.lon = ""; }),
    mutateSnapshot(valid, (value) => { value.positions[0].accuracy_m = true; }),
    mutateSnapshot(valid, (value) => { value.positions[0].sequence = "1"; }),
    mutateSnapshot(valid, (value) => { value.positions[0].altitude_m = "10"; }),
    mutateSnapshot(valid, (value) => {
      value.positions[0].captured_at = "2026-01-01T00:00:00";
    }),
  ];
  for (const value of malformed) {
    equal(
      replaceWithSnapshot(emptyOutingLiveState(), value, SLUG, 0).status,
      "recovery_required",
      "malformed public number or timestamp rejected",
    );
  }
  equal(
    replaceWithSnapshot(
      emptyOutingLiveState(),
      valid,
      "different_outing_slug_123",
      0,
    ).status,
    "recovery_required",
    "wrong snapshot slug rejected",
  );
  const current = replaceWithSnapshot(
    emptyOutingLiveState(),
    valid,
    SLUG,
    0,
  ).state;
  const event = liveEvent();
  event.schema_version = 2;
  equal(
    applyLiveEvent(current, event, "2", 1).status,
    "recovery_required",
    "malformed event schema rejected",
  );
}

async function scenarioClosedDuringRecovery() {
  const lifecycle = createOutingLiveLifecycle();
  let activeSlug = SLUG;
  let closed = false;
  const session = lifecycle.start(SLUG);
  const snapshot = deferred();
  let applied = 0;
  let streams = 0;
  const recovery = createGuardedSingleFlight({
    isCurrent: (value) => lifecycle.owns(value, activeSlug, closed),
    load: () => snapshot.promise,
    apply: () => {
      applied += 1;
      streams += 1;
    },
  });
  const pending = recovery.run(session);
  closed = true;
  lifecycle.invalidate();
  recovery.invalidate();
  snapshot.resolve(liveSnapshot());
  await pending;
  equal(applied, 0, "closed outing rejects stale recovery snapshot");
  equal(streams, 0, "closed outing cannot create replacement stream");
  activeSlug = null;
}

async function scenarioTransientRecoveryReconnect() {
  const lifecycle = createOutingLiveLifecycle();
  const session = lifecycle.start(SLUG);
  let currentConnection = null;
  const streams = [];
  let closedStreams = 0;
  let liveState = emptyOutingLiveState();

  function connectStream() {
    const operation = { session, handlers: null };
    currentConnection = operation;
    operation.handlers = {
      snapshot: (snapshot) => {
        if (
          currentConnection !== operation
          || !lifecycle.owns(session, SLUG, false)
        ) return;
        const result = replaceWithSnapshot(liveState, snapshot, SLUG, 0);
        if (result.status === "applied") liveState = result.state;
      },
    };
    streams.push(operation);
  }

  connectStream();
  const streamA = streams[0];
  const recovery = createGuardedSingleFlight({
    isCurrent: (value) => lifecycle.owns(value, SLUG, false),
    onStart: () => {
      if (currentConnection) closedStreams += 1;
      currentConnection = null;
    },
    load: () => Promise.reject(new TypeError("temporarily offline")),
    onError: () => {
      connectStream();
    },
  });
  await recovery.run(session);
  equal(closedStreams, 1, "reducer gap closes stream A once");
  equal(streams.length, 2, "transient recovery creates stream B once");
  streamA.handlers.snapshot(liveSnapshot());
  equal(liveState.cursor, 0, "old stream A remains quarantined");
  streams[1].handlers.snapshot(liveSnapshot());
  equal(liveState.cursor, 1, "stream B applies its initial snapshot");
}

async function scenarioMembershipDirtyRerun() {
  const lifecycle = createOutingLiveLifecycle();
  const session = lifecycle.start(SLUG);
  const first = deferred();
  const second = deferred();
  const loads = [first, second];
  const applied = [];
  let loadIndex = 0;
  const refresh = createDirtyRerun({
    isCurrent: (value) => lifecycle.owns(value, SLUG, false),
    load: () => loads[loadIndex++].promise,
    apply: (snapshot) => applied.push(snapshot.participants),
  });
  const pending = refresh.run(session);
  refresh.run(session);
  first.resolve({ participants: [PARTICIPANT_ID] });
  await microtasks();
  equal(loadIndex, 2, "dirty refresh schedules one rerun");
  second.resolve({ participants: [] });
  await pending;
  equal(applied.length, 2, "both serialized snapshots applied");
  equal(applied[1].length, 0, "final membership excludes departed participant");
}

async function scenarioJoinInvalidatesStaleMembershipRefresh() {
  const lifecycle = createOutingLiveLifecycle();
  const session = lifecycle.start(SLUG);
  const staleRefresh = deferred();
  const existingParticipantId = "existing_participant_12345";
  const preJoinSnapshot = {
    slug: SLUG,
    participants: [{ participant_id: existingParticipantId }],
  };
  const joinedSnapshot = {
    slug: SLUG,
    participants: [
      ...preJoinSnapshot.participants,
      { participant_id: PARTICIPANT_ID },
    ],
  };
  const joinedReceipt = { ...RECEIPT };
  const state = {
    outingSnapshot: preJoinSnapshot,
    outingParticipantReceipt: null,
    outingLiveAvailable: true,
    outingClosed: false,
  };
  let appliedRefreshes = 0;
  let trackerShutdowns = 0;
  let geolocationStarts = 0;
  let participantCards = [];
  let startControlsVisible = false;

  function renderStructuralView() {
    participantCards = state.outingSnapshot.participants.map(
      (participant) => participant.participant_id,
    );
    startControlsVisible = Boolean(
      state.outingLiveAvailable
      && !state.outingClosed
      && participantReceiptBelongsToOuting(
        state.outingParticipantReceipt,
        state.outingSnapshot,
      ),
    );
  }

  const refresh = createDirtyRerun({
    isCurrent: (value) => lifecycle.owns(value, SLUG, false),
    load: () => staleRefresh.promise,
    apply: (snapshot) => {
      appliedRefreshes += 1;
      state.outingSnapshot = snapshot;
      discardStaleParticipantReceipt(state, snapshot, {
        shutdownTracker: () => {
          trackerShutdowns += 1;
        },
        syncTrackerState: () => {},
      });
      renderStructuralView();
    },
  });
  const pending = refresh.run(session);

  refresh.invalidate();
  state.outingSnapshot = joinedSnapshot;
  state.outingParticipantReceipt = joinedReceipt;
  renderStructuralView();

  staleRefresh.resolve(preJoinSnapshot);
  await pending;
  equal(appliedRefreshes, 0, "invalidated pre-join refresh is not applied");
  equal(
    participantCards.includes(PARTICIPANT_ID),
    true,
    "joined participant card remains",
  );
  equal(
    state.outingParticipantReceipt === joinedReceipt,
    true,
    "joined participant receipt remains",
  );
  equal(trackerShutdowns, 0, "joined tracker is not shut down");
  equal(startControlsVisible, true, "joined Start controls remain visible");
  equal(geolocationStarts, 0, "join does not start geolocation");
}

function scenarioStaleParticipantReceipt() {
  const state = {
    outingParticipantReceipt: { ...RECEIPT },
    outingOwnerReceipt: { slug: SLUG },
  };
  const snapshot = {
    slug: SLUG,
    participants: [{
      participant_id: "another_participant_12345",
    }],
  };
  let trackerActive = true;
  let synchronizedStatus = null;
  const discarded = discardStaleParticipantReceipt(state, snapshot, {
    shutdownTracker: () => {
      trackerActive = false;
    },
    syncTrackerState: () => {
      synchronizedStatus = trackerActive ? "active" : "inactive";
    },
  });
  equal(discarded, true, "departed participant receipt is discarded");
  equal(trackerActive, false, "departed participant tracker shuts down");
  equal(synchronizedStatus, "inactive", "inactive status synchronizes");
  equal(state.outingParticipantReceipt, null, "stale receipt is cleared");
  assert(state.outingOwnerReceipt, "owner capability remains in memory");
  equal(
    participantReceiptBelongsToOuting(RECEIPT, snapshot),
    false,
    "ordinary and live participant actions require current membership",
  );
}

function scenarioOldSessionHandler() {
  const lifecycle = createOutingLiveLifecycle();
  const oldSession = lifecycle.start(SLUG);
  const newSession = lifecycle.start(SLUG);
  equal(
    lifecycle.owns(oldSession, SLUG, false),
    false,
    "old source handler loses epoch ownership",
  );
  equal(
    lifecycle.owns(newSession, SLUG, false),
    true,
    "replacement source owns current epoch",
  );
}

function createTrackerRig(overrides = {}) {
  const scheduler = fakeScheduler();
  const geolocation = fakeGeolocation();
  const statuses = [];
  const published = [];
  const cleared = [];
  let publishCallCount = 0;
  let snapshotCallCount = 0;
  let clearCallCount = 0;
  const publish = overrides.publishPosition
    ?? (() => Promise.resolve({ sequence: 1 }));
  const snapshot = overrides.getLiveSnapshot
    ?? (() => Promise.resolve({ positions: [] }));
  const clear = overrides.clearPosition ?? (() => Promise.resolve());
  const tracker = createOutingTracker({
    publishPosition: (...args) => {
      publishCallCount += 1;
      return publish(...args);
    },
    getLiveSnapshot: (...args) => {
      snapshotCallCount += 1;
      return snapshot(...args);
    },
    clearPosition: (...args) => {
      clearCallCount += 1;
      return clear(...args);
    },
    onStatus: (value) => statuses.push(value),
    onPublished: (value) => published.push(value),
    onCleared: (value) => cleared.push(value),
    clock: overrides.clock ?? (() => 1_000),
    schedule: scheduler.schedule,
    cancelScheduled: scheduler.cancel,
    geolocation: geolocation.api,
    createAbortController: fakeAbortController,
    stopPublishWaitMs: overrides.stopPublishWaitMs ?? 10_000,
  });
  return {
    tracker,
    scheduler,
    geolocation,
    statuses,
    published,
    cleared,
    publishCalls: () => publishCallCount,
    snapshotCalls: () => snapshotCallCount,
    clearCalls: () => clearCallCount,
  };
}

function fakeScheduler() {
  const tasks = [];
  return {
    schedule(callback, delay) {
      const task = { callback, delay, cancelled: false };
      tasks.push(task);
      return task;
    },
    cancel(task) {
      task.cancelled = true;
    },
    runNext(predicate = () => true) {
      const index = tasks.findIndex(
        (task) => !task.cancelled && predicate(task),
      );
      assert(index >= 0, "expected a scheduled task");
      const [task] = tasks.splice(index, 1);
      task.callback();
    },
    runAll() {
      while (tasks.some((task) => !task.cancelled)) this.runNext();
    },
    nextDelay() {
      return tasks.find((task) => !task.cancelled)?.delay ?? null;
    },
  };
}

function fakeGeolocation() {
  let nextId = 1;
  const watches = [];
  return {
    api: {
      watchPosition(success, error) {
        const watch = { id: nextId++, success, error, cleared: false };
        watches.push(watch);
        return watch.id;
      },
      clearWatch(id) {
        const watch = watches.find((value) => value.id === id);
        if (watch) watch.cleared = true;
      },
    },
    latest() {
      return watches.at(-1);
    },
    emit(watch, position) {
      watch.success(position);
    },
  };
}

function fakeAbortController() {
  return {
    signal: { aborted: false },
    abort() {
      this.signal.aborted = true;
    },
  };
}

function rawPosition(offset = 0) {
  return {
    coords: {
      latitude: 48.8 + offset / 1_000,
      longitude: 2.3 + offset / 1_000,
      accuracy: 5,
      altitude: null,
      speed: null,
      heading: null,
    },
    timestamp: 1_700_000_000_000 + offset,
  };
}

function withRawPosition(changes) {
  const value = rawPosition();
  return {
    ...value,
    coords: { ...value.coords, ...changes },
    timestamp: changes.timestamp ?? value.timestamp,
  };
}

function liveSnapshot() {
  return {
    schema_version: 1,
    slug: SLUG,
    generated_at: "2026-01-01T00:00:00Z",
    cursor: 1,
    stale_after_seconds: 120,
    expire_after_seconds: 3_600,
    positions: [{
      schema_version: 1,
      participant_id: PARTICIPANT_ID,
      sequence: 1,
      coordinate: { lat: 48.8, lon: 2.3 },
      accuracy_m: 5,
      altitude_m: null,
      speed_m_s: null,
      heading_deg: null,
      captured_at: "2026-01-01T00:00:00Z",
      received_at: "2026-01-01T00:00:01Z",
      stale_at: "2026-01-01T00:02:01Z",
      expires_at: "2026-01-01T01:00:01Z",
    }],
  };
}

function liveEvent() {
  return {
    schema_version: 1,
    event_id: 2,
    event_type: "position_cleared",
    participant_id: PARTICIPANT_ID,
    occurred_at: "2026-01-01T00:03:00Z",
    position: null,
    clear_reason: "stopped",
  };
}

function mutateSnapshot(snapshot, mutate) {
  const value = JSON.parse(JSON.stringify(snapshot));
  mutate(value);
  return value;
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function microtasks() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

function equal(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${expected}, received ${actual}`);
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
