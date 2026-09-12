package io.github.victorgabillon.sugarglider

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.json.JSONObject
import java.time.Instant

class BundledShellPolicyTest {
    private val allowed = setOf(
        "index.html", "app.js", "android_ui_config.json", "manifest.webmanifest",
        "fonts/Open Sans Semibold/0-255.pbf",
    )
    private val origin = BundledShellPolicy.ORIGIN

    @Test fun publicResourcesResolveOnlyToDeclaredAssets() {
        assertEquals("index.html", asset("/"))
        assertEquals("app.js", asset("/static/app.js"))
        assertEquals("android_ui_config.json", asset("/v1/ui/config"))
        assertEquals("manifest.webmanifest", asset("/manifest.webmanifest"))
        assertEquals("fonts/Open Sans Semibold/0-255.pbf", asset("/static/fonts/Open%20Sans%20Semibold/0-255.pbf"))
        assertNull(asset("/static/unknown.js"))
        assertNull(asset("/static/shell-assets.txt"))
    }

    @Test fun serverDataServiceWorkersAndPrivatePathsNeverResolve() {
        for (path in listOf(
            "/service-worker.js", "/v2/plans", "/v2/outings/fixture",
            "/r/fixture", "/o/fixture", "/private/session", "/static/../index.html",
            "/static/%2e%2e/index.html", "/static/%5capp.js", "/static//app.js",
            "/static/app.js?participant_token=fixture", "/#fixture", "/?a=b",
        )) assertNull(path, asset(path))
        assertNull(BundledShellPolicy.assetPath("$origin/", "POST", allowed))
    }

    @Test fun reservedHostNeverTurnsIntoAnAlternateNetworkOrigin() {
        for (url in listOf(
            "http://appassets.androidplatform.net/", "$origin:8443/",
            "https://fixture@appassets.androidplatform.net/",
        )) {
            assertTrue(BundledShellPolicy.ownsHost(url))
            assertNull(BundledShellPolicy.assetPath(url, "GET", allowed))
        }
        assertFalse(BundledShellPolicy.ownsHost("https://sharing.example/"))
        assertFalse(BundledShellPolicy.ownsHost("$origin.evil.example/"))
        assertNull(BundledShellPolicy.assetPath("https://sharing.example/static/app.js", "GET", allowed))
    }

    @Test fun bundledBridgeAllowsPlanningAndExportWithoutSharingAuthority() {
        val id = "page-one"; val nonce = "page"
        val route = NativeRouteRequest(2, id, listOf(LocalRouteCoordinate(48.0, 2.0), LocalRouteCoordinate(48.1, 2.1)), LocalRouteProfile.HIKE)
        for (request in listOf(
            BridgeRequest.Hello(id, nonce), BridgeRequest.GetLocalRouteCapabilities(id, nonce),
            BridgeRequest.LocalRoute(id, nonce, route), BridgeRequest.SaveGpx(id, nonce, "route.gpx"),
            BridgeRequest.RejectedLocalRoute(id, nonce, NativeRouteFailureCode.INVALID_REQUEST),
        )) assertTrue(BundledShellPolicy.acceptsRequest(request))
        for (request in listOf(
            BridgeRequest.GetStatus(id, nonce), BridgeRequest.StopTracking(id, nonce, "outing", "participant"),
            BridgeRequest.AcknowledgeTerminalFailure(id, nonce, 1, "outing", "participant"),
            BridgeRequest.StartTracking(id, nonce, origin, "outing", "participant", "synthetic-token", Instant.EPOCH, 0),
        )) assertFalse(BundledShellPolicy.acceptsRequest(request))
    }

    @Test fun sharingRejectionIsExplicitAndContainsNoParticipantIdentity() {
        val reply = JSONObject(BridgeProtocol.failure("page-one", "sharing_unavailable"))
        assertEquals("sharing_unavailable", reply.getString("code"))
        assertTrue(reply.isNull("outing_slug"))
        assertTrue(reply.isNull("participant_id"))
        assertTrue(reply.isNull("event_id"))
    }

    private fun asset(path: String) = BundledShellPolicy.assetPath(origin + path, "GET", allowed)
}
