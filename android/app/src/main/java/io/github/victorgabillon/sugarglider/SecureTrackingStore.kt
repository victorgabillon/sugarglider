package io.github.victorgabillon.sugarglider

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import org.json.JSONException
import org.json.JSONObject
import java.io.File
import java.security.KeyStore
import java.time.Instant
import javax.crypto.AEADBadTagException
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

internal object AesGcmRecordCodec {
    private val magic = byteArrayOf(0x53, 0x47, 0x32, 0x37)
    private const val ENVELOPE_VERSION: Byte = 1
    private const val IV_SIZE = 12
    private const val MAXIMUM_PLAINTEXT_BYTES = 32_768
    private const val MAXIMUM_ENVELOPE_BYTES = 65_536

    fun encrypt(plaintext: ByteArray, key: SecretKey): ByteArray {
        require(plaintext.size in 1..MAXIMUM_PLAINTEXT_BYTES)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key)
        val iv = cipher.iv?.copyOf()
            ?: throw IllegalStateException("Encryption provider returned no IV")
        if (iv.size != IV_SIZE) {
            throw IllegalStateException("Encryption provider returned an invalid IV")
        }
        cipher.updateAAD(magic + byteArrayOf(ENVELOPE_VERSION))
        val ciphertext = cipher.doFinal(plaintext)
        return magic + byteArrayOf(ENVELOPE_VERSION, IV_SIZE.toByte()) + iv + ciphertext
    }

    fun decrypt(envelope: ByteArray, key: SecretKey): ByteArray {
        if (envelope.size !in (magic.size + 2 + IV_SIZE + 16)..MAXIMUM_ENVELOPE_BYTES) {
            throw IllegalArgumentException("Invalid encrypted record size")
        }
        if (!envelope.copyOfRange(0, magic.size).contentEquals(magic)) {
            throw IllegalArgumentException("Invalid encrypted record marker")
        }
        if (envelope[magic.size] != ENVELOPE_VERSION) {
            throw IllegalArgumentException("Unsupported encrypted record version")
        }
        val ivSize = envelope[magic.size + 1].toInt()
        if (ivSize != IV_SIZE) throw IllegalArgumentException("Invalid encrypted record IV")
        val ivStart = magic.size + 2
        val ciphertextStart = ivStart + ivSize
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(
            Cipher.DECRYPT_MODE,
            key,
            GCMParameterSpec(128, envelope.copyOfRange(ivStart, ciphertextStart)),
        )
        cipher.updateAAD(magic + byteArrayOf(ENVELOPE_VERSION))
        return try {
            cipher.doFinal(envelope.copyOfRange(ciphertextStart, envelope.size))
        } catch (error: AEADBadTagException) {
            throw IllegalArgumentException("Encrypted record authentication failed", error)
        }
    }
}

internal object SecureRecordJson {
    private val recordFields = setOf("schema_version", "session", "pending_sample")
    private val sessionFields = setOf(
        "schema_version",
        "server_origin",
        "outing_slug",
        "participant_id",
        "participant_token",
        "outing_expires_at",
        "last_accepted_sequence",
        "started_at",
    )
    private val sampleFields = setOf(
        "sample_id",
        "captured_at",
        "queued_at",
        "coordinate",
        "accuracy_m",
        "altitude_m",
        "speed_m_s",
        "heading_deg",
    )
    private val coordinateFields = setOf("lat", "lon")

    fun encode(record: SecureTrackingRecord): ByteArray {
        val session = record.session
        val sessionJson = JSONObject()
            .put("schema_version", SCHEMA_VERSION)
            .put("server_origin", session.serverOrigin)
            .put("outing_slug", session.outingSlug)
            .put("participant_id", session.participantId)
            .put("participant_token", session.participantToken)
            .put("outing_expires_at", session.outingExpiresAt.toString())
            .put("last_accepted_sequence", session.lastAcceptedSequence)
            .put("started_at", session.startedAt.toString())
        val root = JSONObject()
            .put("schema_version", SCHEMA_VERSION)
            .put("session", sessionJson)
            .put("pending_sample", record.pendingSample?.let(::sampleJson) ?: JSONObject.NULL)
        return root.toString().toByteArray(Charsets.UTF_8)
    }

