package io.github.victorgabillon.sugarglider

import org.json.JSONArray
import org.json.JSONObject
import java.io.File

internal const val ROUTING_PACK_MANIFEST_SCHEMA_VERSION = 2
internal const val ROUTING_PACK_ENGINE = "valhalla"
internal const val ROUTING_PACK_ENGINE_VERSION = "3.9.1"

private const val ROUTING_PACK_MANIFEST_NAME = "manifest.json"
private const val ROUTING_PACK_TILE_ARCHIVE_NAME = "valhalla_tiles.tar"
private const val MAX_ROUTING_PACK_MANIFEST_BYTES = 16 * 1_024L
private const val MAX_ROUTING_PACK_DIRECTORY_CANDIDATES = 64
private val ROUTING_PACK_ID_PATTERN = Regex("^[a-z0-9][a-z0-9._-]{0,63}$")

internal data class RoutingPackBounds(
    val west: Double,
    val south: Double,
    val east: Double,
    val north: Double,
) {
    fun isValid(): Boolean = west.isFinite() &&
        south.isFinite() &&
        east.isFinite() &&
        north.isFinite() &&
        west in -180.0..180.0 &&
        east in -180.0..180.0 &&
        south in -90.0..90.0 &&
        north in -90.0..90.0 &&
        west < east &&
        south < north

    fun contains(coordinate: LocalRouteCoordinate): Boolean = isValid() &&
        coordinate.isValid() &&
        coordinate.longitude in west..east &&
        coordinate.latitude in south..north

    fun area(): Double = (east - west) * (north - south)
}

internal data class RoutingPackManifest(
    val schemaVersion: Int,
    val packId: String,
    val engine: String,
    val engineVersion: String,
    val bounds: RoutingPackBounds,
    val accessModes: List<LocalRouteAccessMode>,
) {
    fun isSupported(directoryPackId: String): Boolean =
        schemaVersion == ROUTING_PACK_MANIFEST_SCHEMA_VERSION &&
            packId == directoryPackId &&
            isRoutingPackId(packId) &&
            engine == ROUTING_PACK_ENGINE &&
            engineVersion == ROUTING_PACK_ENGINE_VERSION &&
            bounds.isValid() &&
            accessModes.isNotEmpty() &&
            accessModes == LocalRouteAccessMode.entries

    companion object {
        fun parse(payload: String, directoryPackId: String): RoutingPackManifest? {
            return try {
                val value = JSONObject(payload)
                val schemaVersion = value.strictInteger("schema_version") ?: return null
                val manifestFields = when (schemaVersion) {
                    ROUTING_PACK_MANIFEST_SCHEMA_VERSION -> MANIFEST_V2_FIELDS
                    else -> return null
                }
                if (!value.hasExactly(manifestFields)) return null
                val boundsValue = value.optJSONObject("bounds") ?: return null
                if (!boundsValue.hasExactly(BOUNDS_FIELDS)) return null
                val manifest = RoutingPackManifest(
                    schemaVersion = schemaVersion,
                    packId = value.strictString("pack_id") ?: return null,
                    engine = value.strictString("engine") ?: return null,
                    engineVersion = value.strictString("engine_version") ?: return null,
                    bounds = RoutingPackBounds(
                        west = boundsValue.strictDouble("west") ?: return null,
                        south = boundsValue.strictDouble("south") ?: return null,
                        east = boundsValue.strictDouble("east") ?: return null,
                        north = boundsValue.strictDouble("north") ?: return null,
                    ),
                    accessModes = value.strictAccessModes("access_modes") ?: return null,
                )
                manifest.takeIf { it.isSupported(directoryPackId) }
            } catch (_: Exception) {
                null
            }
        }

        private val BASE_MANIFEST_FIELDS = setOf(
            "schema_version",
            "pack_id",
            "engine",
            "engine_version",
            "bounds",
        )
        private val MANIFEST_V2_FIELDS = BASE_MANIFEST_FIELDS + "access_modes"
        private val BOUNDS_FIELDS = setOf("west", "south", "east", "north")
    }
}

