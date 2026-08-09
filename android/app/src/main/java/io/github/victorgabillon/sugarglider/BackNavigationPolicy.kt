package io.github.victorgabillon.sugarglider

import java.net.URI

internal enum class BackNavigationTarget {
    WEB_VIEW_HISTORY,
    SYSTEM,
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
        val outingSlug = outingSlug(currentUrl, configuredOrigin)
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
        return BackNavigationDecision.Navigate(
            if (canGoBack) BackNavigationTarget.WEB_VIEW_HISTORY else BackNavigationTarget.SYSTEM,
        )
    }

    private fun outingSlug(currentUrl: String?, configuredOrigin: String?): String? {
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
        val path = page.rawPath ?: return null
        if (!path.startsWith(OUTING_PATH_PREFIX)) return null
        val slug = path.removePrefix(OUTING_PATH_PREFIX)
        return slug.takeIf(OUTING_SLUG_PATTERN::matches)
    }

    private const val OUTING_PATH_PREFIX = "/o/"
}

internal object BackNavigationController {
    fun handle(
        decision: BackNavigationDecision,
        navigateWebViewBack: () -> Unit,
        navigateSystemBack: () -> Unit,
        showOutingConfirmation: (BackNavigationDecision.ConfirmOutingLeave, () -> Unit) -> Unit,
    ) {
        when (decision) {
            is BackNavigationDecision.Navigate -> navigate(
                decision.target,
                navigateWebViewBack,
                navigateSystemBack,
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
                    )
                }
            }
        }
    }

    private fun navigate(
        target: BackNavigationTarget,
        navigateWebViewBack: () -> Unit,
        navigateSystemBack: () -> Unit,
    ) {
        when (target) {
            BackNavigationTarget.WEB_VIEW_HISTORY -> navigateWebViewBack()
            BackNavigationTarget.SYSTEM -> navigateSystemBack()
        }
    }
}
