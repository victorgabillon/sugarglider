import { PWA_STORES } from "./pwa_store.js";

const SCHEMA_VERSION = 1;
const RESUME_WINDOW_MS = 15_000;
const FUTURE_CLOCK_TOLERANCE_MS = 1_000;
const MAXIMUM_OUTBOX_BYTES = 4_096;
const IDENTIFIER_PATTERN = /^[A-Za-z0-9_-]{20,128}$/;
const SAMPLE_IDENTIFIER_PATTERN = /^[A-Za-z0-9_-]{16,128}$/;
const SESSION_FIELDS = Object.freeze([
  "schema_version",
  "outing_slug",
  "participant_id",
  "participant_token",
  "outing_expires_at",
  "remembered_at",
  "last_used_at",
]);
const OUTBOX_FIELDS = Object.freeze([
  "schema_version",
  "outing_slug",
  "participant_id",
  "sample_id",
  "captured_at",
  "queued_at",
  "coordinate",
  "accuracy_m",
  "altitude_m",
  "speed_m_s",
  "heading_deg",
  "requires_resume",
]);

export function createParticipantSessionRepository(
  store,
  { clock = () => new Date() } = {},
) {
  async function remember(receipt, outingExpiresAt) {
    const now = isoNow(clock);
    const session = validateParticipantSession({
      schema_version: SCHEMA_VERSION,
      outing_slug: receipt?.slug,
      participant_id: receipt?.participant_id,
      participant_token: receipt?.participant_token,
      outing_expires_at: outingExpiresAt,
      remembered_at: now,
      last_used_at: now,
    });
    await store.replaceAndRemovePrevious({
      name: PWA_STORES.participantSessions,
      key: session.outing_slug,
      value: session,
      relatedName: PWA_STORES.positionOutbox,
      relatedKey: (previous) => (
        typeof previous?.participant_id === "string"
        && previous.participant_id !== session.participant_id
          ? outboxKey(session.outing_slug, previous.participant_id)
          : null
      ),
    });
    return session;
  }

  async function restore(slug, outing = null) {
    if (!validIdentifier(slug)) return null;
    const stored = await store.get(PWA_STORES.participantSessions, slug);
    if (!stored) return null;
    try {
      const session = validateParticipantSession(stored);
      if (
        expired(session.outing_expires_at, clock)
        || (
          outing
          && (
            outing.slug !== slug
            || !outing.participants?.some(
              (participant) => (
                participant.participant_id === session.participant_id
              ),
            )
          )
        )
      ) {
        await forget(slug);
        return null;
      }
      return session;
    } catch {
      await forget(slug);
      return null;
    }
  }

  async function forget(slug) {
    if (!validIdentifier(slug)) return;
    await store.removeSessionAndRelatedOutbox({
      sessionName: PWA_STORES.participantSessions,
      sessionKey: slug,
      outboxName: PWA_STORES.positionOutbox,
      relatedOutboxKey: (session) => outboxKey(
        slug,
        session.participant_id,
      ),
    });
  }

  async function forgetMatching(slug, participantId) {
    if (!validIdentifier(slug) || !validIdentifier(participantId)) return false;
    return store.removeSessionAndRelatedOutbox({
      sessionName: PWA_STORES.participantSessions,
      sessionKey: slug,
      sessionMatches: (session) => (
        session?.participant_id === participantId
      ),
      outboxName: PWA_STORES.positionOutbox,
      relatedOutboxKey: (session) => outboxKey(
        slug,
        session.participant_id,
      ),
    });
  }

  return {
    durable: Boolean(store.durable),
    remember,
    restore,
    forget,
    forgetMatching,
    clear: () => store.clear(PWA_STORES.participantSessions),
  };
}

