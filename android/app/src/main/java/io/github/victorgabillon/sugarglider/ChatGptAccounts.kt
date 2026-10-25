package io.github.victorgabillon.sugarglider

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import java.io.File
import java.security.KeyStore
import java.security.MessageDigest
import java.time.Instant
import java.util.UUID
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import org.json.JSONArray
import org.json.JSONObject

/** Native credentials deliberately have no data-class diagnostic representation. */
internal class ChatGptTokens(val access: String?, val refresh: String?, val idToken: String, val scopes: Set<String>, val expiresAt: Long) {
    val planUsage: Boolean get() = access != null && setOf("resource.invoke", "chatgpt.tokens.use.direct").all(scopes::contains)
}
internal class ChatGptAccount(val clientId: String, val identity: ChatGptIdentity, val tokens: ChatGptTokens?)

internal object ChatGptAccountJson {
    fun encode(account: ChatGptAccount): ByteArray {
        val token = account.tokens
        val root = JSONObject().put("client_id", account.clientId).put("subject", account.identity.subject)
            .put("email", account.identity.email ?: JSONObject.NULL).put("name", account.identity.name ?: JSONObject.NULL)
            .put("tokens", if (token == null) JSONObject.NULL else JSONObject().put("access", token.access ?: JSONObject.NULL)
                .put("refresh", token.refresh ?: JSONObject.NULL).put("id_token", token.idToken)
                .put("scopes", JSONArray(token.scopes.sorted())).put("expires_at", token.expiresAt))
        return root.toString().toByteArray(Charsets.UTF_8).also { require(it.size <= 32_768) }
    }
    fun decode(bytes: ByteArray): ChatGptAccount {
        require(bytes.size in 2..32_768)
        val root = JSONObject(bytes.toString(Charsets.UTF_8))
        val identity = ChatGptIdentity(text(root,"subject",256), nullableText(root,"email",256), nullableText(root,"name",256))
        val token = if (root.isNull("tokens")) null else root.getJSONObject("tokens").let { t ->
            val scopes = t.getJSONArray("scopes")
            require(scopes.length() <= 16)
            val values = (0 until scopes.length()).map { scopes.get(it) }
            require(values.all { it is String && it.length in 1..100 && it.none(Char::isISOControl) })
            val expires = t.get("expires_at"); require(expires is Long || expires is Int)
            ChatGptTokens(nullableText(t,"access",16_384), nullableText(t,"refresh",16_384), text(t,"id_token",16_384), values.map { it as String }.toSet(), (expires as Number).toLong())
        }
        val clientId = text(root,"client_id",256)
        require(clientId.matches(Regex("oaiapp_[A-Za-z0-9_-]+")))
        return ChatGptAccount(clientId,identity,token)
    }
    fun text(value: JSONObject, key: String, maximum: Int): String {
        val raw = value.get(key)
        require(raw is String && raw.length in 1..maximum && raw.none(Char::isISOControl)) { "Invalid account record." }
        return raw
    }
    private fun nullableText(value: JSONObject, key: String, maximum: Int): String? = if (value.isNull(key)) null else text(value,key,maximum)
}

internal interface ChatGptAccounts {
    fun hostId(): String
    fun list(): List<ChatGptAccount>
    fun save(account: ChatGptAccount)
    fun pendingRegistration(): String?
    fun savePendingRegistration(clientId: String?)
}

