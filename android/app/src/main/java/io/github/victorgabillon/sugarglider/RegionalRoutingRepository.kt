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
    private val leases = mutableMapOf<IdentityPath, Int>()

    fun <T> withPack(reference: RegionalRoutingPackReference, action: (RoutingPack) -> T): T {
        if (!reference.isValid()) throw RegionalPackException(RegionalPackFailure.INVALID_REFERENCE)
        val path = IdentityPath(reference.regionId, reference.buildId, reference.packId)
        synchronized(gate) {
            if (leases.values.sum() >= MAX_LEASES) throw RegionalPackException(RegionalPackFailure.BUSY)
            leases[path] = (leases[path] ?: 0) + 1
        }
        try { return action(openPack(reference)) }
        finally {
            synchronized(gate) {
                val remaining = requireNotNull(leases[path]) - 1
                if (remaining == 0) leases.remove(path) else leases[path] = remaining
            }
        }
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

    private companion object { const val MAX_LEASES = 16 }
}
