package io.github.victorgabillon.sugarglider

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.nio.ByteBuffer

class GpxDocumentSaveTest {
    private val requestId = "web-${"a".repeat(32)}-1"
    private val content = "<?xml version=\"1.0\"?><gpx><trk><trkseg/></trk></gpx>".toByteArray()

    private fun frame(change: (JSONObject) -> Unit = {}): ByteArray {
        val value = JSONObject().put("schema_version", 1).put("request_id", requestId)
            .put("type", "save_gpx").put("filename", "Marly-&-woods.gpx")
            .put("byte_count", content.size)
        change(value)
        val header = value.toString().toByteArray()
        return ByteBuffer.allocate(4 + header.size + content.size).putInt(header.size)
            .put(header).put(content).array()
    }

    private fun document(): PreparedGpxDocument = requireNotNull(GpxDocumentProtocol.parse(frame()))

    @Test fun boundedBinaryProtocolPreservesBytesAndContainsOnlyDigestInLedger() {
        val document = document()
        val output = ByteArrayOutputStream()
        document.writeTo(output)
        assertArrayEquals(content, output.toByteArray())
        assertEquals(requestId, document.request.requestId)
        assertEquals("Marly-&-woods.gpx", document.request.filename)
        assertTrue(document.ledgerPayload.matches(Regex("[a-f0-9]{64}")))
        assertNull(BridgeProtocol.parse(JSONObject().put("schema_version", 1)
            .put("request_id", requestId).put("type", "save_gpx").toString()))
    }

    @Test fun malformedFramesAndExtraAuthorityAreRejected() {
        for (bad in listOf(byteArrayOf(), ByteArray(5), ByteBuffer.allocate(6).putInt(-1).array(),
            ByteBuffer.allocate(6).putInt(1_025).array(),
            ByteArray(GpxDocumentProtocol.MAX_OUTPUT_BYTES + 1_029))) {
            assertNull(GpxDocumentProtocol.parse(bad))
        }
        for (change in listOf<(JSONObject) -> Unit>(
            { it.put("byte_count", content.size + 1) }, { it.put("byte_count", content.size.toString()) },
            { it.put("byte_count", content.size + 0.5) }, { it.put("schema_version", "1") },
            { it.put("type", "start_tracking") }, { it.put("participant_token", "never accepted") },
            { it.put("request_id", "web-wrong-1") }, { it.put("filename", "../route.gpx") },
            { it.put("filename", "route.html") }, { it.put("filename", "bad\nroute.gpx") },
        )) assertNull(GpxDocumentProtocol.parse(frame(change)))
        val invalidUtf8 = frame().also { it[4] = 0xff.toByte() }
        assertNull(GpxDocumentProtocol.parse(invalidUtf8))
    }

    private class Harness {
        val picks = mutableListOf<String>()
        val work = ArrayDeque<() -> Unit>()
        val ui = ArrayDeque<() -> Unit>()
        val replies = mutableListOf<GpxSaveStatus>()
        val saver = GpxDocumentSaver(picks::add, work::add, ui::add)
        fun finish() { work.removeFirst().invoke(); ui.removeFirst().invoke() }
    }

    @Test fun writeIsOffloadedAndSuccessWaitsForClose() {
        val h = Harness()
        var closed = false
        val output = object : ByteArrayOutputStream() { override fun close() { closed = true } }
        h.saver.begin(document(), h.replies::add)
        assertEquals(listOf("Marly-&-woods.gpx"), h.picks)
        h.saver.selected { output }
        assertEquals(0, output.size())
        assertTrue(h.replies.isEmpty())
        assertTrue(h.saver.hasPendingWork())
        h.finish()
        assertFalse(h.saver.hasPendingWork())
        assertTrue(closed)
        assertArrayEquals(content, output.toByteArray())
        assertEquals(listOf(GpxSaveStatus.SAVED), h.replies)
        h.saver.selected { error("duplicate picker result must not write") }
    }

    @Test fun cancellationNeverOpensOutputAndReleasesSlot() {
        val h = Harness()
        h.saver.begin(document(), h.replies::add)
        h.saver.begin(document(), h.replies::add)
        h.saver.selected(null)
        assertEquals(listOf(GpxSaveStatus.BUSY, GpxSaveStatus.CANCELLED), h.replies)
        assertTrue(h.work.isEmpty())
        h.saver.begin(document(), h.replies::add)
        assertEquals(2, h.picks.size)
    }

    @Test fun oldPickerCannotWriteNewPagesDocument() {
        val h = Harness()
        h.saver.begin(document(), h.replies::add)
        h.saver.invalidate()
        assertTrue(h.saver.hasPendingWork())
        h.saver.begin(document(), h.replies::add)
        assertEquals(listOf(GpxSaveStatus.BUSY), h.replies)
        h.saver.selected { error("invalidated picker must never open a file") }
        assertTrue(h.work.isEmpty())
        h.saver.begin(document(), h.replies::add)
        h.saver.selected { ByteArrayOutputStream() }
        h.finish()
        assertEquals(listOf(GpxSaveStatus.BUSY, GpxSaveStatus.SAVED), h.replies)
    }

    @Test fun invalidatedWriteRetainsSlotAndCannotReplyToNewPage() {
        val h = Harness()
        h.saver.begin(document(), h.replies::add)
        h.saver.selected { ByteArrayOutputStream() }
        h.saver.invalidate()
        assertTrue(h.saver.hasPendingWork())
        h.saver.begin(document(), h.replies::add)
        h.finish()
        assertEquals(listOf(GpxSaveStatus.BUSY), h.replies)
        h.saver.close()
        h.saver.begin(document(), h.replies::add)
        assertEquals(GpxSaveStatus.UNAVAILABLE, h.replies.last())
    }

    @Test fun outputAndCloseFailuresNeverClaimSuccessOrRetry() {
        for (output in listOf<() -> java.io.OutputStream?>(
            { null }, { throw IOException("private provider detail") },
            { object : ByteArrayOutputStream() { override fun close() { throw IOException("close failed") } } },
        )) {
            val h = Harness()
            h.saver.begin(document(), h.replies::add)
            h.saver.selected(output)
            h.finish()
            assertEquals(listOf(GpxSaveStatus.WRITE_FAILED), h.replies)
            assertTrue(h.work.isEmpty())
            val reply = GpxDocumentProtocol.reply(requestId, h.replies.single())
            assertFalse(reply.contains("private"))
            assertEquals(setOf("schema_version", "request_id", "type", "status"),
                JSONObject(reply).keys().asSequence().toSet())
        }
    }

    @Test fun missingPickerFailsExplicitlyAndCanRetryAfterNewClick() {
        val replies = mutableListOf<GpxSaveStatus>()
        val saver = GpxDocumentSaver({ throw IllegalStateException("no picker") }, { it() }, { it() })
        saver.begin(document(), replies::add)
        saver.begin(document(), replies::add)
        assertEquals(listOf(GpxSaveStatus.UNAVAILABLE, GpxSaveStatus.UNAVAILABLE), replies)
    }
}
