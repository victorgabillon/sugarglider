// Presentation of PR91's already validated, immutable analysis. No DEM access,
// smoothing, ascent/descent calculation or geographic nearest-neighbour search.
export function projectElevationProfile(analysis, coordinates, width = 600) {
  if (!analysis || !Array.isArray(analysis.samples) || analysis.samples.length < 2 || analysis.samples.length > 2048
      || !Array.isArray(analysis.segments) || !Number.isFinite(width)
      || !Array.isArray(coordinates) || coordinates.length !== analysis.samples.length
      || !Number.isFinite(analysis.route_distance_m) || analysis.route_distance_m <= 0) {
    throw Error("elevation_presentation_invalid");
  }
  width = Math.max(240, Math.round(width));
  const height = 210, left = 48, right = width - 14, top = 27, bottom = height - 42;
  let minimum = Infinity, maximum = -Infinity;
  for (const sample of analysis.samples) {
    if (sample.filtered_height_m === null) continue;
    minimum = Math.min(minimum, sample.filtered_height_m);
    maximum = Math.max(maximum, sample.filtered_height_m);
  }
  if (minimum === Infinity) return null;
  const padding = Math.max(5, (maximum - minimum) * 0.12);
  const low = minimum - padding, high = maximum + padding;
  const x = distance => left + (right - left) * distance / analysis.route_distance_m;
  const y = altitude => bottom - (bottom - top) * (altitude - low) / (high - low);
  const paths = [], points = [];
  for (let segmentIndex = 0; segmentIndex < analysis.segments.length; segmentIndex++) {
    const segment = analysis.segments[segmentIndex];
    if (!Number.isInteger(segment.first_index) || !Number.isInteger(segment.last_index)
      || segment.first_index < 0 || segment.last_index < segment.first_index || segment.last_index >= analysis.samples.length) {
      throw Error("elevation_presentation_invalid");
    }
    let path = "";
    // Segment boundaries come from native analysis, including singleton runs.
    for (let i = segment.first_index; i <= segment.last_index; i++) {
      const sample = analysis.samples[i];
      if (!Number.isFinite(sample.filtered_height_m) || sample.segment_index !== segmentIndex
        || !Number.isFinite(sample.distance_m) || sample.distance_m < 0 || sample.distance_m > analysis.route_distance_m
        || i > segment.first_index && (sample.distance_m <= analysis.samples[i - 1].distance_m
          || sample.distance_m - analysis.samples[i - 1].distance_m > analysis.parameters.maximum_gap_m)) {
        throw Error("elevation_presentation_invalid");
      }
      path += `${i === segment.first_index ? "M" : "L"}${x(sample.distance_m).toFixed(2)},${y(sample.filtered_height_m).toFixed(2)}`;
    }
    if (segment.first_index === segment.last_index) {
      const sample = analysis.samples[segment.first_index];
      points.push({x:x(sample.distance_m), y:y(sample.filtered_height_m)});
    } else paths.push(path);
  }
  return {width, height, left, right, top, bottom, low, high, x, y, paths, points,
    altitudeTicks:[low, (low + high) / 2, high],
    distanceTicks:[0, analysis.route_distance_m / 2, analysis.route_distance_m]};
}

// First sample at or after progress; O(log n), including repeated geographic
// positions on loops. No route-geometry scan belongs in a pointer frame.
export function elevationSampleIndex(samples, distance) {
  let left = 0, right = samples.length;
  while (left < right) {
    const middle = (left + right) >>> 1;
    if (samples[middle].distance_m < distance) left = middle + 1;
    else right = middle;
  }
  return Math.min(left, samples.length - 1);
}

export function elevationPositionAtDistance(analysis, coordinates, requestedDistance) {
  if (!Number.isFinite(requestedDistance)) return null;
  const distance = Math.max(0, Math.min(analysis.route_distance_m, requestedDistance));
  const samples = analysis.samples, index = elevationSampleIndex(samples, distance);
  const after = samples[index];
  const unavailable = {distance_m:distance, height_m:null, coordinate:null, sample_index:index};
  if (after.distance_m === distance) {
    return after.filtered_height_m === null ? unavailable : {
      distance_m:distance, height_m:after.filtered_height_m, coordinate:coordinates[index], sample_index:index,
    };
  }
  const before = samples[index - 1];
  if (!before || before.segment_index === null || before.segment_index !== after.segment_index
      || before.filtered_height_m === null || after.filtered_height_m === null
      || after.distance_m - before.distance_m > analysis.parameters.maximum_gap_m) return unavailable;
  const fraction = (distance - before.distance_m) / (after.distance_m - before.distance_m);
  return {distance_m:distance,
    height_m:before.filtered_height_m + fraction * (after.filtered_height_m - before.filtered_height_m),
    coordinate:[coordinates[index - 1][0] + fraction * (coordinates[index][0] - coordinates[index - 1][0]),
      coordinates[index - 1][1] + fraction * (coordinates[index][1] - coordinates[index - 1][1])],
    sample_index:index};
}

export function elevationDistanceLabel(distance, routeDistance) {
  return (distance / 1000).toFixed(routeDistance < 1000 ? 3 : 2);
}
