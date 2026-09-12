package io.github.victorgabillon.sugarglider

import org.json.JSONObject

// Deletion authority names one immutable private version, without pretending
// that damaged manifest bytes still provide a valid routing reference.
internal data class RegionalRoutingVersion(val regionId: String, val buildId: String) {
    fun isValid(): Boolean = isRoutingPackId(regionId) && !regionId.contains("..") &&
        buildId.matches(Regex("[a-f0-9]{64}"))

    companion object {
        fun parse(value: JSONObject?): RegionalRoutingVersion? {
            if (value == null || value.keys().asSequence().toSet() != setOf("region_id", "build_id")) return null
            return RegionalRoutingVersion(value.opt("region_id") as? String ?: return null,
                value.opt("build_id") as? String ?: return null).takeIf(RegionalRoutingVersion::isValid)
        }
    }
}
