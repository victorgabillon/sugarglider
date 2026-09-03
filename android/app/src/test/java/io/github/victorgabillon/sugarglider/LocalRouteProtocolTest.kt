package io.github.victorgabillon.sugarglider

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalRouteProtocolTest {
    @Test
    fun validLocalRouteRequestIsStrictAndVersioned() {
        val parsed = BridgeProtocol.parse(localRoutePayload())
        assertTrue(parsed is BridgeRequest.LocalRoute)
        val request = (parsed as BridgeRequest.LocalRoute).routeRequest
        assertEquals(LOCAL_ROUTE_REQUEST_VERSION, request.version)
        assertEquals(LocalRouteProfile.HIKE, request.profile)
        assertEquals(2, request.points.size)
        assertEquals(LocalRouteCoordinate(48.8715, 2.0965), request.points.first())
        assertTrue(request.isValid())
    }

    @Test
    fun coordinateBoundsProfileWhitelistAndStrictV2ShapeAreEnforced() {
        val invalidCoordinate = BridgeProtocol.parse(
            localRoutePayload(
                points = listOf(coordinate(90.0001, 2.0), coordinate(48.0, 2.1)),
            ),
        )
        assertTrue(invalidCoordinate is BridgeRequest.RejectedLocalRoute)
        assertEquals(
            NativeRouteFailureCode.INVALID_REQUEST,
            (invalidCoordinate as BridgeRequest.RejectedLocalRoute).code,
        )
        for (profile in LocalRouteProfile.entries) {
            val parsed = BridgeProtocol.parse(localRoutePayload(profile = profile.wireValue))
            assertEquals(profile, (parsed as BridgeRequest.LocalRoute).routeRequest.profile)
        }
        val invalidProfile = BridgeProtocol.parse(localRoutePayload(profile = "auto"))
        assertTrue(invalidProfile is BridgeRequest.RejectedLocalRoute)
        assertEquals(
            NativeRouteFailureCode.UNSUPPORTED_PROFILE,
            (invalidProfile as BridgeRequest.RejectedLocalRoute).code,
        )
        assertNull(
            BridgeProtocol.parse(
                JSONObject(localRoutePayload()).put("participant_token", TEST_TOKEN).toString(),
            ),
        )
        assertFalse(LocalRouteCoordinate(Double.NaN, 2.0).isValid())
        val legacy = JSONObject(localRoutePayload())
        legacy.remove("route_version")
        legacy.remove("points")
        legacy.put("origin", coordinate(48.8715, 2.0965))
        legacy.put("destination", coordinate(48.8983, 2.0969))
        assertNull(BridgeProtocol.parse(legacy.toString()))
        val wrongVersion = BridgeProtocol.parse(
            JSONObject(localRoutePayload()).put("route_version", 1).toString(),
        )
        assertEquals(
            NativeRouteFailureCode.INVALID_REQUEST,
            (wrongVersion as BridgeRequest.RejectedLocalRoute).code,
        )
    }

    @Test
    fun localRoutePointCountIsStrictlyBounded() {
        for (points in listOf(
            listOf(coordinate(48.0, 2.0)),
            List(MAX_LOCAL_ROUTE_POINTS + 1) { coordinate(48.0, 2.0) },
        )) {
            val parsed = BridgeProtocol.parse(localRoutePayload(points = points))
            assertEquals(
                NativeRouteFailureCode.INVALID_REQUEST,
                (parsed as BridgeRequest.RejectedLocalRoute).code,
            )
        }
        val via = BridgeProtocol.parse(
            localRoutePayload(
                points = listOf(
                    coordinate(48.8715, 2.0965),
                    coordinate(48.8840, 2.0830),
                    coordinate(48.8983, 2.0969),
                ),
            ),
        ) as BridgeRequest.LocalRoute
        assertEquals(3, via.routeRequest.points.size)
    }

    @Test
    fun capabilitiesAndFailureRepliesContainOnlyBoundedPublicFacts() {
        val capabilities = JSONObject(
            BridgeProtocol.localRouteCapabilitiesReply(
                requestId(),
                NativeRouteCapabilities(
                    enabled = true,
                    engine = "valhalla-mobile",
                    engineVersion = "0.5.1/valhalla-3.6.3",
                    packs = listOf(
                        NativeRoutingPackCapability(
                            "marly-dev-v1",
                            LocalRouteAccessMode.entries,
                        ),
                        NativeRoutingPackCapability(
                            "paris-dev-v1",
                            LocalRouteAccessMode.entries,
                        ),
                    ),
                    supportedProfiles = LocalRouteProfile.entries,
                ),
            ),
        )
        assertEquals("local_route_capabilities_result", capabilities.getString("type"))
        assertEquals(2, capabilities.getInt("installed_pack_count"))
        assertEquals("marly-dev-v1", capabilities.getJSONArray("installed_pack_ids").getString(0))
        assertEquals(6, capabilities.getJSONArray("supported_profile_ids").length())
        assertEquals(
            "bicycle",
            capabilities.getJSONArray("pack_capabilities")
                .getJSONObject(0)
                .getJSONArray("access_modes")
                .getString(1),
        )
        assertFalse(capabilities.toString().contains("participant"))
        assertFalse(capabilities.toString().contains("coordinate"))
        val invalidCapabilities = JSONObject(
            BridgeProtocol.localRouteCapabilitiesReply(
                requestId(),
                NativeRouteCapabilities(
                    enabled = true,
                    engine = "valhalla-mobile",
                    engineVersion = "0.5.1/valhalla-3.6.3",
                    packs = listOf(
                        NativeRoutingPackCapability(
                            "paris-dev-v1",
                            listOf(LocalRouteAccessMode.FOOT),
                        ),
                        NativeRoutingPackCapability(
                            "marly-dev-v1",
                            listOf(LocalRouteAccessMode.FOOT),
                        ),
                    ),
                    supportedProfiles = listOf(
                        LocalRouteProfile.TRAIL_RUN,
                        LocalRouteProfile.HIKE,
                    ),
                ),
            ),
        )
        assertEquals(0, invalidCapabilities.getInt("installed_pack_count"))

        for (code in NativeRouteFailureCode.entries) {
            val failure = JSONObject(BridgeProtocol.localRouteFailure(requestId(), code))
            assertEquals("local_route_failure", failure.getString("type"))
            assertEquals(code.wireValue, failure.getString("code"))
            assertEquals(4, failure.length())
        }
    }

    @Test
    fun successReplyPreservesGraphGeometryAndMeasurements() {
        val reply = requireNotNull(BridgeProtocol.localRouteReply(requestId(), success()))
        val value = JSONObject(reply)
        assertEquals("local_route_result", value.getString("type"))
        assertEquals("marly-dev-v1", value.getString("pack_id"))
        assertEquals(3, value.getJSONArray("geometry").length())
        assertEquals(2.0966, value.getJSONArray("snapped_points").getJSONObject(0).getDouble("lon"), 0.0)
        assertEquals(2, value.getJSONArray("snapped_points").length())
        assertEquals(12L, value.getJSONObject("measurements").getLong("route_ms"))
        assertFalse(reply.contains(TEST_TOKEN))
    }

    @Test
    fun malformedOrOversizedResultsCannotBeSerialized() {
        assertNull(
            BridgeProtocol.localRouteReply(
                requestId(),
                success().copy(geometry = listOf(LocalRouteCoordinate(48.0, 2.0))),
            ),
        )
        val verboseGeometry = List(MAX_LOCAL_ROUTE_VERTICES) { index ->
            LocalRouteCoordinate(
                latitude = 48.1234567890123 + index * 0.0000000000001,
                longitude = 2.1234567890123 + index * 0.0000000000001,
            )
        }
        assertNull(
            BridgeProtocol.localRouteReply(
                requestId(),
                success().copy(geometry = verboseGeometry),
            ),
        )
    }

    @Test
    fun localRouteRequestKeepsExistingPageNonceLedgerSemantics() {
        val ledger = BridgeRequestLedger()
        val payload = localRoutePayload()
        val request = requireNotNull(BridgeProtocol.parse(payload))
        assertTrue(ledger.begin(request, payload))
        val reply = BridgeProtocol.localRouteFailure(
            request.requestId,
            NativeRouteFailureCode.NO_ROUTE,
        )
        ledger.complete(request, payload, reply)
        assertEquals(reply, ledger.lookup(request, payload))

        val secondPagePayload = localRoutePayload(SECOND_NONCE)
        val secondPageRequest = requireNotNull(BridgeProtocol.parse(secondPagePayload))
        assertNull(ledger.lookup(secondPageRequest, secondPagePayload))
    }

    @Test
    fun polyline6DecoderRejectsMalformedAndDecodesGraphShape() {
        val decoded = decodePolyline6("_izlhA~rlgdF_{geC~ywl@_kwzCn`{nI")
        assertEquals(3, decoded.size)
        assertEquals(38.5, decoded[0].latitude, 0.000001)
        assertEquals(-120.2, decoded[0].longitude, 0.000001)
        assertTrue(runCatching { decodePolyline6("") }.isFailure)
        assertTrue(runCatching { decodePolyline6("_") }.isFailure)
    }

    @Test
    fun multiLegGeometryDeduplicatesOnlyTheSharedGraphBoundary() {
        val a = LocalRouteCoordinate(48.0, 2.0)
        val b = LocalRouteCoordinate(48.1, 2.1)
        val c = LocalRouteCoordinate(48.2, 2.2)
        val d = LocalRouteCoordinate(48.3, 2.3)
        val joined = joinLocalRouteLegGeometries(
            listOf(listOf(a, b, c), listOf(c, d)),
        )
        assertEquals(listOf(a, b, c, d), joined.geometry)
        assertEquals(listOf(a, c, d), joined.snappedPoints)
        assertTrue(
            runCatching {
                joinLocalRouteLegGeometries(listOf(listOf(a, b), listOf(c, d)))
            }.isFailure,
        )
    }

    private fun success(): NativeRouteResult.Success = NativeRouteResult.Success(
        profile = LocalRouteProfile.HIKE,
        engine = "valhalla-mobile",
        engineVersion = "0.5.1/valhalla-3.6.3",
        packId = "marly-dev-v1",
        distanceMeters = 3_450.5,
        durationSeconds = 2_600.0,
        geometry = listOf(
            LocalRouteCoordinate(48.8716, 2.0966),
            LocalRouteCoordinate(48.884, 2.083),
            LocalRouteCoordinate(48.8982, 2.0968),
        ),
        snappedPoints = listOf(
            LocalRouteCoordinate(48.8716, 2.0966),
            LocalRouteCoordinate(48.8982, 2.0968),
        ),
        measurements = NativeRouteMeasurements(
            coldStart = true,
            engineInitializationMs = 81,
            routeMs = 12,
            memoryBeforeInitializationBytes = 1_000,
            memoryAfterInitializationBytes = 2_000,
            memoryAfterRouteBytes = 2_100,
        ),
    )

    private fun localRoutePayload(
        nonce: String = FIRST_NONCE,
        profile: String = "hike",
        points: List<JSONObject> = listOf(
            coordinate(48.8715, 2.0965),
            coordinate(48.8983, 2.0969),
        ),
    ): String = JSONObject()
        .put("schema_version", 1)
        .put("request_id", "web-$nonce-1")
        .put("type", "local_route")
        .put("route_version", LOCAL_ROUTE_REQUEST_VERSION)
        .put("profile", profile)
        .put("points", JSONArray(points))
        .toString()

    private fun coordinate(latitude: Double, longitude: Double): JSONObject = JSONObject()
        .put("lat", latitude)
        .put("lon", longitude)

    private fun requestId(): String = "web-$FIRST_NONCE-1"

    private companion object {
        const val FIRST_NONCE = "0123456789abcdef0123456789abcdef"
        const val SECOND_NONCE = "fedcba9876543210fedcba9876543210"
    }
}
