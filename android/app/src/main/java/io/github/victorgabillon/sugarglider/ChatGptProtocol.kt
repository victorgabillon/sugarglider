package io.github.victorgabillon.sugarglider

import org.json.JSONObject

internal class ChatGptCommand(val action: String, val accountId: String? = null,
    val model: String? = null, val instructions: String? = null, val input: String? = null,
    val research: Boolean = false, val schema: JSONObject? = null, val operationId: String? = null)

internal object ChatGptProtocol {
    fun parse(value: JSONObject): ChatGptCommand? = runCatching {
        val action = value.getString("type").removePrefix("chatgpt_")
        val base = setOf("schema_version","request_id","type")
        fun exact(fields: Set<String>) { require(value.keys().asSequence().toSet() == base + fields) }
        fun text(key: String, maximum: Int): String {
            val raw = value.get(key)
            require(raw is String && raw.length in 1..maximum && raw.none { it.isISOControl() && it !in "\n\r\t" })
            return raw
        }
        when (action) {
            "status", "models", "sign_out", "cancel" -> { exact(emptySet()); ChatGptCommand(action) }
            "sign_in", "select" -> {
                exact(setOf("account_id"))
                val id = if (action == "sign_in" && value.isNull("account_id")) null else text("account_id",256)
                require(id == null || id.matches(Regex("oaiapp_[A-Za-z0-9_-]+")))
                ChatGptCommand(action,accountId=id)
            }
            "infer" -> {
                exact(setOf("model","instructions","input","research","output_schema") + if (value.has("operation_id")) setOf("operation_id") else emptySet())
                val operationId = if (value.has("operation_id")) text("operation_id",32).also { require(it.matches(Regex("[a-f0-9]{32}"))) } else null
                require(value.get("research") is Boolean)
                val schema = if (value.isNull("output_schema")) null else value.getJSONObject("output_schema")
                require(schema == null || schema.toString().length <= 24_576)
                ChatGptCommand(action,model=text("model",128),instructions=text("instructions",24_576),
                    input=text("input",32_768),research=value.getBoolean("research"),schema=schema,operationId=operationId)
            }
            else -> null
        }
    }.getOrNull()
    fun reply(requestId: String, result: JSONObject? = null, error: String? = null): String = JSONObject()
        .put("schema_version",SCHEMA_VERSION).put("request_id",requestId).put("type","chatgpt_result")
        .put("result",result ?: JSONObject.NULL).put("error",error ?: JSONObject.NULL).toString()
}
