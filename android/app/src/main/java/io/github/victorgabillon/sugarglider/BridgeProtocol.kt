package io.github.victorgabillon.sugarglider

import org.json.JSONException
import org.json.JSONArray
import org.json.JSONObject
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.time.Instant
import java.util.LinkedHashMap

internal sealed interface BridgeRequest {
    val requestId: String
    val pageNonce: String

    data class Hello(
        override val requestId: String,
        override val pageNonce: String,
    ) : BridgeRequest

    data class GetStatus(
        override val requestId: String,
        override val pageNonce: String,
    ) : BridgeRequest

    data class GetLocalRouteCapabilities(
        override val requestId: String,
        override val pageNonce: String,
    ) : BridgeRequest

    data class LocalRoute(
        override val requestId: String,
        override val pageNonce: String,
        val routeRequest: NativeRouteRequest,
    ) : BridgeRequest

    data class RejectedLocalRoute(
        override val requestId: String,
        override val pageNonce: String,
        val code: NativeRouteFailureCode,
    ) : BridgeRequest

    data class StopTracking(
        override val requestId: String,
        override val pageNonce: String,
        val outingSlug: String,
        val participantId: String,
    ) : BridgeRequest

    data class AcknowledgeTerminalFailure(
        override val requestId: String,
        override val pageNonce: String,
        val eventId: Long,
        val outingSlug: String,
        val participantId: String,
    ) : BridgeRequest

    data class StartTracking(
        override val requestId: String,
        override val pageNonce: String,
        val serverOrigin: String,
        val outingSlug: String,
        val participantId: String,
        val participantToken: String,
        val outingExpiresAt: Instant,
        val currentSequence: Long,
    ) : BridgeRequest
}

internal object BridgeProtocol {
    const val OBJECT_NAME = "sugargliderNative"
    private val baseFields = setOf("schema_version", "request_id", "type")
    private val stopFields = baseFields + setOf("outing_slug", "participant_id")
    private val acknowledgementFields = stopFields + "event_id"
    private val startFields = baseFields + setOf(
        "server_origin",
        "outing_slug",
        "participant_id",
        "participant_token",
        "outing_expires_at",
        "current_sequence",
    )
    private val localRouteFields = baseFields + setOf(
        "route_version",
        "profile",
        "points",
    )
    private val coordinateFields = setOf("lat", "lon")

    fun parse(payload: String): BridgeRequest? {
        if (payload.length !in 2..8_192) return null
        val value = try {
            JSONObject(payload)
        } catch (_: JSONException) {
            return null
        }
        if (value.optInt("schema_version", -1) != SCHEMA_VERSION) return null
        val requestId = value.optString("request_id", "")
        val pageNonce = pageNonce(requestId) ?: return null
        return when (value.optString("type", "")) {
            "hello" -> if (hasExactly(value, baseFields)) {
                BridgeRequest.Hello(requestId, pageNonce)
            } else {
                null
            }
            "get_status" ->
                if (hasExactly(value, baseFields)) {
                    BridgeRequest.GetStatus(requestId, pageNonce)
                } else {
                    null
                }
            "get_local_route_capabilities" ->
                if (hasExactly(value, baseFields)) {
                    BridgeRequest.GetLocalRouteCapabilities(requestId, pageNonce)
                } else {
                    null
                }
            "local_route" -> parseLocalRoute(value, requestId, pageNonce)
            "stop_tracking" ->
                parseStop(value, requestId, pageNonce)
            "ack_terminal_failure" ->
                parseAcknowledgement(value, requestId, pageNonce)
            "start_tracking" -> parseStart(value, requestId, pageNonce)
            else -> null
        }
    }

    fun reply(type: String, requestId: String, status: NativeTrackingStatus): String =
        JSONObject()
            .put("schema_version", SCHEMA_VERSION)
            .put("request_id", requestId)
            .put("type", type)
            .put("outing_slug", status.outingSlug ?: JSONObject.NULL)
            .put("participant_id", status.participantId ?: JSONObject.NULL)
            .put("active", status.active)
            .put("state", status.state)
            .put(
                "last_published_at",
                status.lastPublishedAt?.toString() ?: JSONObject.NULL,
            ).put("pending_sample", status.pendingSample)
            .put("stop_warning", status.stopWarning ?: JSONObject.NULL)
            .toString()

