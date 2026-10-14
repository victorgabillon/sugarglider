package io.github.victorgabillon.sugarglider

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.valhalla.api.models.Coordinate
import com.valhalla.api.models.HeightRequest
import com.valhalla.api.models.HeightResponse
import com.valhalla.config.ValhallaConfigBuilder
import com.valhalla.config.models.AdditionalData
import com.valhalla.config.models.ValhallaConfig
import com.valhalla.valhalla.Valhalla
import java.io.Closeable
import java.io.File
import kotlin.math.abs
import org.json.JSONObject

internal const val MAX_RESEARCH_HEIGHT_SAMPLES = 2_048
internal const val MAX_RESEARCH_HEIGHT_CALL_MS = 5_000L

/** Explicit instrumentation only. No UI, bridge, startup or routing caller. */
internal class NativeHeightResearch(
    elevationDirectory: File,
    private val configurationFile: File,
) : Closeable {
    private val valhalla: Valhalla

    init {
        check(BuildConfig.DEBUG)
        require(elevationDirectory.isDirectory)
        require(!configurationFile.exists())
        configurationFile.writeText(researchHeightConfiguration(elevationDirectory).toString())
        try {
            // The path constructor avoids overwriting the app's valhalla.json.
            valhalla = Valhalla(configurationFile.absolutePath)
        } catch (error: Exception) {
            configurationFile.delete()
            throw error
        }
    }

    fun sample(points: List<LocalRouteCoordinate>, id: String): List<Double?> {
        val request = researchHeightRequest(points, id)
        return researchHeightValues(request, valhalla.height(request))
    }

    // Deliberately invalid native wire requests belong only to the test suite.
    internal fun malformedRequest(): String = valhalla.heightRaw("{not-json")

    override fun close() {
        try { valhalla.close() }
        finally { configurationFile.delete() }
    }
}

internal fun researchHeightRequest(points: List<LocalRouteCoordinate>, id: String): HeightRequest {
    require(points.size in 1..MAX_RESEARCH_HEIGHT_SAMPLES)
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

internal fun researchHeightValues(request: HeightRequest, response: HeightResponse): List<Double?> {
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

internal fun researchHeightConfiguration(elevationDirectory: File): JSONObject {
    val built = ValhallaConfigBuilder().withTileExtract("").withTileDir("").build()
    val config = built.copy(
        additionalData = AdditionalData(elevation = elevationDirectory.absolutePath),
        httpd = null,
        statsd = null,
        mjolnir = requireNotNull(built.mjolnir).copy(
            tileUrl = "", tileUrlGz = false, admin = "", landmarks = "", timezone = "",
            trafficExtract = null, transitDir = "", transitFeedsDir = "",
        ),
    )
    val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
    val value = JSONObject(moshi.adapter(ValhallaConfig::class.java).toJson(config))
    // Native 3.9.1 has a remote DEM loader absent from config models 0.6.0.
    // Explicitly disable its URLs/credentials and scratch download directory.
    value.getJSONObject("additional_data").apply {
        put("elevation_url", "")
        put("elevation_url_user_pw", "")
        put("elevation_dir", "")
    }
    value.getJSONObject("service_limits").getJSONObject("skadi")
        .put("max_shape", MAX_RESEARCH_HEIGHT_SAMPLES)
    return value
}
