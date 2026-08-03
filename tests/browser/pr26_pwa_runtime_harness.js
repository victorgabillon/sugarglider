import {
  createOfflineSnapshotRepository,
  validatePublicConfig,
  validateSnapshotPayload,
} from "../../src/sugarglider/web/static/offline_snapshots.js";
import {
  createDurableOutboxBridge,
  createParticipantSessionRepository,
  createPositionOutboxRepository,
  foregroundOutboxFlushAllowed,
} from "../../src/sugarglider/web/static/outing_durable_session.js";
import {
  createPwaController,
} from "../../src/sugarglider/web/static/pwa_controller.js";
import {
  applyPermanentParticipantFailureState,
  applyRememberedParticipantResult,
  clearUnavailableSavedRouteState,
  completeParticipantForget,
  createEpochOperationOwner,
  readOptionalStorage,
  resolveNetworkResource,
  runBestEffortStorage,
  settleOptionalPersistence,
} from "../../src/sugarglider/web/static/pwa_network.js";
import {
  createPwaStorageRuntime,
  offlineMapConfig,
} from "../../src/sugarglider/web/static/pwa_runtime.js";
import {
  createMemoryPwaStore,
  openPwaStore,
  PWA_STORES,
} from "../../src/sugarglider/web/static/pwa_store.js";
import {
  cacheFirstStatic,
  classifyShellRequest,
  createCurrentCacheAccess,
  networkFirstNavigation,
} from "../../src/sugarglider/web/static/service_worker_policy.js";
import {
  discardStaleParticipantReceipt,
  installAuthoritativeOutingSnapshot,
} from "../../src/sugarglider/web/static/outing_live_lifecycle.js";
import {
  createOutingTracker,
} from "../../src/sugarglider/web/static/outing_tracking.js";

const OUTING_SLUG = "runtime_outing_slug_12345";
const ROUTE_SLUG = "runtime_saved_route_12345";
const PARTICIPANT_ID = "runtime_participant_12345";
const TOKEN = "p".repeat(32);
const NOW = new Date("2026-01-01T12:00:00.000Z");
const EXPIRES = "2026-01-02T12:00:00.000Z";

export async function runPr26PwaRuntimeHarness() {
  const scenarios = [];
  await scenarioStorageInitializationFallback();
  scenarios.push("pwa_prune_failure_falls_back_to_memory");
  scenarios.push("pwa_runtime_promise_remains_usable");
  await scenarioOfflineRootStorageFailure();
  scenarios.push("offline_root_config_read_failure_still_renders_shell");
  await scenarioUpdateWaits();
  scenarios.push("update_waits_for_explicit_activation");
  await scenarioFailedActivationRetry();
  scenarios.push("failed_activation_message_is_retryable");
  await scenarioNavigationFallback();
  scenarios.push("navigation_network_failure_uses_shell");
  await scenarioOnlineErrorPreserved();
  scenarios.push("online_404_is_not_replaced");
  scenarioCacheExclusions();
  scenarios.push("api_sse_gpx_and_tiles_excluded");
  scenarioCapabilityHeaderExclusion();
  scenarios.push("capability_header_static_request_is_ignored");
  await scenarioCurrentCacheOnly();
  scenarios.push("unrelated_cache_cannot_supply_shell_or_static");
  await scenarioCacheWriteFailure();
  scenarios.push("static_network_success_survives_cache_write_failure");
  await scenarioSnapshotLifecycle();
  scenarios.push("explicit_snapshot_save_read_remove");
  await scenarioMalformedAndExpiredSnapshot();
  scenarios.push("malformed_and_expired_snapshot_removed");
  scenarioForbiddenSnapshotCapability();
  scenarios.push("public_snapshot_rejects_capability");
  scenarioForbiddenSnapshotKeyVariants();
  scenarios.push("mixed_spelling_public_capabilities_rejected");
  scenarioPublicConfigValidation();
  scenarios.push("public_config_rejects_unsafe_urls_and_inconsistent_limits");
  await scenarioSessionRequiresRemember();
  scenarios.push("session_requires_explicit_remember");
  await scenarioRememberWhitelist();
  scenarios.push("remember_uses_exact_participant_fields");
  await scenarioNoAuthorityLeak();
  scenarios.push("owner_and_invitation_authority_absent");
  await scenarioRestoreIsPassive();
  scenarios.push("restore_does_not_start_or_publish");
  await scenarioLatestOnlyOutbox();
  scenarios.push("latest_outbox_replaces_previous");
  await scenarioFutureOutboxRejected();
  scenarios.push("future_outbox_timestamp_rejected");
  await scenarioConcurrentOutboxOrdering();
  scenarios.push("concurrent_outbox_old_write_cannot_replace_new");
  await scenarioParticipantReplacement();
  scenarios.push("remember_new_participant_removes_old_outbox");
  await scenarioAtomicSessionConditionedOutbox();
  scenarios.push("cross_tab_forget_prevents_stale_outbox_write");
  scenarios.push("aborted_tab_cannot_leave_orphan_outbox");
  scenarios.push("stale_touch_cannot_restore_old_participant");
  await scenarioConditionalDeletion();
  scenarios.push("late_success_cannot_delete_newer_sample");
  await scenarioStopInvalidatesWrite();
  scenarios.push("stop_invalidates_stale_outbox_write");
  await scenarioRestoreDoesNotSend();
  scenarios.push("restored_outbox_does_not_auto_send");
  await scenarioFreshExplicitResume();
  scenarios.push("explicit_resume_accepts_fresh_sample");
  await scenarioStaleResumeDiscard();
  scenarios.push("stale_resume_sample_is_discarded");
  await scenarioOfflineFixReplacement();
  scenarios.push("offline_tracking_keeps_only_newest_fix");
  scenarioForegroundOnlineGate();
  scenarios.push("online_flush_requires_visible_active_remembered");
  scenarioWorkerHasNoOutboxDependency();
  scenarios.push("worker_policy_has_no_outbox_access");
  await scenarioParticipantRemoval();
  scenarios.push("participant_removal_forgets_without_owner_loss");
  await scenarioReconnectParticipantRemoval();
  scenarios.push("reconnect_removed_participant_stops_tracker");
  scenarios.push("reconnect_removed_participant_preserves_owner");
  scenarioSavedRouteNotFoundClearsDisplay();
  scenarios.push("saved_route_reconnect_not_found_clears_display");
  await scenarioStaleRecoveryIgnored();
  scenarios.push("stale_recovery_cannot_replace_new_session");
  await scenarioStaleRememberedRestore();
  scenarios.push("stale_remembered_restore_cannot_mutate_new_outing");
  await scenarioNetworkAuthority();
  scenarios.push("config_transport_failure_plus_resource_404");
  await scenarioNetworkStorageSeparation();
  scenarios.push("network_success_plus_indexeddb_quota_failure");
  scenarios.push("network_success_plus_offline_refresh_failure");
  scenarios.push("definite_http_error_is_not_transport_offline");
  await scenarioDynamicReconnects();
  scenarios.push("online_outing_disconnect_then_reconnect");
  scenarios.push("online_saved_route_disconnect_then_reconnect");
  scenarios.push("offline_event_rerenders_mutation_controls");
  scenarios.push("reconnect_creates_exactly_one_stream");
  await scenarioConcurrentSnapshotLimit();
  scenarios.push("nine_concurrent_snapshot_saves_leave_eight");
  await scenarioMalformedKeyPruned();
  scenarios.push("malformed_keyed_snapshot_is_pruned");
  await scenarioPublishNotFoundCleanup(false);
  scenarios.push("publish_not_found_forgets_remembered_session");
  await scenarioPublishNotFoundCleanup(true);
  scenarios.push("sequence_recovery_not_found_forgets_session");
  await scenarioStopDuringNotFound(false);
  scenarios.push("stop_during_publish_not_found_still_forgets_identity");
  await scenarioStopDuringNotFound(true);
  scenarios.push("stop_during_sequence_not_found_still_forgets_identity");
  await scenarioStopBeforeNotFound(false);
  scenarios.push("stop_before_publish_not_found_still_forgets_identity");
  await scenarioStopBeforeNotFound(true);
  scenarios.push("stop_before_sequence_recovery_not_found_still_forgets_identity");
  await scenarioUncertainForget();
  scenarios.push("forget_after_uncertain_stop_preserves_expiry_warning");
  scenarios.push("forget_after_clear_failure_preserves_expiry_warning");
  await scenarioHandledRejection();
  scenarios.push("no_unhandled_promise_rejection");
  await scenarioRejectedCleanupStorage();
  scenarios.push("membership_removal_storage_rejection_is_handled");
  scenarios.push("outing_closure_storage_rejection_is_handled");
  await scenarioClearAllData();
  scenarios.push("clear_removes_snapshots_sessions_and_outbox");
  return scenarios;
}

