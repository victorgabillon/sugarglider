package io.github.victorgabillon.sugarglider

import java.io.StringReader
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ChatGptResponseStreamTest {
    private fun event(value: JSONObject): String = "data: $value\n\n"
    private fun completed(text: String = "synthetic answer"): String = event(JSONObject()
        .put("type", "response.completed").put("response", JSONObject().put("status", "completed")
            .put("output", JSONArray().put(JSONObject().put("type", "message").put("role", "assistant").put("status", "completed")
                .put("content", JSONArray().put(JSONObject().put("type", "output_text").put("text", text)))))))
    @Test fun acceptsOnlyCompletedTerminalOutputNotDeltas() {
        val delta = event(JSONObject().put("type", "response.output_text.delta").put("delta", "not authoritative"))
        assertEquals("synthetic answer", ChatGptResponseStream.read(StringReader(delta + completed())))
        assertEquals("synthetic answer", ChatGptResponseStream.read(StringReader(completed().replace("\n", "\r\n"))))
        for (raw in listOf(delta, "data: [DONE]\n\n", completed().trimEnd(), completed() + "data: {")) {
            assertThrows(IllegalStateException::class.java) { ChatGptResponseStream.read(StringReader(raw)) }
        }
    }
    @Test fun rejectsFailuresEvenAfterDeltasOrCompletion() {
        for (type in listOf("response.failed", "response.incomplete", "error")) {
            val failure = event(JSONObject().put("type", type).put("code", "subscription_sharing_usage_limit_exceeded"))
            assertThrows(IllegalStateException::class.java) { ChatGptResponseStream.read(StringReader(failure)) }
            assertThrows(IllegalStateException::class.java) { ChatGptResponseStream.read(StringReader(completed() + failure)) }
        }
        assertThrows(IllegalStateException::class.java) { ChatGptResponseStream.read(StringReader(completed() + completed())) }
    }
    @Test fun enforcesSizeNestingAndCancellation() {
        assertThrows(IllegalArgumentException::class.java) { ChatGptResponseStream.read(StringReader("x".repeat(ChatGptResponseStream.MAX_EVENT_CHARS + 1))) }
        assertThrows(IllegalArgumentException::class.java) { ChatGptResponseStream.read(StringReader(completed("a".repeat(ChatGptResponseStream.MAX_TEXT_CHARS + 1)))) }
        assertThrows(IllegalArgumentException::class.java) { ChatGptResponseStream.read(StringReader("data: " + "[".repeat(33) + "]".repeat(33) + "\n\n")) }
        assertThrows(IllegalStateException::class.java) { ChatGptResponseStream.read(StringReader(completed())) { true } }
        assertThrows(IllegalArgumentException::class.java) { ChatGptResponseStream.read(StringReader("data: invalid\n\n")) }
    }
}
