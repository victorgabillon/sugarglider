import { PWA_STORES } from "./pwa_store.js";
import { DEFAULT_AVATAR_KEY, isAvatarKey } from "./avatar.js";

const SNAPSHOT_SCHEMA_VERSION = 1;
const MAXIMUM_SNAPSHOT_BYTES = 5_000_000;
const MAXIMUM_SNAPSHOTS = 8;
const SLUG_PATTERN = /^[A-Za-z0-9_-]{20,64}$/;
const FORBIDDEN_PUBLIC_KEY_PARTS = Object.freeze([
  "token",
  "capability",
  "mutationreceipt",
  "liveposition",
  "liveevent",
  "eventcursor",
  "replaycursor",
]);
const FORBIDDEN_PUBLIC_KEYS = new Set([
  "positions",
  "events",
  "cursor",
  "oldesteventid",
]);
const PUBLIC_CONFIG_FIELDS = Object.freeze([
  "tile_url_template",
  "tile_attribution",
  "initial_center",
  "initial_zoom",
  "max_required_points",
  "nature_index_available",
  "nature_water_buffer_m",
  "nature_preference_values",
  "loop_geometry_preference_values",
  "poi_index_available",
  "poi_default_limit",
  "poi_max_limit",
  "saved_routes_available",
  "outings_available",
  "outing_max_participants",
  "outing_live_positions_available",
  "outing_live_stale_after_seconds",
  "outing_live_expire_after_seconds",
  "default_planning_mode",
  "auto_tour_max_hard_waypoints",
  "auto_tour_max_preferred_pois",
  "auto_tour_scenic_corridor_radius_m",
  "auto_tour_water_corridor_radius_m",
]);

export function createOfflineSnapshotRepository(
  store,
  {
    clock = () => new Date(),
    maximumBytes = MAXIMUM_SNAPSHOT_BYTES,
    maximumRecords = MAXIMUM_SNAPSHOTS,
  } = {},
) {
  async function save(kind, payload, { refreshOnly = false } = {}) {
    const normalized = validateSnapshotPayload(kind, payload);
    const key = snapshotKey(kind, normalized.slug);
    const existing = await store.get(PWA_STORES.offlineSnapshots, key);
    if (refreshOnly && !existing) return null;
    const now = isoNow(clock);
    const record = validateSnapshotRecord({
      schema_version: SNAPSHOT_SCHEMA_VERSION,
      kind,
      slug: normalized.slug,
      saved_at: existing?.saved_at ?? now,
      updated_at: now,
      expires_at: normalized.expires_at,
      payload: normalized,
    }, { maximumBytes });
    const accepted = await store.putBounded(
      PWA_STORES.offlineSnapshots,
      key,
      record,
      {
        maximumRecords,
        retain: retainStoredSnapshot,
        compareEviction: compareSnapshotEviction,
        onlyIfExisting: refreshOnly,
      },
    );
    return accepted ? record : null;
  }

  async function read(kind, slug) {
    if (!validSlug(slug)) return null;
    const key = snapshotKey(kind, slug);
    const stored = await store.get(PWA_STORES.offlineSnapshots, key);
    if (!stored) return null;
    try {
      const record = validateSnapshotRecord(stored, { maximumBytes });
      if (expired(record.expires_at, clock)) {
        await store.remove(PWA_STORES.offlineSnapshots, key);
        return null;
      }
      return record;
    } catch {
      await store.remove(PWA_STORES.offlineSnapshots, key);
      return null;
    }
  }

  async function has(kind, slug) {
    return Boolean(await read(kind, slug));
  }

  async function remove(kind, slug) {
    if (!validSlug(slug)) return;
    await store.remove(
      PWA_STORES.offlineSnapshots,
      snapshotKey(kind, slug),
    );
  }

  async function prune() {
    const entries = await store.entries(PWA_STORES.offlineSnapshots);
    for (const entry of entries) {
      try {
        const record = validateSnapshotRecord(
          entry.value,
          { maximumBytes },
        );
        if (!expired(record.expires_at, clock)) continue;
        await store.remove(PWA_STORES.offlineSnapshots, entry.key);
      } catch {
        await store.remove(PWA_STORES.offlineSnapshots, entry.key);
      }
    }
  }

  function retainStoredSnapshot(candidate) {
    try {
      const record = validateSnapshotRecord(candidate, { maximumBytes });
      return !expired(record.expires_at, clock);
    } catch {
      return false;
    }
  }

  function compareSnapshotEviction(left, right) {
    return Date.parse(left.value.updated_at) - Date.parse(right.value.updated_at)
      || String(left.key).localeCompare(String(right.key));
  }

  return {
    durable: Boolean(store.durable),
    save,
    refreshExisting: (kind, payload) => save(
      kind,
      payload,
      { refreshOnly: true },
    ),
    read,
    has,
    remove,
    prune,
    clear: () => store.clear(PWA_STORES.offlineSnapshots),
    savePublicConfig: (config) => savePublicConfig(store, config, clock),
    readPublicConfig: () => readPublicConfig(store),
  };
}

