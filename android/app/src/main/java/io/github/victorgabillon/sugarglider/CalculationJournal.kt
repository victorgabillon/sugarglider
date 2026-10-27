package io.github.victorgabillon.sugarglider

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import java.io.File
import java.security.KeyStore
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import org.json.JSONObject

/** One encrypted, backup-excluded progress receipt; never an executable job. */
internal class CalculationJournal(context: Context) {
    private val file = AtomicFile(File(context.noBackupFilesDir, "calculation.enc"))
    private val key: SecretKey by lazy {
        val alias = "sugarglider-calculation-journal"
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey) ?: KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true).build())
        }.generateKey()
    }
    @Synchronized fun save(value: JSONObject) {
        if (value.getString("state") in setOf("completed", "cancelled")) { file.delete(); return }
        val bytes = AesGcmRecordCodec.encrypt(value.toString().toByteArray(Charsets.UTF_8), key)
        val output = file.startWrite()
        try { output.write(bytes); file.finishWrite(output) }
        catch (error: Exception) { file.failWrite(output); throw error }
    }
    @Synchronized fun forget(id: String): Boolean {
        if (recovery()?.getString("operation_id") != id) return false
        file.delete(); return !file.baseFile.exists()
    }
    @Synchronized fun recovery(): JSONObject? = runCatching {
        if (!file.baseFile.exists()) return null
        val bytes = file.openRead().use { input ->
            val output = java.io.ByteArrayOutputStream()
            val buffer = ByteArray(4096)
            while (true) {
                val count = input.read(buffer); if (count < 0) break
                require(output.size() + count <= 65_536); output.write(buffer, 0, count)
            }
            output.toByteArray()
        }
        require(bytes.size <= 65_536)
        val value = JSONObject(AesGcmRecordCodec.decrypt(bytes, key).toString(Charsets.UTF_8))
        require(value.keys().asSequence().toSet() == setOf("schema_version", "operation_id", "kind", "state", "prompt"))
        require(value.getInt("schema_version") == 1 && value.getString("operation_id").matches(Regex("[a-f0-9]{32}")))
        require(value.getString("state") in setOf("running", "interrupted", "timeout", "failed", "completed", "cancelled"))
        if (value.getString("kind") != "adventure" || value.getString("state") in setOf("completed", "cancelled")) return null
        require(value.getString("prompt").length in 3..8000)
        value.put("state", "interrupted")
    }.getOrNull()
}
