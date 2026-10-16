package io.github.victorgabillon.sugarglider

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.valhalla.api.models.HeightRequest
import com.valhalla.api.models.HeightResponse
import com.valhalla.api.models.RouteRequest
import com.valhalla.valhalla.Valhalla
import java.io.File
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class ValhallaLocalConfigurationTest {
    @Test
    fun serializedConfigurationUsesOnlyTheSelectedArchiveAndElevation() {
        val archive = File("/selected-region/valhalla_tiles.tar")
        val config = localValhallaConfiguration(archive, File("/selected-region/elevation/skadi"))
        val value = offlineValhallaJson(config)
        val mjolnir = value.getJSONObject("mjolnir")

        assertEquals(archive.absolutePath, mjolnir.getString("tile_extract"))
        assertEquals("", mjolnir.getString("tile_dir"))
        // Models 0.6.0 serialize an empty default tile_url; only a non-empty
        // URL enables the wrapper's network tile getter.
        assertEquals("", mjolnir.optString("tile_url", ""))
        assertFalse(mjolnir.optBoolean("tile_url_gz", false))
        assertEquals("", mjolnir.optString("traffic_extract", ""))
        for (key in listOf("admin", "landmarks", "timezone", "transit_dir", "transit_feeds_dir")) {
            assertEquals("", mjolnir.getString(key))
        }
        assertEquals("/selected-region/elevation/skadi", value.getJSONObject("additional_data").getString("elevation"))
        for (key in listOf("elevation_url", "elevation_url_user_pw", "elevation_dir")) {
            assertEquals("", value.getJSONObject("additional_data").getString(key))
        }
        assertFalse(value.has("httpd"))
        assertFalse(value.has("statsd"))
        assertEquals(config, localValhallaConfiguration(archive, File("/selected-region/elevation/skadi")))
    }
    @Test
    fun routeRequestSerializesDirectionFieldsAtRootWithModel060() {
        val model = localValhallaRouteRequest(
            listOf(
                LocalRouteCoordinate(48.88, 2.08),
                LocalRouteCoordinate(48.90, 2.11),
            ),
            ValhallaProfilePolicies.forProfile(LocalRouteProfile.HIKE),
            "pr86-route-test",
        )
        val adapter = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
            .adapter(RouteRequest::class.java)
        val value = JSONObject(adapter.toJson(model))
        assertEquals("pedestrian", value.getString("costing"))
        assertEquals("instructions", value.getString("directions_type"))
        assertEquals("json", value.getString("format"))
        assertEquals("polyline6", value.getString("shape_format"))
        assertEquals("pr86-route-test", value.getString("id"))
        assertFalse(value.has("directions_options"))
        assertEquals(2, value.getJSONArray("locations").length())
    }

    @Test
    fun newMobileWrapperExposesTypedOfflineHeightOperation() {
        // API proof only: no Skadi data is installed and no JNI call is made.
        val method = Valhalla::class.java.getMethod("height", HeightRequest::class.java)
        assertEquals(HeightResponse::class.java, method.returnType)
    }

}