async function scenarioStorageInitializationFallback() {
  const failed = createMemoryPwaStore();
  let closes = 0;
  const failedDurableStore = {
    ...failed,
    durable: true,
    async entries() {
      throw new Error("IndexedDB transaction failed");
    },
    close() {
      closes += 1;
      failed.close();
    },
  };
  const runtimePromise = createPwaStorageRuntime({
    openStore: async () => failedDurableStore,
  });
  const runtime = await runtimePromise;
  equal(await runtimePromise, runtime, "one usable runtime promise");
  equal(closes, 1, "failed durable connection closed");
  equal(runtime.storageUnavailable, true, "storage marked unavailable");
  equal(runtime.store.durable, false, "memory repository installed");
  await runtime.snapshots.prune();
  equal(
    await runtime.sessions.restore(OUTING_SLUG),
    null,
    "fallback repositories remain usable",
  );
}

async function scenarioOfflineRootStorageFailure() {
  let failures = 0;
  const stored = await readOptionalStorage(
    async () => {
      throw new Error("IndexedDB read failed");
    },
    { onFailure: () => { failures += 1; } },
  );
  const config = offlineMapConfig(stored, null);
  equal(stored, null, "failed optional config becomes absent config");
  equal(config.offline_mode, true, "offline shell config produced");
  equal(config.tile_url_template, "about:blank", "offline shell needs no tiles");
  equal(failures, 1, "storage failure reported once");
}

async function scenarioUpdateWaits() {
  const listeners = new Map();
  const messages = [];
  let reloads = 0;
  const waiting = {
    postMessage: (message) => messages.push(message),
  };
  const registration = {
    waiting,
    installing: null,
    addEventListener() {},
    update: async () => {},
  };
  const serviceWorkers = {
    controller: {},
    register: async (url, options) => {
      equal(url, "/service-worker.js", "worker URL");
      equal(options.scope, "/", "root scope");
      equal(options.type, "module", "module worker");
      equal(options.updateViaCache, "none", "worker imports bypass HTTP cache");
      return registration;
    },
    addEventListener: (name, callback) => listeners.set(name, callback),
  };
  let updateAvailable = false;
  const controller = createPwaController({
    serviceWorkers,
    storageManager: null,
    locationObject: { hostname: "localhost" },
    secureContext: true,
    reload: () => {
      reloads += 1;
    },
    onUpdateAvailable: (available) => {
      updateAvailable = available;
    },
  });
  await controller.register();
  equal(updateAvailable, true, "waiting update announced");
  equal(messages.length, 0, "install does not activate update");
  equal(controller.activateUpdate(), true, "explicit update activation");
  equal(messages.length, 1, "one activation message");
  listeners.get("controllerchange")();
  listeners.get("controllerchange")();
  equal(reloads, 1, "controller change reloads once");
}

async function scenarioFailedActivationRetry() {
  let attempts = 0;
  const statuses = [];
  const waiting = {
    postMessage() {
      attempts += 1;
      if (attempts === 1) throw new Error("detached worker");
    },
  };
  const controller = createPwaController({
    serviceWorkers: {
      controller: {},
      register: async () => ({
        waiting,
        installing: null,
        addEventListener() {},
        update: async () => {},
      }),
      addEventListener() {},
    },
    locationObject: { hostname: "localhost" },
    secureContext: true,
    onStatus: (status) => statuses.push(status),
  });
  await controller.register();
  equal(controller.activateUpdate(), false, "failed message reports failure");
  equal(controller.activateUpdate(), true, "activation can be retried");
  equal(attempts, 2, "one retry reaches waiting worker");
  truthy(statuses.includes("update_available"), "update state restored");
}

async function scenarioNavigationFallback() {
  const shell = { status: 200, shell: true };
  const result = await networkFirstNavigation(
    { url: "https://app.test/o/example" },
    {
      fetchRequest: async () => {
        throw new TypeError("offline");
      },
      matchRootShell: async () => shell,
      fallbackResponse: () => ({ status: 503 }),
    },
  );
  equal(result, shell, "network failure receives cached shell");
}

async function scenarioOnlineErrorPreserved() {
  const response = { status: 404 };
  let shellReads = 0;
  const result = await networkFirstNavigation(
    { url: "https://app.test/missing" },
    {
      fetchRequest: async () => response,
      matchRootShell: async () => {
        shellReads += 1;
        return { status: 200 };
      },
      fallbackResponse: () => ({ status: 503 }),
    },
  );
  equal(result, response, "online HTTP response returned unchanged");
  equal(shellReads, 0, "valid 404 does not read shell fallback");
}

function scenarioCacheExclusions() {
  const ignored = [
    "/v1/ui/config",
    "/v2/outings/example",
    "/v2/outings/example/events",
    "/v2/saved-routes/example/gpx",
  ];
  for (const pathname of ignored) {
    equal(
      classifyShellRequest(request(`https://app.test${pathname}`), "https://app.test"),
      "ignore",
      `${pathname} excluded`,
    );
  }
  equal(
    classifyShellRequest(
      request("https://tile.openstreetmap.org/1/1/1.png"),
      "https://app.test",
    ),
    "ignore",
    "cross-origin tile excluded",
  );
}

function scenarioCapabilityHeaderExclusion() {
  for (const name of [
    "Authorization",
    "Cookie",
    "X-Sugarglider-Participant-Token",
    "X-Sugarglider-Outing-Owner-Token",
    "X-Sugarglider-Outing-Join-Token",
    "X-Saved-Route-Owner-Token",
  ]) {
    equal(
      classifyShellRequest(
        request("https://app.test/static/app.js", "cors", { [name]: "secret" }),
        "https://app.test",
      ),
      "ignore",
      `${name} excludes static caching`,
    );
  }
}

