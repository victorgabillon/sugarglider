package io.github.victorgabillon.sugarglider

import org.junit.Assert.*
import org.junit.Test
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.io.IOException
import java.io.InputStream

class ExternalItineraryIntentParserTest {
    private val json = "{\"format\":\"sugarglider_itinerary_draft\",\"version\":1}"
    private fun text(value: Any?, mime: String = "text/plain", action: String = ExternalItineraryIntentParser.SEND) =
        ExternalItineraryIntentParser.Input(action, mime, value)
    private fun file(uri: String? = "content://fixture/draft", granted: Boolean = true, action: String = ExternalItineraryIntentParser.SEND) =
        ExternalItineraryIntentParser.Input(action, "application/json", uri = uri, readGranted = granted)
    private fun parse(input: ExternalItineraryIntentParser.Input, bytes: ByteArray = json.toByteArray()) =
        ExternalItineraryIntentParser.parse(input) { ByteArrayInputStream(bytes) }
    private fun accepted(result: ExternalItineraryIntentParser.Result) = (result as ExternalItineraryIntentParser.Result.Accepted).draft
    private fun rejected(result: ExternalItineraryIntentParser.Result) = (result as ExternalItineraryIntentParser.Result.Rejected).reason

    @Test fun rawFencedProseUrlsAndHtmlAreUnparsedTransportOnly() {
        for (value in listOf(json, "```JSON\n$json\n```", "ordinary prose", "https://example.org/share", "http://example.org", "<script>alert(1)</script>")) {
            val result = ExternalItineraryIntentParser.parse(text(value)) { throw AssertionError("No URI/path read for text") }
            assertEquals(value, accepted(result).rawText)
            assertEquals(ExternalItineraryIntentParser.SourceKind.SHARED_TEXT, accepted(result).sourceKind)
        }
    }
    @Test fun jsonMimeTextAndCharSequenceAreSupported() {
        assertEquals(json, accepted(parse(text(json, "application/json"))).rawText)
        assertEquals(json, accepted(parse(text(StringBuilder(json)))).rawText)
    }
    @Test fun emptyWrongTypeMissingWrongMimeAndMultipleAreRejected() {
        for (input in listOf(text(""), text(null), text(7), text(json, "text/html"), text(json, "application/octet-stream"),
            text(json, action = "android.intent.action.SEND_MULTIPLE"), text(json, action = "other"), text("/sdcard/draft.json"), text("file:///tmp/a.json"), text("C:\\draft.json"), file(null), ExternalItineraryIntentParser.Input(null, null))) {
            assertTrue(parse(input) is ExternalItineraryIntentParser.Result.Rejected)
        }
    }
    @Test fun exactUtf8BoundaryAndOneByteOverflow() {
        val limit = ExternalItineraryIntentParser.MAX_BYTES
        for (value in listOf("a".repeat(limit), "é".repeat(limit / 2), "😀".repeat(limit / 4))) {
            assertEquals(value, accepted(parse(text(value))).rawText)
            assertEquals(ExternalItineraryIntentParser.Rejection.TOO_LARGE, rejected(parse(text(value + "a"))))
        }
        assertEquals(ExternalItineraryIntentParser.Rejection.UNREADABLE, rejected(parse(text("\ud800"))))
    }
    @Test fun hugeCharSequenceIsRejectedBeforeConversion() {
        val huge = object : CharSequence {
            override val length = Int.MAX_VALUE
            override fun get(index: Int): Char = throw AssertionError()
            override fun subSequence(startIndex: Int, endIndex: Int): CharSequence = throw AssertionError()
            override fun toString(): String = throw AssertionError("No unbounded conversion")
        }
        assertEquals(ExternalItineraryIntentParser.Rejection.TOO_LARGE, rejected(parse(text(huge))))
    }
    @Test fun onlyGrantedContentJsonFilesReachReader() {
        var reads = 0
        for (input in listOf(file("file:///tmp/a.json"), file("http://example.org/a"), file("https://example.org/a"),
            file("content://fixture/a", false), file("content:///a"), file("content://user@fixture/a"), file("content://fixture/a#fragment"),
            ExternalItineraryIntentParser.Input(ExternalItineraryIntentParser.VIEW, "text/plain", uri = "content://fixture/a", readGranted = true),
            ExternalItineraryIntentParser.Input(ExternalItineraryIntentParser.SEND, "text/plain", uri = "content://fixture/a", readGranted = true))) {
            assertTrue(ExternalItineraryIntentParser.parse(input) { reads++; ByteArrayInputStream(json.toByteArray()) } is ExternalItineraryIntentParser.Result.Rejected)
        }
        assertEquals(0, reads)
        assertEquals(ExternalItineraryIntentParser.SourceKind.SHARED_JSON_FILE, accepted(parse(file())).sourceKind)
        assertEquals(ExternalItineraryIntentParser.SourceKind.OPENED_JSON_FILE, accepted(parse(file(action = ExternalItineraryIntentParser.VIEW))).sourceKind)
    }
    @Test fun boundedStreamStopsAtLimitPlusOneAndCloses() {
        val limit = ExternalItineraryIntentParser.MAX_BYTES
        for (size in listOf(limit, limit + 1, limit * 10)) {
            var count = 0; var closed = false
            val stream = object : InputStream() {
                override fun read(): Int = if (count < size) { count++; 65 } else -1
                override fun close() { closed = true }
            }
            val result = ExternalItineraryIntentParser.parse(file()) { stream }
            assertEquals(minOf(size, limit + 1), count); assertTrue(closed)
            if (size == limit) assertEquals(limit, accepted(result).rawText.length)
            else assertEquals(ExternalItineraryIntentParser.Rejection.TOO_LARGE, rejected(result))
        }
    }
    @Test fun unreadableEmptyAndMalformedUtf8HaveSafeErrors() {
        assertEquals(ExternalItineraryIntentParser.Rejection.UNREADABLE, rejected(ExternalItineraryIntentParser.parse(file()) { null }))
        assertEquals(ExternalItineraryIntentParser.Rejection.UNREADABLE, rejected(ExternalItineraryIntentParser.parse(file()) { throw SecurityException("private payload") }))
        assertEquals(ExternalItineraryIntentParser.Rejection.MISSING, rejected(parse(file(), byteArrayOf())))
        assertEquals(ExternalItineraryIntentParser.Rejection.UNREADABLE, rejected(parse(file(), byteArrayOf(0xff.toByte()))))
        var closed = false
        val stream = object : InputStream() {
            override fun read(): Int = throw IOException("private URI/payload")
            override fun close() { closed = true }
        }
        val result = ExternalItineraryIntentParser.parse(file()) { stream }
        assertTrue(closed); assertFalse(rejected(result).message.contains("private"))
    }
    @Test fun ambiguousTextAndStreamIsRejected() {
        val input = ExternalItineraryIntentParser.Input(ExternalItineraryIntentParser.SEND, "application/json", json, "content://fixture/a", true)
        assertEquals(ExternalItineraryIntentParser.Rejection.UNSUPPORTED, rejected(ExternalItineraryIntentParser.parse(input) { throw AssertionError() }))
    }
    private class Harness {
        val work = ArrayDeque<() -> Unit>(); val ui = ArrayDeque<() -> Unit>()
        val deliveries = mutableListOf<String>(); val errors = mutableListOf<ExternalItineraryIntentParser.Rejection>(); var ready = false
        val receiver = ExternalItineraryReceiver(work::add, ui::add,
            { ByteArrayInputStream(it.substringAfterLast('/').toByteArray()) }, errors::add,
            { if (ready) { deliveries.add(it.rawText); true } else false })
        fun finish() { work.removeFirst().invoke(); ui.removeFirst().invoke() }
    }
    @Test fun coldWaitsForReadyThenDeliversOnce() {
        val h = Harness(); h.receiver.receive(text(json)); assertTrue(h.deliveries.isEmpty())
        h.ready = true; h.receiver.flush(); h.receiver.flush(); assertEquals(listOf(json), h.deliveries)
    }
    @Test fun secondInputReplacesOldPendingAndMalformedThenValidWorks() {
        val h = Harness(); h.receiver.receive(text("first")); h.receiver.receive(text("second"))
        h.ready = true; h.receiver.flush(); assertEquals(listOf("second"), h.deliveries)
        h.receiver.receive(text("")); h.receiver.receive(text(json)); assertEquals(listOf("second", json), h.deliveries)
        assertEquals(listOf(ExternalItineraryIntentParser.Rejection.MISSING), h.errors)
    }
    @Test fun obsoleteFileCompletionCannotOverwriteLatestFileOrText() {
        val h = Harness(); h.ready = true
        h.receiver.receive(file("content://fixture/old")); h.receiver.receive(file("content://fixture/dropped")); h.receiver.receive(file("content://fixture/new"))
        assertEquals(1, h.work.size); h.finish(); assertTrue(h.deliveries.isEmpty()); h.finish(); assertEquals(listOf("new"), h.deliveries)
        h.receiver.receive(file("content://fixture/stale")); h.receiver.receive(text(json)); h.finish(); assertEquals(listOf("new", json), h.deliveries)
    }
    @Test fun destructionRecreationDropsPendingAndNeverReplays() {
        val h = Harness(); h.receiver.receive(file()); h.receiver.close(); h.ready = true; h.finish(); h.receiver.flush(); h.receiver.receive(text(json))
        assertTrue(h.deliveries.isEmpty()); assertTrue(h.errors.isEmpty())
        val recreated = Harness(); recreated.ready = true; recreated.receiver.flush(); assertTrue(recreated.deliveries.isEmpty())
    }
    @Test fun escapedEnvelopeContainsOnlyTextAndSource() {
        val draft = accepted(parse(text("\"\n<script>😀</script>")))
        val value = JSONObject(ExternalItineraryProtocol.draft("native-${"a".repeat(32)}-1", draft))
        assertEquals(setOf("schema_version", "request_id", "type", "text", "source_kind"), value.keys().asSequence().toSet())
        assertEquals(draft.rawText, value.getString("text")); assertEquals(3, JSONObject(ExternalItineraryProtocol.back("native-${"a".repeat(32)}-2")).length())
    }
    @Test fun modalStateIsStrictAndBundledOnly() {
        val id = "web-${"a".repeat(32)}-1"
        val value = JSONObject().put("schema_version", 1).put("request_id", id).put("type", "itinerary_dialog_state").put("open", true)
        val request = BridgeProtocol.parse(value.toString()) as BridgeRequest.ItineraryDialogState
        assertTrue(request.open); assertTrue(BundledShellPolicy.acceptsOrigin(request, BundledShellPolicy.ORIGIN))
        assertFalse(BundledShellPolicy.acceptsOrigin(request, "https://sharing.example")); assertFalse(V1ReleasePolicy.acceptsBridge(request, "https://sharing.example"))
        value.put("open", "true"); assertNull(BridgeProtocol.parse(value.toString()))
        value.put("open", true).put("text", json); assertNull(BridgeProtocol.parse(value.toString()))
    }
}
