// Synthetic coordinates only. These fixtures deliberately exercise the indexed
// and full-scan paths; results are compared against d894ef7's analyzer.
export const NATURE_PERFORMANCE_CASES = Object.freeze([
  "dense_woodland", "complex_water", "holes", "multipart", "priority_overlays",
  "crossing_boundary", "following_boundary", "near_water", "water_tangency", "water_hole",
  "outside_coverage", "long_route", "repeated_segments", "tiny_segments",
]);

export function naturePerformanceFixture(base, name) {
  let features = [], geometry;
  const feature = (primary, coordinates, protectedArea = false) => {
    const osm_id = features.length + 1;
    const value = { feature_id: `way/${osm_id}`, osm_id, osm_source: "way",
      primary_class: primary, park_or_protected: protectedArea, tags: {}, geometry: coordinates };
    features.push(value);
    return value;
  };
  const polygon = (rings) => ({ type: "Polygon", coordinates: rings });
  const circle = (x, y, radius, count = 512, ripple = 0) => {
    const ring = Array.from({ length: count }, (_, i) => {
      const angle = i * 2 * Math.PI / count, r = radius * (1 + ripple * Math.cos(12 * angle));
      return [x + r * Math.cos(angle), y + r * Math.sin(angle)];
    });
    ring.push([...ring[0]]);
    return ring;
  };
  const box = (x, y, width, height, subdivisions = 1) => {
    const corners = [[x, y], [x + width, y], [x + width, y + height], [x, y + height], [x, y]];
    const ring = [];
    for (let side = 1; side < corners.length; side++) {
      for (let i = 0; i < subdivisions; i++) {
        const a = corners[side - 1], b = corners[side], t = i / subdivisions;
        ring.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
      }
    }
    ring.push([...ring[0]]);
    return ring;
  };
  switch (name) {
    case "dense_woodland":
      for (let x = 0; x < 16; x++) for (let y = 0; y < 16; y++) {
        feature("woodland", polygon([box(.001 + x * .0011, .001 + y * .0011, .001, .001)]));
      }
      geometry = Array.from({ length: 33 }, (_, i) => [i % 2 ? .019 : .0005, .001 + i * .0005]);
      break;
    case "complex_water":
      feature("water", polygon([circle(.01, .01, .007, 2400, .05)]));
      geometry = [[.001, .009], [.019, .011], [.019, .0176], [.001, .0176]];
      break;
    case "holes":
      feature("woodland", polygon([circle(.01, .01, .009), circle(.007, .01, .0015, 256), circle(.013, .01, .0015, 256)]), true);
      geometry = [[0, .01], [.02, .01], [.013, .0115], [.013, .0085]];
      break;
    case "multipart":
      feature("woodland", { type: "MultiPolygon", coordinates: [[circle(.004, .01, .003)], [circle(.016, .01, .003)]] });
      geometry = [[0, .01], [.02, .01], [.01, .019], [.01, .001]];
      break;
    case "priority_overlays":
      for (const [index, category] of ["urban", "water", "woodland", "open_natural", "agriculture"].entries()) {
        feature(category, polygon([circle(.006 + index * .002, .01, .005, 256)]));
      }
      feature(null, polygon([circle(.01, .01, .008)]), true);
      geometry = [[0, .01], [.02, .01], [.01, .019], [.01, .001]];
      break;
    case "crossing_boundary":
    case "following_boundary": {
      const ring = box(.003, .003, .014, .014, 48);
      ring.splice(7, 0, [...ring[7]]); // A valid zero-length consecutive edge.
      feature("woodland", polygon([ring]), true);
      geometry = name === "crossing_boundary" ? [[0, .01], [.02, .01], [.01, 0], [.01, .02]]
        : [[.003, .003], [.017, .003], [.017, .017], [.003, .017], [.003, .003]];
      break;
    }
    case "near_water":
      feature("water", polygon([box(.004, .004, .012, .012, 80)]));
      geometry = [[.001, .0165], [.019, .0165], [.019, .018], [.001, .018]];
      break;
    case "water_tangency": {
      feature("water", polygon([box(.004, .004, .012, .012, 80)]));
      const y = .016 + 100 / (6_371_008.8 * Math.PI / 180);
      geometry = [[.003, y], [.017, y], [.017, y + 1e-12], [.003, y + 1e-12], [.003, y - 1e-12], [.017, y - 1e-12]];
      break;
    }
    case "water_hole":
      feature("water", polygon([circle(.01, .01, .008), circle(.01, .01, .003, 256)]));
      geometry = [[.007, .01], [.013, .01], [.01, .0128], [.01, .0072]];
      break;
    case "outside_coverage":
      feature("woodland", polygon([circle(.01, .01, .012)]), true);
      geometry = [[-.005, .01], [.025, .01], [.01, -.005], [.01, .025]];
      break;
    case "long_route":
      feature("woodland", polygon([box(.001, .001, .018, .018)]), true);
      geometry = Array.from({ length: 20_000 }, (_, i) => [.005 + i * .0000005, .01 + Math.sin(i / 23) * .002]);
      break;
    case "repeated_segments":
      feature("woodland", polygon([circle(.01, .01, .008, 256)]), true);
      geometry = Array.from({ length: 301 }, (_, i) => [i % 2 ? .019 : .001, .01 + (i % 3) * 1e-12]);
      break;
    case "tiny_segments":
      feature("woodland", polygon([box(.003, .003, .014, .014, 48)]));
      geometry = [[.01, .003], [.01 + 1e-14, .003], [.01, .003 + 1e-10], [.01, .003], [.01, .003], [.017, .01]];
      break;
    default: throw Error(`Unknown synthetic nature case: ${name}`);
  }
  features.sort((a, b) => a.feature_id < b.feature_id ? -1 : a.feature_id > b.feature_id ? 1 : 0);
  const nature = { metadata: { ...structuredClone(base.nature.metadata), feature_count: features.length, category_counts: {} }, features };
  for (const f of features) {
    for (const category of [f.primary_class, f.park_or_protected ? "park_or_protected" : null]) {
      if (category !== null) nature.metadata.category_counts[category] = (nature.metadata.category_counts[category] ?? 0) + 1;
    }
  }
  return { manifest: structuredClone(base.manifest), nature,
    route: { geometry, distance_m: name === "long_route" ? 35_000 : 5000, pack_id: base.manifest.components.routing.component_id } };
}
