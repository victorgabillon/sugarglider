package io.github.victorgabillon.sugarglider

import android.content.Context
import android.os.storage.StorageManager
import java.io.File

// Constructing the adapter is cheap. The store invokes both platform operations
// on its caller's worker, after creating the private root and before downloading
// the archive. No external-storage permission or alternate directory is used.
internal fun createRegionalRoutingPackStore(context: Context): RegionalRoutingPackStore {
    val application = context.applicationContext
    val root = File(application.filesDir, "regional-routing-packs")
    val manager = application.getSystemService(StorageManager::class.java)
    return RegionalRoutingPackStore(
        rootDirectory = root,
        prepareArchive = { output, bytes ->
            try {
                if (manager == null) throw RegionalPackException(RegionalPackFailure.STORAGE_UNAVAILABLE)
                manager.allocateBytes(output.fd, bytes)
            } catch (_: Exception) {
                throw RegionalPackException(RegionalPackFailure.STORAGE_UNAVAILABLE)
            }
        },
        availableBytes = {
            try {
                if (manager == null) throw RegionalPackException(RegionalPackFailure.STORAGE_UNAVAILABLE)
                manager.getAllocatableBytes(manager.getUuidForPath(root))
            } catch (_: Exception) {
                throw RegionalPackException(RegionalPackFailure.STORAGE_UNAVAILABLE)
            }
        },
    )
}
