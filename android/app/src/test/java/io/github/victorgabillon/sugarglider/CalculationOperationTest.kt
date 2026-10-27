package io.github.victorgabillon.sugarglider

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class CalculationOperationTest {
    private val id = "a".repeat(32)
    private val owner = "b".repeat(32)
    @Test fun oneIdentityOwnsBothModelCallsAndCannotBeRebound() {
        val records = mutableListOf<JSONObject>()
        val operation = CalculationOperation { records.add(it) }
        var starts = 0
        assertTrue(operation.begin(id, owner, "adventure", "Original text", { starts++ }) {})
        assertTrue(operation.begin(id, owner, "adventure", "Original text", { starts++ }) {})
        assertFalse(operation.begin(id, owner, "adventure", "Changed text") {})
        assertFalse(operation.begin("c".repeat(32), owner, "adventure", "Original text") {})
        assertFalse(operation.reserveModel(owner, id)) // no model before notification readiness
        operation.ready(id); operation.ready(id)
        assertEquals(2, starts)
        assertTrue(operation.reserveModel(owner, id)); assertTrue(operation.reserveModel(owner, id))
        assertFalse(operation.reserveModel(owner, id)); assertFalse(operation.reserveModel("wrong", id))
        assertEquals(1, records.size)
        assertEquals(setOf("schema_version", "operation_id", "kind", "prompt", "state"), records[0].keys().asSequence().toSet())
        assertFalse(records[0].toString().contains("token"))
    }
    @Test fun cancellationAndLateCompletionCannotAffectANewerOperation() {
        var cancelled = 0; var idle = 0
        val operation = CalculationOperation().apply { onIdle = { idle++ } }
        operation.begin(id, owner, "offline", null) { cancelled++ }; operation.ready(id)
        assertTrue(operation.cancel(id)); assertFalse(operation.cancel(id))
        assertFalse(operation.begin(id, owner, "offline", null) { cancelled++ })
        val next = "c".repeat(32)
        operation.begin(next, owner, "offline", null) { cancelled++ }
        assertFalse(operation.finish(owner, id, "completed")); assertFalse(operation.cancel(id))
        operation.interruptOwner("unrelated"); assertEquals(next, operation.activeId)
        operation.interruptOwner(owner)
        assertEquals(2, cancelled); assertEquals(2, idle); assertNull(operation.activeId)
    }
    @Test fun persistenceFailureNeverPreventsCancellationOrLeavesAnIdleService() {
        var calls = 0; var cancelled = false; var idle = false
        val operation = CalculationOperation { if (++calls > 1) error("disk failure") }
        operation.onIdle = { idle = true }
        operation.begin(id, owner, "adventure", "Original text") { cancelled = true }
        operation.cancel(id, "timeout")
        assertTrue(cancelled); assertTrue(idle); assertNull(operation.activeId)
        val failing = CalculationOperation { error("cannot journal") }
        assertThrows(IllegalStateException::class.java) { failing.begin(id, owner, "adventure", "Original text") {} }
        assertNull(failing.activeId)
    }
    @Test fun protocolHasExactFieldsAndBoundedOriginalText() {
        fun begin() = JSONObject().put("type", "calculation_begin").put("schema_version", 1).put("request_id", "test")
            .put("operation_id", id).put("kind", "adventure").put("prompt", "Original text")
        assertNotNull(CalculationProtocol.parse(begin()))
        assertNull(CalculationProtocol.parse(begin().put("token", "private")))
        assertNull(CalculationProtocol.parse(begin().put("prompt", "x".repeat(8001))))
        assertNull(CalculationProtocol.parse(begin().put("operation_id", "bad")))
        assertNull(CalculationProtocol.parse(begin().put("kind", "offline")))
        val large = "é".repeat(8000)
        val envelope = begin().put("prompt", large).put("request_id", "web-${owner}-1")
        assertTrue(BridgeProtocol.parse(envelope.toString()) is BridgeRequest.Calculation)
    }
}
