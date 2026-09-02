package io.github.victorgabillon.sugarglider

internal const val LOCAL_ROUTE_REQUEST_VERSION = 1
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

internal enum class LocalRouteProfile(val wireValue: String) {
    HIKE("hike");

    companion object {
        fun parse(value: String): LocalRouteProfile? = entries.singleOrNull {
            it.wireValue == value
        }
    }
}

internal data class NativeRouteRequest(
    val version: Int,
    val requestId: String,
    val origin: LocalRouteCoordinate,
    val destination: LocalRouteCoordinate,
    val profile: LocalRouteProfile,
) {
    fun isValid(): Boolean = version == LOCAL_ROUTE_REQUEST_VERSION &&
        requestId.isNotBlank() &&
        origin.isValid() &&
        destination.isValid()
}

internal data class NativeRouteCapabilities(
    val enabled: Boolean,
    val engine: String,
    val engineVersion: String,
    val installedPackIds: List<String>,
) {
    fun isValid(): Boolean = installedPackIds.size <= 64 &&
        installedPackIds == installedPackIds.distinct().sorted() &&
        installedPackIds.all(::isRoutingPackId)
}

internal enum class NativeRouteFailureCode(val wireValue: String) {
    INVALID_REQUEST("invalid_request"),
    UNSUPPORTED_PROFILE("unsupported_profile"),
    ROUTING_PACK_UNAVAILABLE("routing_pack_unavailable"),
    NO_COVERING_ROUTING_PACK("no_covering_routing_pack"),
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
        val measurements: NativeRouteMeasurements,
    ) : NativeRouteResult {
        fun isValid(): Boolean = isRoutingPackId(packId) &&
            distanceMeters.isFinite() &&
            distanceMeters > 0.0 &&
            (durationSeconds == null || (durationSeconds.isFinite() && durationSeconds >= 0.0)) &&
            geometry.size in 2..MAX_LOCAL_ROUTE_VERTICES &&
            geometry.all(LocalRouteCoordinate::isValid)
    }

    data class Failure(val code: NativeRouteFailureCode) : NativeRouteResult
}

internal interface NativeRouteEngine {
    fun capabilities(): NativeRouteCapabilities

    fun route(request: NativeRouteRequest): NativeRouteResult
}
