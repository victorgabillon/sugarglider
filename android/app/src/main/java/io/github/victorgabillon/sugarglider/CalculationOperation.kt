package io.github.victorgabillon.sugarglider

import org.json.JSONObject

/** One immutable user operation. All calls are serialized on Android's main thread. */
internal class CalculationOperation(private val persist: (JSONObject) -> Unit = {}) {
    private class Run(val id: String, val owner: String, val kind: String, val prompt: String?, val cancel: () -> Unit, ready: () -> Unit) {
        val readyCallbacks = mutableListOf(ready)
        var started = false
        var modelCalls = 0
    }
    private var active: Run? = null
    private val retiredIds = linkedSetOf<String>()
    var onIdle: (() -> Unit)? = null
    val activeId: String? get() = active?.id

    fun begin(id: String, owner: String, kind: String, prompt: String?, ready: () -> Unit = {}, cancel: () -> Unit): Boolean {
        require(id.matches(Regex("[a-f0-9]{32}")) && kind in setOf("adventure", "offline"))
        require(if (kind == "adventure") prompt != null && prompt.length in 3..8000 else prompt == null)
        if (id in retiredIds) return false
        active?.let {
            if (it.id != id || it.owner != owner || it.kind != kind || it.prompt != prompt || it.readyCallbacks.size >= 4) return false
            if (it.started) ready() else it.readyCallbacks.add(ready)
            return true
        }
        // Only ID, state and the user's original text; no pins, geometry or credentials.
        val run = Run(id, owner, kind, prompt, cancel, ready)
        persist(record(run, "running"))
        active = run
        return true
    }
    fun ready(id: String) {
        val run = active?.takeIf { it.id == id && !it.started } ?: return
        run.started = true
        val callbacks = run.readyCallbacks.toList(); run.readyCallbacks.clear()
        callbacks.forEach { it() }
    }
    fun owns(owner: String, id: String? = activeId): Boolean = active?.let { it.owner == owner && it.id == id } == true
    fun reserveModel(owner: String, id: String): Boolean {
        val run = active ?: return false
        if (run.kind != "adventure" || !run.started || !owns(owner, id) || run.modelCalls >= 2) return false
        run.modelCalls++
        return true
    }
    fun finish(owner: String, id: String, state: String): Boolean {
        require(state in setOf("completed", "cancelled", "failed", "interrupted", "timeout"))
        if (!owns(owner, id)) return false
        return end(id, state, false)
    }
    fun cancel(id: String, state: String = "cancelled"): Boolean = end(id, state, true)
    fun interruptOwner(owner: String) { active?.takeIf { it.owner == owner }?.let { cancel(it.id, "interrupted") } }
    private fun end(id: String, state: String, cancel: Boolean): Boolean {
        val run = active?.takeIf { it.id == id } ?: return false
        active = null
        retiredIds.add(id)
        if (retiredIds.size > 32) retiredIds.remove(retiredIds.first())
        try { runCatching { persist(record(run, state)) } } finally {
            try { if (cancel) run.cancel() } finally { onIdle?.invoke() }
        }
        return true
    }
    private fun record(run: Run, state: String): JSONObject = JSONObject().put("schema_version", 1)
        .put("operation_id", run.id).put("kind", run.kind).put("state", state).put("prompt", run.prompt ?: JSONObject.NULL)
}

internal class CalculationCommand(val action: String, val operationId: String? = null,
    val kind: String? = null, val prompt: String? = null, val state: String? = null)

internal object CalculationProtocol {
    fun parse(value: JSONObject): CalculationCommand? = runCatching {
        val action = value.getString("type").removePrefix("calculation_")
        val fields = when (action) {
            "begin" -> setOf("operation_id", "kind", "prompt")
            "finish" -> setOf("operation_id", "state")
            "forget" -> setOf("operation_id")
            "recovery" -> emptySet()
            else -> return null
        }
        require(value.keys().asSequence().toSet() == fields + setOf("schema_version", "request_id", "type"))
        if (action == "recovery") return CalculationCommand(action)
        val id = value.getString("operation_id").also { require(it.matches(Regex("[a-f0-9]{32}"))) }
        if (action == "forget") return CalculationCommand(action, id)
        if (action == "finish") {
            val state = value.getString("state").also { require(it in setOf("completed", "cancelled", "failed", "interrupted")) }
            CalculationCommand(action, id, state = state)
        } else {
            val kind = value.getString("kind").also { require(it in setOf("adventure", "offline")) }
            val prompt = if (value.isNull("prompt")) null else value.getString("prompt")
            require(if (kind == "adventure") prompt != null && prompt.length in 3..8000 else prompt == null)
            CalculationCommand(action, id, kind, prompt)
        }
    }.getOrNull()
    fun reply(requestId: String, id: String? = null, state: String, recovery: JSONObject? = null): String = JSONObject()
        .put("schema_version", 1).put("request_id", requestId).put("type", "calculation_result")
        .put("operation_id", id ?: JSONObject.NULL).put("state", state).put("recovery", recovery ?: JSONObject.NULL).toString()
}
