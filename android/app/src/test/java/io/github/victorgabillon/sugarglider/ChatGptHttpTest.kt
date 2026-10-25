package io.github.victorgabillon.sugarglider

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ChatGptHttpTest {
    private class Response(url: URL, val status: Int = 200, val body: String = "{}", val mime: String? = "application/json") : HttpURLConnection(url) {
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
    @Test fun acceptsOnlyCompletedSseWithDeclaredOrMissingStreamType() {
        val body = "data: " + JSONObject().put("type","response.completed").put("response",JSONObject()
            .put("status","completed").put("output",org.json.JSONArray().put(JSONObject()
                .put("type","message").put("role","assistant").put("status","completed")
                .put("content",org.json.JSONArray().put(JSONObject().put("type","output_text").put("text","synthetic answer")))))) + "\n\n"
        val terminal = JSONObject(body.removePrefix("data: ").trim())
        val message = terminal.getJSONObject("response").getJSONArray("output").getJSONObject(0)
        terminal.getJSONObject("response").put("output",org.json.JSONArray())
        val itemStream = "data: " + JSONObject().put("type","response.output_item.done").put("output_index",0).put("item",message) + "\n\n" + "data: $terminal\n\n"
        for (mime in listOf("text/event-stream; charset=utf-8",null)) {
            for (stream in listOf(body,itemStream)) {
                val http = ChatGptHttp(ConnectionFactory { url -> Response(url,body=stream,mime=mime) })
                val result = http.infer(ChatGptCall(),"synthetic-token",adventureChatGptPayload("visible-model","instructions","synthetic",false,null))
                assertEquals("synthetic answer",result.text)
            }
        }
        val explicitWrongType = ChatGptHttp(ConnectionFactory { url -> Response(url,body=body,mime="application/json") })
        val failure = assertThrows(ChatGptException::class.java) {
            explicitWrongType.infer(ChatGptCall(),"synthetic-token",adventureChatGptPayload("visible-model","instructions","synthetic",false,null))
        }
        assertEquals(ChatGptResponseIssue.CONTENT_TYPE,failure.responseIssue)
    }
    @Test fun absentStreamTypeCannotAcceptHtmlJsonDeltasOrIdentityDocuments() {
        for (body in listOf("<html>not an answer</html>","""{"status":"completed","output":[]}""",
            "data: {\"type\":\"response.output_text.delta\",\"delta\":\"partial\"}\n\n")) {
            val http = ChatGptHttp(ConnectionFactory { url -> Response(url,body=body,mime=null) })
            val failure = assertThrows(ChatGptException::class.java) {
                http.infer(ChatGptCall(),"synthetic-token",adventureChatGptPayload("visible-model","instructions","synthetic",false,null))
            }
            assertEquals(ChatGptFailureKind.INVALID_RESPONSE,failure.kind)
            assertEquals(ChatGptHttpStage.INFERENCE,failure.stage)
        }
        val identity = ChatGptHttp(ConnectionFactory { url -> Response(url,mime=null) })
        assertEquals(ChatGptResponseIssue.CONTENT_TYPE,assertThrows(ChatGptException::class.java) { identity.discovery(ChatGptCall()) }.responseIssue)
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
            assertEquals(ChatGptHttpStage.MODEL_CATALOG,failure.stage)
            assertFalse(failure.diagnostic().toString().contains("secret"))
        }
        val failedRefresh = assertThrows(ChatGptException::class.java) { ChatGptHttp(ConnectionFactory { url -> Response(url,400,"""{"error":"invalid_grant"}""") }).exchange(ChatGptCall(),"synthetic-form") }
        assertEquals(ChatGptFailureKind.AUTH_EXPIRED,failedRefresh.kind)
        assertEquals(ChatGptHttpStage.TOKEN_EXCHANGE,failedRefresh.stage)
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
    @Test fun browserTimeDoesNotConsumeTheSingleBoundedHttpBudget() {
        var elapsed = 0L
        val call = ChatGptCall { elapsed }
        elapsed = 179_000_000_000L
        assertFalse(call.cancelled())
        call.beginNetwork()
        elapsed += 119_000_000_000L
        assertFalse(call.cancelled())
        call.beginNetwork() // Subsequent requests cannot reset the shared budget.
        elapsed += 1_000_000_000L
        assertTrue(call.cancelled())
        assertThrows(ChatGptException::class.java) { call.beginNetwork() }
        val cancelled = ChatGptCall { elapsed }; cancelled.close()
        assertTrue(cancelled.cancelled())
        assertThrows(ChatGptException::class.java) { cancelled.beginNetwork() }
    }
    @Test fun networkDiagnosticsContainOnlyFixedEnums() {
        for ((cause, expected) in listOf(
            java.net.UnknownHostException("secret callback token") to ChatGptNetworkCause.DNS,
            javax.net.ssl.SSLHandshakeException("secret callback token") to ChatGptNetworkCause.TLS,
            java.net.SocketTimeoutException("secret callback token") to ChatGptNetworkCause.TIMEOUT,
            java.net.ConnectException("secret callback token") to ChatGptNetworkCause.CONNECT,
            java.io.IOException("secret callback token") to ChatGptNetworkCause.IO,
        )) {
            val http = ChatGptHttp(ConnectionFactory { throw cause })
            val failure = assertThrows(ChatGptException::class.java) { http.discovery(ChatGptCall()) }
            assertEquals(ChatGptHttpStage.DISCOVERY,failure.stage)
            assertEquals(expected,failure.networkCause)
            assertEquals(setOf("kind","stage","network_cause","response_issue","rejection"),failure.diagnostic().keys().asSequence().toSet())
            assertFalse(failure.diagnostic().toString().contains("secret"))
            assertNull(failure.cause)
        }
    }
    @Test fun rejectionDiagnosticsRetainOnlyKnownCodesAndParameters() {
        for ((code,parameter,expectedCode,expectedParameter) in listOf(
            listOf("subscription_sharing_unsupported_capability","max_output_tokens","subscription_sharing_unsupported_capability","max_output_tokens"),
            listOf("invalid_json_schema","text.format.schema","invalid_json_schema","text.format.schema"),
            listOf("secret-token","secret-token","other","other"),
        )) {
            val body = JSONObject().put("error",JSONObject().put("code",code).put("param",parameter).put("message","secret-token"))
            val http = ChatGptHttp(ConnectionFactory { url -> Response(url,400,body.toString()) })
            val failure = assertThrows(ChatGptException::class.java) { http.models(ChatGptCall(),"synthetic-token") }
            val rejection = failure.diagnostic().getJSONObject("rejection")
            assertEquals(400,rejection.getInt("http_status"))
            assertEquals(expectedCode,rejection.getString("code"))
            assertEquals(expectedParameter,rejection.getString("parameter"))
            assertFalse(failure.diagnostic().toString().contains("secret-token"))
        }
        val detail = ChatGptRejection.parse(400,JSONObject().put("detail","secret-token")).json()
        assertEquals("other",detail.getString("code"));assertEquals("other",detail.getString("parameter"))
        assertFalse(detail.toString().contains("secret-token"))
    }
    @Test fun boundsRichCatalogMetadataSeparatelyAndClassifiesDecodeFailures() {
        val catalog = JSONObject().put("models",org.json.JSONArray()).put("metadata","x".repeat(300_000)).toString()
        val http = ChatGptHttp(ConnectionFactory { url -> Response(url,body=catalog) })
        assertEquals(0,http.models(ChatGptCall(),"synthetic-token").getJSONArray("models").length())
        assertEquals(catalog.toByteArray(Charsets.UTF_8).size,http.modelCatalogBytes)
        val identityLimit = assertThrows(ChatGptException::class.java) { http.discovery(ChatGptCall()) }
        assertEquals(ChatGptResponseIssue.BODY_TOO_LARGE,identityLimit.responseIssue)
        for ((reply,issue) in listOf(
            Response(URL(ChatGptHttp.MODELS),body="x".repeat(1_048_577)) to ChatGptResponseIssue.BODY_TOO_LARGE,
            Response(URL(ChatGptHttp.MODELS),body="not-json") to ChatGptResponseIssue.JSON_SYNTAX,
            Response(URL(ChatGptHttp.MODELS),mime="text/html") to ChatGptResponseIssue.CONTENT_TYPE,
        )) {
            val failure = assertThrows(ChatGptException::class.java) { ChatGptHttp(ConnectionFactory { reply }).models(ChatGptCall(),"synthetic-token") }
            assertEquals(issue,failure.responseIssue)
            assertEquals(ChatGptHttpStage.MODEL_CATALOG,failure.stage)
        }
    }
}
