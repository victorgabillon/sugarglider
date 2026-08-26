package io.github.victorgabillon.sugarglider

import java.time.Instant
import java.util.ArrayDeque
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeTrackingEngineTest {
    @Test
    fun stopBeforeStoredLoadCancelsStartAndClearsExactSessionOnce() {
        val rig = EngineRig()
        rig.store.record = requireNotNull(rig.store.record).copy(
            pendingSample = testSample(),
        )
        assertTrue(rig.engine.startStored())
        assertEquals("starting", rig.engine.currentStatus().state)
        assertTrue(rig.engine.stop())
        assertTrue(rig.engine.stop())

        rig.scheduler.runReady()

        assertFalse(rig.engine.currentStatus().active)
        assertEquals("stopped", rig.engine.currentStatus().state)
        assertEquals(0, rig.location.startCalls)
        assertTrue(rig.publisher.publishedIds.isEmpty())
        assertNull(rig.store.record)
        assertEquals(1, rig.publisher.clearCalls)
        assertEquals(1, rig.stoppedCount)
    }

    @Test
    fun stopDuringStoredLoadPreventsStaleLoaderFromInstallingSession() {
        val rig = EngineRig()
        val load = BlockingLoad()
        rig.store.blockingLoad = load
        assertTrue(rig.engine.startStored())
        val worker = rig.scheduler.runNextImmediateInThread()
        assertTrue(load.entered.await(2, TimeUnit.SECONDS))

        assertTrue(rig.engine.stop())
        load.release.countDown()
        worker.join(2_000)
        assertFalse(worker.isAlive)
        rig.scheduler.runReady()

        assertFalse(rig.engine.currentStatus().active)
        assertEquals(0, rig.location.startCalls)
        assertTrue(rig.publisher.publishedIds.isEmpty())
        assertNull(rig.store.record)
        assertEquals(1, rig.stoppedCount)
    }

    @Test
    fun pendingStartStopStorageFailureIsCaughtAndWarned() {
        val rig = EngineRig()
        rig.store.clearSessionOutcome = StoreMutationResult.STORAGE_FAILURE
        assertTrue(rig.engine.startStored())
        assertTrue(rig.engine.stop())

        rig.scheduler.runReady()

        assertEquals(0, rig.location.startCalls)
        assertTrue(rig.publisher.publishedIds.isEmpty())
        assertEquals(SafeText.UNCERTAIN_STOP, rig.statuses.last().stopWarning)
        assertEquals(1, rig.stoppedCount)
    }

    @Test
    fun stalePendingStartCleanupCannotDeleteNewerExactSession() {
        val rig = EngineRig()
        val original = requireNotNull(rig.store.record)
        val newer = original.copy(
            session = original.session.copy(
                participantToken = "replacement_participant_token_1234567890",
                startedAt = TEST_NOW.plusMillis(1),
            ),
        )
        val load = BlockingLoad()
        rig.store.blockingLoad = load
        assertTrue(rig.engine.startStored())
        val worker = rig.scheduler.runNextImmediateInThread()
        assertTrue(load.entered.await(2, TimeUnit.SECONDS))
        assertTrue(rig.engine.stop())
        rig.store.record = newer

        load.release.countDown()
        worker.join(2_000)
        assertFalse(worker.isAlive)
        rig.scheduler.runReady()

        assertEquals(newer, rig.store.record)
        assertEquals(0, rig.location.startCalls)
        assertEquals(1, rig.stoppedCount)
    }

    @Test
    fun normalStoredStartLoadsAndStartsLocationExactlyOnce() {
        val rig = EngineRig()
        assertTrue(rig.engine.startStored())
        assertFalse(rig.engine.startStored())

        rig.scheduler.runReady()

        assertTrue(rig.engine.currentStatus().active)
        assertEquals("waiting", rig.engine.currentStatus().state)
        assertEquals(1, rig.store.loadCalls)
        assertEquals(1, rig.location.startCalls)
        assertEquals(0, rig.stoppedCount)
    }

    @Test
    fun firstFixPublishesAndFiveSecondCadenceKeepsOnlyNewestFix() {
        val rig = EngineRig()
        rig.start()
        rig.location.fix(rig.fix(0))
        rig.scheduler.runReady()
        assertEquals(listOf("generated-sample-0"), rig.publisher.publishedIds)

        rig.clock.advance(1_000)
        rig.location.fix(rig.fix(1))
        rig.location.fix(rig.fix(2))
        rig.scheduler.runReady()
        assertEquals(1, rig.publisher.publishedIds.size)
        rig.scheduler.advance(3_999)
        assertEquals(1, rig.publisher.publishedIds.size)
        rig.scheduler.advance(1)
        assertEquals(
            listOf("generated-sample-0", "generated-sample-2"),
            rig.publisher.publishedIds,
        )
    }

    @Test
    fun outOfOrderFixIsIgnoredWithoutStopping() {
        val rig = EngineRig()
        rig.start()
        rig.location.fix(rig.fix(2))
        rig.scheduler.runImmediate()
        rig.location.fix(rig.fix(1))
        rig.scheduler.runImmediate()
        rig.scheduler.runReady()
        assertTrue(rig.engine.currentStatus().active)
        assertEquals(1, rig.publisher.publishedIds.size)
        assertTrue(rig.terminals.isEmpty())
    }

    @Test
    fun transientRetryRetainsOnlyLatestAndNeverRunsTwoPuts() {
        val rig = EngineRig()
        rig.publisher.putOutcomes.add(PutOutcome.Transient(uncertainTransport = true))
        rig.publisher.putOutcomes.add(PutOutcome.Accepted(20))
        rig.start()
        rig.location.fix(rig.fix(0))
        rig.scheduler.runReady()
        rig.location.fix(rig.fix(1))
        rig.location.fix(rig.fix(2))
        rig.scheduler.runReady()
        rig.scheduler.advance(1_000)
        assertEquals(
            listOf("generated-sample-0", "generated-sample-2"),
            rig.publisher.publishedIds,
        )
        assertEquals(1, rig.publisher.maximumConcurrentPuts)
    }

    @Test
    fun storageWriteFailureStopsSafelyAndOlderWriteDoesNot() {
        val rig = EngineRig()
        rig.start()
        rig.store.nextPending = PendingWriteResult.IGNORED_OLDER
        rig.location.fix(rig.fix(0))
        rig.scheduler.runReady()
        assertTrue(rig.engine.currentStatus().active)
        rig.store.nextPending = PendingWriteResult.STORAGE_FAILURE
        rig.location.fix(rig.fix(1))
        rig.scheduler.runReady()
        assertFalse(rig.engine.currentStatus().active)
        assertTrue(rig.statuses.last().stopWarning?.contains("storage", true) == true)
    }

    @Test
    fun stopBeforeDirectNotFoundStillClearsAndEmitsExactlyOnce() {
        val rig = EngineRig()
        val gate = BlockingPut(PutOutcome.NotFound)
        rig.publisher.blockingPut = gate
        rig.start()
        rig.location.fix(rig.fix(0))
        rig.scheduler.runImmediate()
        val worker = rig.scheduler.runNextReadyInThread()
        assertTrue(gate.entered.await(2, TimeUnit.SECONDS))
        assertTrue(rig.engine.stop())
        gate.release.countDown()
        worker.join(2_000)
        rig.scheduler.runReady()
        assertEquals(1, rig.terminals.size)
        assertEquals("outing_not_found", rig.terminals.single().second)
        assertNull(rig.store.record)
        assertFalse(rig.engine.currentStatus().active)
    }

    @Test
    fun stopBeforeSequenceRecoveryNotFoundStillClearsAndEmitsExactlyOnce() {
        val rig = EngineRig()
        val recovery = BlockingRecovery(LiveSequenceOutcome.NotFound)
        rig.publisher.putOutcomes.add(PutOutcome.SequenceConflict)
        rig.publisher.blockingRecovery = recovery
        rig.start()
        rig.location.fix(rig.fix(0))
        rig.scheduler.runImmediate()
        val worker = rig.scheduler.runNextReadyInThread()
        assertTrue(recovery.entered.await(2, TimeUnit.SECONDS))
        assertTrue(rig.engine.stop())
        recovery.release.countDown()
        worker.join(2_000)
        rig.scheduler.runReady()
        assertEquals(1, rig.terminals.size)
        assertNull(rig.store.record)
    }

    @Test
    fun terminalCleanupCannotDeleteNewerExactSession() {
        val rig = EngineRig()
        val gate = BlockingPut(PutOutcome.NotFound)
        rig.publisher.blockingPut = gate
        rig.start()
        rig.location.fix(rig.fix(0))
        rig.scheduler.runImmediate()
        val worker = rig.scheduler.runNextReadyInThread()
        assertTrue(gate.entered.await(2, TimeUnit.SECONDS))
        val newer = rig.session.copy(
            participantToken = "replacement_participant_token_1234567890",
        )
        rig.store.record = SecureTrackingRecord(newer, null)
        gate.release.countDown()
        worker.join(2_000)
        assertEquals(newer, rig.store.record?.session)
        assertEquals(1, rig.terminals.size)
    }

    @Test
    fun deleteIsSerializedAfterInflightPutAndStopIsIdempotent() {
        val rig = EngineRig()
        val gate = BlockingPut(PutOutcome.Accepted(20))
        rig.publisher.blockingPut = gate
        rig.start()
        rig.location.fix(rig.fix(0))
        rig.scheduler.runImmediate()
        val worker = rig.scheduler.runNextReadyInThread()
        assertTrue(gate.entered.await(2, TimeUnit.SECONDS))
        assertTrue(rig.engine.stop())
        assertTrue(rig.engine.stop())
        assertEquals(0, rig.publisher.clearCalls)
        gate.release.countDown()
        worker.join(2_000)
        rig.scheduler.runReady()
        assertEquals(1, rig.publisher.clearCalls)
        assertEquals(1, rig.stoppedCount)
    }

    @Test
    fun stoppingRetainsOldSessionAndRejectsSameOrDifferentStartUntilDeleteFinishes() {
        val rig = EngineRig()
        val clear = BlockingClear(ClearOutcome.Cleared)
        rig.publisher.blockingClear = clear
        rig.start()
        assertTrue(rig.engine.stop())
        assertEquals("stopping", rig.engine.currentStatus().state)
        assertFalse(rig.engine.currentStatus().active)

        val worker = rig.scheduler.runNextImmediateInThread()
        assertTrue(clear.entered.await(2, TimeUnit.SECONDS))
        val originalRecord = requireNotNull(rig.store.record)
        val different = originalRecord.copy(
            session = originalRecord.session.copy(
                participantId = "different_participant_12345",
                participantToken = "different_synthetic_participant_token_12345",
            ),
        )
        assertFalse(rig.engine.start(originalRecord))
        assertFalse(rig.engine.start(different))
        assertEquals(originalRecord, rig.store.record)

        clear.release.countDown()
        worker.join(2_000)
        assertFalse(worker.isAlive)
        assertEquals("stopped", rig.engine.currentStatus().state)
        assertNull(rig.store.record)
        assertEquals(1, rig.stoppedCount)

        assertEquals(
            StoreMutationResult.APPLIED,
            rig.store.saveSession(different.session),
        )
        assertTrue(rig.engine.start(requireNotNull(rig.store.record)))
        assertEquals(different.session.participantId, rig.engine.currentStatus().participantId)
    }

    @Test
    fun uncertainPutAndDeleteProduceHonestStopWarning() {
        val rig = EngineRig()
        rig.publisher.putOutcomes.add(PutOutcome.Transient(uncertainTransport = true))
        rig.publisher.clearOutcome = ClearOutcome.Transient(uncertainTransport = true)
        rig.start()
        rig.location.fix(rig.fix(0))
        rig.scheduler.runReady()
        assertTrue(rig.engine.stop())
        rig.scheduler.runReady()
        assertEquals(SafeText.UNCERTAIN_STOP, rig.statuses.last().stopWarning)
    }

    @Test
    fun destroyLeavesStatusInactiveAndCannotResume() {
        val rig = EngineRig()
        rig.start()
        rig.engine.destroy()
        rig.scheduler.runReady()
        assertFalse(rig.statuses.last().active)
        assertFalse(rig.engine.start(SecureTrackingRecord(rig.session, null)))
    }
}

