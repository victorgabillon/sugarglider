package io.github.victorgabillon.sugarglider

import java.math.BigInteger
import java.security.KeyFactory
import java.security.Signature
import java.security.spec.RSAPublicKeySpec
import java.time.Instant
import java.util.Base64
import org.json.JSONArray
import org.json.JSONObject

internal data class ChatGptIdentity(val subject: String, val email: String?, val name: String?)

/** The issuer's discovery document currently advertises RS256 only. No token-supplied URL is fetched. */
internal object ChatGptIdentityVerifier {
    fun verify(token: String, clientId: String, nonce: String?, jwks: JSONObject, now: Instant = Instant.now()): ChatGptIdentity {
        require(token.length in 16..16_384) { "Invalid ChatGPT identity." }
        val parts = token.split('.')
        require(parts.size == 3 && parts.all { it.isNotEmpty() && it.all { c -> c in 'A'..'Z' || c in 'a'..'z' || c in '0'..'9' || c == '-' || c == '_' } }) { "Invalid ChatGPT identity." }
        val header = JSONObject(decode(parts[0]).toString(Charsets.UTF_8))
        require(header.optString("alg") == "RS256" && !header.has("crit")) { "Unsupported identity signature." }
        val kid = header.optString("kid")
        require(kid.length in 1..256) { "Identity key missing." }
        val keys = jwks.getJSONArray("keys")
        require(keys.length() in 1..16) { "Invalid identity key set." }
        val matching = (0 until keys.length()).map { keys.getJSONObject(it) }.filter { it.optString("kid") == kid }
        require(matching.size == 1) { "Identity key unavailable." }
        val key = matching.single()
        require(key.optString("kty") == "RSA" && (!key.has("alg") || key.optString("alg") == "RS256") &&
            (!key.has("use") || key.optString("use") == "sig")) { "Invalid identity key." }
        val modulus = BigInteger(1, decode(key.getString("n")))
        val exponent = BigInteger(1, decode(key.getString("e")))
        require(modulus.bitLength() in 2048..8192 && exponent.bitLength() <= 32 && exponent >= BigInteger.valueOf(3) && exponent.testBit(0)) { "Invalid identity key." }
        val publicKey = KeyFactory.getInstance("RSA").generatePublic(RSAPublicKeySpec(modulus, exponent))
        val verifier = Signature.getInstance("SHA256withRSA")
        verifier.initVerify(publicKey)
        verifier.update((parts[0] + "." + parts[1]).toByteArray(Charsets.US_ASCII))
        require(verifier.verify(decode(parts[2]))) { "Invalid identity signature." }
        val claims = JSONObject(decode(parts[1]).toString(Charsets.UTF_8))
        require(claims.optString("iss") == "https://auth.openai.com") { "Invalid identity issuer." }
        val audience = claims.get("aud")
        val audiences = when (audience) {
            is String -> listOf(audience)
            is JSONArray -> (0 until audience.length()).map { audience.get(it) }.also { require(it.all { v -> v is String }) }
            else -> emptyList()
        }
        require(clientId in audiences && (audiences.size == 1 || claims.optString("azp") == clientId)) { "Invalid identity audience." }
        require(!claims.has("azp") || claims.optString("azp") == clientId) { "Invalid identity party." }
        require(integer(claims, "exp") > now.epochSecond && integer(claims, "iat") <= now.epochSecond + 60) { "Identity expired or not yet valid." }
        require(!claims.has("nbf") || integer(claims, "nbf") <= now.epochSecond + 60) { "Identity not yet valid." }
        if (nonce != null) require(claims.optString("nonce") == nonce) { "Invalid identity nonce." }
        val subject = claims.get("sub")
        require(subject is String && subject.length in 1..256 && subject.none { it.isISOControl() }) { "Invalid identity subject." }
        return ChatGptIdentity(subject, display(claims, "email"), display(claims, "name"))
    }

    private fun decode(value: String): ByteArray {
        require(value.length in 1..16_384) { "Invalid identity encoding." }
        return Base64.getUrlDecoder().decode(value)
    }
    private fun integer(value: JSONObject, key: String): Long {
        val raw = value.get(key)
        require(raw is Int || raw is Long) { "Invalid identity timestamp." }
        return (raw as Number).toLong()
    }
    private fun display(value: JSONObject, key: String): String? {
        val raw = value.opt(key) ?: return null
        return (raw as? String)?.takeIf { it.length in 1..256 && it.none { c -> c.isISOControl() || c == '<' || c == '>' } }
    }
}