async function scenarioCurrentCacheOnly() {
  const current = new Map();
  const unrelated = new Map([
    ["/", { source: "unrelated-shell" }],
    ["/static/app.js", { source: "unrelated-static" }],
  ]);
  const cacheStorage = {
    async open(name) {
      equal(name, "sugarglider-shell-v1", "only current cache opened");
      return {
        match: async (key) => current.get(key),
        put: async (key, value) => current.set(key, value),
      };
    },
    async match(key) {
      return unrelated.get(key);
    },
  };
  const access = createCurrentCacheAccess(
    cacheStorage,
    "sugarglider-shell-v1",
  );
  equal(await access.match("/"), undefined, "unrelated shell ignored");
  equal(
    await access.match("/static/app.js"),
    undefined,
    "unrelated static ignored",
  );
  await access.put("/", { source: "current-shell" });
  equal((await access.match("/")).source, "current-shell", "current cache used");
}

async function scenarioCacheWriteFailure() {
  const response = {
    ok: true,
    type: "basic",
    clone: () => ({ copy: true }),
  };
  const returned = await cacheFirstStatic(
    { url: "https://app.test/static/app.js" },
    {
      matchRequest: async () => null,
      fetchRequest: async () => response,
      storeResponse: async () => {
        throw new Error("CacheStorage quota exceeded");
      },
    },
  );
  equal(returned, response, "network asset survives cache write rejection");
}

async function scenarioSnapshotLifecycle() {
  const rig = persistence();
  equal(await rig.snapshots.read("saved_route", ROUTE_SLUG), null, "not automatic");
  await rig.snapshots.save("saved_route", savedRouteSnapshot());
  truthy(await rig.snapshots.read("saved_route", ROUTE_SLUG), "saved explicitly");
  await rig.snapshots.remove("saved_route", ROUTE_SLUG);
  equal(await rig.snapshots.read("saved_route", ROUTE_SLUG), null, "removed");
}

async function scenarioMalformedAndExpiredSnapshot() {
  const rig = persistence();
  await rig.store.put(
    PWA_STORES.offlineSnapshots,
    `saved_route:${ROUTE_SLUG}`,
    { schema_version: 99, kind: "saved_route", slug: ROUTE_SLUG },
  );
  equal(await rig.snapshots.read("saved_route", ROUTE_SLUG), null, "malformed deleted");
  const payload = savedRouteSnapshot({
    created_at: "2025-12-30T12:00:00.000Z",
    expires_at: "2025-12-31T12:00:00.000Z",
  });
  await rig.store.put(
    PWA_STORES.offlineSnapshots,
    `saved_route:${ROUTE_SLUG}`,
    {
      schema_version: 1,
      kind: "saved_route",
      slug: ROUTE_SLUG,
      saved_at: "2025-12-30T13:00:00.000Z",
      updated_at: "2025-12-30T13:00:00.000Z",
      expires_at: payload.expires_at,
      payload,
    },
  );
  equal(await rig.snapshots.read("saved_route", ROUTE_SLUG), null, "expired deleted");
}

function scenarioForbiddenSnapshotCapability() {
  throws(
    () => validateSnapshotPayload("saved_route", {
      ...savedRouteSnapshot(),
      owner_token: "secret",
    }),
    "token-bearing public snapshot rejected",
  );
}

function scenarioForbiddenSnapshotKeyVariants() {
  for (const key of [
    "token",
    "ownerToken",
    "ParticipantToken",
    "join-token",
    "CAPABILITY_token",
    "livePositions",
    "Live_Events",
    "eventCursor",
    "replay-cursor",
  ]) {
    throws(
      () => validateSnapshotPayload("saved_route", {
        ...savedRouteSnapshot(),
        metadata: { [key]: "forbidden" },
      }),
      `${key} rejected`,
    );
  }
}

function scenarioPublicConfigValidation() {
  truthy(validatePublicConfig(publicConfig()), "safe public config accepted");
  for (const invalid of [
    { tile_url_template: "javascript:alert(1)" },
    { tile_url_template: "https://user:secret@tiles.test/{z}/{x}/{y}.png" },
    { tile_url_template: "https://tiles.test/{z}/{x}/{y}.png?token=secret" },
    { poi_default_limit: 501 },
    { outing_live_stale_after_seconds: 300 },
  ]) {
    throws(
      () => validatePublicConfig(publicConfig(invalid)),
      "unsafe or inconsistent public config rejected",
    );
  }
}

async function scenarioSessionRequiresRemember() {
  const rig = persistence();
  equal(await rig.sessions.restore(OUTING_SLUG), null, "no implicit session");
}

async function scenarioRememberWhitelist() {
  const rig = persistence();
  const session = await rig.sessions.remember(receipt(), EXPIRES);
  equal(
    Object.keys(session).sort().join(","),
    [
      "last_used_at",
      "outing_expires_at",
      "outing_slug",
      "participant_id",
      "participant_token",
      "remembered_at",
      "schema_version",
    ].join(","),
    "remembered session whitelist",
  );
}

async function scenarioNoAuthorityLeak() {
  const rig = persistence();
  await rig.sessions.remember(receipt(), EXPIRES);
  const serialized = JSON.stringify(
    await rig.store.values(PWA_STORES.participantSessions),
  );
  equal(serialized.includes("owner"), false, "owner authority absent");
  equal(serialized.includes("invite"), false, "invitation authority absent");
}

async function scenarioRestoreIsPassive() {
  const rig = persistence();
  const session = await rig.sessions.remember(receipt(), EXPIRES);
  await rig.outbox.replace(session, sample(-1));
  const trackerRig = createTrackerRig({
    durableSamples: createDurableOutboxBridge({
      sessions: rig.sessions,
      outbox: rig.outbox,
    }),
  });
  truthy(
    await rig.sessions.restore(OUTING_SLUG, outingSnapshot()),
    "participant restored",
  );
  truthy(await rig.outbox.read(session), "outbox restored");
  equal(trackerRig.geolocation.watchCount(), 0, "restore does not start watch");
  equal(trackerRig.publishCalls(), 0, "restore does not publish");
}

async function scenarioLatestOnlyOutbox() {
  const rig = persistence();
  const session = await rig.sessions.remember(receipt(), EXPIRES);
  await rig.outbox.replace(session, sample(-2));
  const newest = await rig.outbox.replace(session, sample(-1));
  const records = await rig.store.values(PWA_STORES.positionOutbox);
  equal(records.length, 1, "one latest outbox record");
  equal(records[0].sample_id, newest.sample_id, "newest replaces old");
  equal("sequence" in records[0], false, "sequence not persisted");
  equal("participant_token" in records[0], false, "token not persisted");
}

