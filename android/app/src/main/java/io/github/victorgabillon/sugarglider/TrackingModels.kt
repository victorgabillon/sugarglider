package io.github.victorgabillon.sugarglider

import java.time.Instant

internal const val SCHEMA_VERSION = 1
internal const val MAXIMUM_SAFE_SEQUENCE = 9_007_199_254_740_991L
internal val OUTING_SLUG_PATTERN = Regex("^[A-Za-z0-9_-]{20,64}$")
internal val PARTICIPANT_ID_PATTERN = Regex("^[A-Za-z0-9_-]{20,64}$")
internal val PARTICIPANT_TOKEN_PATTERN = Regex("^[A-Za-z0-9_-]{32,128}$")

internal data class ParticipantSession(
    val serverOrigin: String,
    val outingSlug: String,
    val participantId: String,
    val participantToken: String,
    val outingExpiresAt: Instant,
    val lastAcceptedSequence: Long,
    val startedAt: Instant,
) {
    fun isValid(now: Instant): Boolean =
        ServerOrigin.parse(serverOrigin, allowDevelopmentHttp = true)?.normalized == serverOrigin &&
            OUTING_SLUG_PATTERN.matches(outingSlug) &&
            PARTICIPANT_ID_PATTERN.matches(participantId) &&
            PARTICIPANT_TOKEN_PATTERN.matches(participantToken) &&
            lastAcceptedSequence in -1 until MAXIMUM_SAFE_SEQUENCE &&
            startedAt.isBefore(outingExpiresAt) &&
            now.isBefore(outingExpiresAt)

    fun identityMatches(other: ParticipantSession): Boolean =
        serverOrigin == other.serverOrigin &&
            outingSlug == other.outingSlug &&
            participantId == other.participantId &&
            participantToken == other.participantToken &&
            startedAt == other.startedAt
}

internal data class NormalizedLocationSample(
    val sampleId: String,
    val capturedAt: Instant,
    val queuedAt: Instant,
    val latitude: Double,
    val longitude: Double,
    val accuracyM: Double,
    val altitudeM: Double?,
    val speedMS: Double?,
    val headingDeg: Double?,
) {
    fun isValid(now: Instant): Boolean =
        sampleId.length in 16..128 &&
            capturedAt.epochSecond > 0 &&
            !capturedAt.isAfter(queuedAt) &&
            !queuedAt.isAfter(now.plusSeconds(30)) &&
            latitude.isFinite() && latitude in -90.0..90.0 &&
            longitude.isFinite() && longitude in -180.0..180.0 &&
            accuracyM.isFinite() && accuracyM in 0.0..10_000.0 &&
            boundedOptional(altitudeM, -1_000.0, 12_000.0) &&
            boundedOptional(speedMS, 0.0, 150.0) &&
            boundedOptional(headingDeg, 0.0, 360.0, maximumExclusive = true)

    private fun boundedOptional(
        value: Double?,
        minimum: Double,
        maximum: Double,
        maximumExclusive: Boolean = false,
    ): Boolean = value == null || (
        value.isFinite() &&
            value >= minimum &&
            if (maximumExclusive) value < maximum else value <= maximum
        )
}

internal data class SecureTrackingRecord(
    val session: ParticipantSession,
    val pendingSample: NormalizedLocationSample?,
)

internal data class RawLocationFix(
    val latitude: Double,
    val longitude: Double,
    val accuracyM: Double,
    val capturedAtEpochMs: Long,
    val altitudeM: Double?,
    val speedMS: Double?,
    val headingDeg: Double?,
)

internal data class NativeTrackingStatus(
    val outingSlug: String?,
    val participantId: String?,
    val active: Boolean,
    val state: String,
    val lastPublishedAt: Instant?,
    val pendingSample: Boolean,
    val stopWarning: String?,
) {
    companion object {
        fun stopped(warning: String? = null): NativeTrackingStatus =
            NativeTrackingStatus(
                outingSlug = null,
                participantId = null,
                active = false,
                state = "stopped",
                lastPublishedAt = null,
                pendingSample = false,
                stopWarning = warning,
            )
    }
}

private val NATIVE_BUSY_STATES = setOf(
    "starting",
    "waiting",
    "sharing",
    "offline_retrying",
    "stopping",
)

internal fun NativeTrackingStatus.isNativeBusy(): Boolean =
    active || state in NATIVE_BUSY_STATES

internal fun NativeTrackingStatus.busyIdentity(): Pair<String, String>? =
    if (isNativeBusy()) {
        outingSlug?.let { slug -> participantId?.let { participant -> slug to participant } }
    } else {
        null
    }

internal data class NativeTerminalFailureEvent(
    val eventId: Long,
    val outingSlug: String,
    val participantId: String,
    val code: String,
)

internal enum class PendingWriteResult {
    STORED,
    IGNORED_OLDER,
    SESSION_MISMATCH,
    STORAGE_FAILURE,
}

internal enum class StoreMutationResult {
    APPLIED,
    NO_MATCH,
    SESSION_MISMATCH,
    STORAGE_FAILURE,
}

internal interface AppClock {
    fun now(): Instant

    fun epochMilliseconds(): Long

    fun elapsedMilliseconds(): Long
}

internal interface SecureStateStore {
    fun load(): SecureTrackingRecord?

    fun saveSession(session: ParticipantSession): StoreMutationResult

    fun replacePending(
        session: ParticipantSession,
        sample: NormalizedLocationSample,
    ): PendingWriteResult

    fun clearMatchingSample(
        session: ParticipantSession,
        sampleId: String,
    ): StoreMutationResult

    fun updateSequence(
        session: ParticipantSession,
        sequence: Long,
    ): StoreMutationResult

    fun clearMatchingSession(session: ParticipantSession): StoreMutationResult

    fun clearAll(): StoreMutationResult
}
