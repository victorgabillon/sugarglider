package io.github.victorgabillon.sugarglider

import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.security.MessageDigest
import kotlin.math.max
import kotlin.math.min
import org.json.JSONArray
import org.json.JSONObject

internal const val ELEVATION_ALGORITHM = "distance-box-v1"
internal const val ELEVATION_NUMERICAL_TOLERANCE = 1e-7
internal data class ElevationPoint(val index: Int, val distance: Double, val height: Double?)
internal data class ElevationInput(val source: String, val geometry: String, val profile: String,
    val distance: Double, val heightReference: String, val samples: List<ElevationPoint>) {
    init {
        require(Regex("[a-f0-9]{64}").matches(source) && Regex("[a-f0-9]{64}").matches(geometry))
        require(LocalRouteProfile.entries.any { it.wireValue == profile })
        require(distance.isFinite() && distance > 0 && distance <= 200_000)
        require(heightReference.length in 1..200 && samples.size in 2..MAX_NATIVE_HEIGHT_SAMPLES)
        require(samples.first().distance == 0.0 && samples.last().distance == distance)
        samples.forEachIndexed { index, sample ->
            require(sample.index == index && sample.distance.isFinite() && sample.distance in 0.0..distance)
            require(index == 0 || sample.distance > samples[index - 1].distance)
            require(sample.height == null || sample.height.isFinite() && sample.height in -16_384.0..16_384.0)
        }
    }
}
internal data class ElevationPolicy(val radius: Double = 50.0, val gap: Double = 100.0) {
    init { require(radius.isFinite() && (radius == 0.0 || radius in 1.0..500.0)); require(gap.isFinite() && gap > 0 && gap <= 1_000) }
    fun json(): JSONObject = JSONObject().put("smoothing_radius_m", radius).put("maximum_gap_m", gap)
        .put("boundary_policy", "constant-extension-retain-endpoints").put("missing_policy", "split-no-fill")
}

/** Portable PR89 reference port. No IO, native calls, interpolation across gaps or UI work. */
internal object DistanceBoxElevation {
    fun profileDigest(input: ElevationInput): String {
        val bytes = ByteArrayOutputStream()
        DataOutputStream(bytes).use { out ->
            out.write("sugarglider-elevation-profile-v1\u0000".toByteArray(Charsets.UTF_8))
            for (value in listOf(input.source, input.geometry, input.profile, input.heightReference)) {
                val encoded = value.toByteArray(Charsets.UTF_8); out.writeInt(encoded.size); out.write(encoded)
            }
            out.writeDouble(input.distance); out.writeInt(input.samples.size)
            for (point in input.samples) {
                out.writeInt(point.index); out.writeDouble(point.distance); out.writeByte(if (point.height == null) 0 else 1)
                point.height?.let(out::writeDouble)
            }
        }
        return MessageDigest.getInstance("SHA-256").digest(bytes.toByteArray()).joinToString("") { "%02x".format(it) }
    }

    fun analyze(input: ElevationInput, policy: ElevationPolicy = ElevationPolicy()): JSONObject {
        val points = input.samples
        val runs = mutableListOf<IntRange>(); var first: Int? = null
        points.forEachIndexed { index, point ->
            if (first != null && (point.height == null || point.distance - points[index - 1].distance > policy.gap)) {
                runs.add(first until index); first = null
            }
            if (point.height != null && first == null) first = index
        }
        first?.let { runs.add(it..points.lastIndex) }
        val filtered = arrayOfNulls<Double>(points.size); val indices = arrayOfNulls<Int>(points.size)
        val rawUp = mutableListOf<Double>(); val rawDown = mutableListOf<Double>()
        val up = mutableListOf<Double>(); val down = mutableListOf<Double>(); val lengths = mutableListOf<Double>()
        val segments = JSONArray()
        runs.forEachIndexed { segment, run ->
            val original = run.map { requireNotNull(points[it].height) }.toDoubleArray()
            val distances = run.map { points[it].distance - points[run.first].distance }.toDoubleArray()
            val smoothed = smooth(original, distances, policy.radius)
            val raw = changes(original); val result = changes(smoothed)
            require(result.first <= raw.first + ELEVATION_NUMERICAL_TOLERANCE && result.second <= raw.second + ELEVATION_NUMERICAL_TOLERANCE) {
                "elevation smoothing increased variation"
            }
            if (run.last > run.first) { rawUp.add(raw.first); rawDown.add(raw.second); up.add(result.first); down.add(result.second) }
            val length = points[run.last].distance - points[run.first].distance
            lengths.add(length)
            segments.put(JSONObject().put("first_index", run.first).put("last_index", run.last).put("distance_m", length))
            run.forEachIndexed { local, index -> filtered[index] = smoothed[local]; indices[index] = segment }
        }
        val available = points.mapNotNull { it.height }; val analyzed = sum(lengths)
        val complete = runs.size == 1 && runs.first() == points.indices
        val ascent = if (up.isEmpty()) null else sum(up); val descent = if (down.isEmpty()) null else sum(down)
        return JSONObject().put("schema_version", 1).put("algorithm_version", ELEVATION_ALGORITHM).put("parameters", policy.json())
            .put("source_sha256", input.source).put("geometry_sha256", input.geometry).put("profile_sha256", profileDigest(input))
            .put("routing_profile", input.profile).put("route_distance_m", input.distance).put("height_reference", input.heightReference)
            .put("coverage", if (complete) "complete" else if (available.isEmpty()) "unavailable" else "partial")
            .put("available_sample_count", available.size).put("analyzed_distance_m", analyzed).put("unknown_distance_m", max(0.0, input.distance - analyzed))
            .put("raw_observed_ascent_m", nullable(if (rawUp.isEmpty()) null else sum(rawUp)))
            .put("raw_observed_descent_m", nullable(if (rawDown.isEmpty()) null else sum(rawDown)))
            .put("observed_ascent_m", nullable(ascent)).put("observed_descent_m", nullable(descent))
            .put("total_ascent_m", nullable(if (complete) ascent else null)).put("total_descent_m", nullable(if (complete) descent else null))
            .put("minimum_height_m", nullable(available.minOrNull())).put("maximum_height_m", nullable(available.maxOrNull())).put("segments", segments)
            .put("samples", JSONArray(points.mapIndexed { index, point -> JSONObject().put("index", point.index).put("distance_m", point.distance)
                .put("height_m", nullable(point.height)).put("filtered_height_m", nullable(filtered[index])).put("segment_index", indices[index] ?: JSONObject.NULL) }))
    }

