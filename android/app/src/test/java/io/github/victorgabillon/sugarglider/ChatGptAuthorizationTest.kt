package io.github.victorgabillon.sugarglider

import java.net.URLDecoder
import java.security.MessageDigest
import java.util.Base64
import org.junit.Assert.*
import org.junit.Test

class ChatGptAuthorizationTest {
    private val host = "urn:uuid:871494d4-b81b-4523-9626-3547cff2e4cc"
    private fun query(raw: String): Map<String, String> = raw.split('&').associate {
        val p = it.split('=', limit = 2)
        URLDecoder.decode(p[0], "UTF-8") to URLDecoder.decode(p[1], "UTF-8")
    }
    private fun callback(a: ChatGptAuthorization, extra: String = "code=synthetic-code&client_id=oaiapp_synthetic"): String =
        a.redirectUri + "?state=" + query(a.authorizationUri.rawQuery).getValue("state") + "&" + extra

    @Test fun registrationPkceAndOneTimeExchange() {
        val a = ChatGptAuthorization(host, 34567)
        val p = query(a.authorizationUri.rawQuery)
        assertEquals("https", a.authorizationUri.scheme)
        assertEquals("auth.openai.com", a.authorizationUri.host)
        assertEquals("dynamic_agent_client", p["client_id"])
        assertEquals(host, p["ext_agent_host_id"])
        assertEquals("Sugarglider", p["agent_name_hint"])
        val code = a.receive(callback(a))
        val form = query(code.tokenForm())
        assertEquals("oaiapp_synthetic", form["client_id"])
        assertEquals(a.redirectUri, form["redirect_uri"])
        assertEquals(ChatGptAuthorization.RESOURCE, form["resource"])
        assertEquals(p["nonce"], code.nonce)
        assertEquals(p["code_challenge"], Base64.getUrlEncoder().withoutPadding().encodeToString(
            MessageDigest.getInstance("SHA-256").digest(form.getValue("code_verifier").toByteArray(Charsets.US_ASCII))))
        assertFalse(code.toString().contains("synthetic-code"))
        assertThrows(IllegalStateException::class.java) { a.receive(callback(a)) }
    }
    @Test fun rejectsWrongCallbacksWithoutConsumingValidAttempt() {
        for (change in listOf<(String) -> String>(
            { it.replace("127.0.0.1", "localhost") }, { it.replace(":34567", ":34568") },
            { it.replace("/auth/callback", "/callback") }, { "$it#fragment" },
            { "$it&state=duplicate" }, { it.replace("?state=", "?state=wrong") },
        )) {
            val a = ChatGptAuthorization(host, 34567)
            assertThrows(IllegalArgumentException::class.java) { a.receive(change(callback(a))) }
            assertEquals("oaiapp_synthetic", a.receive(callback(a)).clientId)
        }
    }
    @Test fun denialCancellationExpiryAndAccountBinding() {
        val denied = ChatGptAuthorization(host, 34567)
        assertThrows(IllegalStateException::class.java) { denied.receive(callback(denied, "error=access_denied")) }
        assertThrows(IllegalStateException::class.java) { denied.receive(callback(denied)) }
        val cancelled = ChatGptAuthorization(host, 34567)
        cancelled.cancel()
        assertThrows(IllegalStateException::class.java) { cancelled.receive(callback(cancelled)) }
        var time = 0L
        val expired = ChatGptAuthorization(host, 34567, nowMillis = { time })
        time = 180001
        assertThrows(IllegalStateException::class.java) { expired.receive(callback(expired)) }
        val returning = ChatGptAuthorization(host, 34567, "oaiapp_existing")
        assertFalse(query(returning.authorizationUri.rawQuery).containsKey("agent_name_hint"))
        assertThrows(IllegalArgumentException::class.java) { returning.receive(callback(returning)) }
        val same = ChatGptAuthorization(host, 34567, "oaiapp_existing")
        assertEquals("oaiapp_existing", same.receive(callback(same, "code=synthetic-code")).clientId)
    }
    @Test fun attemptsHaveIndependentRandomStateNonceAndVerifier() {
        val first = query(ChatGptAuthorization(host, 34567).authorizationUri.rawQuery)
        val second = query(ChatGptAuthorization(host, 34567).authorizationUri.rawQuery)
        for (key in listOf("state", "nonce", "code_challenge")) assertNotEquals(first[key], second[key])
    }
}
