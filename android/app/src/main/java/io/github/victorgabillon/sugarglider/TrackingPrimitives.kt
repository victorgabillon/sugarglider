package io.github.victorgabillon.sugarglider

import java.time.Instant
import kotlin.math.min

internal object LocationNormalizer {
    fun normalize(
        fix: RawLocationFix,
        sampleId: String,
        queuedAt: Instant,
    ): NormalizedLocationSample? {
        if (!fix.latitude.isFinite() || fix.latitude !in -90.0..90.0) return null
        if (!fix.longitude.isFinite() || fix.longitude !in -180.0..180.0) return null
        if (!fix.accuracyM.isFinite() || fix.accuracyM !in 0.0..10_000.0) return null
        if (fix.capturedAtEpochMs <= 0) return null
        val capturedAt = try {
            Instant.ofEpochMilli(fix.capturedAtEpochMs)
        } catch (_: Exception) {
            return null
        }
        return NormalizedLocationSample(
            sampleId = sampleId,
            capturedAt = capturedAt,
            queuedAt = queuedAt,
            latitude = fix.latitude,
            longitude = fix.longitude,
            accuracyM = fix.accuracyM,
            altitudeM = optional(fix.altitudeM, -1_000.0, 12_000.0),
            speedMS = optional(fix.speedMS, 0.0, 150.0),
            headingDeg = optional(fix.headingDeg, 0.0, 360.0, maximumExclusive = true),
        )
    }

    private fun optional(
        value: Double?,
        minimum: Double,
        maximum: Double,
        maximumExclusive: Boolean = false,
    ): Double? {
        if (value == null || !value.isFinite() || value < minimum) return null
        if (maximumExclusive && value >= maximum) return null
        if (!maximumExclusive && value > maximum) return null
        return value
    }
}

internal object SequenceAllocator {
    fun next(epochMilliseconds: Long, lastAccepted: Long): Long? {
        if (epochMilliseconds !in 0..MAXIMUM_SAFE_SEQUENCE) return null
        if (lastAccepted >= MAXIMUM_SAFE_SEQUENCE) return null
        return maxOf(epochMilliseconds, lastAccepted + 1)
    }
}

internal class RetryPolicy(
    private val initialDelayMs: Long = 1_000,
    private val maximumDelayMs: Long = 30_000,
) {
    private var nextDelayMs = initialDelayMs

    fun takeDelay(): Long {
        val delay = nextDelayMs
        nextDelayMs = min(maximumDelayMs, nextDelayMs * 2)
        return delay
    }

    fun reset() {
        nextDelayMs = initialDelayMs
    }
}

internal class GenerationOwner {
    private var current = 0L

    fun advance(): Long {
        current += 1
        return current
    }

    fun owns(generation: Long): Boolean = generation == current

    fun value(): Long = current
}

internal class ServiceStartIdGuard {
    private var latestStartId = 0
    private var pendingStopStartId: Int? = null

    @Synchronized
    fun recordStart(startId: Int) {
        latestStartId = maxOf(latestStartId, startId)
        pendingStopStartId = null
    }

    @Synchronized
    fun recordStop(startId: Int) {
        latestStartId = maxOf(latestStartId, startId)
        pendingStopStartId = startId
    }

    @Synchronized
    fun captureStopStartId(): Int = pendingStopStartId ?: latestStartId

    @Synchronized
    fun stopStillOwnsService(capturedStartId: Int): Boolean =
        latestStartId <= capturedStartId
}

internal class LatestOnlyPending {
    private var sample: NormalizedLocationSample? = null

    fun replace(value: NormalizedLocationSample) {
        val existing = sample
        if (existing == null || compare(value, existing) >= 0) sample = value
    }

    fun peek(): NormalizedLocationSample? = sample

    fun take(): NormalizedLocationSample? = sample.also { sample = null }

    fun clearMatching(sampleId: String): Boolean {
        if (sample?.sampleId != sampleId) return false
        sample = null
        return true
    }

    fun clear() {
        sample = null
    }

    private fun compare(
        left: NormalizedLocationSample,
        right: NormalizedLocationSample,
    ): Int = compareValuesBy(left, right, { it.capturedAt }, { it.queuedAt }, { it.sampleId })
}

internal enum class HttpOutcomeKind {
    ACCEPTED,
    NOT_FOUND,
    SEQUENCE_CONFLICT,
    INVALID_FIX,
    TRANSIENT,
    DEFINITE_FAILURE,
}

internal object HttpOutcomeClassifier {
    fun classify(status: Int?, code: String?): HttpOutcomeKind = when {
        status == null -> HttpOutcomeKind.TRANSIENT
        status in 200..299 -> HttpOutcomeKind.ACCEPTED
        status == 404 && code == "outing_not_found" -> HttpOutcomeKind.NOT_FOUND
        status == 409 && code == "outing_position_sequence_conflict" ->
            HttpOutcomeKind.SEQUENCE_CONFLICT
        status == 422 && code == "outing_position_invalid" -> HttpOutcomeKind.INVALID_FIX
        status == 408 || status == 429 || status >= 500 -> HttpOutcomeKind.TRANSIENT
        else -> HttpOutcomeKind.DEFINITE_FAILURE
    }
}

internal object SafeText {
    const val UNCERTAIN_STOP =
        "Sharing stopped on this device. The last position may remain visible until server expiry."
    const val STORAGE_FAILURE =
        "Secure latest-position storage failed. Sharing stopped safely on this device."

    fun notification(state: String, lastPublishedAt: Instant?): String = when {
        state == "offline_retrying" -> "Offline — latest update delayed"
        state == "stopping" -> "Stopping location sharing"
        lastPublishedAt != null -> "Last update ${lastPublishedAt}"
        else -> "Waiting for a precise location fix"
    }

    fun safeFailureCode(value: String): String = when (value) {
        "outing_not_found",
        "sequence_exhausted",
        "permission_denied",
        "approximate_location",
        "notification_permission_denied",
        "location_disabled",
        "different_participant_active",
        "start_in_progress",
        "stop_in_progress",
        -> value
        else -> "native_tracking_failure"
    }
}

internal data class StartConditions(
    val explicitRequest: Boolean,
    val disclosureConfirmed: Boolean,
    val activityVisible: Boolean,
    val preciseLocationGranted: Boolean,
    val notificationsGranted: Boolean,
    val locationServicesEnabled: Boolean,
    val currentStatus: NativeTrackingStatus,
    val requestedIdentity: Pair<String, String>,
)

internal sealed interface StartDecision {
    data object Allowed : StartDecision

    data object AlreadyActive : StartDecision

    data class Rejected(val code: String) : StartDecision
}

internal object StartPolicy {
    fun decide(value: StartConditions): StartDecision = when {
        !value.explicitRequest || !value.disclosureConfirmed || !value.activityVisible ->
            StartDecision.Rejected("permission_denied")
        !value.preciseLocationGranted -> StartDecision.Rejected("approximate_location")
        !value.notificationsGranted ->
            StartDecision.Rejected("notification_permission_denied")
        !value.locationServicesEnabled -> StartDecision.Rejected("location_disabled")
        value.currentStatus.state == "stopping" ->
            StartDecision.Rejected("stop_in_progress")
        value.currentStatus.busyIdentity() == value.requestedIdentity ->
            StartDecision.AlreadyActive
        value.currentStatus.isNativeBusy() ->
            StartDecision.Rejected("different_participant_active")
        else -> StartDecision.Allowed
    }
}

internal object ServerChangePolicy {
    fun allowed(currentStatus: NativeTrackingStatus): Boolean =
        !currentStatus.isNativeBusy()
}
