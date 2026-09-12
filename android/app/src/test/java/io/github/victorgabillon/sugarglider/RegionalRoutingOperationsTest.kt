package io.github.victorgabillon.sugarglider

import java.util.concurrent.Executor
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class RegionalRoutingOperationsTest {
    private val reference = syntheticRegionalRoutingReference()
    private val id = "a".repeat(32)
    private val owner = "page-one"

    @Test fun onlyOneWorkerAndLatestOperationAreRetained() {
        val queue = QueueExecutor()
        var calls = 0
        val manager = manager(queue, inspect = { calls++ })
        val command = RegionalRoutingCommand(id, RegionalRoutingAction.INSPECT, reference)
        assertEquals("running", manager.start(owner, command).state)
        assertEquals("running", manager.start(owner, command).state)
        assertEquals(1, queue.work.size)
        assertEquals(RegionalPackFailure.BUSY, manager.start("other", command.copy(operationId = "b".repeat(32))).code)
        assertEquals(RegionalPackFailure.UNAVAILABLE, manager.status("other", id).code)
        queue.run()
        assertEquals(1, calls)
        assertEquals("ready", manager.status(owner, id).state)
        assertEquals("ready", manager.start(owner, command).state)
        assertTrue(queue.work.isEmpty())
        manager.start(owner, command.copy(operationId = "b".repeat(32)))
        assertEquals(RegionalPackFailure.UNAVAILABLE, manager.status(owner, id).code)
    }

    @Test fun cancellationOwnsBusyStateUntilWorkerCleanup() {
        val queue = QueueExecutor()
        var calls = 0
        val manager = manager(queue, inspect = { calls++ })
        val command = RegionalRoutingCommand(id, RegionalRoutingAction.INSPECT, reference)
        manager.start(owner, command)
        assertEquals("running", manager.cancel(owner, id).state)
        assertEquals(RegionalPackFailure.BUSY, manager.start("new-page", command).code)
        queue.run()
        assertEquals(0, calls)
        assertEquals(RegionalPackFailure.CANCELLED, manager.status(owner, id).code)
    }

    @Test fun progressAndCancellationHavePageOwnershipAndDefiniteCompletion() {
        val queue = QueueExecutor()
        lateinit var manager: RegionalRoutingOperations
        var cleaned = false
        manager = RegionalRoutingOperations(queue, {}, { _, _, cancelled, progress ->
            progress(256)
            assertEquals(256, manager.status(owner, id).receivedBytes)
            manager.cancelOwner("old-page")
            assertFalse(cancelled())
            manager.cancelOwner(owner)
            assertTrue(cancelled())
            assertEquals("running", manager.status(owner, id).state)
            cleaned = true
            throw RegionalPackException(RegionalPackFailure.CANCELLED)
        }, {}, {}, {})
        manager.start(owner, RegionalRoutingCommand(id, RegionalRoutingAction.INSTALL, reference, "https://example.org/manifest.json"))
        queue.run()
        assertTrue(cleaned)
        assertEquals(RegionalPackFailure.CANCELLED, manager.status(owner, id).code)
    }

    @Test fun reusedInstallReportsCompleteBytesAndUnexpectedFailuresAreSanitized() {
        val queue = QueueExecutor()
        val manager = RegionalRoutingOperations(queue, { throw IllegalStateException("private source") }, { _, _, _, _ -> }, {}, {}, {})
        manager.start(owner, RegionalRoutingCommand(id, RegionalRoutingAction.INSTALL, reference, "https://example.org/manifest.json"))
        queue.run()
        assertEquals(reference.archive.byteSize, manager.status(owner, id).receivedBytes)
        assertEquals("ready", manager.status(owner, id).state)
        val next = "b".repeat(32)
        manager.start(owner, RegionalRoutingCommand(next, RegionalRoutingAction.INSPECT, reference))
        queue.run()
        val reply = RegionalRoutingProtocol.reply("web-page-2", manager.status(owner, next))
        assertFalse(reply.contains("private source"))
        assertEquals("regional_routing_unavailable", JSONObject(reply).getString("code"))
        assertEquals(8, JSONObject(reply).length())
    }

    @Test fun removalAcknowledgesItsDefiniteOutcomeDespiteLateCancellation() {
        val queue = QueueExecutor()
        lateinit var manager: RegionalRoutingOperations
        manager = RegionalRoutingOperations(queue, {}, { _, _, _, _ -> }, { manager.cancelOwner(owner) }, {}, {})
        manager.start(owner, RegionalRoutingCommand(id, RegionalRoutingAction.REMOVE, reference))
        queue.run()
        assertEquals("removed", manager.status(owner, id).state)
    }

    @Test fun invalidAndRejectedStartsNeverCreateWork() {
        val queue = QueueExecutor()
        val manager = manager(queue)
        val command = RegionalRoutingCommand(id, RegionalRoutingAction.INSTALL, reference)
        assertEquals(RegionalPackFailure.INVALID_REFERENCE, manager.start(owner, command).code)
        assertTrue(queue.work.isEmpty())
        val unavailable = manager(Executor { throw IllegalStateException("closed") })
        assertEquals(RegionalPackFailure.UNAVAILABLE, unavailable.start(owner, command.copy(action = RegionalRoutingAction.INSPECT)).code)
    }

    @Test fun protocolsRejectExtraAuthorityMalformedIdentityAndUnknownActions() {
        for (type in listOf("regional_routing_inspect", "regional_routing_install", "regional_routing_remove")) {
            val json = envelope(type).put("regional_reference", reference.toJson())
            if (type == "regional_routing_install") json.put("manifest_url", "https://example.org/manifest.json")
            val parsed = BridgeProtocol.parse(json.toString())
            assertTrue(type, parsed is BridgeRequest.RegionalWork)
            assertTrue(BundledShellPolicy.acceptsOrigin(requireNotNull(parsed), BundledShellPolicy.ORIGIN))
            assertFalse(BundledShellPolicy.acceptsOrigin(parsed, "https://sharing.example"))
            assertNull(BridgeProtocol.parse(JSONObject(json.toString()).put("participant_token", "private").toString()))
            assertNull(BridgeProtocol.parse(JSONObject(json.toString()).put("operation_id", "../other").toString()))
            assertNull(BridgeProtocol.parse(JSONObject(json.toString()).put("regional_reference", JSONObject.NULL).toString()))
        }
        for (type in listOf("regional_routing_status", "regional_routing_cancel")) {
            val json = envelope(type)
            assertTrue(BridgeProtocol.parse(json.toString()) is BridgeRequest.RegionalStatus)
            assertNull(BridgeProtocol.parse(json.put("manifest_url", "https://example.org").toString()))
        }
        assertNull(BridgeProtocol.parse(envelope("regional_routing_other").toString()))
    }

    private fun envelope(type: String) = JSONObject().put("schema_version", 1).put("request_id", "web-${"a".repeat(32)}-1")
        .put("type", type).put("operation_id", id)

    @Test fun damagedMetadataRemovalUsesOnlyAnExplicitVersionIdentity() {
        val queue = QueueExecutor()
        val removed = mutableListOf<RegionalRoutingVersion>()
        val manager = RegionalRoutingOperations(queue, { error("No inspection") }, { _, _, _, _ -> error("No download") },
            { error("No fabricated reference") }, removed::add, {})
        val version = JSONObject().put("region_id", reference.regionId).put("build_id", reference.buildId)
        val envelope = envelope("regional_routing_remove_version").put("regional_version", version)
        val request = BridgeProtocol.parse(envelope.toString()) as BridgeRequest.RegionalWork
        assertFalse(BundledShellPolicy.acceptsOrigin(request, "https://sharing.example"))
        assertEquals("running", manager.start(owner, request.command).state)
        queue.run()
        assertEquals("removed", manager.status(owner, id).state)
        assertEquals(listOf(RegionalRoutingVersion(reference.regionId, reference.buildId)), removed)
        assertNull(BridgeProtocol.parse(JSONObject(envelope.toString()).put("regional_reference", reference.toJson()).toString()))
        for (invalid in listOf("../other", "a..b", "/private")) {
            val bad = JSONObject(envelope.toString())
            bad.getJSONObject("regional_version").put("region_id", invalid)
            assertNull(BridgeProtocol.parse(bad.toString()))
        }
        version.put("participant_token", "private")
        assertNull(BridgeProtocol.parse(envelope.toString()))
    }

    @Test fun wholeRegionRecoveryNeedsNoFabricatedVersionOrRoutingReference() {
        val queue = QueueExecutor()
        val removed = mutableListOf<String>()
        val manager = RegionalRoutingOperations(queue, {}, { _, _, _, _ -> }, {}, {}, removed::add)
        val envelope = envelope("regional_routing_remove_region").put("region_id", reference.regionId)
        val request = BridgeProtocol.parse(envelope.toString()) as BridgeRequest.RegionalWork
        assertFalse(BundledShellPolicy.acceptsOrigin(request, "https://sharing.example"))
        assertEquals("running", manager.start(owner, request.command).state)
        queue.run()
        assertEquals("removed", manager.status(owner, id).state)
        assertEquals(listOf(reference.regionId), removed)
        assertNull(BridgeProtocol.parse(JSONObject(envelope.toString()).put("build_id", reference.buildId).toString()))
        assertNull(BridgeProtocol.parse(envelope.put("region_id", "../other").toString()))
    }

    private fun manager(executor: Executor, inspect: (RegionalRoutingPackReference) -> Unit = {}) =
        RegionalRoutingOperations(executor, inspect, { _, _, _, _ -> }, {}, {}, {})

    private class QueueExecutor : Executor {
        val work = mutableListOf<Runnable>()
        override fun execute(command: Runnable) { work.add(command) }
        fun run() { work.removeAt(0).run() }
    }
}
