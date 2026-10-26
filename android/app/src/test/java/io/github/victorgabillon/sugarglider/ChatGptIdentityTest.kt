package io.github.victorgabillon.sugarglider

import java.security.KeyPairGenerator
import java.security.Signature
import java.security.interfaces.RSAPublicKey
import java.time.Instant
import java.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ChatGptIdentityTest {
    private val pair = KeyPairGenerator.getInstance("RSA").apply { initialize(2048) }.generateKeyPair()
    private val now = Instant.ofEpochSecond(1_800_000_000)
    private fun b64(bytes: ByteArray): String = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)
    private fun claims(): JSONObject = JSONObject().put("iss", "https://auth.openai.com").put("aud", "oaiapp_test")
        .put("sub", "synthetic-account").put("nonce", "synthetic-nonce").put("iat", now.epochSecond).put("exp", now.epochSecond + 600)
    private fun token(c: JSONObject = claims(), h: JSONObject = JSONObject().put("alg", "RS256").put("kid", "test")): String {
        val message = b64(h.toString().toByteArray()) + "." + b64(c.toString().toByteArray())
        val signature = Signature.getInstance("SHA256withRSA").apply { initSign(pair.private); update(message.toByteArray(Charsets.US_ASCII)) }.sign()
        return message + "." + b64(signature)
    }
    private fun keys(): JSONObject {
        val key = pair.public as RSAPublicKey
        fun unsigned(value: java.math.BigInteger): ByteArray = value.toByteArray().dropWhile { it == 0.toByte() }.toByteArray()
        return JSONObject().put("keys", JSONArray().put(JSONObject().put("kid", "test").put("kty", "RSA").put("alg", "RS256")
            .put("n", b64(unsigned(key.modulus))).put("e", b64(unsigned(key.publicExponent)))))
    }
    @Test fun acceptsValidSignatureAndClaims() {
        assertEquals("synthetic-account", ChatGptIdentityVerifier.verify(token(), "oaiapp_test", "synthetic-nonce", keys(), now).subject)
    }
    @Test fun rejectsWrongClaimsEvenWithValidSignature() {
        for ((key,value) in listOf("iss" to "https://evil.invalid", "aud" to "other", "nonce" to "wrong", "exp" to now.epochSecond, "iat" to now.epochSecond + 61, "sub" to "", "exp" to "1800000001", "azp" to "other")) {
            assertThrows(IllegalArgumentException::class.java) { ChatGptIdentityVerifier.verify(token(claims().put(key,value)), "oaiapp_test", "synthetic-nonce", keys(), now) }
        }
        assertThrows(IllegalArgumentException::class.java) { ChatGptIdentityVerifier.verify(token(claims().put("aud", JSONArray().put("oaiapp_test").put("other"))), "oaiapp_test", "synthetic-nonce", keys(), now) }
    }
    @Test fun rejectsTamperingUnknownKeysAndAlgorithmConfusion() {
        val original = token(); val parts = original.split('.')
        val tampered = parts[0] + "." + b64(claims().put("sub","attacker").toString().toByteArray()) + "." + parts[2]
        assertThrows(IllegalArgumentException::class.java) { ChatGptIdentityVerifier.verify(tampered,"oaiapp_test","synthetic-nonce",keys(),now) }
        for (h in listOf(JSONObject().put("alg","none").put("kid","test"),JSONObject().put("alg","HS256").put("kid","test"),JSONObject().put("alg","RS256").put("kid","missing"),JSONObject().put("alg","RS256").put("kid","test").put("crit", JSONArray()))) {
            assertThrows(IllegalArgumentException::class.java) { ChatGptIdentityVerifier.verify(token(h=h),"oaiapp_test","synthetic-nonce",keys(),now) }
        }
    }
}