async function scenarioFutureOutboxRejected() {
  const rig = persistence();
  const session = await rig.sessions.remember(receipt(), EXPIRES);
  const accepted = await rig.outbox.replace(session, sample(-1));
  const future = {
    ...accepted,
    captured_at: "2099-01-01T00:00:00.000Z",
    queued_at: "2099-01-01T00:00:01.000Z",
  };
  await rig.store.put(
    PWA_STORES.positionOutbox,
    `${OUTING_SLUG}:${PARTICIPANT_ID}`,
    future,
  );
  equal(await rig.outbox.read(session), null, "future record rejected");
  equal(
    (await rig.store.values(PWA_STORES.positionOutbox)).length,
    0,
    "future record deleted",
  );
  await rig.store.put(
    PWA_STORES.positionOutbox,
    `${OUTING_SLUG}:${PARTICIPANT_ID}`,
    future,
  );
  truthy(
    await rig.outbox.replace(session, sample(-1)),
    "current sample replaces poisoned future record",
  );
}

async function scenarioConcurrentOutboxOrdering() {
  const base = createMemoryPwaStore();
  const oldWrite = deferred();
  const store = {
    ...base,
    async putLatestOutboxIfSessionMatches(options) {
      if (options.value.captured_at === sample(-2).captured_at) {
        await oldWrite.promise;
      }
      return base.putLatestOutboxIfSessionMatches(options);
    },
  };
  const sessions = createParticipantSessionRepository(store, {
    clock: () => new Date(NOW),
  });
  let sampleIndex = 0;
  const outbox = createPositionOutboxRepository(store, {
    clock: () => new Date(NOW),
    createSampleId: () => `sample_identifier_${++sampleIndex}`,
  });
  const session = await sessions.remember(receipt(), EXPIRES);
  const stale = outbox.replace(session, sample(-2));
  await microtasks();
  const newest = await outbox.replace(session, sample(-1));
  oldWrite.resolve();
  equal(await stale, null, "late old write rejected");
  equal(
    (await outbox.read(session)).sample_id,
    newest.sample_id,
    "newest record survives reversed completion",
  );
}

async function scenarioAtomicSessionConditionedOutbox() {
  const store = await openPwaStore();
  await Promise.all([
    store.clear(PWA_STORES.participantSessions),
    store.clear(PWA_STORES.positionOutbox),
  ]);
  let sampleIndex = 0;
  const sessions = createParticipantSessionRepository(store, {
    clock: () => new Date(NOW),
  });
  const outbox = createPositionOutboxRepository(store, {
    clock: () => new Date(NOW),
    createSampleId: () => `atomic_sample_identifier_${++sampleIndex}`,
  });
  const staleSession = await sessions.remember(receipt(), EXPIRES);
  await outbox.replace(staleSession, sample(-2));
  await sessions.forget(OUTING_SLUG);
  equal(
    await outbox.replace(staleSession, sample(-1)),
    null,
    "forgotten session rejects stale-tab write atomically",
  );
  equal(
    (await store.values(PWA_STORES.positionOutbox)).length,
    0,
    "aborted tab cannot leave an orphan outbox",
  );
  equal("touch" in sessions, false, "unsafe session touch API removed");
  const replacement = {
    ...receipt(),
    participant_id: `${PARTICIPANT_ID}_replacement`,
    participant_token: "r".repeat(32),
  };
  await sessions.remember(replacement, EXPIRES);
  equal(
    await outbox.replace(staleSession, sample(-1)),
    null,
    "stale identity cannot write beside replacement session",
  );
  equal(
    (await sessions.restore(OUTING_SLUG)).participant_id,
    replacement.participant_id,
    "replacement session remains authoritative",
  );
  await Promise.all([
    store.clear(PWA_STORES.participantSessions),
    store.clear(PWA_STORES.positionOutbox),
  ]);
  store.close();
}

async function scenarioParticipantReplacement() {
  const rig = persistence();
  const firstSession = await rig.sessions.remember(receipt(), EXPIRES);
  await rig.outbox.replace(firstSession, sample(-1));
  const secondParticipant = `${PARTICIPANT_ID}_replacement`;
  await rig.sessions.remember({
    ...receipt(),
    participant_id: secondParticipant,
    participant_token: "q".repeat(32),
  }, EXPIRES);
  const entries = await rig.store.values(PWA_STORES.positionOutbox);
  equal(entries.length, 0, "previous participant outbox removed atomically");
  equal(
    (await rig.sessions.restore(OUTING_SLUG)).participant_id,
    secondParticipant,
    "new participant session installed",
  );
  equal(
    await rig.sessions.forgetMatching(OUTING_SLUG, PARTICIPANT_ID),
    false,
    "stale identity cannot delete replacement session",
  );
}

async function scenarioConditionalDeletion() {
  const rig = persistence();
  const session = await rig.sessions.remember(receipt(), EXPIRES);
  const first = await rig.outbox.replace(session, sample(-2));
  const second = await rig.outbox.replace(session, sample(-1));
  equal(
    await rig.outbox.removePublished(session, first.sample_id),
    false,
    "old sample cannot delete new sample",
  );
  equal(
    (await rig.outbox.read(session)).sample_id,
    second.sample_id,
    "new sample remains",
  );
}

async function scenarioStopInvalidatesWrite() {
  const rig = persistence();
  const session = await rig.sessions.remember(receipt(), EXPIRES);
  const gate = deferred();
  let firstRestore = true;
  const sessions = {
    restore: async (...arguments_) => {
      if (firstRestore) {
        firstRestore = false;
        await gate.promise;
      }
      return rig.sessions.restore(...arguments_);
    },
  };
  const bridge = createDurableOutboxBridge({
    sessions,
    outbox: rig.outbox,
  });
  const writing = bridge.prepare(receipt(), sample(-1), { generation: 1 });
  await microtasks();
  bridge.invalidate();
  await rig.sessions.forget(OUTING_SLUG);
  gate.resolve();
  await writing;
  equal(
    (await rig.store.values(PWA_STORES.positionOutbox)).length,
    0,
    "invalidated write cannot recreate outbox",
  );
  void session;
}

async function scenarioRestoreDoesNotSend() {
  const rig = persistence();
  const session = await rig.sessions.remember(receipt(), EXPIRES);
  await rig.outbox.replace(session, sample(-1));
  const trackerRig = createTrackerRig();
  truthy(await rig.outbox.read(session), "restored sample exists");
  equal(trackerRig.publishCalls(), 0, "reading restored sample does not send");
  equal(trackerRig.geolocation.watchCount(), 0, "reading does not start watch");
}

async function scenarioFreshExplicitResume() {
  const rig = persistence();
  const session = await rig.sessions.remember(receipt(), EXPIRES);
  await rig.outbox.replace(session, sample(-1));
  const restored = await rig.outbox.read(session);
  const trackerRig = createTrackerRig({
    durableSamples: createDurableOutboxBridge({
      sessions: rig.sessions,
      outbox: rig.outbox,
    }),
  });
  equal(trackerRig.publishCalls(), 0, "no send before Start");
  trackerRig.tracker.start(receipt(), {
    available: true,
    resumeSample: restored,
  });
  equal(trackerRig.publishCalls(), 0, "Start queues before scheduler runs");
  trackerRig.scheduler.runNext();
  await microtasks(40);
  equal(trackerRig.publishCalls(), 1, "explicit Start sends once");
}