export function createPositionOutboxRepository(
  store,
  {
    clock = () => new Date(),
    createSampleId = defaultSampleId,
    resumeWindowMs = RESUME_WINDOW_MS,
  } = {},
) {
  async function replace(session, sample, { requiresResume = true } = {}) {
    validateSessionIdentity(session);
    const now = clock().getTime();
    const record = validateOutboxRecord({
      schema_version: SCHEMA_VERSION,
      outing_slug: session.outing_slug,
      participant_id: session.participant_id,
      sample_id: createSampleId(),
      captured_at: sample?.captured_at,
      queued_at: new Date(now).toISOString(),
      coordinate: sample?.coordinate,
      accuracy_m: sample?.accuracy_m,
      altitude_m: sample?.altitude_m ?? null,
      speed_m_s: sample?.speed_m_s ?? null,
      heading_deg: sample?.heading_deg ?? null,
      requires_resume: Boolean(requiresResume),
    }, { now });
    const accepted = await store.putLatestOutboxIfSessionMatches({
      sessionName: PWA_STORES.participantSessions,
      sessionKey: record.outing_slug,
      sessionMatches: (stored) => matchingSession(stored, session),
      outboxName: PWA_STORES.positionOutbox,
      outboxKey: outboxKey(record.outing_slug, record.participant_id),
      value: record,
      isNewer: newerOutboxRecord,
    });
    return accepted ? record : null;
  }

  async function read(session, { discardStale = true } = {}) {
    validateSessionIdentity(session);
    const key = outboxKey(session.outing_slug, session.participant_id);
    const stored = await store.get(PWA_STORES.positionOutbox, key);
    if (!stored) return null;
    try {
      const now = clock().getTime();
      const record = validateOutboxRecord(stored, { now });
      const age = now - Date.parse(record.captured_at);
      if (
        record.outing_slug !== session.outing_slug
        || record.participant_id !== session.participant_id
        || (
          discardStale
          && (age < 0 || age > resumeWindowMs)
        )
      ) {
        await store.remove(PWA_STORES.positionOutbox, key);
        return null;
      }
      return record;
    } catch {
      await store.remove(PWA_STORES.positionOutbox, key);
      return null;
    }
  }

  async function removePublished(session, sampleId) {
    validateSessionIdentity(session);
    return store.removeIf(
      PWA_STORES.positionOutbox,
      outboxKey(session.outing_slug, session.participant_id),
      (record) => record?.sample_id === sampleId,
    );
  }

  async function remove(session) {
    validateSessionIdentity(session);
    await store.remove(
      PWA_STORES.positionOutbox,
      outboxKey(session.outing_slug, session.participant_id),
    );
  }

  async function removeForOuting(slug) {
    if (!validIdentifier(slug)) return;
    const records = await store.entries(PWA_STORES.positionOutbox);
    await Promise.all(
      records
        .filter((entry) => entry.value?.outing_slug === slug)
        .map((entry) => store.remove(
          PWA_STORES.positionOutbox,
          entry.key,
        )),
    );
  }

  return {
    durable: Boolean(store.durable),
    replace,
    read,
    removePublished,
    remove,
    removeForOuting,
    clear: () => store.clear(PWA_STORES.positionOutbox),
  };
}

