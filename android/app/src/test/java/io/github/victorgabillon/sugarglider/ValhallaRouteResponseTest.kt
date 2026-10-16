package io.github.victorgabillon.sugarglider

import com.squareup.moshi.JsonDataException
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.valhalla.api.models.RouteRequest
import com.valhalla.api.models.RouteResponse
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class ValhallaRouteResponseTest {
    private val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
    private val responseAdapter = moshi.adapter(RouteResponse::class.java)

    @Test
    fun directionsNoneResponseFailsAtTheRequiredLegManeuvers() {
        // Matches the physical PR86 failure: native routing returns a trip,
        // but directions_type=none omits the field required by models 0.6.0.
        val response = responseFixture()
        response.getJSONObject("trip").getJSONArray("legs").getJSONObject(0).remove("maneuvers")

        val error = assertThrows(JsonDataException::class.java) {
            responseAdapter.fromJson(response.toString())
        }
        assertTrue(error.message.orEmpty().contains("Required value 'maneuvers' missing"))
        assertTrue(error.message.orEmpty().contains("$.trip.legs"))
    }

    @Test
    fun maneuversWithoutInstructionsAlsoFailTheTypedResponseContract() {
        val response = responseFixture()
        response.getJSONObject("trip").getJSONArray("legs").getJSONObject(0)
            .getJSONArray("maneuvers").getJSONObject(0).remove("instruction")

        val error = assertThrows(JsonDataException::class.java) {
            responseAdapter.fromJson(response.toString())
        }
        assertTrue(error.message.orEmpty().contains("Required value 'instruction' missing"))
    }

    @Test
    fun instructionsResponsePreservesNativeShapeAndSummary() {
        val response = requireNotNull(responseAdapter.fromJson(responseFixture().toString()))

        assertEquals(0, response.trip.status)
        assertEquals(1, response.trip.legs.size)
        assertEquals(SHAPE, response.trip.legs.single().shape)
        assertEquals(4.0, response.trip.summary.length, 0.0)
        assertEquals(1_200.0, response.trip.summary.time, 0.0)
        assertEquals("Walk.", response.trip.legs.single().maneuvers.single().instruction)
    }

    @Test
    fun everyProfileRequestsInstructionsAndPreservesOrderedBreakPoints() {
        val points = listOf(
            LocalRouteCoordinate(48.8715, 2.0965),
            LocalRouteCoordinate(48.8983, 2.0969),
            LocalRouteCoordinate(48.8715, 2.0965),
        )
        val adapter = moshi.adapter(RouteRequest::class.java)
        LocalRouteProfile.entries.forEach { profile ->
            val policy = ValhallaProfilePolicies.forProfile(profile)
            val request = localValhallaRouteRequest(points, policy, "response-contract")
            val json = JSONObject(adapter.toJson(request))

            assertEquals("instructions", json.getString("directions_type"))
            assertEquals(policy.costingModel, request.costing)
            assertEquals(policy.costingOptions, request.costingOptions)
            assertEquals("json", json.getString("format"))
            assertEquals("polyline6", json.getString("shape_format"))
            val locations = json.getJSONArray("locations")
            assertEquals(points.size, locations.length())
            points.forEachIndexed { index, point ->
                val location = locations.getJSONObject(index)
                assertEquals(point.latitude, location.getDouble("lat"), 0.0)
                assertEquals(point.longitude, location.getDouble("lon"), 0.0)
                assertEquals("break", location.getString("type"))
            }
        }
    }

    // A small wire-schema fixture, independent of JNI, graph data or services.
    // Physical graph compatibility is validated separately on the device.
    private fun responseFixture(): JSONObject = JSONObject(
        """
        {"trip": {
          "status": 0, "status_message": "Found route between points",
          "units": "kilometers", "language": "en-US", "locations": [],
          "summary": $SUMMARY,
          "legs": [{"shape": "$SHAPE", "summary": $SUMMARY, "maneuvers": [{
            "type": 1, "instruction": "Walk.", "time": 1200, "length": 4,
            "begin_shape_index": 0, "end_shape_index": 2,
            "travel_mode": "pedestrian", "travel_type": "foot"
          }]}]
        }}
        """.trimIndent(),
    )

    private companion object {
        const val SHAPE = "_izlhA~rlgdF_{geC~ywl@_kwzCn`{nI"
        const val SUMMARY = """{"time":1200,"length":4,"min_lat":38.5,"max_lat":43.252,"min_lon":-126.453,"max_lon":-120.2}"""
    }
}