    fun failure(
        requestId: String,
        code: String,
        status: NativeTrackingStatus? = null,
        eventId: Long? = null,
        outingSlug: String? = status?.outingSlug,
        participantId: String? = status?.participantId,
    ): String = JSONObject()
        .put("schema_version", SCHEMA_VERSION)
        .put("request_id", requestId)
        .put("type", "permanent_failure")
        .put("code", SafeText.safeFailureCode(code))
        .put("event_id", eventId ?: JSONObject.NULL)
        .put("outing_slug", outingSlug ?: JSONObject.NULL)
        .put("participant_id", participantId ?: JSONObject.NULL)
        .toString()

    fun localRouteCapabilitiesReply(
        requestId: String,
        capabilities: NativeRouteCapabilities,
    ): String {
        val validCapabilities = capabilities.takeIf(NativeRouteCapabilities::isValid)
        val packs = validCapabilities?.packs ?: emptyList()
        val installedPackIds = packs.map(NativeRoutingPackCapability::packId)
        val supportedProfiles = validCapabilities?.supportedProfiles ?: emptyList()
        val packCapabilities = JSONArray()
        packs.forEach { pack ->
            packCapabilities.put(
                JSONObject()
                    .put("pack_id", pack.packId)
                    .put(
                        "access_modes",
                        JSONArray(pack.accessModes.map(LocalRouteAccessMode::wireValue)),
                    ),
            )
        }
        return JSONObject()
            .put("schema_version", SCHEMA_VERSION)
            .put("request_id", requestId)
            .put("type", "local_route_capabilities_result")
            .put("enabled", capabilities.enabled)
            .put("engine", capabilities.engine)
            .put("engine_version", capabilities.engineVersion)
            .put("installed_pack_count", installedPackIds.size)
            .put("installed_pack_ids", JSONArray(installedPackIds))
            .put(
                "supported_profile_ids",
                JSONArray(supportedProfiles.map(LocalRouteProfile::wireValue)),
            ).put("pack_capabilities", packCapabilities)
            .toString()
    }

    fun localRouteReply(requestId: String, result: NativeRouteResult.Success): String? {
        if (!result.isValid()) return null
        val geometry = org.json.JSONArray()
        result.geometry.forEach { coordinate ->
            geometry.put(
                org.json.JSONArray()
                    .put(coordinate.longitude)
                    .put(coordinate.latitude),
            )
        }
        val snappedPoints = JSONArray()
        result.snappedPoints.forEach { coordinate ->
            snappedPoints.put(coordinateJson(coordinate))
        }
        val reply = JSONObject()
            .put("schema_version", SCHEMA_VERSION)
            .put("request_id", requestId)
            .put("type", "local_route_result")
            .put("profile", result.profile.wireValue)
            .put("engine", result.engine)
            .put("engine_version", result.engineVersion)
            .put("pack_id", result.packId)
            .put("distance_m", result.distanceMeters)
            .put("duration_s", result.durationSeconds ?: JSONObject.NULL)
            .put("geometry", geometry)
            .put("snapped_points", snappedPoints)
            .put(
                "measurements",
                JSONObject()
                    .put("cold_start", result.measurements.coldStart)
                    .put(
                        "engine_initialization_ms",
                        result.measurements.engineInitializationMs,
                    ).put("route_ms", result.measurements.routeMs)
                    .put(
                        "memory_before_initialization_bytes",
                        result.measurements.memoryBeforeInitializationBytes,
                    ).put(
                        "memory_after_initialization_bytes",
                        result.measurements.memoryAfterInitializationBytes,
                    ).put(
                        "memory_after_route_bytes",
                        result.measurements.memoryAfterRouteBytes,
                    ),
            ).toString()
        return reply.takeIf {
            it.toByteArray(StandardCharsets.UTF_8).size <= MAX_LOCAL_ROUTE_REPLY_BYTES
        }
    }

