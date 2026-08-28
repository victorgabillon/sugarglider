package io.github.victorgabillon.sugarglider

internal enum class WebGeolocationPermissionAction {
    REJECTED,
    GRANTED,
    BUSY,
    REQUEST_FOREGROUND_LOCATION,
}

internal class WebGeolocationPermissionCoordinator {
    private data class PendingRequest(
        val origin: String,
        val navigationEpoch: Long,
        val webViewIdentity: Int,
        val resolve: (Boolean) -> Unit,
    )

    private var pending: PendingRequest? = null

    fun begin(
        requestedOrigin: String,
        configuredOrigin: String?,
        navigationEpoch: Long,
        sourceWebViewIdentity: Int,
        currentWebViewIdentity: Int?,
        activityVisible: Boolean,
        preciseLocationGranted: Boolean,
        resolve: (Boolean) -> Unit,
    ): WebGeolocationPermissionAction {
        if (
            requestedOrigin != configuredOrigin ||
            currentWebViewIdentity == null ||
            sourceWebViewIdentity != currentWebViewIdentity ||
            !activityVisible
        ) {
            resolve(false)
            return WebGeolocationPermissionAction.REJECTED
        }
        if (preciseLocationGranted) {
            resolve(true)
            return WebGeolocationPermissionAction.GRANTED
        }
        if (pending != null) {
            resolve(false)
            return WebGeolocationPermissionAction.BUSY
        }
        pending = PendingRequest(
            origin = requestedOrigin,
            navigationEpoch = navigationEpoch,
            webViewIdentity = sourceWebViewIdentity,
            resolve = resolve,
        )
        return WebGeolocationPermissionAction.REQUEST_FOREGROUND_LOCATION
    }

    fun complete(
        preciseLocationGranted: Boolean,
        configuredOrigin: String?,
        navigationEpoch: Long,
        currentWebViewIdentity: Int?,
    ): Boolean {
        val request = pending ?: return false
        pending = null
        val allow = preciseLocationGranted &&
            request.origin == configuredOrigin &&
            request.navigationEpoch == navigationEpoch &&
            request.webViewIdentity == currentWebViewIdentity
        request.resolve(allow)
        return allow
    }

    fun invalidate() {
        pending?.resolve(false)
        pending = null
    }

    fun hasPending(): Boolean = pending != null
}
