package io.github.victorgabillon.sugarglider

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets

internal sealed interface PutOutcome {
    data class Accepted(val sequence: Long) : PutOutcome

    data object NotFound : PutOutcome

    data object SequenceConflict : PutOutcome

    data object InvalidFix : PutOutcome

    data class Transient(val uncertainTransport: Boolean) : PutOutcome

    data object DefiniteFailure : PutOutcome
}

internal sealed interface LiveSequenceOutcome {
    data class Accepted(val sequence: Long?) : LiveSequenceOutcome

    data object NotFound : LiveSequenceOutcome

    data class Transient(val uncertainTransport: Boolean) : LiveSequenceOutcome

    data object DefiniteFailure : LiveSequenceOutcome
}

internal sealed interface ClearOutcome {
    data object Cleared : ClearOutcome

    data object NotFound : ClearOutcome

    data class Transient(val uncertainTransport: Boolean) : ClearOutcome

    data object DefiniteFailure : ClearOutcome
}

internal fun interface ConnectionFactory {
    fun open(url: URL): HttpURLConnection
}

internal interface NativeTrackingPublisher {
    fun publish(
        session: ParticipantSession,
        sequence: Long,
        sample: NormalizedLocationSample,
    ): PutOutcome

    fun recoverSequence(session: ParticipantSession): LiveSequenceOutcome

    fun clear(session: ParticipantSession): ClearOutcome
}

