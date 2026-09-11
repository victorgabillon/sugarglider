package io.github.victorgabillon.sugarglider

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.valhalla.config.models.ValhallaConfig
import java.io.File
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class ValhallaLocalConfigurationTest {
    @Test
    fun serializedConfigurationUsesOnlyTheSelectedArchiveWithoutAuxiliaryData() {
        val archive = File("/selected-region/valhalla_tiles.tar")
        val config = localValhallaConfiguration(archive)
        val adapter = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
            .adapter(ValhallaConfig::class.java)
        val value = JSONObject(adapter.toJson(config))
        val mjolnir = value.getJSONObject("mjolnir")

        assertEquals(archive.absolutePath, mjolnir.getString("tile_extract"))
        assertEquals("", mjolnir.getString("tile_dir"))
        assertFalse(mjolnir.has("tile_url"))
        assertFalse(mjolnir.has("traffic_extract"))
        for (key in listOf("admin", "landmarks", "timezone", "transit_dir", "transit_feeds_dir")) {
            assertEquals("", mjolnir.getString(key))
        }
        assertEquals("", value.getJSONObject("additional_data").getString("elevation"))
        assertFalse(value.has("httpd"))
        assertFalse(value.has("statsd"))
        assertEquals(config, localValhallaConfiguration(archive))
    }
}
