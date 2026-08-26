package io.github.victorgabillon.sugarglider

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BackNavigationPolicyTest {
    @Test
    fun exactPlannerRootWithoutHistoryBackgroundsInsteadOfFinishing() {
        val rig = BackRig(decision("$ORIGIN/", canGoBack = false))

        rig.handle()

        assertEquals(1, rig.backgroundRequests)
        assertEquals(0, rig.webViewBacks)
        assertEquals(0, rig.systemBacks)
    }

    @Test
    fun exactPlannerRootWithHistoryStillBackgroundsInsteadOfNavigating() {
        val rig = BackRig(decision(ORIGIN, canGoBack = true))

        rig.handle()

        assertEquals(1, rig.backgroundRequests)
        assertEquals(0, rig.webViewBacks)
        assertEquals(0, rig.systemBacks)
    }

    @Test
    fun outingWithHistoryRequiresConfirmationWithoutImmediateNavigation() {
        val rig = BackRig(
            decision(
                currentUrl = "$ORIGIN/o/$OUTING_SLUG",
                canGoBack = true,
            ),
        )

        rig.handle()

        assertEquals(1, rig.confirmations)
        assertEquals(0, rig.webViewBacks)
        assertEquals(0, rig.systemBacks)
    }

    @Test
    fun stayDoesNotNavigateOrFinish() {
        val rig = BackRig(decision("$ORIGIN/o/$OUTING_SLUG", canGoBack = true))
        rig.handle()

        assertEquals(0, rig.webViewBacks)
        assertEquals(0, rig.systemBacks)
    }

    @Test
    fun leaveNavigatesWebViewExactlyOnce() {
        val rig = BackRig(decision("$ORIGIN/o/$OUTING_SLUG", canGoBack = true))
        rig.handle()

        rig.leave()
        rig.leave()

        assertEquals(1, rig.webViewBacks)
        assertEquals(0, rig.systemBacks)
    }

    @Test
    fun matchingBusyTrackingExplainsThatSharingContinuesWithoutStoppingIt() {
        val status = NativeTrackingStatus(
            outingSlug = OUTING_SLUG,
            participantId = PARTICIPANT_ID,
            active = false,
            state = "stopping",
            lastPublishedAt = null,
            pendingSample = false,
            stopWarning = null,
        )
        val rig = BackRig(
            decision("$ORIGIN/o/$OUTING_SLUG", canGoBack = true, status = status),
        )

        rig.handle()

        assertTrue(rig.confirmation?.backgroundSharingContinues == true)
        assertEquals(0, rig.webViewBacks)
        assertEquals(0, rig.systemBacks)
    }

    @Test
    fun trackingForAnotherOutingDoesNotClaimThisPageWillContinueSharing() {
        val otherStatus = NativeTrackingStatus(
            outingSlug = OTHER_OUTING_SLUG,
            participantId = PARTICIPANT_ID,
            active = true,
            state = "sharing",
            lastPublishedAt = null,
            pendingSample = false,
            stopWarning = null,
        )

        val result = decision(
            "$ORIGIN/o/$OUTING_SLUG",
            canGoBack = true,
            status = otherStatus,
        )

        assertTrue(result is BackNavigationDecision.ConfirmOutingLeave)
        assertFalse((result as BackNavigationDecision.ConfirmOutingLeave).backgroundSharingContinues)
    }

    @Test
    fun nonOutingPageWithHistoryUsesExistingWebViewBack() {
        val rig = BackRig(decision("$ORIGIN/saved-routes", canGoBack = true))

        rig.handle()

        assertEquals(0, rig.confirmations)
        assertEquals(1, rig.webViewBacks)
        assertEquals(0, rig.systemBacks)
    }

    @Test
    fun pageWithoutHistoryAllowsSystemBack() {
        val rig = BackRig(decision("$ORIGIN/saved-routes", canGoBack = false))

        rig.handle()

        assertEquals(0, rig.confirmations)
        assertEquals(0, rig.webViewBacks)
        assertEquals(1, rig.systemBacks)
    }

    @Test
    fun outingWithoutHistoryStillRequiresConfirmationBeforeSystemBack() {
        val rig = BackRig(decision("$ORIGIN/o/$OUTING_SLUG", canGoBack = false))
        rig.handle()

        assertEquals(1, rig.confirmations)
        assertEquals(0, rig.systemBacks)

        rig.leave()

        assertEquals(1, rig.systemBacks)
    }

    @Test
    fun onlySameOriginExactOutingPathsReceiveOutingPolicy() {
        for (
            url in listOf(
                "https://other.example/o/$OUTING_SLUG",
                "$ORIGIN/o/$OUTING_SLUG/extra",
                "$ORIGIN/routes/o/$OUTING_SLUG",
                "$ORIGIN/o/not-a-valid-slug",
            )
        ) {
            assertEquals(
                BackNavigationDecision.Navigate(BackNavigationTarget.WEB_VIEW_HISTORY),
                decision(url, canGoBack = true),
            )
        }
    }

    @Test
    fun otherOriginsMalformedUrlsAndRootVariantsAreNotPlannerRoot() {
        for (
            url in listOf(
                "https://other.example/",
                "$ORIGIN/?view=planner",
                "$ORIGIN/#planner",
                "not a valid URL",
            )
        ) {
            assertEquals(
                BackNavigationDecision.Navigate(BackNavigationTarget.WEB_VIEW_HISTORY),
                decision(url, canGoBack = true),
            )
        }
    }

    private fun decision(
        currentUrl: String,
        canGoBack: Boolean,
        status: NativeTrackingStatus = NativeTrackingStatus.stopped(),
    ): BackNavigationDecision = BackNavigationPolicy.decide(
        currentUrl = currentUrl,
        configuredOrigin = ORIGIN,
        canGoBack = canGoBack,
        trackingStatus = status,
    )

    private class BackRig(
        private val decision: BackNavigationDecision,
    ) {
        var webViewBacks = 0
        var systemBacks = 0
        var backgroundRequests = 0
        var confirmations = 0
        var confirmation: BackNavigationDecision.ConfirmOutingLeave? = null
        private var leaveAction: (() -> Unit)? = null

        fun handle() {
            BackNavigationController.handle(
                decision = decision,
                navigateWebViewBack = { webViewBacks += 1 },
                navigateSystemBack = { systemBacks += 1 },
                moveTaskToBackground = { backgroundRequests += 1 },
                showOutingConfirmation = { received, leave ->
                    confirmations += 1
                    confirmation = received
                    leaveAction = leave
                },
            )
        }

        fun leave() {
            leaveAction?.invoke()
        }
    }

    companion object {
        private const val ORIGIN = "https://example.test"
        private const val OUTING_SLUG = "outing_slug_1234567890"
        private const val OTHER_OUTING_SLUG = "other_outing_1234567890"
        private const val PARTICIPANT_ID = "participant_1234567890"
    }
}
