package io.github.victorgabillon.sugarglider

import android.app.Activity
import android.app.Instrumentation
import android.net.TrafficStats
import android.os.Bundle
import android.os.Debug
import android.os.Process
import android.os.SystemClock
import com.valhalla.valhalla.ValhallaException
import java.io.File
import java.security.MessageDigest
import org.json.JSONArray
import org.json.JSONObject

/** Real JNI integration test. Input DEM/route files are supplied explicitly. */
class HeightResearchInstrumentation : Instrumentation() {
    private lateinit var researchId: String
    private var calls = 0
    private var nativeElapsedMs = 0L
    private val measurements = JSONArray()

    override fun onCreate(arguments: Bundle?) {
        super.onCreate(arguments)
        researchId = arguments?.getString("research_id").orEmpty()
        start()
    }

    override fun onStart() {
        val result = Bundle()
        try {
            check(BuildConfig.DEBUG)
            require(researchId.matches(Regex("[a-z0-9-]{1,64}")))
            val root = File(targetContext.cacheDir, researchId).canonicalFile
            require(root.parentFile == targetContext.cacheDir.canonicalFile && root.isDirectory)
            val inputFile = File(root, "plan.json")
            require(inputFile.length() in 1..1_048_576)
            val input = JSONObject(inputFile.readText())
            require(input.getInt("schema_version") == 1 && !input.getBoolean("publication_allowed"))
            val sourceSha = input.getString("source_sha256")
            require(sourceSha.matches(Regex("[0-9a-f]{64}")))
            val realDirectory = File(root, "real")
            val tile = File(realDirectory, "N48/N48E002.hgt.gz")
            require(tile.canonicalFile.toPath().startsWith(root.toPath()))
            require(sha256(tile) == sourceSha)
            val points = coordinates(input.getJSONArray("points"))
            val fixture = listOf(
                LocalRouteCoordinate(48.8715, 2.0965),
                LocalRouteCoordinate(48.8983, 2.0969),
                LocalRouteCoordinate(48.8840, 2.0830),
            )
            val uid = Process.myUid()
            val txBefore = TrafficStats.getUidTxBytes(uid)
            val rxBefore = TrafficStats.getUidRxBytes(uid)
            val initialPss = pssBytes()
            val actorStarted = SystemClock.elapsedRealtime()
            val native = NativeHeightResearch(realDirectory, File(root, "real-actor.json"))
            val initializationMs = SystemClock.elapsedRealtime() - actorStarted
            val initializedPss = pssBytes()
            val cold: List<Double?>
            val fixtures: List<Double?>
            val outside: List<Double?>
            var malformedCode = ""
            native.use { engine ->
                cold = measure(engine, points, "route-cold")
                val warm = measure(engine, points, "route-warm")
                require(warm == cold)
                fixtures = measure(engine, fixture, "known-fixtures")
                require(fixtures.all { it != null })
                outside = measure(engine, listOf(
                    fixture.first(), LocalRouteCoordinate(48.87, 1.99),
                    LocalRouteCoordinate(49.0, 2.1), LocalRouteCoordinate(48.87, 3.0),
                ), "missing-neighbors")
                require(outside.first() != null && outside.drop(1).all { it == null })
                reserve()
                val started = SystemClock.elapsedRealtime()
                try {
                    engine.malformedRequest()
                    error("native accepted malformed JSON")
                } catch (error: ValhallaException.Internal) {
                    malformedCode = error.message.orEmpty()
                } finally { recordTime(started) }
            }
            val closedPss = pssBytes()
            val emptyDirectory = File(root, "empty")
            require(emptyDirectory.isDirectory && emptyDirectory.listFiles()?.isEmpty() == true)
            val missing = NativeHeightResearch(emptyDirectory, File(root, "empty-actor.json")).use {
                measure(it, fixture, "missing-tile")
            }
            require(missing.all { it == null })
            val voidDirectory = File(root, "void")
            val void = NativeHeightResearch(voidDirectory, File(root, "void-actor.json")).use {
                measure(it, fixture, "synthetic-void")
            }
            require(void.all { it == null })
            // Bounds and malformed local input reject before a JNI request.
            require(runCatching { localValhallaHeightRequest(emptyList(), "empty") }.isFailure)
            require(runCatching {
                localValhallaHeightRequest(List(MAX_RESEARCH_HEIGHT_SAMPLES + 1) { fixture.first() }, "oversized")
            }.isFailure)
            val txAfter = TrafficStats.getUidTxBytes(uid)
            val rxAfter = TrafficStats.getUidRxBytes(uid)
            require(txBefore >= 0 && rxBefore >= 0 && txAfter == txBefore && rxAfter == rxBefore)
            val output = JSONObject()
                .put("source_sha256", sourceSha).put("input_sha256", sha256(inputFile))
                .put("heights", nullableArray(cold))
            File(root, "native-result.json").writeText(output.toString())
            val diagnostics = JSONObject()
                .put("engine_version", "0.6.4/valhalla-3.9.1")
                .put("sample_count", cold.size).put("native_call_count", calls).put("native_call_limit", 8)
                .put("native_elapsed_ms", nativeElapsedMs).put("maximum_call_ms", MAX_RESEARCH_HEIGHT_CALL_MS)
                .put("initialization_ms", initializationMs).put("measurements", measurements)
                .put("pss_initial_bytes", initialPss).put("pss_initialized_bytes", initializedPss)
                .put("pss_after_real_close_bytes", closedPss).put("pss_final_bytes", pssBytes())
                .put("fixtures", nullableArray(fixtures)).put("missing_neighbors", nullableArray(outside))
                .put("missing_tile", nullableArray(missing)).put("synthetic_void", nullableArray(void))
                .put("malformed_native_error", malformedCode)
                .put("uid_tx_delta_bytes", txAfter - txBefore).put("uid_rx_delta_bytes", rxAfter - rxBefore)
                .put("publication_allowed", false)
            File(root, "diagnostics.json").writeText(diagnostics.toString(2))
            result.putString("stream", "Native height research passed: ${cold.size} samples; $calls native calls.\n")
            finish(Activity.RESULT_OK, result)
        } catch (error: Exception) {
            result.putString("stream", "Native height research failed: ${error.javaClass.name}: ${error.message}\n")
            finish(Activity.RESULT_CANCELED, result)
        }
    }

