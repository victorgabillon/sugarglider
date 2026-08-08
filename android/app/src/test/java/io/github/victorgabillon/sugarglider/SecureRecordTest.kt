package io.github.victorgabillon.sugarglider

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.security.SecureRandom
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
            SecureRandom(),
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
            SecureRandom(),
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
            SecureRandom(),
        )
        assertThrows(IllegalArgumentException::class.java) {
            AesGcmRecordCodec.decrypt(encrypted.copyOf(10), key())
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
}
