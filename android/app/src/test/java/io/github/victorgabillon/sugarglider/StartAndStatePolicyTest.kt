package io.github.victorgabillon.sugarglider

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

class StartAndStatePolicyTest {
    private val identity = TEST_SLUG to TEST_PARTICIPANT

    @Test
    fun serviceCannotStartWithoutExplicitConfirmedRequest() {
        assertRejected(conditions(explicitRequest = false), "permission_denied")
        assertRejected(conditions(disclosureConfirmed = false), "permission_denied")
        assertRejected(conditions(activityVisible = false), "permission_denied")
    }

    @Test
    fun approximateOnlyPermissionLeavesSharingStopped() {
        assertRejected(conditions(preciseLocationGranted = false), "approximate_location")
    }

    @Test
    fun missingNotificationPermissionLeavesSharingStopped() {
        assertRejected(
            conditions(notificationsGranted = false),
            "notification_permission_denied",
        )
    }

    @Test
    fun disabledLocationServicesLeaveSharingStopped() {
        assertRejected(conditions(locationServicesEnabled = false), "location_disabled")
    }

    @Test
    fun validExplicitStartIsAllowed() {
        assertSame(StartDecision.Allowed, StartPolicy.decide(conditions()))
    }

    @Test
    fun sameActiveParticipantIsIdempotent() {
        assertSame(
            StartDecision.AlreadyActive,
            StartPolicy.decide(conditions(activeIdentity = identity)),
        )
    }

    @Test
    fun differentParticipantCannotSilentlyReplaceActiveOne() {
        assertRejected(
            conditions(activeIdentity = TEST_SLUG to "different_participant_1"),
            "different_participant_active",
        )
    }

    @Test
    fun sameParticipantCannotRestartWhileStopOwnsLifecycle() {
        assertRejected(
            conditions(currentStatus = stoppingStatus(identity)),
            "stop_in_progress",
        )
    }

    @Test
    fun differentParticipantCannotReplaceStoppingSession() {
        assertRejected(
            conditions(
                currentStatus = stoppingStatus(
                    TEST_SLUG to "different_participant_1",
                ),
            ),
            "stop_in_progress",
        )
    }

    @Test
    fun everyNonterminalNativeLifecycleStateIsBusy() {
        for (state in listOf("starting", "waiting", "sharing", "offline_retrying", "stopping")) {
            assertTrue(stoppingStatus(identity).copy(state = state).isNativeBusy())
        }
        assertFalse(NativeTrackingStatus.stopped().isNativeBusy())
    }

    @Test
    fun oldStopCompletionCannotOwnServiceAfterNewStartId() {
        val guard = ServiceStartIdGuard()
        guard.recordStart(1)
        guard.recordStop(2)
        val oldStop = guard.captureStopStartId()
        guard.recordStart(3)
        assertFalse(guard.stopStillOwnsService(oldStop))
        assertEquals(3, guard.captureStopStartId())
        assertTrue(guard.stopStillOwnsService(3))
    }

    @Test
    fun serverChangeRemainsBlockedUntilStoppingIsComplete() {
        assertFalse(ServerChangePolicy.allowed(stoppingStatus(identity)))
        assertTrue(ServerChangePolicy.allowed(NativeTrackingStatus.stopped()))
    }

    @Test
    fun repositoryRemainsBusyUntilServiceShutdownCompletes() {
        val repository = NativeStatusRepository()
        val session = testSession()
        repository.activate(
            session,
            NativeTrackingStatus(
                TEST_SLUG,
                TEST_PARTICIPANT,
                false,
                "stopped",
                TEST_NOW,
                false,
                null,
            ),
        )
        assertTrue(repository.markServiceShutdownPending(session))
        assertEquals("stopping", repository.current().state)
        assertTrue(repository.current().isNativeBusy())
        assertFalse(ServerChangePolicy.allowed(repository.current()))
        repository.completeServiceShutdown()
        assertEquals("stopped", repository.current().state)
        assertFalse(repository.current().isNativeBusy())
    }

    @Test
    fun oldServiceShutdownCannotReplaceNewerActiveStatus() {
        val repository = NativeStatusRepository()
        val old = testSession()
        val newer = testSession(
            token = "replacement_participant_token_1234567890",
            startedAt = TEST_NOW.plusMillis(1),
        )
        val newerStatus = NativeTrackingStatus(
            TEST_SLUG,
            TEST_PARTICIPANT,
            true,
            "starting",
            null,
            false,
            null,
        )
        repository.activate(newer, newerStatus)
        assertFalse(repository.markServiceShutdownPending(old))
        assertEquals(newerStatus, repository.current())
    }

