export class ApiError extends Error {
  constructor(message, details = "", code = "api_error", metadata = {}) {
    super(message);
    this.name = "ApiError";
    this.details = details;
    this.code = code;
    this.metadata = metadata;
  }
}

async function responseError(response) {
  let body;
  try { body = await response.json(); } catch { body = null; }
  const publicError = body?.error && typeof body.error === "object" ? body.error : {};
  const code = publicError.code ?? `http_${response.status}`;
  const message = publicError.message ?? `The server returned HTTP ${response.status}.`;
  const metadata = {
    point_index: Number.isInteger(publicError.point_index) ? publicError.point_index : null,
    point_id: typeof publicError.point_id === "string" ? publicError.point_id : null,
    point_name: typeof publicError.point_name === "string" ? publicError.point_name : null,
    snap_distance_m: typeof publicError.snap_distance_m === "number" ? publicError.snap_distance_m : null,
    maximum_snap_distance_m: typeof publicError.maximum_snap_distance_m === "number"
      ? publicError.maximum_snap_distance_m
      : null,
    profile: typeof publicError.profile === "string" ? publicError.profile : null,
    suggestion: typeof publicError.suggestion === "string" ? publicError.suggestion : null,
  };
  const safeDetails = {
    status: response.status,
    code,
    ...Object.fromEntries(Object.entries(metadata).filter(([, value]) => value !== null)),
  };
  return new ApiError(message, JSON.stringify(safeDetails, null, 2), code, metadata);
}

export async function getConfig() {
  const response = await fetch("/v1/ui/config", { headers: { Accept: "application/json" } });
  if (!response.ok) throw await responseError(response);
  return response.json();
}

export async function getRoutingProfiles() {
  const response = await fetch("/v2/routing-profiles", { headers: { Accept: "application/json" } });
  if (!response.ok) throw await responseError(response);
  return response.json();
}

export async function getPoiStatus() {
  const response = await fetch("/v1/pois/status", { headers: { Accept: "application/json" } });
  if (!response.ok) throw await responseError(response);
  return response.json();
}

export async function searchPois(request, signal) {
  const response = await fetch("/v1/pois/search", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok) throw await responseError(response);
  return response.json();
}

export async function generatePlan(request, signal) {
  const response = await fetch("/v2/plans/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok) throw await responseError(response);
  return response.json();
}

export async function visualizeRoute(route, signal) {
  const response = await fetch("/v2/plans/visualization", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(route),
    signal,
  });
  if (!response.ok) throw await responseError(response);
  return response.json();
}

export async function exportPlanCandidate(candidate) {
  const response = await fetch("/v2/plans/gpx", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/gpx+xml" },
    body: JSON.stringify({ schema_version: 1, candidate }),
  });
  if (!response.ok) throw await responseError(response);
  return { blob: await response.blob(), filename: attachmentFilename(response.headers.get("Content-Disposition")) };
}

function attachmentFilename(header) {
  const match = header?.match(/filename="?([^";]+)"?/i);
  return match?.[1] ?? "sugarglider-route.gpx";
}
