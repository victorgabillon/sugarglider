export function createOutingLiveLifecycle() {
  let epoch = 0;
  let current = null;

  return {
    start(slug) {
      epoch += 1;
      current = Object.freeze({ slug, epoch });
      return current;
    },
    invalidate() {
      epoch += 1;
      current = null;
    },
    owns(session, activeSlug, closed) {
      return Boolean(
        session
        && current === session
        && session.epoch === epoch
        && session.slug === activeSlug
        && !closed
      );
    },
  };
}

export function participantReceiptBelongsToOuting(receipt, outing) {
  return Boolean(
    receipt
    && outing
    && receipt.slug === outing.slug
    && outing.participants.some(
      (participant) => participant.participant_id === receipt.participant_id,
    )
  );
}

export function discardStaleParticipantReceipt(
  state,
  snapshot,
  { shutdownTracker, syncTrackerState },
) {
  const receipt = state.outingParticipantReceipt;
  if (
    !receipt
    || receipt.slug !== snapshot.slug
    || participantReceiptBelongsToOuting(receipt, snapshot)
  ) {
    return false;
  }
  shutdownTracker();
  syncTrackerState();
  state.outingParticipantReceipt = null;
  return true;
}

export function createGuardedSingleFlight({
  isCurrent,
  onStart,
  load,
  apply,
  onError,
}) {
  let activeOperation = null;

  return {
    run(session) {
      if (!isCurrent(session)) return null;
      if (activeOperation?.session === session) {
        return activeOperation.promise;
      }
      const operation = { session, promise: null };
      activeOperation = operation;
      onStart?.(session);
      operation.promise = (async () => {
        try {
          const value = await load(session);
          if (!owns(operation)) return;
          await apply(value, session);
        } catch (error) {
          if (owns(operation)) await onError?.(error, session);
        } finally {
          if (activeOperation === operation) activeOperation = null;
        }
      })();
      return operation.promise;
    },
    invalidate() {
      activeOperation = null;
    },
  };

  function owns(operation) {
    return activeOperation === operation && isCurrent(operation.session);
  }
}

export function createDirtyRerun({
  isCurrent,
  load,
  apply,
  onError,
}) {
  let activeOperation = null;

  return {
    run(session) {
      if (!isCurrent(session)) return null;
      if (activeOperation?.session === session) {
        activeOperation.dirty = true;
        return activeOperation.promise;
      }
      const operation = { session, dirty: false, promise: null };
      activeOperation = operation;
      operation.promise = execute(operation);
      return operation.promise;
    },
    invalidate() {
      activeOperation = null;
    },
  };

  async function execute(operation) {
    try {
      do {
        operation.dirty = false;
        const value = await load(operation.session);
        if (!owns(operation)) return;
        await apply(value, operation.session);
      } while (operation.dirty && owns(operation));
    } catch (error) {
      if (owns(operation)) await onError?.(error, operation.session);
    } finally {
      if (activeOperation === operation) activeOperation = null;
    }
  }

  function owns(operation) {
    return activeOperation === operation && isCurrent(operation.session);
  }
}
