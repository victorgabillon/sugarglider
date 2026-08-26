package io.github.victorgabillon.sugarglider

import java.time.Duration
import java.time.Instant
import java.util.UUID
import java.util.concurrent.ScheduledThreadPoolExecutor
import java.util.concurrent.TimeUnit

internal fun interface ScheduledTask {
    fun cancel()
}

internal interface NativeTaskScheduler {
    fun execute(task: () -> Unit)

    fun schedule(delayMs: Long, task: () -> Unit): ScheduledTask

    fun shutdown()
}

internal class ExecutorTaskScheduler : NativeTaskScheduler {
    private val executor = ScheduledThreadPoolExecutor(1).apply {
        removeOnCancelPolicy = true
    }

    override fun execute(task: () -> Unit) {
        executor.execute(task)
    }

    override fun schedule(delayMs: Long, task: () -> Unit): ScheduledTask {
        val future = executor.schedule(task, delayMs.coerceAtLeast(0), TimeUnit.MILLISECONDS)
        return ScheduledTask { future.cancel(false) }
    }

    override fun shutdown() {
        executor.shutdown()
    }
}

internal class NativeTrackingEngine(
    private val store: SecureStateStore,
    private val publisher: NativeTrackingPublisher,
    private val locationSource: LocationSource,
    private val scheduler: NativeTaskScheduler,
    private val clock: AppClock,
    private val statusSink: (ParticipantSession?, NativeTrackingStatus) -> Unit,
    private val terminalSink: (ParticipantSession, String, Boolean) -> Unit,
    private val notificationSink: (NativeTrackingStatus) -> Unit,
    private val stoppedSink: (ParticipantSession?) -> Unit,
    private val sampleId: () -> String = { UUID.randomUUID().toString() },
    private val publicationIntervalMs: Long = 5_000L,
) {
    private val lock = Any()
    private val retryPolicy = RetryPolicy()
    private val pending = LatestOnlyPending()
    private var session: ParticipantSession? = null
    private var generation = 0L
    private var stopping = false
    private var destroyed = false
    private var publishInFlight = false
    private var terminalRecorded = false
    private var terminalSession: ParticipantSession? = null
    private var lastAcceptedSequence = -1L
    private var lastPublishedAt: Instant? = null
    private var lastPublishedElapsedMs: Long? = null
    private var cadenceTask: ScheduledTask? = null
    private var retryTask: ScheduledTask? = null
    private var expiryTask: ScheduledTask? = null
    private var sessionHadUncertainPut = false
    private var stopCompletionStarted = false
    private var pendingStoredStart: PendingStoredStart? = null
    private var pendingStoredStop: PendingStoredStop? = null

    fun startStored(): Boolean {
        val ownership = synchronized(lock) {
            if (
                destroyed || session != null || stopping ||
                pendingStoredStart != null || pendingStoredStop != null
            ) return false
            generation += 1
            PendingStoredStart(generation).also { pendingStoredStart = it }
        }
        scheduler.execute { loadStoredStart(ownership) }
        return true
    }

    fun start(record: SecureTrackingRecord): Boolean {
        val ownership = synchronized(lock) {
            if (
                destroyed || session != null || stopping ||
                pendingStoredStart != null || pendingStoredStop != null
            ) return false
            generation += 1
            installSessionLocked(record, generation) ?: return false
        }
        activateInstalledSession(record, ownership)
        return true
    }

    fun stop(): Boolean {
        val activeSession: ParticipantSession?
        val pendingStop: PendingStoredStop?
        synchronized(lock) {
            if (stopping) return true
            if (destroyed) return false
            activeSession = session
            val pendingStart = pendingStoredStart
            if (activeSession == null && pendingStart == null) return false
            stopping = true
            generation += 1
            cancelTimersLocked()
            pending.clear()
            pendingStop = if (activeSession == null) {
                PendingStoredStop(pendingStartGeneration = requireNotNull(pendingStart).generation)
                    .also {
                        pendingStoredStart = null
                        pendingStoredStop = it
                    }
            } else {
                null
            }
        }
        locationSource.stop()
        if (activeSession != null) {
            emit(status(activeSession, "stopping", active = false))
            scheduler.execute { completeStop(activeSession) }
        } else {
            emit(pendingStartStatus("stopping", active = false), null)
            scheduler.execute { completePendingStoredStop(requireNotNull(pendingStop)) }
        }
        return true
    }

    fun destroy() {
        val current: ParticipantSession?
        synchronized(lock) {
            if (destroyed) return
            destroyed = true
            generation += 1
            current = session
            session = null
            stopping = false
            pendingStoredStart = null
            pendingStoredStop = null
            publishInFlight = false
            pending.clear()
            cancelTimersLocked()
        }
        locationSource.stop()
        if (current != null) statusSink(current, NativeTrackingStatus.stopped())
        if (current != null) {
            scheduler.execute { store.clearMatchingSession(current) }
        }
        scheduler.shutdown()
    }

    fun currentStatus(): NativeTrackingStatus = synchronized(lock) {
        val current = session
        when {
            current != null -> status(
                current,
                if (stopping) "stopping" else if (publishInFlight) "sharing" else "waiting",
                active = !stopping,
            )
            pendingStoredStop != null -> pendingStartStatus("stopping", active = false)
            pendingStoredStart != null -> pendingStartStatus("starting", active = true)
            else -> NativeTrackingStatus.stopped()
        }
    }

    private fun loadStoredStart(ownership: PendingStoredStart) {
        val shouldLoad = synchronized(lock) {
            pendingStoredStart == ownership ||
                pendingStoredStop?.pendingStartGeneration == ownership.generation
        }
        if (!shouldLoad) return
        val record = store.load()
        var failed = false
        val activeOwnership = synchronized(lock) {
            when {
                pendingStoredStart == ownership -> {
                    pendingStoredStart = null
                    installSessionLocked(record, ownership.generation).also {
                        failed = it == null
                        if (failed) generation += 1
                    }
                }
                pendingStoredStop?.pendingStartGeneration == ownership.generation -> {
                    if (record != null) pendingStoredStop?.loadedSession = record.session
                    null
                }
                else -> null
            }
        }
        if (activeOwnership != null && record != null) {
            activateInstalledSession(record, activeOwnership)
        } else if (failed) {
            val failedSession = record?.session
            if (failedSession != null) store.clearMatchingSession(failedSession)
            emit(NativeTrackingStatus.stopped(SafeText.STORAGE_FAILURE), failedSession)
            stoppedSink(failedSession)
        }
    }

    private fun installSessionLocked(
        record: SecureTrackingRecord?,
        operationGeneration: Long,
    ): Ownership? {
        val current = record?.session ?: return null
        if (destroyed || stopping || !current.isValid(clock.now())) return null
        session = current
        terminalRecorded = false
        terminalSession = null
        stopCompletionStarted = false
        publishInFlight = false
        sessionHadUncertainPut = false
        lastAcceptedSequence = current.lastAcceptedSequence
        pending.clear()
        record.pendingSample?.let(pending::replace)
        return Ownership(operationGeneration, current)
    }

    private fun activateInstalledSession(
        record: SecureTrackingRecord,
        ownership: Ownership,
    ) {
        if (!owns(ownership)) return
        emitIfOwned(ownership, "waiting")
        if (!owns(ownership)) return
        val locationStarted = synchronized(lock) {
            if (!ownsLocked(ownership)) return
            locationSource.start(::receiveFix, ::receiveLocationUnavailable)
        }
        if (!locationStarted) {
            scheduler.execute { failCurrent(ownership.session, "location_disabled") }
            return
        }
        if (!owns(ownership)) {
            locationSource.stop()
            return
        }
        scheduleExpiry(ownership)
        synchronized(lock) {
            if (ownsLocked(ownership) && record.pendingSample != null) {
                scheduleCadenceLocked(0, ownership.session, ownership.generation)
            }
        }
    }

    private fun completePendingStoredStop(stopOwnership: PendingStoredStop) {
        val loadedSession = synchronized(lock) {
            if (pendingStoredStop !== stopOwnership) return
            stopOwnership.loadedSession
        }
        val stoppingSession = loadedSession ?: store.load()?.session
        val clearOutcome = stoppingSession?.let(publisher::clear)
        val storeOutcome = if (stoppingSession == null) {
            StoreMutationResult.STORAGE_FAILURE
        } else {
            store.clearMatchingSession(stoppingSession)
        }
        val warning = if (
            clearOutcome != null &&
            (clearOutcome is ClearOutcome.Cleared || clearOutcome is ClearOutcome.NotFound) &&
            storeOutcome != StoreMutationResult.STORAGE_FAILURE
        ) {
            null
        } else {
            SafeText.UNCERTAIN_STOP
        }
        synchronized(lock) {
            if (pendingStoredStop !== stopOwnership) return
            pendingStoredStop = null
            stopping = false
            publishInFlight = false
        }
        val stoppedStatus = if (stoppingSession == null) {
            NativeTrackingStatus.stopped(warning)
        } else {
            NativeTrackingStatus(
                outingSlug = stoppingSession.outingSlug,
                participantId = stoppingSession.participantId,
                active = false,
                state = "stopped",
                lastPublishedAt = null,
                pendingSample = false,
                stopWarning = warning,
            )
        }
        emit(stoppedStatus, stoppingSession)
        stoppedSink(stoppingSession)
    }

    private fun pendingStartStatus(state: String, active: Boolean): NativeTrackingStatus =
        NativeTrackingStatus(
            outingSlug = null,
            participantId = null,
            active = active,
            state = state,
            lastPublishedAt = null,
            pendingSample = false,
            stopWarning = null,
        )

    private fun receiveFix(fix: RawLocationFix) {
        val ownership = synchronized(lock) {
            val current = session ?: return
            if (destroyed || stopping) return
            Ownership(generation, current)
        }
        val queuedAt = clock.now()
        val normalized = LocationNormalizer.normalize(fix, sampleId(), queuedAt) ?: run {
            emitIfOwned(ownership, "waiting")
            return
        }
        if (!normalized.isValid(queuedAt)) {
            emitIfOwned(ownership, "waiting")
            return
        }
        scheduler.execute { storeAndQueue(ownership, normalized) }
    }

    private fun storeAndQueue(ownership: Ownership, sample: NormalizedLocationSample) {
        if (!owns(ownership)) return
        when (store.replacePending(ownership.session, sample)) {
            PendingWriteResult.STORED -> synchronized(lock) {
                if (!ownsLocked(ownership)) return
                pending.replace(sample)
                emitLocked(status(ownership.session, "sharing", active = true))
                if (!publishInFlight && cadenceTask == null && retryTask == null) {
                    scheduleCadenceLocked(publicationDelay(), ownership.session, ownership.generation)
                }
            }
            PendingWriteResult.IGNORED_OLDER -> Unit
            PendingWriteResult.SESSION_MISMATCH -> obsoleteLocalSession(ownership)
            PendingWriteResult.STORAGE_FAILURE -> failCurrent(
                ownership.session,
                "native_tracking_failure",
                SafeText.STORAGE_FAILURE,
            )
        }
    }

    private fun receiveLocationUnavailable() {
        val ownership = synchronized(lock) {
            val current = session ?: return
            Ownership(generation, current)
        }
        emitIfOwned(ownership, "waiting")
    }

    private fun scheduleCadenceLocked(
        delayMs: Long,
        current: ParticipantSession,
        operationGeneration: Long,
    ) {
        if (
            destroyed || stopping || publishInFlight || cadenceTask != null ||
            retryTask != null || pending.peek() == null
        ) return
        cadenceTask = scheduler.schedule(delayMs) {
            synchronized(lock) { cadenceTask = null }
            beginPublish(Ownership(operationGeneration, current))
        }
    }

    private fun scheduleRetry(ownership: Ownership) {
        synchronized(lock) {
            if (!ownsLocked(ownership) || retryTask != null) return
            cadenceTask?.cancel()
            cadenceTask = null
            retryTask = scheduler.schedule(retryPolicy.takeDelay()) {
                synchronized(lock) { retryTask = null }
                beginPublish(ownership)
            }
        }
    }

    private fun beginPublish(ownership: Ownership) {
        val sample: NormalizedLocationSample
        val sequence: Long
        synchronized(lock) {
            if (!ownsLocked(ownership) || publishInFlight) return
            sample = pending.take() ?: return
            sequence = SequenceAllocator.next(clock.epochMilliseconds(), lastAcceptedSequence)
                ?: run {
                    scheduler.execute { failCurrent(ownership.session, "sequence_exhausted") }
                    return
                }
            publishInFlight = true
        }
        publish(ownership, sample, sequence, conflictRetried = false)
    }

    private fun publish(
        ownership: Ownership,
        sample: NormalizedLocationSample,
        sequence: Long,
        conflictRetried: Boolean,
    ) {
        val outcome = publisher.publish(ownership.session, sequence, sample)
        if (outcome is PutOutcome.Transient && outcome.uncertainTransport) {
            synchronized(lock) { sessionHadUncertainPut = true }
        }
        if (outcome is PutOutcome.NotFound) {
            handleTerminalNotFound(ownership)
            return
        }
        if (!owns(ownership)) return
        when (outcome) {
            is PutOutcome.Accepted -> accepted(ownership, sample, outcome.sequence)
            PutOutcome.SequenceConflict -> if (conflictRetried) {
                discardAndContinue(ownership, sample)
            } else {
                recoverSequence(ownership, sample)
            }
            PutOutcome.InvalidFix,
            PutOutcome.DefiniteFailure,
            -> discardAndContinue(ownership, sample)
            is PutOutcome.Transient -> {
                synchronized(lock) {
                    if (!ownsLocked(ownership)) return
                    if (pending.peek() == null) pending.replace(sample)
                    publishInFlight = false
                    emitLocked(status(ownership.session, "offline_retrying", active = true))
                }
                scheduleRetry(ownership)
            }
            PutOutcome.NotFound -> Unit
        }
    }

    private fun accepted(
        ownership: Ownership,
        sample: NormalizedLocationSample,
        acceptedSequence: Long,
    ) {
        val sampleClear = store.clearMatchingSample(ownership.session, sample.sampleId)
        val sequenceUpdate = store.updateSequence(ownership.session, acceptedSequence)
        synchronized(lock) {
            if (!ownsLocked(ownership)) return
            lastAcceptedSequence = acceptedSequence
            lastPublishedAt = clock.now()
            lastPublishedElapsedMs = clock.elapsedMilliseconds()
            retryPolicy.reset()
            publishInFlight = false
            val warning = if (
                sampleClear == StoreMutationResult.STORAGE_FAILURE ||
                sequenceUpdate == StoreMutationResult.STORAGE_FAILURE
            ) SafeText.STORAGE_FAILURE else null
            emitLocked(status(ownership.session, "sharing", active = true, warning = warning))
            schedulePendingLocked(ownership)
        }
    }

    private fun discardAndContinue(
        ownership: Ownership,
        sample: NormalizedLocationSample,
    ) {
        val result = store.clearMatchingSample(ownership.session, sample.sampleId)
        synchronized(lock) {
            if (!ownsLocked(ownership)) return
            publishInFlight = false
            emitLocked(
                status(
                    ownership.session,
                    "waiting",
                    active = true,
                    warning = if (result == StoreMutationResult.STORAGE_FAILURE) {
                        SafeText.STORAGE_FAILURE
                    } else {
                        null
                    },
                ),
            )
            schedulePendingLocked(ownership)
        }
    }

    private fun recoverSequence(
        ownership: Ownership,
        conflictedSample: NormalizedLocationSample,
    ) {
        when (val recovery = publisher.recoverSequence(ownership.session)) {
            is LiveSequenceOutcome.NotFound -> handleTerminalNotFound(ownership)
            is LiveSequenceOutcome.Accepted -> {
                if (!owns(ownership)) return
                synchronized(lock) {
                    recovery.sequence?.let { lastAcceptedSequence = maxOf(lastAcceptedSequence, it) }
                }
                val latest = synchronized(lock) { pending.take() } ?: conflictedSample
                val sequence = synchronized(lock) {
                    SequenceAllocator.next(clock.epochMilliseconds(), lastAcceptedSequence)
                }
                if (sequence == null) {
                    failCurrent(ownership.session, "sequence_exhausted")
                    return
                }
                publish(ownership, latest, sequence, conflictRetried = true)
            }
            is LiveSequenceOutcome.Transient -> {
                if (recovery.uncertainTransport) {
                    synchronized(lock) { sessionHadUncertainPut = true }
                }
                synchronized(lock) {
                    if (!ownsLocked(ownership)) return
                    if (pending.peek() == null) pending.replace(conflictedSample)
                    publishInFlight = false
                    emitLocked(status(ownership.session, "offline_retrying", active = true))
                }
                scheduleRetry(ownership)
            }
            LiveSequenceOutcome.DefiniteFailure -> discardAndContinue(
                ownership,
                conflictedSample,
            )
        }
    }

    private fun handleTerminalNotFound(ownership: Ownership) {
        store.clearMatchingSession(ownership.session)
        val clearCurrent: Boolean
        synchronized(lock) {
            if (terminalRecorded && terminalSession?.identityMatches(ownership.session) == true) {
                return
            }
            terminalRecorded = true
            terminalSession = ownership.session
            clearCurrent = session?.identityMatches(ownership.session) == true
            if (clearCurrent) {
                generation += 1
                session = null
                stopping = false
                publishInFlight = false
                pending.clear()
                cancelTimersLocked()
            }
        }
        if (clearCurrent) locationSource.stop()
        terminalSink(ownership.session, "outing_not_found", clearCurrent)
        if (clearCurrent) stoppedSink(ownership.session)
    }

    private fun completeStop(stoppingSession: ParticipantSession) {
        synchronized(lock) {
            if (stopCompletionStarted || session?.identityMatches(stoppingSession) != true) return
            stopCompletionStarted = true
        }
        val clearOutcome = publisher.clear(stoppingSession)
        val storeOutcome = store.clearMatchingSession(stoppingSession)
        val warning = synchronized(lock) {
            val clearSucceeded = clearOutcome is ClearOutcome.Cleared || clearOutcome is ClearOutcome.NotFound
            if (
                clearSucceeded &&
                !sessionHadUncertainPut &&
                storeOutcome != StoreMutationResult.STORAGE_FAILURE
            ) null else SafeText.UNCERTAIN_STOP
        }
        synchronized(lock) {
            if (session?.identityMatches(stoppingSession) != true) return
            session = null
            stopping = false
            publishInFlight = false
        }
        emit(
            NativeTrackingStatus(
                outingSlug = stoppingSession.outingSlug,
                participantId = stoppingSession.participantId,
                active = false,
                state = "stopped",
                lastPublishedAt = synchronized(lock) { lastPublishedAt },
                pendingSample = false,
                stopWarning = warning,
            ),
            stoppingSession,
        )
        stoppedSink(stoppingSession)
    }

    private fun failCurrent(
        failedSession: ParticipantSession,
        code: String,
        warning: String? = null,
    ) {
        val owns: Boolean
        synchronized(lock) {
            owns = session?.identityMatches(failedSession) == true
            if (!owns) return
            generation += 1
            session = null
            stopping = false
            publishInFlight = false
            pending.clear()
            cancelTimersLocked()
        }
        locationSource.stop()
        store.clearMatchingSession(failedSession)
        emit(
            NativeTrackingStatus(
                outingSlug = failedSession.outingSlug,
                participantId = failedSession.participantId,
                active = false,
                state = "stopped",
                lastPublishedAt = synchronized(lock) { lastPublishedAt },
                pendingSample = false,
                stopWarning = warning,
            ),
            failedSession,
        )
        if (code == "outing_not_found") {
            terminalSink(failedSession, code, true)
        }
        stoppedSink(failedSession)
    }

    private fun obsoleteLocalSession(ownership: Ownership) {
        synchronized(lock) {
            if (!ownsLocked(ownership)) return
            generation += 1
            session = null
            stopping = false
            publishInFlight = false
            pending.clear()
            cancelTimersLocked()
        }
        locationSource.stop()
        stoppedSink(ownership.session)
    }

    private fun scheduleExpiry(ownership: Ownership) {
        val delay = try {
            Duration.between(clock.now(), ownership.session.outingExpiresAt)
                .toMillis()
                .coerceAtLeast(0)
        } catch (_: ArithmeticException) {
            Long.MAX_VALUE
        }
        synchronized(lock) {
            if (!ownsLocked(ownership)) return
            expiryTask = scheduler.schedule(delay) {
                if (owns(ownership)) stop()
            }
        }
    }

    private fun schedulePendingLocked(ownership: Ownership) {
        if (pending.peek() != null) {
            scheduleCadenceLocked(publicationDelay(), ownership.session, ownership.generation)
        }
    }

    private fun publicationDelay(): Long {
        val publishedAt = synchronized(lock) { lastPublishedElapsedMs } ?: return 0
        return (publicationIntervalMs - (clock.elapsedMilliseconds() - publishedAt)).coerceAtLeast(0)
    }

    private fun emitIfOwned(ownership: Ownership, state: String) {
        synchronized(lock) {
            if (!ownsLocked(ownership)) return
            emitLocked(status(ownership.session, state, active = true))
        }
    }

    private fun status(
        current: ParticipantSession,
        state: String,
        active: Boolean,
        warning: String? = null,
    ): NativeTrackingStatus = NativeTrackingStatus(
        outingSlug = current.outingSlug,
        participantId = current.participantId,
        active = active,
        state = state,
        lastPublishedAt = synchronized(lock) { lastPublishedAt },
        pendingSample = synchronized(lock) { pending.peek() != null },
        stopWarning = warning,
    )

    private fun emit(
        status: NativeTrackingStatus,
        ownerSession: ParticipantSession? = synchronized(lock) { session },
    ) {
        statusSink(ownerSession, status)
        notificationSink(status)
    }

    private fun emitLocked(status: NativeTrackingStatus) {
        statusSink(session, status)
        notificationSink(status)
    }

    private fun owns(ownership: Ownership): Boolean = synchronized(lock) {
        ownsLocked(ownership)
    }

    private fun ownsLocked(ownership: Ownership): Boolean =
        !destroyed &&
            !stopping &&
            generation == ownership.generation &&
            session?.identityMatches(ownership.session) == true

    private fun cancelTimersLocked() {
        cadenceTask?.cancel()
        cadenceTask = null
        retryTask?.cancel()
        retryTask = null
        expiryTask?.cancel()
        expiryTask = null
    }

    private data class Ownership(
        val generation: Long,
        val session: ParticipantSession,
    )

    private data class PendingStoredStart(val generation: Long)

    private data class PendingStoredStop(
        val pendingStartGeneration: Long,
        var loadedSession: ParticipantSession? = null,
    )
}