    fun decode(payload: ByteArray, now: Instant): SecureTrackingRecord {
        if (payload.size !in 2..32_768) throw IllegalArgumentException("Invalid record size")
        val root = try {
            JSONObject(payload.toString(Charsets.UTF_8))
        } catch (error: JSONException) {
            throw IllegalArgumentException("Malformed tracking record", error)
        }
        requireExact(root, recordFields)
        if (root.optInt("schema_version", -1) != SCHEMA_VERSION) {
            throw IllegalArgumentException("Unsupported tracking record schema")
        }
        val sessionJson = root.getJSONObject("session")
        requireExact(sessionJson, sessionFields)
        if (sessionJson.optInt("schema_version", -1) != SCHEMA_VERSION) {
            throw IllegalArgumentException("Unsupported session schema")
        }
        val session = ParticipantSession(
            serverOrigin = sessionJson.getString("server_origin"),
            outingSlug = sessionJson.getString("outing_slug"),
            participantId = sessionJson.getString("participant_id"),
            participantToken = sessionJson.getString("participant_token"),
            outingExpiresAt = Instant.parse(sessionJson.getString("outing_expires_at")),
            lastAcceptedSequence = strictLong(sessionJson, "last_accepted_sequence"),
            startedAt = Instant.parse(sessionJson.getString("started_at")),
        )
        if (!session.isValid(now)) throw IllegalArgumentException("Invalid or expired session")
        val sample = if (root.isNull("pending_sample")) {
            null
        } else {
            parseSample(root.getJSONObject("pending_sample"), now)
        }
        return SecureTrackingRecord(session, sample)
    }

    private fun sampleJson(sample: NormalizedLocationSample): JSONObject = JSONObject()
        .put("sample_id", sample.sampleId)
        .put("captured_at", sample.capturedAt.toString())
        .put("queued_at", sample.queuedAt.toString())
        .put(
            "coordinate",
            JSONObject().put("lat", sample.latitude).put("lon", sample.longitude),
        ).put("accuracy_m", sample.accuracyM)
        .put("altitude_m", sample.altitudeM ?: JSONObject.NULL)
        .put("speed_m_s", sample.speedMS ?: JSONObject.NULL)
        .put("heading_deg", sample.headingDeg ?: JSONObject.NULL)

    private fun parseSample(value: JSONObject, now: Instant): NormalizedLocationSample {
        requireExact(value, sampleFields)
        val coordinate = value.getJSONObject("coordinate")
        requireExact(coordinate, coordinateFields)
        val sample = NormalizedLocationSample(
            sampleId = value.getString("sample_id"),
            capturedAt = Instant.parse(value.getString("captured_at")),
            queuedAt = Instant.parse(value.getString("queued_at")),
            latitude = strictDouble(coordinate, "lat"),
            longitude = strictDouble(coordinate, "lon"),
            accuracyM = strictDouble(value, "accuracy_m"),
            altitudeM = nullableDouble(value, "altitude_m"),
            speedMS = nullableDouble(value, "speed_m_s"),
            headingDeg = nullableDouble(value, "heading_deg"),
        )
        if (!sample.isValid(now)) throw IllegalArgumentException("Invalid pending sample")
        return sample
    }

    private fun strictLong(value: JSONObject, key: String): Long = when (val raw = value.get(key)) {
        is Byte -> raw.toLong()
        is Short -> raw.toLong()
        is Int -> raw.toLong()
        is Long -> raw
        else -> throw IllegalArgumentException("Invalid integer field")
    }

    private fun strictDouble(value: JSONObject, key: String): Double {
        val raw = value.get(key)
        if (raw !is Number) throw IllegalArgumentException("Invalid number field")
        return raw.toDouble().also {
            if (!it.isFinite()) throw IllegalArgumentException("Invalid finite number")
        }
    }

    private fun nullableDouble(value: JSONObject, key: String): Double? =
        if (value.isNull(key)) null else strictDouble(value, key)

    private fun requireExact(value: JSONObject, fields: Set<String>) {
        val actual = buildSet { value.keys().forEachRemaining(::add) }
        if (actual != fields) throw IllegalArgumentException("Unexpected tracking record fields")
    }
}

