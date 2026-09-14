package io.github.victorgabillon.sugarglider

import android.content.Context
import android.net.Uri
import android.webkit.WebResourceResponse
import androidx.webkit.WebViewAssetLoader
import java.io.ByteArrayInputStream
import java.io.IOException
import java.net.URI

internal class BundledShellAssets(context: Context) {
    private val assets = context.applicationContext.assets
    private val allowed = assets.open("shell-assets.txt").bufferedReader().useLines { lines ->
        lines.filter { it.isNotBlank() && !it.startsWith('#') }.toSet()
    }
    private val loader = WebViewAssetLoader.Builder()
        .addPathHandler("/") { path ->
            responseFor(URI("https", BundledShellPolicy.HOST, "/$path", null).toASCIIString(), "GET")
        }.build()

    fun intercept(url: Uri, method: String): WebResourceResponse? {
        if (!BundledShellPolicy.ownsHost(url.toString())) return null
        // Validate the raw request before the loader decodes/normalizes its path.
        if (BundledShellPolicy.assetPath(url.toString(), method, allowed) == null) return missing()
        return loader.shouldInterceptRequest(url) ?: missing()
    }

    private fun responseFor(url: String, method: String): WebResourceResponse {
        val path = BundledShellPolicy.assetPath(url, method, allowed) ?: return missing()
        return try {
            WebResourceResponse(
                mimeType(path), "UTF-8", 200, "OK", HEADERS, assets.open("web/$path"),
            )
        } catch (_: IOException) { missing() }
    }

    private fun missing() = WebResourceResponse(
        "text/plain", "UTF-8", 404, "Not Found", HEADERS,
        ByteArrayInputStream("This resource is not included in Sugarglider.".toByteArray()),
    )

    private fun mimeType(path: String): String = when (path.substringAfterLast('.')) {
        "html" -> "text/html"
        "js", "mjs" -> "application/javascript"
        "css" -> "text/css"
        "json" -> "application/json"
        "webmanifest" -> "application/manifest+json"
        "png" -> "image/png"
        "txt", "md" -> "text/plain"
        else -> "application/octet-stream"
    }

    companion object {
        private val HEADERS = mapOf(
            "Cache-Control" to "no-store",
            "X-Content-Type-Options" to "nosniff",
        )
    }
}
