// Screen-space correction only: no route coordinates or camera state are stored.
export function pointVisibilityOffset(point, width, height) {
  if (!point || ![point.x, point.y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) return null;
  // Leave room for the marker body and the existing map controls/legend.
  const xMargin = Math.min(96, width / 3);
  const topMargin = Math.min(80, height / 3);
  const bottomMargin = Math.min(128, height / 2);
  const x = Math.max(xMargin, Math.min(width - xMargin, point.x));
  const y = Math.max(topMargin, Math.min(height - bottomMargin, point.y));
  return x === point.x && y === point.y ? null : [point.x - x, point.y - y];
}

export function keepMapCoordinateVisible(map, coordinate) {
  if (!map || !Array.isArray(coordinate) || coordinate.length !== 2 || !coordinate.every(Number.isFinite)) return false;
  const point = map.project(coordinate);
  // Canvas CSS dimensions can lag resize() by a frame. Measure the visible
  // container against the already resized projection instead.
  const container = map.getContainer();
  const offset = pointVisibilityOffset(point, container.clientWidth, container.clientHeight);
  if (!offset) return false;
  map.panBy(offset, { duration: 0 });
  return true;
}