/** Dedicated native files/key; never shares participant credentials or browser storage. */
internal class AndroidChatGptAccounts(context: Context) : ChatGptAccounts {
    private val directory = File(context.noBackupFilesDir, "chatgpt").apply { check(mkdirs() || isDirectory) }
    private val key: SecretKey by lazy {
        val alias = "sugarglider-chatgpt-accounts"
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias,null) as? SecretKey) ?: KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setRandomizedEncryptionRequired(true).build())
        }.generateKey()
    }
    @Synchronized override fun hostId(): String {
        val file = AtomicFile(File(directory,"host"))
        if (file.baseFile.exists()) {
            val value = file.openRead().use { bounded(it,100) }.toString(Charsets.US_ASCII)
            require(value == "urn:uuid:" + UUID.fromString(value.removePrefix("urn:uuid:")).toString())
            return value
        }
        val value = "urn:uuid:" + UUID.randomUUID()
        write(file,value.toByteArray(Charsets.US_ASCII))
        return value
    }
    @Synchronized override fun pendingRegistration(): String? {
        val file = AtomicFile(File(directory,"pending-client"))
        if (!file.baseFile.exists()) return null
        return file.openRead().use { bounded(it,256) }.toString(Charsets.US_ASCII).also { require(it.matches(Regex("oaiapp_[A-Za-z0-9_-]+"))) }
    }
    @Synchronized override fun savePendingRegistration(clientId: String?) {
        val file = AtomicFile(File(directory,"pending-client"))
        if (clientId == null) file.delete()
        else { require(clientId.length <= 256 && clientId.matches(Regex("oaiapp_[A-Za-z0-9_-]+"))); write(file,clientId.toByteArray(Charsets.US_ASCII)) }
    }
    @Synchronized override fun list(): List<ChatGptAccount> {
        val files = directory.listFiles { f -> f.name.matches(Regex("[a-f0-9]{64}\\.enc(?:\\.bak)?")) } ?: error("Account storage unavailable.")
        val names = files.map { it.name.removeSuffix(".bak") }.distinct().sorted()
        require(names.size <= 4)
        return names.map { name ->
            val file = AtomicFile(File(directory,name))
            val bytes = file.openRead().use { bounded(it,65_536) }
            ChatGptAccountJson.decode(AesGcmRecordCodec.decrypt(bytes,key)).also { require(filename(it.clientId) == name) }
        }
    }
    @Synchronized override fun save(account: ChatGptAccount) {
        val accounts = list()
        val existing = accounts.find { it.clientId == account.clientId }
        require(existing == null || existing.identity.subject == account.identity.subject) { "Account identity changed." }
        require(existing != null || accounts.size < 4) { "At most four ChatGPT registrations can be retained." }
        write(AtomicFile(File(directory,filename(account.clientId))), AesGcmRecordCodec.encrypt(ChatGptAccountJson.encode(account),key))
    }
    private fun filename(clientId: String): String = MessageDigest.getInstance("SHA-256").digest(clientId.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) } + ".enc"
    private fun bounded(input: java.io.InputStream, maximum: Int): ByteArray {
        val output = java.io.ByteArrayOutputStream()
        val buffer = ByteArray(4096)
        while (true) { val n = input.read(buffer); if (n < 0) break; require(output.size()+n <= maximum); output.write(buffer,0,n) }
        return output.toByteArray()
    }
    private fun write(file: AtomicFile, value: ByteArray) {
        val output = file.startWrite()
        try { output.write(value); file.finishWrite(output) }
        catch (error: Exception) { file.failWrite(output); throw error }
    }
}

internal object ChatGptTokenResponse {
    fun parse(value: JSONObject, prior: ChatGptTokens? = null, now: Instant = Instant.now()): ChatGptTokens {
        require(ChatGptAccountJson.text(value,"token_type",20).equals("Bearer",ignoreCase=true))
        val expires = value.get("expires_in")
        require((expires is Int || expires is Long) && (expires as Number).toLong() in 1..604_800)
        val scopes = if (value.has("scope")) ChatGptAccountJson.text(value,"scope",1600).split(' ').filter(String::isNotBlank).toSet()
            else prior?.scopes ?: emptySet()
        require(scopes.size <= 16)
        val access = if (value.has("access_token")) ChatGptAccountJson.text(value,"access_token",16_384) else null
        val refresh = if (value.has("refresh_token")) ChatGptAccountJson.text(value,"refresh_token",16_384) else prior?.refresh
        val id = if (value.has("id_token")) ChatGptAccountJson.text(value,"id_token",16_384) else prior?.idToken ?: error("Identity token missing.")
        require(access != null || "chatgpt.tokens.use.direct" !in scopes)
        return ChatGptTokens(access, refresh, id, scopes, now.epochSecond + (expires as Number).toLong())
    }
}