    @Test
    fun matchingSampleDeletionDoesNotRemoveNewerSample() {
        val pending = LatestOnlyPending()
        val old = testSample(id = "sample-old-123456")
        val latest = testSample(
            id = "sample-new-123456",
            capturedAt = TEST_NOW.plusSeconds(1),
            queuedAt = TEST_NOW.plusSeconds(1),
        )
        pending.replace(old)
        pending.replace(latest)
        assertFalse(pending.clearMatching(old.sampleId))
        assertSame(latest, pending.peek())
        assertTrue(pending.clearMatching(latest.sampleId))
        assertNull(pending.peek())
    }

    @Test
    fun stopWarningContainsNoAuthorityOrCoordinate() {
        assertFalse(SafeText.UNCERTAIN_STOP.contains(TEST_TOKEN))
        assertFalse(SafeText.UNCERTAIN_STOP.contains("48.8"))
        assertTrue(SafeText.UNCERTAIN_STOP.contains("may remain visible until server expiry"))
    }

    @Test
    fun notificationTextIsSafeAndBounded() {
        val text = SafeText.notification("offline_retrying", TEST_NOW)
        assertEquals("Offline — latest update delayed", text)
        assertFalse(text.contains(TEST_TOKEN))
        assertFalse(text.contains(TEST_SLUG))
    }

    @Test
    fun sessionIdentityIncludesServerOriginAndToken() {
        val session = testSession()
        assertFalse(session.identityMatches(testSession(origin = "https://other.test")))
        assertFalse(
            session.identityMatches(
                testSession(token = "different_synthetic_participant_token_12345"),
            ),
        )
    }

    @Test
    fun exactSessionIdentityMatches() {
        val session = testSession()
        assertTrue(session.identityMatches(session.copy()))
    }

    @Test
    fun terminalFailureIsRetainedUntilExactAcknowledgement() {
        val repository = NativeStatusRepository()
        val session = testSession()
        repository.activate(
            session,
            NativeTrackingStatus(
                TEST_SLUG,
                TEST_PARTICIPANT,
                true,
                "sharing",
                TEST_NOW,
                false,
                null,
            ),
        )
        val event = repository.recordTerminalFailure(
            session,
            "outing_not_found",
            clearCurrentStatus = true,
        )
        assertSame(event, repository.terminalFailure())
        assertFalse(repository.current().active)
        assertEquals("stopping", repository.current().state)
        assertFalse(
            repository.acknowledgeTerminalFailure(
                event.eventId,
                TEST_SLUG,
                "different_participant_1",
            ),
        )
        assertSame(event, repository.terminalFailure())
        assertTrue(
            repository.acknowledgeTerminalFailure(
                event.eventId,
                TEST_SLUG,
                TEST_PARTICIPANT,
            ),
        )
        assertNull(repository.terminalFailure())
    }

    @Test
    fun oldTerminalFailureCannotClearNewExactSessionStatus() {
        val repository = NativeStatusRepository()
        val old = testSession()
        val newer = testSession(
            token = "replacement_participant_token_1234567890",
            startedAt = TEST_NOW.plusMillis(1),
        )
        val sharing = NativeTrackingStatus(
            TEST_SLUG,
            TEST_PARTICIPANT,
            true,
            "sharing",
            TEST_NOW,
            false,
            null,
        )
        repository.activate(newer, sharing)
        repository.recordTerminalFailure(old, "outing_not_found", clearCurrentStatus = true)
        assertEquals(sharing, repository.current())
        assertTrue(repository.current().active)
    }

    private fun conditions(
        explicitRequest: Boolean = true,
        disclosureConfirmed: Boolean = true,
        activityVisible: Boolean = true,
        preciseLocationGranted: Boolean = true,
        notificationsGranted: Boolean = true,
        locationServicesEnabled: Boolean = true,
        activeIdentity: Pair<String, String>? = null,
        currentStatus: NativeTrackingStatus = activeIdentity?.let {
            NativeTrackingStatus(
                outingSlug = it.first,
                participantId = it.second,
                active = true,
                state = "sharing",
                lastPublishedAt = null,
                pendingSample = false,
                stopWarning = null,
            )
        } ?: NativeTrackingStatus.stopped(),
    ): StartConditions = StartConditions(
        explicitRequest,
        disclosureConfirmed,
        activityVisible,
        preciseLocationGranted,
        notificationsGranted,
        locationServicesEnabled,
        currentStatus,
        identity,
    )

    private fun stoppingStatus(value: Pair<String, String>): NativeTrackingStatus =
        NativeTrackingStatus(
            outingSlug = value.first,
            participantId = value.second,
            active = false,
            state = "stopping",
            lastPublishedAt = null,
            pendingSample = false,
            stopWarning = null,
        )

    private fun assertRejected(value: StartConditions, code: String) {
        val decision = StartPolicy.decide(value)
        assertTrue(decision is StartDecision.Rejected)
        assertEquals(code, (decision as StartDecision.Rejected).code)
    }

}
