package io.github.victorgabillon.sugarglider

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ChatGptProtocolTest {
    private fun envelope(type: String): JSONObject = JSONObject().put("schema_version",1)
        .put("request_id","web-" + "a".repeat(32) + "-1").put("type",type)
    @Test fun boundsInferenceAndRejectsArbitraryOperationsAndSecrets() {
        val value = envelope("chatgpt_infer").put("model","available").put("instructions","First line\nSecond line")
            .put("input","Une aventure en forêt").put("research",false).put("output_schema",JSONObject.NULL)
        val parsed = BridgeProtocol.parse(value.toString()) as BridgeRequest.ChatGpt
        assertEquals("infer",parsed.command.action)
        assertTrue(BundledShellPolicy.acceptsRequest(parsed))
        assertTrue(BundledShellPolicy.acceptsOrigin(parsed,BundledShellPolicy.ORIGIN))
        assertFalse(BundledShellPolicy.acceptsOrigin(parsed,"https://untrusted.invalid"))
        for ((key,v) in listOf("endpoint" to "https://untrusted.invalid", "access_token" to "forbidden", "research" to "true", "input" to "a".repeat(32769))) {
            val invalid = JSONObject(value.toString()).put(key,v)
            assertNull(BridgeProtocol.parse(invalid.toString()))
        }
        assertNull(BridgeProtocol.parse(envelope("chatgpt_execute_native_command").toString()))
    }
    @Test fun accountOperationsHaveExactFields() {
        assertNotNull(BridgeProtocol.parse(envelope("chatgpt_sign_in").put("account_id",JSONObject.NULL).toString()))
        assertNull(BridgeProtocol.parse(envelope("chatgpt_select").put("account_id",JSONObject.NULL).toString()))
        assertNull(BridgeProtocol.parse(envelope("chatgpt_select").put("account_id","../../private").toString()))
        assertNotNull(BridgeProtocol.parse(envelope("chatgpt_cancel").toString()))
        assertNull(BridgeProtocol.parse(envelope("chatgpt_status").put("unexpected",true).toString()))
        assertFalse(ChatGptProtocol.reply("test",JSONObject().put("connected",true)).contains("access_token"))
    }
}
