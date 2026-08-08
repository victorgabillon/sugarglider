package io.github.victorgabillon.sugarglider

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.URL

class NativeOutingApiTest {
    @Test
    fun acceptedPublicationUsesExactContract() {
        val connection = FakeConnection(
            URL("$TEST_ORIGIN/"),
            200,
            "{\"sequence\":1234}",
        )
        val api = NativeOutingApi(ConnectionFactory { connection })
        val outcome = api.publish(testSession(), 1_234, testSample())
        assertEquals(PutOutcome.Accepted(1_234), outcome)
        assertEquals("PUT", connection.requestMethod)
        assertEquals(TEST_TOKEN, connection.getRequestProperty("X-Sugarglider-Participant-Token"))
        val body = connection.written.toString(Charsets.UTF_8.name())
        assertTrue(body.contains("\"schema_version\":1"))
        assertTrue(body.contains("\"captured_at\":\"$TEST_NOW\""))
    }

    @Test
    fun redirectIsNeverFollowedAndNeverReceivesSecondToken() {
        val connections = mutableListOf<FakeConnection>()
        val api = NativeOutingApi(ConnectionFactory { url ->
            FakeConnection(url, 302, "").also(connections::add)
        })
        assertEquals(PutOutcome.DefiniteFailure, api.publish(testSession(), 12, testSample()))
        assertEquals(1, connections.size)
        assertFalse(connections.single().instanceFollowRedirects)
        assertEquals(TEST_ORIGIN, "${connections.single().url.protocol}://${connections.single().url.authority}")
    }

    @Test
    fun conflictAndInvalidFixAreClassified() {
        val conflict = NativeOutingApi(ConnectionFactory { url ->
            FakeConnection(
                url,
                409,
                "{\"error\":{\"code\":\"outing_position_sequence_conflict\"}}",
            )
        })
        val invalid = NativeOutingApi(ConnectionFactory { url ->
            FakeConnection(
                url,
                422,
                "{\"error\":{\"code\":\"outing_position_invalid\"}}",
            )
        })
        assertEquals(PutOutcome.SequenceConflict, conflict.publish(testSession(), 12, testSample()))
        assertEquals(PutOutcome.InvalidFix, invalid.publish(testSession(), 12, testSample()))
    }

    @Test
    fun directAndRecoveryNotFoundAreDefinitive() {
        val api = NativeOutingApi(ConnectionFactory { url ->
            FakeConnection(url, 404, "{\"error\":{\"code\":\"outing_not_found\"}}")
        })
        assertEquals(PutOutcome.NotFound, api.publish(testSession(), 12, testSample()))
        assertEquals(LiveSequenceOutcome.NotFound, api.recoverSequence(testSession()))
    }

    @Test
    fun liveRecoveryReadsOnlyMatchingParticipantSequence() {
        val body = """
            {"positions":[
              {"participant_id":"someone_else_123456789","sequence":999},
              {"participant_id":"$TEST_PARTICIPANT","sequence":42}
            ]}
        """.trimIndent()
        val api = NativeOutingApi(ConnectionFactory { url -> FakeConnection(url, 200, body) })
        assertEquals(LiveSequenceOutcome.Accepted(42), api.recoverSequence(testSession()))
    }

    @Test
    fun deleteIsAuthenticatedOnceAndTransportFailureIsUncertain() {
        val connection = FakeConnection(URL("$TEST_ORIGIN/"), 204, "")
        val api = NativeOutingApi(ConnectionFactory { connection })
        assertEquals(ClearOutcome.Cleared, api.clear(testSession()))
        assertEquals("DELETE", connection.requestMethod)
        assertEquals(TEST_TOKEN, connection.getRequestProperty("X-Sugarglider-Participant-Token"))

        val offline = NativeOutingApi(ConnectionFactory { throw java.io.IOException("offline") })
        assertEquals(ClearOutcome.Transient(true), offline.clear(testSession()))
    }

    private class FakeConnection(
        url: URL,
        private val status: Int,
        private val body: String,
    ) : HttpURLConnection(url) {
        val written = ByteArrayOutputStream()

        override fun connect() = Unit

        override fun disconnect() = Unit

        override fun usingProxy(): Boolean = false

        override fun getResponseCode(): Int = status

        override fun getInputStream(): InputStream = ByteArrayInputStream(
            body.toByteArray(Charsets.UTF_8),
        )

        override fun getErrorStream(): InputStream? = if (status >= 400) {
            ByteArrayInputStream(body.toByteArray(Charsets.UTF_8))
        } else {
            null
        }

        override fun getOutputStream(): OutputStream = written
    }
}
