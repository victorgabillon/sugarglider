const PUBLICATION_INTERVAL_MS = 5_000;
const INITIAL_RETRY_MS = 1_000;
const MAXIMUM_RETRY_MS = 30_000;
const STOP_PUBLISH_WAIT_MS = 10_000;
const WATCH_OPTIONS = {
  enableHighAccuracy: true,
  maximumAge: 10_000,
  timeout: 30_000,
};

export function normalizeGeolocationPosition(position) {
  const latitude = position?.coords?.latitude;
  const longitude = position?.coords?.longitude;
  const accuracy = position?.coords?.accuracy;
  const timestamp = position?.timestamp;
  if (
    !boundedPrimitiveNumber(latitude, -90, 90)
    || !boundedPrimitiveNumber(longitude, -180, 180)
    || !boundedPrimitiveNumber(accuracy, 0, 10_000)
    || !primitiveFiniteNumber(timestamp)
  ) return null;
  const capturedAt = new Date(timestamp);
  if (!Number.isFinite(capturedAt.getTime())) return null;
  return {
    coordinate: { lat: latitude, lon: longitude },
    accuracy_m: accuracy,
    altitude_m: boundedOptional(position.coords.altitude, -1_000, 12_000),
    speed_m_s: boundedOptional(position.coords.speed, 0, 150),
    heading_deg: boundedOptional(
      position.coords.heading,
      0,
      360,
      true,
    ),
    captured_at: capturedAt.toISOString(),
  };
}

