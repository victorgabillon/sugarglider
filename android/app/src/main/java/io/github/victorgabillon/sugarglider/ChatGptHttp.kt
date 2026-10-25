package io.github.victorgabillon.sugarglider

import java.io.FilterInputStream
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.atomic.AtomicBoolean
import org.json.JSONObject

internal enum class ChatGptFailureKind { CANCELLED, NETWORK, AUTH_EXPIRED, AUTH_TIMEOUT, USAGE_LIMIT, UNSUPPORTED, INVALID_RESPONSE, STORAGE, BROWSER_UNAVAILABLE }
internal enum class ChatGptHttpStage { DISCOVERY, IDENTITY_KEYS, TOKEN_EXCHANGE, REVOCATION, MODEL_CATALOG, INFERENCE }
internal enum class ChatGptNetworkCause { DNS, TLS, TIMEOUT, CONNECT, IO, HTTP_STATUS }
internal enum class ChatGptResponseIssue { CONTENT_TYPE, BODY_TOO_LARGE, JSON_SYNTAX, CATALOG_SCHEMA }
// Only fixed enums cross the diagnostic boundary, never provider bodies,
// exception messages, URLs, headers or token forms.
internal class ChatGptException(val kind: ChatGptFailureKind, val stage: ChatGptHttpStage? = null,
    val networkCause: ChatGptNetworkCause? = null, val responseIssue: ChatGptResponseIssue? = null) : IllegalStateException(kind.name) {
    fun diagnostic(): JSONObject = JSONObject().put("kind",kind.name.lowercase())
        .put("stage",stage?.name?.lowercase() ?: JSONObject.NULL)
        .put("network_cause",networkCause?.name?.lowercase() ?: JSONObject.NULL)
        .put("response_issue",responseIssue?.name?.lowercase() ?: JSONObject.NULL)
}

/** Owns one foreground operation's connections; closing aborts blocked network reads. */
internal class ChatGptCall(private val nowNanos: () -> Long = System::nanoTime) : AutoCloseable {
    private val stopped = AtomicBoolean(false)
    @Volatile private var networkStarted: Long? = null
    @Volatile private var connection: HttpURLConnection? = null
    fun cancelled(): Boolean = stopped.get() || networkStarted?.let { nowNanos() - it >= 120_000_000_000L } == true
    @Synchronized fun beginNetwork() {
        if (cancelled()) throw ChatGptException(ChatGptFailureKind.CANCELLED)
        if (networkStarted == null) networkStarted = nowNanos()
    }
    @Synchronized fun attach(value: HttpURLConnection) {
        if (cancelled()) { value.disconnect(); throw ChatGptException(ChatGptFailureKind.CANCELLED) }
        connection = value
    }
    @Synchronized fun detach(value: HttpURLConnection) { if (connection === value) connection = null; value.disconnect() }
    @Synchronized override fun close() { stopped.set(true); connection?.disconnect() }
}