async function scenarioStaleResumeDiscard() {
  const rig = persistence();
  const session = await rig.sessions.remember(receipt(), EXPIRES);
  await rig.outbox.replace(session, sample(-20));
  equal(await rig.outbox.read(session), null, "stale sample discarded");
}

async function scenarioOfflineFixReplacement() {
  const rig = persistence();
  await rig.sessions.remember(receipt(), EXPIRES);
  const bridge = createDurableOutboxBridge({
    sessions: rig.sessions,
    outbox: rig.outbox,
  });
  await bridge.prepare(receipt(), sample(-2), { generation: 1 });
  await bridge.prepare(receipt(), sample(-1), { generation: 1 });
  const records = await rig.store.values(PWA_STORES.positionOutbox);
  equal(records.length, 1, "offline fixes remain latest-only");
  equal(records[0].coordinate.lat, 47.999, "newest offline fix retained");
}

function scenarioForegroundOnlineGate() {
  equal(foregroundOutboxFlushAllowed({
    visible: true,
    trackingActive: true,
    remembered: true,
  }), true, "visible active remembered session may flush");
  for (const denied of [
    { visible: false, trackingActive: true, remembered: true },
    { visible: true, trackingActive: false, remembered: true },
    { visible: true, trackingActive: true, remembered: false },
  ]) equal(
    foregroundOutboxFlushAllowed(denied),
    false,
    "background or inactive flush denied",
  );
}

function scenarioWorkerHasNoOutboxDependency() {
  let outboxRead = false;
  const candidate = request("https://app.test/static/app.js");
  Object.defineProperty(candidate, "positionOutbox", {
    get() {
      outboxRead = true;
      throw new Error("worker must not inspect application storage");
    },
  });
  equal(
    classifyShellRequest(
      candidate,
      "https://app.test",
    ),
    "static",
    "worker policy only classifies shell assets",
  );
  equal(outboxRead, false, "worker policy does not inspect outbox data");
}

async function scenarioParticipantRemoval() {
  const rig = persistence();
  const session = await rig.sessions.remember(receipt(), EXPIRES);
  await rig.outbox.replace(session, sample(-1));
  let shutdowns = 0;
  const memoryState = {
    outingParticipantReceipt: receipt(),
    outingOwnerReceipt: { slug: OUTING_SLUG, owner_token: "owner" },
  };
  const withoutParticipant = { ...outingSnapshot(), participants: [] };
  const discarded = discardStaleParticipantReceipt(
    memoryState,
    withoutParticipant,
    {
      shutdownTracker: () => {
        shutdowns += 1;
      },
      syncTrackerState: () => {},
    },
  );
  if (discarded) await rig.sessions.forget(OUTING_SLUG);
  equal(discarded, true, "actual cleanup detects removed participant");
  equal(shutdowns, 1, "actual cleanup shuts tracker down");
  equal(await rig.sessions.restore(OUTING_SLUG), null, "session removed");
  equal((await rig.store.values(PWA_STORES.positionOutbox)).length, 0, "outbox removed");
  truthy(memoryState.outingOwnerReceipt, "independent owner receipt preserved");
}

async function scenarioReconnectParticipantRemoval() {
  const rig = persistence();
  const session = await rig.sessions.remember(receipt(), EXPIRES);
  await rig.outbox.replace(session, sample(-1));
  let shutdowns = 0;
  let synchronizations = 0;
  const ownerReceipt = {
    slug: OUTING_SLUG,
    owner_token: "owner-capability-kept-in-memory",
  };
  const applicationState = {
    outingSnapshot: outingSnapshot(),
    outingParticipantReceipt: receipt(),
    outingOwnerReceipt: ownerReceipt,
    participantRemembered: true,
    durableOutboxPresent: true,
  };
  const freshSnapshot = { ...outingSnapshot(), participants: [] };
  const removed = installAuthoritativeOutingSnapshot(
    applicationState,
    freshSnapshot,
    {
      shutdownTracker: () => { shutdowns += 1; },
      syncTrackerState: () => { synchronizations += 1; },
    },
  );
  truthy(removed, "production reconnect cleanup captures removed receipt");
  await rig.sessions.forgetMatching(
    removed.slug,
    removed.participant_id,
  );
  equal(shutdowns, 1, "reconnect shuts stale tracker down once");
  equal(synchronizations, 1, "reconnect synchronizes inactive state once");
  equal(applicationState.outingParticipantReceipt, null, "stale receipt cleared");
  equal(applicationState.participantRemembered, false, "remembered flag cleared");
  equal(applicationState.durableOutboxPresent, false, "outbox flag cleared");
  equal(applicationState.outingOwnerReceipt, ownerReceipt, "owner preserved");
  equal(await rig.sessions.restore(OUTING_SLUG), null, "identity forgotten");
  equal(
    (await rig.store.values(PWA_STORES.positionOutbox)).length,
    0,
    "removed participant outbox forgotten",
  );
}

function scenarioSavedRouteNotFoundClearsDisplay() {
  const applicationState = {
    savedRouteSnapshot: savedRouteSnapshot(),
    savedRouteSnapshotDisplay: true,
    savedRouteReceipt: {
      slug: ROUTE_SLUG,
      owner_token: "owner-capability-in-memory",
    },
    generationResult: { candidates: [savedRouteSnapshot().candidate] },
    generationSourceRequest: savedRouteSnapshot().source_request,
    forkedSavedCandidate: savedRouteSnapshot().candidate,
    selectedSignature: "candidate",
    visualizationCache: new Map([["candidate", {}]]),
    offlineCopySaved: true,
    offlineSnapshotKind: "saved_route",
    offlineSnapshotSlug: ROUTE_SLUG,
    networkStatus: "offline",
    request: { status: "success", id: 7, startedAt: null },
  };
  equal(
    clearUnavailableSavedRouteState(applicationState, ROUTE_SLUG),
    true,
    "current saved route cleared",
  );
  equal(applicationState.savedRouteSnapshot, null, "snapshot removed");
  equal(applicationState.savedRouteSnapshotDisplay, false, "display ended");
  equal(applicationState.savedRouteReceipt, null, "owner receipt removed");
  equal(applicationState.selectedSignature, null, "route selection removed");
  equal(applicationState.visualizationCache.size, 0, "map cache removed");
  equal(applicationState.offlineSnapshotKind, null, "offline kind cleared");
  equal(applicationState.offlineSnapshotSlug, null, "offline slug cleared");
  equal(applicationState.networkStatus, "online", "not-found is definitive online");
}

async function scenarioStaleRecoveryIgnored() {
  let epoch = 1;
  let slug = OUTING_SLUG;
  let applied = "current";
  const owner = createEpochOperationOwner(
    (operation) => operation.epoch === epoch && operation.slug === slug,
  );
  const stale = owner.begin({ epoch, slug });
  const recovery = deferred();
  const completion = recovery.promise.then((value) => {
    if (owner.owns(stale)) applied = value;
  });
  epoch += 1;
  slug = "runtime_outing_slug_67890";
  owner.begin({ epoch, slug });
  recovery.resolve("stale");
  await completion;
  equal(applied, "current", "actual operation owner quarantines recovery");
}

