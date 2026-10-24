package io.github.victorgabillon.sugarglider

import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import java.security.MessageDigest
import java.util.zip.GZIPInputStream
import kotlin.math.floor
import org.json.JSONArray
import org.json.JSONObject

internal const val HGT_DECODED_BYTES = 25_934_402L
internal const val HGT_PIXELS = 12_967_201L
internal const val MAX_HGT_COMPRESSED_BYTES = 26_982_978L

internal data class RegionalElevationTile(val path: String, val identity: RegionalFileIdentity) {
    fun toJson(): JSONObject = identity.toJson().put("path", path)
}

internal data class RegionalElevationReference(
    val componentId: String,
    val manifest: RegionalFileIdentity,
    val tiles: List<RegionalElevationTile>,
) {
    val byteSize: Long get() = manifest.byteSize + tiles.sumOf { it.identity.byteSize }
    fun isValid(bounds: RoutingPackBounds): Boolean = isRoutingPackId(componentId) && !componentId.contains("..") &&
        manifest.isValid(65_536) && tiles.size in 1..16 &&
        tiles.map { it.path } == elevationTilePaths(bounds) &&
        tiles.all { it.identity.isValid(MAX_HGT_COMPRESSED_BYTES) }

    fun toJson(): JSONObject = JSONObject().put("component_id", componentId)
        .put("manifest", manifest.toJson()).put("tiles", JSONArray(tiles.map { it.toJson() }))

    companion object {
        fun parse(value: JSONObject?): RegionalElevationReference? {
            if (value == null || value.keys().asSequence().toSet() != setOf("component_id", "manifest", "tiles")) return null
            val rows = value.optJSONArray("tiles") ?: return null
            if (rows.length() !in 1..16) return null
            val tiles = (0 until rows.length()).map { index ->
                val row = rows.optJSONObject(index) ?: return null
                if (row.keys().asSequence().toSet() != setOf("path", "byte_size", "sha256")) return null
                val identity = RegionalFileIdentity.parse(JSONObject().put("byte_size", row.opt("byte_size"))
                    .put("sha256", row.opt("sha256"))) ?: return null
                RegionalElevationTile(row.opt("path") as? String ?: return null, identity)
            }
            return RegionalElevationReference(value.opt("component_id") as? String ?: return null,
                RegionalFileIdentity.parse(value.optJSONObject("manifest")) ?: return null, tiles)
        }
    }
}

internal fun elevationTilePaths(bounds: RoutingPackBounds): List<String> {
    if (!bounds.isValid() || bounds.east >= 180) return emptyList()
    val west = floor(bounds.west).toInt()
    val east = floor(bounds.east).toInt()
    val south = floor(bounds.south).toInt()
    val north = floor(bounds.north).toInt()
    if ((east - west + 1) * (north - south + 1) !in 1..16) return emptyList()
    return (south..north).flatMap { lat -> (west..east).map { lon ->
        val prefix = (if (lat < 0) "S" else "N") + kotlin.math.abs(lat).toString().padStart(2, '0')
        val name = prefix + (if (lon < 0) "W" else "E") + kotlin.math.abs(lon).toString().padStart(3, '0')
        "skadi/$prefix/$name.hgt.gz"
    } }.sorted()
}