/** Fixed official endpoints only; no redirects, cookies, retries or custom TLS trust. */
internal class ChatGptHttp(private val connections: ConnectionFactory = ConnectionFactory { it.openConnection() as HttpURLConnection }) {
    var modelCatalogBytes: Int? = null
        private set
    fun discovery(call: ChatGptCall): JSONObject = json(call, DISCOVERY)
    fun jwks(call: ChatGptCall): JSONObject = json(call, JWKS)
    fun exchange(call: ChatGptCall, form: String): JSONObject = json(call, TOKEN, form.toByteArray(Charsets.UTF_8), "application/x-www-form-urlencoded")
    fun revoke(call: ChatGptCall, form: String) {
        request(call, REVOKE, form.toByteArray(Charsets.UTF_8), "application/x-www-form-urlencoded", null) { input -> readBounded(input, 4096); Unit }
    }
    fun models(call: ChatGptCall, token: String): JSONObject {
        modelCatalogBytes = null
        return json(call, MODELS, bearer = token)
    }
    fun infer(call: ChatGptCall, token: String, payload: JSONObject): ChatGptCompletion {
        require(payload.optBoolean("stream") && payload.has("store") && !payload.getBoolean("store"))
        val body = payload.toString().toByteArray(Charsets.UTF_8)
        require(body.size <= 98_304)
        return request(call, RESPONSES, body, "application/json", token) { input ->
            ChatGptResponseStream.completed(input.reader(Charsets.UTF_8), call::cancelled)
        }
    }
    private fun json(call: ChatGptCall, endpoint: String, body: ByteArray? = null, contentType: String = "application/json", bearer: String? = null): JSONObject =
        request(call, endpoint, body, contentType, bearer) { input ->
            try {
                // Catalog entries may carry substantial unused provider metadata.
                // Identity/token documents retain their smaller independent cap.
                val bytes = readBounded(input, if (endpoint == MODELS) 1_048_576 else 262_144)
                if (endpoint == MODELS) modelCatalogBytes = bytes.size
                JSONObject(bytes.toString(Charsets.UTF_8))
            }
            catch (error: ChatGptException) { throw error }
            catch (_: Exception) { throw ChatGptException(ChatGptFailureKind.INVALID_RESPONSE,responseIssue=ChatGptResponseIssue.JSON_SYNTAX) }
        }
    private fun <T> request(call: ChatGptCall, endpoint: String, body: ByteArray?, contentType: String, bearer: String?, read: (InputStream) -> T): T {
        require(endpoint in setOf(DISCOVERY, JWKS, TOKEN, REVOKE, MODELS, RESPONSES))
        val stage = when (endpoint) {
            DISCOVERY -> ChatGptHttpStage.DISCOVERY
            JWKS -> ChatGptHttpStage.IDENTITY_KEYS
            TOKEN -> ChatGptHttpStage.TOKEN_EXCHANGE
            REVOKE -> ChatGptHttpStage.REVOCATION
            MODELS -> ChatGptHttpStage.MODEL_CATALOG
            else -> ChatGptHttpStage.INFERENCE
        }
        if (bearer != null) require(bearer.length in 1..16_384 && bearer.none { it.isISOControl() })
        call.beginNetwork()
        val connection = try { connections.open(URL(endpoint)) } catch (error: Exception) { throw networkFailure(call,stage,error) }
        call.attach(connection)
        try {
            connection.instanceFollowRedirects = false
            connection.connectTimeout = 10_000
            connection.readTimeout = 15_000
            connection.useCaches = false
            connection.requestMethod = if (body == null) "GET" else "POST"
            connection.setRequestProperty("Accept", if (endpoint == RESPONSES) "text/event-stream" else "application/json")
            connection.setRequestProperty("Cache-Control", "no-store")
            if (bearer != null) connection.setRequestProperty("Authorization", "Bearer $bearer")
            if (body != null) {
                connection.setRequestProperty("Content-Type", contentType)
                connection.doOutput = true
                connection.setFixedLengthStreamingMode(body.size)
                connection.outputStream.use { it.write(body) }
            }
            when (connection.responseCode) {
                in 200..299 -> Unit
                401, 403 -> throw ChatGptException(ChatGptFailureKind.AUTH_EXPIRED)
                429 -> throw ChatGptException(ChatGptFailureKind.USAGE_LIMIT)
                400, 404, 422 -> {
                    val error = runCatching { connection.errorStream?.use { JSONObject(readBounded(it,16_384).toString(Charsets.UTF_8)) } }.getOrNull()
                    val code = (error?.opt("error") as? String) ?: error?.optJSONObject("error")?.optString("code")
                    throw ChatGptException(if (code == "invalid_grant") ChatGptFailureKind.AUTH_EXPIRED else ChatGptFailureKind.UNSUPPORTED)
                }
                else -> throw ChatGptException(ChatGptFailureKind.NETWORK,stage,ChatGptNetworkCause.HTTP_STATUS)
            }
            val type = connection.contentType?.substringBefore(';')?.trim()?.lowercase()
            if (endpoint != REVOKE && type != if (endpoint == RESPONSES) "text/event-stream" else "application/json") {
                throw ChatGptException(ChatGptFailureKind.INVALID_RESPONSE,stage,responseIssue=ChatGptResponseIssue.CONTENT_TYPE)
            }
            return connection.inputStream.use { raw ->
                val bounded = object : FilterInputStream(raw) {
                    override fun read(): Int { checkCurrent(); return super.read() }
                    override fun read(buffer: ByteArray, offset: Int, count: Int): Int { checkCurrent(); return super.read(buffer, offset, count) }
                    private fun checkCurrent() { if (call.cancelled()) throw ChatGptException(ChatGptFailureKind.CANCELLED) }
                }
                read(bounded)
            }
        } catch (error: ChatGptException) { throw ChatGptException(error.kind,error.stage ?: stage,error.networkCause,error.responseIssue) }
        catch (error: java.io.IOException) { throw networkFailure(call,stage,error) }
        catch (_: Exception) { throw ChatGptException(if (call.cancelled()) ChatGptFailureKind.CANCELLED else ChatGptFailureKind.INVALID_RESPONSE,stage) }
        finally { call.detach(connection) }
    }
    private fun networkFailure(call: ChatGptCall, stage: ChatGptHttpStage, error: Exception): ChatGptException {
        val cause = when (error) {
            is java.net.UnknownHostException -> ChatGptNetworkCause.DNS
            is javax.net.ssl.SSLException -> ChatGptNetworkCause.TLS
            is java.net.SocketTimeoutException -> ChatGptNetworkCause.TIMEOUT
            is java.net.ConnectException -> ChatGptNetworkCause.CONNECT
            else -> ChatGptNetworkCause.IO
        }
        return ChatGptException(if (call.cancelled()) ChatGptFailureKind.CANCELLED else ChatGptFailureKind.NETWORK,stage,cause)
    }
    private fun readBounded(input: InputStream, maximum: Int): ByteArray {
        val output = java.io.ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        while (true) {
            val count = input.read(buffer, 0, minOf(buffer.size, maximum + 1 - output.size()))
            if (count < 0) break
            output.write(buffer, 0, count)
            if (output.size() > maximum) throw ChatGptException(ChatGptFailureKind.INVALID_RESPONSE,responseIssue=ChatGptResponseIssue.BODY_TOO_LARGE)
        }
        return output.toByteArray()
    }
    companion object {
        const val DISCOVERY: String = "https://auth.openai.com/.well-known/openid-configuration"
        const val JWKS: String = "https://auth.openai.com/.well-known/jwks.json"
        const val TOKEN: String = "https://auth.openai.com/api/accounts/oauth/token"
        const val REVOKE: String = "https://auth.openai.com/api/accounts/oauth/revoke"
        const val MODELS: String = "https://api.openai.com/v1/models"
        const val RESPONSES: String = "https://api.openai.com/v1/responses"
    }
}
