const PARTICIPANT_ID_PATTERN = /^[A-Za-z0-9_-]{20,64}$/;
const SLUG_PATTERN = /^[A-Za-z0-9_-]{20,64}$/;
const OFFSET_TIMESTAMP_PATTERN = /(?:Z|[+-]\d{2}:\d{2})$/;
const VALID_CONNECTION_STATUSES = new Set([
  "closed",
  "connecting",
  "open",
  "reconnecting",
  "unavailable",
]);
const CLEAR_REASONS = new Set([
  "stopped",
  "expired",
  "participant_left",
]);

export function emptyOutingLiveState() {
  return {
    cursor: 0,
    positions: [],
    generatedAt: null,
    serverClockOffsetMs: 0,
    connectionStatus: "closed",
    lastEventReceivedAt: null,
  };
}

export function replaceWithSnapshot(
  current,
  snapshot,
  expectedSlug,
  clientNow = Date.now(),
) {
  const normalized = normalizeSnapshot(snapshot, expectedSlug);
  if (!normalized || !primitiveFiniteNumber(clientNow)) {
    return { status: "recovery_required", state: current };
  }
  return {
    status: "applied",
    state: {
      cursor: normalized.cursor,
      positions: normalized.positions,
      generatedAt: normalized.generated_at,
      serverClockOffsetMs: (
        Date.parse(normalized.generated_at) - clientNow
      ),
      connectionStatus: current.connectionStatus,
      lastEventReceivedAt: clientNow,
    },
  };
}

export function applyLiveEvent(
  current,
  event,
  lastEventId,
  clientNow = Date.now(),
) {
  const normalized = normalizeEvent(event);
  if (
    !normalized
    || !eventIdentifierMatches(lastEventId, normalized.event_id)
    || !primitiveFiniteNumber(clientNow)
  ) {
    return { status: "recovery_required", state: current };
  }
  if (normalized.event_id <= current.cursor) {
    return { status: "ignored", state: current };
  }
  if (normalized.event_id !== current.cursor + 1) {
    return { status: "recovery_required", state: current };
  }

  const positions = normalized.event_type === "position_updated"
    ? upsertPosition(current.positions, normalized.position)
    : current.positions.filter(
      (position) => (
        position.participant_id !== normalized.participant_id
      ),
    );
  return {
    status: "applied",
    state: {
      ...current,
      cursor: normalized.event_id,
      positions,
      lastEventReceivedAt: clientNow,
    },
  };
}

export function upsertOptimisticPosition(current, position) {
  const normalized = normalizePosition(position);
  if (!normalized) return current;
  return {
    ...current,
    positions: upsertPosition(current.positions, normalized),
  };
}

export function removeOptimisticPosition(current, participantId) {
  if (!validParticipantId(participantId)) return current;
  return {
    ...current,
    positions: current.positions.filter(
      (position) => position.participant_id !== participantId,
    ),
  };
}

export function livePositionForParticipant(current, participantId) {
  return current.positions.find(
    (position) => position.participant_id === participantId,
  ) ?? null;
}

export function estimatedServerNow(current, clientNow = Date.now()) {
  return clientNow + current.serverClockOffsetMs;
}

export function liveFreshness(position, serverNow) {
  const staleAt = Date.parse(position?.stale_at);
  const expiresAt = Date.parse(position?.expires_at);
  if (
    !primitiveFiniteNumber(serverNow)
    || !Number.isFinite(staleAt)
    || !Number.isFinite(expiresAt)
  ) {
    return "expired";
  }
  if (serverNow >= expiresAt) return "expired";
  return serverNow >= staleAt ? "stale" : "fresh";
}

export function visibleLivePositions(current, serverNow) {
  return current.positions.filter(
    (position) => liveFreshness(position, serverNow) !== "expired",
  );
}

export function withConnectionStatus(current, connectionStatus) {
  if (!VALID_CONNECTION_STATUSES.has(connectionStatus)) return current;
  return { ...current, connectionStatus };
}

function normalizeSnapshot(snapshot, expectedSlug) {
  const cursor = safeCursor(snapshot?.cursor);
  const generatedAt = normalizedTimestamp(snapshot?.generated_at);
  const staleAfterSeconds = positiveSafeInteger(
    snapshot?.stale_after_seconds,
  );
  const expireAfterSeconds = positiveSafeInteger(
    snapshot?.expire_after_seconds,
  );
  if (
    snapshot?.schema_version !== 1
    || !validSlug(expectedSlug)
    || snapshot.slug !== expectedSlug
    || cursor === null
    || !generatedAt
    || staleAfterSeconds === null
    || expireAfterSeconds === null
    || staleAfterSeconds >= expireAfterSeconds
    || !Array.isArray(snapshot.positions)
  ) return null;

  const positions = [];
  const participantIds = new Set();
  for (const value of snapshot.positions) {
    const position = normalizePosition(value);
    if (!position || participantIds.has(position.participant_id)) return null;
    participantIds.add(position.participant_id);
    positions.push(position);
  }
  return {
    cursor,
    generated_at: generatedAt,
    positions,
  };
}

