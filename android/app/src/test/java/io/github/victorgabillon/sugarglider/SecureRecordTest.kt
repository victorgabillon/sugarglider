package io.github.victorgabillon.sugarglider

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

class SecureRecordTest {
    @Test
    fun encryptedRecordRoundTrips() {
        val key = key()
        val record = SecureTrackingRecord(testSession(), testSample())
        val envelope = AesGcmRecordCodec.encrypt(
            SecureRecordJson.encode(record),
            key,
        )
        val decoded = SecureRecordJson.decode(
            AesGcmRecordCodec.decrypt(envelope, key),
            TEST_NOW,
        )
        assertEquals(record, decoded)
    }

    @Test
    fun wrongKeyAuthenticationFailureIsRejected() {
        val envelope = AesGcmRecordCodec.encrypt(
            SecureRecordJson.encode(SecureTrackingRecord(testSession(), null)),
            key(),
        )
        assertThrows(IllegalArgumentException::class.java) {
            AesGcmRecordCodec.decrypt(envelope, key())
        }
    }

    @Test
    fun truncatedRecordIsRejected() {
        val encrypted = AesGcmRecordCodec.encrypt(
            SecureRecordJson.encode(SecureTrackingRecord(testSession(), null)),
            key(),
        )
        assertThrows(IllegalArgumentException::class.java) {
            AesGcmRecordCodec.decrypt(encrypted.copyOf(10), key())
        }
    }

    @Test
    fun providerGeneratesDifferentIvAndCiphertextForSamePlaintext() {
        val key = key()
        val plaintext = SecureRecordJson.encode(SecureTrackingRecord(testSession(), null))

        val first = AesGcmRecordCodec.encrypt(plaintext, key)
        val second = AesGcmRecordCodec.encrypt(plaintext, key)

        assertFalse(
            first.copyOfRange(IV_START, CIPHERTEXT_START).contentEquals(
                second.copyOfRange(IV_START, CIPHERTEXT_START),
            ),
        )
        assertFalse(
            first.copyOfRange(CIPHERTEXT_START, first.size).contentEquals(
                second.copyOfRange(CIPHERTEXT_START, second.size),
            ),
        )
    }

    @Test
    fun malformedEnvelopeIvLengthIsRejected() {
        val key = key()
        val envelope = AesGcmRecordCodec.encrypt(
            SecureRecordJson.encode(SecureTrackingRecord(testSession(), null)),
            key,
        )
        envelope[IV_LENGTH_OFFSET] = (IV_SIZE - 1).toByte()

        assertThrows(IllegalArgumentException::class.java) {
            AesGcmRecordCodec.decrypt(envelope, key)
        }
    }

    @Test
    fun authenticatedIvAndCiphertextTamperingAreRejected() {
        val key = key()
        val envelope = AesGcmRecordCodec.encrypt(
            SecureRecordJson.encode(SecureTrackingRecord(testSession(), null)),
            key,
        )
        val tamperedIv = envelope.copyOf().also {
            it[IV_START] = (it[IV_START].toInt() xor 1).toByte()
        }
        val tamperedCiphertext = envelope.copyOf().also {
            it[it.lastIndex] = (it[it.lastIndex].toInt() xor 1).toByte()
        }

        assertThrows(IllegalArgumentException::class.java) {
            AesGcmRecordCodec.decrypt(tamperedIv, key)
        }
        assertThrows(IllegalArgumentException::class.java) {
            AesGcmRecordCodec.decrypt(tamperedCiphertext, key)
        }
    }

    @Test
    fun authenticatedEnvelopeHeaderTamperingIsRejected() {
        val key = key()
        val envelope = AesGcmRecordCodec.encrypt(
            SecureRecordJson.encode(SecureTrackingRecord(testSession(), null)),
            key,
        )
        val tamperedMagic = envelope.copyOf().also {
            it[0] = (it[0].toInt() xor 1).toByte()
        }
        val tamperedVersion = envelope.copyOf().also {
            it[ENVELOPE_VERSION_OFFSET] = (it[ENVELOPE_VERSION_OFFSET] + 1).toByte()
        }

        assertThrows(IllegalArgumentException::class.java) {
            AesGcmRecordCodec.decrypt(tamperedMagic, key)
        }
        assertThrows(IllegalArgumentException::class.java) {
            AesGcmRecordCodec.decrypt(tamperedVersion, key)
        }
    }

    @Test
    fun unsupportedSchemaIsRejected() {
        val invalid = JSONObject(String(SecureRecordJson.encode(
            SecureTrackingRecord(testSession(), null),
        ))).put("schema_version", 2).toString().toByteArray()
        assertThrows(IllegalArgumentException::class.java) {
            SecureRecordJson.decode(invalid, TEST_NOW)
        }
    }

    @Test
    fun expiredSessionIsRejected() {
        val payload = SecureRecordJson.encode(SecureTrackingRecord(testSession(), null))
        assertThrows(IllegalArgumentException::class.java) {
            SecureRecordJson.decode(payload, TEST_NOW.plusSeconds(7_200))
        }
    }

    @Test
    fun unexpectedAuthorityAndHistoryFieldsAreRejected() {
        val root = JSONObject(String(SecureRecordJson.encode(
            SecureTrackingRecord(testSession(), testSample()),
        )))
        root.getJSONObject("session").put("owner_token", "forbidden")
        root.put("coordinate_history", listOf(1, 2))
        assertThrows(IllegalArgumentException::class.java) {
            SecureRecordJson.decode(root.toString().toByteArray(), TEST_NOW)
        }
    }

    @Test
    fun encodedRecordHasOnePendingSampleAndNoForbiddenHistory() {
        val encoded = String(SecureRecordJson.encode(
            SecureTrackingRecord(testSession(), testSample()),
        ))
        assertEquals(1, "pending_sample".toRegex().findAll(encoded).count())
        for (forbidden in listOf("owner_token", "join_token", "invitation_token", "history")) {
            assertFalse(encoded.contains(forbidden))
        }
    }

    @Test
    fun criticalCleanupMatchesStartedSessionNotJustParticipant() {
        val old = testSession(startedAt = TEST_NOW)
        val newer = testSession(startedAt = TEST_NOW.plusSeconds(1))
        assertFalse(old.identityMatches(newer))
        assertTrue(old.identityMatches(old.copy()))
    }

    @Test
    fun invalidFuturePendingSampleIsRejected() {
        val future = testSample(
            capturedAt = TEST_NOW.plusSeconds(31),
            queuedAt = TEST_NOW.plusSeconds(31),
        )
        assertThrows(IllegalArgumentException::class.java) {
            SecureRecordJson.decode(
                SecureRecordJson.encode(SecureTrackingRecord(testSession(), future)),
                TEST_NOW,
            )
        }
    }

    @Test
    fun recordWithoutPendingSampleRoundTripsAsNull() {
        val decoded = SecureRecordJson.decode(
            SecureRecordJson.encode(SecureTrackingRecord(testSession(), null)),
            TEST_NOW,
        )
        assertNull(decoded.pendingSample)
    }

    private fun key(): SecretKey = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()

    companion object {
        private const val ENVELOPE_VERSION_OFFSET = 4
        private const val IV_LENGTH_OFFSET = 5
        private const val IV_START = 6
        private const val IV_SIZE = 12
        private const val CIPHERTEXT_START = IV_START + IV_SIZE
    }
}
