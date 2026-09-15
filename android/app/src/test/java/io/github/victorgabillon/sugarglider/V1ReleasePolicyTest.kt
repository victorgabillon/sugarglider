package io.github.victorgabillon.sugarglider

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

class V1ReleasePolicyTest {
    @Test fun neitherBuildVariantCanEnableSharingOrOpenStoredRemoteOrigins() {
        assertFalse(V1ReleasePolicy.sharingEnabled)
        assertTrue(V1ReleasePolicy.allowsOrigin(BundledShellPolicy.ORIGIN))
        for (origin in listOf("https://sharing.example", "http://127.0.0.1:8000",
            "https://appassets.androidplatform.net.evil.example", "sugarglider://o/outing")) {
            assertFalse(V1ReleasePolicy.allowsOrigin(origin))
        }
    }

    @Test fun sharingRequestsCannotReachDispatchEvenFromAnOtherwiseTrustedPage() {
        val requests = listOf(
            BridgeRequest.StartTracking("start", "page", "https://sharing.example",
                "outing", "participant", "synthetic-token", Instant.EPOCH, 0),
            BridgeRequest.GetStatus("status", "page"),
            BridgeRequest.StopTracking("stop", "page", "outing", "participant"),
            BridgeRequest.AcknowledgeTerminalFailure("ack", "page", 1, "outing", "participant"),
        )
        for (origin in listOf(BundledShellPolicy.ORIGIN, "https://sharing.example")) {
            for (request in requests) assertFalse(V1ReleasePolicy.acceptsBridge(request, origin))
        }
    }

    @Test fun localCapabilitiesRoutingAndGpxRemainAvailableOnlyToBundledPlanner() {
        val route = NativeRouteRequest(LOCAL_ROUTE_REQUEST_VERSION, "route",
            listOf(LocalRouteCoordinate(48.0, 2.0), LocalRouteCoordinate(48.1, 2.1)),
            LocalRouteProfile.TRAIL_RUN, syntheticRegionalRoutingReference())
        for (request in listOf(
            BridgeRequest.Hello("hello", "page"),
            BridgeRequest.GetLocalRouteCapabilities("capabilities", "page", null),
            BridgeRequest.LocalRoute("route", "page", route),
            BridgeRequest.SaveGpx("save", "page", "route.gpx"),
        )) {
            assertTrue(V1ReleasePolicy.acceptsBridge(request, BundledShellPolicy.ORIGIN))
            assertFalse(V1ReleasePolicy.acceptsBridge(request, "https://sharing.example"))
        }
    }
}
