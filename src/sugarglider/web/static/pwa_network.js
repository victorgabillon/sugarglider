export async function resolveNetworkResource({
  loadResource,
  loadConfig,
  loadStoredConfig = async () => null,
  fallbackConfig,
}) {
  const [resourceResult, configResult] = await Promise.allSettled([
    loadResource(),
    loadConfig(),
  ]);
  if (resourceResult.status === "rejected") {
    throw resourceResult.reason;
  }
  if (configResult.status === "fulfilled") {
    return {
      resource: resourceResult.value,
      config: configResult.value,
      configFromNetwork: true,
    };
  }
  let storedConfig = null;
  try {
    storedConfig = await loadStoredConfig();
  } catch {
    storedConfig = null;
  }
  return {
    resource: resourceResult.value,
    config: storedConfig ?? fallbackConfig(resourceResult.value),
    configFromNetwork: false,
  };
}

export async function settleOptionalPersistence(actions) {
  const results = await Promise.allSettled(
    actions.map((action) => Promise.resolve().then(action)),
  );
  return {
    failed: results.some((result) => result.status === "rejected"),
    results,
    values: results.map((result) => (
      result.status === "fulfilled" ? result.value : null
    )),
  };
}

export async function readOptionalStorage(
  read,
  { onFailure = () => {} } = {},
) {
  try {
    return await read();
  } catch (error) {
    try {
      onFailure(error);
    } catch {
      // Optional-storage reporting must not replace the primary outcome.
    }
    return null;
  }
}

export function runBestEffortStorage(
  actions,
  { onFailure = () => {} } = {},
) {
  return settleOptionalPersistence(actions).then((result) => {
    if (result.failed) {
      try {
        onFailure(result);
      } catch {
        // Optional-storage reporting is itself best effort.
      }
    }
    return result;
  });
}

export function clearUnavailableSavedRouteState(applicationState, slug) {
  if (applicationState.savedRouteSnapshot?.slug !== slug) return false;
  applicationState.savedRouteSnapshot = null;
  applicationState.savedRouteSnapshotDisplay = false;
  if (applicationState.savedRouteReceipt?.slug === slug) {
    applicationState.savedRouteReceipt = null;
  }
  applicationState.generationResult = null;
  applicationState.generationSourceRequest = null;
  applicationState.forkedSavedCandidate = null;
  applicationState.selectedSignature = null;
  applicationState.visualizationCache?.clear();
  applicationState.offlineCopySaved = false;
  if (
    applicationState.offlineSnapshotKind === "saved_route"
    && applicationState.offlineSnapshotSlug === slug
  ) {
    applicationState.offlineSnapshotKind = null;
    applicationState.offlineSnapshotSlug = null;
  }
  applicationState.networkStatus = "online";
  applicationState.request = {
    status: "idle",
    id: applicationState.request?.id ?? 0,
    startedAt: null,
  };
  return true;
}

export function applyPermanentParticipantFailureState(
  applicationState,
  failure,
  trackerGeneration,
) {
  const receipt = applicationState.outingParticipantReceipt;
  if (
    trackerGeneration !== failure?.generation
    || receipt?.slug !== failure?.receipt?.slug
    || receipt?.participant_id !== failure?.receipt?.participant_id
  ) return false;
  applicationState.participantRemembered = false;
  applicationState.durableOutboxPresent = false;
  applicationState.outingParticipantReceipt = null;
  return true;
}

export function createEpochOperationOwner(isIdentityCurrent) {
  let active = null;

  function begin(identity) {
    const operation = Object.freeze({ ...identity });
    active = operation;
    return operation;
  }

  function owns(operation) {
    return active === operation && isIdentityCurrent(operation);
  }

  function finish(operation) {
    if (active === operation) active = null;
  }

  function invalidate() {
    active = null;
  }

  return { begin, owns, finish, invalidate };
}

export function applyRememberedParticipantResult(
  applicationState,
  outing,
  restored,
  { isCurrent },
) {
  if (!isCurrent() || applicationState.outingSnapshot?.slug !== outing.slug) {
    return false;
  }
  applicationState.participantRemembered = Boolean(restored);
  applicationState.durableOutboxPresent = Boolean(restored?.outbox);
  if (restored) {
    applicationState.outingParticipantReceipt = restored.receipt;
    applicationState.selectedOutingParticipantId = (
      restored.receipt.participant_id
    );
  }
  return true;
}

export async function completeParticipantForget({
  stop,
  forget,
  clearServer,
}) {
  let stopResult = { cleared: false, pending: false };
  let stopFailure = null;
  let storageFailure = null;
  try {
    stopResult = await stop();
  } catch (error) {
    stopFailure = error;
    stopResult = { cleared: false, pending: false, error };
  }
  try {
    await forget();
  } catch (error) {
    storageFailure = error;
  }
  return {
    stopResult,
    stopFailure,
    storageFailure,
    warningRequired: !clearServer
      || stopResult.cleared !== true
      || Boolean(stopResult.uncertain)
      || Boolean(stopResult.error)
      || Boolean(stopResult.pending),
  };
}
