package io.github.victorgabillon.sugarglider

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BridgeProtocolTest {
    @Test
    fun exactOriginMainFrameCurrentWebViewAccepted() {
        assertTrue(BridgeGate.accepts(TEST_ORIGIN, TEST_ORIGIN, true, 7, 7))
    }

    @Test
    fun equivalentWebViewOriginSpellingAcceptedAfterCanonicalization() {
        val configured = "http://localhost:8000"
        val source = ServerOrigin.parse("http://localhost:8000/", true)?.normalized
        assertEquals(configured, source)
        assertTrue(BridgeGate.accepts(requireNotNull(source), configured, true, 7, 7))
    }

    @Test
    fun differentCanonicalWebViewOriginsRemainRejected() {
        val configured = "http://localhost:8000"
        for (rawSource in listOf(
            "http://127.0.0.1:8000",
            "http://localhost:8001",
            "https://localhost:8000",
        )) {
            val source = ServerOrigin.parse(rawSource, true)?.normalized
            assertNotNull(source)
            assertFalse(BridgeGate.accepts(requireNotNull(source), configured, true, 7, 7))
        }
    }

    @Test
    fun malformedWebViewOriginsFailClosedBeforeBridgeGate() {
        for (rawSource in listOf(
            "not an origin",
            "javascript:alert(1)",
            "http://user:secret@localhost:8000",
            "http://localhost:8000/hostile",
        )) {
            assertNull(ServerOrigin.parse(rawSource, true)?.normalized)
        }
    }

    @Test
    fun wrongOriginRejected() {
        assertFalse(BridgeGate.accepts("https://evil.test", TEST_ORIGIN, true, 7, 7))
    }

    @Test
    fun subframeRejected() {
        assertFalse(BridgeGate.accepts(TEST_ORIGIN, TEST_ORIGIN, false, 7, 7))
    }

    @Test
    fun staleWebViewRejected() {
        assertFalse(BridgeGate.accepts(TEST_ORIGIN, TEST_ORIGIN, true, 8, 7))
    }

    @Test
    fun unknownAndMalformedMessagesCannotStart() {
        assertNull(BridgeProtocol.parse("not-json"))
        assertNull(BridgeProtocol.parse(base("launch_secret_tracker")))
    }

    @Test
    fun extraAuthorityFieldRejected() {
        val payload = JSONObject(startPayload()).put("owner_token", "forbidden").toString()
        assertNull(BridgeProtocol.parse(payload))
    }

    @Test
    fun validStartHasStrictFields() {
        val request = BridgeProtocol.parse(startPayload())
        assertTrue(request is BridgeRequest.StartTracking)
        assertEquals(TEST_PARTICIPANT, (request as BridgeRequest.StartTracking).participantId)
    }

    @Test
    fun replyContainsNoTokenOrCoordinate() {
        val reply = BridgeProtocol.reply(
            "tracking_status",
            "request-1",
            NativeTrackingStatus(
                TEST_SLUG,
                TEST_PARTICIPANT,
                true,
                "sharing",
                TEST_NOW,
                true,
                null,
            ),
        )
        assertFalse(reply.contains(TEST_TOKEN))
        assertFalse(reply.contains("coordinate"))
        assertFalse(reply.contains("latitude"))
    }

    @Test
    fun duplicateRequestIdReturnsCachedReply() {
        val ledger = BridgeRequestLedger()
        val payload = base("hello")
        val request = requireNotNull(BridgeProtocol.parse(payload))
        assertTrue(ledger.begin(request, payload))
        ledger.complete(request, payload, "safe-reply")
        assertEquals("safe-reply", ledger.lookup(request, payload))
        assertFalse(ledger.begin(request, payload))
    }

    @Test
    fun reusedRequestIdWithDifferentPayloadFailsSafely() {
        val ledger = BridgeRequestLedger()
        val first = base("hello")
        val request = requireNotNull(BridgeProtocol.parse(first))
        ledger.begin(request, first)
        ledger.complete(request, first, "safe-reply")
        val changedPayload = base("get_status")
        val changed = requireNotNull(BridgeProtocol.parse(changedPayload))
        val failure = ledger.lookup(changed, changedPayload)
        assertNotNull(failure)
        assertTrue(failure!!.contains("permanent_failure"))
        assertFalse(failure.contains(TEST_TOKEN))
    }

    @Test
    fun newPageNonceCannotReceiveOldPageCachedStatus() {
        val ledger = BridgeRequestLedger()
        val firstPayload = base("get_status", FIRST_NONCE)
        val first = requireNotNull(BridgeProtocol.parse(firstPayload))
        ledger.begin(first, firstPayload)
        ledger.complete(first, firstPayload, "stopped-page-one")

        val secondPayload = base("get_status", SECOND_NONCE)
        val second = requireNotNull(BridgeProtocol.parse(secondPayload))
        assertNull(ledger.lookup(second, secondPayload))
        assertTrue(ledger.begin(second, secondPayload))
        ledger.complete(second, secondPayload, "sharing-page-two")
        assertEquals("sharing-page-two", ledger.lookup(second, secondPayload))
        assertEquals("stopped-page-one", ledger.lookup(first, firstPayload))
    }

    @Test
    fun startAndStopCountersDoNotCollideAcrossPages() {
        val ledger = BridgeRequestLedger()
        val startPayload = startPayload(FIRST_NONCE)
        val start = requireNotNull(BridgeProtocol.parse(startPayload))
        val stopPayload = stopPayload(SECOND_NONCE)
        val stop = requireNotNull(BridgeProtocol.parse(stopPayload))
        assertTrue(ledger.begin(start, startPayload))
        assertTrue(ledger.begin(stop, stopPayload))
        ledger.complete(start, startPayload, "start-result")
        ledger.complete(stop, stopPayload, "stop-result")
        assertEquals("start-result", ledger.lookup(start, startPayload))
        assertEquals("stop-result", ledger.lookup(stop, stopPayload))
    }

    private fun base(type: String, nonce: String = FIRST_NONCE): String = JSONObject()
        .put("schema_version", 1)
        .put("request_id", "web-$nonce-1")
        .put("type", type)
        .toString()

    private fun startPayload(nonce: String = FIRST_NONCE): String = JSONObject()
        .put("schema_version", 1)
        .put("request_id", "web-$nonce-1")
        .put("type", "start_tracking")
        .put("server_origin", TEST_ORIGIN)
        .put("outing_slug", TEST_SLUG)
        .put("participant_id", TEST_PARTICIPANT)
        .put("participant_token", TEST_TOKEN)
        .put("outing_expires_at", TEST_NOW.plusSeconds(3_600).toString())
        .put("current_sequence", 10L)
        .toString()

    private fun stopPayload(nonce: String): String = JSONObject()
        .put("schema_version", 1)
        .put("request_id", "web-$nonce-1")
        .put("type", "stop_tracking")
        .put("outing_slug", TEST_SLUG)
        .put("participant_id", TEST_PARTICIPANT)
        .toString()

    private companion object {
        const val FIRST_NONCE = "0123456789abcdef0123456789abcdef"
        const val SECOND_NONCE = "fedcba9876543210fedcba9876543210"
    }
}
