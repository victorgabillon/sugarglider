package io.github.victorgabillon.sugarglider

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import java.util.zip.GZIPOutputStream
import org.json.JSONArray
import org.json.JSONObject

internal fun fixtureIdentity(bytes: ByteArray) = RegionalFileIdentity(bytes.size.toLong(),
    MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) })

internal object SyntheticHgt {
    val bytes: ByteArray by lazy {
        val output = ByteArrayOutputStream()
        GZIPOutputStream(output).use { gzip ->
            val buffer = ByteArray(65_536)
            var remaining = HGT_DECODED_BYTES
            while (remaining > 0) {
                val count = minOf(remaining, buffer.size.toLong()).toInt()
                gzip.write(buffer, 0, count)
                remaining -= count
            }
        }
        output.toByteArray()
    }
}

internal class V2ElevationFixture(bounds: RoutingPackBounds, componentId: String = "synthetic-elevation") {
    val tiles = elevationTilePaths(bounds).map { RegionalElevationTile(it, fixtureIdentity(SyntheticHgt.bytes)) }
    val manifest = JSONObject().put("schema_version", 1).put("component_id", componentId)
        .put("bounds", JSONArray(listOf(bounds.west, bounds.south, bounds.east, bounds.north)))
        .put("format", "skadi-hgt-gzip-v1").put("publication_allowed", false)
        .put("provenance_status", "unresolved").put("vertical_datum", "unresolved")
        .put("tiles", JSONArray(tiles.map { tile -> tile.toJson()
            .put("source_url", "https://example.test/synthetic/" + tile.path)
            .put("acquired_at", "2026-10-15T00:00:00Z").put("decoded_bytes", HGT_DECODED_BYTES)
            .put("pixels_valid", HGT_PIXELS).put("pixels_void", 0).put("pixels_invalid", 0)
            .put("minimum_height_m", 0).put("maximum_height_m", 0) }))
        .toString().toByteArray()
    val reference = RegionalElevationReference(componentId, fixtureIdentity(manifest), tiles)
}

internal fun RegionalRoutingPackStore.stageFixture(
    reference: RegionalRoutingPackReference, manifest: ByteArray, archiveSource: () -> InputStream,
    cancelled: () -> Boolean = { false }, onProgress: (Long) -> Unit = {},
): RoutingPack = stage(reference, manifest, archiveSource,
    V2ElevationFixture(reference.bounds, reference.elevation.componentId).manifest,
    { ByteArrayInputStream(SyntheticHgt.bytes) }, cancelled, onProgress)

internal fun syntheticValhallaArchive(size: Int = 256 * 1_024 + 512): ByteArray {
    val result = ByteArray(size)
    fun header(offset: Int, name: String, bytes: Int) {
        name.toByteArray().copyInto(result, offset)
        fun field(position: Int, length: Int, value: Int) {
            (value.toString(8).padStart(length - 1, '0') + '\u0000').toByteArray().copyInto(result, offset + position)
        }
        field(100, 8, 420); field(108, 8, 0); field(116, 8, 0); field(124, 12, bytes); field(136, 12, 0)
        result[offset + 156] = '0'.code.toByte()
        "ustar\u000000".toByteArray().copyInto(result, offset + 257)
        (148..155).forEach { result[offset + it] = 32 }
        val checksum = (offset until offset + 512).sumOf { result[it].toInt() and 255 }
        (checksum.toString(8).padStart(6, '0') + "\u0000 ").toByteArray().copyInto(result, offset + 148)
    }
    header(0, "index.bin", 16)
    ByteBuffer.wrap(result, 512, 16).order(ByteOrder.LITTLE_ENDIAN).putLong(1536).putInt(2).putInt(32)
    header(1024, "2/000/000.gph", 32)
    ByteBuffer.wrap(result, 1536, 8).order(ByteOrder.LITTLE_ENDIAN).putLong((1L shl 62) or 2)
    "3.9.1".toByteArray().copyInto(result, 1552)
    return result
}
