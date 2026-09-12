package io.github.victorgabillon.sugarglider

import org.json.JSONArray
import org.json.JSONObject

internal const val MAX_REGIONAL_ROUTING_PACK_BYTES = 2_147_483_648L
internal const val MAX_REGIONAL_ROUTING_MANIFEST_BYTES = 16_384L
private val REGIONAL_SHA256 = Regex("^[0-9a-f]{64}$")

internal data class RegionalFileIdentity(val byteSize: Long, val sha256: String) {
    fun isValid(maximum: Long): Boolean = byteSize in 1..maximum &&
        REGIONAL_SHA256.matches(sha256)

    fun toJson(): JSONObject = JSONObject().put("byte_size", byteSize).put("sha256", sha256)

    companion object {
        fun parse(value: JSONObject?): RegionalFileIdentity? {
            if (value == null || value.keys().asSequence().toSet() != setOf("byte_size", "sha256")) return null
            val size = when (val raw = value.opt("byte_size")) {
                is Int -> raw.toLong()
                is Long -> raw
                else -> return null
            }
            return RegionalFileIdentity(size, value.opt("sha256") as? String ?: return null)
        }
    }
}

// Public immutable data identity, never a path or a participant capability.
// The coordinator captures these references before starting a planning request.
internal data class RegionalRoutingPackReference(
    val regionId: String,
    val buildId: String,
    val packId: String,
    val bounds: RoutingPackBounds,
    val manifest: RegionalFileIdentity,
    val archive: RegionalFileIdentity,
) {
    fun isValid(): Boolean = isRoutingPackId(regionId) && !regionId.contains("..") && REGIONAL_SHA256.matches(buildId) &&
        isRoutingPackId(packId) && !packId.contains("..") && bounds.isValid() &&
        bounds.south >= -85.0511287798066 && bounds.north <= 85.0511287798066 &&
        manifest.isValid(MAX_REGIONAL_ROUTING_MANIFEST_BYTES) &&
        archive.isValid(MAX_REGIONAL_ROUTING_PACK_BYTES) && archive.byteSize % 512L == 0L

    fun toJson(): JSONObject = JSONObject()
        .put("region_id", regionId)
        .put("build_id", buildId)
        .put("pack_id", packId)
        .put("bounds", JSONArray(listOf(bounds.west, bounds.south, bounds.east, bounds.north)))
        .put("manifest", manifest.toJson())
        .put("archive", archive.toJson())

    companion object {
        fun parse(value: JSONObject?): RegionalRoutingPackReference? {
            if (value == null || value.keys().asSequence().toSet() != FIELDS) return null
            val coordinates = value.optJSONArray("bounds") ?: return null
            if (coordinates.length() != 4) return null
            val bounds = (0..3).map { index ->
                (coordinates.opt(index) as? Number)?.toDouble()?.takeIf(Double::isFinite)
                    ?: return null
            }
            return RegionalRoutingPackReference(
                regionId = value.opt("region_id") as? String ?: return null,
                buildId = value.opt("build_id") as? String ?: return null,
                packId = value.opt("pack_id") as? String ?: return null,
                bounds = RoutingPackBounds(bounds[0], bounds[1], bounds[2], bounds[3]),
                manifest = RegionalFileIdentity.parse(value.optJSONObject("manifest")) ?: return null,
                archive = RegionalFileIdentity.parse(value.optJSONObject("archive")) ?: return null,
            ).takeIf(RegionalRoutingPackReference::isValid)
        }

        private val FIELDS = setOf("region_id", "build_id", "pack_id", "bounds", "manifest", "archive")
    }
}