    private fun smooth(heights: DoubleArray, distances: DoubleArray, radius: Double): DoubleArray {
        if (heights.size <= 2 || radius == 0.0) return heights
        val origin = heights[0]; val offsets = heights.map { it - origin }; val count = heights.size - 1
        val tree = DoubleArray(2 * count)
        for (index in 0 until count) tree[count + index] = (offsets[index] + offsets[index + 1]) * 0.5 * (distances[index + 1] - distances[index])
        for (index in count - 1 downTo 1) tree[index] = tree[index * 2] + tree[index * 2 + 1]
        fun whole(start: Int, end: Int): Double {
            var left = start + count; var right = end + count; val parts = mutableListOf<Double>()
            while (left < right) {
                if (left % 2 == 1) parts.add(tree[left++])
                if (right % 2 == 1) parts.add(tree[--right])
                left /= 2; right /= 2
            }
            return sum(parts)
        }
        fun partial(edge: Int, start: Double, end: Double): Double {
            val width = distances[edge + 1] - distances[edge]; val delta = offsets[edge + 1] - offsets[edge]
            val a = offsets[edge] + delta * ((start - distances[edge]) / width)
            val b = offsets[edge] + delta * ((end - distances[edge]) / width)
            return (a + b) * 0.5 * (end - start)
        }
        val low = heights.min(); val high = heights.max()
        return DoubleArray(heights.size) { index ->
            if (index == 0 || index == heights.lastIndex) heights[index] else {
                val center = distances[index]; val left = max(0.0, center - radius); val right = min(distances.last(), center + radius)
                val first = bound(distances, left, true) - 1; val last = bound(distances, right, false) - 1
                val extension = offsets.last() * max(0.0, center + radius - distances.last())
                val area = if (first == last) partial(first, left, right) + extension else sum(listOf(
                    partial(first, left, distances[first + 1]), whole(first + 1, last), partial(last, distances[last], right), extension))
                (origin + area / (2 * radius)).coerceIn(low, high)
            }
        }
    }
    private fun bound(values: DoubleArray, key: Double, upper: Boolean): Int {
        var left = 0; var right = values.size
        while (left < right) { val mid = (left + right) / 2; if (values[mid] < key || upper && values[mid] == key) left = mid + 1 else right = mid }
        return left
    }
    private fun changes(values: DoubleArray): Pair<Double, Double> = Pair(
        sum((1 until values.size).map { max(0.0, values[it] - values[it - 1]) }),
        sum((1 until values.size).map { max(0.0, values[it - 1] - values[it]) }))
    // Error-free partial sums, matching the reference's fsum within 1e-7 m.
    private fun sum(values: Iterable<Double>): Double {
        val partials = mutableListOf<Double>()
        for (value in values) {
            var x = value; var i = 0
            for (part in partials.toList()) {
                var y = part
                if (kotlin.math.abs(x) < kotlin.math.abs(y)) { val swap = x; x = y; y = swap }
                val high = x + y; val low = y - (high - x)
                if (low != 0.0) { partials[i] = low; i++ }; x = high
            }
            while (partials.size > i) partials.removeAt(partials.lastIndex)
            partials.add(x)
        }
        return partials.asReversed().fold(0.0) { result, value -> result + value }
    }
    private fun nullable(value: Double?): Any = value ?: JSONObject.NULL
}