internal data class RoutingPack(
    val manifest: RoutingPackManifest,
    val tileArchive: File,
    val tileArchiveLength: Long,
    val tileArchiveLastModified: Long,
    val elevationDirectory: File? = null,
    val regionalReference: RegionalRoutingPackReference? = null,
) {
    val packId: String
        get() = manifest.packId

    fun covers(points: List<LocalRouteCoordinate>): Boolean = points.isNotEmpty() &&
        points.all(manifest.bounds::contains)

    fun supports(accessMode: LocalRouteAccessMode): Boolean = accessMode in manifest.accessModes

    internal fun actorKey(): RoutingPackActorKey = RoutingPackActorKey(
        packId = packId,
        tileArchivePath = tileArchive.absolutePath,
        tileArchiveLength = tileArchiveLength,
        tileArchiveLastModified = tileArchiveLastModified,
        elevationPath = elevationDirectory?.absolutePath,
        elevationIdentity = regionalReference?.elevation?.manifest?.sha256,
    )
}

internal class RoutingPackRegistry(private val rootDirectory: File) {
    fun installedPacks(): List<RoutingPack> {
        val canonicalRoot = rootDirectory.canonicalFileOrNull() ?: return emptyList()
        if (!canonicalRoot.isDirectory) return emptyList()
        return canonicalRoot.listFiles()
            ?.asSequence()
            ?.filter { it.isDirectory && isRoutingPackId(it.name) }
            ?.sortedBy(File::getName)
            ?.take(MAX_ROUTING_PACK_DIRECTORY_CANDIDATES)
            ?.mapNotNull { loadPack(canonicalRoot, it) }
            ?.sortedBy(RoutingPack::packId)
            ?.toList()
            ?: emptyList()
    }

    fun select(
        points: List<LocalRouteCoordinate>,
        accessMode: LocalRouteAccessMode,
    ): RoutingPackSelection {
        val geographicallyEligible = installedPacks()
            .filter { it.covers(points) }
        if (geographicallyEligible.isEmpty()) {
            return RoutingPackSelection.NoGeographicCoverage
        }
        val selected = geographicallyEligible
            .asSequence()
            .filter { it.supports(accessMode) }
            .minWithOrNull(
                compareBy<RoutingPack> { it.manifest.bounds.area() }
                    .thenBy(RoutingPack::packId),
            ) ?: return RoutingPackSelection.NoCompatibleAccessMode
        return RoutingPackSelection.Selected(selected)
    }

    private fun loadPack(canonicalRoot: File, directoryEntry: File): RoutingPack? {
        val directory = directoryEntry.canonicalFileOrNull() ?: return null
        if (
            directory.parentFile != canonicalRoot ||
            directory.name != directoryEntry.name ||
            !directory.isDirectory
        ) return null
        val manifestFile = confinedFile(directory, ROUTING_PACK_MANIFEST_NAME) ?: return null
        if (
            !manifestFile.isFile ||
            !manifestFile.canRead() ||
            manifestFile.length() !in 1..MAX_ROUTING_PACK_MANIFEST_BYTES
        ) return null
        val tileArchive = confinedFile(directory, ROUTING_PACK_TILE_ARCHIVE_NAME) ?: return null
        val archiveLength = tileArchive.length()
        if (!validTileArchive(tileArchive, archiveLength)) return null
        val manifest = RoutingPackManifest.parse(
            manifestFile.readText(Charsets.UTF_8),
            directoryEntry.name,
        ) ?: return null
        return RoutingPack(
            manifest = manifest,
            tileArchive = tileArchive,
            tileArchiveLength = archiveLength,
            tileArchiveLastModified = tileArchive.lastModified(),
        )
    }

