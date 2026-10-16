package io.github.victorgabillon.sugarglider

import android.os.Debug
import android.os.SystemClock
import java.io.File
import org.json.JSONArray
import org.json.JSONObject

/** Opt-in physical review of two already-installed regions. Never installs or removes files. */
internal object V2EnduranceReview {
    fun run(application: SugargliderApplication, root: File, first: RegionalRoutingPackReference): JSONObject {
        val second = requireNotNull(RegionalRoutingPackReference.parse(
            JSONObject(File(root, "reference-control.json").readText())))
        check(first.regionId != second.regionId && first.buildId != second.buildId)
        check(first.archive.sha256 != second.archive.sha256) { "Distinct graph bytes required" }
        val engine = application.nativeOfflineEngine
        val repository = application.regionalRoutingRepository
        val points = listOf(LocalRouteCoordinate(48.871281, 2.095997),
            LocalRouteCoordinate(48.8840, 2.0830), LocalRouteCoordinate(48.889384, 2.099125))
        val rows = JSONArray()
        val started = SystemClock.elapsedRealtime()
        fun record(phase: String, selected: RegionalRoutingPackReference? = null): JSONObject {
            val maps = File("/proc/self/maps").readLines().filter { "/regional-routing-packs/" in it }
            val paths = maps.map { it.substringAfter("/regional-routing-packs/") }.distinct().sorted()
            if (selected == null) check(paths.isEmpty()) { "Native mappings survived actor close" }
            else {
                val prefix = "${selected.regionId}/${selected.buildId}/${selected.packId}/"
                check(paths.isNotEmpty() && paths.all { it.startsWith(prefix) }) { "Cross-region native mappings" }
            }
            val runtime = Runtime.getRuntime()
            val value = JSONObject().put("phase", phase).put("elapsed_ms", SystemClock.elapsedRealtime() - started)
                .put("main_pss_bytes", Debug.getPss() * 1024L)
                .put("native_heap_allocated_bytes", Debug.getNativeHeapAllocatedSize())
                .put("java_heap_used_bytes", runtime.totalMemory() - runtime.freeMemory())
                .put("native_mapping_paths", JSONArray(paths)).put("native_mapping_count", maps.size)
                .put("thread_count", File("/proc/self/task").list()?.size)
            rows.put(value)
            // Persist progress so a process failure does not erase earlier measurements.
            File(root, "endurance-progress.json").writeText(rows.toString())
            return value
        }
        engine.close()
        record("initial-closed")
        val expectedHeights = mutableMapOf<String, List<Double?>>()
        var previous: RegionalRoutingPackReference? = null
        repeat(40) { index ->
            val selected = listOf(first, second, second, first)[index % 4]
            val result = engine.route(NativeRouteRequest(LOCAL_ROUTE_REQUEST_VERSION,
                "endurance-$index", points, LocalRouteProfile.HIKE, selected))
            check(result is NativeRouteResult.Success && result.isValid() && result.packId == selected.packId)
            check(result.measurements.coldStart == (previous != selected))
            if (index < 2) record("route-before-height-$index", selected)
            val height = engine.height(selected, points, "endurance-height-$index")
            check(height is NativeHeightResult.Success && height.reference == selected && !height.coldStart)
            check(height.heights.all { it != null })
            expectedHeights[selected.regionId]?.let { check(height.heights == it) }
            expectedHeights[selected.regionId] = height.heights
            val warm = engine.height(selected, points, "endurance-warm-$index")
            check(warm is NativeHeightResult.Success && warm.heights == height.heights && !warm.coldStart)
            // Same local point, different DEM coverage: Marly has only N48E002,
            // while Yvelines also owns N48E001. Never treat absence as sea level.
            val boundary = engine.height(selected, listOf(LocalRouteCoordinate(48.5, 1.5)), "endurance-coverage-$index")
            check(boundary is NativeHeightResult.Success)
            val covered = selected.elevation.tiles.any { it.path == "skadi/N48/N48E001.hgt.gz" }
            check((boundary.heights.single() != null) == covered)
            // Attempt through the repository: BUSY must precede any file mutation.
            check(runCatching { repository.remove(selected) }.exceptionOrNull().let {
                it is RegionalPackException && it.code == RegionalPackFailure.BUSY })
            record("active-$index", selected).put("cold_start", result.measurements.coldStart)
                .put("route_distance_m", result.distanceMeters).put("height_values", JSONArray(height.heights))
            SystemClock.sleep(15_000)
            record("steady-$index", selected)
            previous = selected
        }
        engine.close()
        record("post-close")
        repeat(4) { SystemClock.sleep(30_000); record("closed-idle-$it") }
        // Restart the exact first region after cleanup, then leave no actor behind.
        val reopened = engine.height(first, points, "endurance-reopen")
        check(reopened is NativeHeightResult.Success && reopened.coldStart)
        check(reopened.heights == expectedHeights[first.regionId])
        record("reopened", first)
        engine.close()
        record("final-closed")
        return JSONObject().put("rows", rows).put("iterations", 40)
            .put("distinct_graphs", true).put("active_removal_blocked", true)
            .put("closed_mapping_count", 0).put("elapsed_ms", SystemClock.elapsedRealtime() - started)
    }
}
