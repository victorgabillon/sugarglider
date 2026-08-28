package io.github.victorgabillon.sugarglider

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WebGeolocationPermissionCoordinatorTest {
    @Test
    fun exactConfiguredOriginWithPermissionIsGrantedImmediately() {
        val decisions = mutableListOf<Boolean>()
        val action = coordinator().begin(
            requestedOrigin = ORIGIN,
            configuredOrigin = ORIGIN,
            navigationEpoch = 4,
            sourceWebViewIdentity = 8,
            currentWebViewIdentity = 8,
            activityVisible = true,
            preciseLocationGranted = true,
            resolve = decisions::add,
        )

        assertEquals(WebGeolocationPermissionAction.GRANTED, action)
        assertEquals(listOf(true), decisions)
    }

    @Test
    fun canonicalEquivalentRequestedOriginWithPermissionIsGrantedImmediately() {
        val configured = "http://localhost:8000"
        val requested = ServerOrigin.parse("http://localhost:8000/", true)?.normalized
        val decisions = mutableListOf<Boolean>()

        val action = coordinator().begin(
            requestedOrigin = requested ?: error("origin must normalize"),
            configuredOrigin = configured,
            navigationEpoch = 4,
            sourceWebViewIdentity = 8,
            currentWebViewIdentity = 8,
            activityVisible = true,
            preciseLocationGranted = true,
            resolve = decisions::add,
        )

        assertEquals(WebGeolocationPermissionAction.GRANTED, action)
        assertEquals(listOf(true), decisions)
    }

    @Test
    fun differentOriginIsRejected() {
        val decisions = mutableListOf<Boolean>()
        val action = coordinator().begin(
            requestedOrigin = "https://other.example",
            configuredOrigin = ORIGIN,
            navigationEpoch = 4,
            sourceWebViewIdentity = 8,
            currentWebViewIdentity = 8,
            activityVisible = true,
            preciseLocationGranted = true,
            resolve = decisions::add,
        )

        assertEquals(WebGeolocationPermissionAction.REJECTED, action)
        assertEquals(listOf(false), decisions)
    }

    @Test
    fun differentCanonicalHostPortAndSchemeAreRejected() {
        val configured = "http://localhost:8000"

        for (rawRequested in listOf(
            "http://127.0.0.1:8000",
            "http://localhost:8001",
            "https://localhost:8000",
        )) {
            val requested = ServerOrigin.parse(rawRequested, true)?.normalized
                ?: error("test origin must normalize")
            val decisions = mutableListOf<Boolean>()
            val action = coordinator().begin(
                requestedOrigin = requested,
                configuredOrigin = configured,
                navigationEpoch = 4,
                sourceWebViewIdentity = 8,
                currentWebViewIdentity = 8,
                activityVisible = true,
                preciseLocationGranted = true,
                resolve = decisions::add,
            )

            assertEquals(rawRequested, WebGeolocationPermissionAction.REJECTED, action)
            assertEquals(rawRequested, listOf(false), decisions)
        }
    }

    @Test
    fun missingPermissionRequestsOnlyOneForegroundDecision() {
        val first = mutableListOf<Boolean>()
        val second = mutableListOf<Boolean>()
        val gate = coordinator()

        assertEquals(
            WebGeolocationPermissionAction.REQUEST_FOREGROUND_LOCATION,
            beginPending(gate, first::add),
        )
        assertTrue(gate.hasPending())
        assertEquals(
            WebGeolocationPermissionAction.BUSY,
            beginPending(gate, second::add),
        )
        assertEquals(emptyList<Boolean>(), first)
        assertEquals(listOf(false), second)
    }

    @Test
    fun staleNavigationCannotGrantPendingRequest() {
        val decisions = mutableListOf<Boolean>()
        val gate = coordinator()
        beginPending(gate, decisions::add)

        assertFalse(
            gate.complete(
                preciseLocationGranted = true,
                configuredOrigin = ORIGIN,
                navigationEpoch = 5,
                currentWebViewIdentity = 8,
            ),
        )
        assertEquals(listOf(false), decisions)
        assertFalse(gate.hasPending())
    }

    @Test
    fun destructionRejectsPendingRequest() {
        val decisions = mutableListOf<Boolean>()
        val gate = coordinator()
        beginPending(gate, decisions::add)

        gate.invalidate()

        assertEquals(listOf(false), decisions)
        assertFalse(gate.hasPending())
    }

    @Test
    fun serverChangeCannotReusePriorOriginRequest() {
        val oldDecisions = mutableListOf<Boolean>()
        val newDecisions = mutableListOf<Boolean>()
        val gate = coordinator()
        beginPending(gate, oldDecisions::add)

        assertFalse(
            gate.complete(
                preciseLocationGranted = true,
                configuredOrigin = "https://new.example",
                navigationEpoch = 4,
                currentWebViewIdentity = 8,
            ),
        )
        assertEquals(listOf(false), oldDecisions)
        assertEquals(
            WebGeolocationPermissionAction.GRANTED,
            gate.begin(
                requestedOrigin = "https://new.example",
                configuredOrigin = "https://new.example",
                navigationEpoch = 4,
                sourceWebViewIdentity = 8,
                currentWebViewIdentity = 8,
                activityVisible = true,
                preciseLocationGranted = true,
                resolve = newDecisions::add,
            ),
        )
        assertEquals(listOf(true), newDecisions)
    }

    private fun coordinator() = WebGeolocationPermissionCoordinator()

    private fun beginPending(
        gate: WebGeolocationPermissionCoordinator,
        resolve: (Boolean) -> Unit,
    ): WebGeolocationPermissionAction = gate.begin(
        requestedOrigin = ORIGIN,
        configuredOrigin = ORIGIN,
        navigationEpoch = 4,
        sourceWebViewIdentity = 8,
        currentWebViewIdentity = 8,
        activityVisible = true,
        preciseLocationGranted = false,
        resolve = resolve,
    )

    companion object {
        private const val ORIGIN = "https://sugarglider.example"
    }
}
