package io.github.victorgabillon.sugarglider

import android.content.Context
import android.os.Debug
import android.os.SystemClock
import com.valhalla.api.models.CostingModel
import com.valhalla.api.models.DirectionsOptions
import com.valhalla.api.models.RouteRequest
import com.valhalla.api.models.RoutingWaypoint
import com.valhalla.config.ValhallaConfigBuilder
import com.valhalla.valhalla.Valhalla
import com.valhalla.valhalla.ValhallaException
import com.valhalla.valhalla.ValhallaResponse
import java.io.File

internal object NativeRouteEngineFactory {
    fun create(context: Context): NativeRouteEngine = ValhallaMobileRouteEngine(context)
}

private class ValhallaMobileRouteEngine(context: Context) : NativeRouteEngine {
    private val applicationContext = context.applicationContext
    private val registry = RoutingPackRegistry(
        File(
            applicationContext.filesDir,
            "routing-packs",
        ),
    )
    private val actorHolder = SingleCurrentRoutingPackActor(
        ::initializeActor,
    )

    override fun capabilities(): NativeRouteCapabilities {
        val installedPackIds = registry.installedPacks()
            .map(RoutingPack::packId)
        return NativeRouteCapabilities(
            enabled = BuildConfig.LOCAL_ROUTING_EXPERIMENT,
            engine = ENGINE_ID,
            engineVersion = ENGINE_VERSION,
            installedPackIds = installedPackIds,
        )
    }

    @Synchronized
    override fun route(request: NativeRouteRequest): NativeRouteResult {
        if (!request.isValid()) {
            return NativeRouteResult.Failure(NativeRouteFailureCode.INVALID_REQUEST)
        }
        if (request.profile != LocalRouteProfile.HIKE) {
            return NativeRouteResult.Failure(NativeRouteFailureCode.UNSUPPORTED_PROFILE)
        }
        val selectedPack = registry.select(request.origin, request.destination)
            ?: return NativeRouteResult.Failure(
                NativeRouteFailureCode.NO_COVERING_ROUTING_PACK,
            )
        val selectedActor = try {
            actorHolder.actorFor(selectedPack)
        } catch (_: Exception) {
            return NativeRouteResult.Failure(NativeRouteFailureCode.ROUTING_PACK_UNAVAILABLE)
        }
        val started = SystemClock.elapsedRealtime()
        val response = try {
            selectedActor.actor.valhalla.route(
                RouteRequest(
                    locations = listOf(
                        RoutingWaypoint(
                            lat = request.origin.latitude,
                            lon = request.origin.longitude,
                        ),
                        RoutingWaypoint(
                            lat = request.destination.latitude,
                            lon = request.destination.longitude,
                        ),
                    ),
                    costing = CostingModel.pedestrian,
                    id = request.requestId,
                    directionsOptions = DirectionsOptions(
                        directionsType = DirectionsOptions.DirectionsType.none,
                        format = DirectionsOptions.Format.json,
                        shapeFormat = DirectionsOptions.ShapeFormat.polyline6,
                    ),
                ),
            )
        } catch (error: ValhallaException.Internal) {
            return NativeRouteResult.Failure(classifyValhallaFailure(error.message))
        } catch (_: Exception) {
            return NativeRouteResult.Failure(NativeRouteFailureCode.ROUTING_FAILURE)
        }
        val routeMs = SystemClock.elapsedRealtime() - started
        if (response !is ValhallaResponse.Json) {
            return NativeRouteResult.Failure(NativeRouteFailureCode.ROUTING_FAILURE)
        }
        val trip = response.jsonResponse.trip
        if (trip.status != 0 || trip.legs.isEmpty()) {
            return NativeRouteResult.Failure(NativeRouteFailureCode.NO_ROUTE)
        }
        val geometry = try {
            trip.legs.flatMapIndexed { index, leg ->
                decodePolyline6(leg.shape).let { points ->
                    if (index == 0) points else points.drop(1)
                }
            }
        } catch (_: IllegalArgumentException) {
            return NativeRouteResult.Failure(NativeRouteFailureCode.ROUTING_FAILURE)
        }
        if (geometry.size !in 2..MAX_LOCAL_ROUTE_VERTICES) {
            return NativeRouteResult.Failure(NativeRouteFailureCode.ROUTE_TOO_LARGE)
        }
        val measurement = selectedActor.actor.measurement
        return NativeRouteResult.Success(
            profile = request.profile,
            engine = ENGINE_ID,
            engineVersion = ENGINE_VERSION,
            packId = selectedPack.packId,
            distanceMeters = trip.summary.length * 1_000.0,
            durationSeconds = trip.summary.time,
            geometry = geometry,
            measurements = NativeRouteMeasurements(
                coldStart = selectedActor.coldStart,
                engineInitializationMs = if (selectedActor.coldStart) {
                    measurement.elapsedMs
                } else {
                    0
                },
                routeMs = routeMs,
                memoryBeforeInitializationBytes = measurement.memoryBeforeBytes,
                memoryAfterInitializationBytes = measurement.memoryAfterBytes,
                memoryAfterRouteBytes = processPssBytes(),
            ),
        ).takeIf(NativeRouteResult.Success::isValid)
            ?: NativeRouteResult.Failure(NativeRouteFailureCode.ROUTING_FAILURE)
    }

    private fun initializeActor(pack: RoutingPack): ValhallaActor {
        val before = processPssBytes()
        val started = SystemClock.elapsedRealtime()
        val config = ValhallaConfigBuilder()
            .withTileExtract(pack.tileArchive.absolutePath)
            .build()
        val created = Valhalla(applicationContext, config)
        return ValhallaActor(
            valhalla = created,
            measurement = InitializationMeasurement(
                elapsedMs = SystemClock.elapsedRealtime() - started,
                memoryBeforeBytes = before,
                memoryAfterBytes = processPssBytes(),
            ),
        )
    }

    private fun processPssBytes(): Long = Debug.getPss() * 1_024L

    private data class ValhallaActor(
        val valhalla: Valhalla,
        val measurement: InitializationMeasurement,
    )

    private data class InitializationMeasurement(
        val elapsedMs: Long,
        val memoryBeforeBytes: Long,
        val memoryAfterBytes: Long,
    )

    companion object {
        private const val ENGINE_ID = "valhalla-mobile"
        private const val ENGINE_VERSION = "0.5.1/valhalla-3.6.3"
    }
}

private fun classifyValhallaFailure(message: String?): NativeRouteFailureCode =
    if (message?.contains("code=170") == true ||
        message?.contains("code=171") == true ||
        message?.contains("code=442") == true
    ) {
        NativeRouteFailureCode.NO_ROUTE
    } else {
        NativeRouteFailureCode.ROUTING_FAILURE
    }

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
            throw IllegalArgumentException("polyline exceeds vertex limit")
        }
    }
    return coordinates
}

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
