package io.github.victorgabillon.sugarglider

internal const val LOCAL_ROUTE_REQUEST_VERSION = 2
internal const val MIN_LOCAL_ROUTE_POINTS = 2
internal const val MAX_LOCAL_ROUTE_POINTS = 16
internal const val MAX_LOCAL_ROUTE_VERTICES = 20_000
internal const val MAX_LOCAL_ROUTE_REPLY_BYTES = 512 * 1_024

internal data class LocalRouteCoordinate(
    val latitude: Double,
    val longitude: Double,
) {
    fun isValid(): Boolean = latitude.isFinite() &&
        longitude.isFinite() &&
        latitude in -90.0..90.0 &&
        longitude in -180.0..180.0
}

internal enum class LocalRouteAccessMode(val wireValue: String) {
    FOOT("foot"),
    BICYCLE("bicycle");

    companion object {
        fun parse(value: String): LocalRouteAccessMode? = entries.singleOrNull {
            it.wireValue == value
        }
    }
}

internal enum class LocalRouteProfile(
    val wireValue: String,
    val accessMode: LocalRouteAccessMode,
) {
    TRAIL_RUN("trail_run", LocalRouteAccessMode.FOOT),
    HIKE("hike", LocalRouteAccessMode.FOOT),
    CITY_BIKE("city_bike", LocalRouteAccessMode.BICYCLE),
    GRAVEL_BIKE("gravel_bike", LocalRouteAccessMode.BICYCLE),
    MOUNTAIN_BIKE("mountain_bike", LocalRouteAccessMode.BICYCLE),
    ROAD_BIKE("road_bike", LocalRouteAccessMode.BICYCLE);

    companion object {
        fun parse(value: String): LocalRouteProfile? = entries.singleOrNull {
            it.wireValue == value
        }
    }
}

internal data class NativeRouteRequest(
    val version: Int,
    val requestId: String,
    val points: List<LocalRouteCoordinate>,
    val profile: LocalRouteProfile,
) {
    fun isValid(): Boolean = version == LOCAL_ROUTE_REQUEST_VERSION &&
        requestId.isNotBlank() &&
        points.size in MIN_LOCAL_ROUTE_POINTS..MAX_LOCAL_ROUTE_POINTS &&
        points.all(LocalRouteCoordinate::isValid)
}

internal data class NativeRoutingPackCapability(
    val packId: String,
    val accessModes: List<LocalRouteAccessMode>,
) {
    fun isValid(): Boolean = isRoutingPackId(packId) &&
        accessModes.isNotEmpty() &&
        accessModes == LocalRouteAccessMode.entries.filter(accessModes::contains)
}

internal data class NativeRouteCapabilities(
    val enabled: Boolean,
    val engine: String,
    val engineVersion: String,
    val packs: List<NativeRoutingPackCapability>,
    val supportedProfiles: List<LocalRouteProfile>,
) {
    val installedPackIds: List<String>
        get() = packs.map(NativeRoutingPackCapability::packId)

    fun isValid(): Boolean = packs.size <= 64 &&
        installedPackIds == installedPackIds.distinct().sorted() &&
        packs.all(NativeRoutingPackCapability::isValid) &&
        supportedProfiles == LocalRouteProfile.entries.filter { profile ->
            packs.any { profile.accessMode in it.accessModes }
        }
}

internal enum class NativeRouteFailureCode(val wireValue: String) {
    INVALID_REQUEST("invalid_request"),
    UNSUPPORTED_PROFILE("unsupported_profile"),
    ROUTING_PACK_UNAVAILABLE("routing_pack_unavailable"),
    NO_COVERING_ROUTING_PACK("no_covering_routing_pack"),
    NO_COMPATIBLE_ROUTING_PACK("no_compatible_routing_pack"),
    NO_ROUTE("no_route"),
    ROUTE_TOO_LARGE("route_too_large"),
    ROUTING_BUSY("routing_busy"),
    ROUTING_FAILURE("routing_failure");
}

internal data class NativeRouteMeasurements(
    val coldStart: Boolean,
    val engineInitializationMs: Long,
    val routeMs: Long,
    val memoryBeforeInitializationBytes: Long,
    val memoryAfterInitializationBytes: Long,
    val memoryAfterRouteBytes: Long,
)

internal sealed interface NativeRouteResult {
    data class Success(
        val profile: LocalRouteProfile,
        val engine: String,
        val engineVersion: String,
        val packId: String,
        val distanceMeters: Double,
        val durationSeconds: Double?,
        val geometry: List<LocalRouteCoordinate>,
        val snappedPoints: List<LocalRouteCoordinate>,
        val measurements: NativeRouteMeasurements,
    ) : NativeRouteResult {
        fun isValid(): Boolean = isRoutingPackId(packId) &&
            distanceMeters.isFinite() &&
            distanceMeters > 0.0 &&
            (durationSeconds == null || (durationSeconds.isFinite() && durationSeconds >= 0.0)) &&
            geometry.size in 2..MAX_LOCAL_ROUTE_VERTICES &&
            geometry.all(LocalRouteCoordinate::isValid) &&
            snappedPoints.size in MIN_LOCAL_ROUTE_POINTS..MAX_LOCAL_ROUTE_POINTS &&
            snappedPoints.all(LocalRouteCoordinate::isValid) &&
            geometry.first() == snappedPoints.first() &&
            geometry.last() == snappedPoints.last()
    }

    data class Failure(val code: NativeRouteFailureCode) : NativeRouteResult
}

internal interface NativeRouteEngine {
    fun capabilities(): NativeRouteCapabilities

    fun route(request: NativeRouteRequest): NativeRouteResult
}
