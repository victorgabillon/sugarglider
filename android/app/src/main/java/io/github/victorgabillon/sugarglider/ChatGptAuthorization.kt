package io.github.victorgabillon.sugarglider

import java.net.URI
import java.net.URLDecoder
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64
import java.util.UUID

/** Native-only, single-use OAuth transaction. Never serialize this object to the bridge. */
internal class ChatGptAuthorization(
    hostId: String,
    port: Int,
    private val registeredClientId: String? = null,
    private val nowMillis: () -> Long = { System.nanoTime() / 1_000_000 },
    random: SecureRandom = SecureRandom(),
) {
    private val createdAt: Long = nowMillis()
    private var consumed: Boolean = false
    private val state: String = randomValue(random)
    val nonce: String = randomValue(random)
    private val verifier: String = randomValue(random)
    val redirectUri: String = "http://127.0.0.1:$port/auth/callback"
    val authorizationUri: URI

    init {
        require(port in 1..65535)
        require(hostId.startsWith("urn:uuid:") && UUID.fromString(hostId.removePrefix("urn:uuid:")).toString() == hostId.removePrefix("urn:uuid:"))
        require(registeredClientId == null || validClientId(registeredClientId))
        val parameters: MutableMap<String, String> = linkedMapOf(
            "client_id" to (registeredClientId ?: "dynamic_agent_client"),
            "ext_agent_host_id" to hostId,
            "response_type" to "code",
            "redirect_uri" to redirectUri,
            "scope" to "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct",
            "resource" to RESOURCE,
            "state" to state,
            "nonce" to nonce,
            "code_challenge_method" to "S256",
            "code_challenge" to Base64.getUrlEncoder().withoutPadding().encodeToString(
                MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(StandardCharsets.US_ASCII)),
            ),
        )
        if (registeredClientId == null) parameters["agent_name_hint"] = "Sugarglider"
        authorizationUri = URI("https://auth.openai.com/api/accounts/authorize?${form(parameters)}")
    }

    /** The listener must bind only 127.0.0.1; this validates the exact callback too. */
    @Synchronized
    fun receive(callback: String): ChatGptCode {
        check(!consumed) { "Sign-in attempt is no longer active." }
        check(nowMillis() - createdAt in 0..180_000) { "Sign-in timed out." }
        require(callback.length <= 16_384) { "Invalid sign-in callback." }
        val uri: URI = URI(callback)
        require(uri.scheme == "http" && uri.host == "127.0.0.1" && uri.port == URI(redirectUri).port &&
            uri.rawPath == "/auth/callback" && uri.rawFragment == null && uri.rawUserInfo == null) { "Invalid sign-in callback." }
        val parameters: Map<String, String> = query(uri.rawQuery ?: "")
        require(MessageDigest.isEqual(parameters["state"]?.toByteArray(StandardCharsets.UTF_8) ?: byteArrayOf(), state.toByteArray(StandardCharsets.UTF_8))) { "Invalid sign-in state." }
        consumed = true
        require(parameters["iss"] == null || parameters["iss"] == "https://auth.openai.com") { "Invalid sign-in issuer." }
        check(parameters["error"] == null) { "ChatGPT sign-in was not completed." }
        val clientId: String = parameters["client_id"] ?: registeredClientId ?: error("ChatGPT registration was not completed.")
        require(validClientId(clientId) && (registeredClientId == null || registeredClientId == clientId)) { "Invalid ChatGPT registration." }
        val code: String = parameters["code"] ?: error("Sign-in code missing.")
        require(code.isNotBlank() && code.length <= 4096 && code.none { it.isISOControl() }) { "Invalid sign-in code." }
        return ChatGptCode(clientId, code, verifier, redirectUri, nonce)
    }

    @Synchronized
    fun isActive(): Boolean = !consumed && nowMillis() - createdAt in 0..180_000

    @Synchronized
    fun cancel(): Unit { consumed = true }

    companion object {
        const val RESOURCE: String = "https://api.openai.com/v1"
        private fun randomValue(random: SecureRandom): String = Base64.getUrlEncoder().withoutPadding()
            .encodeToString(ByteArray(32).also(random::nextBytes))
        private fun validClientId(value: String): Boolean = value.length in 8..256 && value.startsWith("oaiapp_") && value.all { it in 'a'..'z' || it in 'A'..'Z' || it in '0'..'9' || it == '_' || it == '-' }
        internal fun form(parameters: Map<String, String>): String = parameters.entries.joinToString("&") {
            "${URLEncoder.encode(it.key, "UTF-8")}=${URLEncoder.encode(it.value, "UTF-8")}"
        }
        private fun query(raw: String): Map<String, String> {
            val result: MutableMap<String, String> = linkedMapOf()
            for (part in raw.split('&')) {
                val pair: List<String> = part.split('=', limit = 2)
                require(pair.size == 2) { "Invalid sign-in callback." }
                val key: String = URLDecoder.decode(pair[0], "UTF-8")
                require(key in setOf("state", "code", "client_id", "scope", "error", "error_description", "iss") && !result.containsKey(key)) { "Invalid sign-in callback." }
                result[key] = URLDecoder.decode(pair[1], "UTF-8")
            }
            return result
        }
    }
}

/** Not a data class: default diagnostic output must not contain code or verifier. */
internal class ChatGptCode(
    val clientId: String,
    private val code: String,
    private val verifier: String,
    private val redirectUri: String,
    val nonce: String,
) {
    fun tokenForm(): String = ChatGptAuthorization.form(linkedMapOf(
        "grant_type" to "authorization_code", "client_id" to clientId,
        "code" to code, "code_verifier" to verifier,
        "redirect_uri" to redirectUri, "resource" to ChatGptAuthorization.RESOURCE,
    ))
}
