package io.github.victorgabillon.sugarglider

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ChatGptHttpTest {
    private class Response(url: URL, val status: Int = 200, val body: String = "{}", val mime: String = "application/json") : HttpURLConnection(url) {
        val written = ByteArrayOutputStream()
        var closed = false
        override fun connect() = Unit
        override fun disconnect() { closed = true }
        override fun usingProxy() = false
        override fun getResponseCode() = status
        override fun getContentType() = mime
        override fun getInputStream() = ByteArrayInputStream(body.toByteArray())
        override fun getErrorStream() = ByteArrayInputStream(body.toByteArray())
        override fun getOutputStream() = written
    }
    @Test fun usesOnlyPublicEndpointsAndNoRedirects() {
        val rows = mutableListOf<Response>()
        val http = ChatGptHttp(ConnectionFactory { url -> Response(url).also(rows::add) })
        ChatGptCall().use { http.models(it,"synthetic-token") }
        assertEquals(ChatGptHttp.MODELS, rows.single().url.toString())
        assertEquals("Bearer synthetic-token", rows.single().getRequestProperty("Authorization"))
        assertFalse(rows.single().instanceFollowRedirects)
        assertFalse(rows.single().useCaches)
        assertTrue(rows.single().closed)
        assertThrows(ChatGptException::class.java) { ChatGptHttp(ConnectionFactory { url -> Response(url,302) }).models(ChatGptCall(),"synthetic-token") }
    }
    @Test fun protectsTokensAndClassifiesErrorsWithoutProviderMessages() {
        for ((status,kind) in listOf(401 to ChatGptFailureKind.AUTH_EXPIRED,403 to ChatGptFailureKind.AUTH_EXPIRED,429 to ChatGptFailureKind.USAGE_LIMIT,400 to ChatGptFailureKind.UNSUPPORTED,500 to ChatGptFailureKind.NETWORK)) {
            val failure = assertThrows(ChatGptException::class.java) { ChatGptHttp(ConnectionFactory { url -> Response(url,status,"secret provider details") }).models(ChatGptCall(),"synthetic-token") }
            assertEquals(kind,failure.kind); assertFalse(failure.toString().contains("secret"))
        }
        val failedRefresh = assertThrows(ChatGptException::class.java) { ChatGptHttp(ConnectionFactory { url -> Response(url,400,"""{"error":"invalid_grant"}""") }).exchange(ChatGptCall(),"synthetic-form") }
        assertEquals(ChatGptFailureKind.AUTH_EXPIRED,failedRefresh.kind)
    }
    @Test fun boundsInputAndCancelsWithoutFallback() {
        val huge = ChatGptHttp(ConnectionFactory { url -> Response(url,body="a".repeat(262_145)) })
        assertThrows(ChatGptException::class.java) { huge.models(ChatGptCall(),"synthetic-token") }
        val call = ChatGptCall(); call.close()
        assertEquals(ChatGptFailureKind.CANCELLED,assertThrows(ChatGptException::class.java) { ChatGptHttp(ConnectionFactory { url -> Response(url) }).models(call,"synthetic-token") }.kind)
        val offline = ChatGptHttp(ConnectionFactory { throw java.io.IOException("offline") })
        assertEquals(ChatGptFailureKind.NETWORK,assertThrows(ChatGptException::class.java) { offline.models(ChatGptCall(),"synthetic-token") }.kind)
        assertThrows(IllegalArgumentException::class.java) { ChatGptHttp().infer(ChatGptCall(),"synthetic",JSONObject().put("stream",false).put("store",true)) }
    }
}