    private fun confinedFile(directory: File, name: String): File? =
        File(directory, name).canonicalFileOrNull()?.takeIf {
            it.parentFile == directory && it.name == name
        }

    private fun validTileArchive(file: File, length: Long): Boolean {
        if (
            !file.isFile ||
            !file.canRead() ||
            length < TAR_BLOCK_BYTES ||
            length % TAR_BLOCK_BYTES != 0L
        ) return false
        return validV2ValhallaArchive(file)
    }

    private companion object {
        const val TAR_BLOCK_BYTES = 512L
        const val TAR_NAME_BYTES = 100
        const val TAR_MAGIC_OFFSET = 257
        const val TAR_MAGIC = "ustar"
        const val VALHALLA_INDEX_ENTRY = "index.bin"
    }
}

internal sealed interface RoutingPackSelection {
    data class Selected(val pack: RoutingPack) : RoutingPackSelection

    data object NoGeographicCoverage : RoutingPackSelection

    data object NoCompatibleAccessMode : RoutingPackSelection
}

internal data class RoutingPackActorSelection<T : Any>(
    val actor: T,
    val coldStart: Boolean,
    val packId: String,
)

internal class SingleCurrentRoutingPackActor<T : Any>(
    private val disposeActor: (T) -> Unit = {},
    private val createActor: (RoutingPack) -> T,
) {
    private var current: CurrentActor<T>? = null

    @Synchronized
    fun actorFor(pack: RoutingPack): RoutingPackActorSelection<T> {
        val key = pack.actorKey()
        current?.takeIf { it.key == key }?.let {
            return RoutingPackActorSelection(it.actor, coldStart = false, pack.packId)
        }
        // Valhalla Mobile 0.6.4 owns a persistent native actor/mmap per instance.
        // Close the old actor BEFORE constructing the replacement, so a switch
        // never retains both graph archives. A failed switch leaves no actor.
        release()
        val created = createActor(pack)
        current = CurrentActor(key, created)
        return RoutingPackActorSelection(created, coldStart = true, pack.packId)
    }

    @Synchronized
    fun release() {
        val previous = current ?: return
        current = null
        disposeActor(previous.actor)
    }

    @Synchronized
    internal fun currentPackId(): String? = current?.key?.packId

    private data class CurrentActor<T : Any>(
        val key: RoutingPackActorKey,
        val actor: T,
    )
}

internal fun isRoutingPackId(value: String): Boolean = ROUTING_PACK_ID_PATTERN.matches(value)

internal data class RoutingPackActorKey(
    val packId: String,
    val tileArchivePath: String,
    val tileArchiveLength: Long,
    val tileArchiveLastModified: Long,
    val elevationPath: String?,
    val elevationIdentity: String?,
)

private fun File.canonicalFileOrNull(): File? = try {
    canonicalFile
} catch (_: Exception) {
    null
}

private fun JSONObject.hasExactly(expected: Set<String>): Boolean {
    val actual = mutableSetOf<String>()
    val iterator = keys()
    while (iterator.hasNext()) actual += iterator.next()
    return actual == expected
}

private fun JSONObject.strictInteger(name: String): Int? = opt(name) as? Int

private fun JSONObject.strictString(name: String): String? = opt(name) as? String

private fun JSONObject.strictDouble(name: String): Double? = (opt(name) as? Number)
    ?.toDouble()
    ?.takeIf(Double::isFinite)
    ?.canonicalCoordinate()

private fun JSONObject.strictAccessModes(name: String): List<LocalRouteAccessMode>? {
    val values = opt(name) as? JSONArray ?: return null
    if (values.length() !in 1..LocalRouteAccessMode.entries.size) return null
    val parsed = buildList {
        repeat(values.length()) { index ->
            val value = values.opt(index) as? String ?: return null
            add(LocalRouteAccessMode.parse(value) ?: return null)
        }
    }
    return parsed.takeIf {
        it == LocalRouteAccessMode.entries.filter(it::contains)
    }
}
