package io.github.victorgabillon.sugarglider

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ServerOriginTest {
    @Test
    fun releaseRejectsHttp() {
        assertNull(ServerOrigin.parse("http://10.0.2.2:8000", allowDevelopmentHttp = false))
    }

    @Test
    fun debugAllowsEmulatorHttp() {
        assertEquals(
            "http://10.0.2.2:8000",
            ServerOrigin.parse("http://10.0.2.2:8000/", allowDevelopmentHttp = true)?.normalized,
        )
    }

    @Test
    fun debugRejectsPublicHttp() {
        assertNull(ServerOrigin.parse("http://example.com", allowDevelopmentHttp = true))
    }

    @Test
    fun credentialsAreRejected() {
        assertNull(ServerOrigin.parse("https://user:secret@example.test", false))
    }

    @Test
    fun nonRootPathIsRejected() {
        assertNull(ServerOrigin.parse("https://example.test/o/outing", false))
    }

    @Test
    fun queryAndFragmentAreRejected() {
        assertNull(ServerOrigin.parse("https://example.test/?x=1", false))
        assertNull(ServerOrigin.parse("https://example.test/#fragment", false))
    }

    @Test
    fun defaultPortAndCaseAreNormalized() {
        assertEquals(
            "https://example.test",
            ServerOrigin.parse("HTTPS://EXAMPLE.TEST:443/", false)?.normalized,
        )
    }

    @Test
    fun privateLanRangesAreAcceptedOnlyInDebug() {
        assertEquals(
            "http://192.168.1.12:8000",
            ServerOrigin.parse("http://192.168.1.12:8000", true)?.normalized,
        )
        assertNull(ServerOrigin.parse("http://192.168.1.12:8000", false))
    }
}
