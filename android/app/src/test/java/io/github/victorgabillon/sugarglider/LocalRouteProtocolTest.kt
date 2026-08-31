package io.github.victorgabillon.sugarglider

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
        assertEquals(LocalRouteCoordinate(48.8715, 2.0965), request.origin)
        assertTrue(request.isValid())
    }

    @Test
    fun coordinateBoundsAndProfileWhitelistAreEnforced() {
        val invalidCoordinate = BridgeProtocol.parse(
                JSONObject(localRoutePayload())
                    .put("origin", coordinate(90.0001, 2.0))
                    .toString(),
            )
        assertTrue(invalidCoordinate is BridgeRequest.RejectedLocalRoute)
        assertEquals(
            NativeRouteFailureCode.INVALID_REQUEST,
            (invalidCoordinate as BridgeRequest.RejectedLocalRoute).code,
        )
        val invalidProfile = BridgeProtocol.parse(
                JSONObject(localRoutePayload()).put("profile", "auto").toString(),
            )
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
                    packInstalled = false,
                    packId = "marly-dev-v1",
                ),
            ),
        )
        assertEquals("local_route_capabilities_result", capabilities.getString("type"))
        assertFalse(capabilities.toString().contains("participant"))
        assertFalse(capabilities.toString().contains("coordinate"))

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
        assertEquals(3, value.getJSONArray("geometry").length())
        assertEquals(2.0966, value.getJSONObject("snapped_origin").getDouble("lon"), 0.0)
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

    private fun success(): NativeRouteResult.Success = NativeRouteResult.Success(
        profile = LocalRouteProfile.HIKE,
        engine = "valhalla-mobile",
        engineVersion = "0.5.1/valhalla-3.6.3",
        distanceMeters = 3_450.5,
        durationSeconds = 2_600.0,
        geometry = listOf(
            LocalRouteCoordinate(48.8716, 2.0966),
            LocalRouteCoordinate(48.884, 2.083),
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

    private fun localRoutePayload(nonce: String = FIRST_NONCE): String = JSONObject()
        .put("schema_version", 1)
        .put("request_id", "web-$nonce-1")
        .put("type", "local_route")
        .put("profile", "hike")
        .put("origin", coordinate(48.8715, 2.0965))
        .put("destination", coordinate(48.8983, 2.0969))
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