    fun localRouteFailure(requestId: String, code: NativeRouteFailureCode): String =
        JSONObject()
            .put("schema_version", SCHEMA_VERSION)
            .put("request_id", requestId)
            .put("type", "local_route_failure")
            .put("code", code.wireValue)
            .toString()

    private fun parseStart(
        value: JSONObject,
        requestId: String,
        pageNonce: String,
    ): BridgeRequest.StartTracking? {
        if (!hasExactly(value, startFields)) return null
        val sequence = strictLong(value, "current_sequence") ?: return null
        if (sequence !in 0..MAXIMUM_SAFE_SEQUENCE) return null
        val expiresAt = try {
            Instant.parse(value.getString("outing_expires_at"))
        } catch (_: Exception) {
            return null
        }
        val origin = value.optString("server_origin", "")
        val slug = value.optString("outing_slug", "")
        val participantId = value.optString("participant_id", "")
        val token = value.optString("participant_token", "")
        if (
            origin.length !in 8..2_048 ||
            !OUTING_SLUG_PATTERN.matches(slug) ||
            !PARTICIPANT_ID_PATTERN.matches(participantId) ||
            !PARTICIPANT_TOKEN_PATTERN.matches(token)
        ) return null
        return BridgeRequest.StartTracking(
            requestId = requestId,
            pageNonce = pageNonce,
            serverOrigin = origin,
            outingSlug = slug,
            participantId = participantId,
            participantToken = token,
            outingExpiresAt = expiresAt,
            currentSequence = sequence,
        )
    }

    private fun parseLocalRoute(
        value: JSONObject,
        requestId: String,
        pageNonce: String,
    ): BridgeRequest? {
        if (!hasExactly(value, localRouteFields)) return null
        val routeVersion = strictLong(value, "route_version")
            ?.takeIf { it == LOCAL_ROUTE_REQUEST_VERSION.toLong() }
            ?.toInt()
            ?: return BridgeRequest.RejectedLocalRoute(
                requestId,
                pageNonce,
                NativeRouteFailureCode.INVALID_REQUEST,
            )
        val profileValue = value.optString("profile", "")
        val profile = LocalRouteProfile.parse(profileValue) ?: return BridgeRequest.RejectedLocalRoute(
            requestId,
            pageNonce,
            NativeRouteFailureCode.UNSUPPORTED_PROFILE,
        )
        val pointValues = value.optJSONArray("points")
            ?: return BridgeRequest.RejectedLocalRoute(
                requestId,
                pageNonce,
                NativeRouteFailureCode.INVALID_REQUEST,
            )
        if (pointValues.length() !in MIN_LOCAL_ROUTE_POINTS..MAX_LOCAL_ROUTE_POINTS) {
            return BridgeRequest.RejectedLocalRoute(
                requestId,
                pageNonce,
                NativeRouteFailureCode.INVALID_REQUEST,
            )
        }
        val points = buildList {
            repeat(pointValues.length()) { index ->
                val point = parseCoordinate(pointValues.optJSONObject(index))
                    ?: return BridgeRequest.RejectedLocalRoute(
                        requestId,
                        pageNonce,
                        NativeRouteFailureCode.INVALID_REQUEST,
                    )
                add(point)
            }
        }
        val routeRequest = NativeRouteRequest(
            version = routeVersion,
            requestId = requestId,
            points = points,
            profile = profile,
        )
        if (!routeRequest.isValid()) {
            return BridgeRequest.RejectedLocalRoute(
                requestId,
                pageNonce,
                NativeRouteFailureCode.INVALID_REQUEST,
            )
        }
        return BridgeRequest.LocalRoute(requestId, pageNonce, routeRequest)
    }

    private fun parseStop(
        value: JSONObject,
        requestId: String,
        pageNonce: String,
    ): BridgeRequest.StopTracking? {
        if (!hasExactly(value, stopFields)) return null
        val slug = value.optString("outing_slug", "")
        val participantId = value.optString("participant_id", "")
        if (!OUTING_SLUG_PATTERN.matches(slug) || !PARTICIPANT_ID_PATTERN.matches(participantId)) {
            return null
        }
        return BridgeRequest.StopTracking(requestId, pageNonce, slug, participantId)
    }