internal class NativeOutingApi(
    private val connectionFactory: ConnectionFactory = ConnectionFactory {
        it.openConnection() as HttpURLConnection
    },
    private val connectTimeoutMs: Int = 10_000,
    private val readTimeoutMs: Int = 10_000,
) : NativeTrackingPublisher {
    override fun publish(
        session: ParticipantSession,
        sequence: Long,
        sample: NormalizedLocationSample,
    ): PutOutcome {
        val payload = JSONObject()
            .put("schema_version", SCHEMA_VERSION)
            .put("sequence", sequence)
            .put(
                "coordinate",
                JSONObject().put("lat", sample.latitude).put("lon", sample.longitude),
            ).put("accuracy_m", sample.accuracyM)
            .put("altitude_m", sample.altitudeM ?: JSONObject.NULL)
            .put("speed_m_s", sample.speedMS ?: JSONObject.NULL)
            .put("heading_deg", sample.headingDeg ?: JSONObject.NULL)
            .put("captured_at", sample.capturedAt.toString())
            .toString()
            .toByteArray(StandardCharsets.UTF_8)
        return request(
            session = session,
            method = "PUT",
            endpoint = positionEndpoint(session),
            authenticated = true,
            body = payload,
        ) { response ->
            when (HttpOutcomeClassifier.classify(response.status, response.errorCode)) {
                HttpOutcomeKind.ACCEPTED -> {
                    val accepted = response.json?.strictSafeLong("sequence")
                    if (accepted == null) PutOutcome.DefiniteFailure else PutOutcome.Accepted(accepted)
                }
                HttpOutcomeKind.NOT_FOUND -> PutOutcome.NotFound
                HttpOutcomeKind.SEQUENCE_CONFLICT -> PutOutcome.SequenceConflict
                HttpOutcomeKind.INVALID_FIX -> PutOutcome.InvalidFix
                HttpOutcomeKind.TRANSIENT -> PutOutcome.Transient(uncertainTransport = false)
                HttpOutcomeKind.DEFINITE_FAILURE -> PutOutcome.DefiniteFailure
            }
        } ?: PutOutcome.Transient(uncertainTransport = true)
    }

    override fun recoverSequence(session: ParticipantSession): LiveSequenceOutcome = request(
        session = session,
        method = "GET",
        endpoint = "${session.serverOrigin}/v2/outings/${session.outingSlug}/live",
        authenticated = false,
        body = null,
    ) { response ->
        when (HttpOutcomeClassifier.classify(response.status, response.errorCode)) {
            HttpOutcomeKind.ACCEPTED -> LiveSequenceOutcome.Accepted(
                participantSequence(response.json, session.participantId),
            )
            HttpOutcomeKind.NOT_FOUND -> LiveSequenceOutcome.NotFound
            HttpOutcomeKind.TRANSIENT -> LiveSequenceOutcome.Transient(uncertainTransport = false)
            else -> LiveSequenceOutcome.DefiniteFailure
        }
    } ?: LiveSequenceOutcome.Transient(uncertainTransport = true)

    override fun clear(session: ParticipantSession): ClearOutcome = request(
        session = session,
        method = "DELETE",
        endpoint = positionEndpoint(session),
        authenticated = true,
        body = null,
    ) { response ->
        when (HttpOutcomeClassifier.classify(response.status, response.errorCode)) {
            HttpOutcomeKind.ACCEPTED -> ClearOutcome.Cleared
            HttpOutcomeKind.NOT_FOUND -> ClearOutcome.NotFound
            HttpOutcomeKind.TRANSIENT -> ClearOutcome.Transient(uncertainTransport = false)
            else -> ClearOutcome.DefiniteFailure
        }
    } ?: ClearOutcome.Transient(uncertainTransport = true)

    private fun positionEndpoint(session: ParticipantSession): String =
        "${session.serverOrigin}/v2/outings/${session.outingSlug}/participants/" +
            "${session.participantId}/position"

    private fun <T> request(
        session: ParticipantSession,
        method: String,
        endpoint: String,
        authenticated: Boolean,
        body: ByteArray?,
        transform: (NativeResponse) -> T,
    ): T? {
        val expectedOrigin = ServerOrigin.parse(session.serverOrigin, allowDevelopmentHttp = true)
            ?: return null
        val url = try {
            URL(endpoint)
        } catch (_: Exception) {
            return null
        }
        if ("${url.protocol}://${url.authority}" != expectedOrigin.normalized) return null
        val connection = try {
            connectionFactory.open(url)
        } catch (_: Exception) {
            return null
        }
        return try {
            configure(connection, method, authenticated, session.participantToken, body)
            if (body != null) connection.outputStream.use { it.write(body) }
            val status = connection.responseCode
            val responseBody = readBoundedBody(connection, status)
            transform(
                NativeResponse(
                    status = status,
                    json = responseBody?.let(::parseObject),
                    errorCode = responseBody?.let(::safeErrorCode),
                ),
            )
        } catch (_: Exception) {
            null
        } finally {
            connection.disconnect()
        }
    }

    private fun configure(
        connection: HttpURLConnection,
        method: String,
        authenticated: Boolean,
        token: String,
        body: ByteArray?,
    ) {
        connection.requestMethod = method
        connection.instanceFollowRedirects = false
        connection.connectTimeout = connectTimeoutMs
        connection.readTimeout = readTimeoutMs
        connection.useCaches = false
        connection.doInput = true
        connection.setRequestProperty("Accept", "application/json")
        if (authenticated) {
            connection.setRequestProperty("X-Sugarglider-Participant-Token", token)
        }
        if (body != null) {
            connection.doOutput = true
            connection.setFixedLengthStreamingMode(body.size)
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
        }
    }

    private fun readBoundedBody(connection: HttpURLConnection, status: Int): String? {
        val stream = if (status >= 400) connection.errorStream else connection.inputStream
        if (stream == null) return null
        return stream.use { input ->
            val buffer = ByteArray(8_193)
            var total = 0
            while (total < buffer.size) {
                val count = input.read(buffer, total, buffer.size - total)
                if (count < 0) break
                total += count
            }
            if (total > 8_192) null else String(buffer, 0, total, StandardCharsets.UTF_8)
        }
    }

    private fun parseObject(value: String): JSONObject? = try {
        JSONObject(value)
    } catch (_: Exception) {
        null
    }

    private fun safeErrorCode(value: String): String? = parseObject(value)
        ?.optJSONObject("error")
        ?.optString("code")
        ?.takeIf { it.length in 1..80 }

    private fun participantSequence(value: JSONObject?, participantId: String): Long? {
        val positions = value?.optJSONArray("positions") ?: return null
        for (index in 0 until positions.length()) {
            val position = positions.optJSONObject(index) ?: continue
            if (position.optString("participant_id") != participantId) continue
            return position.strictSafeLong("sequence")
        }
        return null
    }

    private data class NativeResponse(
        val status: Int,
        val json: JSONObject?,
        val errorCode: String?,
    )
}

private fun JSONObject.strictSafeLong(key: String): Long? {
    val value = try {
        get(key)
    } catch (_: Exception) {
        return null
    }
    val result = when (value) {
        is Byte -> value.toLong()
        is Short -> value.toLong()
        is Int -> value.toLong()
        is Long -> value
        else -> return null
    }
    return result.takeIf { it in 0..MAXIMUM_SAFE_SEQUENCE }
}