private class EngineRig {
    val clock = FakeClock()
    val scheduler = ManualScheduler()
    val location = FakeLocationSource()
    val session = testSession()
    val store = FakeSecureStore(SecureTrackingRecord(session, null))
    val publisher = FakePublisher()
    val statuses = mutableListOf<NativeTrackingStatus>()
    val terminals = mutableListOf<Triple<ParticipantSession, String, Boolean>>()
    var stoppedCount = 0
    private var sampleCounter = 0
    val engine = NativeTrackingEngine(
        store = store,
        publisher = publisher,
        locationSource = location,
        scheduler = scheduler,
        clock = clock,
        statusSink = { _, status -> statuses += status },
        terminalSink = { failed, code, clear -> terminals += Triple(failed, code, clear) },
        notificationSink = {},
        stoppedSink = { stoppedCount += 1 },
        sampleId = { "generated-sample-${sampleCounter++}" },
    )

    fun start() {
        assertTrue(engine.start(requireNotNull(store.record)))
    }

    fun fix(offset: Int): RawLocationFix = RawLocationFix(
        latitude = 48.8 + offset / 10_000.0,
        longitude = 2.1,
        accuracyM = 8.0,
        capturedAtEpochMs = clock.now().minusMillis((100 - offset).toLong()).toEpochMilli(),
        altitudeM = null,
        speedMS = null,
        headingDeg = null,
    )
}

