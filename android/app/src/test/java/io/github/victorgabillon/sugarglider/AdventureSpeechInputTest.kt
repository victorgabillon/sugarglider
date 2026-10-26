package io.github.victorgabillon.sugarglider

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class AdventureSpeechInputTest {
    private fun envelope(action: String): JSONObject = JSONObject().put("schema_version", 1)
        .put("request_id", "web-" + "a".repeat(32) + "-1").put("type", "adventure_speech_$action")
    @Test fun onDeviceIsPreferredAndUnavailableRecognitionNeverRequiresSpeech() {
        assertEquals(AdventureSpeechMode.ON_DEVICE, AdventureSpeechPolicy.mode(31, true, true))
        assertEquals(AdventureSpeechMode.ON_DEVICE, AdventureSpeechPolicy.mode(36, true, false))
        assertEquals(AdventureSpeechMode.PLATFORM, AdventureSpeechPolicy.mode(30, false, true))
        assertEquals(AdventureSpeechMode.UNAVAILABLE, AdventureSpeechPolicy.mode(36, false, false))
    }
    @Test fun onlyBoundedEditableTranscriptionIsReturned() {
        assertEquals("Une aventure en forêt", AdventureSpeechPolicy.transcript(" Une aventure en forêt "))
        for (value in listOf(null, "", "   ", "a".repeat(8001), "a\u0000b")) assertNull(AdventureSpeechPolicy.transcript(value))
        val reply = JSONObject(AdventureSpeechPolicy.reply("request", "completed", AdventureSpeechMode.ON_DEVICE, "Editable text"))
        assertEquals(setOf("schema_version", "request_id", "type", "status", "mode", "text"), reply.keys().asSequence().toSet())
        assertEquals("Editable text", reply.getString("text"))
        assertTrue(AdventureSpeechInput.handlesResult(0x6001))
        assertFalse(AdventureSpeechInput.handlesPermission(0x6001))
        assertFalse(AdventureSpeechInput.handlesResult(41))
    }
    @Test fun confirmedSegmentsSurvivePausesWithoutDuplicatingFinalResults() {
        val text = AdventureSpeechTranscript()
        text.partial("Une balade")
        text.partial("Une balade en forêt")
        assertEquals("Une balade en forêt", text.draft())
        assertTrue(text.segment("Une balade en forêt."))
        assertTrue(text.segment("Avec un château."))
        assertEquals("Une balade en forêt. Avec un château.", text.finalResult("Une balade en forêt. Avec un château."))
        assertEquals(text.finalResult(null), text.draft())
    }
    @Test fun interruptedRecognitionKeepsOnlyLatestPartialAndEnforcesTextBound() {
        val text = AdventureSpeechTranscript()
        assertNull(text.draft())
        assertFalse(text.segment("\u0000"))
        assertTrue(text.segment("Départ à Marly."))
        text.partial("Je veux")
        text.partial("Je veux courir trente kilomètres")
        assertEquals("Départ à Marly. Je veux courir trente kilomètres", text.draft())
        assertFalse(text.segment("x".repeat(8000)))
        assertEquals("Départ à Marly.", text.finalResult(null))
        text.partial("x".repeat(8000))
        assertEquals("Départ à Marly.", text.draft())
        // Each new explicit recording starts empty; cancelled text is not reused.
        assertNull(AdventureSpeechTranscript().draft())
    }
    @Test fun speechCommandsRequireExactOriginAndExplicitPlatformChoice() {
        val value = envelope("start").put("language", "fr-FR").put("mode", "on_device")
        val parsed = BridgeProtocol.parse(value.toString()) as BridgeRequest.AdventureSpeech
        assertEquals(AdventureSpeechMode.ON_DEVICE, parsed.mode)
        assertTrue(BundledShellPolicy.acceptsOrigin(parsed, BundledShellPolicy.ORIGIN))
        assertFalse(BundledShellPolicy.acceptsOrigin(parsed, "https://untrusted.invalid"))
        assertTrue(V1ReleasePolicy.acceptsBridge(parsed, BundledShellPolicy.ORIGIN))
        for (change in listOf("language" to "fr-FR;execute", "mode" to "auto", "audio_url" to "https://untrusted.invalid")) {
            assertNull(BridgeProtocol.parse(JSONObject(value.toString()).put(change.first, change.second).toString()))
        }
        assertNull(BridgeProtocol.parse(envelope("start").put("language", "fr-FR").toString()))
        assertNotNull(BridgeProtocol.parse(envelope("cancel").toString()))
        assertNotNull(BridgeProtocol.parse(envelope("stop").toString()))
        assertEquals(AdventureSpeechMode.PLATFORM, (BridgeProtocol.parse(JSONObject(value.toString()).put("mode", "platform").toString()) as BridgeRequest.AdventureSpeech).mode)
        assertNull(BridgeProtocol.parse(envelope("stop").put("audio", "anything").toString()))
        assertNull(BridgeProtocol.parse(envelope("background_start").toString()))
    }
}
