package io.github.victorgabillon.sugarglider

import java.net.URI
import java.time.Instant
import org.json.JSONArray
import org.json.JSONObject

/** One Activity-owned native connection. Call blocking methods on its dedicated executor. */
internal class ChatGptConnection(
    private val accounts: ChatGptAccounts,
    private val http: ChatGptHttp = ChatGptHttp(),
    private val now: () -> Instant = Instant::now,
) {
    private val lock = Any()
    private var generation = 0L
    private var selectedId: String? = null
    private var activeCall: ChatGptCall? = null
    private var listener: ChatGptLoopback? = null
    private val blockedAccounts = mutableSetOf<String>()
    private var catalog: List<ChatGptModel> = emptyList()
    private var lastFailure: ChatGptException? = null

    fun status(): JSONObject {
        val saved = accounts.list()
        synchronized(lock) {
            if (selectedId == null) selectedId = saved.firstOrNull { it.tokens != null }?.clientId ?: saved.firstOrNull()?.clientId
            val rows = JSONArray()
            saved.forEach { account -> rows.put(JSONObject().put("id",account.clientId)
                .put("label",account.identity.email ?: account.identity.name ?: "ChatGPT account")
                .put("connected",account.tokens != null && account.clientId !in blockedAccounts)
                .put("plan_usage",account.tokens?.planUsage == true && account.clientId !in blockedAccounts)) }
            return JSONObject().put("accounts",rows).put("selected_account",selectedId ?: JSONObject.NULL)
                .put("models",JSONArray(catalog.map { JSONObject().put("id",it.slug).put("label",it.label) }))
                .put("last_failure",lastFailure?.diagnostic() ?: JSONObject.NULL)
                .put("model_catalog_bytes",http.modelCatalogBytes ?: JSONObject.NULL)
        }
    }

    fun select(clientId: String) {
        require(accounts.list().any { it.clientId == clientId })
        cancel()
        synchronized(lock) { selectedId = clientId; catalog = emptyList(); lastFailure = null }
    }

    fun signIn(clientId: String?, expectedEpoch: Long? = null,
        awaitForeground: (Long, () -> Boolean) -> Unit, openBrowser: (URI) -> Unit): JSONObject = operation(expectedEpoch) { call, owned ->
        val prior = clientId?.let { id -> accounts.list().single { it.clientId == id } }
        val pending = if (clientId == null) accounts.pendingRegistration() else null
        val callback = ChatGptLoopback()
        synchronized(lock) { requireCurrent(owned); listener = callback }
        try {
            val transaction = ChatGptAuthorization(accounts.hostId(), callback.port, prior?.clientId ?: pending)
            val browserDeadline = System.nanoTime() + 180_000_000_000L
            openBrowser(transaction.authorizationUri)
            val code = callback.awaitCode(transaction,call::cancelled)
            callback.close()
            synchronized(lock) { if (listener === callback) listener = null }
            rememberRegistration(code,prior,owned)
            // The system browser is usually still foreground at callback time.
            // Use the remaining browser-phase budget, not a new indefinite wait.
            awaitForeground(((browserDeadline-System.nanoTime())/1_000_000).coerceIn(0,180_000),call::cancelled)
            connect(code,prior,call,owned)
            status()
        } finally {
            callback.close()
            synchronized(lock) { if (listener === callback) listener = null }
        }
    }

    /** Separate from browser I/O so the full token validation boundary is unit-testable. */
    internal fun acceptCode(code: ChatGptCode, priorClientId: String? = null): JSONObject = operation { call, owned ->
        val prior = priorClientId?.let { id -> accounts.list().single { it.clientId == id } }
        rememberRegistration(code,prior,owned)
        connect(code,prior,call,owned)
        status()
    }

    private fun rememberRegistration(code: ChatGptCode, prior: ChatGptAccount?, owned: Long) {
        // The issued public registration survives a later metadata/network
        // failure. It is not a token and never authorizes an account by itself.
        synchronized(lock) {
            requireCurrent(owned)
            if (prior == null) accounts.savePendingRegistration(code.clientId)
        }
    }

    private fun connect(code: ChatGptCode, prior: ChatGptAccount?, call: ChatGptCall, owned: Long) {
        validateDiscovery(call)
        val tokens = ChatGptTokenResponse.parse(http.exchange(call,code.tokenForm()),now=now())
        val identity = ChatGptIdentityVerifier.verify(tokens.idToken,code.clientId,code.nonce,http.jwks(call),now())
        require(prior == null || prior.clientId == code.clientId && prior.identity.subject == identity.subject) { "ChatGPT account changed." }
        synchronized(lock) {
            requireCurrent(owned)
            accounts.save(ChatGptAccount(code.clientId,identity,tokens))
            if (accounts.pendingRegistration() == code.clientId) accounts.savePendingRegistration(null)
            selectedId = code.clientId
            blockedAccounts.remove(code.clientId)
            catalog = emptyList()
        }
    }

    fun models(expectedEpoch: Long? = null): JSONObject = operation(expectedEpoch) { call, owned ->
        val account = authorized(call,owned)
        val response = http.models(call,account.tokens!!.access!!)
        val models = try {
            val rows = response.getJSONArray("models")
            require(rows.length() <= 100)
            (0 until rows.length()).map { rows.getJSONObject(it) }.filter { it.optString("visibility") == "list" }.map {
                ChatGptModel(ChatGptAccountJson.text(it,"slug",128),ChatGptAccountJson.text(it,"display_name",256)).also { model ->
                    require(model.slug.matches(Regex("[A-Za-z0-9._-]+")))
                }
            }.also { require(it.map { model -> model.slug }.distinct().size == it.size) }
        } catch (_: Exception) {
            throw ChatGptException(ChatGptFailureKind.INVALID_RESPONSE,ChatGptHttpStage.MODEL_CATALOG,
                responseIssue=ChatGptResponseIssue.CATALOG_SCHEMA)
        }
        synchronized(lock) { requireCurrent(owned); catalog = models }
        status()
    }

    fun infer(model: String, instructions: String, input: String, research: Boolean, schema: JSONObject?, expectedEpoch: Long? = null): JSONObject = operation(expectedEpoch) { call, owned ->
        require(instructions.length in 1..24_576 && input.length in 1..32_768)
        val account = authorized(call,owned)
        synchronized(lock) { require(catalog.any { it.slug == model }) { "Select an available ChatGPT model." } }
        val payload = adventureChatGptPayload(model,instructions,input,research,schema)
        val started = System.nanoTime()
        val answer = http.infer(call,account.tokens!!.access!!,payload)
        synchronized(lock) { requireCurrent(owned) }
        JSONObject().put("text",answer.text).put("usage",answer.usage).put("citations",answer.citations)
            .put("researched",research && answer.researched).put("elapsed_ms",(System.nanoTime()-started)/1_000_000)
    }

    fun signOut(): JSONObject {
        cancel()
        val id = synchronized(lock) { selectedId } ?: return status()
        val account = accounts.list().single { it.clientId == id }
        synchronized(lock) { blockedAccounts.add(id); catalog = emptyList(); lastFailure = null }
        var confirmed = account.tokens?.refresh == null
        try {
            val refresh = account.tokens?.refresh
            if (refresh != null) ChatGptCall().use { call ->
                validateDiscovery(call)
                http.revoke(call,ChatGptAuthorization.form(mapOf("client_id" to id,"token" to refresh,"token_type_hint" to "refresh_token")))
                confirmed = true
            }
        } catch (_: Exception) { confirmed = false }
        finally {
            val current = accounts.list().single { it.clientId == id }
            if (current.tokens?.refresh == account.tokens?.refresh && current.tokens?.access == account.tokens?.access) accounts.save(ChatGptAccount(id,account.identity,null))
        }
        return status().put("remote_revocation_confirmed",confirmed)
    }

    /** Immediate even while the executor is blocked in browser callback or HTTP. */
    fun cancel() {
        synchronized(lock) {
            generation += 1
            activeCall?.close()
            runCatching { listener?.close() }
        }
    }

    private fun authorized(call: ChatGptCall, owned: Long): ChatGptAccount {
        val id = synchronized(lock) { requireCurrent(owned); selectedId?.takeUnless(blockedAccounts::contains) } ?: throw ChatGptException(ChatGptFailureKind.AUTH_EXPIRED)
        var account = accounts.list().single { it.clientId == id }
        val before = account.tokens ?: throw ChatGptException(ChatGptFailureKind.AUTH_EXPIRED)
        if (before.expiresAt <= now().epochSecond + 60) {
            val refresh = before.refresh ?: throw ChatGptException(ChatGptFailureKind.AUTH_EXPIRED)
            val next = ChatGptTokenResponse.parse(http.exchange(call,ChatGptAuthorization.form(mapOf("grant_type" to "refresh_token","client_id" to id,"refresh_token" to refresh,"resource" to ChatGptAuthorization.RESOURCE))),before,now())
            val identity = if (next.idToken != before.idToken) ChatGptIdentityVerifier.verify(next.idToken,id,null,http.jwks(call),now()) else account.identity
            require(identity.subject == account.identity.subject) { "ChatGPT account changed." }
            account = ChatGptAccount(id,identity,next)
            synchronized(lock) { requireCurrent(owned); accounts.save(account) }
        }
        if (account.tokens?.planUsage != true) throw ChatGptException(ChatGptFailureKind.UNSUPPORTED)
        return account
    }
    private fun validateDiscovery(call: ChatGptCall) {
        val metadata = http.discovery(call)
        require(metadata.optString("issuer") == "https://auth.openai.com" && metadata.optString("jwks_uri") == ChatGptHttp.JWKS && metadata.optString("token_endpoint") == ChatGptHttp.TOKEN && metadata.optString("revocation_endpoint") == ChatGptHttp.REVOKE) { "Unsupported ChatGPT authorization metadata." }
    }
    private fun requireCurrent(owned: Long) { if (generation != owned) throw ChatGptException(ChatGptFailureKind.CANCELLED) }
    fun epoch(): Long = synchronized(lock) { generation }

    private fun <T> operation(expectedEpoch: Long? = null, run: (ChatGptCall,Long) -> T): T {
        val call = ChatGptCall()
        val owned = synchronized(lock) { if (expectedEpoch != null) requireCurrent(expectedEpoch); check(activeCall == null) { "A ChatGPT operation is still finishing." }; activeCall = call; lastFailure = null; generation }
        try { return run(call,owned) }
        catch (error: ChatGptException) {
            synchronized(lock) { if (generation == owned && error.kind != ChatGptFailureKind.CANCELLED) lastFailure = error }
            throw error
        }
        finally { call.close(); synchronized(lock) { if (activeCall === call) activeCall = null } }
    }
}
internal data class ChatGptModel(val slug: String, val label: String)

// ChatGPT plan sharing rejects server-side token/tool caps. Bound the foreground
// stream locally; do not send fields supported only by other Responses routes.
internal fun adventureChatGptPayload(
    model: String,
    instructions: String,
    input: String,
    research: Boolean,
    schema: JSONObject?,
): JSONObject {
    val payload = JSONObject().put("model",model).put("store",false).put("stream",true)
        .put("instructions",instructions).put("input",JSONArray().put(JSONObject().put("role","user").put("content",input)))
    if (research) payload.put("tools",JSONArray().put(JSONObject().put("type","web_search")))
    if (schema != null) payload.put("text",JSONObject().put("format",JSONObject().put("type","json_schema")
        .put("name","sugarglider_adventure").put("strict",true).put("schema",schema)))
    return payload
}