private class FakeClock : AppClock {
    private var elapsed = 0L
    override fun now(): Instant = TEST_NOW.plusMillis(elapsed)
    override fun epochMilliseconds(): Long = now().toEpochMilli()
    override fun elapsedMilliseconds(): Long = elapsed
    fun advance(value: Long) {
        elapsed += value
    }
}

private class ManualScheduler : NativeTaskScheduler {
    private data class Timed(val due: Long, val order: Long, val task: () -> Unit) {
        var cancelled = false
    }

    private val immediate = ArrayDeque<() -> Unit>()
    private val timed = mutableListOf<Timed>()
    private var now = 0L
    private var order = 0L
    private var shutdown = false

    @Synchronized
    override fun execute(task: () -> Unit) {
        if (!shutdown) immediate.add(task)
    }

    @Synchronized
    override fun schedule(delayMs: Long, task: () -> Unit): ScheduledTask {
        val value = Timed(now + delayMs, order++, task)
        if (!shutdown) timed += value
        return ScheduledTask { synchronized(this) { value.cancelled = true } }
    }

    @Synchronized
    override fun shutdown() {
        shutdown = true
    }

    fun runImmediate() {
        while (true) {
            val task = synchronized(this) { immediate.poll() } ?: return
            task()
        }
    }

    fun runReady() {
        while (true) {
            runImmediate()
            val task = synchronized(this) {
                timed.filter { !it.cancelled && it.due <= now }
                    .minWithOrNull(compareBy<Timed>({ it.due }, { it.order }))
                    ?.also { timed.remove(it) }
                    ?.task
            } ?: return
            task()
        }
    }

