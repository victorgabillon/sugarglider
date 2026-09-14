package io.github.victorgabillon.sugarglider

import org.json.JSONObject
import java.io.OutputStream
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.nio.charset.StandardCharsets
import java.security.MessageDigest

/** One bounded, already serialized GPX. This adapter does no route computation. */
internal class PreparedGpxDocument(
    val request: BridgeRequest.SaveGpx,
    val ledgerPayload: String,
    private val bytes: ByteArray,
    private val offset: Int,
) {
    fun writeTo(output: OutputStream) {
        output.write(bytes, offset, bytes.size - offset)
        output.flush()
    }
}

internal object GpxDocumentProtocol {
    const val MAX_OUTPUT_BYTES = 16 * 1024 * 1024
    const val MAX_HEADER_BYTES = 1_024
    const val MIME_TYPE = "application/gpx+xml"
    private val fields = setOf("schema_version", "request_id", "type", "filename", "byte_count")
    private val filenamePattern = Regex("""^[\x20-\x7E&&[^<>:"/\\|?*]]{1,100}\.gpx$""")

    // Four-byte big-endian header length, strict UTF-8 JSON header, then GPX bytes.
    // Do not decode or log the GPX, URI, or full message in native code.
    fun parse(bytes: ByteArray): PreparedGpxDocument? {
        if (bytes.size !in 6..(MAX_OUTPUT_BYTES + MAX_HEADER_BYTES + 4)) return null
        val headerLength = ByteBuffer.wrap(bytes, 0, 4).int
        if (headerLength !in 2..MAX_HEADER_BYTES || headerLength + 4 >= bytes.size) return null
        val offset = headerLength + 4
        if (bytes.size - offset > MAX_OUTPUT_BYTES) return null
        val header = try {
            StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes, 4, headerLength)).toString()
        } catch (_: Exception) {
            return null
        }
        val value = try { JSONObject(header) } catch (_: Exception) { return null }
        if (buildSet { value.keys().forEachRemaining(::add) } != fields) return null
        if (value.opt("schema_version") != 1 || value.opt("type") != "save_gpx") return null
        val requestId = value.opt("request_id") as? String ?: return null
        val nonce = BridgeProtocol.pageNonce(requestId) ?: return null
        val filename = value.opt("filename") as? String ?: return null
        if (!filenamePattern.matches(filename) || filename.startsWith('.')) return null
        if (value.opt("byte_count") != bytes.size - offset) return null
        val digest = MessageDigest.getInstance("SHA-256").digest(bytes)
            .joinToString("") { "%02x".format(it) }
        return PreparedGpxDocument(BridgeRequest.SaveGpx(requestId, nonce, filename), digest, bytes, offset)
    }

    fun reply(requestId: String, status: GpxSaveStatus): String = JSONObject()
        .put("schema_version", 1)
        .put("request_id", requestId)
        .put("type", "save_gpx_result")
        .put("status", status.wireValue)
        .toString()
}

internal enum class GpxSaveStatus(val wireValue: String) {
    SAVED("saved"), CANCELLED("cancelled"), BUSY("busy"), UNAVAILABLE("unavailable"),
    WRITE_FAILED("write_failed"),
}

/** Called on the UI thread except for the explicitly dispatched output write. */
internal class GpxDocumentSaver(
    private val showPicker: (String) -> Unit,
    private val execute: (() -> Unit) -> Unit,
    private val dispatch: (() -> Unit) -> Unit,
) {
    private class Operation(val document: PreparedGpxDocument, var reply: ((GpxSaveStatus) -> Unit)?)
    private var pending: Operation? = null
    private var writing: Operation? = null
    private var pickerOpen = false
    private var closed = false

    fun begin(document: PreparedGpxDocument, reply: (GpxSaveStatus) -> Unit) {
        if (closed) { reply(GpxSaveStatus.UNAVAILABLE); return }
        if (pickerOpen || writing != null) { reply(GpxSaveStatus.BUSY); return }
        val operation = Operation(document, reply)
        pending = operation
        pickerOpen = true
        try { showPicker(document.request.filename) } catch (_: Exception) {
            pickerOpen = false
            pending = null
            operation.reply?.invoke(GpxSaveStatus.UNAVAILABLE)
        }
    }

    fun selected(openOutput: (() -> OutputStream?)?) {
        if (!pickerOpen) return
        pickerOpen = false
        val operation = pending.also { pending = null } ?: return
        if (openOutput == null) { operation.reply?.invoke(GpxSaveStatus.CANCELLED); return }
        writing = operation
        try {
            execute {
                val status = try {
                    val output = openOutput() ?: error("document unavailable")
                    output.use(operation.document::writeTo)
                    GpxSaveStatus.SAVED
                } catch (_: Exception) { GpxSaveStatus.WRITE_FAILED }
                dispatch {
                    if (writing === operation) writing = null
                    operation.reply?.invoke(status)
                    operation.reply = null
                }
            }
        } catch (_: Exception) {
            writing = null
            operation.reply?.invoke(GpxSaveStatus.WRITE_FAILED)
            operation.reply = null
        }
    }

    fun hasPendingWork(): Boolean = pickerOpen || writing != null

    fun invalidate() {
        pending?.reply = null
        pending = null
        writing?.reply = null
        // An old picker/result or write still owns its slot until it finishes.
        // Never let a late result write a newer page's document.
    }

    fun close() { closed = true; invalidate() }
}
