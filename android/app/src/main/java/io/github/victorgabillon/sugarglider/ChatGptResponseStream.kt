package io.github.victorgabillon.sugarglider

import java.io.Reader
import org.json.JSONObject

/** Bounded native SSE reader. Partial deltas are never an accepted model answer. */
internal object ChatGptResponseStream {
    const val MAX_STREAM_CHARS: Int = 2_097_152
    const val MAX_EVENT_CHARS: Int = 262_144
    const val MAX_TEXT_CHARS: Int = 65_536
    const val MAX_RESEARCH_CALLS: Int = 4
    const val MAX_COMPLETED_ITEMS: Int = 16

    fun read(reader: Reader, cancelled: () -> Boolean = { false }): String = completed(reader,cancelled).text

    fun completed(reader: Reader, cancelled: () -> Boolean = { false }): ChatGptCompletion {
        val line = StringBuilder()
        val data = StringBuilder()
        var total = 0
        var sawCompleted = false
        var answer: ChatGptCompletion? = null
        val researchCalls = mutableSetOf<String>()
        val completedItems = sortedMapOf<Int,JSONObject>()
        var completedItemChars = 0
        fun event() {
            if (data.isEmpty()) return
            val payload = data.toString().trimEnd('\n')
            data.setLength(0)
            // [DONE] alone does not establish a successful response.
            if (payload == "[DONE]") return
            boundDepth(payload)
            val json = try { JSONObject(payload) } catch (_: Exception) { throw IllegalArgumentException("Invalid model stream.") }
            when (json.optString("type")) {
                "response.output_item.done" -> {
                    val item = json.getJSONObject("item")
                    if (item.optString("type") in setOf("message","web_search_call")) {
                        val index = json.get("output_index")
                        require(index is Int && index in 0 until MAX_COMPLETED_ITEMS) { "Invalid completed item index." }
                        check(!completedItems.containsKey(index)) { "Duplicate completed item." }
                        if (item.optString("type") == "message") {
                            check(item.optString("role") == "assistant" && item.optString("status") == "completed") { "Incomplete model message." }
                        }
                        completedItemChars += item.toString().length
                        require(completedItemChars <= MAX_EVENT_CHARS) { "Completed model items are too large." }
                        completedItems[index] = item
                        require(completedItems.values.count { it.optString("type") == "web_search_call" } <= MAX_RESEARCH_CALLS) { "Research budget exceeded." }
                    }
                }
                "response.output_item.added" -> {
                    val item = json.optJSONObject("item")
                    if (item?.optString("type") == "web_search_call") {
                        val id = item.getString("id")
                        require(id.length in 1..256) { "Invalid research call identity." }
                        researchCalls.add(id)
                        require(researchCalls.size <= MAX_RESEARCH_CALLS) { "Research budget exceeded." }
                    }
                }
                "response.failed", "response.incomplete", "error" -> {
                    val code = json.optJSONObject("response")?.optJSONObject("error")?.optString("code") ?: json.optString("code")
                    throw ChatGptException(if (code in setOf("subscription_sharing_usage_limit_exceeded", "subscription_sharing_usage_unavailable")) ChatGptFailureKind.USAGE_LIMIT else ChatGptFailureKind.INVALID_RESPONSE)
                }
                "response.completed" -> {
                    check(!sawCompleted) { "Duplicate model completion." }
                    val response = json.optJSONObject("response") ?: error("Model completion missing.")
                    check(response.optString("status") == "completed") { "Model response was not completed." }
                    var output = response.optJSONArray("output") ?: error("Model output missing.")
                    // Some plan-sharing completions omit the aggregate items.
                    // Only item.done messages can supply that output, and only
                    // after this terminal response has itself completed.
                    if (output.length() == 0 && completedItems.isNotEmpty()) {
                        output = org.json.JSONArray(completedItems.values.toList())
                        response.put("output",output)
                    }
                    require(output.length() <= MAX_COMPLETED_ITEMS) { "Too many completed model items." }
                    require((0 until output.length()).count { output.getJSONObject(it).optString("type") == "web_search_call" } <= MAX_RESEARCH_CALLS) { "Research budget exceeded." }
                    val text = StringBuilder()
                    for (index in 0 until output.length()) {
                        val item = output.getJSONObject(index)
                        if (item.optString("type") != "message") continue
                        check(item.optString("role") == "assistant" && item.optString("status") == "completed") { "Incomplete model message." }
                        val content = item.getJSONArray("content")
                        for (n in 0 until content.length()) {
                            val part = content.getJSONObject(n)
                            check(part.optString("type") == "output_text") { "Model did not provide an answer." }
                            val value = part.get("text")
                            require(value is String) { "Invalid model text." }
                            require(text.length + value.length <= MAX_TEXT_CHARS) { "Model answer is too large." }
                            text.append(value)
                        }
                    }
                    check(text.isNotBlank()) { "Model answer is empty." }
                    sawCompleted = true
                    answer = ChatGptCompletion.from(response,text.toString())
                }
            }
        }
        fun finishLine() {
            val value = line.toString().removeSuffix("\r")
            line.setLength(0)
            if (value.isEmpty()) event()
            else if (value.startsWith("data:")) {
                val chunk = value.removePrefix("data:").removePrefix(" ")
                require(data.length + chunk.length + 1 <= MAX_EVENT_CHARS) { "Model event is too large." }
                data.append(chunk).append('\n')
            }
        }
        while (true) {
            check(!cancelled()) { "Model request cancelled." }
            val next = reader.read()
            if (next == -1) break
            total += 1
            require(total <= MAX_STREAM_CHARS) { "Model stream is too large." }
            if (next == '\n'.code) {
                finishLine()
                if (sawCompleted) return answer ?: error("Model answer missing.")
            }
            else {
                require(line.length < MAX_EVENT_CHARS) { "Model stream line is too large." }
                line.append(next.toChar())
            }
        }
        // An event requires its SSE blank-line terminator. Truncated JSON at EOF
        // cannot convert an interrupted answer into success.
        check(sawCompleted && line.isEmpty() && data.isEmpty()) { "Model stream interrupted." }
        return answer ?: error("Model answer missing.")
    }

