package io.github.victorgabillon.sugarglider

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ElevationAnalysisTest {
    @Test fun portablePythonGoldenContracts() {
        for (file in listOf("contract-v1.json", "runtime-v1.json")) {
            val cases = JSONArray(requireNotNull(javaClass.classLoader!!.getResourceAsStream(file)).bufferedReader().use { it.readText() })
            for (index in 0 until cases.length()) {
                val case = cases.getJSONObject(index); val input = case.getJSONObject("input"); val rows = input.getJSONArray("samples")
                val profile = ElevationInput(input.getString("source_sha256"), input.getString("geometry_sha256"), input.getString("routing_profile"),
                    input.getDouble("route_distance_m"), input.getString("height_reference"), (0 until rows.length()).map { i ->
                        val row = rows.getJSONObject(i); ElevationPoint(row.getInt("index"), row.getDouble("distance_m"), if (row.isNull("height_m")) null else row.getDouble("height_m")) })
                val policy = case.getJSONObject("parameters")
                compare(case.getJSONObject("expected"), DistanceBoxElevation.analyze(profile, ElevationPolicy(policy.getDouble("smoothing_radius_m"), policy.getDouble("maximum_gap_m"))), case.getString("name"))
            }
        }
    }
    @Test fun rejectsInvalidProgressAndMissingIsNotZero() {
        fun input(points: List<ElevationPoint>) = ElevationInput("a".repeat(64),"b".repeat(64),"hike",100.0,"fixture",points)
        for (points in listOf(listOf(ElevationPoint(0,0.0,1.0),ElevationPoint(1,0.0,2.0)),
            listOf(ElevationPoint(0,0.0,Double.NaN),ElevationPoint(1,100.0,2.0)),
            listOf(ElevationPoint(0,1.0,1.0),ElevationPoint(1,100.0,2.0)))) assertTrue(runCatching { input(points) }.isFailure)
        val absent=DistanceBoxElevation.analyze(input(listOf(ElevationPoint(0,0.0,null),ElevationPoint(1,100.0,null))))
        assertEquals("unavailable",absent.getString("coverage")); assertTrue(absent.isNull("total_ascent_m")); assertTrue(absent.isNull("minimum_height_m"))
    }
    private fun compare(expected: Any, actual: Any, path: String) {
        when(expected) {
            is JSONObject -> { assertTrue(path,actual is JSONObject); actual as JSONObject
                assertEquals(path,expected.keys().asSequence().toSet(),actual.keys().asSequence().toSet())
                expected.keys().forEach { key -> compare(expected.get(key),actual.get(key),"$path.$key") } }
            is JSONArray -> { assertTrue(path,actual is JSONArray);actual as JSONArray; assertEquals(path,expected.length(),actual.length());for(i in 0 until expected.length())compare(expected.get(i),actual.get(i),"$path[$i]") }
            is Number -> { assertTrue(path,actual is Number);assertEquals(path,expected.toDouble(),(actual as Number).toDouble(),1e-7) }
            else -> assertEquals(path,expected,actual)
        }
    }
}
