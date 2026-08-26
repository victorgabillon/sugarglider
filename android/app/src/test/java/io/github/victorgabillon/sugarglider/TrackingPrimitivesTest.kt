package io.github.victorgabillon.sugarglider

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

class TrackingPrimitivesTest {
    @Test
    fun validFullFixPreservesCapturedTime() {
        val sample = LocationNormalizer.normalize(validFix(), "sample-1234567890", TEST_NOW)
        assertEquals(TEST_NOW, sample?.capturedAt)
        assertEquals(92.0, sample?.altitudeM)
        assertEquals(180.0, sample?.headingDeg)
    }

    @Test
    fun nullableOptionalFieldsRemainNull() {
        val sample = LocationNormalizer.normalize(
            validFix().copy(altitudeM = null, speedMS = null, headingDeg = null),
            "sample-1234567890",
            TEST_NOW,
        )
        assertNull(sample?.altitudeM)
        assertNull(sample?.speedMS)
        assertNull(sample?.headingDeg)
    }

    @Test
    fun invalidRequiredFixFieldsAreRejected() {
        assertNull(LocationNormalizer.normalize(validFix().copy(latitude = 91.0), "sample-1-valid-id", TEST_NOW))
        assertNull(LocationNormalizer.normalize(validFix().copy(longitude = -181.0), "sample-1-valid-id", TEST_NOW))
        assertNull(LocationNormalizer.normalize(validFix().copy(accuracyM = 10_001.0), "sample-1-valid-id", TEST_NOW))
        assertNull(LocationNormalizer.normalize(validFix().copy(capturedAtEpochMs = 0), "sample-1-valid-id", TEST_NOW))
    }

    @Test
    fun invalidOptionalFieldsBecomeNullWithoutClamping() {
        val sample = LocationNormalizer.normalize(
            validFix().copy(altitudeM = 13_000.0, speedMS = -1.0, headingDeg = 360.0),
            "sample-1234567890",
            TEST_NOW,
        )
        assertNull(sample?.altitudeM)
        assertNull(sample?.speedMS)
        assertNull(sample?.headingDeg)
    }

    @Test
    fun sequenceUsesEpochThenMonotonicIncrement() {
        assertEquals(1_000L, SequenceAllocator.next(1_000, 20))
        assertEquals(1_001L, SequenceAllocator.next(900, 1_000))
    }

    @Test
    fun sequenceStopsAtJavascriptSafeLimit() {
        assertNull(SequenceAllocator.next(1, MAXIMUM_SAFE_SEQUENCE))
        assertNull(SequenceAllocator.next(MAXIMUM_SAFE_SEQUENCE + 1, 1))
    }

    @Test
    fun newestPendingReplacesOldWithoutHistory() {
        val pending = LatestOnlyPending()
        val old = testSample(id = "sample-old-123456", capturedAt = TEST_NOW.minusSeconds(1))
        val latest = testSample(id = "sample-new-123456")
        pending.replace(old)
        pending.replace(latest)
        assertSame(latest, pending.peek())
        assertSame(latest, pending.take())
        assertNull(pending.take())
    }

    @Test
    fun lateOlderSampleCannotReplaceLatest() {
        val pending = LatestOnlyPending()
        val latest = testSample(id = "sample-new-123456")
        pending.replace(latest)
        pending.replace(testSample(id = "sample-old-123456", capturedAt = TEST_NOW.minusSeconds(1)))
        assertSame(latest, pending.peek())
    }

    @Test
    fun retryPolicyCapsAroundThirtySeconds() {
        val policy = RetryPolicy()
        assertEquals(listOf(1_000L, 2_000L, 4_000L, 8_000L, 16_000L, 30_000L, 30_000L), List(7) { policy.takeDelay() })
    }

    @Test
    fun generationOwnershipRejectsOldCallbacks() {
        val owner = GenerationOwner()
        val old = owner.advance()
        val current = owner.advance()
        assertFalse(owner.owns(old))
        assertTrue(owner.owns(current))
    }

    @Test
    fun httpOutcomesAreSafelyClassified() {
        assertEquals(HttpOutcomeKind.NOT_FOUND, HttpOutcomeClassifier.classify(404, "outing_not_found"))
        assertEquals(HttpOutcomeKind.SEQUENCE_CONFLICT, HttpOutcomeClassifier.classify(409, "outing_position_sequence_conflict"))
        assertEquals(HttpOutcomeKind.INVALID_FIX, HttpOutcomeClassifier.classify(422, "outing_position_invalid"))
        assertEquals(HttpOutcomeKind.TRANSIENT, HttpOutcomeClassifier.classify(503, null))
        assertEquals(HttpOutcomeKind.TRANSIENT, HttpOutcomeClassifier.classify(null, null))
    }

    private fun validFix(): RawLocationFix = RawLocationFix(
        latitude = 48.8,
        longitude = 2.1,
        accuracyM = 8.0,
        capturedAtEpochMs = TEST_NOW.toEpochMilli(),
        altitudeM = 92.0,
        speedMS = 1.5,
        headingDeg = 180.0,
    )
}