    private fun coordinates(values: JSONArray): List<LocalRouteCoordinate> {
        require(values.length() in 2..MAX_RESEARCH_HEIGHT_SAMPLES)
        return List(values.length()) { index ->
            val value = values.getJSONObject(index)
            require(value.getInt("index") == index)
            LocalRouteCoordinate(value.getDouble("lat"), value.getDouble("lon"))
        }.also { require(it.all(LocalRouteCoordinate::isValid)) }
    }

    private fun measure(engine: NativeHeightResearch, points: List<LocalRouteCoordinate>, id: String): List<Double?> {
        reserve()
        val started = SystemClock.elapsedRealtime()
        val heights = engine.sample(points, id)
        val elapsed = recordTime(started)
        measurements.put(JSONObject().put("id", id).put("elapsed_ms", elapsed).put("pss_bytes", pssBytes()))
        return heights
    }

    private fun reserve() { check(calls < 8); calls += 1 }

    private fun recordTime(started: Long): Long {
        val elapsed = SystemClock.elapsedRealtime() - started
        nativeElapsedMs += elapsed
        require(elapsed <= MAX_RESEARCH_HEIGHT_CALL_MS && nativeElapsedMs <= 20_000)
        return elapsed
    }

    private fun pssBytes(): Long = Debug.getPss() * 1_024L

    private fun nullableArray(values: List<Double?>): JSONArray = JSONArray().also { array ->
        values.forEach { array.put(it ?: JSONObject.NULL) }
    }

    private fun sha256(file: File): String {
        val hash = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { stream ->
            val buffer = ByteArray(64 * 1_024)
            while (true) { val count = stream.read(buffer); if (count < 0) break; hash.update(buffer, 0, count) }
        }
        return hash.digest().joinToString("") { "%02x".format(it) }
    }
}
