package io.github.victorgabillon.sugarglider

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ApplicationLanguageTest {
    private fun request(language: Any): JSONObject = JSONObject()
        .put("schema_version", 1).put("type", "set_ui_language")
        .put("request_id", "web-0123456789abcdef0123456789abcdef-1").put("language", language)

    @Test fun onlyExplicitSupportedLanguagesCrossTheBridge() {
        for (language in listOf("fr", "en")) {
            val parsed = BridgeProtocol.parse(request(language).toString()) as BridgeRequest.SetUiLanguage
            assertEquals(language, parsed.language)
            assertTrue(BundledShellPolicy.acceptsOrigin(parsed, BundledShellPolicy.ORIGIN))
            assertFalse(BundledShellPolicy.acceptsOrigin(parsed, "https://example.invalid"))
            assertTrue(BundledShellPolicy.acceptsRequest(parsed))
        }
        for (language in listOf<Any>("", "FR", "fr-FR", "de", true, 1, JSONObject.NULL)) {
            assertNull(BridgeProtocol.parse(request(language).toString()))
        }
        assertNull(BridgeProtocol.parse(request("fr").put("url", "https://example.invalid").toString()))
    }

    @Test fun unsupportedNativePreferencesAreNeverAccepted() {
        assertTrue(ApplicationLanguage.valid("fr"))
        assertTrue(ApplicationLanguage.valid("en"))
        for (language in listOf("", "FR", "fr-FR", "de", " en")) assertFalse(ApplicationLanguage.valid(language))
        assertEquals("en", ApplicationLanguage.normalized("en"))
        for (value in listOf(null, "fr", "EN", "en-US", "de", true, 3, emptyMap<String, String>())) {
            assertEquals("fr", ApplicationLanguage.normalized(value))
        }
    }
}
