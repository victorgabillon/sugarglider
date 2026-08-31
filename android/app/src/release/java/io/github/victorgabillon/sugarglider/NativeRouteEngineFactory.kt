package io.github.victorgabillon.sugarglider

import android.content.Context

internal object NativeRouteEngineFactory {
    fun create(@Suppress("UNUSED_PARAMETER") context: Context): NativeRouteEngine =
        DisabledNativeRouteEngine
}

private object DisabledNativeRouteEngine : NativeRouteEngine {
    override fun capabilities(): NativeRouteCapabilities = NativeRouteCapabilities(
        enabled = false,
        engine = "none",
        engineVersion = "none",
        packInstalled = false,
        packId = "none",
    )

    override fun route(request: NativeRouteRequest): NativeRouteResult =
        NativeRouteResult.Failure(NativeRouteFailureCode.ROUTING_PACK_UNAVAILABLE)
}
