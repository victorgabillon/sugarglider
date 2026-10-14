package io.github.victorgabillon.sugarglider

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.valhalla.api.models.HeightRequest
import com.valhalla.api.models.HeightResponse
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Test

class NativeHeightResearchTest {
    private val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
    private val point = LocalRouteCoordinate(48.8715, 2.0965)

    @Test
    fun serializedConfigurationDisablesBothNativeDownloadersAndBoundsShape() {
        val directory = File("/research-only-dem")
        val config = researchHeightConfiguration(directory)
        val additional = config.getJSONObject("additional_data")
        assertEquals(directory.absolutePath, additional.getString("elevation"))
        for (key in listOf("elevation_url", "elevation_url_user_pw", "elevation_dir")) {
            assertEquals("", additional.getString(key))
        }
        val mjolnir = config.getJSONObject("mjolnir")
        assertEquals("", mjolnir.getString("tile_extract"))
        assertEquals("", mjolnir.getString("tile_dir"))
        assertEquals("", mjolnir.optString("tile_url", ""))
        assertFalse(mjolnir.optBoolean("tile_url_gz", false))
        assertFalse(config.has("httpd"))
        assertEquals(MAX_RESEARCH_HEIGHT_SAMPLES, config.getJSONObject("service_limits")
            .getJSONObject("skadi").getInt("max_shape"))
    }

    @Test
    fun typedNativeNullRemainsUnavailableWhileActualZeroIsPreserved() {
        val request = researchHeightRequest(listOf(point, point), "null-and-zero")
        val response = requireNotNull(moshi.adapter(HeightResponse::class.java).fromJson(
            """{"id":"null-and-zero","shape":[{"lat":48.8715,"lon":2.0965},{"lat":48.8715,"lon":2.0965}],"height":[null,0]}""",
        ))
        assertEquals(listOf(null, 0.0), researchHeightValues(request, response))
    }

    @Test
    fun typedRequestUsesTheNativeMaximumTwoDecimalHeightPrecision() {
        val request = researchHeightRequest(listOf(point), "height-test")
        val json = org.json.JSONObject(moshi.adapter(HeightRequest::class.java).toJson(request))
        assertEquals("height-test", json.getString("id"))
        assertEquals(1, json.getJSONArray("shape").length())
        assertEquals(2, json.getInt("height_precision"))
        assertFalse(json.getBoolean("range"))
        assertFalse(json.has("encoded_polyline"))
    }

    @Test
    fun malformedOrOversizedLocalRequestsAreRejectedBeforeNativeWork() {
        for (points in listOf(emptyList(), List(MAX_RESEARCH_HEIGHT_SAMPLES + 1) { point },
            listOf(LocalRouteCoordinate(Double.NaN, 2.0)), listOf(LocalRouteCoordinate(91.0, 2.0)))) {
            assertThrows(IllegalArgumentException::class.java) { researchHeightRequest(points, "invalid") }
        }
    }

    @Test
    fun responseIdentityCountShapeAndNonfiniteValuesAreNeverAccepted() {
        val request = researchHeightRequest(listOf(point), "owned")
        val valid = HeightResponse(id = "owned", shape = requireNotNull(request.shape), height = listOf(100.0))
        val responses = listOf(
            valid.copy(id = "other"), valid.copy(height = emptyList()),
            valid.copy(shape = emptyList()), valid.copy(height = listOf(Double.NaN)),
            valid.copy(height = listOf(-32_768.0)), valid.copy(rangeHeight = listOf(listOf(0.0, 100.0))),
        )
        responses.forEach { response ->
            assertThrows(IllegalArgumentException::class.java) { researchHeightValues(request, response) }
        }
    }
}
