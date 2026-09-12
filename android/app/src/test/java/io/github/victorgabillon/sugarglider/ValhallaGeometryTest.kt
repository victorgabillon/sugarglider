package io.github.victorgabillon.sugarglider

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ValhallaGeometryTest {
    @Test
    fun polyline6DecoderRejectsMalformedAndDecodesGraphShape() {
        val decoded = decodePolyline6("_izlhA~rlgdF_{geC~ywl@_kwzCn`{nI")
        assertEquals(3, decoded.size)
        assertEquals(38.5, decoded[0].latitude, 0.000001)
        assertEquals(-120.2, decoded[0].longitude, 0.000001)
        assertTrue(runCatching { decodePolyline6("") }.isFailure)
        assertTrue(runCatching { decodePolyline6("_") }.isFailure)
    }

    @Test
    fun multiLegGeometryDeduplicatesOnlyTheSharedGraphBoundary() {
        val a = LocalRouteCoordinate(48.0, 2.0)
        val b = LocalRouteCoordinate(48.1, 2.1)
        val c = LocalRouteCoordinate(48.2, 2.2)
        val d = LocalRouteCoordinate(48.3, 2.3)
        val joined = joinLocalRouteLegGeometries(
            listOf(listOf(a, b, c), listOf(c, d)),
        )
        assertEquals(listOf(a, b, c, d), joined.geometry)
        assertEquals(listOf(a, c, d), joined.snappedPoints)
        assertTrue(
            runCatching {
                joinLocalRouteLegGeometries(listOf(listOf(a, b), listOf(c, d)))
            }.isFailure,
        )
    }

}
