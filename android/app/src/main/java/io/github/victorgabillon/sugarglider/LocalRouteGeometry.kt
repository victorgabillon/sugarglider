package io.github.victorgabillon.sugarglider

internal fun decodePolyline6(shape: String): List<LocalRouteCoordinate> {
    if (shape.isEmpty()) throw IllegalArgumentException("empty polyline")
    val coordinates = mutableListOf<LocalRouteCoordinate>()
    var index = 0
    var latitude = 0
    var longitude = 0
    while (index < shape.length) {
        val latitudeDelta = decodePolylineValue(shape, index)
        index = latitudeDelta.nextIndex
        val longitudeDelta = decodePolylineValue(shape, index)
        index = longitudeDelta.nextIndex
        latitude += latitudeDelta.value
        longitude += longitudeDelta.value
        val coordinate = LocalRouteCoordinate(
            latitude = latitude / 1_000_000.0,
            longitude = longitude / 1_000_000.0,
        )
        if (!coordinate.isValid()) throw IllegalArgumentException("invalid polyline coordinate")
        coordinates += coordinate
        if (coordinates.size > MAX_LOCAL_ROUTE_VERTICES) {
            throw LocalRouteTooLargeException()
        }
    }
    return coordinates
}

internal data class JoinedLocalRouteGeometry(
    val geometry: List<LocalRouteCoordinate>,
    val snappedPoints: List<LocalRouteCoordinate>,
)

internal fun joinLocalRouteLegGeometries(
    legs: List<List<LocalRouteCoordinate>>,
): JoinedLocalRouteGeometry {
    if (legs.isEmpty()) throw IllegalArgumentException("route has no legs")
    val geometry = mutableListOf<LocalRouteCoordinate>()
    val snappedPoints = mutableListOf<LocalRouteCoordinate>()
    legs.forEachIndexed { index, leg ->
        if (leg.size < 2 || !leg.all(LocalRouteCoordinate::isValid)) {
            throw IllegalArgumentException("invalid route leg")
        }
        if (index == 0) {
            geometry += leg
            snappedPoints += leg.first()
        } else {
            if (geometry.last() != leg.first()) {
                throw IllegalArgumentException("disconnected route legs")
            }
            geometry += leg.drop(1)
        }
        snappedPoints += leg.last()
        if (geometry.size > MAX_LOCAL_ROUTE_VERTICES) {
            throw LocalRouteTooLargeException()
        }
    }
    return JoinedLocalRouteGeometry(geometry, snappedPoints)
}

internal class LocalRouteTooLargeException : IllegalArgumentException("route exceeds vertex limit")

private data class DecodedPolylineValue(val value: Int, val nextIndex: Int)

private fun decodePolylineValue(shape: String, startIndex: Int): DecodedPolylineValue {
    var index = startIndex
    var result = 0
    var shift = 0
    var chunk: Int
    do {
        if (index >= shape.length || shift > 30) throw IllegalArgumentException("invalid polyline")
        chunk = shape[index].code - 63
        if (chunk !in 0..63) throw IllegalArgumentException("invalid polyline")
        index += 1
        result = result or ((chunk and 0x1f) shl shift)
        shift += 5
    } while (chunk >= 0x20)
    val value = if ((result and 1) != 0) (result shr 1).inv() else result shr 1
    return DecodedPolylineValue(value, index)
}
