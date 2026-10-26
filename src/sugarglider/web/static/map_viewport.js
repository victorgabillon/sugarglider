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

// Screen rectangles only. Find the nearest position whose painted pin fits in
// the viewport without covering the actual toolbar, dock or source credits.
export function unobstructedPointOffset(point, width, height, obstacles, footprint = { width: 48, height: 80 }) {
  const half = footprint.width / 2, tall = footprint.height, below = footprint.bottom ?? 0, gap = 8;
  const xs = [point.x, half + gap, width - half - gap];
  const ys = [point.y, tall - below + gap, height - below - gap];
  for (const r of obstacles) {
    xs.push(r.left - half - gap, r.right + half + gap);
    ys.push(r.top - below - gap, r.bottom + tall - below + gap);
  }
  let best = null, distance = Infinity;
  for (const x of xs) for (const y of ys) {
    const pin = { left: x - half, right: x + half, top: y - tall + below, bottom: y + below };
    if (pin.left < 0 || pin.right > width || pin.top < 0 || pin.bottom > height
      || obstacles.some(r => pin.left < r.right && pin.right > r.left && pin.top < r.bottom && pin.bottom > r.top)) continue;
    const squared = (point.x - x) ** 2 + (point.y - y) ** 2;
    if (squared < distance) { best = [point.x - x, point.y - y]; distance = squared; }
  }
  return best && distance > .01 ? best : null;
}