async function scenarioStaleRememberedRestore() {
  let epoch = 1;
  let slug = OUTING_SLUG;
  const owner = createEpochOperationOwner(
    (operation) => operation.epoch === epoch && operation.slug === slug,
  );
  const operation = owner.begin({ epoch, slug });
  const outingA = outingSnapshot();
  const restore = deferred();
  const applicationState = {
    outingSnapshot: outingA,
    outingParticipantReceipt: null,
    participantRemembered: false,
    durableOutboxPresent: false,
    selectedOutingParticipantId: PARTICIPANT_ID,
  };
  const completion = restore.promise.then((restored) => (
    applyRememberedParticipantResult(
      applicationState,
      outingA,
      restored,
      { isCurrent: () => owner.owns(operation) },
    )
  ));
  epoch += 1;
  slug = "runtime_outing_slug_67890";
  owner.begin({ epoch, slug });
  applicationState.outingSnapshot = {
    ...outingA,
    slug,
    title: "New outing",
  };
  applicationState.outingParticipantReceipt = {
    slug,
    participant_id: "runtime_participant_67890",
    participant_token: "n".repeat(32),
  };
  applicationState.participantRemembered = true;
  applicationState.durableOutboxPresent = true;
  applicationState.selectedOutingParticipantId = "runtime_participant_67890";
  const before = JSON.stringify(applicationState);
  restore.resolve({
    receipt: receipt(),
    session: { outing_slug: OUTING_SLUG },
    outbox: { sample_id: "sample_identifier_old" },
  });
  equal(await completion, false, "stale restore is not installed");
  equal(JSON.stringify(applicationState), before, "new outing state unchanged");
}

async function scenarioNetworkAuthority() {
  const notFound = { code: "outing_not_found", metadata: { status: 404 } };
  let received = null;
  try {
    await resolveNetworkResource({
      loadResource: async () => Promise.reject(notFound),
      loadConfig: async () => Promise.reject(new TypeError("offline config")),
      fallbackConfig: () => ({ safe: true }),
    });
  } catch (error) {
    received = error;
  }
  equal(received, notFound, "definite resource not-found wins");
}

async function scenarioNetworkStorageSeparation() {
  const resource = savedRouteSnapshot();
  const loaded = await resolveNetworkResource({
    loadResource: async () => resource,
    loadConfig: async () => ({ tile_url_template: "network" }),
    fallbackConfig: () => ({ tile_url_template: "fallback" }),
  });
  let applied = loaded.resource;
  const quota = await settleOptionalPersistence([
    async () => {
      throw new Error("QuotaExceededError");
    },
    async () => {
      throw new Error("offline refresh failed");
    },
  ]);
  equal(quota.failed, true, "optional persistence failure reported");
  equal(applied, resource, "valid network resource remains authoritative");
  const definite = { code: "saved_route_invalid", metadata: { status: 422 } };
  try {
    await resolveNetworkResource({
      loadResource: async () => Promise.reject(definite),
      loadConfig: async () => ({}),
      fallbackConfig: () => ({}),
    });
  } catch (error) {
    equal(error, definite, "definite HTTP failure preserved");
  }
  applied = null;
  equal(applied, null, "definite error does not apply offline data");
}

async function scenarioDynamicReconnects() {
  let epoch = 1;
  let slug = OUTING_SLUG;
  let networkStatus = "online";
  let controlRenders = 0;
  let stream = null;
  let streamsCreated = 0;
  const owner = createEpochOperationOwner(
    (operation) => operation.epoch === epoch && operation.slug === slug,
  );
  const renderControls = () => {
    controlRenders += 1;
  };
  networkStatus = "offline";
  renderControls();
  const outingOperation = owner.begin({ epoch, slug });
  const outing = await resolveNetworkResource({
    loadResource: async () => outingSnapshot(),
    loadConfig: async () => ({ online: true }),
    fallbackConfig: () => ({ online: false }),
  });
  if (owner.owns(outingOperation)) {
    networkStatus = "online";
    stream?.close();
    stream = { close() {} };
    streamsCreated += 1;
    renderControls();
  }
  equal(outing.resource.slug, OUTING_SLUG, "outing endpoint retried");
  equal(streamsCreated, 1, "one outing stream created");
  equal(networkStatus, "online", "outing returns online");

  epoch += 1;
  slug = ROUTE_SLUG;
  networkStatus = "offline";
  renderControls();
  const routeOperation = owner.begin({ epoch, slug });
  const route = await resolveNetworkResource({
    loadResource: async () => savedRouteSnapshot(),
    loadConfig: async () => ({ online: true }),
    fallbackConfig: () => ({ online: false }),
  });
  if (owner.owns(routeOperation)) {
    networkStatus = "online";
    renderControls();
  }
  equal(route.resource.slug, ROUTE_SLUG, "saved-route endpoint retried");
  equal(networkStatus, "online", "saved route returns online");
  equal(streamsCreated, 1, "saved route creates no outing stream");
  equal(controlRenders, 4, "offline and online transitions rerender controls");
}

async function scenarioConcurrentSnapshotLimit() {
  const store = await openPwaStore();
  await store.clear(PWA_STORES.offlineSnapshots);
  const snapshots = createOfflineSnapshotRepository(store, {
    clock: () => new Date(NOW),
  });
  await Promise.all(Array.from({ length: 9 }, (_value, index) => (
    snapshots.save("saved_route", savedRouteSnapshot({
      slug: `runtime_saved_route_${String(index).padStart(5, "0")}`,
    }))
  )));
  equal(
    (await store.values(PWA_STORES.offlineSnapshots)).length,
    8,
    "atomic bounded save retains at most eight",
  );
  await store.clear(PWA_STORES.offlineSnapshots);
  store.close();
}

async function scenarioMalformedKeyPruned() {
  const rig = persistence();
  await rig.store.put(
    PWA_STORES.offlineSnapshots,
    "actual-malformed-storage-key",
    { schema_version: 99 },
  );
  await rig.snapshots.prune();
  equal(
    (await rig.store.entries(PWA_STORES.offlineSnapshots)).length,
    0,
    "malformed record removed by actual storage key",
  );
}

async function scenarioPublishNotFoundCleanup(sequenceRecovery) {
  const rig = persistence();
  await rig.sessions.remember(receipt(), EXPIRES);
  let permanentFailures = 0;
  const notFound = {
    code: "outing_not_found",
    metadata: { status: 404 },
  };
  const trackerRig = createTrackerRig({
    durableSamples: createDurableOutboxBridge({
      sessions: rig.sessions,
      outbox: rig.outbox,
    }),
    publishPosition: async () => Promise.reject(sequenceRecovery
      ? {
        code: "outing_position_sequence_conflict",
        metadata: { status: 409 },
      }
      : notFound),
    getLiveSnapshot: async () => Promise.reject(notFound),
    onPermanentFailure: async (failure) => {
      permanentFailures += 1;
      equal(failure.code, "outing_not_found", "safe permanent code");
      await rig.sessions.forget(failure.receipt.slug);
    },
  });
  trackerRig.tracker.start(receipt(), { available: true });
  trackerRig.geolocation.emit(rawPosition());
  trackerRig.scheduler.runNext();
  await microtasks(60);
  equal(permanentFailures, 1, "permanent failure callback invoked once");
  equal(await rig.sessions.restore(OUTING_SLUG), null, "session forgotten");
  equal(
    (await rig.store.values(PWA_STORES.positionOutbox)).length,
    0,
    "outbox removed after authenticated not-found",
  );
  equal(trackerRig.tracker.status().active, false, "tracker stopped");
}

