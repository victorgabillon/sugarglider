package io.github.victorgabillon.sugarglider

import java.util.concurrent.Executor
import java.util.concurrent.atomic.AtomicBoolean

internal enum class RegionalRoutingAction { INSPECT, INSTALL, REMOVE }

internal sealed interface RegionalOperationCommand {
    val operationId: String
    val totalBytes: Long
    val removesData: Boolean
    fun isValid(): Boolean
}

internal data class RegionalRoutingCommand(
    override val operationId: String,
    val action: RegionalRoutingAction,
    val reference: RegionalRoutingPackReference,
    val manifestUrl: String? = null,
) : RegionalOperationCommand {
    override val totalBytes: Long get() = if (action == RegionalRoutingAction.INSTALL) reference.archive.byteSize else 0
    override val removesData: Boolean get() = action == RegionalRoutingAction.REMOVE
    override fun isValid(): Boolean = reference.isValid() &&
        (action == RegionalRoutingAction.INSTALL) == (manifestUrl != null)
}

internal data class RegionalRoutingVersionRemoval(
    override val operationId: String,
    val version: RegionalRoutingVersion,
) : RegionalOperationCommand {
    override val totalBytes: Long = 0
    override val removesData: Boolean = true
    override fun isValid(): Boolean = version.isValid()
}

internal data class RegionalRoutingRegionRemoval(
    override val operationId: String,
    val regionId: String,
) : RegionalOperationCommand {
    override val totalBytes: Long = 0
    override val removesData: Boolean = true
    override fun isValid(): Boolean = isRoutingPackId(regionId) && !regionId.contains("..")
}

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
    private val removeVersion: (RegionalRoutingVersion) -> Unit,
    private val removeRegion: (String) -> Unit,
) {
    private val gate = Any()
    private var current: Operation? = null

    fun start(owner: String, command: RegionalOperationCommand): RegionalRoutingOperationStatus = synchronized(gate) {
        val old = current
        if (old != null && old.owner == owner && old.command == command) return@synchronized old.status
        if (old?.status?.state == "running") return@synchronized failure(command.operationId, RegionalPackFailure.BUSY)
        if (!command.isValid() || !validOperationId(command.operationId)) {
            return@synchronized failure(command.operationId, RegionalPackFailure.INVALID_REFERENCE)
        }
        val operation = Operation(owner, command, RegionalRoutingOperationStatus(command.operationId, "running",
            totalBytes = command.totalBytes))
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
            when (command) {
                is RegionalRoutingRegionRemoval -> removeRegion(command.regionId)
                is RegionalRoutingVersionRemoval -> removeVersion(command.version)
                is RegionalRoutingCommand -> when (command.action) {
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
            }
            // Removal is already definite once its filesystem operation succeeds.
            if (!command.removesData) checkCancelled(operation)
            RegionalRoutingOperationStatus(command.operationId,
                if (command.removesData) "removed" else "ready",
                receivedBytes = command.totalBytes, totalBytes = command.totalBytes)
        } catch (error: Exception) {
            failure(command.operationId, if (error is RegionalPackException) error.code else RegionalPackFailure.UNAVAILABLE)
        }
        synchronized(gate) { operation.status = outcome }
    }

    private fun checkCancelled(operation: Operation) {
        if (operation.cancelled.get()) throw RegionalPackException(RegionalPackFailure.CANCELLED)
    }

    private class Operation(val owner: String, val command: RegionalOperationCommand, var status: RegionalRoutingOperationStatus) {
        val cancelled = AtomicBoolean(false)
    }

    private fun failure(id: String, code: RegionalPackFailure) = RegionalRoutingOperationStatus(id, "failed", code = code)

    companion object {
        fun validOperationId(value: String): Boolean = value.matches(Regex("[a-f0-9]{32}"))
    }
}
