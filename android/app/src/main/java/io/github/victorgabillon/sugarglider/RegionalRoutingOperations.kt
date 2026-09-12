package io.github.victorgabillon.sugarglider

import java.util.concurrent.Executor
import java.util.concurrent.atomic.AtomicBoolean

internal enum class RegionalRoutingAction { INSPECT, INSTALL, REMOVE }

internal data class RegionalRoutingCommand(
    val operationId: String,
    val action: RegionalRoutingAction,
    val reference: RegionalRoutingPackReference,
    val manifestUrl: String? = null,
)

internal data class RegionalRoutingOperationStatus(
    val operationId: String,
    val state: String,
    val receivedBytes: Long = 0,
    val totalBytes: Long = 0,
    val code: RegionalPackFailure? = null,
)

// One application-owned worker and one latest operation, with no durable queue.
// Page invalidation requests cancellation; ownership lasts until file work ends.
internal class RegionalRoutingOperations(
    private val executor: Executor,
    private val inspect: (RegionalRoutingPackReference) -> Unit,
    private val install: (RegionalRoutingPackReference, String, () -> Boolean, (Long) -> Unit) -> Unit,
    private val remove: (RegionalRoutingPackReference) -> Unit,
) {
    private val gate = Any()
    private var current: Operation? = null

    fun start(owner: String, command: RegionalRoutingCommand): RegionalRoutingOperationStatus = synchronized(gate) {
        val old = current
        if (old != null && old.owner == owner && old.command == command) return@synchronized old.status
        if (old?.status?.state == "running") return@synchronized failure(command.operationId, RegionalPackFailure.BUSY)
        if (!command.reference.isValid() || !validOperationId(command.operationId) ||
            (command.action == RegionalRoutingAction.INSTALL) != (command.manifestUrl != null)
        ) return@synchronized failure(command.operationId, RegionalPackFailure.INVALID_REFERENCE)
        val operation = Operation(owner, command, RegionalRoutingOperationStatus(command.operationId, "running",
            totalBytes = if (command.action == RegionalRoutingAction.INSTALL) command.reference.archive.byteSize else 0))
        current = operation
        try { executor.execute { execute(operation) } }
        catch (_: Exception) { operation.status = failure(command.operationId, RegionalPackFailure.UNAVAILABLE) }
        operation.status
    }

    fun status(owner: String, operationId: String): RegionalRoutingOperationStatus = synchronized(gate) {
        matching(owner, operationId)?.status ?: failure(operationId, RegionalPackFailure.UNAVAILABLE)
    }

    fun cancel(owner: String, operationId: String): RegionalRoutingOperationStatus = synchronized(gate) {
        val operation = matching(owner, operationId) ?: return@synchronized failure(operationId, RegionalPackFailure.UNAVAILABLE)
        operation.cancelled.set(true)
        operation.status
    }

    fun cancelOwner(owner: String) = synchronized(gate) {
        current?.takeIf { it.owner == owner }?.cancelled?.set(true)
        Unit
    }

    private fun matching(owner: String, id: String) = current?.takeIf {
        it.owner == owner && it.command.operationId == id
    }

    private fun execute(operation: Operation) {
        val command = operation.command
        val outcome = try {
            checkCancelled(operation)
            when (command.action) {
                RegionalRoutingAction.INSPECT -> inspect(command.reference)
                RegionalRoutingAction.INSTALL -> install(command.reference, requireNotNull(command.manifestUrl),
                    operation.cancelled::get) { received ->
                    synchronized(gate) {
                        if (received !in operation.status.receivedBytes..operation.status.totalBytes) {
                            throw RegionalPackException(RegionalPackFailure.SIZE_MISMATCH)
                        }
                        operation.status = operation.status.copy(receivedBytes = received)
                    }
                }
                RegionalRoutingAction.REMOVE -> remove(command.reference)
            }
            // Removal is already definite once its filesystem operation succeeds.
            if (command.action != RegionalRoutingAction.REMOVE) checkCancelled(operation)
            RegionalRoutingOperationStatus(command.operationId,
                if (command.action == RegionalRoutingAction.REMOVE) "removed" else "ready",
                receivedBytes = if (command.action == RegionalRoutingAction.INSTALL) command.reference.archive.byteSize else 0,
                totalBytes = if (command.action == RegionalRoutingAction.INSTALL) command.reference.archive.byteSize else 0)
        } catch (error: Exception) {
            failure(command.operationId, if (error is RegionalPackException) error.code else RegionalPackFailure.UNAVAILABLE)
        }
        synchronized(gate) { operation.status = outcome }
    }

    private fun checkCancelled(operation: Operation) {
        if (operation.cancelled.get()) throw RegionalPackException(RegionalPackFailure.CANCELLED)
    }

    private class Operation(val owner: String, val command: RegionalRoutingCommand, var status: RegionalRoutingOperationStatus) {
        val cancelled = AtomicBoolean(false)
    }

    private fun failure(id: String, code: RegionalPackFailure) = RegionalRoutingOperationStatus(id, "failed", code = code)

    companion object {
        fun validOperationId(value: String): Boolean = value.matches(Regex("[a-f0-9]{32}"))
    }
}