    private fun boundDepth(source: String) {
        var quoted = false
        var escaped = false
        var depth = 0
        for (c in source) {
            if (quoted) {
                if (escaped) escaped = false
                else if (c == '\\') escaped = true
                else if (c == '"') quoted = false
            } else if (c == '"') quoted = true
            else if (c == '{' || c == '[') { depth += 1; require(depth <= 32) { "Model event is too deeply nested." } }
            else if (c == '}' || c == ']') depth -= 1
        }
    }
}

internal class ChatGptCompletion(val text: String, val usage: JSONObject, val citations: org.json.JSONArray, val researched: Boolean) {
    companion object {
        fun from(response: JSONObject, text: String): ChatGptCompletion {
            val usage = JSONObject()
            for (name in listOf("input_tokens","output_tokens","total_tokens")) {
                val value = response.optJSONObject("usage")?.opt(name)
                usage.put(name, if ((value is Int || value is Long) && (value as Number).toLong() in 0..1_000_000_000) value else JSONObject.NULL)
            }
            val output = response.getJSONArray("output")
            val researched = (0 until output.length()).any { val item = output.getJSONObject(it); item.optString("type") == "web_search_call" && item.optString("status") == "completed" }
            val citations = org.json.JSONArray()
            val seen = mutableSetOf<String>()
            if (researched) for (i in 0 until output.length()) {
                val content = output.getJSONObject(i).optJSONArray("content") ?: continue
                for (n in 0 until content.length()) {
                    val annotations = content.getJSONObject(n).optJSONArray("annotations") ?: continue
                    for (k in 0 until minOf(annotations.length(),40)) {
                        val source = annotations.getJSONObject(k)
                        if (source.optString("type") != "url_citation") continue
                        val url = source.optString("url")
                        val uri = runCatching { java.net.URI(url) }.getOrNull() ?: continue
                        if (citations.length() >= 40 || url.length > 2048 || uri.scheme != "https" || uri.host.isNullOrEmpty() || uri.rawUserInfo != null || !seen.add(url)) continue
                        val title = source.optString("title").take(300).filterNot(Char::isISOControl)
                        citations.put(JSONObject().put("url",url).put("title",title))
                    }
                }
            }
            return ChatGptCompletion(text,usage,citations,researched)
        }
    }
}
