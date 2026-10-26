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
    private fun item(text: String, index: Int = 0): JSONObject = JSONObject().put("type","response.output_item.done")
        .put("output_index",index).put("item",JSONObject().put("type","message").put("role","assistant").put("status","completed")
            .put("content",JSONArray().put(JSONObject().put("type","output_text").put("text",text))))
    private fun emptyCompletion(): String = event(JSONObject().put("type","response.completed")
        .put("response",JSONObject().put("status","completed").put("output",JSONArray())
            .put("usage",JSONObject().put("input_tokens",3).put("output_tokens",2).put("total_tokens",5))))
    @Test fun preservesHostedSearchSourcesSeparatelyFromResponseCitations() {
        val url = "https://official.invalid/landmark"
        val search = JSONObject().put("type","web_search_call").put("status","completed")
            .put("action",JSONObject().put("sources",org.json.JSONArray()
                .put(JSONObject().put("type","url").put("url",url).put("title","Official landmark"))
                .put(JSONObject().put("type","url").put("url","javascript:unsafe"))
                .put(JSONObject().put("type","url").put("url","https://user:synthetic@official.invalid/"))))
        val response = JSONObject().put("output",org.json.JSONArray().put(search))
        val result = ChatGptCompletion.from(response,"synthetic JSON answer")
        assertEquals(1,result.citations.length())
        assertEquals("research_source",result.citations.getJSONObject(0).getString("evidence"))
        val message = JSONObject().put("content",org.json.JSONArray().put(JSONObject().put("annotations",org.json.JSONArray()
            .put(JSONObject().put("type","url_citation").put("url",url)))))
        response.getJSONArray("output").put(message)
        val cited = ChatGptCompletion.from(response,"synthetic JSON answer")
        assertEquals(1,cited.citations.length())
        assertEquals("response_citation",cited.citations.getJSONObject(0).getString("evidence"))
        search.put("status","failed")
        assertEquals(0,ChatGptCompletion.from(response,"synthetic").citations.length())
    }

    @Test fun acceptsOnlyCompletedTerminalOutputNotDeltas() {
        val delta = event(JSONObject().put("type", "response.output_text.delta").put("delta", "not authoritative"))
        assertEquals("synthetic answer", ChatGptResponseStream.read(StringReader(delta + completed())))
        assertEquals("synthetic answer", ChatGptResponseStream.read(StringReader(completed().replace("\n", "\r\n"))))
        for (raw in listOf(delta, "data: [DONE]\n\n", completed().trimEnd())) {
            assertThrows(IllegalStateException::class.java) { ChatGptResponseStream.read(StringReader(raw)) }
        }
    }
    @Test fun rejectsFailuresEvenAfterDeltasOrCompletion() {
        for (type in listOf("response.failed", "response.incomplete", "error")) {
            val failure = event(JSONObject().put("type", type).put("code", "subscription_sharing_usage_limit_exceeded"))
            assertThrows(IllegalStateException::class.java) { ChatGptResponseStream.read(StringReader(failure)) }
            assertEquals("synthetic answer", ChatGptResponseStream.read(StringReader(completed() + failure)))
        }
        assertEquals("synthetic answer", ChatGptResponseStream.read(StringReader(completed() + completed())))
    }
    @Test fun retainsOnlyActualResearchCitationsAndMeasuredUsage() {
        val response = JSONObject().put("usage",JSONObject().put("input_tokens",12).put("output_tokens",8).put("total_tokens",20))
            .put("output",org.json.JSONArray().put(JSONObject().put("type","web_search_call").put("status","completed"))
                .put(JSONObject().put("type","message").put("content",org.json.JSONArray().put(JSONObject().put("annotations",org.json.JSONArray()
                    .put(JSONObject().put("type","url_citation").put("url","https://example.invalid/source").put("title","Source"))
                    .put(JSONObject().put("type","url_citation").put("url","javascript:bad").put("title","Bad")))))))
        val result = ChatGptCompletion.from(response,"synthetic")
        assertTrue(result.researched);assertEquals(1,result.citations.length());assertEquals(20,result.usage.getInt("total_tokens"))
        response.getJSONArray("output").remove(0)
        assertEquals(0,ChatGptCompletion.from(response,"synthetic").citations.length())
    }
    @Test fun enforcesSizeNestingAndCancellation() {
        assertThrows(IllegalArgumentException::class.java) { ChatGptResponseStream.read(StringReader("x".repeat(ChatGptResponseStream.MAX_EVENT_CHARS + 1))) }
        assertThrows(IllegalArgumentException::class.java) { ChatGptResponseStream.read(StringReader(completed("a".repeat(ChatGptResponseStream.MAX_TEXT_CHARS + 1)))) }
        assertThrows(IllegalArgumentException::class.java) { ChatGptResponseStream.read(StringReader("data: " + "[".repeat(33) + "]".repeat(33) + "\n\n")) }
        assertThrows(IllegalStateException::class.java) { ChatGptResponseStream.read(StringReader(completed())) { true } }
        assertThrows(IllegalArgumentException::class.java) { ChatGptResponseStream.read(StringReader("data: invalid\n\n")) }
    }
    @Test fun boundsResearchFromStreamEventsAndCompletedOutput() {
        fun call(id: String): String = event(JSONObject().put("type","response.output_item.added")
            .put("item",JSONObject().put("type","web_search_call").put("id",id)))
        val four = (1..4).joinToString("") { call("call-$it") }
        assertEquals("synthetic answer",ChatGptResponseStream.read(StringReader(four + call("call-1") + completed())))
        assertThrows(IllegalArgumentException::class.java) { ChatGptResponseStream.read(StringReader(four + call("call-5") + completed())) }
        val terminal = JSONObject(completed().removePrefix("data: ").trim())
        val output = terminal.getJSONObject("response").getJSONArray("output")
        repeat(5) { output.put(JSONObject().put("type","web_search_call").put("status","completed")) }
        assertThrows(IllegalArgumentException::class.java) { ChatGptResponseStream.read(StringReader(event(terminal))) }
    }
    @Test fun completedItemsRequireTerminalCompletionAndKeepActualUsageAndCitations() {
        val message = item("synthetic answer")
        message.getJSONObject("item").getJSONArray("content").getJSONObject(0).put("annotations",JSONArray()
            .put(JSONObject().put("type","url_citation").put("url","https://example.invalid/source").put("title","Synthetic source")))
        val research = event(JSONObject().put("type","response.output_item.done").put("output_index",1)
            .put("item",JSONObject().put("type","web_search_call").put("status","completed")))
        val result = ChatGptResponseStream.completed(StringReader(event(message) + research + emptyCompletion()))
        assertEquals("synthetic answer",result.text);assertTrue(result.researched)
        assertEquals(5,result.usage.getInt("total_tokens"));assertEquals(1,result.citations.length())
        for (suffix in listOf("", "data: [DONE]\n\n",event(JSONObject().put("type","response.incomplete")))) {
            assertThrows(IllegalStateException::class.java) { ChatGptResponseStream.read(StringReader(event(message) + suffix)) }
        }
        val delta = event(JSONObject().put("type","response.output_text.delta").put("delta","not authoritative"))
        assertThrows(IllegalStateException::class.java) { ChatGptResponseStream.read(StringReader(delta + emptyCompletion())) }
        assertThrows(IllegalStateException::class.java) { ChatGptResponseStream.read(StringReader(event(message).trimEnd() + emptyCompletion())) }
    }
    @Test fun completedItemsUseOutputOrderWithoutDuplicatingTheAggregate() {
        val reversedArrival = event(item("second",1)) + event(item("first",0))
        assertEquals("firstsecond",ChatGptResponseStream.read(StringReader(reversedArrival + emptyCompletion())))
        assertEquals("synthetic answer",ChatGptResponseStream.read(StringReader(event(item("synthetic answer")) + completed())))
    }
    @Test fun boundsAndValidatesCompletedItemsBeforeAcceptingAnEmptyAggregate() {
        val incomplete = item("partial");incomplete.getJSONObject("item").put("status","in_progress")
        val user = item("untrusted");user.getJSONObject("item").put("role","user")
        for (raw in listOf(event(incomplete),event(user),event(item("one")) + event(item("duplicate")))) {
            assertThrows(IllegalStateException::class.java) { ChatGptResponseStream.read(StringReader(raw + emptyCompletion())) }
        }
        for (raw in listOf(event(item("out of range",16)),event(item("large".repeat(60_000))),
            event(item("a".repeat(40_000),0)) + event(item("b".repeat(40_000),1)))) {
            assertThrows(IllegalArgumentException::class.java) { ChatGptResponseStream.read(StringReader(raw + emptyCompletion())) }
        }
        val searches = (0..4).joinToString("") { index -> event(JSONObject().put("type","response.output_item.done").put("output_index",index)
            .put("item",JSONObject().put("type","web_search_call").put("status","completed"))) }
        assertThrows(IllegalArgumentException::class.java) { ChatGptResponseStream.read(StringReader(searches + event(item("answer",5)) + emptyCompletion())) }
    }
}
