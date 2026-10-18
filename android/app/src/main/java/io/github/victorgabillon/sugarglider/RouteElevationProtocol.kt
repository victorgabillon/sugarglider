package io.github.victorgabillon.sugarglider

import android.os.Debug
import android.os.SystemClock
import kotlin.math.abs
import kotlin.math.ceil
import org.json.JSONArray
import org.json.JSONObject

internal const val MAX_ELEVATION_REQUEST_CHARS = 262_144
internal const val MAX_ELEVATION_REPLY_CHARS = 1_048_576
internal const val ELEVATION_HEIGHT_REFERENCE = "unresolved vertical datum; verified V2 elevation component manifest"
internal const val ELEVATION_EGM96_REFERENCE = "EGM96 orthometric metres; verified V2 elevation component manifest"
internal const val ELEVATION_IGN69_REFERENCE = "IGN69 normal metres; IGN RGE ALTI 5 m; Licence Ouverte 2.0; verified V2 elevation component manifest"
internal data class RouteElevationRequest(val operationId: String, val candidateId: String, val profile: String,
    val geometry: String, val distance: Double, val reference: RegionalRoutingPackReference, val interval: Double,
    val positions: List<Pair<Double, LocalRouteCoordinate>>)

internal object RouteElevationProtocol {
    private val base = setOf("schema_version", "request_id", "type")
    private val fields = base + setOf("elevation_version", "operation_id", "candidate_id", "profile", "geometry_sha256", "distance_m", "regional_reference", "sampling_interval_m", "samples")
    fun parse(value: JSONObject, id: String, nonce: String): BridgeRequest = try {
        require(value.opt("schema_version") == 1)
        if (value.optString("type") == "cancel_route_elevation") {
            require(exact(value, base + "operation_id")); val operation = value.getString("operation_id"); require(operation.matches(Regex("[a-f0-9]{32}")))
            BridgeRequest.CancelRouteElevation(id, nonce, operation)
        } else {
            require(exact(value, fields) && value.opt("elevation_version") == 1)
            val operation = value.getString("operation_id"); require(operation.matches(Regex("[a-f0-9]{32}")))
            val candidate = value.getString("candidate_id"); require(candidate.matches(Regex("geometry:[a-f0-9]{64}")))
            val profile = value.getString("profile"); require(LocalRouteProfile.entries.any { it.wireValue == profile })
            val geometry = value.getString("geometry_sha256"); require(geometry.matches(Regex("[a-f0-9]{64}")))
            val reference = requireNotNull(RegionalRoutingPackReference.parse(value.optJSONObject("regional_reference")))
            val distance = number(value.get("distance_m")); require(distance > 0 && distance <= 200_000)
            val interval = number(value.get("sampling_interval_m")); val expectedInterval = maxOf(50.0, distance / 2_047)
            require(interval == expectedInterval && interval <= 100)
            val samples = value.getJSONArray("samples")
            val count = if (distance > 50.0 * 2_047) 2_048 else ceil(distance / 50.0).toInt() + 1
            require(samples.length() == count && count in 2..MAX_NATIVE_HEIGHT_SAMPLES)
            val positions = (0 until count).map { index ->
                val row = samples.getJSONArray(index); require(row.length() == 3)
                val progress = number(row.get(0)); val expected = if (index == count - 1) distance else index * interval
                require(progress in 0.0..distance && abs(progress - expected) <= 1e-7)
                if (index == 0) require(progress == 0.0)
                if (index == count - 1) require(progress == distance)
                val coordinate = LocalRouteCoordinate(number(row.get(1)), number(row.get(2))); require(coordinate.isValid())
                Pair(progress, coordinate)
            }
            require(positions.zipWithNext().all { (left, right) -> right.first > left.first && right.first - left.first <= 100.0 })
            BridgeRequest.RouteElevation(id, nonce, RouteElevationRequest(operation, candidate, profile, geometry, distance, reference, interval, positions))
        }
    } catch (_: Exception) { BridgeRequest.RejectedRouteElevation(id, nonce) }

    fun execute(id: String, request: RouteElevationRequest, engine: NativeOfflineEngine, cancelled: () -> Boolean): String {
        val started = SystemClock.elapsedRealtime()
        if (cancelled()) return failure(id, request.operationId, "elevation_cancelled")
        val height = engine.height(request.reference, request.positions.map { it.second }, "route-elevation")
        if (cancelled()) return failure(id, request.operationId, "elevation_cancelled")
        if (height !is NativeHeightResult.Success || height.reference != request.reference) return failure(id, request.operationId, "elevation_region_unavailable")
        val analysisStarted = SystemClock.elapsedRealtime()
        return try {
            val input = ElevationInput(request.reference.elevation.manifest.sha256, request.geometry, request.profile,
                request.distance, height.heightReference, request.positions.mapIndexed { index, point -> ElevationPoint(index, point.first, height.heights[index]?.let { if (it == 0.0) 0.0 else it }) })
            val analysis = DistanceBoxElevation.analyze(input)
            if (cancelled()) return failure(id, request.operationId, "elevation_cancelled")
            val result = JSONObject().put("schema_version", 1).put("type", "local_elevation_result").put("request_id", id)
                .put("elevation_version", 1).put("operation_id", request.operationId).put("candidate_id", request.candidateId)
                .put("regional_reference", request.reference.toJson()).put("sampling_interval_m", request.interval)
                .put("sample_coordinates", JSONArray(request.positions.map { JSONArray(listOf(it.second.longitude, it.second.latitude)) }))
                .put("analysis", analysis).put("measurements", JSONObject().put("native_height_ms", height.elapsedMs)
                    .put("analysis_ms", SystemClock.elapsedRealtime() - analysisStarted).put("total_ms", SystemClock.elapsedRealtime() - started)
                    .put("pss_bytes", Debug.getPss() * 1_024L).put("cold_start", height.coldStart)).toString()
            if (result.length > MAX_ELEVATION_REPLY_CHARS) failure(id, request.operationId, "elevation_reply_too_large") else result
        } catch (_: Exception) { failure(id, request.operationId, "elevation_analysis_failed") }
    }
    fun failure(id: String, operation: String?, code: String): String = JSONObject().put("schema_version", 1).put("type", "local_elevation_failure")
        .put("request_id", id).put("operation_id", operation ?: JSONObject.NULL).put("code", code).toString()
    fun cancelled(id: String, operation: String, accepted: Boolean): String = JSONObject().put("schema_version", 1).put("type", "local_elevation_cancel_result")
        .put("request_id", id).put("operation_id", operation).put("accepted", accepted).toString()
    private fun exact(value: JSONObject, fields: Set<String>): Boolean = value.keys().asSequence().toSet() == fields
    private fun number(value: Any): Double { require(value is Number); return value.toDouble().also { require(it.isFinite()) } }
}