export function validateSnapshotPayload(kind, payload) {
  if (!["saved_route", "outing"].includes(kind)) {
    throw new Error("Unsupported offline snapshot kind.");
  }
  const normalized = plainJson(payload);
  rejectForbiddenPublicData(normalized);
  if (normalized.schema_version !== SNAPSHOT_SCHEMA_VERSION) {
    throw new Error("Unsupported public snapshot schema.");
  }
  if (!validSlug(normalized.slug)) throw new Error("Invalid snapshot slug.");
  if (!validTimestamp(normalized.created_at)) {
    throw new Error("Invalid snapshot creation time.");
  }
  if (!validTimestamp(normalized.expires_at)) {
    throw new Error("Invalid snapshot expiration.");
  }
  if (Date.parse(normalized.expires_at) <= Date.parse(normalized.created_at)) {
    throw new Error("Snapshot expiration must follow creation.");
  }
  if (kind === "saved_route") validateSavedRoute(normalized);
  else validateOuting(normalized);
  return normalized;
}

export function validateSnapshotRecord(
  value,
  { maximumBytes = MAXIMUM_SNAPSHOT_BYTES } = {},
) {
  const record = plainJson(value);
  if (
    record.schema_version !== SNAPSHOT_SCHEMA_VERSION
    || !["saved_route", "outing"].includes(record.kind)
    || !validSlug(record.slug)
    || !validTimestamp(record.saved_at)
    || !validTimestamp(record.updated_at)
    || !validTimestamp(record.expires_at)
    || Date.parse(record.updated_at) < Date.parse(record.saved_at)
    || Date.parse(record.expires_at) <= Date.parse(record.saved_at)
  ) {
    throw new Error("Malformed offline snapshot record.");
  }
  const payload = validateSnapshotPayload(record.kind, record.payload);
  if (
    payload.slug !== record.slug
    || payload.expires_at !== record.expires_at
  ) {
    throw new Error("Offline snapshot record does not match its payload.");
  }
  record.payload = payload;
  if (new TextEncoder().encode(JSON.stringify(record)).length > maximumBytes) {
    throw new Error("Offline snapshot exceeds its size limit.");
  }
  return record;
}

export function rejectForbiddenPublicData(value) {
  walkJson(value, (key) => {
    const normalized = canonicalSecurityKey(key);
    if (
      FORBIDDEN_PUBLIC_KEYS.has(normalized)
      || FORBIDDEN_PUBLIC_KEY_PARTS.some(
        (forbidden) => normalized.includes(forbidden),
      )
    ) {
      throw new Error("Capabilities and live state cannot be saved offline.");
    }
  });
}

export function validatePublicConfig(value) {
  const source = plainJson(value);
  const config = Object.fromEntries(
    PUBLIC_CONFIG_FIELDS.map((field) => [field, source[field]]),
  );
  if (
    !validTileUrlTemplate(config.tile_url_template)
    || typeof config.tile_attribution !== "string"
    || !validCoordinate(config.initial_center)
    || !boundedNumber(config.initial_zoom, 0, 22)
    || !integerAtLeast(config.max_required_points, 2)
    || typeof config.nature_index_available !== "boolean"
    || !boundedNumber(config.nature_water_buffer_m, 0, 1000)
    || !preferenceList(config.nature_preference_values)
    || !preferenceList(config.loop_geometry_preference_values)
    || typeof config.poi_index_available !== "boolean"
    || !integerAtLeast(config.poi_default_limit, 1)
    || !integerAtLeast(config.poi_max_limit, 1)
    || config.poi_default_limit > config.poi_max_limit
    || typeof config.saved_routes_available !== "boolean"
    || typeof config.outings_available !== "boolean"
    || !boundedInteger(config.outing_max_participants, 2, 20)
    || typeof config.outing_live_positions_available !== "boolean"
    || !boundedInteger(config.outing_live_stale_after_seconds, 15, 3600)
    || !boundedInteger(config.outing_live_expire_after_seconds, 60, 86400)
    || config.outing_live_stale_after_seconds
      >= config.outing_live_expire_after_seconds
    || config.default_planning_mode !== "auto_tour"
    || config.auto_tour_max_hard_waypoints !== 6
    || config.auto_tour_max_preferred_pois !== 8
    || !boundedNumber(
      config.auto_tour_scenic_corridor_radius_m,
      50,
      2000,
    )
    || !boundedNumber(
      config.auto_tour_water_corridor_radius_m,
      25,
      1000,
    )
  ) {
    throw new Error("Invalid public UI configuration.");
  }
  return config;
}

async function savePublicConfig(store, value, clock) {
  const config = validatePublicConfig(value);
  await store.put(PWA_STORES.publicRuntime, "ui-config", {
    schema_version: 1,
    saved_at: isoNow(clock),
    config,
  });
  return config;
}

async function readPublicConfig(store) {
  const record = await store.get(PWA_STORES.publicRuntime, "ui-config");
  try {
    if (
      record?.schema_version !== 1
      || !validTimestamp(record.saved_at)
    ) throw new Error("Invalid stored configuration.");
    return validatePublicConfig(record.config);
  } catch {
    await store.remove(PWA_STORES.publicRuntime, "ui-config");
    return null;
  }
}