    private fun parseAcknowledgement(
        value: JSONObject,
        requestId: String,
        pageNonce: String,
    ): BridgeRequest.AcknowledgeTerminalFailure? {
        if (!hasExactly(value, acknowledgementFields)) return null
        val eventId = strictLong(value, "event_id") ?: return null
        val slug = value.optString("outing_slug", "")
        val participantId = value.optString("participant_id", "")
        if (
            eventId <= 0 ||
            !OUTING_SLUG_PATTERN.matches(slug) ||
            !PARTICIPANT_ID_PATTERN.matches(participantId)
        ) return null
        return BridgeRequest.AcknowledgeTerminalFailure(
            requestId,
            pageNonce,
            eventId,
            slug,
            participantId,
        )
    }

    private fun pageNonce(requestId: String): String? =
        Regex("^web-([A-Fa-f0-9]{32})-[1-9][0-9]{0,9}$")
            .matchEntire(requestId)
            ?.groupValues
            ?.get(1)

    private fun hasExactly(value: JSONObject, expected: Set<String>): Boolean {
        val fields = buildSet { value.keys().forEachRemaining(::add) }
        return fields == expected
    }

    private fun strictLong(value: JSONObject, key: String): Long? {
        val raw = try {
            value.get(key)
        } catch (_: JSONException) {
            return null
        }
        return when (raw) {
            is Byte -> raw.toLong()
            is Short -> raw.toLong()
            is Int -> raw.toLong()
            is Long -> raw
            else -> null
        }
    }

    private fun parseCoordinate(value: JSONObject?): LocalRouteCoordinate? {
        if (value == null || !hasExactly(value, coordinateFields)) return null
        val latitude = strictDouble(value, "lat") ?: return null
        val longitude = strictDouble(value, "lon") ?: return null
        return LocalRouteCoordinate(latitude, longitude).takeIf(LocalRouteCoordinate::isValid)
    }

    private fun strictDouble(value: JSONObject, key: String): Double? {
        val raw = try {
            value.get(key)
        } catch (_: JSONException) {
            return null
        }
        if (raw !is Number) return null
        return raw.toDouble().takeIf(Double::isFinite)
    }

    private fun coordinateJson(coordinate: LocalRouteCoordinate): JSONObject = JSONObject()
        .put("lat", coordinate.latitude)
        .put("lon", coordinate.longitude)
}

internal object BridgeGate {
    fun accepts(
        canonicalSourceOrigin: String,
        configuredOrigin: String,
        isMainFrame: Boolean,
        currentWebViewIdentity: Int,
        sourceWebViewIdentity: Int,
    ): Boolean = isMainFrame &&
        canonicalSourceOrigin == configuredOrigin &&
        currentWebViewIdentity == sourceWebViewIdentity
}

internal class BridgeRequestLedger(private val maximumEntries: Int = 64) {
    private data class Key(val pageNonce: String, val requestId: String)
    private data class Entry(val digest: String, val reply: String?)

    private val entries = object : LinkedHashMap<Key, Entry>(maximumEntries, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<Key, Entry>?): Boolean =
            size > maximumEntries
    }

    @Synchronized
    fun lookup(request: BridgeRequest, payload: String): String? {
        val entry = entries[Key(request.pageNonce, request.requestId)] ?: return null
        return if (entry.digest == digest(payload)) entry.reply else BridgeProtocol.failure(
            request.requestId,
            "native_tracking_failure",
        )
    }

    @Synchronized
    fun begin(request: BridgeRequest, payload: String): Boolean {
        val key = Key(request.pageNonce, request.requestId)
        val existing = entries[key]
        if (existing != null) return false
        entries[key] = Entry(digest(payload), null)
        return true
    }

    @Synchronized
    fun complete(request: BridgeRequest, payload: String, reply: String) {
        val key = Key(request.pageNonce, request.requestId)
        val payloadDigest = digest(payload)
        val existing = entries[key]
        if (existing?.digest == payloadDigest) entries[key] = Entry(payloadDigest, reply)
    }

    private fun digest(payload: String): String = MessageDigest.getInstance("SHA-256")
        .digest(payload.toByteArray(StandardCharsets.UTF_8))
        .joinToString("") { "%02x".format(it) }
}