function normalizeEvent(event) {
  const eventId = positiveSafeInteger(event?.event_id);
  const occurredAt = normalizedTimestamp(event?.occurred_at);
  if (
    event?.schema_version !== 1
    || eventId === null
    || !["position_updated", "position_cleared"].includes(event.event_type)
    || !validParticipantId(event.participant_id)
    || !occurredAt
  ) return null;

  if (event.event_type === "position_updated") {
    const position = normalizePosition(event.position);
    if (
      !position
      || position.participant_id !== event.participant_id
      || event.clear_reason !== null
    ) return null;
    return {
      schema_version: 1,
      event_id: eventId,
      event_type: "position_updated",
      participant_id: event.participant_id,
      occurred_at: occurredAt,
      position,
      clear_reason: null,
    };
  }
  if (
    event.position !== null
    || !CLEAR_REASONS.has(event.clear_reason)
  ) return null;
  return {
    schema_version: 1,
    event_id: eventId,
    event_type: "position_cleared",
    participant_id: event.participant_id,
    occurred_at: occurredAt,
    position: null,
    clear_reason: event.clear_reason,
  };
}

function normalizePosition(position) {
  const coordinate = position?.coordinate;
  const sequence = safeCursor(position?.sequence);
  const capturedAt = normalizedTimestamp(position?.captured_at);
  const receivedAt = normalizedTimestamp(position?.received_at);
  const staleAt = normalizedTimestamp(position?.stale_at);
  const expiresAt = normalizedTimestamp(position?.expires_at);
  const altitude = normalizedOptionalNumber(
    position?.altitude_m,
    -1_000,
    12_000,
  );
  const speed = normalizedOptionalNumber(position?.speed_m_s, 0, 150);
  const heading = normalizedOptionalNumber(
    position?.heading_deg,
    0,
    360,
    true,
  );
  if (
    position?.schema_version !== 1
    || !validParticipantId(position.participant_id)
    || sequence === null
    || !validCoordinate(coordinate)
    || !boundedPrimitiveNumber(position.accuracy_m, 0, 10_000)
    || !altitude.valid
    || !speed.valid
    || !heading.valid
    || !capturedAt
    || !receivedAt
    || !staleAt
    || !expiresAt
    || Date.parse(receivedAt) >= Date.parse(staleAt)
    || Date.parse(staleAt) >= Date.parse(expiresAt)
  ) return null;
  return {
    schema_version: 1,
    participant_id: position.participant_id,
    sequence,
    coordinate: {
      lat: coordinate.lat,
      lon: coordinate.lon,
    },
    accuracy_m: position.accuracy_m,
    altitude_m: altitude.value,
    speed_m_s: speed.value,
    heading_deg: heading.value,
    captured_at: capturedAt,
    received_at: receivedAt,
    stale_at: staleAt,
    expires_at: expiresAt,
  };
}

function upsertPosition(positions, incoming) {
  const existing = positions.find(
    (position) => position.participant_id === incoming.participant_id,
  );
  if (existing && existing.sequence > incoming.sequence) return positions;
  return [
    ...positions.filter(
      (position) => position.participant_id !== incoming.participant_id,
    ),
    incoming,
  ];
}

function eventIdentifierMatches(lastEventId, eventId) {
  if (lastEventId === undefined || lastEventId === null || lastEventId === "") {
    return true;
  }
  return /^[0-9]+$/.test(lastEventId)
    && Number(lastEventId) === eventId;
}

function safeCursor(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function positiveSafeInteger(value) {
  return Number.isSafeInteger(value) && value > 0 ? value : null;
}

function validParticipantId(value) {
  return typeof value === "string" && PARTICIPANT_ID_PATTERN.test(value);
}

function validSlug(value) {
  return typeof value === "string" && SLUG_PATTERN.test(value);
}

function validCoordinate(value) {
  return boundedPrimitiveNumber(value?.lat, -90, 90)
    && boundedPrimitiveNumber(value?.lon, -180, 180);
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

function normalizedOptionalNumber(
  value,
  minimum,
  maximum,
  maximumExclusive = false,
) {
  if (value === null || value === undefined) {
    return { valid: true, value: null };
  }
  if (!boundedPrimitiveNumber(
    value,
    minimum,
    maximum,
    maximumExclusive,
  )) {
    return { valid: false, value: null };
  }
  return { valid: true, value };
}

function normalizedTimestamp(value) {
  if (
    typeof value !== "string"
    || !OFFSET_TIMESTAMP_PATTERN.test(value)
  ) return null;
  const milliseconds = Date.parse(value);
  return Number.isFinite(milliseconds)
    ? new Date(milliseconds).toISOString()
    : null;
}
