package io.github.victorgabillon.sugarglider

import java.time.Instant
import javax.crypto.KeyGenerator
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ChatGptAccountTest {
    private val now = Instant.ofEpochSecond(1_800_000_000)
    private fun response(): JSONObject = JSONObject().put("token_type","Bearer").put("expires_in",3600)
        .put("access_token","synthetic-access").put("refresh_token","synthetic-refresh").put("id_token","synthetic-id")
        .put("scope","openid profile email offline_access resource.invoke chatgpt.tokens.use.direct")
    @Test fun takesScopesFromTokenResponseAndRotatesTogether() {
        val first = ChatGptTokenResponse.parse(response(),now=now)
        assertTrue(first.planUsage)
        val second = ChatGptTokenResponse.parse(response().put("refresh_token","rotated").also { it.remove("scope"); it.remove("id_token") },first,now.plusSeconds(1))
        assertEquals("rotated",second.refresh);assertEquals(first.scopes,second.scopes);assertEquals(now.epochSecond+3601,second.expiresAt)
        assertFalse(ChatGptTokenResponse.parse(response().put("scope","openid"),now=now).planUsage)
        assertThrows(IllegalArgumentException::class.java) { ChatGptTokenResponse.parse(response().put("expires_in","3600"),now=now) }
        assertThrows(IllegalArgumentException::class.java) { ChatGptTokenResponse.parse(response().put("token_type","mac"),now=now) }
    }
    @Test fun encryptedRecordsRoundTripAndSignOutKeepsIdentityOnly() {
        val account = ChatGptAccount("oaiapp_synthetic",ChatGptIdentity("subject","test@example.invalid","Test"),ChatGptTokenResponse.parse(response(),now=now))
        val key = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()
        val encrypted = AesGcmRecordCodec.encrypt(ChatGptAccountJson.encode(account),key)
        assertFalse(encrypted.toString(Charsets.ISO_8859_1).contains("synthetic-access"))
        val decoded = ChatGptAccountJson.decode(AesGcmRecordCodec.decrypt(encrypted,key))
        assertEquals(account.clientId,decoded.clientId);assertEquals(account.identity,decoded.identity);assertEquals(account.tokens?.refresh,decoded.tokens?.refresh)
        assertFalse(account.toString().contains("synthetic-access"));assertFalse(account.tokens.toString().contains("synthetic-refresh"))
        val signedOut = ChatGptAccountJson.decode(ChatGptAccountJson.encode(ChatGptAccount(account.clientId,account.identity,null)))
        assertNull(signedOut.tokens);assertEquals(account.identity,signedOut.identity)
        encrypted[encrypted.lastIndex] = (encrypted.last().toInt() xor 1).toByte()
        assertThrows(IllegalArgumentException::class.java) { AesGcmRecordCodec.decrypt(encrypted,key) }
    }
}