export function createOutingTracker({
  publishPosition,
  getLiveSnapshot,
  clearPosition,
  onStatus,
  onPublished,
  onCleared,
  clock = () => Date.now(),
  schedule = (callback, delay) => window.setTimeout(callback, delay),
  cancelScheduled = (timer) => window.clearTimeout(timer),
  geolocation = browserGeolocation(),
  createAbortController = () => new AbortController(),
  stopPublishWaitMs = STOP_PUBLISH_WAIT_MS,
} = {}) {
  let generationCounter = 0;
  let activeGeneration = 0;
  let activeWatch = null;
  let activeReceipt = null;
  let pendingSample = null;
  let cadenceTimer = null;
  let retryTimer = null;
  let activePublish = null;
  let activeClear = null;
  let transitionOperation = null;
  let lastAcceptedSequence = -1;
  let lastPublishedAt = null;
  let retryDelayMs = INITIAL_RETRY_MS;
  let trackingStatus = "inactive";
  let clearingFailed = false;
  let sessionHasUncertainPublish = false;

  function supported() {
    return Boolean(
      geolocation
      && typeof geolocation.watchPosition === "function"
      && typeof geolocation.clearWatch === "function"
    );
  }

  function start(receipt, { available, currentPosition = null } = {}) {
    if (transitionOperation || currentWatchActive()) return false;
    const generation = advanceGeneration();
    resetForNewSession(generation);
    if (!available) {
      updateStatus(
        generation,
        "unsupported",
        "Live position sharing is unavailable.",
      );
      return false;
    }
    if (!supported()) {
      updateStatus(
        generation,
        "unsupported",
        "Browser geolocation is unavailable on this device.",
      );
      return false;
    }
    if (!validReceipt(receipt)) {
      updateStatus(
        generation,
        "inactive",
        "A current participant receipt is required.",
      );
      return false;
    }

    activeReceipt = receipt;
    lastAcceptedSequence = Number.isSafeInteger(currentPosition?.sequence)
      ? currentPosition.sequence
      : -1;
    const transition = { generation, kind: "start" };
    transitionOperation = transition;
    updateStatus(
      generation,
      "starting",
      "Waiting for location permission",
    );
    const watch = { generation, id: null };
    activeWatch = watch;
    try {
      watch.id = geolocation.watchPosition(
        (position) => receivePosition(generation, position),
        (error) => receiveError(generation, error),
        WATCH_OPTIONS,
      );
      updateStatus(generation, "waiting", "Waiting for a location fix");
      return true;
    } catch {
      if (ownsGeneration(generation)) {
        activeWatch = null;
        activeReceipt = null;
        updateStatus(
          generation,
          "unsupported",
          "Browser geolocation is unavailable.",
        );
      }
      return false;
    } finally {
      if (transitionOperation === transition) transitionOperation = null;
    }
  }

  async function stop(
    receipt,
    { clearServer = true, keepalive = false } = {},
  ) {
    if (transitionOperation) return { cleared: false, pending: true };
    const publish = activePublish;
    const generation = invalidateLocalSession({ abortPublish: false });
    const transition = { generation, kind: "stop" };
    transitionOperation = transition;
    if (!clearServer || !validReceipt(receipt)) {
      activeReceipt = null;
      clearingFailed = false;
      finishTransition(transition);
      updateStatus(generation, "inactive", "Position sharing stopped");
      return { cleared: false, pending: false };
    }

    updateStatus(generation, "stopping", "Stopping position sharing");
    const publishOutcome = await waitForPublishOutcome(publish, generation);
    if (!ownsTransition(transition)) {
      return { cleared: false, pending: false, stale: true };
    }

    const clear = beginClear(generation, receipt, { keepalive });
    try {
      await clear.promise;
      if (!ownsClear(clear) || !ownsTransition(transition)) {
        return { cleared: false, pending: false, stale: true };
      }
      activeReceipt = null;
      if (
        publishOutcome !== "definite"
        || sessionHasUncertainPublish
      ) {
        clearingFailed = true;
        updateStatus(
          generation,
          "stop_failed",
          "Stop failed — last position may remain until expiry",
        );
        return {
          cleared: false,
          pending: false,
          uncertain: true,
        };
      }
      clearingFailed = false;
      onCleared?.(receipt.participant_id);
      updateStatus(generation, "inactive", "Position sharing stopped");
      return { cleared: true, pending: false };
    } catch (error) {
      if (!ownsClear(clear) || !ownsTransition(transition)) {
        return { cleared: false, pending: false, stale: true };
      }
      activeReceipt = null;
      clearingFailed = true;
      updateStatus(
        generation,
        "stop_failed",
        "Stop failed — last position may remain until expiry",
        error,
      );
      return { cleared: false, pending: false, error };
    } finally {
      if (activeClear === clear) activeClear = null;
      finishTransition(transition);
    }
  }

  function shutdown() {
    const generation = invalidateLocalSession({
      abortPublish: true,
      abortClear: true,
    });
    activeReceipt = null;
    activePublish = null;
    activeClear = null;
    transitionOperation = null;
    clearingFailed = false;
    updateStatus(generation, "inactive", "Position sharing stopped");
  }

  function pagehide(receipt) {
    const wasActive = currentWatchActive();
    const generation = invalidateLocalSession({
      abortPublish: true,
      abortClear: true,
    });
    activeReceipt = null;
    activePublish = null;
    activeClear = null;
    transitionOperation = null;
    if (!wasActive || !validReceipt(receipt)) return;

    const clear = beginClear(
      generation,
      receipt,
      { keepalive: true, useAbortSignal: false },
    );
    void clear.promise
      .catch(() => {})
      .finally(() => {
        if (ownsClear(clear)) activeClear = null;
      });
  }

  function online() {
    const generation = activeGeneration;
    if (
      currentWatchActive()
      && pendingForGeneration(generation)
      && !publishForGeneration(generation)
    ) {
      cancelRetryTimer();
      scheduleCadence(generation, 0);
    }
  }

  function status() {
    return {
      status: trackingStatus,
      active: currentWatchActive(),
      transitionPending: transitionOperation !== null,
      clearingFailed,
      lastPublishedAt,
      hasPendingSample: pendingForGeneration(activeGeneration),
      requestInFlight: publishForGeneration(activeGeneration),
      generation: activeGeneration,
      retryDelayMs,
    };
  }

  function receivePosition(generation, position) {
    if (!ownsSamplingGeneration(generation)) return;
    const sample = normalizeGeolocationPosition(position);
    if (!sample) {
      updateStatus(
        generation,
        "temporary_error",
        "Location temporarily unavailable",
      );
      return;
    }
    pendingSample = {
      generation,
      value: { ...sample, conflictRetried: false },
    };
    updateStatus(generation, "sharing", "Sharing current position");
    if (!retryForGeneration(generation)) {
      scheduleCadence(generation, publicationDelay());
    }
  }

  function receiveError(generation, error) {
    if (!ownsSamplingGeneration(generation)) return;
    if (error?.code === 1) {
      invalidateLocalSession({ abortPublish: true });
      activeReceipt = null;
      updateStatus(
        activeGeneration,
        "permission_denied",
        "Permission denied — location permission is required",
      );
    } else if (error?.code === 2) {
      updateStatus(
        generation,
        "temporary_error",
        "Location temporarily unavailable",
      );
    } else {
      updateStatus(generation, "waiting", "Waiting for a location fix");
    }
  }

  function scheduleCadence(generation, delay) {
    if (
      !ownsSamplingGeneration(generation)
      || publishForGeneration(generation)
      || cadenceForGeneration(generation)
      || retryForGeneration(generation)
      || !pendingForGeneration(generation)
    ) return;
    const operation = { generation, timer: null };
    operation.timer = schedule(() => {
      if (cadenceTimer === operation) cadenceTimer = null;
      if (!ownsSamplingGeneration(generation)) return;
      beginPublish(generation);
    }, Math.max(0, delay));
    cadenceTimer = operation;
  }

  function scheduleRetry(generation) {
    if (
      !ownsSamplingGeneration(generation)
      || retryForGeneration(generation)
    ) return;
    cancelCadenceTimer();
    const delay = retryDelayMs;
    retryDelayMs = Math.min(retryDelayMs * 2, MAXIMUM_RETRY_MS);
    const operation = { generation, timer: null };
    operation.timer = schedule(() => {
      if (retryTimer === operation) retryTimer = null;
      if (!ownsSamplingGeneration(generation)) return;
      beginPublish(generation);
    }, delay);
    retryTimer = operation;
  }

  function beginPublish(generation) {
    if (
      !ownsSamplingGeneration(generation)
      || publishForGeneration(generation)
      || !pendingForGeneration(generation)
      || !validReceipt(activeReceipt)
    ) return;
    const pending = pendingSample;
    pendingSample = null;
    const sequence = nextSequence();
    if (sequence === null) {
      invalidateLocalSession({ abortPublish: true });
      activeReceipt = null;
      updateStatus(
        activeGeneration,
        "sequence_exhausted",
        "Position sharing stopped because its sequence limit was reached.",
      );
      return;
    }
    const sample = pending.value;
    const payload = {
      schema_version: 1,
      sequence,
      coordinate: sample.coordinate,
      accuracy_m: sample.accuracy_m,
      altitude_m: sample.altitude_m,
      speed_m_s: sample.speed_m_s,
      heading_deg: sample.heading_deg,
      captured_at: sample.captured_at,
    };
    let resolveTerminal;
    const operation = {
      generation,
      controller: createAbortController(),
      terminalPromise: new Promise((resolve) => {
        resolveTerminal = resolve;
      }),
      resolveTerminal,
      terminalSettled: false,
      promise: null,
    };
    activePublish = operation;
    operation.promise = performPublish(operation, sample, payload);
  }

  async function performPublish(operation, sample, payload) {
    let outcome = "uncertain";
    try {
      const receipt = activeReceipt;
      if (!validReceipt(receipt)) return outcome;
      const published = await publishPosition(
        receipt.slug,
        receipt.participant_id,
        receipt.participant_token,
        payload,
        { signal: operation.controller.signal },
      );
      outcome = "definite";
      settlePublishOutcome(operation, outcome);
      if (!ownsPublish(operation)) return outcome;
      if (!Number.isSafeInteger(published?.sequence)) {
        throw new Error("Published position was invalid.");
      }
      lastAcceptedSequence = published.sequence;
      lastPublishedAt = clock();
      retryDelayMs = INITIAL_RETRY_MS;
      onPublished?.(published, lastPublishedAt);
      updateStatus(
        operation.generation,
        "sharing",
        "Sharing current position",
      );
      return outcome;
    } catch (error) {
      outcome = definiteHttpOutcome(error) ? "definite" : "uncertain";
      settlePublishOutcome(operation, outcome);
      if (!ownsPublish(operation)) return outcome;
      if (outcome === "uncertain") sessionHasUncertainPublish = true;
      if (
        error?.code === "outing_position_sequence_conflict"
        && !sample.conflictRetried
      ) {
        await recoverSequence(operation, sample);
      } else if (transientFailure(error)) {
        retainLatestSample(operation.generation, sample);
        updateStatus(
          operation.generation,
          "retrying",
          "Live update delayed — retrying in the foreground",
        );
        scheduleRetry(operation.generation);
      } else {
        updateStatus(
          operation.generation,
          "temporary_error",
          "Location temporarily unavailable",
          error,
        );
      }
      return outcome;
    } finally {
      settlePublishOutcome(operation, outcome);
      if (activePublish === operation) activePublish = null;
      if (
        ownsSamplingGeneration(operation.generation)
        && pendingForGeneration(operation.generation)
        && !retryForGeneration(operation.generation)
      ) {
        scheduleCadence(operation.generation, publicationDelay());
      }
    }
  }

  async function recoverSequence(operation, sample) {
    if (!ownsPublish(operation) || !validReceipt(activeReceipt)) return;
    const receipt = activeReceipt;
    try {
      const snapshot = await getLiveSnapshot(receipt.slug);
      if (!ownsPublish(operation)) return;
      const current = Array.isArray(snapshot?.positions)
        ? snapshot.positions.find(
          (position) => (
            position.participant_id === receipt.participant_id
          ),
        )
        : null;
      if (Number.isSafeInteger(current?.sequence)) {
        lastAcceptedSequence = Math.max(
          lastAcceptedSequence,
          current.sequence,
        );
      }
      const latest = pendingForGeneration(operation.generation)
        ? pendingSample.value
        : sample;
      pendingSample = {
        generation: operation.generation,
        value: { ...latest, conflictRetried: true },
      };
    } catch (error) {
      if (!ownsPublish(operation)) return;
      retainLatestSample(operation.generation, sample);
      updateStatus(
        operation.generation,
        "retrying",
        "Live update delayed — retrying in the foreground",
        error,
      );
      scheduleRetry(operation.generation);
    }
  }

  function retainLatestSample(generation, sample) {
    if (!ownsSamplingGeneration(generation)) return;
    if (!pendingForGeneration(generation)) {
      pendingSample = { generation, value: sample };
    }
  }

  function beginClear(
    generation,
    receipt,
    { keepalive = false, useAbortSignal = true } = {},
  ) {
    const controller = useAbortSignal ? createAbortController() : null;
    const options = { keepalive };
    if (controller) options.signal = controller.signal;
    const operation = {
      generation,
      controller,
      promise: clearPosition(
        receipt.slug,
        receipt.participant_id,
        receipt.participant_token,
        options,
      ),
    };
    activeClear = operation;
    return operation;
  }

  async function waitForPublishOutcome(operation, generation) {
    if (!operation || operation.generation !== generation - 1) {
      return "definite";
    }
    let timeoutOperation = null;
    const timeout = new Promise((resolve) => {
      timeoutOperation = {
        generation,
        timer: schedule(() => resolve("uncertain"), stopPublishWaitMs),
      };
    });
    const outcome = await Promise.race([
      operation.terminalPromise,
      timeout,
    ]);
    if (timeoutOperation) cancelScheduled(timeoutOperation.timer);
    if (!ownsGeneration(generation)) return "uncertain";
    if (outcome === "uncertain" && !operation.terminalSettled) {
      operation.controller.abort();
    }
    return outcome;
  }

  function settlePublishOutcome(operation, outcome) {
    if (operation.terminalSettled) return;
    operation.terminalSettled = true;
    operation.resolveTerminal(outcome);
  }

  function resetForNewSession(generation) {
    clearOwnedWatch();
    cancelCadenceTimer();
    cancelRetryTimer();
    activePublish?.controller.abort();
    activeClear?.controller?.abort();
    activePublish = null;
    activeClear = null;
    transitionOperation = null;
    activeReceipt = null;
    pendingSample = null;
    lastAcceptedSequence = -1;
    lastPublishedAt = null;
    retryDelayMs = INITIAL_RETRY_MS;
    clearingFailed = false;
    sessionHasUncertainPublish = false;
    trackingStatus = "inactive";
    activeGeneration = generation;
  }

  function invalidateLocalSession({
    abortPublish = false,
    abortClear = false,
  } = {}) {
    const generation = advanceGeneration();
    clearOwnedWatch();
    pendingSample = null;
    cancelCadenceTimer();
    cancelRetryTimer();
    if (abortPublish) activePublish?.controller.abort();
    if (abortClear) activeClear?.controller?.abort();
    return generation;
  }

  function clearOwnedWatch() {
    const watch = activeWatch;
    activeWatch = null;
    if (watch && supported()) geolocation.clearWatch(watch.id);
  }

  function cancelCadenceTimer() {
    if (cadenceTimer) cancelScheduled(cadenceTimer.timer);
    cadenceTimer = null;
  }

  function cancelRetryTimer() {
    if (retryTimer) cancelScheduled(retryTimer.timer);
    retryTimer = null;
  }

  function publicationDelay() {
    if (lastPublishedAt === null) return 0;
    return Math.max(
      0,
      PUBLICATION_INTERVAL_MS - (clock() - lastPublishedAt),
    );
  }

  function nextSequence() {
    const now = Math.trunc(clock());
    if (!Number.isSafeInteger(now) || now < 0) return null;
    if (lastAcceptedSequence >= Number.MAX_SAFE_INTEGER) return null;
    return Math.max(now, lastAcceptedSequence + 1);
  }

  function advanceGeneration() {
    generationCounter += 1;
    activeGeneration = generationCounter;
    return activeGeneration;
  }

  function ownsGeneration(generation) {
    return activeGeneration === generation;
  }

  function currentWatchActive() {
    return activeWatch?.generation === activeGeneration;
  }

  function ownsSamplingGeneration(generation) {
    return ownsGeneration(generation)
      && activeWatch?.generation === generation;
  }

  function ownsPublish(operation) {
    return activePublish === operation
      && ownsSamplingGeneration(operation.generation);
  }

  function ownsClear(operation) {
    return activeClear === operation
      && ownsGeneration(operation.generation);
  }

  function ownsTransition(operation) {
    return transitionOperation === operation
      && ownsGeneration(operation.generation);
  }

  function publishForGeneration(generation) {
    return activePublish?.generation === generation;
  }

  function pendingForGeneration(generation) {
    return pendingSample?.generation === generation;
  }

  function cadenceForGeneration(generation) {
    return cadenceTimer?.generation === generation;
  }

  function retryForGeneration(generation) {
    return retryTimer?.generation === generation;
  }

  function finishTransition(operation) {
    if (transitionOperation === operation) transitionOperation = null;
  }

  function updateStatus(generation, nextStatus, message, error = null) {
    if (!ownsGeneration(generation)) return;
    trackingStatus = nextStatus;
    onStatus?.({
      status: nextStatus,
      message,
      error,
      active: currentWatchActive(),
      transitionPending: transitionOperation !== null,
      clearingFailed,
      lastPublishedAt,
      generation,
    });
  }

  return {
    start,
    stop,
    shutdown,
    pagehide,
    online,
    status,
    supported,
  };
}

function browserGeolocation() {
  return typeof navigator === "undefined" ? null : navigator.geolocation;
}

function validReceipt(receipt) {
  return typeof receipt?.slug === "string"
    && typeof receipt?.participant_id === "string"
    && typeof receipt?.participant_token === "string";
}

function primitiveFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function boundedPrimitiveNumber(
  value,
  minimum,
  maximum,
  maximumExclusive = false,
) {
  return primitiveFiniteNumber(value)
    && value >= minimum
    && (maximumExclusive ? value < maximum : value <= maximum);
}

function boundedOptional(
  value,
  minimum,
  maximum,
  maximumExclusive = false,
) {
  if (value === null || value === undefined) return null;
  return boundedPrimitiveNumber(value, minimum, maximum, maximumExclusive)
    ? value
    : null;
}

function definiteHttpOutcome(error) {
  return Number.isInteger(error?.metadata?.status);
}

function transientFailure(error) {
  const status = error?.metadata?.status;
  return !Number.isInteger(status) || status === 429 || status >= 500;
}
