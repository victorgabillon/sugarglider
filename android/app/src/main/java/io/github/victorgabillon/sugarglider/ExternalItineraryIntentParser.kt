package io.github.victorgabillon.sugarglider

import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.net.URI
import java.nio.ByteBuffer
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.nio.charset.StandardCharsets

/** Transport only: the web Review button owns JSON/schema validation. */
internal object ExternalItineraryIntentParser {
    const val MAX_BYTES = 64 * 1024
    const val SEND = "android.intent.action.SEND"
    const val VIEW = "android.intent.action.VIEW"

    class Input(
        val action: String?, val mimeType: String?, val text: Any? = null,
        val uri: String? = null, val readGranted: Boolean = false,
    )

    enum class SourceKind(val wireValue: String) {
        SHARED_TEXT("shared_text"), SHARED_JSON_FILE("shared_json_file"), OPENED_JSON_FILE("opened_json_file"),
    }

    class Pending(val rawText: String, val sourceKind: SourceKind)

    enum class Rejection(val message: String) {
        UNSUPPORTED("Share plain text or one JSON document with Sugarglider."),
        MISSING("The shared item contains no readable text or JSON document."),
        TOO_LARGE("Itinerary JSON must be at most 64 KiB."),
        URI_NOT_GRANTED("Open or share a readable content JSON document with temporary read access."),
        UNREADABLE("The shared item could not be read as UTF-8 text."),
    }

    sealed interface Result {
        class Accepted(val draft: Pending) : Result
        class Rejected(val reason: Rejection) : Result
    }

    fun parse(input: Input, openContent: (String) -> InputStream?): Result {
        if (input.action !in setOf(SEND, VIEW) || input.mimeType !in setOf("text/plain", "application/json") ||
            input.action == VIEW && input.mimeType != "application/json") return rejected(Rejection.UNSUPPORTED)
        return try {
            if (input.action == SEND && input.text != null) {
                if (input.uri != null || input.text !is CharSequence) return rejected(Rejection.UNSUPPORTED)
                // Check length before toString/encoding, including very large CharSequences.
                if (input.text.length > MAX_BYTES) return rejected(Rejection.TOO_LARGE)
                val text = input.text.toString()
                if (text.length > MAX_BYTES) return rejected(Rejection.TOO_LARGE)
                val trimmed = text.trim()
                if (trimmed.startsWith("/") || trimmed.startsWith("file:") || Regex("^[A-Za-z]:[\\\\/].*").matches(trimmed))
                    return rejected(Rejection.UNSUPPORTED)
                val bytes = StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(text)).remaining()
                if (bytes > MAX_BYTES) rejected(Rejection.TOO_LARGE)
                else if (text.isEmpty()) rejected(Rejection.MISSING)
                else Result.Accepted(Pending(text, SourceKind.SHARED_TEXT))
            } else {
                if (input.mimeType != "application/json") return rejected(Rejection.MISSING)
                val text = input.uri ?: return rejected(Rejection.MISSING)
                val uri = URI(text)
                if (uri.scheme != "content" || uri.rawAuthority.isNullOrEmpty() || uri.rawUserInfo != null ||
                    uri.rawFragment != null || !input.readGranted) return rejected(Rejection.URI_NOT_GRANTED)
                val stream = openContent(text) ?: return rejected(Rejection.UNREADABLE)
                val bytes = stream.use { source ->
                    val output = ByteArrayOutputStream()
                    val buffer = ByteArray(4096)
                    while (output.size() <= MAX_BYTES) {
                        val count = source.read(buffer, 0, minOf(buffer.size, MAX_BYTES + 1 - output.size()))
                        if (count < 0) break
                        if (count == 0) {
                            val byte = source.read(); if (byte < 0) break; output.write(byte)
                        } else output.write(buffer, 0, count)
                    }
                    output.toByteArray()
                }
                if (bytes.size > MAX_BYTES) return rejected(Rejection.TOO_LARGE)
                if (bytes.isEmpty()) return rejected(Rejection.MISSING)
                val raw = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes)).toString()
                Result.Accepted(Pending(raw, if (input.action == VIEW) SourceKind.OPENED_JSON_FILE else SourceKind.SHARED_JSON_FILE))
            }
        } catch (_: Exception) { rejected(Rejection.UNREADABLE) }
    }

    private fun rejected(reason: Rejection) = Result.Rejected(reason)
}

/** One bounded latest input/read and pending draft; obsolete completions lose ownership. */
internal class ExternalItineraryReceiver(
    private val execute: (() -> Unit) -> Unit,
    private val dispatch: (() -> Unit) -> Unit,
    private val openContent: (String) -> InputStream?,
    private val reject: (ExternalItineraryIntentParser.Rejection) -> Unit,
    private val deliver: (ExternalItineraryIntentParser.Pending) -> Boolean,
) {
    private var generation = 0L
    private var busy = false
    private var closed = false
    private var latest: ExternalItineraryIntentParser.Input? = null
    private var pending: ExternalItineraryIntentParser.Pending? = null

    fun receive(input: ExternalItineraryIntentParser.Input) {
        if (closed) return
        generation += 1; pending = null; latest = null
        if (input.text != null) {
            when (val result = ExternalItineraryIntentParser.parse(input, openContent)) {
                is ExternalItineraryIntentParser.Result.Accepted -> { pending = result.draft; flush() }
                is ExternalItineraryIntentParser.Result.Rejected -> reject(result.reason)
            }
        } else { latest = input; readLatest() }
    }

    fun flush() {
        if (closed) return
        val draft = pending ?: return
        if (deliver(draft)) pending = null
    }

    fun close() { closed = true; generation += 1; latest = null; pending = null }

    private fun readLatest() {
        if (busy || closed) return
        val input = latest ?: return
        latest = null; busy = true
        val owned = generation
        execute {
            val result = ExternalItineraryIntentParser.parse(input, openContent)
            dispatch {
                busy = false
                if (closed) return@dispatch
                if (owned == generation) when (result) {
                    is ExternalItineraryIntentParser.Result.Accepted -> { pending = result.draft; flush() }
                    is ExternalItineraryIntentParser.Result.Rejected -> reject(result.reason)
                }
                readLatest()
            }
        }
    }
}
