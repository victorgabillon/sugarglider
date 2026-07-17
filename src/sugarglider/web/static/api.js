export class ApiError extends Error {
  constructor(message, details = "", code = "api_error") {
    super(message);
    this.name = "ApiError";
    this.details = details;
    this.code = code;
  }
}

async function responseError(response) {
  let body;
  try { body = await response.json(); } catch { body = null; }
  const code = body?.error?.code ?? `http_${response.status}`;
  const message = body?.error?.message ?? `The server returned HTTP ${response.status}.`;
  return new ApiError(message, JSON.stringify(body ?? { status: response.status }, null, 2), code);
}

export async function getConfig() {
  const response = await fetch("/v1/ui/config", { headers: { Accept: "application/json" } });
  if (!response.ok) throw await responseError(response);
  return response.json();
}

export async function generateRoutes(request, signal) {
  const response = await fetch("/v1/routes/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok) throw await responseError(response);
  return response.json();
}

export async function visualizeRoute(route, signal) {
  const response = await fetch("/v1/routes/visualization", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(route),
    signal,
  });
  if (!response.ok) throw await responseError(response);
  return response.json();
}

export async function exportRoute(route) {
  const response = await fetch("/v1/routes/gpx/from-result", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/gpx+xml" },
    body: JSON.stringify(route),
  });
  if (!response.ok) throw await responseError(response);
  return { blob: await response.blob(), filename: attachmentFilename(response.headers.get("Content-Disposition")) };
}

function attachmentFilename(header) {
  const match = header?.match(/filename="?([^";]+)"?/i);
  return match?.[1] ?? "sugarglider-route.gpx";
}
