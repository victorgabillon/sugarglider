package io.github.victorgabillon.sugarglider

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.KeyPairGenerator
import java.security.Signature
import java.security.interfaces.RSAPublicKey
import java.time.Instant
import java.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ChatGptConnectionTest {
    private class Memory : ChatGptAccounts {
        val saved = linkedMapOf<String,ChatGptAccount>()
        var pending: String? = null
        override fun hostId() = "urn:uuid:871494d4-b81b-4523-9626-3547cff2e4cc"
        override fun list() = saved.values.toList()
        override fun save(account: ChatGptAccount) { saved[account.clientId] = account }
        override fun pendingRegistration() = pending
        override fun savePendingRegistration(clientId: String?) { pending = clientId }
    }
    private class Reply(url: URL, private val body: String, private val type: String = "application/json") : HttpURLConnection(url) {
        val written = ByteArrayOutputStream()
        override fun connect() = Unit
        override fun disconnect() = Unit
        override fun usingProxy() = false
        override fun getResponseCode() = 200
        override fun getContentType() = type
        override fun getInputStream() = ByteArrayInputStream(body.toByteArray())
        override fun getOutputStream() = written
    }
    private val pair = KeyPairGenerator.getInstance("RSA").apply { initialize(2048) }.generateKeyPair()
    private val time = Instant.ofEpochSecond(1_800_000_000)
    private fun b64(bytes: ByteArray) = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)
    private fun signed(subject: String = "one", nonce: String = "nonce"): String {
        val h = JSONObject().put("alg","RS256").put("kid","test")
        val c = JSONObject().put("iss","https://auth.openai.com").put("aud","oaiapp_test").put("sub",subject).put("nonce",nonce).put("iat",time.epochSecond).put("exp",time.epochSecond+600)
        val message = b64(h.toString().toByteArray()) + "." + b64(c.toString().toByteArray())
        val sig = Signature.getInstance("SHA256withRSA").apply { initSign(pair.private);update(message.toByteArray()) }.sign()
        return message + "." + b64(sig)
    }
    private fun jwks(): String {
        val key = pair.public as RSAPublicKey
        fun unsigned(v: java.math.BigInteger) = v.toByteArray().dropWhile { it == 0.toByte() }.toByteArray()
        return JSONObject().put("keys",JSONArray().put(JSONObject().put("kid","test").put("kty","RSA").put("n",b64(unsigned(key.modulus))).put("e",b64(unsigned(key.publicExponent))))).toString()
    }
    private fun response(idToken: String = signed()): JSONObject = JSONObject().put("token_type","Bearer").put("expires_in",3600)
        .put("access_token","synthetic-access").put("refresh_token","synthetic-refresh").put("id_token",idToken)
        .put("scope","openid profile email offline_access resource.invoke chatgpt.tokens.use.direct")
    private fun discovery(): String = JSONObject().put("issuer","https://auth.openai.com").put("jwks_uri",ChatGptHttp.JWKS).put("token_endpoint",ChatGptHttp.TOKEN).put("revocation_endpoint",ChatGptHttp.REVOKE).toString()
    private fun code() = ChatGptCode("oaiapp_test","synthetic-code","synthetic-verifier","http://127.0.0.1:12345/auth/callback","nonce")
    private fun service(token: () -> JSONObject = { response() }, requests: MutableList<Reply> = mutableListOf()): ChatGptHttp = ChatGptHttp(ConnectionFactory { url ->
        Reply(url,when(url.toString()) {
            ChatGptHttp.DISCOVERY -> discovery()
            ChatGptHttp.JWKS -> jwks()
            ChatGptHttp.TOKEN -> token().toString()
            ChatGptHttp.REVOKE -> ""
            ChatGptHttp.MODELS -> """{"models":[{"slug":"available","display_name":"Available","visibility":"list"},{"slug":"hidden","display_name":"Hidden","visibility":"hidden"}]}"""
            else -> error("Unexpected endpoint")
        }).also(requests::add)
    })
    @Test fun verifiesConnectionDiscoversModelsAndSignOutKeepsRegistration() {
        val memory = Memory();val requests = mutableListOf<Reply>()
        val connection = ChatGptConnection(memory,service(requests=requests)) { time }
        connection.acceptCode(code())
        assertNull(memory.pending);assertEquals("one",memory.saved.getValue("oaiapp_test").identity.subject)
        val status = connection.models()
        assertEquals(1,status.getJSONArray("models").length())
        assertEquals("available",status.getJSONArray("models").getJSONObject(0).getString("id"))
        assertFalse(status.toString().contains("synthetic-access"))
        assertTrue(connection.signOut().getBoolean("remote_revocation_confirmed"))
        assertNull(memory.saved.getValue("oaiapp_test").tokens)
        assertEquals("one",memory.saved.getValue("oaiapp_test").identity.subject)
        assertEquals(ChatGptFailureKind.AUTH_EXPIRED,assertThrows(ChatGptException::class.java) { connection.models() }.kind)
        assertEquals(1,requests.count { it.url.toString() == ChatGptHttp.REVOKE })
    }
    @Test fun invalidIdentityCannotReplaceExistingRegistration() {
        val memory = Memory()
        memory.save(ChatGptAccount("oaiapp_test",ChatGptIdentity("one",null,null),null))
        val connection = ChatGptConnection(memory,service(token={response(signed(subject="other"))})) { time }
        assertThrows(IllegalArgumentException::class.java) { connection.acceptCode(code(),"oaiapp_test") }
        assertEquals("one",memory.saved.getValue("oaiapp_test").identity.subject);assertNull(memory.saved.getValue("oaiapp_test").tokens)
        val invalid = ChatGptConnection(memory,service(token={response(signed(nonce="wrong"))})) { time }
        assertThrows(IllegalArgumentException::class.java) { invalid.acceptCode(code()) }
        assertEquals("oaiapp_test",memory.pending)
    }
    @Test fun refreshRotationStaysWithItsClientAndGrantedScopes() {
        val memory = Memory();val requests = mutableListOf<Reply>()
        val prior = ChatGptTokens("old-access","old-refresh",signed(),setOf("resource.invoke","chatgpt.tokens.use.direct"),time.epochSecond)
        memory.save(ChatGptAccount("oaiapp_test",ChatGptIdentity("one",null,null),prior))
        val connection = ChatGptConnection(memory,service(token={ response().put("refresh_token","rotated").also { it.remove("id_token");it.remove("scope") } },requests=requests)) { time }
        connection.select("oaiapp_test");connection.models()
        assertEquals("rotated",memory.saved.getValue("oaiapp_test").tokens!!.refresh)
        assertEquals(prior.scopes,memory.saved.getValue("oaiapp_test").tokens!!.scopes)
        val form = requests.single { it.url.toString() == ChatGptHttp.TOKEN }.written.toString("UTF-8")
        assertTrue(form.contains("client_id=oaiapp_test"));assertFalse(form.contains("dynamic_agent_client"))
        assertEquals("Bearer synthetic-access",requests.single { it.url.toString() == ChatGptHttp.MODELS }.getRequestProperty("Authorization"))
    }
    @Test fun cancellationDuringTokenExchangeCannotCommitCredentials() {
        val memory = Memory()
        lateinit var connection: ChatGptConnection
        connection = ChatGptConnection(memory,service(token={ connection.cancel();response() })) { time }
        assertEquals(ChatGptFailureKind.CANCELLED,assertThrows(ChatGptException::class.java) { connection.acceptCode(code()) }.kind)
        assertTrue(memory.saved.isEmpty())
    }
    @Test fun metadataFailureRetainsIssuedRegistrationWithoutAuthorizingAnAccount() {
        val memory = Memory()
        val connection = ChatGptConnection(memory,ChatGptHttp(ConnectionFactory {
            throw java.net.UnknownHostException("secret callback or credential")
        })) { time }
        assertThrows(ChatGptException::class.java) { connection.acceptCode(code()) }
        assertEquals("oaiapp_test",memory.pending)
        assertTrue(memory.saved.isEmpty())
        val status = connection.status()
        assertEquals(0,status.getJSONArray("accounts").length())
        assertEquals("discovery",status.getJSONObject("last_failure").getString("stage"))
        assertEquals("dns",status.getJSONObject("last_failure").getString("network_cause"))
        assertFalse(status.toString().contains("secret"))
    }
    @Test fun inferencePayloadBoundsOutputAndResearchWithoutAssumingModelCapabilities() {
        val schema = JSONObject().put("type","object").put("properties",JSONObject())
        val payload = adventureChatGptPayload("account-visible-model","instructions","synthetic description",true,schema)
        assertEquals("account-visible-model",payload.getString("model"))
        assertFalse(payload.getBoolean("store"));assertTrue(payload.getBoolean("stream"))
        assertEquals(16_384,payload.getInt("max_output_tokens"));assertEquals(4,payload.getInt("max_tool_calls"))
        assertEquals(1,payload.getJSONArray("tools").length())
        assertEquals("web_search",payload.getJSONArray("tools").getJSONObject(0).getString("type"))
        val format = payload.getJSONObject("text").getJSONObject("format")
        assertEquals("json_schema",format.getString("type"));assertTrue(format.getBoolean("strict"))
        assertEquals(schema.toString(),format.getJSONObject("schema").toString())
        for (key in listOf("authorization","access_token","refresh_token","api_key","previous_response_id","conversation","background")) assertFalse(payload.has(key))
    }
    @Test fun inferenceCanOmitUnsupportedOptionalResearchAndSchema() {
        val payload = adventureChatGptPayload("another-visible-model","instructions","synthetic description",false,null)
        assertFalse(payload.has("tools"));assertFalse(payload.has("max_tool_calls"));assertFalse(payload.has("text"))
        assertEquals(16_384,payload.getInt("max_output_tokens"))
    }

}
