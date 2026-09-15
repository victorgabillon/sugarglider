package io.github.victorgabillon.sugarglider

/** V1 is a local planner. No preference, intent or build variant enables sharing. */
internal object V1ReleasePolicy {
    val sharingEnabled: Boolean = false

    fun allowsOrigin(origin: String): Boolean = origin == BundledShellPolicy.ORIGIN

    fun acceptsBridge(request: BridgeRequest, origin: String): Boolean =
        allowsOrigin(origin) && BundledShellPolicy.acceptsRequest(request)
}
