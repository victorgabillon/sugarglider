package io.github.victorgabillon.sugarglider

import com.valhalla.valhalla.Valhalla
import java.io.Closeable
import java.io.File
import org.json.JSONObject

internal const val MAX_RESEARCH_HEIGHT_SAMPLES = 2_048
internal const val MAX_RESEARCH_HEIGHT_CALL_MS = 5_000L

/** Explicit instrumentation only. No UI, bridge, startup or routing caller. */
internal class NativeHeightResearch(
    elevationDirectory: File,
    private val configurationFile: File,
) : Closeable {
    private val valhalla: Valhalla

    init {
        check(BuildConfig.DEBUG)
        require(elevationDirectory.isDirectory)
        require(!configurationFile.exists())
        configurationFile.writeText(researchHeightConfiguration(elevationDirectory).toString())
        try {
            // The path constructor avoids overwriting the app's valhalla.json.
            valhalla = Valhalla(configurationFile.absolutePath)
        } catch (error: Exception) {
            configurationFile.delete()
            throw error
        }
    }

    fun sample(points: List<LocalRouteCoordinate>, id: String): List<Double?> {
        val request = localValhallaHeightRequest(points, id)
        return localValhallaHeightValues(request, valhalla.height(request))
    }

    // Deliberately invalid native wire requests belong only to the test suite.
    internal fun malformedRequest(): String = valhalla.heightRaw("{not-json")

    override fun close() {
        try { valhalla.close() }
        finally { configurationFile.delete() }
    }
}

internal fun researchHeightConfiguration(elevationDirectory: File): JSONObject =
    offlineValhallaJson(localValhallaConfiguration(null, elevationDirectory))