function validateSavedRoute(snapshot) {
  if (!plainObject(snapshot.source_request)) {
    throw new Error("Saved route source request is missing.");
  }
  validateCandidate(snapshot.candidate);
}

function validateOuting(snapshot) {
  if (
    typeof snapshot.title !== "string"
    || !snapshot.title.trim()
    || !boundedInteger(snapshot.max_participants, 2, 20)
    || !Array.isArray(snapshot.participants)
    || snapshot.participants.length > snapshot.max_participants
  ) throw new Error("Invalid outing snapshot.");
  const participantIds = new Set();
  for (const participant of snapshot.participants) {
    if (participant?.avatar_key === undefined) {
      participant.avatar_key = DEFAULT_AVATAR_KEY;
    }
    if (
      !plainObject(participant)
      || !validSlug(participant.participant_id)
      || participantIds.has(participant.participant_id)
      || typeof participant.display_name !== "string"
      || !participant.display_name.trim()
      || !isAvatarKey(participant.avatar_key)
      || !validTimestamp(participant.joined_at)
      || !plainObject(participant.planned_route?.source_request)
    ) throw new Error("Invalid outing participant.");
    participantIds.add(participant.participant_id);
    validateCandidate(participant.planned_route.candidate);
  }
}

function validateCandidate(candidate) {
  if (
    !plainObject(candidate)
    || !plainObject(candidate.route)
    || !validGeometry(candidate.route.geometry)
  ) throw new Error("Snapshot route geometry is invalid.");
}

function validGeometry(geometry) {
  return Array.isArray(geometry)
    && geometry.length > 0
    && geometry.every(validCoordinate);
}

function validCoordinate(coordinate) {
  return Array.isArray(coordinate)
    && coordinate.length === 2
    && boundedNumber(coordinate[0], -180, 180)
    && boundedNumber(coordinate[1], -90, 90);
}

function plainJson(value) {
  assertPlainJson(value, new Set());
  return JSON.parse(JSON.stringify(value));
}

function assertPlainJson(value, seen) {
  if (
    value === null
    || typeof value === "string"
    || typeof value === "boolean"
    || (typeof value === "number" && Number.isFinite(value))
  ) return;
  if (typeof value !== "object" || seen.has(value)) {
    throw new Error("Stored data must be finite plain JSON.");
  }
  const prototype = Object.getPrototypeOf(value);
  if (!Array.isArray(value) && prototype !== Object.prototype) {
    throw new Error("Stored data must use plain objects.");
  }
  seen.add(value);
  for (const entry of Array.isArray(value) ? value : Object.values(value)) {
    assertPlainJson(entry, seen);
  }
  seen.delete(value);
}

function walkJson(value, inspectKey) {
  if (Array.isArray(value)) {
    for (const entry of value) walkJson(entry, inspectKey);
    return;
  }
  if (!plainObject(value)) return;
  for (const [key, entry] of Object.entries(value)) {
    inspectKey(key);
    walkJson(entry, inspectKey);
  }
}

function canonicalSecurityKey(key) {
  return key.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function validTileUrlTemplate(value) {
  if (typeof value !== "string" || !value) return false;
  try {
    const url = new URL(value);
    const canonicalUrl = canonicalSecurityKey(decodeURIComponent(value));
    const sensitive = [
      "token",
      "capability",
      "authorization",
      "participant",
      "owner",
      "jointoken",
      "invitation",
    ];
    return ["http:", "https:"].includes(url.protocol)
      && Boolean(url.hostname)
      && !url.username
      && !url.password
      && !url.hash
      && ["{z}", "{x}", "{y}"].every((marker) => value.includes(marker))
      && !sensitive.some((marker) => canonicalUrl.includes(marker));
  } catch {
    return false;
  }
}

function snapshotKey(kind, slug) {
  return `${kind}:${slug}`;
}

function validSlug(value) {
  return typeof value === "string" && SLUG_PATTERN.test(value);
}

function validTimestamp(value) {
  return typeof value === "string"
    && /(?:Z|[+-]\d\d:\d\d)$/.test(value)
    && Number.isFinite(Date.parse(value));
}

function expired(value, clock) {
  return Date.parse(value) <= clock().getTime();
}

function isoNow(clock) {
  const value = clock();
  if (!(value instanceof Date) || !Number.isFinite(value.getTime())) {
    throw new Error("Invalid storage clock.");
  }
  return value.toISOString();
}

function plainObject(value) {
  return value !== null
    && typeof value === "object"
    && !Array.isArray(value)
    && Object.getPrototypeOf(value) === Object.prototype;
}

function boundedNumber(value, minimum, maximum) {
  return typeof value === "number"
    && Number.isFinite(value)
    && value >= minimum
    && value <= maximum;
}

function boundedInteger(value, minimum, maximum) {
  return Number.isInteger(value) && value >= minimum && value <= maximum;
}

function integerAtLeast(value, minimum) {
  return Number.isInteger(value) && value >= minimum;
}

function preferenceList(value) {
  return Array.isArray(value)
    && value.length > 0
    && value.every((entry) => ["off", "prefer"].includes(entry));
}