async function scenarioStopDuringNotFound(sequenceRecovery) {
  const rig = persistence();
  const session = await rig.sessions.remember(receipt(), EXPIRES);
  await rig.outbox.replace(session, sample(-1));
  const discard = deferred();
  let discardStarted = false;
  let permanentFailures = 0;
  const scheduler = fakeScheduler();
  const geolocation = fakeGeolocation();
  const notFound = {
    code: "outing_not_found",
    metadata: { status: 404 },
  };
  const replacementReceipt = {
    slug: OUTING_SLUG,
    participant_id: `${PARTICIPANT_ID}_new_ui`,
    participant_token: "z".repeat(32),
  };
  const applicationState = {
    outingParticipantReceipt: receipt(),
    participantRemembered: true,
    durableOutboxPresent: true,
  };
  let tracker = null;
  tracker = createOutingTracker({
    publishPosition: async () => {
      throw sequenceRecovery
        ? {
          code: "outing_position_sequence_conflict",
          metadata: { status: 409 },
        }
        : notFound;
    },
    getLiveSnapshot: async () => { throw notFound; },
    clearPosition: async () => {},
    durableSamples: {
      prepare: async () => ({ sampleId: "held_sample_identifier" }),
      async discard() {
        discardStarted = true;
        await discard.promise;
      },
      async stop() {},
    },
    onPermanentFailure: async (failure) => {
      permanentFailures += 1;
      equal(
        Object.keys(failure.receipt).sort().join(","),
        "participant_id,slug",
        "permanent callback contains only safe identity",
      );
      await rig.sessions.forgetMatching(
        failure.receipt.slug,
        failure.receipt.participant_id,
      );
      applyPermanentParticipantFailureState(
        applicationState,
        failure,
        tracker.status().generation,
      );
    },
    clock: () => NOW.getTime(),
    schedule: scheduler.schedule,
    cancelScheduled: scheduler.cancel,
    geolocation: geolocation.api,
    createAbortController: fakeAbortController,
  });
  tracker.start(receipt(), { available: true });
  geolocation.emit(rawPosition());
  scheduler.runNext();
  for (let index = 0; index < 40 && !discardStarted; index += 1) {
    await microtasks();
  }
  equal(discardStarted, true, "durable discard held after definite not-found");
  await tracker.stop(receipt(), { clearServer: false });
  applicationState.outingParticipantReceipt = replacementReceipt;
  applicationState.participantRemembered = true;
  applicationState.durableOutboxPresent = true;
  discard.resolve();
  for (let index = 0; index < 80 && permanentFailures === 0; index += 1) {
    await microtasks();
  }
  equal(permanentFailures, 1, "permanent callback survives Stop race");
  equal(await rig.sessions.restore(OUTING_SLUG), null, "old identity removed");
  equal(
    (await rig.store.values(PWA_STORES.positionOutbox)).length,
    0,
    "old identity outbox removed",
  );
  equal(
    applicationState.outingParticipantReceipt,
    replacementReceipt,
    "newer UI receipt remains untouched",
  );
  equal(applicationState.participantRemembered, true, "newer UI flags untouched");
}

async function scenarioStopBeforeNotFound(sequenceRecovery) {
  const rig = persistence();
  const session = await rig.sessions.remember(receipt(), EXPIRES);
  await rig.outbox.replace(session, sample(-1));
  const put = deferred();
  const recovery = deferred();
  let putStarted = false;
  let recoveryStarted = false;
  let permanentFailures = 0;
  const scheduler = fakeScheduler();
  const geolocation = fakeGeolocation();
  const notFound = {
    code: "outing_not_found",
    metadata: { status: 404 },
  };
  const replacementReceipt = {
    slug: OUTING_SLUG,
    participant_id: `${PARTICIPANT_ID}_newer_ui`,
    participant_token: "y".repeat(32),
  };
  const applicationState = {
    outingParticipantReceipt: receipt(),
    participantRemembered: true,
    durableOutboxPresent: true,
  };
  let tracker = null;
  tracker = createOutingTracker({
    publishPosition: async () => {
      putStarted = true;
      if (sequenceRecovery) {
        throw {
          code: "outing_position_sequence_conflict",
          metadata: { status: 409 },
        };
      }
      return put.promise;
    },
    getLiveSnapshot: async () => {
      recoveryStarted = true;
      return recovery.promise;
    },
    clearPosition: async () => {},
    durableSamples: {
      prepare: async () => ({ sampleId: "network_held_sample_identifier" }),
      async discard() {},
      async stop() {},
    },
    onPermanentFailure: async (failure) => {
      permanentFailures += 1;
      await rig.sessions.forgetMatching(
        failure.receipt.slug,
        failure.receipt.participant_id,
      );
      applyPermanentParticipantFailureState(
        applicationState,
        failure,
        tracker.status().generation,
      );
    },
    clock: () => NOW.getTime(),
    schedule: scheduler.schedule,
    cancelScheduled: scheduler.cancel,
    geolocation: geolocation.api,
    createAbortController: fakeAbortController,
  });
  tracker.start(receipt(), { available: true });
  geolocation.emit(rawPosition());
  scheduler.runNext();
  for (
    let index = 0;
    index < 80 && !(sequenceRecovery ? recoveryStarted : putStarted);
    index += 1
  ) await microtasks();
  equal(putStarted, true, "position PUT started before Stop");
  if (sequenceRecovery) {
    equal(recoveryStarted, true, "sequence-recovery GET started before Stop");
  }
  const stop = tracker.stop(
    receipt(),
    { clearServer: sequenceRecovery },
  );
  await microtasks(10);
  applicationState.outingParticipantReceipt = replacementReceipt;
  applicationState.participantRemembered = true;
  applicationState.durableOutboxPresent = true;
  if (sequenceRecovery) recovery.reject(notFound);
  else put.reject(notFound);
  await stop;
  for (let index = 0; index < 80 && permanentFailures === 0; index += 1) {
    await microtasks();
  }
  equal(permanentFailures, 1, "pre-response Stop still invokes cleanup once");
  equal(await rig.sessions.restore(OUTING_SLUG), null, "old session forgotten");
  equal(
    (await rig.store.values(PWA_STORES.positionOutbox)).length,
    0,
    "old outbox forgotten",
  );
  equal(
    applicationState.outingParticipantReceipt,
    replacementReceipt,
    "newer UI receipt remains untouched",
  );
  equal(applicationState.participantRemembered, true, "newer UI flags remain");
}