    fun advance(value: Long) {
        synchronized(this) { now += value }
        runReady()
    }

    fun runNextReadyInThread(): Thread {
        val task = synchronized(this) {
            timed.filter { !it.cancelled && it.due <= now }
                .minWithOrNull(compareBy<Timed>({ it.due }, { it.order }))
                ?.also { timed.remove(it) }
                ?.task
        } ?: error("no ready scheduled task")
        return Thread(task).also { it.start() }
    }

    fun runNextImmediateInThread(): Thread {
        val task = synchronized(this) { immediate.poll() } ?: error("no immediate task")
        return Thread(task).also { it.start() }
    }
}

private class FakeLocationSource : LocationSource {
    private var onFix: ((RawLocationFix) -> Unit)? = null
    var startCalls = 0

    override fun start(onFix: (RawLocationFix) -> Unit, onUnavailable: () -> Unit): Boolean {
        startCalls += 1
        this.onFix = onFix
        return true
    }

    override fun stop() {
        onFix = null
    }

    fun fix(value: RawLocationFix) {
        requireNotNull(onFix)(value)
    }
}

private class FakeSecureStore(initial: SecureTrackingRecord?) : SecureStateStore {
    var record = initial
    var nextPending: PendingWriteResult? = null
    var blockingLoad: BlockingLoad? = null
    var clearSessionOutcome: StoreMutationResult? = null
    var loadCalls = 0

    override fun load(): SecureTrackingRecord? {
        loadCalls += 1
        val snapshot = record
        blockingLoad.also { blockingLoad = null }?.let { blocked ->
            blocked.entered.countDown()
            assertTrue(blocked.release.await(2, TimeUnit.SECONDS))
        }
        return snapshot
    }
    override fun saveSession(session: ParticipantSession): StoreMutationResult {
        record = SecureTrackingRecord(session, null)
        return StoreMutationResult.APPLIED
    }

