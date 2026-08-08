package io.github.victorgabillon.sugarglider

import java.net.IDN
import java.net.URI

internal class ServerOrigin private constructor(
    val normalized: String,
    val scheme: String,
    val host: String,
    val port: Int,
) {
    companion object {
        fun parse(input: String, allowDevelopmentHttp: Boolean): ServerOrigin? {
            val uri = try {
                URI(input.trim())
            } catch (_: Exception) {
                return null
            }
            val scheme = uri.scheme?.lowercase() ?: return null
            if (scheme != "https" && scheme != "http") return null
            if (scheme == "http" && (!allowDevelopmentHttp || !isDevelopmentHost(uri.host))) {
                return null
            }
            if (uri.rawUserInfo != null || uri.rawQuery != null || uri.rawFragment != null) {
                return null
            }
            if (uri.rawPath != null && uri.rawPath.isNotEmpty() && uri.rawPath != "/") {
                return null
            }
            val rawHost = uri.host ?: return null
            val host = normalizeHost(rawHost) ?: return null
            val port = uri.port
            if (port !in -1..65_535 || port == 0) return null
            val normalizedPort = when {
                port == -1 -> -1
                scheme == "https" && port == 443 -> -1
                scheme == "http" && port == 80 -> -1
                else -> port
            }
            val formattedHost = if (host.contains(':')) "[$host]" else host
            val normalized = buildString {
                append(scheme)
                append("://")
                append(formattedHost)
                if (normalizedPort != -1) {
                    append(':')
                    append(normalizedPort)
                }
            }
            return ServerOrigin(normalized, scheme, host, normalizedPort)
        }

        private fun normalizeHost(value: String): String? {
            val lower = value.lowercase().removeSuffix(".")
            if (lower.isBlank() || lower.any { it.isWhitespace() }) return null
            if (lower.contains(':')) return lower
            return try {
                IDN.toASCII(lower, IDN.USE_STD3_ASCII_RULES).lowercase()
            } catch (_: IllegalArgumentException) {
                null
            }
        }

        private fun isDevelopmentHost(value: String?): Boolean {
            val host = value?.lowercase()?.removeSuffix(".") ?: return false
            if (host == "localhost" || host == "127.0.0.1" || host == "::1") return true
            val octets = host.split('.').map { it.toIntOrNull() ?: return false }
            if (octets.size != 4 || octets.any { it !in 0..255 }) return false
            return octets[0] == 10 ||
                (octets[0] == 192 && octets[1] == 168) ||
                (octets[0] == 172 && octets[1] in 16..31) ||
                (octets[0] == 169 && octets[1] == 254)
        }
    }
}
