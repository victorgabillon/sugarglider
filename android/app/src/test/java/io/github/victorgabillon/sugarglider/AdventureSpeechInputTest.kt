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
    @Test fun speechCommandsRequireExactOriginAndExplicitPlatformChoice() {
        val value = envelope("start").put("language", "fr-FR").put("allow_platform", false)
        val parsed = BridgeProtocol.parse(value.toString()) as BridgeRequest.AdventureSpeech
        assertFalse(parsed.allowPlatform)
        assertTrue(BundledShellPolicy.acceptsOrigin(parsed, BundledShellPolicy.ORIGIN))
        assertFalse(BundledShellPolicy.acceptsOrigin(parsed, "https://untrusted.invalid"))
        assertTrue(V1ReleasePolicy.acceptsBridge(parsed, BundledShellPolicy.ORIGIN))
        for (change in listOf("language" to "fr-FR;execute", "allow_platform" to "true", "audio_url" to "https://untrusted.invalid")) {
            assertNull(BridgeProtocol.parse(JSONObject(value.toString()).put(change.first, change.second).toString()))
        }
        assertNull(BridgeProtocol.parse(envelope("start").put("language", "fr-FR").toString()))
        assertNotNull(BridgeProtocol.parse(envelope("cancel").toString()))
        assertNull(BridgeProtocol.parse(envelope("background_start").toString()))
    }
}