    override fun replacePending(
        session: ParticipantSession,
        sample: NormalizedLocationSample,
    ): PendingWriteResult {
        nextPending?.let { result ->
            nextPending = null
            return result
        }
        val current = record ?: return PendingWriteResult.SESSION_MISMATCH
        if (!current.session.identityMatches(session)) return PendingWriteResult.SESSION_MISMATCH
        val previous = current.pendingSample
        if (previous != null && sample.capturedAt < previous.capturedAt) {
            return PendingWriteResult.IGNORED_OLDER
        }
        record = current.copy(pendingSample = sample)
        return PendingWriteResult.STORED
    }

    override fun clearMatchingSample(
        session: ParticipantSession,
        sampleId: String,
    ): StoreMutationResult {
        val current = record ?: return StoreMutationResult.NO_MATCH
        if (!current.session.identityMatches(session)) return StoreMutationResult.SESSION_MISMATCH
        if (current.pendingSample?.sampleId != sampleId) return StoreMutationResult.NO_MATCH
        record = current.copy(pendingSample = null)
        return StoreMutationResult.APPLIED
    }

    override fun updateSequence(
        session: ParticipantSession,
        sequence: Long,
    ): StoreMutationResult {
        val current = record ?: return StoreMutationResult.NO_MATCH
        if (!current.session.identityMatches(session)) return StoreMutationResult.SESSION_MISMATCH
        record = current.copy(
            session = current.session.copy(lastAcceptedSequence = sequence),
        )
        return StoreMutationResult.APPLIED
    }

    override fun clearMatchingSession(session: ParticipantSession): StoreMutationResult {
        clearSessionOutcome?.let { return it }
        val current = record ?: return StoreMutationResult.NO_MATCH
        if (!current.session.identityMatches(session)) return StoreMutationResult.SESSION_MISMATCH
        record = null
        return StoreMutationResult.APPLIED
    }

    override fun clearAll(): StoreMutationResult {
        record = null
        return StoreMutationResult.APPLIED
    }
}

private data class BlockingPut(
    val outcome: PutOutcome,
    val entered: CountDownLatch = CountDownLatch(1),
    val release: CountDownLatch = CountDownLatch(1),
)

private data class BlockingRecovery(
    val outcome: LiveSequenceOutcome,
    val entered: CountDownLatch = CountDownLatch(1),
    val release: CountDownLatch = CountDownLatch(1),
)

private data class BlockingLoad(
    val entered: CountDownLatch = CountDownLatch(1),
    val release: CountDownLatch = CountDownLatch(1),
)

private data class BlockingClear(
    val outcome: ClearOutcome,
    val entered: CountDownLatch = CountDownLatch(1),
    val release: CountDownLatch = CountDownLatch(1),
)

private class FakePublisher : NativeTrackingPublisher {
    val putOutcomes = ArrayDeque<PutOutcome>()
    var blockingPut: BlockingPut? = null
    var blockingRecovery: BlockingRecovery? = null
    var blockingClear: BlockingClear? = null
    var clearOutcome: ClearOutcome = ClearOutcome.Cleared
    val publishedIds = mutableListOf<String>()
    var clearCalls = 0
    var concurrentPuts = 0
    var maximumConcurrentPuts = 0

    override fun publish(
        session: ParticipantSession,
        sequence: Long,
        sample: NormalizedLocationSample,
    ): PutOutcome {
        concurrentPuts += 1
        maximumConcurrentPuts = maxOf(maximumConcurrentPuts, concurrentPuts)
        publishedIds += sample.sampleId
        return try {
            val blocked = blockingPut.also { blockingPut = null }
            if (blocked != null) {
                blocked.entered.countDown()
                assertTrue(blocked.release.await(2, TimeUnit.SECONDS))
                blocked.outcome
            } else {
                putOutcomes.poll() ?: PutOutcome.Accepted(sequence)
            }
        } finally {
            concurrentPuts -= 1
        }
    }

    override fun recoverSequence(session: ParticipantSession): LiveSequenceOutcome {
        val blocked = blockingRecovery.also { blockingRecovery = null }
        if (blocked != null) {
            blocked.entered.countDown()
            assertTrue(blocked.release.await(2, TimeUnit.SECONDS))
            return blocked.outcome
        }
        return LiveSequenceOutcome.Accepted(session.lastAcceptedSequence)
    }

    override fun clear(session: ParticipantSession): ClearOutcome {
        clearCalls += 1
        val blocked = blockingClear.also { blockingClear = null }
        if (blocked != null) {
            blocked.entered.countDown()
            assertTrue(blocked.release.await(2, TimeUnit.SECONDS))
            return blocked.outcome
        }
        return clearOutcome
    }
}