internal class AndroidSecureStateStore(
    context: Context,
    private val now: () -> Instant = Instant::now,
) : SecureStateStore {
    private val atomicFile = AtomicFile(File(context.noBackupFilesDir, "pr27-native-session.enc"))
    private val key: SecretKey by lazy(::loadOrCreateKey)

    @Synchronized
    override fun load(): SecureTrackingRecord? = loadInternal(deleteOnFailure = true)

    @Synchronized
    override fun saveSession(session: ParticipantSession): StoreMutationResult {
        if (!session.isValid(now())) return StoreMutationResult.STORAGE_FAILURE
        return try {
            write(SecureTrackingRecord(session, null))
            StoreMutationResult.APPLIED
        } catch (_: Exception) {
            StoreMutationResult.STORAGE_FAILURE
        }
    }

    @Synchronized
    override fun replacePending(
        session: ParticipantSession,
        sample: NormalizedLocationSample,
    ): PendingWriteResult {
        val record = try {
            loadForMutation()
        } catch (_: Exception) {
            safeDelete()
            return PendingWriteResult.STORAGE_FAILURE
        } ?: return PendingWriteResult.SESSION_MISMATCH
        if (!record.session.identityMatches(session)) return PendingWriteResult.SESSION_MISMATCH
        if (!sample.isValid(now())) return PendingWriteResult.STORAGE_FAILURE
        val existing = record.pendingSample
        if (existing != null && compareSample(sample, existing) < 0) {
            return PendingWriteResult.IGNORED_OLDER
        }
        return try {
            write(record.copy(pendingSample = sample))
            PendingWriteResult.STORED
        } catch (_: Exception) {
            PendingWriteResult.STORAGE_FAILURE
        }
    }

    @Synchronized
    override fun clearMatchingSample(
        session: ParticipantSession,
        sampleId: String,
    ): StoreMutationResult {
        val record = mutationRecord() ?: return missingMutationResult()
        if (!record.session.identityMatches(session)) return StoreMutationResult.SESSION_MISMATCH
        if (record.pendingSample?.sampleId != sampleId) return StoreMutationResult.NO_MATCH
        return writeResult(record.copy(pendingSample = null))
    }

    @Synchronized
    override fun updateSequence(
        session: ParticipantSession,
        sequence: Long,
    ): StoreMutationResult {
        if (sequence !in 0..MAXIMUM_SAFE_SEQUENCE) return StoreMutationResult.STORAGE_FAILURE
        val record = mutationRecord() ?: return missingMutationResult()
        if (!record.session.identityMatches(session)) return StoreMutationResult.SESSION_MISMATCH
        val updated = record.session.copy(
            lastAcceptedSequence = maxOf(record.session.lastAcceptedSequence, sequence),
        )
        return writeResult(record.copy(session = updated))
    }

    @Synchronized
    override fun clearMatchingSession(session: ParticipantSession): StoreMutationResult {
        val record = mutationRecord() ?: return missingMutationResult()
        if (!record.session.identityMatches(session)) return StoreMutationResult.SESSION_MISMATCH
        return if (safeDelete()) StoreMutationResult.APPLIED else StoreMutationResult.STORAGE_FAILURE
    }

    @Synchronized
    override fun clearAll(): StoreMutationResult =
        if (safeDelete()) StoreMutationResult.APPLIED else StoreMutationResult.STORAGE_FAILURE

    private var lastMutationLoadFailed = false

    private fun mutationRecord(): SecureTrackingRecord? {
        lastMutationLoadFailed = false
        return try {
            loadForMutation()
        } catch (_: Exception) {
            lastMutationLoadFailed = true
            safeDelete()
            null
        }
    }

    private fun missingMutationResult(): StoreMutationResult =
        if (lastMutationLoadFailed) {
            StoreMutationResult.STORAGE_FAILURE
        } else {
            StoreMutationResult.NO_MATCH
        }

    private fun writeResult(record: SecureTrackingRecord): StoreMutationResult = try {
        write(record)
        StoreMutationResult.APPLIED
    } catch (_: Exception) {
        StoreMutationResult.STORAGE_FAILURE
    }

    private fun loadInternal(deleteOnFailure: Boolean): SecureTrackingRecord? {
        if (!atomicFile.baseFile.exists()) return null
        return try {
            loadForMutation()
        } catch (_: Exception) {
            if (deleteOnFailure) safeDelete()
            null
        }
    }

    private fun loadForMutation(): SecureTrackingRecord? {
        if (!atomicFile.baseFile.exists()) return null
        val envelope = atomicFile.openRead().use { input ->
            val bytes = input.readBytes()
            if (bytes.size > 65_536) throw IllegalArgumentException("Tracking record too large")
            bytes
        }
        return SecureRecordJson.decode(AesGcmRecordCodec.decrypt(envelope, key), now())
    }

    private fun safeDelete(): Boolean = try {
        atomicFile.delete()
        true
    } catch (_: Exception) {
        false
    }

    private fun write(record: SecureTrackingRecord) {
        val envelope = AesGcmRecordCodec.encrypt(SecureRecordJson.encode(record), key)
        val output = atomicFile.startWrite()
        try {
            output.write(envelope)
            output.flush()
            atomicFile.finishWrite(output)
        } catch (error: Exception) {
            atomicFile.failWrite(output)
            throw error
        }
    }

    private fun loadOrCreateKey(): SecretKey {
        val alias = "sugarglider-pr27-native-state"
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                alias,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            ).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        return generator.generateKey()
    }

    private fun compareSample(
        left: NormalizedLocationSample,
        right: NormalizedLocationSample,
    ): Int = compareValuesBy(left, right, { it.capturedAt }, { it.queuedAt }, { it.sampleId })
}
