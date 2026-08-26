package io.github.victorgabillon.sugarglider

import java.net.URI

internal enum class BackNavigationTarget {
    WEB_VIEW_HISTORY,
    SYSTEM,
    BACKGROUND_TASK,
}

internal sealed interface BackNavigationDecision {
    data class ConfirmOutingLeave(
        val outingSlug: String,
        val backgroundSharingContinues: Boolean,
        val leaveTarget: BackNavigationTarget,
    ) : BackNavigationDecision

    data class Navigate(val target: BackNavigationTarget) : BackNavigationDecision
}

internal object BackNavigationPolicy {
    fun decide(
        currentUrl: String?,
        configuredOrigin: String?,
        canGoBack: Boolean,
        trackingStatus: NativeTrackingStatus,
    ): BackNavigationDecision {
        val page = sameOriginPage(currentUrl, configuredOrigin)
        val outingSlug = outingSlug(page)
        if (outingSlug != null) {
            return BackNavigationDecision.ConfirmOutingLeave(
                outingSlug = outingSlug,
                backgroundSharingContinues =
                    trackingStatus.isNativeBusy() && trackingStatus.outingSlug == outingSlug,
                leaveTarget = if (canGoBack) {
                    BackNavigationTarget.WEB_VIEW_HISTORY
                } else {
                    BackNavigationTarget.SYSTEM
                },
            )
        }
        if (page?.isExactPlannerRoot() == true) {
            return BackNavigationDecision.Navigate(BackNavigationTarget.BACKGROUND_TASK)
        }
        return BackNavigationDecision.Navigate(
            if (canGoBack) BackNavigationTarget.WEB_VIEW_HISTORY else BackNavigationTarget.SYSTEM,
        )
    }

    private fun sameOriginPage(currentUrl: String?, configuredOrigin: String?): URI? {
        val origin = configuredOrigin?.let {
            ServerOrigin.parse(it, allowDevelopmentHttp = true)
        } ?: return null
        val page = try {
            URI(currentUrl ?: return null)
        } catch (_: Exception) {
            return null
        }
        val pageAuthority = page.rawAuthority ?: return null
        val pageOrigin = ServerOrigin.parse(
            "${page.scheme}://$pageAuthority",
            allowDevelopmentHttp = true,
        ) ?: return null
        if (pageOrigin.normalized != origin.normalized) return null
        return page
    }

    private fun outingSlug(page: URI?): String? {
        val path = page?.rawPath ?: return null
        if (!path.startsWith(OUTING_PATH_PREFIX)) return null
        val slug = path.removePrefix(OUTING_PATH_PREFIX)
        return slug.takeIf(OUTING_SLUG_PATTERN::matches)
    }

    private fun URI.isExactPlannerRoot(): Boolean =
        (rawPath.isNullOrEmpty() || rawPath == "/") && rawQuery == null && rawFragment == null

    private const val OUTING_PATH_PREFIX = "/o/"
}

internal object BackNavigationController {
    fun handle(
        decision: BackNavigationDecision,
        navigateWebViewBack: () -> Unit,
        navigateSystemBack: () -> Unit,
        moveTaskToBackground: () -> Unit,
        showOutingConfirmation: (BackNavigationDecision.ConfirmOutingLeave, () -> Unit) -> Unit,
    ) {
        when (decision) {
            is BackNavigationDecision.Navigate -> navigate(
                decision.target,
                navigateWebViewBack,
                navigateSystemBack,
                moveTaskToBackground,
            )
            is BackNavigationDecision.ConfirmOutingLeave -> {
                var consumed = false
                showOutingConfirmation(decision) {
                    if (consumed) return@showOutingConfirmation
                    consumed = true
                    navigate(
                        decision.leaveTarget,
                        navigateWebViewBack,
                        navigateSystemBack,
                        moveTaskToBackground,
                    )
                }
            }
        }
    }

    private fun navigate(
        target: BackNavigationTarget,
        navigateWebViewBack: () -> Unit,
        navigateSystemBack: () -> Unit,
        moveTaskToBackground: () -> Unit,
    ) {
        when (target) {
            BackNavigationTarget.WEB_VIEW_HISTORY -> navigateWebViewBack()
            BackNavigationTarget.SYSTEM -> navigateSystemBack()
            BackNavigationTarget.BACKGROUND_TASK -> moveTaskToBackground()
        }
    }
}
