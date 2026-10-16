package io.github.victorgabillon.sugarglider

import android.app.Activity
import android.app.Instrumentation
import android.content.Intent
import android.net.TrafficStats
import android.os.Bundle
import android.os.Debug
import android.os.Process
import android.os.SystemClock
import java.io.File
import java.util.zip.GZIPOutputStream
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt
import org.json.JSONArray
import org.json.JSONObject

/** Explicit isolated-app acceptance; regional files are installed only by the normal UI. */
class V2RegionInstrumentation : Instrumentation() {
    private lateinit var researchId: String
    private lateinit var phase: String
    private var blockWebNetwork = false

    override fun onCreate(arguments: Bundle?) {
        super.onCreate(arguments)
        researchId = arguments?.getString("research_id").orEmpty()
        phase = arguments?.getString("phase").orEmpty()
        blockWebNetwork = arguments?.getString("block_web_network") == "true"
        start()
    }

    override fun onStart() {
        val summary = Bundle()
        try {
            check(BuildConfig.DEBUG && targetContext.packageName == "io.github.victorgabillon.sugarglider.v2debug")
            check(researchId.matches(Regex("[a-z0-9-]{1,64}")))
            val root = File(targetContext.cacheDir, researchId).canonicalFile
            check(root.parentFile == targetContext.cacheDir.canonicalFile && root.isDirectory)
            if (phase == "planner") {
                val uid = Process.myUid()
                val startupTx = TrafficStats.getUidTxBytes(uid)
                val startupRx = TrafficStats.getUidRxBytes(uid)
                val activity = startActivitySync(Intent(targetContext, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                runOnMainSync {
                    activity.window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                    if (blockWebNetwork) {
                        val queue = java.util.ArrayDeque<android.view.View>()
                        queue.add(activity.window.decorView)
                        var found = false
                        while (queue.isNotEmpty()) {
                            val view = queue.removeFirst()
                            if (view is android.webkit.WebView) { view.settings.blockNetworkLoads = true; found = true }
                            if (view is android.view.ViewGroup) for (i in 0 until view.childCount) queue.add(view.getChildAt(i))
                        }
                        check(found)
                    }
                }
                val finished = File(root, "planner-finished")
                check(!finished.exists())
                val deadline = SystemClock.elapsedRealtime() + 20 * 60 * 1_000
                val ready = File(root, "planner-ready")
                while (!ready.exists() && SystemClock.elapsedRealtime() < deadline) SystemClock.sleep(200)
                check(ready.isFile) { "planner ready deadline" }
                val tx = TrafficStats.getUidTxBytes(uid)
                val rx = TrafficStats.getUidRxBytes(uid)
                while (!finished.exists() && SystemClock.elapsedRealtime() < deadline) SystemClock.sleep(200)
                check(finished.isFile) { "planner acceptance harness deadline" }
                val txDelta = TrafficStats.getUidTxBytes(uid) - tx
                val rxDelta = TrafficStats.getUidRxBytes(uid) - rx
                File(root, "planner-result.json").writeText(JSONObject().put("publication_allowed", false)
                    .put("normal_generate_workflow", true).put("webview_network_loads_blocked", blockWebNetwork).put("uid_tx_delta_bytes", txDelta).put("uid_rx_delta_bytes", rxDelta)
                    .put("startup_uid_tx_delta_bytes", tx - startupTx).put("startup_uid_rx_delta_bytes", rx - startupRx)
                    .put("initial_uid_tx_bytes", tx).put("initial_uid_rx_bytes", rx)
                    .put("pss_final_bytes", pss()).toString())
                check(tx >= 0 && rx >= 0 && txDelta == 0L && rxDelta == 0L) { "planner network counters: tx=$txDelta rx=$rxDelta" }
                runOnMainSync { activity.finish() }
                summary.putString("stream", "V2 planner acceptance passed\n")
                finish(Activity.RESULT_OK, summary)
                return
            }
            if (phase == "installer") {
                // Keep the explicitly instrumented process eligible to execute
                // its real WebView/installer while the device is locked. This
                // does not dismiss authentication or install any files itself.
                val activity = startActivitySync(Intent(targetContext, MainActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                val finished = File(root, "installer-finished")
                check(!finished.exists())
                val deadline = SystemClock.elapsedRealtime() + 10 * 60 * 1_000
                while (!finished.exists() && SystemClock.elapsedRealtime() < deadline) SystemClock.sleep(200)
                check(finished.isFile) { "installer harness deadline" }
                File(root, "installer-result.json").writeText(JSONObject().put("publication_allowed", false)
                    .put("installer_harness_completed", true).toString())
                runOnMainSync { activity.finish() }
                summary.putString("stream", "V2 installer acceptance passed\n")
                finish(Activity.RESULT_OK, summary)
                return
            }
            val referenceFile = File(root, "reference.json")
            check(referenceFile.length() in 1..16_384)
            val reference = requireNotNull(RegionalRoutingPackReference.parse(JSONObject(referenceFile.readText())))
            val application = targetContext.applicationContext as SugargliderApplication
            val engine = application.nativeOfflineEngine
            val uid = Process.myUid()
            val tx = TrafficStats.getUidTxBytes(uid)
            val rx = TrafficStats.getUidRxBytes(uid)
            val started = SystemClock.elapsedRealtime()
            val initialPss = pss()
            val output = JSONObject().put("publication_allowed", false).put("reference", reference.toJson())
            if (phase == "endurance") {
                output.put("endurance", V2EnduranceReview.run(application, root, reference))
            } else if (phase == "analysis") {
                // Synthetic coverage/gap/limit fixtures on the physical runtime;
                // never alter installed DEM or substitute heights in the planner.
                val results = JSONArray()
                for (file in listOf("contract-v1.json", "runtime-v1.json")) {
                    val cases = JSONArray(context.assets.open(file).bufferedReader().use { it.readText() })
                    for (index in 0 until cases.length()) {
                        val fixture = cases.getJSONObject(index)
                        val input = fixture.getJSONObject("input")
                        val rows = input.getJSONArray("samples")
                        val points = (0 until rows.length()).map { i -> rows.getJSONObject(i).let { row ->
                            ElevationPoint(row.getInt("index"), row.getDouble("distance_m"), if (row.isNull("height_m")) null else row.getDouble("height_m")) } }
                        val profile = ElevationInput(input.getString("source_sha256"), input.getString("geometry_sha256"), input.getString("routing_profile"),
                            input.getDouble("route_distance_m"), input.getString("height_reference"), points)
                        val policy = fixture.getJSONObject("parameters")
                        val result = DistanceBoxElevation.analyze(profile, ElevationPolicy(policy.getDouble("smoothing_radius_m"), policy.getDouble("maximum_gap_m")))
                        check(result.getString("profile_sha256") == fixture.getJSONObject("expected").getString("profile_sha256"))
                        results.put(JSONObject().put("name", fixture.getString("name")).put("analysis", result))
                    }
                }
                output.put("synthetic_analysis_fixtures", results)
            } else if (phase == "routes") {
                val results = JSONArray()
                // Public test endpoints on real graph vertices shared by all six profiles.
                val start = LocalRouteCoordinate(48.871281, 2.095997)
                val via = LocalRouteCoordinate(48.8840, 2.0830)
                val end = LocalRouteCoordinate(48.889384, 2.099125)
                for (profile in LocalRouteProfile.entries) for (loop in listOf(false, true)) {
                    val points = if (loop) listOf(start, via, end, start) else listOf(start, end)
                    val result = engine.route(NativeRouteRequest(LOCAL_ROUTE_REQUEST_VERSION,
                        "v2-${profile.wireValue}-${if (loop) "loop" else "open"}", points, profile, reference))
                    check(result is NativeRouteResult.Success) { "routing failed: $profile loop=$loop $result" }
                    check(result.engineVersion == "0.6.4/valhalla-3.9.1" && result.packId == reference.packId && result.isValid())
                    check(result.snappedPoints.size == points.size)
                    val snapOffsets = points.zip(result.snappedPoints).map { (requested, snapped) -> distanceMeters(requested, snapped) }
                    check(snapOffsets.all { it <= 25.0 }) { "test point exceeded 25 m: $snapOffsets" }
                    if (loop) check(result.geometry.first() == result.geometry.last())
                    results.put(JSONObject().put("profile", profile.wireValue).put("loop", loop)
                        .put("distance_m", result.distanceMeters).put("duration_s", result.durationSeconds)
                        .put("requested_points", coordinates(points)).put("snap_distances_m", JSONArray(snapOffsets))
                        .put("geometry", coordinates(result.geometry)).put("snapped_points", coordinates(result.snappedPoints))
                        .put("cold_start", result.measurements.coldStart).put("initialization_ms", result.measurements.engineInitializationMs)
                        .put("route_ms", result.measurements.routeMs).put("pss_bytes", result.measurements.memoryAfterRouteBytes))
                }
                output.put("routes", results)
                // The persistent actor's lease must prevent file removal.
                check(runCatching { application.regionalRoutingRepository.remove(reference) }.exceptionOrNull()
                    .let { it is RegionalPackException && it.code == RegionalPackFailure.BUSY })
                output.put("active_actor_removal_blocked", true)
            } else if (phase == "height") {
                val input = File(root, "height-plan.json")
                check(input.length() in 1..1_048_576)
                val plan = JSONObject(input.readText())
                val rows = plan.getJSONArray("points")
                check(rows.length() in 2..MAX_NATIVE_HEIGHT_SAMPLES)
                val points = (0 until rows.length()).map { index -> rows.getJSONObject(index).let {
                    LocalRouteCoordinate(it.getDouble("lat"), it.getDouble("lon")) } }
                val coldStarted = SystemClock.elapsedRealtime()
                val values = engine.height(reference, points, "installed-route")
                val coldTotalMs = SystemClock.elapsedRealtime() - coldStarted
                check(values is NativeHeightResult.Success && values.heights.size == points.size)
                val warm = engine.height(reference, points, "installed-route-warm")
                check(warm is NativeHeightResult.Success && warm.heights == values.heights && !warm.coldStart)
                output.put("heights", nullable(values.heights)).put("cold_ms", values.elapsedMs).put("cold_total_ms", coldTotalMs).put("warm_ms", warm.elapsedMs)
                val repeated = JSONArray()
                repeat(20) { index ->
                    val next = engine.height(reference, points, "repeat-$index")
                    check(next is NativeHeightResult.Success && next.reference == reference && next.heights == values.heights && !next.coldStart)
                    repeated.put(JSONObject().put("ms", next.elapsedMs).put("pss_bytes", next.pssBytes))
                }
                output.put("repeated_heights", repeated)
                // API-budget stress fixture derived from actual sampled points;
                // this repeated shape is not published as a routed profile.
                val budgetPoints = List(MAX_NATIVE_HEIGHT_SAMPLES) { points[it % points.size] }
                val budget = engine.height(reference, budgetPoints, "sample-budget")
                check(budget is NativeHeightResult.Success && budget.heights.size == MAX_NATIVE_HEIGHT_SAMPLES)
                check(budget.heights.indices.all { budget.heights[it] == values.heights[it % points.size] })
                check(engine.height(reference, budgetPoints + points.first(), "over-budget") is NativeHeightResult.Failure)
                check(engine.height(reference, listOf(LocalRouteCoordinate(Double.NaN, 2.0)), "invalid-coordinate") is NativeHeightResult.Failure)
                output.put("budget_sample_count", budget.heights.size).put("budget_ms", budget.elapsedMs)
                engine.close()
                val reopened = engine.height(reference, points, "reopened")
                check(reopened is NativeHeightResult.Success && reopened.coldStart && reopened.heights == values.heights)
                output.put("closed_actor_reopened", true)
                val fixtures = listOf(LocalRouteCoordinate(48.5, 1.5), LocalRouteCoordinate(48.5, 2.1),
                    LocalRouteCoordinate(49.05, 1.5), LocalRouteCoordinate(49.05, 2.1),
                    LocalRouteCoordinate(49.0, 2.0), LocalRouteCoordinate(48.5, 3.0), LocalRouteCoordinate(50.0, 2.1))
                val boundary = engine.height(reference, fixtures, "tile-boundaries")
                check(boundary is NativeHeightResult.Success)
                check(boundary.heights.take(5).all { it != null } && boundary.heights.drop(5).all { it == null })
                output.put("fixture_coordinates", coordinates(fixtures)).put("fixture_heights", nullable(boundary.heights))
                check(engine.height(reference, emptyList(), "empty") is NativeHeightResult.Failure)
                val wrong = reference.copy(elevation = reference.elevation.copy(componentId = "wrong-component"))
                check(engine.height(wrong, points, "wrong-component") is NativeHeightResult.Failure)
                check(engine.height(reference.copy(buildId = "f".repeat(64)), points, "wrong-build") is NativeHeightResult.Failure)
                output.put("invalid_and_wrong_identity_rejected", true).put("pss_after_height_bytes", pss())
            } else if (phase == "void") {
                // Synthetic JNI fixtures, never installed regional data.
                val missingDirectory = File(root, "synthetic-missing").apply { check(mkdir()) }
                val voidDirectory = File(root, "synthetic-void").apply { check(mkdir()) }
                val tile = File(voidDirectory, "N48/N48E002.hgt.gz").apply { check(parentFile!!.mkdir()) }
                GZIPOutputStream(tile.outputStream()).use { compressed ->
                    val buffer = ByteArray(64 * 1024) { if (it % 2 == 0) 0x80.toByte() else 0 }
                    var remaining = HGT_DECODED_BYTES
                    while (remaining > 0) { val count = minOf(remaining, buffer.size.toLong()).toInt(); compressed.write(buffer, 0, count); remaining -= count }
                }
                val points = listOf(LocalRouteCoordinate(48.8715, 2.0965), LocalRouteCoordinate(48.8983, 2.0969))
                NativeHeightResearch(missingDirectory, File(root, "missing.json")).use {
                    check(it.sample(points, "synthetic-missing").all { value -> value == null })
                }
                NativeHeightResearch(voidDirectory, File(root, "void.json")).use {
                    check(it.sample(points, "synthetic-void").all { value -> value == null })
                    check(runCatching { it.malformedRequest() }.isFailure)
                }
                output.put("synthetic_missing_and_void_remain_null", true).put("malformed_native_json_rejected", true)
            } else if (phase == "switch") {
                val second = requireNotNull(RegionalRoutingPackReference.parse(JSONObject(File(root, "reference-control.json").readText())))
                check(second.regionId != reference.regionId && second.buildId != reference.buildId)
                val results = JSONArray()
                for ((index, selected) in listOf(reference, second, second, reference).withIndex()) {
                    val points = listOf(LocalRouteCoordinate(48.8715, 2.0965), LocalRouteCoordinate(48.8983, 2.0969))
                    val route = engine.route(NativeRouteRequest(LOCAL_ROUTE_REQUEST_VERSION, "switch-$index", points, LocalRouteProfile.HIKE, selected))
                    check(route is NativeRouteResult.Success && route.isValid() && route.packId == selected.packId)
                    val heights = engine.height(selected, points, "switch-height-$index")
                    check(heights is NativeHeightResult.Success && heights.reference == selected && heights.heights.all { it != null })
                    check(route.measurements.coldStart == (index != 2) && !heights.coldStart)
                    results.put(JSONObject().put("region_id", selected.regionId).put("build_id", selected.buildId)
                        .put("cold_start", route.measurements.coldStart).put("route_ms", route.measurements.routeMs)
                        .put("pss_bytes", pss()).put("heights", nullable(heights.heights)))
                }
                output.put("region_switches", results)
            } else error("unknown research phase")
            output.put("pss_before_close_bytes", pss())
            engine.close()
            output.put("pss_after_close_bytes", pss()).put("pss_initial_bytes", initialPss)
                .put("elapsed_ms", SystemClock.elapsedRealtime() - started)
                .put("uid_tx_delta_bytes", TrafficStats.getUidTxBytes(uid) - tx)
                .put("uid_rx_delta_bytes", TrafficStats.getUidRxBytes(uid) - rx)
            if (phase != "installer") {
                check(tx >= 0 && rx >= 0 && output.getLong("uid_tx_delta_bytes") == 0L && output.getLong("uid_rx_delta_bytes") == 0L)
            }
            File(root, "$phase-result.json").writeText(output.toString())
            summary.putString("stream", "V2 $phase acceptance passed\n")
            finish(Activity.RESULT_OK, summary)
        } catch (error: Throwable) {
            summary.putString("stream", "V2 acceptance failed: ${error.javaClass.name}: ${error.message}\n" + error.stackTraceToString())
            finish(Activity.RESULT_CANCELED, summary)
        }
    }

    private fun distanceMeters(first: LocalRouteCoordinate, second: LocalRouteCoordinate): Double {
        val firstLatitude = Math.toRadians(first.latitude)
        val secondLatitude = Math.toRadians(second.latitude)
        val latitudeDelta = secondLatitude - firstLatitude
        val longitudeDelta = Math.toRadians(second.longitude - first.longitude)
        val halfChord = sin(latitudeDelta / 2) * sin(latitudeDelta / 2) +
            cos(firstLatitude) * cos(secondLatitude) * sin(longitudeDelta / 2) * sin(longitudeDelta / 2)
        return 6_371_008.8 * 2 * asin(sqrt(halfChord.coerceIn(0.0, 1.0)))
    }

    private fun coordinates(points: List<LocalRouteCoordinate>): JSONArray = JSONArray(points.map {
        JSONArray(listOf(it.longitude, it.latitude)) })
    private fun nullable(heights: List<Double?>): JSONArray = JSONArray(heights.map { it ?: JSONObject.NULL })
    private fun pss(): Long = Debug.getPss() * 1_024L
}
