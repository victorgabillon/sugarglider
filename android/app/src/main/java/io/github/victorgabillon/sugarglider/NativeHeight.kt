package io.github.victorgabillon.sugarglider

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.valhalla.api.models.Coordinate
import com.valhalla.api.models.HeightRequest
import com.valhalla.api.models.HeightResponse
import com.valhalla.config.models.ValhallaConfig
import kotlin.math.abs
import org.json.JSONObject

internal const val MAX_NATIVE_HEIGHT_SAMPLES = 2_048

// Promoted unchanged request/null handling from the physically validated PR88 experiment.
internal fun localValhallaHeightRequest(points: List<LocalRouteCoordinate>, id: String): HeightRequest {
    require(points.size in 1..MAX_NATIVE_HEIGHT_SAMPLES)
    require(points.all(LocalRouteCoordinate::isValid))
    require(id.matches(Regex("[a-z0-9_-]{1,64}")))
    return HeightRequest(
        id = id,
        shape = points.map { Coordinate(lat = it.latitude, lon = it.longitude) },
        shapeFormat = HeightRequest.ShapeFormat.polyline6,
        range = false,
        // Core 3.9.1 accepts only 0..2; larger values silently keep default 0.
        heightPrecision = 2,
    )
}

internal fun localValhallaHeightValues(request: HeightRequest, response: HeightResponse): List<Double?> {
    require(response.id == request.id)
    require(response.rangeHeight == null && response.encodedPolyline == null)
    val shape = requireNotNull(response.shape)
    val requested = requireNotNull(request.shape)
    require(shape.size == requested.size)
    shape.zip(requested).forEach { (actual, expected) ->
        require(abs(actual.lat - expected.lat) <= 0.000001)
        require(abs(actual.lon - expected.lon) <= 0.000001)
    }
    // Generated 0.6.0 models declare List<Double>, although native missing
    // heights are JSON null. Widen element nullability before any unboxing.
    val heights: List<Double?> = requireNotNull(response.height)
    require(heights.size == requested.size)
    require(heights.all { it == null || (it.isFinite() && it in -16_384.0..16_384.0) })
    return heights.toList()
}


internal fun offlineValhallaJson(config: ValhallaConfig): JSONObject {
    val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
    val value = JSONObject(moshi.adapter(ValhallaConfig::class.java).toJson(config))
    value.getJSONObject("additional_data").apply {
        put("elevation_url", "")
        put("elevation_url_user_pw", "")
        put("elevation_dir", "")
    }
    value.getJSONObject("service_limits").getJSONObject("skadi").put("max_shape", MAX_NATIVE_HEIGHT_SAMPLES)
    return value
}

internal interface NativeOfflineEngine : NativeRouteEngine {
    fun height(reference: RegionalRoutingPackReference, points: List<LocalRouteCoordinate>, id: String): NativeHeightResult
}

internal sealed interface NativeHeightResult {
    data class Success(val reference: RegionalRoutingPackReference, val heights: List<Double?>,
        val elapsedMs: Long, val pssBytes: Long, val coldStart: Boolean,
        val heightReference: String = ELEVATION_HEIGHT_REFERENCE) : NativeHeightResult
    data class Failure(val code: String) : NativeHeightResult
}
