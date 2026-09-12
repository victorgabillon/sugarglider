package io.github.victorgabillon.sugarglider

import java.io.ByteArrayOutputStream
import java.io.FilterInputStream
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URI
import java.net.URL

internal class RegionalDownloadLocation private constructor(
    val manifest: URL,
    val archive: URL,
) {
    companion object {
        fun parse(value: String, allowDevelopmentHttp: Boolean = false): RegionalDownloadLocation? {
            if (value.length !in 1..2_048 || value != value.trim()) return null
            return try {
                val uri = URI(value)
                if (uri.rawQuery != null || uri.rawFragment != null || uri.rawUserInfo != null) return null
                val origin = ServerOrigin.parse("${uri.scheme}://${uri.rawAuthority}", allowDevelopmentHttp)
                    ?: return null
                // Distribution uses the PR39 directory layout. There is no
                // arbitrary path, signed-query URL or redirect interpretation.
                val path = uri.rawPath ?: return null
                if (!path.startsWith('/') || !path.endsWith("/manifest.json")) return null
                val segments = path.drop(1).split('/')
                if (segments.any { it.isEmpty() || it == "." || it.contains("..") || !SEGMENT.matches(it) }) return null
                val base = URI(origin.normalized + path)
                RegionalDownloadLocation(base.resolve("routing/manifest.json").toURL(),
                    base.resolve("routing/valhalla_tiles.tar").toURL())
            } catch (_: Exception) { null }
        }

        private val SEGMENT = Regex("^[A-Za-z0-9._~-]+$")
    }
}

internal fun interface RegionalConnectionFactory {
    fun open(url: URL): HttpURLConnection
}

// Runs on a worker. Cancellation is a cheap caller-owned flag; a stalled read
// remains bounded by the socket timeout before cleanup reports a final outcome.
// This adapter never holds participant authority or changes global TLS settings.
internal class RegionalRoutingDownloader(
    private val store: RegionalRoutingPackStore,
    private val connectionFactory: RegionalConnectionFactory = RegionalConnectionFactory {
        it.openConnection() as HttpURLConnection
    },
    private val allowDevelopmentHttp: Boolean = false,
    private val nanoTime: () -> Long = System::nanoTime,
) {
    fun install(
        reference: RegionalRoutingPackReference,
        regionalManifestUrl: String,
        cancelled: () -> Boolean = { false },
        onProgress: (Long) -> Unit = {},
    ): RoutingPack {
        if (!reference.isValid()) throw RegionalPackException(RegionalPackFailure.INVALID_REFERENCE)
        val location = RegionalDownloadLocation.parse(regionalManifestUrl, allowDevelopmentHttp)
            ?: throw RegionalPackException(RegionalPackFailure.INVALID_SOURCE)
        val started = nanoTime()
        fun check() {
            if (cancelled()) throw RegionalPackException(RegionalPackFailure.CANCELLED)
            if (nanoTime() - started >= MAX_TRANSFER_NANOS) {
                throw RegionalPackException(RegionalPackFailure.TRANSFER_TIMEOUT)
            }
        }
        val interrupted = { check(); false }
        check()
        try {
            // Restart/resume reuses completed immutable bytes without a download.
            return store.open(reference, interrupted)
        } catch (error: RegionalPackException) {
            if (error.code != RegionalPackFailure.UNAVAILABLE) throw error
        }
        val manifest = open(location.manifest, reference.manifest, ::check).use { input ->
            val output = ByteArrayOutputStream(reference.manifest.byteSize.toInt())
            val buffer = ByteArray(4_096)
            var size = 0L
            while (true) {
                val length = input.read(buffer)
                if (length < 0) break
                if (length == 0) throw RegionalPackException(RegionalPackFailure.TRANSFER_FAILED)
                size += length
                if (size > reference.manifest.byteSize) throw RegionalPackException(RegionalPackFailure.SIZE_MISMATCH)
                output.write(buffer, 0, length)
            }
            if (size != reference.manifest.byteSize) throw RegionalPackException(RegionalPackFailure.SIZE_MISMATCH)
            output.toByteArray()
        }
        check()
        return store.stage(reference, manifest,
            archiveSource = { open(location.archive, reference.archive, ::check) },
            cancelled = interrupted, onProgress = onProgress)
    }

    private fun open(url: URL, identity: RegionalFileIdentity, check: () -> Unit): InputStream {
        check()
        var connection: HttpURLConnection? = null
        try {
            val opened = connectionFactory.open(url)
            connection = opened
            opened.requestMethod = "GET"
            opened.instanceFollowRedirects = false
            opened.connectTimeout = SOCKET_TIMEOUT_MS
            opened.readTimeout = SOCKET_TIMEOUT_MS
            opened.useCaches = false
            opened.doInput = true
            opened.doOutput = false
            opened.setRequestProperty("Accept", "application/octet-stream")
            opened.setRequestProperty("Accept-Encoding", "identity")
            // No authority from the configured social origin enters this client.
            opened.setRequestProperty("Cookie", "")
            check()
            if (opened.responseCode != HttpURLConnection.HTTP_OK || opened.url.toExternalForm() != url.toExternalForm()) {
                throw RegionalPackException(RegionalPackFailure.TRANSFER_FAILED)
            }
            val encoding = opened.getHeaderField("Content-Encoding")
            if (encoding != null && !encoding.trim().equals("identity", ignoreCase = true)) {
                throw RegionalPackException(RegionalPackFailure.ENCODED_TRANSFER)
            }
            val declared = opened.getHeaderField("Content-Length")
            if (declared != null && declared.trim().toLongOrNull() != identity.byteSize) {
                throw RegionalPackException(RegionalPackFailure.SIZE_MISMATCH)
            }
            check()
            return object : FilterInputStream(opened.inputStream) {
                override fun read(): Int = guarded { super.read() }
                override fun read(bytes: ByteArray, offset: Int, length: Int): Int =
                    guarded { `in`.read(bytes, offset, length) }

                private fun guarded(read: () -> Int): Int = try {
                    check()
                    val result = read()
                    check()
                    result
                } catch (error: Exception) { throw sanitized(error, check) }

                override fun close() {
                    try { super.close() }
                    catch (error: Exception) { throw sanitized(error, check) }
                    finally { runCatching { opened.disconnect() } }
                }
            }
        } catch (error: Exception) {
            runCatching { connection?.disconnect() }
            throw sanitized(error, check)
        }
    }

    private fun sanitized(error: Exception, check: () -> Unit): RegionalPackException {
        check()
        return when (error) {
            is RegionalPackException -> error
            is SocketTimeoutException -> RegionalPackException(RegionalPackFailure.TRANSFER_TIMEOUT)
            else -> RegionalPackException(RegionalPackFailure.TRANSFER_FAILED)
        }
    }

    private companion object {
        const val SOCKET_TIMEOUT_MS = 15_000
        const val MAX_TRANSFER_NANOS = 30 * 60 * 1_000_000_000L
    }
}
