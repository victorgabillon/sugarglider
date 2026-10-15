package io.github.victorgabillon.sugarglider

// One application-owned repository coordinates native reads and explicit removal.
// Staging writes only fresh immutable versions and uses the store's mutation lock.
// Every route holds its lease through the complete native call, even if its page
// disappears before the result is delivered. No graph selection or cache lives here.
internal class RegionalRoutingRepository(
    private val openPack: (RegionalRoutingPackReference) -> RoutingPack,
    private val removePack: (RegionalRoutingPackReference) -> Unit,
    private val removeVersionFiles: (RegionalRoutingVersion) -> Unit,
    private val removeRegionFiles: (String) -> Unit,
) {
    private val gate = Any()
    private val leases = mutableMapOf<IdentityPath, LeaseState>()

    fun <T> withPack(reference: RegionalRoutingPackReference, action: (RoutingPack) -> T): T {
        return acquire(reference).use { action(it.pack) }
    }

    fun acquire(reference: RegionalRoutingPackReference): RegionalPackLease {
        if (!reference.isValid()) throw RegionalPackException(RegionalPackFailure.INVALID_REFERENCE)
        val path = IdentityPath(reference.regionId, reference.buildId, reference.packId)
        synchronized(gate) {
            if (leases.values.sumOf { it.count } >= MAX_LEASES) throw RegionalPackException(RegionalPackFailure.BUSY)
            val state = leases.getOrPut(path) { LeaseState(reference) }
            if (state.reference != reference) throw RegionalPackException(RegionalPackFailure.IDENTITY_MISMATCH)
            state.count++
        }
        fun release() {
            synchronized(gate) {
                val state = requireNotNull(leases[path])
                state.count--
                if (state.count == 0) leases.remove(path)
            }
        }
        try {
            // Verification happens once during a lease lifetime. Immutable
            // private files cannot be replaced/removed while an actor owns one.
            val existing = synchronized(gate) { leases[path]?.pack }
            val opened = existing ?: openPack(reference)
            val pack = synchronized(gate) {
                val state = requireNotNull(leases[path])
                state.pack ?: opened.also { state.pack = it }
            }
            return RegionalPackLease(pack, ::release)
        } catch (error: Exception) { release(); throw error }
    }

    fun remove(reference: RegionalRoutingPackReference) {
        if (!reference.isValid()) throw RegionalPackException(RegionalPackFailure.INVALID_REFERENCE)
        synchronized(gate) {
            val path = IdentityPath(reference.regionId, reference.buildId, reference.packId)
            if (path in leases) throw RegionalPackException(RegionalPackFailure.BUSY)
            // New readers cannot acquire the same path halfway through removal.
            removePack(reference)
        }
    }

    fun removeVersion(version: RegionalRoutingVersion) {
        if (!version.isValid()) throw RegionalPackException(RegionalPackFailure.INVALID_REFERENCE)
        synchronized(gate) {
            if (leases.keys.any { it.regionId == version.regionId && it.buildId == version.buildId }) {
                throw RegionalPackException(RegionalPackFailure.BUSY)
            }
            removeVersionFiles(version)
        }
    }

    fun removeRegion(regionId: String) {
        if (!isRoutingPackId(regionId) || regionId.contains("..")) throw RegionalPackException(RegionalPackFailure.INVALID_REFERENCE)
        synchronized(gate) {
            if (leases.keys.any { it.regionId == regionId }) throw RegionalPackException(RegionalPackFailure.BUSY)
            removeRegionFiles(regionId)
        }
    }

    private data class IdentityPath(val regionId: String, val buildId: String, val packId: String)
    private class LeaseState(val reference: RegionalRoutingPackReference, var count: Int = 0, var pack: RoutingPack? = null)

    private companion object { const val MAX_LEASES = 16 }
}

internal class RegionalPackLease(val pack: RoutingPack, private val release: () -> Unit) : AutoCloseable {
    private val closed = java.util.concurrent.atomic.AtomicBoolean(false)
    override fun close() { if (closed.compareAndSet(false, true)) release() }
}