export function createDurableOutboxBridge({
  sessions,
  outbox,
  onPresence = () => {},
} = {}) {
  let operationVersion = 0;
  let writes = Promise.resolve();

  function prepare(receipt, sample, { generation } = {}) {
    const version = operationVersion;
    const write = writes.then(async () => {
      if (version !== operationVersion) return null;
      const session = await sessions.restore(receipt?.slug);
      if (
        version !== operationVersion
        || !matchingReceipt(session, receipt)
      ) return null;
      const record = await outbox.replace(session, sample);
      if (!record) return null;
      if (version !== operationVersion) return null;
      notifyPresence(true, receipt, generation, version);
      return {
        sampleId: record.sample_id,
        session,
        generation,
        operationVersion: version,
      };
    });
    writes = write.catch(() => {});
    return write;
  }

  function prepareRestored(receipt, record, { generation } = {}) {
    const version = operationVersion;
    const preparation = writes.then(async () => {
      if (version !== operationVersion) return null;
      const session = await sessions.restore(receipt?.slug);
      if (
        version !== operationVersion
        || !matchingReceipt(session, receipt)
      ) return null;
      const current = await outbox.read(session);
      if (
        version !== operationVersion
        || current?.sample_id !== record?.sample_id
      ) return null;
      notifyPresence(true, receipt, generation, version);
      return {
        sampleId: current.sample_id,
        session,
        generation,
        operationVersion: version,
      };
    });
    writes = preparation.catch(() => {});
    return preparation;
  }

  async function published(receipt, prepared, { generation } = {}) {
    if (!ownsPrepared(prepared, receipt, generation)) return;
    await outbox.removePublished(prepared.session, prepared.sampleId);
    if (!ownsPrepared(prepared, receipt, generation)) return;
    const remaining = await outbox.read(
      prepared.session,
      { discardStale: false },
    );
    if (!ownsPrepared(prepared, receipt, generation)) return;
    notifyPresence(
      Boolean(remaining),
      receipt,
      generation,
      prepared.operationVersion,
    );
  }

  async function discard(receipt, prepared, { generation } = {}) {
    if (!ownsPrepared(prepared, receipt, generation)) return;
    await outbox.removePublished(prepared.session, prepared.sampleId);
    if (!ownsPrepared(prepared, receipt, generation)) return;
    const remaining = await outbox.read(
      prepared.session,
      { discardStale: false },
    );
    if (!ownsPrepared(prepared, receipt, generation)) return;
    notifyPresence(
      Boolean(remaining),
      receipt,
      generation,
      prepared.operationVersion,
    );
  }

  function invalidate() {
    operationVersion += 1;
  }

  async function stop(receipt, { generation } = {}) {
    invalidate();
    const version = operationVersion;
    const session = await sessions.restore(receipt?.slug);
    if (version !== operationVersion) return;
    if (matchingReceipt(session, receipt)) await outbox.remove(session);
    if (version !== operationVersion) return;
    notifyPresence(false, receipt, generation, version);
  }

  function ownsPrepared(prepared, receipt, generation) {
    return Boolean(
      prepared
      && prepared.operationVersion === operationVersion
      && prepared.generation === generation
      && matchingReceipt(prepared.session, receipt)
    );
  }

  function notifyPresence(present, receipt, generation, version) {
    if (version !== operationVersion) return;
    onPresence(present, {
      generation,
      operationVersion: version,
      outingSlug: receipt?.slug,
      participantId: receipt?.participant_id,
    });
  }

  return {
    prepare,
    prepareRestored,
    published,
    discard,
    invalidate,
    stop,
  };
}

export function validateParticipantSession(value) {
  exactFields(value, SESSION_FIELDS);
  if (
    value.schema_version !== SCHEMA_VERSION
    || !validIdentifier(value.outing_slug)
    || !validIdentifier(value.participant_id)
    || typeof value.participant_token !== "string"
    || value.participant_token.length < 32
    || value.participant_token.length > 128
    || !validTimestamp(value.outing_expires_at)
    || !validTimestamp(value.remembered_at)
    || !validTimestamp(value.last_used_at)
    || Date.parse(value.outing_expires_at) <= Date.parse(value.remembered_at)
    || Date.parse(value.last_used_at) < Date.parse(value.remembered_at)
    || Date.parse(value.last_used_at) >= Date.parse(value.outing_expires_at)
  ) throw new Error("Invalid remembered participant session.");
  return clone(value);
}

export function validateOutboxRecord(
  value,
  {
    now = Date.now(),
    futureToleranceMs = FUTURE_CLOCK_TOLERANCE_MS,
  } = {},
) {
  exactFields(value, OUTBOX_FIELDS);
  if (
    value.schema_version !== SCHEMA_VERSION
    || !validIdentifier(value.outing_slug)
    || !validIdentifier(value.participant_id)
    || typeof value.sample_id !== "string"
    || !SAMPLE_IDENTIFIER_PATTERN.test(value.sample_id)
    || !validTimestamp(value.captured_at)
    || !validTimestamp(value.queued_at)
    || Date.parse(value.captured_at) > Date.parse(value.queued_at)
    || Date.parse(value.queued_at) > now + futureToleranceMs
    || !validCoordinate(value.coordinate)
    || !boundedNumber(value.accuracy_m, 0, 10_000)
    || !optionalBounded(value.altitude_m, -1_000, 12_000)
    || !optionalBounded(value.speed_m_s, 0, 150)
    || !optionalBounded(value.heading_deg, 0, 360, true)
    || typeof value.requires_resume !== "boolean"
  ) throw new Error("Invalid durable position sample.");
  const cloned = clone(value);
  if (
    new TextEncoder().encode(JSON.stringify(cloned)).length
    > MAXIMUM_OUTBOX_BYTES
  ) throw new Error("Durable position sample exceeds its size limit.");
  return cloned;
}

