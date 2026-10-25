package io.github.victorgabillon.sugarglider

import java.io.Reader
import org.json.JSONObject

/** Bounded native SSE reader. Partial deltas are never an accepted model answer. */
internal object ChatGptResponseStream {
    const val MAX_STREAM_CHARS: Int = 2_097_152
    const val MAX_EVENT_CHARS: Int = 262_144
    const val MAX_TEXT_CHARS: Int = 65_536

    fun read(reader: Reader, cancelled: () -> Boolean = { false }): String {
        val line = StringBuilder()
        val data = StringBuilder()
        var total = 0
        var sawCompleted = false
        var answer: String? = null
        fun event() {
            if (data.isEmpty()) return
            val payload = data.toString().trimEnd('\n')
            data.setLength(0)
            // [DONE] alone does not establish a successful response.
            if (payload == "[DONE]") return
            boundDepth(payload)
            val json = try { JSONObject(payload) } catch (_: Exception) { throw IllegalArgumentException("Invalid model stream.") }
            when (json.optString("type")) {
                "response.failed", "response.incomplete", "error" -> {
                    val code = json.optJSONObject("response")?.optJSONObject("error")?.optString("code") ?: json.optString("code")
                    throw ChatGptException(if (code in setOf("subscription_sharing_usage_limit_exceeded", "subscription_sharing_usage_unavailable")) ChatGptFailureKind.USAGE_LIMIT else ChatGptFailureKind.INVALID_RESPONSE)
                }
                "response.completed" -> {
                    check(!sawCompleted) { "Duplicate model completion." }
                    val response = json.optJSONObject("response") ?: error("Model completion missing.")
                    check(response.optString("status") == "completed") { "Model response was not completed." }
                    val output = response.optJSONArray("output") ?: error("Model output missing.")
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
                    answer = text.toString()
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
            if (next == '\n'.code) finishLine()
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