/** One bounded stream buffer; native Skadi alone performs runtime interpolation. */
internal object RegionalElevationValidation {
    fun verify(directory: File, reference: RegionalRoutingPackReference, cancelled: () -> Boolean = { false }) {
        val elevation = reference.elevation
        check(elevation.isValid(reference.bounds))
        check(directory.canonicalFile == directory.absoluteFile && directory.isDirectory)
        val expected = setOf("manifest.json") + elevation.tiles.map { it.path }
        val actual = mutableSetOf<String>()
        val directories = setOf("", "skadi") + elevation.tiles.map { it.path.substringBeforeLast('/') }
        Files.walk(directory.toPath(), 4).use { paths ->
            paths.forEach { path ->
                check(!Files.isSymbolicLink(path))
                if (Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
                    check(actual.add(directory.toPath().relativize(path).toString()))
                    check(actual.size <= 17)
                } else check(Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS) &&
                    directory.toPath().relativize(path).toString() in directories)
            }
        }
        check(actual == expected)
        val manifestFile = File(directory, "manifest.json")
        verifyIdentity(manifestFile, elevation.manifest, cancelled)
        val manifest = JSONObject(manifestFile.readText(Charsets.UTF_8))
        val ign = manifest.opt("provenance_status") == "documented" && manifest.opt("vertical_datum") == "IGN69"
        val publicIgn = ign && manifest.opt("publication_allowed") == true
        check(manifest.keys().asSequence().toSet() == setOf("schema_version", "component_id", "bounds", "format",
            "publication_allowed", "provenance_status", "vertical_datum", "tiles") + (if (ign) setOf("derivation") else emptySet()) +
            (if (publicIgn) setOf("publication_basis_sha256") else emptySet()))
        // Reader compatibility is separate from the independently pinned export
        // approval. A flag alone cannot turn private IGN metadata into a release.
        if (ign) check(validIgnPublicationMetadata(manifest))
        check(manifest.opt("schema_version") == 1 && manifest.opt("component_id") == elevation.componentId)
        check(manifest.opt("format") == "skadi-hgt-gzip-v1" && manifest.opt("publication_allowed") is Boolean)
        val documented = manifest.opt("provenance_status") == "documented" && manifest.opt("vertical_datum") == "EGM96"
        val research = manifest.opt("provenance_status") == "unresolved" && manifest.opt("vertical_datum") == "unresolved"
        check(documented || research || ign)
        check(manifest.opt("publication_allowed") != true || documented || publicIgn)
        val bounds = manifest.getJSONArray("bounds")
        check(bounds.length() == 4 && (0..3).map { (bounds.opt(it) as? Number)?.toDouble()?.canonicalCoordinate() } ==
            listOf(reference.bounds.west, reference.bounds.south, reference.bounds.east, reference.bounds.north))
        val metadata = manifest.getJSONArray("tiles")
        check(metadata.length() == elevation.tiles.size)
        elevation.tiles.forEachIndexed { index, tile ->
            check(!cancelled())
            val row = metadata.getJSONObject(index)
            check(row.keys().asSequence().toSet() == setOf("path", "byte_size", "sha256", "source_url", "acquired_at",
                "decoded_bytes", "pixels_valid", "pixels_void", "pixels_invalid", "minimum_height_m", "maximum_height_m"))
            check(row.opt("path") == tile.path && strictLong(row, "byte_size") == tile.identity.byteSize &&
                row.opt("sha256") == tile.identity.sha256 && strictLong(row, "decoded_bytes") == HGT_DECODED_BYTES)
            check(row.opt("source_url") is String && row.opt("acquired_at") is String)
            val file = File(directory, tile.path)
            check(file.canonicalFile == file.absoluteFile && file.isFile)
            verifyIdentity(file, tile.identity, cancelled)
            val counts = inspectHgt(file, cancelled)
            check(counts.valid > 0 && counts.invalid == 0L && counts.valid + counts.void == HGT_PIXELS)
            check(strictLong(row, "pixels_valid") == counts.valid && strictLong(row, "pixels_void") == counts.void &&
                strictLong(row, "pixels_invalid") == 0L && strictLong(row, "minimum_height_m") == counts.minimum &&
                strictLong(row, "maximum_height_m") == counts.maximum)
        }
    }

    internal fun verifyIdentity(file: File, identity: RegionalFileIdentity, cancelled: () -> Boolean) {
        check(file.isFile && !Files.isSymbolicLink(file.toPath()) && file.length() == identity.byteSize)
        val hash = MessageDigest.getInstance("SHA-256")
        var count = 0L
        file.inputStream().use { stream ->
            val buffer = ByteArray(65_536)
            while (true) {
                check(!cancelled())
                val length = stream.read(buffer)
                if (length < 0) break
                check(length > 0)
                count += length
                check(count <= identity.byteSize)
                hash.update(buffer, 0, length)
            }
        }
        check(count == identity.byteSize && hash.digest().joinToString("") { "%02x".format(it) } == identity.sha256)
    }

    private data class Coverage(val valid: Long, val void: Long, val invalid: Long, val minimum: Long, val maximum: Long)

    private fun inspectHgt(file: File, cancelled: () -> Boolean): Coverage {
        var bytes = 0L
        var valid = 0L
        var void = 0L
        var invalid = 0L
        var minimum = 16_384L
        var maximum = -16_384L
        var high = -1
        GZIPInputStream(file.inputStream().buffered(65_536), 65_536).use { input ->
            val buffer = ByteArray(65_536)
            while (true) {
                check(!cancelled())
                val length = input.read(buffer)
                if (length < 0) break
                check(length > 0)
                bytes += length
                check(bytes <= HGT_DECODED_BYTES)
                for (index in 0 until length) {
                    val next = buffer[index].toInt() and 255
                    if (high < 0) high = next else {
                        val value = ((high shl 8) or next).toShort().toLong()
                        high = -1
                        when {
                            value == -32_768L -> void++
                            value !in -16_384L..16_384L -> invalid++
                            else -> { valid++; minimum = minOf(minimum, value); maximum = maxOf(maximum, value) }
                        }
                    }
                }
            }
        }
        check(bytes == HGT_DECODED_BYTES && high < 0)
        return Coverage(valid, void, invalid, minimum, maximum)
    }

    private fun strictLong(value: JSONObject, key: String): Long? = when (val raw = value.opt(key)) {
        is Int -> raw.toLong()
        is Long -> raw
        else -> null
    }
}
