const EARTH_RADIUS_M = 6371008.8;

export function haversineDistance(start, end) {
  const radians = (degrees) => degrees * Math.PI / 180;
  const [lon1, lat1] = start;
  const [lon2, lat2] = end;
  const dLat = radians(lat2 - lat1);
  const dLon = radians(lon2 - lon1);
  const value = Math.sin(dLat / 2) ** 2 + Math.cos(radians(lat1)) * Math.cos(radians(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(Math.min(1, value)));
}

function coordinates(elements) {
  return [...elements].map((element) => {
    const lat = Number(element.getAttribute("lat"));
    const lon = Number(element.getAttribute("lon"));
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
    return [lon, lat];
  }).filter(Boolean);
}

function descendants(parent, name) {
  return parent.getElementsByTagNameNS("*", name);
}

export function parseGpx(text, filename) {
  const document = new DOMParser().parseFromString(text, "application/xml");
  if (document.querySelector("parsererror")) throw new Error("The GPX file is malformed XML.");
  const tracks = [...descendants(document, "trk")];
  let segments = tracks.flatMap((track) => [...descendants(track, "trkseg")].map((segment) => coordinates(descendants(segment, "trkpt"))).filter((segment) => segment.length >= 2));
  if (!segments.length) {
    segments = [...descendants(document, "rte")].map((route) => coordinates(descendants(route, "rtept"))).filter((segment) => segment.length >= 2);
  }
  if (!segments.length) throw new Error("The GPX file contains no track or route segment with at least two valid coordinates.");
  const waypoints = [...descendants(document, "wpt")].map((element) => {
    const point = coordinates([element])[0];
    const name = descendants(element, "name")[0]?.textContent?.trim() || "Waypoint";
    return point ? { coordinate: point, name } : null;
  }).filter(Boolean);
  const distanceM = segments.reduce((total, segment) => total + segment.slice(1).reduce((sum, point, index) => sum + haversineDistance(segment[index], point), 0), 0);
  return { filename, segments, waypoints, pointCount: segments.reduce((sum, segment) => sum + segment.length, 0), distanceM };
}

export function gpxFeatureCollection(imported) {
  return {
    type: "FeatureCollection",
    features: imported.segments.map((segment, index) => ({ type: "Feature", id: index, properties: {}, geometry: { type: "LineString", coordinates: segment } })),
  };
}