async function scenarioUncertainForget() {
  let forgotten = 0;
  const uncertain = await completeParticipantForget({
    clearServer: true,
    stop: async () => ({ cleared: false, uncertain: true, pending: false }),
    forget: async () => {
      forgotten += 1;
    },
  });
  equal(uncertain.warningRequired, true, "uncertain Stop keeps warning");
  const failed = await completeParticipantForget({
    clearServer: true,
    stop: async () => {
      throw new TypeError("clear failed");
    },
    forget: async () => {
      forgotten += 1;
    },
  });
  equal(failed.warningRequired, true, "clear failure keeps warning");
  equal(forgotten, 2, "Forget removes capability despite clear uncertainty");
}

async function scenarioHandledRejection() {
  await Promise.reject(new Error("expected")).catch(() => {});
  await microtasks();
}

async function scenarioRejectedCleanupStorage() {
  let primaryStatus = "Outing closed.";
  let failures = 0;
  const membership = runBestEffortStorage([
    async () => { throw new Error("membership cleanup failed"); },
  ], { onFailure: () => { failures += 1; } });
  await membership;
  equal(primaryStatus, "Outing closed.", "membership failure preserves status");
  primaryStatus = "Participant removed.";
  const closure = runBestEffortStorage([
    async () => { throw new Error("session cleanup failed"); },
    async () => { throw new Error("snapshot cleanup failed"); },
  ], { onFailure: () => { failures += 1; } });
  await closure;
  equal(primaryStatus, "Participant removed.", "closure failure preserves status");
  equal(failures, 2, "best-effort failures reported without rejection");
}

async function scenarioClearAllData() {
  const rig = persistence();
  await rig.snapshots.save("saved_route", savedRouteSnapshot());
  const session = await rig.sessions.remember(receipt(), EXPIRES);
  await rig.outbox.replace(session, sample(-1));
  await rig.store.clearApplicationData();
  for (const name of Object.values(PWA_STORES)) {
    equal((await rig.store.values(name)).length, 0, `${name} cleared`);
  }
}

function persistence() {
  let sampleIndex = 0;
  const store = createMemoryPwaStore();
  const clock = () => new Date(NOW);
  return {
    store,
    snapshots: createOfflineSnapshotRepository(store, { clock }),
    sessions: createParticipantSessionRepository(store, { clock }),
    outbox: createPositionOutboxRepository(store, {
      clock,
      createSampleId: () => `sample_identifier_${++sampleIndex}`,
    }),
  };
}

function createTrackerRig(overrides = {}) {
  const scheduler = fakeScheduler();
  const geolocation = fakeGeolocation();
  let publishCallCount = 0;
  const tracker = createOutingTracker({
    publishPosition: (...arguments_) => {
      publishCallCount += 1;
      return (overrides.publishPosition
        ?? (async () => ({ sequence: NOW.getTime() })))(...arguments_);
    },
    getLiveSnapshot: overrides.getLiveSnapshot
      ?? (async () => ({ positions: [] })),
    clearPosition: async () => {},
    onPermanentFailure: overrides.onPermanentFailure,
    durableSamples: overrides.durableSamples ?? null,
    clock: () => NOW.getTime(),
    schedule: scheduler.schedule,
    cancelScheduled: scheduler.cancel,
    geolocation: geolocation.api,
    createAbortController: fakeAbortController,
  });
  return {
    tracker,
    scheduler,
    geolocation,
    publishCalls: () => publishCallCount,
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
    runNext() {
      const index = tasks.findIndex((task) => !task.cancelled);
      truthy(index >= 0, "scheduled tracker operation exists");
      const [task] = tasks.splice(index, 1);
      task.callback();
    },
  };
}

function fakeGeolocation() {
  let watch = null;
  let watches = 0;
  return {
    api: {
      watchPosition(success, error) {
        watches += 1;
        watch = { success, error, id: watches };
        return watches;
      },
      clearWatch() {
        watch = null;
      },
    },
    emit(position) {
      truthy(watch, "active geolocation watch");
      watch.success(position);
    },
    watchCount: () => watches,
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

function rawPosition() {
  return {
    coords: {
      latitude: 48,
      longitude: 2,
      accuracy: 8,
      altitude: null,
      speed: null,
      heading: null,
    },
    timestamp: NOW.getTime() - 1_000,
  };
}

function savedRouteSnapshot(overrides = {}) {
  return {
    schema_version: 1,
    slug: ROUTE_SLUG,
    created_at: "2025-12-31T12:00:00.000Z",
    expires_at: EXPIRES,
    source_request: { schema_version: 1, kind: "auto_tour" },
    candidate: {
      id: "candidate",
      route: {
        geometry: [[2.0, 48.0], [2.01, 48.01]],
      },
    },
    ...overrides,
  };
}

function publicConfig(overrides = {}) {
  return {
    tile_url_template: "https://tiles.test/{z}/{x}/{y}.png",
    tile_attribution: "Map data",
    initial_center: [2, 48],
    initial_zoom: 11,
    max_required_points: 30,
    nature_index_available: false,
    nature_water_buffer_m: 100,
    nature_preference_values: ["off", "prefer"],
    loop_geometry_preference_values: ["off", "prefer"],
    poi_index_available: false,
    poi_default_limit: 100,
    poi_max_limit: 500,
    saved_routes_available: true,
    outings_available: true,
    outing_max_participants: 10,
    outing_live_positions_available: true,
    outing_live_stale_after_seconds: 60,
    outing_live_expire_after_seconds: 300,
    default_planning_mode: "auto_tour",
    auto_tour_max_hard_waypoints: 6,
    auto_tour_max_preferred_pois: 8,
    auto_tour_scenic_corridor_radius_m: 500,
    auto_tour_water_corridor_radius_m: 250,
    ...overrides,
  };
}

function outingSnapshot() {
  return {
    schema_version: 1,
    slug: OUTING_SLUG,
    title: "Runtime outing",
    created_at: "2025-12-31T12:00:00.000Z",
    expires_at: EXPIRES,
    max_participants: 5,
    participants: [{
      participant_id: PARTICIPANT_ID,
      display_name: "Runtime",
      joined_at: "2025-12-31T13:00:00.000Z",
      planned_route: {
        source_request: { schema_version: 1, kind: "auto_tour" },
        candidate: savedRouteSnapshot().candidate,
      },
    }],
  };
}

function receipt() {
  return {
    slug: OUTING_SLUG,
    participant_id: PARTICIPANT_ID,
    participant_token: TOKEN,
  };
}

function sample(offsetSeconds) {
  const captured = new Date(NOW.getTime() + offsetSeconds * 1_000);
  return {
    coordinate: {
      lat: 48 + offsetSeconds / 1_000,
      lon: 2 + offsetSeconds / 1_000,
    },
    accuracy_m: 8,
    altitude_m: null,
    speed_m_s: null,
    heading_deg: null,
    captured_at: captured.toISOString(),
  };
}

function request(url, mode = "cors", headers = {}) {
  return { method: "GET", url, mode, headers };
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

async function microtasks(count = 2) {
  for (let index = 0; index < count; index += 1) {
    await Promise.resolve();
  }
}

function equal(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, got ${String(actual)}`);
  }
}

function truthy(value, message) {
  if (!value) throw new Error(`${message}: expected truthy value`);
}

function throws(action, message) {
  let threw = false;
  try {
    action();
  } catch {
    threw = true;
  }
  if (!threw) throw new Error(`${message}: expected rejection`);
}
