package io.github.victorgabillon.sugarglider

import java.net.URI

/** The APK's local namespace has no network fallback and no participant authority. */
internal object BundledShellPolicy {
    const val HOST = "appassets.androidplatform.net"
    const val ORIGIN = "https://$HOST"

    fun ownsHost(url: String): Boolean = try {
        URI(url).host?.equals(HOST, ignoreCase = true) == true
    } catch (_: Exception) {
        false
    }

    fun assetPath(url: String, method: String, allowedAssets: Set<String>): String? {
        val uri = try { URI(url) } catch (_: Exception) { return null }
        if (
            method != "GET" || uri.scheme != "https" || uri.host != HOST ||
            uri.port !in setOf(-1, 443) || uri.rawUserInfo != null ||
            uri.rawQuery != null || uri.rawFragment != null
        ) return null
        val path = uri.path ?: return null
        if ('\\' in path || path.split('/').any { it == "." || it == ".." }) return null
        val asset = when {
            path == "/" -> "index.html"
            path == "/manifest.webmanifest" -> "manifest.webmanifest"
            path == "/v1/ui/config" -> "android_ui_config.json"
            path.startsWith("/static/") -> path.removePrefix("/static/")
            else -> return null
        }
        return asset.takeIf { it in allowedAssets }
    }

    fun acceptsRequest(request: BridgeRequest): Boolean = when (request) {
        is BridgeRequest.Hello, is BridgeRequest.SaveGpx,
        is BridgeRequest.GetLocalRouteCapabilities, is BridgeRequest.LocalRoute,
        is BridgeRequest.RejectedLocalRoute -> true
        else -> false
    }
}