function newerOutboxRecord(candidate, existing) {
  try {
    validateOutboxRecord(existing, {
      now: Date.parse(candidate.queued_at),
    });
  } catch {
    return true;
  }
  return compareTimestamp(candidate.captured_at, existing.captured_at)
    || (
      candidate.captured_at === existing.captured_at
      && (
        compareTimestamp(candidate.queued_at, existing.queued_at)
        || (
          candidate.queued_at === existing.queued_at
          && candidate.sample_id.localeCompare(existing.sample_id) > 0
        )
      )
    );
}

function compareTimestamp(left, right) {
  return Date.parse(left) > Date.parse(right);
}

export function foregroundOutboxFlushAllowed({
  visible,
  trackingActive,
  remembered,
}) {
  return visible === true
    && trackingActive === true
    && remembered === true;
}

function validateSessionIdentity(session) {
  if (
    !validIdentifier(session?.outing_slug)
    || !validIdentifier(session?.participant_id)
  ) throw new Error("A remembered participant identity is required.");
}

function matchingReceipt(session, receipt) {
  return Boolean(
    session
    && session.outing_slug === receipt?.slug
    && session.participant_id === receipt?.participant_id
    && session.participant_token === receipt?.participant_token,
  );
}

function matchingSession(stored, expected) {
  return Boolean(
    stored
    && stored.outing_slug === expected?.outing_slug
    && stored.participant_id === expected?.participant_id
    && stored.participant_token === expected?.participant_token
  );
}

function outboxKey(slug, participantId) {
  return `${slug}:${participantId}`;
}

function defaultSampleId() {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  const bytes = new Uint8Array(16);
  globalThis.crypto?.getRandomValues?.(bytes);
  const value = [...bytes]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
  if (/^0+$/.test(value)) {
    return `sample_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
  }
  return value;
}

function exactFields(value, expected) {
  if (
    value === null
    || typeof value !== "object"
    || Array.isArray(value)
    || Object.getPrototypeOf(value) !== Object.prototype
    || Object.keys(value).sort().join("\0")
      !== [...expected].sort().join("\0")
  ) throw new Error("Stored participant data has unexpected fields.");
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function validIdentifier(value) {
  return typeof value === "string" && IDENTIFIER_PATTERN.test(value);
}

function validTimestamp(value) {
  return typeof value === "string"
    && /(?:Z|[+-]\d\d:\d\d)$/.test(value)
    && Number.isFinite(Date.parse(value));
}

function validCoordinate(value) {
  return value !== null
    && typeof value === "object"
    && !Array.isArray(value)
    && Object.keys(value).sort().join("\0") === "lat\0lon"
    && boundedNumber(value.lat, -90, 90)
    && boundedNumber(value.lon, -180, 180);
}

function boundedNumber(value, minimum, maximum, maximumExclusive = false) {
  return typeof value === "number"
    && Number.isFinite(value)
    && value >= minimum
    && (maximumExclusive ? value < maximum : value <= maximum);
}

function optionalBounded(value, minimum, maximum, maximumExclusive = false) {
  return value === null
    || boundedNumber(value, minimum, maximum, maximumExclusive);
}

function isoNow(clock) {
  const value = clock();
  if (!(value instanceof Date) || !Number.isFinite(value.getTime())) {
    throw new Error("Invalid participant storage clock.");
  }
  return value.toISOString();
}

function expired(timestamp, clock) {
  return Date.parse(timestamp) <= clock().getTime();
}
