package io.github.victorgabillon.sugarglider

import java.time.Instant

internal val TEST_NOW: Instant = Instant.parse("2026-08-06T12:00:00Z")
internal const val TEST_ORIGIN = "https://example.test"
internal const val TEST_SLUG = "outing_slug_1234567890"
internal const val TEST_PARTICIPANT = "participant_1234567890"
internal const val TEST_TOKEN = "synthetic_participant_token_1234567890"

internal fun testSession(
    origin: String = TEST_ORIGIN,
    participantId: String = TEST_PARTICIPANT,
    token: String = TEST_TOKEN,
    startedAt: Instant = TEST_NOW,
): ParticipantSession = ParticipantSession(
    serverOrigin = origin,
    outingSlug = TEST_SLUG,
    participantId = participantId,
    participantToken = token,
    outingExpiresAt = TEST_NOW.plusSeconds(3_600),
    lastAcceptedSequence = 10,
    startedAt = startedAt,
)

internal fun testSample(
    id: String = "sample-1234567890",
    capturedAt: Instant = TEST_NOW,
    queuedAt: Instant = TEST_NOW,
    latitude: Double = 48.8,
): NormalizedLocationSample = NormalizedLocationSample(
    sampleId = id,
    capturedAt = capturedAt,
    queuedAt = queuedAt,
    latitude = latitude,
    longitude = 2.1,
    accuracyM = 8.0,
    altitudeM = 92.0,
    speedMS = 1.5,
    headingDeg = 180.0,
)
